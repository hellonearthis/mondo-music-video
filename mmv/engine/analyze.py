"""
Audio analysis -> ScoreMap.

Everything this module emits is quantized to integer frame indices at 24 fps
before it leaves. Downstream code never sees a float second, which is what
keeps cut timestamps from drifting.

Section labels here are structural, not semantic: librosa can tell us where
the song changes character, not that a passage is "the chorus". We label by
relative energy rank, which is what the planner actually needs in order to
choose a montage type.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path

import numpy as np

from .grid import FPS, quantize_to_frame


@dataclass
class Section:
    start_frame: int
    end_frame: int
    index: int
    energy: float          # 0..1, mean normalized energy
    label: str             # "low" | "mid" | "high" | "peak"

    @property
    def n_frames(self) -> int:
        return self.end_frame - self.start_frame


@dataclass
class ScoreMap:
    source: str
    duration_frames: int
    sample_rate: int
    tempo_bpm: float
    beats_per_bar: int
    beat_frames: list[int] = field(default_factory=list)
    downbeat_frames: list[int] = field(default_factory=list)
    beat_energy: list[float] = field(default_factory=list)   # parallel to beat_frames
    sections: list[Section] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        return self.duration_frames / FPS

    def energy_at(self, frame: int) -> float:
        """Normalized energy at an absolute frame, by nearest beat."""
        if not self.beat_frames:
            return 0.5
        idx = int(np.argmin(np.abs(np.asarray(self.beat_frames) - frame)))
        return float(self.beat_energy[idx])

    def beats_in(self, start_frame: int, end_frame: int) -> list[int]:
        return [b for b in self.beat_frames if start_frame <= b < end_frame]

    def downbeats_in(self, start_frame: int, end_frame: int) -> list[int]:
        return [b for b in self.downbeat_frames if start_frame <= b < end_frame]

    def to_json(self, path: str | Path) -> None:
        d = asdict(self)
        Path(path).write_text(json.dumps(d, indent=2))

    @classmethod
    def from_json(cls, path: str | Path) -> "ScoreMap":
        d = json.loads(Path(path).read_text())
        d["sections"] = [Section(**s) for s in d["sections"]]
        return cls(**d)


def _estimate_downbeats(
    beat_frames: list[int],
    onset_env: np.ndarray,
    onset_frame_times: np.ndarray,
    beats_per_bar: int,
) -> list[int]:
    """Pick the bar phase whose beats carry the most onset weight.

    librosa has no downbeat tracker. For 4/4 material the downbeat is almost
    always the strongest of the four phases, so we score each candidate phase
    by mean onset strength and take the winner. Crude, but it fails safely:
    a wrong phase still lands on a beat, so cuts stay musical.
    """
    if not beat_frames:
        return []

    strengths = []
    for b in beat_frames:
        t = b / FPS
        i = int(np.argmin(np.abs(onset_frame_times - t)))
        strengths.append(float(onset_env[i]))
    strengths = np.asarray(strengths)

    best_phase, best_score = 0, -np.inf
    for phase in range(beats_per_bar):
        picked = strengths[phase::beats_per_bar]
        if picked.size == 0:
            continue
        score = float(picked.mean())
        if score > best_score:
            best_phase, best_score = phase, score

    return beat_frames[best_phase::beats_per_bar]


def _label_sections(energies: np.ndarray) -> list[str]:
    """Rank sections into four buckets by relative energy."""
    if energies.size == 0:
        return []
    order = np.argsort(np.argsort(energies))       # rank 0..n-1
    denom = max(1, energies.size - 1)
    labels = []
    for r in order:
        q = r / denom
        if q < 0.25:
            labels.append("low")
        elif q < 0.55:
            labels.append("mid")
        elif q < 0.85:
            labels.append("high")
        else:
            labels.append("peak")
    return labels


def analyze(
    audio_path: str | Path,
    *,
    beats_per_bar: int = 4,
    target_section_seconds: float = 22.0,
    sr: int = 22050,
) -> ScoreMap:
    """Analyze a song into a frame-quantized ScoreMap."""
    import librosa

    audio_path = str(audio_path)
    y, sr = librosa.load(audio_path, sr=sr, mono=True)
    duration_s = len(y) / sr
    duration_frames = quantize_to_frame(duration_s)

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_times = librosa.times_like(onset_env, sr=sr)

    tempo, beat_idx = librosa.beat.beat_track(
        onset_envelope=onset_env, sr=sr, units="frames", trim=False
    )
    tempo = float(np.atleast_1d(tempo)[0])
    beat_times = librosa.frames_to_time(beat_idx, sr=sr)

    # Master clock conversion: seconds -> integer video frames, once.
    beat_frames = sorted({quantize_to_frame(t) for t in beat_times})
    beat_frames = [b for b in beat_frames if 0 <= b < duration_frames]

    downbeat_frames = _estimate_downbeats(
        beat_frames, onset_env, onset_times, beats_per_bar
    )

    # Per-beat energy from RMS, normalized robustly (5th..95th percentile).
    rms = librosa.feature.rms(y=y)[0]
    rms_times = librosa.times_like(rms, sr=sr)
    raw = []
    for b in beat_frames:
        i = int(np.argmin(np.abs(rms_times - b / FPS)))
        raw.append(float(rms[i]))
    raw_arr = np.asarray(raw)
    if raw_arr.size:
        lo, hi = np.percentile(raw_arr, 5), np.percentile(raw_arr, 95)
        beat_energy = list(np.clip((raw_arr - lo) / max(hi - lo, 1e-9), 0.0, 1.0))
        beat_energy = [float(x) for x in beat_energy]
    else:
        beat_energy = []

    # Structural segmentation over beat-synchronous timbre+harmony features.
    sections: list[Section] = []
    if len(beat_idx) >= 4:
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        feat = np.vstack([mfcc, chroma])
        feat_sync = librosa.util.sync(feat, beat_idx, aggregate=np.median)

        k = int(max(2, min(len(beat_idx) // 4, round(duration_s / target_section_seconds))))
        bounds = librosa.segment.agglomerative(feat_sync, k)
        bound_beats = sorted({int(b) for b in bounds})

        edges = []
        for bb in bound_beats:
            bb = min(bb, len(beat_frames) - 1)
            edges.append(beat_frames[bb])
        edges = sorted(set([0] + edges + [duration_frames]))

        for i in range(len(edges) - 1):
            s, e = edges[i], edges[i + 1]
            if e - s < FPS:            # discard sub-second slivers
                continue
            inner = [
                beat_energy[j]
                for j, b in enumerate(beat_frames)
                if s <= b < e
            ]
            sections.append(
                Section(
                    start_frame=s,
                    end_frame=e,
                    index=len(sections),
                    energy=float(np.mean(inner)) if inner else 0.5,
                    label="mid",
                )
            )

    if not sections:
        sections = [
            Section(0, duration_frames, 0, float(np.mean(beat_energy or [0.5])), "mid")
        ]

    for sec, lab in zip(sections, _label_sections(np.array([s.energy for s in sections]))):
        sec.label = lab

    return ScoreMap(
        source=audio_path,
        duration_frames=duration_frames,
        sample_rate=sr,
        tempo_bpm=round(tempo, 3),
        beats_per_bar=beats_per_bar,
        beat_frames=beat_frames,
        downbeat_frames=downbeat_frames,
        beat_energy=beat_energy,
        sections=sections,
    )
