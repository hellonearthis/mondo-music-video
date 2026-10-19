"""Subliminal message mode: a few frames of a chosen picture or of words flashed into the finished video.

Applied after assembly with FFmpeg, outside the original engine. The finished video keeps its exact frame count, duration and
audio (the audio stream is copied, never re-encoded); the untouched video is kept next to it as music-video-clean.mp4.
Flashes are brief by design, so they are kept at least a second apart and at most MAX_FRAMES long (photosensitivity).
"""
from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path

from .storage import inside

MODES = ('off', 'image', 'text')
PLACEMENTS = ('manual', 'downbeats')
MAX_FRAMES = 12
MAX_TIMES = 20
MAX_TEXT = 60
MIN_GAP_SECONDS = 1.0           # at most one flash per second
EDGE_SECONDS = 1.0              # no flash in the first or last second
NOTICE = ('Subliminal flashes are brief full-frame flashes and can affect viewers who are sensitive to flashing images. '
          'Mondo keeps them at least a second apart; a clean copy of the video is always kept.')


def clean(settings):
    """Validated, normalised settings (or None when off)."""
    if not settings or settings.get('mode', 'off') == 'off':
        return None
    mode = settings.get('mode')
    if mode not in MODES:
        raise ValueError('Subliminal mode is off, image or text')
    frames = settings.get('frames', 2)
    if isinstance(frames, bool) or not isinstance(frames, int) or not 1 <= frames <= MAX_FRAMES:
        raise ValueError(f'A subliminal flash lasts 1 to {MAX_FRAMES} frames')
    placement = settings.get('placement', 'manual')
    if placement not in PLACEMENTS:
        raise ValueError('Subliminal placement is manual or downbeats')
    text = ' '.join(str(settings.get('text') or '').split())
    image = settings.get('image') or ''
    if mode == 'text' and not text:
        raise ValueError('Enter the words to flash')
    if mode == 'image' and not image:
        raise ValueError('Choose the picture to flash')
    if len(text) > MAX_TEXT:
        raise ValueError(f'Flash words are at most {MAX_TEXT} characters')
    times = settings.get('times') or []
    if len(times) > MAX_TIMES or any(isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or t < 0 for t in times):
        raise ValueError(f'Give up to {MAX_TIMES} flash times in seconds')
    count = settings.get('count', 3)
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= MAX_TIMES:
        raise ValueError(f'Flash count is 1 to {MAX_TIMES}')
    if placement == 'manual' and not times:
        raise ValueError('Enter at least one time in seconds, or choose downbeats')
    return {'mode': mode, 'frames': frames, 'placement': placement, 'text': text, 'image': image,
            'times': sorted({round(float(t), 3) for t in times}), 'count': count}


