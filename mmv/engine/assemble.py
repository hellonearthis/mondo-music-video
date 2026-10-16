from __future__ import annotations
import json
import subprocess
from pathlib import Path
from .grid import FPS
from .atomic_io import write_text_atomic
PROBE_TIMEOUT_S = 120

def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True)

def probe_frames(path: str | Path) -> int:
    """Count frames in a clip, for verifying H3 honoured the requested length."""
    out = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-count_frames', '-show_entries', 'stream=nb_read_frames', '-of', 'csv=p=0', str(path)], check=True, capture_output=True, text=True, timeout=PROBE_TIMEOUT_S).stdout.strip()
    return int(out) if out.isdigit() else 0

def trim_to_frames(src: str | Path, dest: str | Path, frames: int, *, fps: int=FPS, quality: str='high', video_filter: str | None=None) -> Path:
    """Keep exactly the first `frames` frames.

    high: single encode at the VHS_VideoCombine settings (CRF 6, preset slow).
    low:  single encode at share size (CRF 16, preset slow).
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if quality == 'low':
        crf, preset = ('16', 'slow')
    else:
        crf, preset = ('6', 'slow')
    _run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(src), '-frames:v', str(frames), *(['-vf', video_filter] if video_filter else []), '-c:v', 'libx264', '-crf', crf, '-preset', preset, '-pix_fmt', 'yuv420p', '-an', str(dest)])
    return dest

def extract_audio_span(src: str | Path, dest: str | Path, frames: int, *, fps: int=FPS, sample_rate: int=48000) -> Path:
    """Pull the diegetic audio for exactly the trimmed picture span."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(src), '-t', f'{frames / fps:.6f}', '-ar', str(sample_rate), '-ac', '2', '-c:a', 'pcm_s24le', str(dest)])
    return dest

def concat_video(clips: list[str | Path], dest: str | Path, workdir: str | Path) -> Path:
    """Join trimmed clips in timeline order. Stream copy: no re-encode."""
    workdir, dest = (Path(workdir), Path(dest))
    workdir.mkdir(parents=True, exist_ok=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    listfile = workdir / 'concat_video.txt'
    listfile.write_text(''.join((f"file '{Path(c).resolve()}'\n" for c in clips)))
    _run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', str(listfile), '-c', 'copy', str(dest)])
    return dest

def concat_diegetic(stems: list[str | Path], dest: str | Path, workdir: str | Path, *, crossfade_ms: int=40) -> Path:
    """Join the per-segment diegetic stems with a short crossfade at each seam.

    Each segment's audio was generated independently, so the room tone changes
    abruptly at every join. A few tens of milliseconds of overlap hides it
    without smearing transients.
    """
    workdir, dest = (Path(workdir), Path(dest))
    workdir.mkdir(parents=True, exist_ok=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if len(stems) == 1:
        _run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(stems[0]), '-c:a', 'pcm_s24le', str(dest)])
        return dest
    cmd: list[str] = ['ffmpeg', '-y', '-loglevel', 'error']
    for s in stems:
        cmd += ['-i', str(s)]
    xf = crossfade_ms / 1000.0
    parts, prev = ([], '[0:a]')
    for i in range(1, len(stems)):
        out = f'[a{i}]'
        parts.append(f'{prev}[{i}:a]acrossfade=d={xf}:c1=tri:c2=tri{out}')
        prev = out
    cmd += ['-filter_complex', ';'.join(parts), '-map', prev, '-c:a', 'pcm_s24le', str(dest)]
    _run(cmd)
    return dest

def mux(video: str | Path, song: str | Path, dest: str | Path, *, quality: str='high', audio_bitrate: str='320k') -> Path:
    """Lay the original song over the cut picture. Shortest stream wins.

    high: video stream copied bit-for-bit (already the single CRF-6 encode);
    only the song audio is encoded. Zero added video generation.
    low:  video stream copied bit-for-bit (already the single CRF-16 encode);
    only the song audio is encoded. Zero added video generation.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    venc = ['-c:v', 'copy']
    _run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(video), '-i', str(song), '-map', '0:v:0', '-map', '1:a:0', *venc, '-c:a', 'aac', '-b:a', audio_bitrate, '-shortest', str(dest)])
    return dest

def assemble_run(plan, rendered: dict[str, dict], song: str | Path, outdir: str | Path, *, quality: str='high', stems_dir: str | Path | None=None, overlay: dict | None=None) -> dict[str, str]:
    """Trim, join, and mux a completed run.

    `rendered` maps segment_id -> {"video": path, "audio": path}. Segments with
    no render (a generation that failed and exhausted its retries) are skipped,
    and the timeline closes over the gap rather than aborting the run.
    """
    outdir = Path(outdir)
    work = outdir / 'work'
    work.mkdir(parents=True, exist_ok=True)
    trimmed, stems, report = ([], [], [])
    text_start = 0.0
    for seg in plan.segments:
        got = rendered.get(seg.segment_id)
        if not got or not got.get('video'):
            report.append({'segment': seg.segment_id, 'status': 'missing'})
            continue
        actual = probe_frames(got['video'])
        text_args = {}
        tv = trim_to_frames(got['video'], work / f'{seg.segment_id}.mp4', seg.trim_frames, quality=quality, **text_args)
        text_start += seg.trim_frames / plan.fps
        trimmed.append(tv)
        if got.get('audio'):
            stems.append(extract_audio_span(got['audio'], work / f'{seg.segment_id}.wav', seg.trim_frames))
        report.append({'segment': seg.segment_id, 'status': 'ok', 'requested_frames': seg.gen_frames, 'actual_frames': actual, 'trimmed_to': seg.trim_frames, 'frame_delta': actual - seg.gen_frames})
    if not trimmed:
        raise RuntimeError('nothing rendered; nothing to assemble')
    silent = concat_video(trimmed, work / 'picture.mp4', work)
    audio_track = song
    final = mux(silent, audio_track, outdir / f'{plan.slug}.mp4', quality=quality)
    out = {'video': str(final), 'report': str(outdir / 'assembly_report.json')}
    if stems:
        out['diegetic_stem'] = str(concat_diegetic(stems, outdir / f'{plan.slug}_diegetic.wav', work))
    write_text_atomic(outdir / 'assembly_report.json', json.dumps(report, indent=2))
    return out

def normalize_clip(src: str | Path, dest: str | Path, *, quality: str='high') -> Path:
    """Encode one clip once at the lane recipe, full length, no audio.

    Attached elements (the ident) enter the picture concat as
    first-generation prints matching the trimmed segments, so the
    stream-copy concat and the single-encode contract both hold.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if quality == 'low':
        crf, preset = ('16', 'slow')
    else:
        crf, preset = ('6', 'slow')
    _run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(src), '-c:v', 'libx264', '-crf', crf, '-preset', preset, '-pix_fmt', 'yuv420p', '-an', str(dest)])
    return dest

