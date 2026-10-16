from __future__ import annotations

import base64, json, re

from pathlib import Path

from .atomic_io import write_text_atomic

STYLES_DIR = Path(__file__).parent / "styles"

BASE_TEMPLATE = Path(__file__).parent / "prompts/writer_base.md"

IDENT_BASE_TEMPLATE = Path(__file__).parent / "prompts/ident_base.md"

def load_style(style_id):
    return (Path(style_id) / "aesthetic.md").read_text(encoding="utf-8")


IMAGE_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

SFW_BLOCK = """
CONTENT RATING: SFW (SAFE FOR WORK) — HARD OVERRIDE
This rating overrides every other content boundary, aesthetic directive, and stylistic instruction in this prompt. It is absolute and non-negotiable.
No nudity of any kind. Every subject is fully clothed in every shot.
No exposed breasts, buttocks, or genitals. No see-through, removed, or slipping clothing that reveals the body.
No blood, no gore, no open wounds, no visible injury, no bodily fluids.
No violence, no weapons used against people, no striking, no harm depicted.
No sexual acts, no erotic posing, no sexually suggestive framing.
Keep every image clothed, non-graphic, and non-sexual. The style, composition, lighting, mood, and texture all remain fully in force — only the explicit content is removed. If a shot you would otherwise write violates these rules, rewrite it so the subject is clothed and the action is non-graphic while preserving the look. This constraint takes precedence over all aesthetic goals."""

RESTRICT_NUDITY = "nudity"

RESTRICT_BLOOD = "blood"

RESTRICT_VIOLENCE = "violence"

RESTRICT_SEXUAL = "sexual"

RESTRICTIONS = (RESTRICT_NUDITY, RESTRICT_BLOOD, RESTRICT_VIOLENCE,
                RESTRICT_SEXUAL)

SFW_RESTRICTIONS = (RESTRICT_NUDITY, RESTRICT_BLOOD, RESTRICT_VIOLENCE,
                    RESTRICT_SEXUAL)

RESTRICTION_LABELS = {
    RESTRICT_NUDITY: "NO NUDITY",
    RESTRICT_BLOOD: "NO BLOOD OR GORE",
    RESTRICT_VIOLENCE: "NO VIOLENCE",
    RESTRICT_SEXUAL: "NO SEXUAL CONTENT",
}

RESTRICTION_CLAUSES = {
    RESTRICT_NUDITY: (
        "NUDITY — PROHIBITED. Every subject is fully clothed in every shot. "
        "No exposed breasts, buttocks, or genitals. No see-through, removed, "
        "or slipping clothing that reveals the body. If a shot you would "
        "otherwise write exposes a subject, rewrite it so the subject is "
        "clothed while preserving the look, the framing, and the mood."
    ),
    RESTRICT_BLOOD: (
        "BLOOD AND GORE — PROHIBITED. No blood, no gore, no open wounds, no "
        "visible injury, no bodily fluids, no viscera, no medical or "
        "slaughter residue. Surfaces stay clean of it. If a shot depends on "
        "such matter, substitute a non-organic equivalent — oil, slip, "
        "pigment, rust, resin — and keep the composition intact."
    ),
    RESTRICT_VIOLENCE: (
        "VIOLENCE — PROHIBITED. No violence, no weapons used against people, "
        "no striking, no restraint of a person against their will, no harm "
        "depicted or implied to any subject. Tension, threat and dread may "
        "remain, expressed through light, framing, pace and environment "
        "rather than through an act."
    ),
    RESTRICT_SEXUAL: (
        "SEXUAL CONTENT — PROHIBITED. No sexual acts, no erotic posing, no "
        "sexually suggestive framing, no lingering on the body as an object. "
        "Subjects are photographed as people, not as invitations."
    ),
}

def normalize_restrictions(restrictions=None, sfw=False):
    """Resolve the granular set, honouring the legacy boolean.

    Passing sfw=True is exactly equivalent to selecting every restriction, so
    every existing caller, run_config, and queue item keeps working unchanged.
    """
    out = []
    if sfw:
        out = list(SFW_RESTRICTIONS)
    for r in (restrictions or []):
        r = str(r).strip().lower()
        if r in RESTRICTIONS and r not in out:
            out.append(r)
    return [r for r in RESTRICTIONS if r in out]