def place(settings, fps, total_frames, downbeat_frames=(), offset_frames=0):
    """Start frames (on the final video's clock). Manual times are used as given; downbeats are spread evenly over the song."""
    frames, gap = settings['frames'], int(MIN_GAP_SECONDS * fps) + settings['frames']
    edge = min(int(EDGE_SECONDS * fps), total_frames // 10)           # a second from each end, or a tenth of a very short video
    if settings['placement'] == 'manual':
        starts = [round(t * fps) for t in settings['times']]
    else:
        usable = [f + offset_frames for f in downbeat_frames if edge <= f + offset_frames <= total_frames - edge - frames]
        if not usable:
            raise ValueError('This song has no downbeat far enough from its ends to flash on')
        wanted = min(settings['count'], len(usable))
        starts, last = [], None
        for i in range(wanted):
            pick = usable[round(i * (len(usable) - 1) / max(wanted - 1, 1))] if wanted > 1 else usable[len(usable) // 2]
            if last is None or pick - last >= gap:
                starts.append(pick)
                last = pick
    starts = sorted(set(starts))
    for start in starts:
        if start + frames > total_frames or start < 0:
            raise ValueError('A flash falls outside the video')
        if start < edge or start + frames > total_frames - edge:
            raise ValueError(f'Flashes stay at least {edge / fps:.1f} s away from the start and the end of the video')
    for a, b in zip(starts, starts[1:]):
        if b - a < gap:
            raise ValueError(f'Flashes must be at least {MIN_GAP_SECONDS:g} second apart (and not overlap)')
    return starts


def plan_run(settings, fps, total_frames, downbeat_frames, offset_frames, upload_dir):
    """What the preview shows and the run stores: validated settings, start frames and times. None when off."""
    cleaned = clean(settings)
    if not cleaned:
        return None
    if cleaned['mode'] == 'image':
        path = inside(upload_dir, cleaned['image'])
        if not path.is_file() or path.suffix.lower() not in ('.png', '.jpg', '.jpeg'):
            raise ValueError('The flash picture was not found; upload a PNG or JPEG')
    starts = place(cleaned, fps, total_frames, downbeat_frames, offset_frames)
    return {**cleaned, 'fps': fps, 'starts': starts, 'times': [round(s / fps, 3) for s in starts], 'notice': NOTICE}


def text_png(text, width, height, target):
    """The words, large and centred, white on black, as a full-frame picture."""
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new('RGB', (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    size = max(int(height * 0.28), 12)
    while size > 10:
        font = ImageFont.load_default(size=size)
        lines, line = [], ''
        for word in text.split():
            trial = (line + ' ' + word).strip()
            if draw.textlength(trial, font=font) <= width * 0.9 or not line:
                line = trial
            else:
                lines.append(line)
                line = word
        lines.append(line)
        spacing = int(size * 0.2)
        total = len(lines) * size + (len(lines) - 1) * spacing
        if total <= height * 0.9 and all(draw.textlength(l, font=font) <= width * 0.95 for l in lines):
            break
        size = int(size * 0.85)
    y = (height - total) / 2
    for line in lines:
        draw.text((width / 2, y), line, font=font, fill=(255, 255, 255), anchor='mt')
        y += size + spacing
    image.save(target)
    return Path(target)


def _probe(path):
    """(frame count, width, height, frame rate as ffmpeg writes it) of the first video stream."""
    done = subprocess.run(['ffprobe', '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries',
                           'stream=nb_read_frames,width,height,r_frame_rate', '-of', 'csv=p=0', str(path)],
                          capture_output=True, text=True, timeout=300)
    width, height, rate, frames = done.stdout.strip().split(',')[:4]
    return int(frames), int(width), int(height), rate


def _count_frames(path):
    return _probe(path)[:3]


def apply(source, target, picture, starts, frames):
    """Overlay the picture on the given frame ranges. Audio is copied; frame count and duration are unchanged."""
    enable = '+'.join(f'between(n,{s},{s + frames - 1})' for s in starts)
    _, width, height, rate = _probe(source)
    graph = (f'[1:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},format=yuv420p[flash];'
             f"[0:v][flash]overlay=enable='{enable}':shortest=1[v]")
    done = subprocess.run(['ffmpeg', '-nostdin', '-y', '-v', 'error', '-i', str(source), '-framerate', rate, '-loop', '1', '-i', str(picture),      # the picture must run at the video's own rate
                           '-filter_complex', graph,
                           '-map', '[v]', '-map', '0:a?', '-c:v', 'libx264', '-crf', '12', '-preset', 'medium', '-pix_fmt', 'yuv420p',
                           '-c:a', 'copy', str(target)], capture_output=True, text=True, timeout=1800)
    if done.returncode:
        raise ValueError('The subliminal flash could not be applied: ' + done.stderr[-300:])
    return target


def apply_to_run(store, directory, plan):
    """Flash the finished video in place, keeping the untouched one as music-video-clean.mp4. Returns a short result record.

    The finished video is never modified until the new one has passed a frame-count check, and then it is replaced atomically;
    on any failure it is left exactly as it was."""
    final, clean_copy = directory / 'music-video.mp4', directory / 'music-video-clean.mp4'
    work = directory / 'subliminal-work'
    work.mkdir(exist_ok=True)
    try:
        before, width, height = _count_frames(final)
        if plan['mode'] == 'text':
            picture = text_png(plan['text'], width, height, work / 'flash.png')
        else:
            picture = inside(store.home / 'uploads', plan['image'])
        out = apply(final, work / 'flashed.mp4', picture, plan['starts'], plan['frames'])
        after, _, _ = _count_frames(out)
        if after != before:
            raise ValueError(f'The flashed video has {after} frames instead of {before}; keeping the clean video')
        staged = work / 'clean.mp4'
        shutil.copy2(final, staged)
        staged.replace(clean_copy)              # the untouched video first, atomically (same folder tree, so a plain rename)
        out.replace(final)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return {'mode': plan['mode'], 'frames': plan['frames'], 'times': plan['times'], 'clean_copy': clean_copy.name}
