"""Owner edits to a song's analysis, applied between the cached analysis and the planner.

The cached ScoreMap is never changed. Edits are validated, quantized to frames and
applied to a copy, so the original engine sources and the analysis cache stay as they
were. Beats keep their identity by index into the detected beat list.
"""
from __future__ import annotations

import copy
import math

from .engine.analyze import ScoreMap, Section
from .engine.grid import FPS

LABELS = ("low", "mid", "high", "peak")
LABEL_ENERGY = {"low": 0.15, "mid": 0.4, "high": 0.65, "peak": 0.9}
MIN_SECTION_FRAMES = FPS            # one second; the planner silently skips anything under 12 frames
MAX_SECTIONS = 64
MAX_NUDGE_MS = 250
MAX_MUTED = 2000


def is_empty(edits) -> bool:
    if not edits:
        return True
    # Beat 0 is a real bar-phase choice, so only None means "not edited" for bar_one_beat.
    return (edits.get('bar_one_beat') is None and not edits.get('beat_nudge_ms')
            and not edits.get('muted_beats') and not edits.get('sections'))


def apply_score_edits(score: ScoreMap, edits) -> ScoreMap:
    """Return an edited copy of ``score``; ``score`` itself is not modified."""
    result = copy.deepcopy(score)
    if is_empty(edits):
        return result
    count = len(result.beat_frames)
    has_energy = bool(result.beat_energy)
    rows = list(zip(range(count), result.beat_frames, result.beat_energy or [0.5] * count))
    bpb = max(1, int(result.beats_per_bar))

    nudge_ms = edits.get('beat_nudge_ms') or 0
    if isinstance(nudge_ms, bool) or not isinstance(nudge_ms, int) or abs(nudge_ms) > MAX_NUDGE_MS:
        raise ValueError(f'Beat nudge must be whole milliseconds within {MAX_NUDGE_MS}')
    shift = round(nudge_ms * FPS / 1000)
    downbeats = list(result.downbeat_frames)
    if shift:
        rows = [(i, f + shift, e) for i, f, e in rows if 0 <= f + shift < result.duration_frames]
        downbeats = [d + shift for d in downbeats if 0 <= d + shift < result.duration_frames]

    bar_one = edits.get('bar_one_beat')
    if bar_one is not None:
        if isinstance(bar_one, bool) or not isinstance(bar_one, int) or not 0 <= bar_one < max(count, 1):
            raise ValueError('Bar one must be one of the detected beats')
        # Phase follows each beat's original index, so beats dropped by a nudge cannot shift it.
        downbeats = [f for i, f, _ in rows if i % bpb == bar_one % bpb]

    muted = edits.get('muted_beats') or []
    if len(muted) > MAX_MUTED or len(set(muted)) != len(muted):
        raise ValueError('Muted beats must be unique and at most ' + str(MAX_MUTED))
    for index in muted:
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < count:
            raise ValueError('A muted beat is not one of the detected beats')

    new_sections = result.sections
    if edits.get('sections'):
        new_sections = _sections(edits['sections'], result, [f for _, f, _ in rows], [e for _, _, e in rows])

    if muted:
        # Muted beats stop being cut candidates but keep their place in bar counting.
        rows = [row for row in rows if row[0] not in set(muted)]
        if not rows:
            raise ValueError('At least one beat must stay active')

    result.beat_frames = [f for _, f, _ in rows]
    result.beat_energy = [e for _, _, e in rows] if has_energy else []
    result.downbeat_frames = sorted(set(downbeats))
    result.sections = new_sections
    return result


def _sections(items, score, beats, energy):
    if len(items) > MAX_SECTIONS:
        raise ValueError(f'At most {MAX_SECTIONS} sections')
    starts = []
    for item in items:
        value = item.get('start')
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError('Section starts must be numbers of seconds')
        if item.get('label') not in LABELS:
            raise ValueError('Section labels are ' + ', '.join(LABELS))
        starts.append(round(value * FPS))
    if starts[0] != 0:
        raise ValueError('The first section must start at 0 s')
    ends = starts[1:] + [score.duration_frames]
    sections = []
    for index, (start, end, item) in enumerate(zip(starts, ends, items)):
        if end - start < MIN_SECTION_FRAMES:
            raise ValueError('Each section must be at least 1 second long and in order')
        inner = [e for b, e in zip(beats, energy) if start <= b < end]
        sections.append(Section(start_frame=start, end_frame=end, index=index,
                                energy=float(sum(inner) / len(inner)) if inner else LABEL_ENERGY[item['label']],
                                label=item['label']))
    return sections


def detected_view(score: ScoreMap) -> dict:
    """The unedited analysis in seconds, so an editor can show muted beats and the original grid."""
    at = lambda frame: round(frame / FPS, 4)
    downbeats = set(score.downbeat_frames)
    return {'duration': at(score.duration_frames), 'tempo_bpm': score.tempo_bpm, 'beats_per_bar': score.beats_per_bar,
            'beats': [{'time': at(b), 'downbeat': b in downbeats} for b in score.beat_frames],
            # The planner always opens the first section at frame 0, so the editor shows it that way.
            'sections': [{'start': at(0 if i == 0 else s.start_frame), 'end': at(s.end_frame), 'label': s.label,
                          'energy': s.energy} for i, s in enumerate(score.sections)]}


def check_plan_coverage(segments, total_frames, tolerance=0):
    """Edited plans must keep the picture locked to the song: no frames dropped or doubled between passages."""
    expected = 0
    for segment in segments:
        start = segment['song_start_frame']
        if abs(start - expected) > tolerance:
            raise ValueError(
                f'These edits leave {abs(start - expected) / FPS:.2f} s of the song without a passage near '
                f'{min(start, expected) / FPS:.2f} s, which would shift the picture against the music. '
                'Move the nearest section boundary or bar start so passages meet, then re-plan.')
        expected = start + segment['trim_frames']