def build_restriction_block(restrictions):
    """Compose the content override for whichever restrictions are active."""
    active = normalize_restrictions(restrictions)
    if not active:
        return ""
    if len(active) == len(RESTRICTIONS):
        return SFW_BLOCK

    labels = ", ".join(RESTRICTION_LABELS[r] for r in active)
    head = (
        "\nCONTENT RESTRICTIONS — HARD OVERRIDE\n"
        f"Active restrictions: {labels}.\n"
        "These override every other content boundary, aesthetic directive, and "
        "stylistic instruction in this prompt. They are absolute and "
        "non-negotiable. Anything NOT listed below remains permitted and is "
        "governed by the aesthetic directives alone.\n"
    )
    body = "\n".join(RESTRICTION_CLAUSES[r] for r in active)
    tail = (
        "\nThe style, composition, lighting, mood, and texture all remain "
        "fully in force — only the restricted content is removed. If a shot "
        "you would otherwise write violates a restriction above, rewrite that "
        "shot to comply while preserving the look. These constraints take "
        "precedence over all aesthetic goals."
    )
    return head + body + tail

HARVEST_PROMPT = """You are a style harvester for an automated music-video pipeline. You will receive one or more reference images. Read each image for HOW it was made, not what it is a picture of.

A reference image is a set of manufacturing decisions — ink count, edge behaviour, grain, light falloff, wear — that can be lifted whole and applied to entirely different content. Harvest those decisions. Do not harvest the content itself (the subjects, objects, or scenes depicted).

THE SUBTRACTION TEST — run it on every line you write:
State each trait without naming anything in the picture. If a trait cannot survive that sentence, it is content, not style, and you must discard it.
"Blacks are crushed to a single flat value with no detail" — style. Keep.
"Warm light rakes in from the left, unmotivated by any visible source" — style. Keep.
"A woman stands in a doorway" — content. Discard.
"Doorways frame the subject" — content wearing a style costume. Discard.

Read every image against all ELEVEN AXES. Write what is actually there, not what the genre usually does.

1 INK ECONOMY — distinct colours carrying real area; the accent colour and what it is reserved for; the saturation ceiling.
2 TONAL STRUCTURE — where the darks sit (true black / lifted charcoal / crushed flat); highlights (blown / held / capped); contrast local or global; midtones crowded or stretched.
3 SURFACE — what the image is physically made of (halftone, film grain, digital noise, engraving line, flat vector, chalk, weave, visible pixel); the size of the smallest repeating unit. Surface is the single most transferable trait.
4 EDGE BEHAVIOUR — hard or soft; outlined or unoutlined; forms terminate cleanly or dissolve; registration slip, halo, chromatic fringing, or bleed.
5 LIGHT LOGIC — how many sources; direction; point / diffuse / ambient / none; falloff steep or gentle; is light depicted, or merely implied by value.
6 DEPTH STRATEGY — overlap, scale, atmospheric haze, blur, linear perspective, isometric, or none; whether the image reads as a window or a surface.
7 COMPOSITION GRAMMAR — symmetry or asymmetry; where mass sits; empty-to-occupied ratio; framing devices.
8 SCALE RELATIONSHIP — how large the primary form sits in frame.
9 PROVENANCE MARKERS — wear, fading, foxing, creases, dust, scratches, vignetting, misregistration, colour shift, the tint of aged stock. These make an image read as an object with a history rather than a render.
10 TYPOGRAPHY — if present: weight, width, stroke contrast, case, letterspacing, and how type sits relative to the image. If absent, say none.
11 MOTION IMPLICATION — what in this image would move if it were alive, and how slowly. Grain suggests shimmer; halftone suggests dot migration; long exposure suggests drift; heavy vignetting suggests a projected or optical origin. THIS IS THE MOST IMPORTANT AXIS, because the output is video.

READING MULTIPLE IMAGES:
Recurrence is the vibe; variance is the permitted range.
A trait in every image is load-bearing. Lock it.
A trait in most images is a strong default. State it, allow deviation.
A trait that differed across the set is an axis the user does not care about. Declare it free.
A trait in exactly one image is noise. Discard it unless unmistakably deliberate.
Take the intersection, never the union.

ANTI-PASTICHE:
Harvest characteristics, never authorship. Never name a living artist, a studio, a specific photograph, or a copyrighted work. State everything as traits (ink count, edge quality, falloff, grain size). Broad traditions and processes are fair game and precise: letterpress, riso, wet-plate, screenprint, cyanotype, engraving.

DO NOT HARVEST:
Accidental file artefacts (compression blocking, unintended crop, oversharpening, auto-HDR flattening, watermark, interface chrome, bad-scan colour cast). Faces and identifiable people are content — they never enter the harvest.

CONTENT BOUNDARY (always apply, do not override):
All subjects depicted by this style will be fictional adults. The style may be suggestive, tactile, and voyeuristic, but remains non-explicit. No minors, no explicit sexual content, no real people, no gore.

OUTPUT — return a single JSON object with exactly two string fields:
"style_card": a labeled STYLE CARD block listing all eleven axes, the free axes, and up to two borrowable motifs (each to be re-rendered in the target world's materials).
"aesthetic_directives": prose directives written as instructions to a video segment writer, in the imperative voice. These tell the writer how every shot must look and feel so that it embodies the harvested style. Base them on the eleven axes, but write them as living instructions, not a form. Include a dedicated motion-and-texture paragraph derived from axis 11, since the output is moving video. Do not name any subject, object, or scene from the reference images. End with the content boundary rule.
Return ONLY the JSON object. No preamble, no code fence, no commentary."""

