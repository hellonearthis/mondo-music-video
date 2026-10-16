"""
H3 full-reference prompt assembly and validation.

The safety property this module exists to enforce: **the writer never emits a
timestamp.** Qwen returns per-shot body prose with no prefix; Python prepends
`[Shot N] At MM:SS.mmm, ` from the planner's absolute frame indices. A model
cannot get the timing wrong if it is never handed the timing to write.

Everything else here is the envelope — the six ref-mode fields, in order, with
exact names, because the format is strict and a run that drifts at 3am should
fail loudly at validation rather than quietly produce garbage on the GPU.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .grid import FPS

FIELDS = [
    "subject_definitions",
    "summary",
    "retention_analysis",
    "detailed_description",
    "overall_soundscape",
    "non_diegetic_music",
]

CUT_VERBS = [
    "the camera cuts to",
    "the shot cuts to",
    "the shot transitions to",
    "the shot changes to",
    "the shot switches to",
]

TIMESTAMP_RE = re.compile(r"\b\d{1,2}:\d{2}\.\d{1,3}\b")
SHOT_RE = re.compile(r"\[Shot (\d+)\]")
LABEL_RE = re.compile(r"<(Picture|Video|Audio|Subject) (\d+)>")

RIGGING_TAIL = "to prevent any facial babbling or lip-sync hallucinations."


class ValidationError(Exception):
    pass


@dataclass
class WriterResponse:
    """What the writer model returns. Deliberately timestamp-free."""
    segment_id: str
    style_opening: str
    subject_definitions: list[str] = field(default_factory=list)
    summary: str = ""
    retention_analysis: list[str] = field(default_factory=list)
    shot_bodies: list[str] = field(default_factory=list)   # one per shot, no prefix
    overall_soundscape: str = ""
    non_diegetic_music: str = "N/A"

    @classmethod
    def parse(cls, raw: str, expected_id: str | None = None) -> "WriterResponse":
        """Parse the writer's JSON, tolerating fenced code blocks."""
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\n", "", text)
            text = re.sub(r"\n```$", "", text.rstrip())
        try:
            d = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValidationError(f"writer did not return valid JSON: {e}") from e
        missing = {"style_opening", "shot_bodies"} - set(d)
        if missing:
            raise ValidationError(f"writer response missing keys: {sorted(missing)}")
        if expected_id and d.get("segment_id") not in (None, expected_id):
            raise ValidationError(
                f"segment_id mismatch: got {d.get('segment_id')!r}, want {expected_id!r}"
            )
        d.setdefault("segment_id", expected_id or "")
        return cls(**{k: v for k, v in d.items() if k in cls.__annotations__})


def build_writer_request(
    plan,
    segment,
    tags,
    cast: list[dict] | None = None,
    *,
    silent_mouths: bool = True,
) -> dict:
    """The JSON job handed to the writer. Contains slots, never prose.

    `cast` binds each wired picture tag to a named actor. It is the only place
    the writer learns *who* `<Picture 2>` is; the CAST section of the composed
    system prompt says what each named actor looks like. Keeping the binding in
    the job and the appearance in the system prompt is what allows one actor to
    be `<Picture 1>` in one segment and `<Picture 2>` in the next without
    rewriting a system prompt per segment.
    """
    cast = cast or []
    shot_count = len(segment.shots)
    min_words = max(150, int(shot_count * 55))
    max_words = max(900, int(shot_count * 100))
    max_words = min(1500, max_words)
    min_words = min(min_words, max_words)
    body_min_words = max(120, int(shot_count * 45))
    body_max_words = max(600, int(shot_count * 85))
    body_max_words = min(1350, body_max_words)
    body_min_words = min(body_min_words, body_max_words)
    per_shot_target = max(35, int(round(body_min_words / max(1, shot_count))))
    length_requirement = (
        f"Target shot_bodies, not detailed_description. The combined shot_bodies total MUST be between "
        f"{body_min_words} and {body_max_words} words, about {per_shot_target} words per shot. "
        f"The assembled detailed_description will be validated in the {min_words}-{max_words} word window."
    )
    request = {
        "segment_id": segment.segment_id,
        "montage_type": segment.montage_type,
        "thematic_anchor": segment.thematic_anchor,
        "duration_seconds": round(segment.gen_frames / FPS, 3),
        "shot_count": shot_count,
        "length_requirement": length_requirement,
        "footage_anchor": segment.footage_anchor,
        "practical_effects": segment.practical_effects,
        "rigging": segment.rigging,
        "audio_tag": tags.music_tag,
        "picture_tags": tags.images,
        "cast": [
            {
                "picture_tag": member.get("picture_tag", ""),
                "actor": member.get("display_name", ""),
                "actor_id": member.get("actor_id", ""),
                "role": member.get("role", "lead"),
                "part": member.get("part", member.get("display_name", "")),
                "lines": list(member.get("lines") or []),
                "direction": member.get("direction", ""),
            }
            for member in cast
        ],
        "shots": [
            {
                "n": s.n,
                "duration_seconds": round(s.frames / FPS, 3),
                "shot_scale": s.shot_scale,
                "camera": s.camera,
                "energy_0_to_1": s.energy,
                "vocabulary": s.vocab,
            }
            for s in segment.shots
        ],
    }
    if not silent_mouths:
        request.pop("rigging", None)
    return request


