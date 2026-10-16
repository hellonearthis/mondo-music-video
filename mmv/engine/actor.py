from __future__ import annotations

import base64, json, re

from pathlib import Path

from .atomic_io import write_text_atomic

def load_actor_meta(actor_id):
    return json.loads((ACTORS_DIR / actor_id / "actor.json").read_text(encoding="utf-8"))

ACTORS_DIR = Path("actors")

def resolve_sheet(meta: dict, sheet_rel: str | None = None) -> str | None:
    """Which sheet is the active outfit for this actor."""
    vc = meta.get("visual_contract") or {}
    rel = sheet_rel or vc.get("default_sheet")
    if rel:
        return rel
    refs = meta.get("reference_sheets") or []
    return refs[0] if refs else None

def actor_profile_lines(actor_id: str, sheet_rel: str | None = None) -> list[str]:
    """One cast member's appearance, as contract prose. No tag references.

    Deliberately tag-free: the same actor may be <Picture 1> in one segment and
    <Picture 2> in the next, so appearance is keyed to the actor's NAME and the
    binding is left to the job's cast array.
    """
    try:
        meta = load_actor_meta(actor_id)
    except FileNotFoundError:
        return []
    display = meta.get("display_name", actor_id)
    vc = meta.get("visual_contract") or {}
    rel = resolve_sheet(meta, sheet_rel)
    desc = (vc.get("sheets", {}) or {}).get(rel) if rel else None

    lines = [f"--- CAST MEMBER: {display} ---"]
    if desc:
        if desc.get("canonical_summary"):
            lines.append(f"Canonical look: {desc['canonical_summary']}")
        for key, label in (
            ("identity", "Identity"),
            ("hair", "Hair"),
            ("makeup", "Makeup"),
            ("wardrobe", "Wardrobe (active outfit)"),
            ("footwear", "Footwear"),
            ("detail_notes", "Detail notes"),
        ):
            value = str(desc.get(key) or "").strip()
            if value:
                lines.append(f"{label}: {value}")
        acc = desc.get("accessories") or []
        if acc:
            lines.append(f"Accessories: {', '.join(str(a) for a in acc)}")
        expr = desc.get("expression_range") or []
        if expr:
            lines.append(
                "Expression range: " + ", ".join(str(e) for e in expr) +
                ". Let each shot's energy choose from these expressions; the "
                "face may emote but must remain the same person."
            )
    else:
        lines.append(
            f"Canonical look: exactly as depicted in the reference image bound "
            f"to {display} in this segment's cast array — the same face, hair, "
            f"makeup, wardrobe, footwear, and accessories in every shot."
        )
    return lines

CASTING_RULES = """CASTING RULES
1. Binding. The job's "cast" array binds each wired picture tag to one cast member by name. Use exactly the tags listed there. A segment with an empty "cast" array has no cast member in it: write it from the vocabulary alone and never name a cast member or cite a picture tag.
2. Subject labels. In subject_definitions, define each cast member present as their own <Subject N>, in the same order the cast array lists them, and restate that member's wardrobe in one clause. Name the cast member and their bound picture tag together the first time each appears.
3. Multi-scene amendment. When a cast member is assigned to a type2_chaotic_multi_scene or type3_thematic_multi_scene segment, the cast member OVERRIDES the grammar's "new subject" rule. The cast member MUST appear in EVERY shot of the segment as the dominant subject. The "one-off subjects" rule is suspended for shots containing a cast member. If the segment has no cast member, only then do you generate one-off subjects.
4. More than one cast member in a segment. When the cast array lists two or more members, all of them are wired and all of them may appear. They may share a frame. Alternating them shot to shot is equally valid and is the safer reading; use a shared frame where the moment earns it.
5. Frame prominence. Each cast entry carries a "role". The member whose role is "lead" takes the nearer or larger position in frame. Members whose role is "support" sit further back, smaller, more peripheral, or partially occluded. Never give two contracted characters equivalent size, distance, and sharpness in the same frame — differentiated prominence is what keeps two identities from bleeding into one another. With three or more in frame, stage them at three distinct depths rather than in a row.
6. Rigging in shared frames. State the required face-and-mouth rigging for EVERY cast member visible in a shot, not only the lead. A shot with three contracted characters carries three rigging clauses.
7. Non-cast subjects. A cast member never shares a frame with a subject who is not in the cast array. Anonymous figures, crowds, hands, and body parts belonging to no one are subjects too, and they go in their own shots.
8. Style boundary. The selected style may change lighting, texture, grain, colour processing, environment, and era atmosphere. It may NOT change any cast member's face, hair, makeup, wardrobe, footwear, or accessories.
9. Costume vocabulary. If the job supplies costume vocabulary for a shot containing a cast member, ignore it for that cast member and dress them in the wardrobe above. Costume vocabulary still applies to non-cast subjects.
10. Reserved fields. A cast entry may carry "part", "lines", and "direction". When "lines" is empty and "direction" is empty, ignore all three and treat the member as a silent visual subject: this pipeline generates no dialogue and no lip movement, and the rigging clause overrides everything else. Never invent lines, never depict speech, and never write a character as speaking because a "part" name is present."""