SILENT_MOUTHS_RULE_V013 = (
    "Every shot states its subject's face and mouth, ending with the exact "
    "phrase `to prevent any facial babbling or lip-sync hallucinations.` "
    "Use the `rigging` value supplied. This is not optional: the model "
    "generates speech unprompted, and mouths moving under a song is the "
    "single clearest tell that a video is generated."
)

NATURAL_MOUTHS_RULE = (
    "Every shot states its subject's face and mouth naturally. If the "
    "subject is speaking, describe the articulation of their words and the "
    "movement of the lips, teeth, and tongue. If the subject is silent, "
    "keep the face expressive and relaxed. Do not force sealed lips or "
    "unnatural facial stillness."
)

RIGGING_EXAMPLE_LINE_V013 = '"rigging": "lips firmly sealed shut, jaw completely relaxed",'

SUBJECT_RIGGING_HEADER = "SUBJECT RIGGING (critical)."

AFTER_SUBJECT_RIGGING = "PRACTICAL EFFECTS AND COSTUME."

NATURAL_FACIAL_BLOCK = (
    "FACIAL MOVEMENT (critical).\n"
    "Describe the subject's face and mouth naturally. If the subject is "
    "speaking, describe the articulation of their words and the movement "
    "of the lips, teeth, and tongue. If the subject is silent, keep the "
    "face expressive and relaxed. Do not force sealed lips or unnatural "
    "facial stillness.\n\n"
)

def _replace_subject_rigging_block(aesthetic: str) -> str:
    """Replace the sealed-lips SUBJECT RIGGING block with natural facial movement."""
    start = aesthetic.find(SUBJECT_RIGGING_HEADER)
    end = aesthetic.find(AFTER_SUBJECT_RIGGING)
    if start == -1 or end == -1 or end < start:
        return aesthetic
    return aesthetic[:start] + NATURAL_FACIAL_BLOCK + aesthetic[end:]