def assemble_prompt(segment, resp: WriterResponse, tags) -> str:
    """Compose the final six-field prompt string. Timestamps injected here."""
    if len(resp.shot_bodies) != len(segment.shots):
        raise ValidationError(
            f"{segment.segment_id}: writer returned {len(resp.shot_bodies)} shot "
            f"bodies, plan has {len(segment.shots)}"
        )

    subject_defs = list(resp.subject_definitions)
    audio_def = (
        f"{tags.music_tag} is the rhythmic and tempo reference for the target "
        f"video, providing the beat and pacing the visuals follow."
    )
    if not any(tags.music_tag in s for s in subject_defs):
        subject_defs.append(audio_def)

    retention = list(resp.retention_analysis)
    if not any(tags.music_tag in r for r in retention):
        retention.append(
            f"{tags.music_tag}: reference - only its beat, tempo, and rhythmic "
            f"structure guide the visual pacing; the signal is not copied."
        )

    body_parts = [resp.style_opening.strip()]
    for shot, text in zip(segment.shots, resp.shot_bodies):
        text = text.strip()
        if shot.cut_time is None:
            body_parts.append(f"[Shot {shot.n}] {text}")
        else:
            verb = CUT_VERBS[(shot.n - 1) % len(CUT_VERBS)]
            lead = text[0].lower() + text[1:] if text else text
            body_parts.append(
                f"[Shot {shot.n}] At {shot.cut_time}, {verb} {lead}"
            )
    detailed = " ".join(body_parts)

    out = [
        "subject_definitions:",
        "\n".join(subject_defs),
        "",
        "summary:",
        resp.summary.strip(),
        "",
        "retention_analysis:",
        "\n".join(retention),
        "",
        "detailed_description:",
        detailed,
        "",
        "overall_soundscape:",
        resp.overall_soundscape.strip(),
        "",
        "non_diegetic_music:",
        resp.non_diegetic_music.strip() or "N/A",
    ]
    return "\n".join(out)


def validate_prompt(
    prompt: str,
    segment,
    tags,
    *,
    strict_words: bool = True,
    silent_mouths: bool = True,
) -> list[str]:
    """Return a list of problems. Empty list means the prompt may be queued."""
    problems: list[str] = []

    for f in FIELDS:
        if f"{f}:" not in prompt:
            problems.append(f"missing required field '{f}:'")

    positions = [prompt.find(f"{f}:") for f in FIELDS if f"{f}:" in prompt]
    if positions != sorted(positions):
        problems.append("fields are out of the required order")

    shots_found = [int(m) for m in SHOT_RE.findall(prompt)]
    expected = list(range(1, len(segment.shots) + 1))
    if shots_found != expected:
        problems.append(f"shot numbering is {shots_found}, expected {expected}")

    # Timestamps: exactly the planner's, no extras, strictly increasing.
    want = [s.cut_time for s in segment.shots if s.cut_time]
    got = TIMESTAMP_RE.findall(prompt)
    if got != want:
        problems.append(f"cut times are {got}, expected {want}")

    def to_frames(ts: str) -> int:
        mm, rest = ts.split(":")
        ss, ms = rest.split(".")
        return round((int(mm) * 60 + int(ss) + int(ms.ljust(3, '0')) / 1000) * FPS)

    prev = -1
    for ts in got:
        f = to_frames(ts)
        if f <= prev:
            problems.append(f"cut time {ts} is not strictly increasing")
        if f >= segment.musical_frames:
            problems.append(
                f"cut time {ts} ({f}f) falls at or past the trim point "
                f"({segment.musical_frames}f) and would be cut off"
            )
        prev = f

    # No reference label may be used that is not actually wired.
    allowed = set(tags.images) | set(tags.videos) | set(tags.audios)
    for kind, num in LABEL_RE.findall(prompt):
        if kind == "Subject":
            continue
        lbl = f"<{kind} {num}>"
        if lbl not in allowed:
            problems.append(f"prompt references {lbl}, which is not wired")

    if silent_mouths and RIGGING_TAIL.rstrip(".").lower() not in prompt.lower():
        problems.append("Subject Rigging block is missing (lip-sync suppression)")

    start = prompt.find("detailed_description:")
    end = prompt.find("overall_soundscape:")
    if start >= 0 and end > start:
        n = len(prompt[start:end].split())
        shot_count = max(1, len(segment.shots))
        min_words = max(150, int(shot_count * 55))
        max_words = max(900, int(shot_count * 100))
        max_words = min(1500, max_words)
        min_words = min(min_words, max_words)
        if strict_words and not (min_words <= n <= max_words):
            problems.append(
                f"detailed_description is {n} words; expected roughly "
                f"{min_words}-{max_words} for {shot_count} shot(s)"
            )
    max_prompt_chars = 12000
    if strict_words and len(prompt) > max_prompt_chars:
        problems.append(
            f"WARNING: prompt is {len(prompt)} characters; context budget roughly {max_prompt_chars}"
        )
    return problems
