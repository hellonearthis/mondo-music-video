"""Small independent song planner and FFmpeg assembly helpers."""
from __future__ import annotations

import json
import math
import shutil
import subprocess


def duration(path):
    if not shutil.which("ffprobe"):
        raise ValueError("FFprobe is missing. Install FFmpeg and add it to PATH")
    try:
        result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "json", str(path)], check=True, capture_output=True, timeout=20)
        seconds = float(json.loads(result.stdout)["format"]["duration"])
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError("Invalid duration")
        return seconds
    except (subprocess.SubprocessError, KeyError, ValueError) as exc:
        raise ValueError("Cannot read media duration") from exc


def plan(seconds, backend, segment_seconds=8, bpm=None):
    # Optional BPM aligns spans to whole bars without copying the studio planner.
    span = float(segment_seconds)
    if bpm:
        bar = 240 / float(bpm)
        span = max(bar, math.floor(span / bar) * bar)
    max_span = 14 if backend == "local_h3" else 15
    span = min(max_span, max(1, span))
    total = max(1, math.ceil(seconds * 24))
    step = max(1, round(span * 24))
    segments = []
    for start in range(0, total, step):
        frames = min(step, total - start)
        if backend == "local_h3":
            gen_frames = max(5, math.ceil((frames - 5) / 17) * 17 + 5)
            gen_seconds = gen_frames / 24
        else:
            gen_seconds = max(4, math.ceil(frames / 24))
            gen_frames = gen_seconds * 24
        segments.append({"start": start / 24, "frames": frames,
                         "gen_frames": gen_frames, "duration": gen_seconds})
    return segments


def slice_song(context, song, output, start, seconds):
    # Pad a final short passage so an upstream renderer receives its requested duration.
    context.command(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", str(start),
                     "-i", song, "-af", "apad", "-t", str(seconds), "-ar", "44100",
                     "-ac", "2", output])


def assemble(context, clips, segments, song, directory, width, height, *, start_ident=None, end_ident=None):
    if not clips or len(clips) != len(segments):
        raise ValueError("Missing generated clips")
    trimmed = []
    for index, (source, segment) in enumerate(zip(clips, segments)):
        context.check()
        available = duration(source)
        if available + 1 / 24 < segment["frames"] / 24:
            raise ValueError("Renderer returned a clip shorter than its planned music passage")
        target = directory / f"trim-{index:04d}.mp4"
        context.command(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", source,
                         "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                         f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fps=24,setsar=1",
                         "-frames:v", str(segment["frames"]), "-an", "-c:v", "libx264",
                         "-crf", "18", "-pix_fmt", "yuv420p", target])
        trimmed.append(target)
    # Generated filenames are controlled and contain no quotes or user text.
    listing = directory / "concat.txt"
    listing.write_text("".join(f"file '{p.name}'\n" for p in trimmed), encoding="utf-8")
    master = directory / "music-video.mp4"
    context.command(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "concat", "-safe", "1",
                     "-i", listing, "-i", song, "-map", "0:v:0", "-map", "1:a:0",
                     "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-shortest",
                     "-movflags", "+faststart", master])
    # Idents use their own silence so the song itself remains intact.
    if start_ident or end_ident:
        inputs = [x for x in (start_ident, master, end_ident) if x]
        argv = ["ffmpeg", "-nostdin", "-y", "-v", "error"]
        for path in inputs:
            argv.extend(["-i", path])
        filters, pairs = [], []
        for index, path in enumerate(inputs):
            filters.append(f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                           f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fps=24,setsar=1[v{index}]")
            if path == master:
                filters.append(f"[{index}:a]aresample=48000,aformat=channel_layouts=stereo[a{index}]")
            else:
                filters.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={duration(path)},"
                               f"asetpts=PTS-STARTPTS[a{index}]")
            pairs.append(f"[v{index}][a{index}]")
        filters.append("".join(pairs) + f"concat=n={len(inputs)}:v=1:a=1[v][a]")
        output = directory / "music-video-with-credits.mp4"
        context.command(argv + ["-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[a]",
                                 "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                                 "-c:a", "aac", "-movflags", "+faststart", output])
        master = output
    return master