def compose_writer_prompt(
    style_id,
    sfw=False,
    actor_block=None,
    restrictions=None,
    *,
    silent_mouths: bool = True,
    lyrics: str | None = None,
    direction: str | None = None,
  ):
    template = BASE_TEMPLATE.read_text()
    # Silent-mouths placeholders first.
    if silent_mouths:
        template = template.replace("{{SILENT_MOUTHS_RULE}}", SILENT_MOUTHS_RULE_V013)
        template = template.replace("{{RIGGING_EXAMPLE_LINE}}", RIGGING_EXAMPLE_LINE_V013)
    else:
        template = template.replace("{{SILENT_MOUTHS_RULE}}", NATURAL_MOUTHS_RULE)
        template = re.sub(r"[ \t]*\{\{RIGGING_EXAMPLE_LINE\}\}\n?", "", template)

    if lyrics:
          template = template.replace("{{LYRICS_FLAVOR}}", f"\n\nLyrics / Flavor Text:\n{lyrics}\n")
    else:
          template = re.sub(r"[ \t]*\{\{LYRICS_FLAVOR\}\}\n?", "", template)

    aesthetic = load_style(style_id)
    if not silent_mouths:
        aesthetic = _replace_subject_rigging_block(aesthetic)
    composed = template.replace("{{AESTHETIC_DIRECTIVES}}", aesthetic)
    if actor_block:
        composed += "\n" + actor_block

    if direction:
        composed += "\n\nDIRECTOR'S DIRECTION:\n" + direction + "\n"
    # The content override goes last so it is the final word the writer reads.
    composed += build_restriction_block(normalize_restrictions(restrictions, sfw))
    return composed

def inject_conceptual_theme(jobs_dir, theme_phrase):
    jobs_dir = Path(jobs_dir)
    job_files = sorted(jobs_dir.glob("*.json"))
    for job_file in job_files:
        job = json.loads(job_file.read_text())
        job.pop("theme", None)
        if theme_phrase:
            job["conceptual_theme"] = theme_phrase
        else:
            job.pop("conceptual_theme", None)
        write_text_atomic(job_file, json.dumps(job, indent=2))

def build_harvest_payload(image_paths):
    content = [{"type": "text", "text": HARVEST_PROMPT}]
    for p in image_paths:
        mime = IMAGE_MIME.get(p.suffix.lower(), "image/jpeg")
        b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
        content.append(
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
        )
    return content