RIGGING_SHARED_FRAMES_V013 = (
    "6. Rigging in shared frames. State the required face-and-mouth rigging "
    "for EVERY cast member visible in a shot, not only the lead. A shot with "
    "three contracted characters carries three rigging clauses."
)

NATURAL_SHARED_FRAMES_RULE = (
    "6. Faces in shared frames. State the face and mouth state for EVERY cast "
    "member visible in a shot, not only the lead. If a cast member speaks, "
    "describe their mouth movement naturally. If a cast member is silent, keep "
    "their face relaxed and expressive. A shot with three contracted characters "
    "carries three facial descriptions."
)

RESERVED_FIELDS_V013 = (
    "10. Reserved fields. A cast entry may carry \"part\", \"lines\", and "
    "\"direction\". When \"lines\" is empty and \"direction\" is empty, ignore "
    "all three and treat the member as a silent visual subject: this pipeline "
    "generates no dialogue and no lip movement, and the rigging clause overrides "
    "everything else. Never invent lines, never depict speech, and never write "
    "a character as speaking because a \"part\" name is present."
)

RESERVED_FIELDS_NATURAL = (
    "10. Reserved fields. A cast entry may carry \"part\", \"lines\", and "
    "\"direction\". If \"lines\" is present, the subject speaks those words and "
    "their mouth moves naturally. If \"lines\" is empty and \"direction\" is "
    "empty, the subject is silent but their face remains naturally expressive. "
    "Never invent lines that are not supplied."
)

def _casting_rules(silent_mouths: bool) -> str:
    """Return the CASTING RULES text for the given mode."""
    if silent_mouths:
        return CASTING_RULES
    rules = CASTING_RULES
    rules = rules.replace(RIGGING_SHARED_FRAMES_V013, NATURAL_SHARED_FRAMES_RULE)
    rules = rules.replace(RESERVED_FIELDS_V013, RESERVED_FIELDS_NATURAL)
    return rules

def cast_writer_block(
    actor_ids: list[str],
    sheets: dict[str, str] | None = None,
    *,
    silent_mouths: bool = True,
) -> str:
    """The CAST block appended to the composed writer prompt.

    One block describes the whole production's cast. Per-segment binding rides
    in the job, so this text is identical for every segment of a run and the
    composed prompt stays a single file.
    """
    actor_ids = [a for a in (actor_ids or []) if a]
    if not actor_ids:
        return ""
    sheets = sheets or {}

    profiles = []
    for actor_id in actor_ids:
        lines = actor_profile_lines(actor_id, sheets.get(actor_id))
        if lines:
            profiles.append("\n".join(lines))
    if not profiles:
        return ""

    header = [
        "CAST — NON-NEGOTIABLE CONTINUITY",
        f"This production has a cast of {len(profiles)}. Each cast member below "
        f"is a fixed physical identity that must survive every shot they appear "
        f"in, in every style.",
        "Each job carries a \"cast\" array naming which cast members appear in "
        "that segment and which picture tag is bound to each of them. The "
        "appearance descriptions below are keyed to NAMES, not tags, because a "
        "cast member's tag changes from segment to segment.",
    ]
    return "\n".join(header) + "\n" + "\n".join(profiles) + "\n" + _casting_rules(silent_mouths)
