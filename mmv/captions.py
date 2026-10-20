"""Lyric captions: the timed lyric lines as a subtitle file, optionally burned into the finished video.

Applied after assembly with FFmpeg, outside the original engine, and never touches a prompt: the lines come from the lyrics the user
already supplied. `sidecar` writes lyrics.srt next to the video and re-encodes nothing; `burned` also draws the words with libass.
The burned video keeps its exact frame count, duration and audio (copied); the video without captions is kept next to it.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

MODES = ('off', 'sidecar', 'burned')
MIN_SECONDS = 0.4               # shorter cues are unreadable
SRT_NAME, UNCAPTIONED_NAME = 'lyrics.srt', 'music-video-uncaptioned.mp4'
NO_LINES = 'Lyric captions are on, but there are no timed lyric lines yet, so this video would have none. Detect or paste the lyrics in the score editor and re-plan.'
SKIPPED_TIMINGS = ('interpolated', 'uncertain')   # guessed or unconfirmed windows would caption the wrong moment


def clean(settings):
    """Validated settings (or None when off)."""
    if not settings or settings.get('mode', 'off') == 'off':
        return None
    mode = settings.get('mode')
    if mode not in MODES:
        raise ValueError('Lyric captions are off, sidecar or burned')
    return {'mode': mode, **look(settings)}


def cues(lines, offset_s, song_s, total_s):
    """[(start, end, text)] on the video clock: lines shifted by the opening length, clamped to the song's own stretch of the video
    (so none lands on an ident) and to the video itself, never overlapping.

    Lines whose timing was only guessed are left out. A line shorter than MIN_SECONDS is held up to the next line or the video end."""
    ordered = sorted((l for l in lines if l.get('timing') not in SKIPPED_TIMINGS), key=lambda l: (l['start'], l['end']))
    shifted = [(l['start'] + offset_s, l['end'] + offset_s, l['text']) for l in ordered]
    song_end = min(offset_s + song_s, total_s)
    result = []
    for i, (start, end, text) in enumerate(shifted):
        limit = min(shifted[i + 1][0] if i + 1 < len(shifted) else song_end, song_end)
        end = min(max(end, start + MIN_SECONDS), limit)
        if start < song_end and end - start > 0.05:
            result.append((round(start, 3), round(end, 3), text))
    return result


def _stamp(seconds, comma=True):
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}' if comma else f'{h}:{m:02d}:{s:02d}.{ms // 10:02d}'      # SRT, or ASS centiseconds


def to_srt(items):
    return ''.join(f'{i}\n{_stamp(a)} --> {_stamp(b)}\n{t}\n\n' for i, (a, b, t) in enumerate(items, 1))


def _ass_text(text):
    """Plain text for an ASS event: braces would start override tags and a backslash would escape, so neither is passed through."""
    return text.replace('\\', '/').replace('{', '(').replace('}', ')')


# Colours are ASS &HAABBGGRR (AA 00 = opaque). `tag` is an override block put in front of every line.
STYLES = {
    'classic': {'colour': '&H00FFFFFF', 'outline': '&H00000000', 'back': '&H80000000', 'bold': 1, 'box': 0, 'weight': 1.0, 'tag': ''},
    'bold': {'colour': '&H0000F0FF', 'outline': '&H00000000', 'back': '&H00000000', 'bold': 1, 'box': 0, 'weight': 1.8, 'upper': True,
             'tag': '\\fscx105'},
    'neon': {'colour': '&H00FFFFFF', 'outline': '&H00FF40FF', 'back': '&H00FF40FF', 'bold': 1, 'box': 0, 'weight': 1.4,
             'tag': '\\blur3\\shad0'},
    'box': {'colour': '&H00FFFFFF', 'outline': '&H99000000', 'back': '&H99000000', 'bold': 0, 'box': 3, 'weight': 0.6, 'tag': ''},
}
POSITIONS = {'bottom': 2, 'middle': 5, 'top': 8}            # ASS numpad alignment: centred, low / middle / high
SIZES = {'small': 0.04, 'medium': 0.055, 'large': 0.075}    # of the frame height
FADE_MS = 180


def look(settings):
    """Validated style, position and size from the settings, with defaults."""
    chosen = {'style': (settings or {}).get('style') or 'classic', 'position': (settings or {}).get('position') or 'bottom',
              'size': (settings or {}).get('size') or 'medium'}
    for key, table in (('style', STYLES), ('position', POSITIONS), ('size', SIZES)):
        if chosen[key] not in table:
            raise ValueError(f'Caption {key} must be one of ' + ', '.join(table))
    return chosen


def to_ass(items, width, height, chosen=None):
    """An ASS script sized to the video: the chosen style, centred at the chosen height, fading in and out softly."""
    chosen = look(chosen)
    style = STYLES[chosen['style']]
    size, margin = max(round(height * SIZES[chosen['size']]), 14), max(round(height * 0.07), 10)
    outline = max(round(size / 14 * style['weight']), 2)
    header = ('[Script Info]\nScriptType: v4.00+\nWrapStyle: 0\nScaledBorderAndShadow: yes\n'
              f'PlayResX: {width}\nPlayResY: {height}\n\n[V4+ Styles]\n'
              'Format: Name,Fontname,Fontsize,PrimaryColour,OutlineColour,BackColour,Bold,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV\n'
              f"Style: Lyric,Sans,{size},{style['colour']},{style['outline']},{style['back']},{style['bold']},{style['box'] or 1},"
              f"{outline if not style['box'] else max(size // 5, 4)},0,{POSITIONS[chosen['position']]},{margin},{margin},{margin}\n\n"
              '[Events]\nFormat: Layer,Start,End,Style,Text\n')
    fade = f"{{\\fad({FADE_MS},{FADE_MS}){style['tag']}}}"
    shape = (lambda t: t.upper()) if style.get('upper') else (lambda t: t)
    return header + ''.join(f'Dialogue: 0,{_stamp(a, False)},{_stamp(b, False)},Lyric,{fade}{_ass_text(shape(t))}\n' for a, b, t in items)


def plan_run(settings, lines, offset_s, song_s, total_s):
    """The prepared record for a production: the mode and the cues (with a note when there are none), or None when captions are off. The lines are validated here, on
    their own, so captions never depend on (or switch on) lip sync."""
    cleaned = clean(settings)
    if not cleaned:
        return None
    from .lipsync import clean_lines
    items = cues(clean_lines(lines), offset_s, song_s, total_s)
    return {**cleaned, 'cues': items, **({} if items else {'note': NO_LINES})}


def downloads(record):
    """Names of the extra files a finished video offers beside the video itself (a subtitle file and the backup videos)."""
    extras = [(record.get('captions') or {}).get(k) for k in ('srt', 'uncaptioned_copy')] + [(record.get('subliminal') or {}).get('clean_copy')]
    return [name for name in extras if name]


def _probe_size(path):
    done = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,nb_read_frames',
                           '-count_frames', '-of', 'csv=p=0', str(path)], capture_output=True, text=True, timeout=300)
    width, height, frames = done.stdout.strip().split(',')[:3]
    return int(width), int(height), int(frames)


def _run_ffmpeg(argv, cwd):
    done = subprocess.run(argv, capture_output=True, text=True, timeout=1800, cwd=cwd)
    if done.returncode:
        raise ValueError('The captions could not be burned in: ' + done.stderr[-300:])


def burn(source, target, script, run=_run_ffmpeg):
    """Draw the ASS script on the video. Audio is copied. The script is passed by bare name from its own folder so no path needs
    escaping in the filter, on any platform. `run(argv, cwd)` runs FFmpeg (a job passes its cancellable runner)."""
    run(['ffmpeg', '-nostdin', '-y', '-v', 'error', '-i', str(Path(source).resolve()), '-vf', f'ass={script.name}',
         '-map', '0:v', '-map', '0:a?', '-c:v', 'libx264', '-crf', '12', '-preset', 'medium', '-pix_fmt', 'yuv420p',
         '-c:a', 'copy', str(Path(target).resolve())], script.parent)
    return target


def apply_to_run(directory, plan):
    """Write lyrics.srt and, for burned mode, replace the finished video once the captioned one passes a frame-count check.

    The finished video is never modified until the new one is verified; on any failure it is left exactly as it was
    (the .srt, already written, stays and a failed burn is reported as burn_error). Returns a short result record."""
    final = directory / 'music-video.mp4'
    items = [tuple(c) for c in plan['cues']]
    (directory / SRT_NAME).write_text(to_srt(items), encoding='utf-8')
    result = {'mode': plan['mode'], 'cues': len(items), 'srt': SRT_NAME, **({k: plan[k] for k in ('style', 'position', 'size')} if plan['mode'] == 'burned' else {})}
    if plan['mode'] != 'burned':
        return result
    try:
        return {**result, **_burn_in(directory, final, items, plan)}
    except Exception as exc:                    # the sidecar is already written and the video untouched
        return {**result, 'burn_error': str(exc)}


def render(source, target, items, work, chosen=None, run=_run_ffmpeg):
    """Burn the cues into a copy of the video at `target`, in the scratch folder `work`, and check the frame count is unchanged."""
    width, height, before = _probe_size(source)
    script = work / 'captions.ass'
    script.write_text(to_ass(items, width, height, chosen), encoding='utf-8')
    out = burn(source, target, script, run)
    after = _probe_size(out)[2]
    if after != before:
        raise ValueError(f'The captioned video has {after} frames instead of {before}; keeping the original')
    return out


def _burn_in(directory, final, items, chosen):
    work = directory / 'captions-work'
    work.mkdir(exist_ok=True)
    try:
        out = render(final, work / 'captioned.mp4', items, work, chosen)
        staged = work / 'original.mp4'
        shutil.copy2(final, staged)
        staged.replace(directory / UNCAPTIONED_NAME)
        out.replace(final)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return {'uncaptioned_copy': UNCAPTIONED_NAME}


def run_name(store, source, appearance=None, now=None):
    """The readable folder name for a captioned copy: the source video's title, "captions", the style, and the date and time."""
    from .jobs import output_run_id
    from .storage import inside, read_json
    title = read_json(inside(store.home / 'runs', source).parent / 'output.json', {}).get('title') or 'video'
    return output_run_id(store, {'title': f"{title[:19].strip()} captions {look(appearance)['style']}"}, now=now)