def extract_audio(src: str | Path, dest: str | Path, *, sample_rate: int=48000) -> Path:
    """Pull a clip's audio track to PCM; synthesize silence if absent."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    probe = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', str(src)], capture_output=True, text=True, timeout=PROBE_TIMEOUT_S)
    if probe.stdout.strip():
        _run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(src), '-ar', str(sample_rate), '-ac', '2', '-c:a', 'pcm_s16le', str(dest)])
    else:
        dur = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(src)], capture_output=True, text=True, timeout=PROBE_TIMEOUT_S).stdout.strip() or '4'
        _run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'lavfi', '-i', f'anullsrc=r={sample_rate}:cl=stereo', '-t', dur, '-c:a', 'pcm_s16le', str(dest)])
    return dest

def concat_audio(clips: list[str | Path], dest: str | Path, workdir: str | Path) -> Path:
    """Join PCM audio files in order. Stream copy: no re-encode."""
    workdir, dest = (Path(workdir), Path(dest))
    workdir.mkdir(parents=True, exist_ok=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    listfile = workdir / 'concat_audio.txt'
    listfile.write_text(''.join((f"file '{Path(c).resolve()}'\n" for c in clips)))
    _run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', str(listfile), '-c', 'copy', str(dest)])
    return dest

def _probe_audio(path: str | Path) -> tuple[int, float]:
    """(sample_rate, duration_seconds) of an audio file, via ffprobe."""
    sr = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=sample_rate', '-of', 'csv=p=0', str(path)], capture_output=True, text=True, timeout=PROBE_TIMEOUT_S).stdout.strip()
    dur = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(path)], capture_output=True, text=True, timeout=PROBE_TIMEOUT_S).stdout.strip()
    try:
        sample_rate = int(sr)
    except ValueError:
        sample_rate = 48000
    try:
        duration = float(dur)
    except ValueError:
        duration = 0.0
    return (sample_rate, duration)

def assemble_run_with_ident(plan, rendered: dict[str, dict], song: str | Path, ident_clip: str | Path, position: str, outdir: str | Path, *, quality: str='high', stems_dir: str | Path | None=None, overlay: dict | None=None) -> dict[str, str]:
    """Assemble a with-ident final as ONE encode per raw source.

    The ident is normalized once at the lane recipe and stream-copy
    concatenated with the trimmed segments; the ident's audio (or digital
    silence) is concatenated with the song before the single mux. This
    is a separate first-generation print, never a re-encode of a final.
    """
    outdir = Path(outdir)
    work = outdir / 'work'
    work.mkdir(parents=True, exist_ok=True)
    trimmed, report = ([], [])
    text_start = 0.0
    for seg in plan.segments:
        got = rendered.get(seg.segment_id)
        if not got or not got.get('video'):
            report.append({'segment': seg.segment_id, 'status': 'missing'})
            continue
        actual = probe_frames(got['video'])
        text_args = {}
        tv = trim_to_frames(got['video'], work / f'{seg.segment_id}.mp4', seg.trim_frames, quality=quality, **text_args)
        text_start += seg.trim_frames / plan.fps
        trimmed.append(tv)
        report.append({'segment': seg.segment_id, 'status': 'ok', 'requested_frames': seg.gen_frames, 'actual_frames': actual, 'trimmed_to': seg.trim_frames, 'frame_delta': actual - seg.gen_frames})
    if not trimmed:
        raise RuntimeError('nothing rendered; nothing to assemble')
    ident_video = normalize_clip(ident_clip, work / 'ident_video.mp4', quality=quality)
    if position == 'start':
        picture_clips = [ident_video] + trimmed
    else:
        picture_clips = trimmed + [ident_video]
    silent = concat_video(picture_clips, work / 'picture.mp4', work)
    ident_audio = extract_audio(ident_clip, work / 'ident_audio.wav')
    song_pcm = work / 'song_pcm.wav'
    _run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(song), '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le', str(song_pcm)])
    if position == 'start':
        full_audio = concat_audio([ident_audio, song_pcm], work / 'audio.wav', work)
    else:
        full_audio = concat_audio([song_pcm, ident_audio], work / 'audio.wav', work)
    audio_track = full_audio
    final = mux(silent, audio_track, outdir / f'{plan.slug}.mp4', quality=quality)
    report.append({'segment': 'ident', 'status': 'ok', 'position': position})
    out = {'video': str(final), 'report': str(outdir / 'assembly_report.json')}
    write_text_atomic(outdir / 'assembly_report.json', json.dumps(report, indent=2))
    return out