def parse_harvest_response(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        text = text[start:end + 1]
    data = json.loads(text)
    return data.get("style_card", ""), data.get("aesthetic_directives", "")

IDENT_STYLE_CARD_FORMAT = """STYLE CARD: {short name}
Harvested from {N} reference image(s).
CRAFT: {palette economy and accent; tonal structure; surface and its grain scale; edge behaviour; light logic and whether light is depicted or implied; depth strategy; composition grammar; scale of primary form; provenance markers; typography; what would move and how slowly}
GRAMMAR: {the generative rule — stated so it mentions nothing visible in the reference and still constrains what gets built}
DEVIATION: {how many departures from the ordinary, at what magnitude, sited where, against what left deliberately untouched}
AFFECT: {the feeling} — produced by {the machinery that produces it}
CONTRACT: {how the image asks to be looked at; where it places the viewer}
TEMPORALITY: {before / during / after / held out of time; posed or caught}
REFUSAL: {the premise the image declines to acknowledge}
PERMITTED SPACE: {what else this grammar allows — the range to draw from}
CHOSEN POINT: {where in this space this build lands, and it is not where the reference landed}
FREE AXES: {traits that varied across the set}
BORROWABLE MOTIFS: {up to two, re-rendered in world materials}"""

IDENT_VISION_INSTRUCTION = (
    "You are the style reader for the mondo ident pipeline. Read the "
    "attached reference image(s) forensically — craft, grammar, deviation, "
    "affect, contract, temporality, refusal — and fill in the Style Card "
    "format below. Every field comes from what the image(s) actually show. "
    "Output the completed Style Card only: no prose before it, no prose "
    "after it.\n\n" + IDENT_STYLE_CARD_FORMAT
)

IDENT_SCENE_OVERRIDE_ADDENDUM = """

NO-TEXT SCENE COMMISSION — RUNTIME OVERRIDES (v0.18.5-local)
This commission is a freeform scene with no words. These overrides
supersede any conflicting rule above:
- There is no TEXT. Every rule about the words — the exact string in double
  quotes, the THE TEXT blocks, letter and word counts, legibility as the
  deliverable, the reverse removal test — is void for this commission.
- There is NO final hold. The rules that the last beat be motionless, that
  the words stand complete and still, and that the camera settle into
  stillness are suspended. The scene never pauses; continuous motion
  through the last frame is the deliverable.
- Mouth restrictions are suspended. SUBJECT RIGGING does not apply here;
  figures may speak and mouths may move naturally. Do not add rigging
  clauses; this form is freeform.
What still applies, unchanged: the Audio Anchor verbatim (a purely silent
scene — zero musical score, no soundtrack); the forbidden words (ident,
title card, bumper, logo, sting, intro); the motion floor; the law of
fresh starts; output ONLY the prompt text.
"""

def compose_ident_prompt(no_text=False):
    """The ident writer's system prompt: ident_base.md, whole. The file
    already carries the constrained pipeline wrapper; nothing is
    substituted. Parameters ride the user message.

    no_text (v0.18.5-local): the attached prompt carries a runtime
    NO-TEXT SCENE addendum that supersedes the TEXT, hold, and mouth
    rules for freeform scene-only commissions. ident_base.md on disk
    is never edited."""
    base = IDENT_BASE_TEMPLATE.read_text()
    if not no_text:
        return base
    return base + IDENT_SCENE_OVERRIDE_ADDENDUM

def build_ident_style_card_payload(image_paths):
    """The vision step's user message: the Style Card instruction plus the
    reference images. Mirrors build_harvest_payload's shape exactly."""
    content = [{"type": "text", "text": IDENT_VISION_INSTRUCTION}]
    for p in image_paths:
        mime = IMAGE_MIME.get(p.suffix.lower(), "image/jpeg")
        b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
        content.append(
            {"type": "image_url",
             "image_url": {"url": f"data:{mime};base64,{b64}"}}
        )
    return content

def build_ident_writer_message(text, duration, mode, style_card=None,
                               ident_notes=None, no_text=False):
    """The ident writer's user message: labeled parameters only. The system
    prompt (ident_base.md) says how to consume them.

    no_text (v0.18.5-local): the NO IDENT scene-only commission. The TEXT
    line is replaced and a runtime override block supersedes every TEXT
    requirement in ident_base.md; ident_base.md on disk is never edited.
    Scenographic mode additionally carries a TEXT INTEGRITY reinforcement
    when no_text is False, closing the textless-scenographic class."""
    lines = []
    if no_text:
        lines.append("TEXT: (none — scene only)")
    else:
        lines.append(f"TEXT: {text}")
    lines.append(f"DURATION: {duration:g}")
    lines.append(f"MODE: {mode}")
    if no_text:
        lines.append("")
        lines.append("NO-TEXT SCENE OVERRIDE (supersedes every TEXT rule in this document,")
        lines.append("including 'The prompt must contain the exact TEXT string in double quotes'):")
        lines.append("This ident carries NO words. Omit every letterform, caption, sign,")
        lines.append("stamp, inscription, and readable mark; the scene must contain nothing")
        lines.append("that reads as text. The removal test is the whole commission: the clip")
        lines.append("is a small event in the world, worth watching with no word in it.")
        lines.append("This is a freeform scene: SUBJECT RIGGING and every mouth restriction")
        lines.append("are suspended — figures may speak and mouths may move naturally.")
        lines.append("There is NO final hold: the scene never pauses, and motion continues")
        lines.append("through the last frame. The Audio Anchor verbatim and the forbidden")
        lines.append("words still apply; the law of fresh starts still applies.")
    elif str(mode).strip().lower() == "scenographic":
        lines.append("")
        lines.append(f'TEXT INTEGRITY (scenographic reinforcement): the words "{text}" are')
        lines.append("the entire subject of this shot. Open the prompt by declaring that the")
        lines.append(f'words "{text}" are the whole subject and what they are made of; keep')
        lines.append(f'the exact string "{text}" in double quotes; the final beat holds them')
        lines.append("fully formed, legible, and motionless. A scene without the words is a")
        lines.append("failed ident.")
    if style_card:
        lines.append("")
        lines.append("STYLE CARD:")
        lines.append(str(style_card))
    if ident_notes:
        lines.append("")
        lines.append("IDENT NOTES (Director's wishes):")
        lines.append(str(ident_notes))
    return "\n".join(lines) + "\n"
