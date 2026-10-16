"""
The planner. Deterministic, seeded, and the only thing that decides timing.

Nothing in here asks a language model anything. Frame counts, cut positions,
segment boundaries, camera motion and vocabulary sampling are all computed,
because these are the parts that must be *correct* rather than *good*, and a
model writing them in prose will eventually emit a 143-frame request or a cut
at 00:16.200 in a 15-second clip and you will not notice for three hundred
videos.

The output is a ShotPlan with empty content slots. The writer fills the slots.

One timing question is no longer answered here: how a musical span snaps to
a generatable duration. That is a renderer fact, not a planning fact — 17n+5
is MiniMax H3, not physics — so the planner asks the active backend
(mondo.backends) and the backend answers. The planner still owns every
structural decision, including how many reference slots a segment carries.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, asdict, field
from pathlib import Path

from .analyze import ScoreMap, Section
from .backends import get_backend
from .backends.base import BackendError
from .grid import Span
from .atomic_io import write_text_atomic

# Montage grammars, from the v1.6 instruction file.
STANDARD = "standard"
FRAGMENTATION = "type1_single_subject_fragmentation"
CHAOTIC = "type2_chaotic_multi_scene"
THEMATIC = "type3_thematic_multi_scene"

# Section energy label -> montage grammar.
# Peak sections return to the recurring subject: that is the visual refrain,
# and it is why a montage reads as a music video instead of a slideshow.
DEFAULT_MONTAGE_BY_LABEL = {
    "low": STANDARD,
    "mid": THEMATIC,
    "high": CHAOTIC,
    "peak": FRAGMENTATION,
}

# Beats between cuts, before energy modulation.
BEATS_PER_CUT = {
    STANDARD: 8,
    THEMATIC: 4,
    CHAOTIC: 2,
    FRAGMENTATION: 2,
}

MIN_SHOT_FRAMES = 12      # 0.5s, the floor from the instruction file
MAX_SHOT_FRAMES = 96      # 4.0s, above this a "montage" stops reading as one
MAX_SHOTS_PER_SEGMENT = 16

# Which grammars carry an actor's reference image.
#
# `fragmentation` is the original wiring, kept as the rollback path: only the
# peak-section grammar returns to a recurring subject, so only it was given a
# picture. `single_subject` adds `standard`, which is the other grammar that
# holds one subject for a whole segment. `all` wires every grammar, including
# the two multi-scene ones, where the cast member is not the segment's whole
# content but a recurring thread running through otherwise discontinuous shots
# -- the writer contract carries that amendment, not this module.
REF_POLICY_FRAGMENTATION = "fragmentation"
REF_POLICY_SINGLE_SUBJECT = "single_subject"
REF_POLICY_ALL = "all"

REF_POLICIES = (
    REF_POLICY_FRAGMENTATION,
    REF_POLICY_SINGLE_SUBJECT,
    REF_POLICY_ALL,
)

REF_POLICY_GRAMMARS = {
    REF_POLICY_FRAGMENTATION: {FRAGMENTATION},
    REF_POLICY_SINGLE_SUBJECT: {FRAGMENTATION, STANDARD},
    REF_POLICY_ALL: {STANDARD, FRAGMENTATION, CHAOTIC, THEMATIC},
}

# How many contracted cast members share one frame.
#
# This is a SCENE POPULATION question, not a two-shot question, and it is
# modelled that way on purpose. In a music video the only thing that matters is
# how many reference sheets are wired. In a film a scene has a headcount, some
# of those people are contracted characters with reference sheets, and the rest
# are extras who need no sheet at all. The reference budget and the scene
# population are therefore separate numbers, and only the first one costs
# conditioning. `extras` is carried through the whole pipeline already so that
# a future scene description can populate it without a schema change.
#
# off    -- exactly one cast member per eligible segment. The v0.9.0 world.
# always -- exactly the requested on-screen count, every eligible segment.
#           This is the setting that GUARANTEES people share a frame.
# mixed  -- the requested count on high-energy segments, solo elsewhere.
#           Deterministic, and tied to the song rather than to a dice roll.
# auto   -- energy-scaled probability. Retained from v0.10.0 because it does
#           produce good music videos when nothing is being forced.
ENSEMBLE_OFF = "off"
ENSEMBLE_ALWAYS = "always"
ENSEMBLE_MIXED = "mixed"
ENSEMBLE_AUTO = "auto"

ENSEMBLE_MODES = (ENSEMBLE_OFF, ENSEMBLE_ALWAYS, ENSEMBLE_MIXED, ENSEMBLE_AUTO)

DEFAULT_ENSEMBLE_MODE = ENSEMBLE_OFF
DEFAULT_ENSEMBLE_BIAS = 0.45          # only consulted by ENSEMBLE_AUTO
MIXED_ENERGY_THRESHOLD = 0.6          # at or above this, `mixed` goes ensemble


def parse_on_screen(spec, cast_size: int) -> tuple[int, int]:
    """Turn an on-screen spec into an inclusive (low, high) headcount range.

    Accepts an int, "3", "2-3", or "all". Everything is clamped to the cast
    actually available, because promising three faces from a cast of two is a
    graph that cannot be built.
    """
    if cast_size <= 0:
        return (0, 0)
    if spec is None:
        return (1, 1)

    if isinstance(spec, int):
        low = high = spec
    else:
        text = str(spec).strip().lower()
        if text in ("all", "max", "everyone", "full"):
            low = high = cast_size
        elif "-" in text:
            a, _, b = text.partition("-")
            try:
                low, high = int(a), int(b)
            except ValueError:
                low = high = 1
        else:
            try:
                low = high = int(text)
            except ValueError:
                low = high = 1

    if low > high:
        low, high = high, low
    low = max(1, min(low, cast_size))
    high = max(1, min(high, cast_size))
    if low > high:
        low = high
    return (low, high)


def ref_slots_for(
    montage_type: str,
    energy: float,
    *,
    ref_policy: str,
    cast_size: int,
    on_screen=1,
    ensemble_mode: str = DEFAULT_ENSEMBLE_MODE,
    ensemble_bias: float = DEFAULT_ENSEMBLE_BIAS,
    rng: random.Random,
) -> int:
    """How many reference images this segment carries.

    Called once per segment, in order, from a private RNG. The privacy is not
    cosmetic: sharing the sampler's stream would shift every vocabulary draw
    that follows, and a plan seed that produced a known-good run last week
    would quietly produce a different one today.

    The RNG is consumed in exactly one place regardless of mode, so switching
    between `always` and `mixed` does not desynchronise anything downstream.
    """
    if cast_size <= 0:
        return 0
    if montage_type not in REF_POLICY_GRAMMARS.get(ref_policy, set()):
        return 0

    low, high = parse_on_screen(on_screen, cast_size)
    e = max(0.0, min(1.0, energy))

    # One draw, always, whatever the mode. Keeps the stream stable across modes.
    roll = rng.random()

    if ensemble_mode == ENSEMBLE_OFF or high < 2:
        return 1

    if ensemble_mode == ENSEMBLE_ALWAYS:
        target = high

    elif ensemble_mode == ENSEMBLE_MIXED:
        target = high if e >= MIXED_ENERGY_THRESHOLD else 1

    elif ensemble_mode == ENSEMBLE_AUTO:
        p = max(0.0, min(1.0, ensemble_bias)) * (0.35 + 0.65 * e)
        target = high if roll < p else 1

    else:
        target = 1

    if target < 2:
        return 1

    # A range spec picks within the band, weighted toward the top as energy
    # rises, so a "2-4" scene is a crowd at the peak and a pair in the verse.
    if low < high and target == high:
        span = high - low
        target = low + int(round(span * e))
        target = max(low, min(high, target))

    return max(1, min(target, cast_size))


@dataclass
class Shot:
    n: int                      # 1-based; shot 1 carries no timestamp
    start_frame: int            # relative to segment start
    frames: int
    cut_time: str | None        # "MM:SS.mmm", None for shot 1
    camera: str
    shot_scale: str
    energy: float
    vocab: dict[str, str] = field(default_factory=dict)


@dataclass
class Segment:
    index: int
    song_start_frame: int
    musical_frames: int
    gen_frames: int
    trim_frames: int
    duration_input: float
    montage_type: str
    section_index: int
    section_label: str
    energy: float
    thematic_anchor: str | None
    ref_image_slots: int
    footage_anchor: str
    practical_effects: str
    rigging: str
    audio_slice_start_s: float
    audio_slice_end_s: float
    shots: list[Shot] = field(default_factory=list)

    @property
    def segment_id(self) -> str:
        return f"seg{self.index:03d}"


@dataclass
class ShotPlan:
    song: str
    slug: str
    seed: int
    fps: int
    width: int
    height: int
    tempo_bpm: float
    total_frames: int
    segments: list[Segment] = field(default_factory=list)

    def to_json(self, path: str | Path) -> None:
        write_text_atomic(Path(path), json.dumps(asdict(self), indent=2))

    @classmethod
    def from_json(cls, path: str | Path) -> "ShotPlan":
        d = json.loads(Path(path).read_text())
        d.pop("provenance", None)
        segs = []
        for s in d["segments"]:
            s.pop("provenance", None)
            shots = [Shot(**sh) for sh in s.pop("shots")]
            segs.append(Segment(**s, shots=shots))
        d["segments"] = segs
        return cls(**d)


class VocabSampler:
    """Samples rotation tables without repeating until a table is exhausted.

    This is the mechanism that replaces "never repeat a concept, track
    internally" — an instruction no model can honour across sessions but which
    is trivial with a deque and a seed.
    """

    def __init__(self, vocab: dict, seed: int, used: dict[str, list] | None = None):
        self.vocab = vocab
        self.rng = random.Random(seed)
        self.used: dict[str, list] = used or {}

    def pick(self, table: str) -> str:
        pool = list(self.vocab[table])
        seen = self.used.setdefault(table, [])
        remaining = [x for x in pool if x not in seen]
        if not remaining:
            seen.clear()
            remaining = pool
        choice = self.rng.choice(remaining)
        seen.append(choice)
        return choice

    def camera_for(self, energy: float) -> str:
        bands = sorted(self.vocab["camera_by_energy"].items(), key=lambda kv: float(kv[0]))
        chosen = bands[0][1]
        for threshold, pool in bands:
            if energy >= float(threshold):
                chosen = pool
        return self.rng.choice(chosen)

    def scale_for(self, energy: float) -> str:
        scales = self.vocab["shot_scales"]
        if energy > 0.75:
            return self.rng.choice([s for s in scales if "close" in s or "macro" in s] or scales)
        return self.rng.choice(scales)


def _partition_section(
    score: ScoreMap,
    section: Section,
    max_frames: int,
    bars_per_phrase: int,
    snap,
) -> list[tuple[int, int]]:
    """Split one section into phrase-aligned spans that fit the grid ceiling.

    Boundaries land on detected downbeats, so every segment seam is also a
    musical seam — which is what lets the seam double as a montage cut.
    `snap` is the active backend's snap_gen_frames: how a span rounds up to
    a generatable duration is the backend's answer, not the planner's.
    """
    downs = score.downbeats_in(section.start_frame, section.end_frame)
    if not downs:
        return [(section.start_frame, section.end_frame)]

    edges = [section.start_frame] if downs[0] > section.start_frame else []
    edges += downs
    if edges[-1] < section.end_frame:
        edges.append(section.end_frame)
    edges = sorted(set(edges))

    def fits(frames):
        # Hosted adapters reject an oversized snap instead of returning it.
        # Treat that rejection as "shrink the phrase", preserving musical edges.
        try:
            return snap(frames) <= max_frames
        except BackendError:
            return False

    # Shrink the phrase length until the snapped span fits under the ceiling.
    bars = bars_per_phrase
    while bars > 1:
        widest = 0
        for i in range(0, len(edges) - 1, bars):
            j = min(i + bars, len(edges) - 1)
            widest = max(widest, edges[j] - edges[i])
        if fits(widest):
            break
        bars //= 2

    spans: list[tuple[int, int]] = []
    i = 0
    while i < len(edges) - 1:
        j = min(i + bars, len(edges) - 1)
        start, end = edges[i], edges[j]
        # Hard safety: never hand H3 more than it can generate.
        while not fits(end - start) and j > i + 1:
            j -= 1
            end = edges[j]
        spans.append((start, end))
        i = j
    return spans


def _place_shots(
    score: ScoreMap,
    span_start: int,
    musical_frames: int,
    gen_frames: int,
    montage_type: str,
    sampler: VocabSampler,
    backend,
) -> list[Shot]:
    """Place cuts on beats, with density driven by energy.

    Cut times are computed from absolute beat frames and only then made
    relative, so error never accumulates across a segment.
    """
    beats = score.beats_in(span_start, span_start + musical_frames)
    if not beats or beats[0] > span_start:
        beats = [span_start] + beats

    base = BEATS_PER_CUT[montage_type]
    energy = score.energy_at(span_start + musical_frames // 2)
    # Hotter passages cut faster; cooler ones hold.
    stride = max(1, round(base * (1.35 - 0.7 * energy)))

    picked = beats[::stride]
    if picked[0] != beats[0]:
        picked = [beats[0]] + picked

    # Enforce the minimum shot length by dropping cuts that land too close.
    culled = [picked[0]]
    for b in picked[1:]:
        if b - culled[-1] >= MIN_SHOT_FRAMES:
            culled.append(b)
    picked = culled[:MAX_SHOTS_PER_SEGMENT]

    # Break up any shot that overstays; a montage that holds too long stops
    # reading as a montage.
    expanded = []
    for i, b in enumerate(picked):
        expanded.append(b)
        nxt = picked[i + 1] if i + 1 < len(picked) else span_start + musical_frames
        gap = nxt - b
        if gap > MAX_SHOT_FRAMES:
            n_extra = gap // MAX_SHOT_FRAMES
            for k in range(1, n_extra + 1):
                cand = b + k * (gap // (n_extra + 1))
                near = min(beats, key=lambda x: abs(x - cand))
                if near - expanded[-1] >= MIN_SHOT_FRAMES and near < nxt:
                    expanded.append(near)
    picked = sorted(set(expanded))[:MAX_SHOTS_PER_SEGMENT]

    # The final shot runs to the end of the musical span, so a cut placed too
    # close to that end leaves a one-frame flash. Drop such cuts.
    while len(picked) > 1 and (span_start + musical_frames) - picked[-1] < MIN_SHOT_FRAMES:
        picked.pop()

    shots: list[Shot] = []
    for i, b in enumerate(picked):
        rel = b - span_start
        end_rel = (picked[i + 1] - span_start) if i + 1 < len(picked) else musical_frames
        e = score.energy_at(b)
        shots.append(
            Shot(
                n=i + 1,
                start_frame=rel,
                frames=end_rel - rel,
                cut_time=None if i == 0 else backend.format_timestamp(rel),
                camera=sampler.camera_for(e),
                shot_scale=sampler.scale_for(e),
                energy=round(e, 3),
                vocab={},
            )
        )
    return shots


def plan(
    score: ScoreMap,
    *,
    width: int,
    height: int,
    vocab: dict,
    seed: int = 0,
    slug: str = "untitled",
    max_frames: int | None = None,
    bars_per_phrase: int = 8,
    montage_by_label: dict[str, str] | None = None,
    used_vocab: dict[str, list] | None = None,
    ref_policy: str = REF_POLICY_FRAGMENTATION,
    cast_size: int = 0,
    on_screen=1,
    ensemble_mode: str = DEFAULT_ENSEMBLE_MODE,
    ensemble_bias: float = DEFAULT_ENSEMBLE_BIAS,
    backend=None,
) -> ShotPlan:
    """Build a complete, timing-correct ShotPlan with empty content slots.

    `backend` is the renderer the plan targets (mondo.backends.Backend);
    None means the default, local MiniMax H3. `max_frames` of None takes
    the backend's own ceiling.
    """
    backend = backend or get_backend()
    if max_frames is None:
        max_frames = backend.max_gen_frames
    montage_by_label = montage_by_label or DEFAULT_MONTAGE_BY_LABEL
    sampler = VocabSampler(vocab, seed, used_vocab)
    # Deliberately not the sampler's stream. See ref_slots_for.
    ref_rng = random.Random((seed ^ 0x9E3779B9) & 0x7FFFFFFF)

    segments: list[Segment] = []
    # The first detected downbeat is rarely at frame 0; without this the head
    # of the song would have no picture over it.
    if score.sections:
        score.sections[0].start_frame = 0
    for section in score.sections:
        montage_type = montage_by_label.get(section.label, THEMATIC)
        anchor = sampler.pick("mechanisms") if montage_type == THEMATIC else None

        for start, end in _partition_section(score, section, max_frames,
                                             bars_per_phrase,
                                             backend.snap_gen_frames):
            musical = end - start
            if musical < MIN_SHOT_FRAMES:
                continue
            span = Span(start, musical, backend.snap_gen_frames(musical))

            seg = Segment(
                index=len(segments),
                song_start_frame=span.start_frame,
                musical_frames=span.musical_frames,
                gen_frames=span.gen_frames,
                trim_frames=span.trim_frames,
                duration_input=backend.duration_input_for(span.gen_frames),
                montage_type=montage_type,
                section_index=section.index,
                section_label=section.label,
                energy=round(section.energy, 3),
                thematic_anchor=anchor,
                ref_image_slots=ref_slots_for(
                    montage_type,
                    section.energy,
                    ref_policy=ref_policy,
                    cast_size=cast_size,
                    on_screen=on_screen,
                    ensemble_mode=ensemble_mode,
                    ensemble_bias=ensemble_bias,
                    rng=ref_rng,
                ),
                footage_anchor=sampler.pick("footage_anchors"),
                practical_effects=sampler.pick("practical_effects"),
                rigging=sampler.pick("rigging"),
                audio_slice_start_s=span.start_frame / backend.fps,
                audio_slice_end_s=(span.start_frame + span.gen_frames) / backend.fps,
                shots=[],
            )
            seg.shots = _place_shots(
                score, span.start_frame, span.musical_frames, span.gen_frames,
                montage_type, sampler, backend,
            )
            for sh in seg.shots:
                # Chaotic montage rotates everything per shot; the others hold
                # the setting steady and vary only within it.
                if montage_type in (CHAOTIC, THEMATIC):
                    sh.vocab = {
                        "setting": sampler.pick("settings"),
                        "subject_type": sampler.pick("subject_types"),
                        "mechanism": anchor or sampler.pick("mechanisms"),
                        "lighting": sampler.pick("lighting"),
                        "tonal_register": sampler.pick("tonal_registers"),
                        "costume": sampler.pick("costume"),
                    }
                else:
                    sh.vocab = {"lighting": sampler.pick("lighting")}
            if montage_type in (STANDARD, FRAGMENTATION):
                shared = {
                    "setting": sampler.pick("settings"),
                    "subject_type": sampler.pick("subject_types"),
                    "mechanism": sampler.pick("mechanisms"),
                    "tonal_register": sampler.pick("tonal_registers"),
                    "costume": sampler.pick("costume"),
                }
                for sh in seg.shots:
                    sh.vocab.update(shared)

            segments.append(seg)

    return ShotPlan(
        song=score.source,
        slug=slug,
        seed=seed,
        fps=backend.fps,
        width=width,
        height=height,
        tempo_bpm=score.tempo_bpm,
        total_frames=score.duration_frames,
        segments=segments,
    )