def caption_finished(store, source, lines, context, appearance=None):
    """Caption an already finished music video as a new output; the original is never touched.

    `source` is "<run id>/<file>" of a completed video. The lines are the ones given, or else those saved with that video's request.
    A video that was captioned when made is captioned again from its uncaptioned copy, so words are never drawn twice."""
    from .lipsync import clean_lines
    from .media import duration
    from .score_view import _opening_offset
    from .storage import inside, read_json, write_json
    path = inside(store.home / 'runs', source)
    output = read_json(path.parent / 'output.json', {})
    if output.get('kind') != 'video' or output.get('file') != path.name or path.suffix != '.mp4':
        raise ValueError('Choose a completed music video to caption')
    request, plan = read_json(path.parent / 'request.json', {}), read_json(path.parent / 'plan.json', {})
    chosen = clean_lines(lines or request.get('lyric_lines'))
    if not chosen or not plan.get('segments'):
        raise ValueError('This video has no timed lyric lines saved; detect or paste the lyrics and pass them as lyric_lines')
    original = path.parent / UNCAPTIONED_NAME
    if (output.get('captions') or {}).get('uncaptioned_copy') and not original.is_file():
        raise ValueError('This video was captioned when it was made and its uncaptioned copy is gone; captioning it again would draw the words twice')
    video = original if original.is_file() else path
    opening = request.get('start_ident')
    if opening and not (inside(store.home / 'runs', opening).parent / 'output.json').is_file():
        raise ValueError('This video has an opening ident that was deleted, so the caption timing cannot be worked out')
    fps = float(plan['fps'])
    song_s = min(plan['total_frames'], sum(s['trim_frames'] for s in plan['segments'])) / fps
    items = cues(chosen, _opening_offset(store, request), song_s, duration(video))
    if not items:
        raise ValueError('None of the lyric lines falls inside the song, or all of them have guessed timing; confirm their timing first')
    directory = context.log_path.parent
    context.update('Burning the lyric captions', 20)
    work = directory / 'captions-work'
    work.mkdir(exist_ok=True)
    try:
        out = render(video, work / 'captioned.mp4', items, work, look(appearance),
                     lambda argv, cwd: context.command(argv, cwd=cwd))
        context.check()                          # a cancelled job publishes nothing
        out.replace(directory / 'captioned.mp4')
    finally:
        shutil.rmtree(work, ignore_errors=True)
    (directory / SRT_NAME).write_text(to_srt(items), encoding='utf-8')
    measured = duration(directory / 'captioned.mp4')
    write_json(directory / 'output.json', {'file': 'captioned.mp4', 'duration': measured, 'kind': 'captioned',
                                           'title': f"{output.get('title') or 'Music video'} (captions, {look(appearance)['style']})", 'source': source,
                                           'captions': {'mode': 'burned', 'cues': len(items), 'srt': SRT_NAME, **look(appearance)}})
    return {'file': context.record['id'] + '/captioned.mp4', 'duration': measured}
