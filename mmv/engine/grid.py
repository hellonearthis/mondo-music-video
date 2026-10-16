"""
H3 frame grid.

MiniMax H3 only accepts frame counts on the lattice  f = 17n + 5.
This is enforced inside the ComfyUI graph by ComfyMathExpression:

    max(5, round(a * 24)) + (5 - (max(5, round(a * 24)) % 17)) % 17

which always snaps UP to the next lattice point (or is a no-op if already
on it). Every timing decision in this pipeline lives on that lattice.

Strategy: the planner computes the exact musical span it wants, snaps UP to
the next lattice point, generates that many frames, then trims back down to
the musical span during assembly. Because the snap is always upward we are
guaranteed to have enough frames to cut.

We deliberately feed ComfyUI a duration in seconds that is ALREADY on the
lattice (frames / 24), so the node's own snap becomes a no-op and the two
implementations can never disagree.
"""

from __future__ import annotations

from dataclasses import dataclass

FPS = 24
STEP = 17
OFFSET = 5

# H3 tops out around 15s. 362 frames = 15.083s, 345 = 14.375s.
# Default to 345 to stay comfortably inside the documented ceiling.
MAX_FRAMES_SAFE = 345
MAX_FRAMES_HARD = 362
MIN_FRAMES = 5

# Resolution constraints from the H3 ComfyUI implementation.
DIM_MULTIPLE = 32
MIN_SHORT_EDGE = 384


def is_on_grid(frames: int) -> bool:
    """True if `frames` is a legal H3 frame count."""
    return frames >= OFFSET and (frames - OFFSET) % STEP == 0


def snap_up(frames: int) -> int:
    """Snap a frame count UP to the next lattice point.

    Mirrors the ComfyMathExpression in the workflow exactly, including its
    clamp at 5.
    """
    f = max(MIN_FRAMES, int(frames))
    return f + (OFFSET - (f % STEP)) % STEP


def snap_down(frames: int) -> int:
    """Snap DOWN to the previous lattice point. Never returns below 5."""
    f = max(MIN_FRAMES, int(frames))
    down = f - ((f - OFFSET) % STEP)
    return max(MIN_FRAMES, down)


def seconds_to_frames(seconds: float) -> int:
    """Raw, unsnapped frame count for a duration."""
    return max(MIN_FRAMES, round(seconds * FPS))


def frames_to_seconds(frames: int) -> float:
    return frames / FPS


def duration_input_for(frames: int) -> float:
    """The value to write into the workflow's Float (Duration) primitive.

    Feeding frames/24 makes the graph's own snap a no-op, so Python owns the
    frame count and ComfyUI just agrees with it.
    """
    if not is_on_grid(frames):
        raise ValueError(f"{frames} is not on the H3 grid (17n+5)")
    return frames / FPS


def lattice(max_frames: int = MAX_FRAMES_HARD) -> list[int]:
    """All legal frame counts up to `max_frames`."""
    out, f = [], OFFSET
    while f <= max_frames:
        out.append(f)
        f += STEP
    return out


def format_timestamp(frames: int) -> str:
    """Frame index -> H3 cut-time string, MM:SS.mmm.

    H3 writes cut times as `[Shot N] At 00:03.500, ...`. We always emit from
    an absolute frame index so timestamps can never drift by accumulation.
    """
    if frames < 0:
        raise ValueError("negative frame index")
    total_ms = round(frames * 1000 / FPS)
    minutes, rem_ms = divmod(total_ms, 60_000)
    seconds, ms = divmod(rem_ms, 1000)
    return f"{minutes:02d}:{seconds:02d}.{ms:03d}"


def format_duration_2dp(frames: int) -> str:
    """Effective duration to exactly two decimals, for the FL2VA/L2VA
    instruction line ('...aligns with the S.SS-second mark')."""
    return f"{frames / FPS:.2f}"


def quantize_to_frame(seconds: float) -> int:
    """Absolute time in seconds -> nearest integer frame index.

    The master clock is frames, not seconds. Beat positions get quantized
    here once, and everything downstream works in integers.
    """
    return max(0, round(seconds * FPS))


def snap_resolution(aspect_w: int, aspect_h: int, megapixels: float) -> tuple[int, int]:
    """Pick width/height for an arbitrary aspect ratio at a pixel budget.

    Replaces ComfyUI's ResolutionSelector dropdown so any ratio is allowed.
    Both dimensions land on a multiple of 32. Raises if the short edge would
    fall below H3's 384 minimum, which is what bites on extreme ratios.
    """
    if aspect_w <= 0 or aspect_h <= 0:
        raise ValueError("aspect components must be positive")
    if megapixels <= 0:
        raise ValueError("megapixels must be positive")

    target_px = megapixels * 1_000_000
    ratio = aspect_w / aspect_h
    h = (target_px / ratio) ** 0.5
    w = h * ratio

    def round32(x: float) -> int:
        return max(DIM_MULTIPLE, int(round(x / DIM_MULTIPLE)) * DIM_MULTIPLE)

    w_i, h_i = round32(w), round32(h)
    short = min(w_i, h_i)
    if short < MIN_SHORT_EDGE:
        needed = megapixels * (MIN_SHORT_EDGE / short) ** 2
        raise ValueError(
            f"{aspect_w}:{aspect_h} at {megapixels} MP gives a short edge of "
            f"{short}px, below H3's {MIN_SHORT_EDGE}px minimum. "
            f"Raise megapixels to about {needed:.2f} for this ratio."
        )
    return w_i, h_i


@dataclass(frozen=True)
class Span:
    """A musical span pinned to the frame grid.

    `musical_frames` is what the song actually wants. `gen_frames` is what we
    ask H3 for (snapped up). The difference is trimmed off in assembly.
    """

    start_frame: int          # absolute position in the song
    musical_frames: int       # exact phrase length
    gen_frames: int           # H3 lattice value, >= musical_frames

    @classmethod
    def from_musical(cls, start_frame: int, musical_frames: int) -> "Span":
        return cls(start_frame, musical_frames, snap_up(musical_frames))

    @property
    def end_frame(self) -> int:
        return self.start_frame + self.musical_frames

    @property
    def trim_frames(self) -> int:
        """How many frames to keep from the generated clip."""
        return self.musical_frames

    @property
    def waste_frames(self) -> int:
        return self.gen_frames - self.musical_frames

    @property
    def duration_input(self) -> float:
        return duration_input_for(self.gen_frames)
