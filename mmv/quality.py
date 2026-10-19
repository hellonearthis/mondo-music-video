"""Motion and framing quality gates for music-video passages.

Two failure modes seen on real H3 renders motivate this module: a passage that
renders as a near-still image, and a picture shown inside a projected-film frame
with wide uniform borders. The prompt checks run before rendering and feed the
writer's existing correction loop; the clip checks measure rendered pixels.
Original engine sources stay unmodified; this is Mondo Music Video's own layer.

Thresholds are provisional calibrations from real renders, not universal limits,
so clip findings retry only on free local renderers and otherwise only warn.
"""
from __future__ import annotations

import io
import re
import subprocess

# Appended to the composed music-video writer system prompt.
WRITER_RULES = """

Motion and framing rules (Mondo Music Video quality gate)

Every shot must show visible motion on screen. When the supplied camera holds a static shot, the subject or the environment must visibly move; use the supplied mechanism. Never describe the subject as motionless, frozen or perfectly still, and never call the composition, image or scene static.

The picture always fills the frame edge to edge. Footage and film-stock references describe texture, colour, grain and lens character only. Never depict the shot as a projected film, a film frame with borders, a photo print, a screen within the frame, letterboxing, pillarboxing or split screen, unless the director's direction explicitly asks for that device.
"""

_NEGATION = re.compile(r"\b(?:no|not|never|without|avoid|avoiding|free of|instead of)\b[^.;:]{0,30}$", re.I)
_STILL_SCENE = re.compile(
    r"\b(?:composition|image|picture|frame|scene|passage|shot)s? (?:is|are|remains?|stays?) "
    r"(?:entirely |completely |fully |totally |perfectly )?(?:static|still|frozen|motionless|unmoving)\b"
    r"|\b(?:static|still|frozen|motionless|unmoving) (?:image|photograph|picture|composition|tableau)\b"
    r"|\bfrozen (?:frame|moment)\b|\bstill frame\b|\bnothing (?:moves|stirs)\b"
    r"|\bno (?:visible )?(?:movement|motion)(?! blur)\b", re.I)
_STILL_SUBJECT = re.compile(
    r"\b(?:remains?|stays?|stands?|sits?|is|are|holds?) (?:completely |perfectly |entirely |totally )?"
    r"(?:motionless|still|stationary|unmoving|frozen|immobile)\b", re.I)
# Visible movement elsewhere in a static-camera shot satisfies the motion rule.
_MOTION_WORDS = re.compile(
    r"\b(?:mov(?:e|es|ing)|sway(?:s|ing)?|drift(?:s|ing)?|flicker(?:s|ing)?|ripple(?:s|ing)?|stream(?:s|ing)?|"
    r"flow(?:s|ing)?|blow(?:s|ing|n)?|fall(?:s|ing)?|turn(?:s|ing)?|walk(?:s|ing)?|run(?:s|ning)?|"
    r"spin(?:s|ning)?|swirl(?:s|ing)?|billow(?:s|ing)?|flutter(?:s|ing)?|rise(?:s)?|rising|pulse(?:s)?|pulsing|"
    r"shift(?:s|ing)?|sweep(?:s|ing)?|rotat(?:e|es|ing)|danc(?:e|es|ing)|gestur(?:e|es|ing)|rais(?:e|es|ing)|"
    r"lift(?:s|ing)?|reach(?:es|ing)?|breath(?:e|es|ing)|tremble(?:s)?|trembling|wav(?:e|es|ing)|"
    r"shimmer(?:s|ing)?|roll(?:s|ing)?|scatter(?:s|ing)?|haul(?:s|ing)?|pull(?:s|ing)?|push(?:es|ing)?)\b", re.I)
_FRAMING_DEVICE = re.compile(
    r"\bprojected (?:film|image|footage|picture)\b|\bprojected onto a screen\b|\b(?:projector|projection) screen\b"
    r"|\bfilm (?:frame|gate) (?:border|edge)s?\b|\b(?:photo|photographic) print\b|\bpolaroid\b"
    r"|\bletterbox(?:ed|ing)?\b|\bpillarbox(?:ed|ing)?\b|\b(?:white|black|thick|wide) (?:border|borders|bars)\b"
    r"|\bpicture[- ]in[- ]picture\b|\bsplit[- ]screen\b|\bframed (?:photograph|picture|print)\b", re.I)
_SHOT_BODY = re.compile(r"\[Shot (\d+)\](.*?)(?=\[Shot \d+\]|\noverall_soundscape:|\Z)", re.S)


def _affirmative(pattern, text):
    """First match not preceded by a nearby negation ('without black bars', 'no motion blur')."""
    for match in pattern.finditer(text):
        if not _NEGATION.search(text[max(0, match.start() - 40):match.start()]):
            return match
    return None


def framing_requested(direction):
    """The director explicitly asked for a framing device, so framing checks step aside."""
    return bool(direction and _affirmative(_FRAMING_DEVICE, direction))


def _camera(shot):
    return (shot.get("camera") if isinstance(shot, dict) else getattr(shot, "camera", None)) or ""


def _number(shot):
    return shot.get("n") if isinstance(shot, dict) else getattr(shot, "n", None)


def prompt_problems(prompt, segment, direction=""):
    """Deterministic motion/framing problems in a written prompt, for the writer retry loop."""
    problems = []
    match = _affirmative(_STILL_SCENE, prompt)
    if match:
        problems.append(f"The prompt declares a still image ('{match.group(0)}'). Every shot must show visible "
                        "motion of the camera, the subject or the environment.")
    start = prompt.find("detailed_description:")
    body = prompt[start:] if start >= 0 else prompt
    shots = {_number(shot): shot for shot in segment.shots}
    for number, text in _SHOT_BODY.findall(body):
        camera = _camera(shots.get(int(number)) or {})
        if "static" not in camera.lower():
            continue
        # The planned camera does not move, so the subject or the environment must.
        text = text.replace(camera, "")
        still = _affirmative(_STILL_SUBJECT, text)
        if still and not _affirmative(_MOTION_WORDS, text):
            problems.append(f"Shot {number} holds a static camera and describes the subject as "
                            f"'{still.group(0)}' with nothing else moving. With a static camera, the subject "
                            "or the environment must visibly move.")
    if not framing_requested(direction):
        match = _affirmative(_FRAMING_DEVICE, prompt)
        if match:
            problems.append(f"The prompt describes a framing device ('{match.group(0)}'). The picture must fill "
                            "the frame edge to edge; describe film or photo looks as texture only.")
    return problems


# Mean absolute frame-to-frame luminance change (0-255) at 184x104 grayscale.
# Calibration from real H3 passages: frozen 0.05, slow push-in 1.25, peaks about 10.
FROZEN_MOTION = 0.35
# Frames skipped either side of a planned cut so the cut itself is not counted as motion.
CUT_GUARD = 2
MIN_WINDOW = 8
# Uniform opposite edge bands with a detailed interior are borders. Near-black
# flat edges can be a night scene, so they are reported as inconclusive only.
BORDER_STDDEV = 2.0
INTERIOR_STDDEV = 8.0
DARK_MEAN = 40
BORDER_BAND = 0.06
SAMPLES = 5
TIMEOUT = 120


def frame_differences(video, frames):
    output = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(video), "-frames:v", str(int(frames)), "-vf",
         "scale=184:104,format=gray,tblend=all_mode=difference,signalstats,"
         "metadata=print:key=lavfi.signalstats.YAVG:file=-", "-f", "null", "-"],
        capture_output=True, text=True, check=True, timeout=TIMEOUT).stdout
    # Value i is the change from frame i to frame i+1.
    return [float(line.split("=", 1)[1]) for line in output.splitlines() if "YAVG=" in line]


def shot_motion(differences, shot_starts, frames):
    """Motion per planned shot, excluding frames around cuts. Short shots are measured whole."""
    starts = sorted({s for s in shot_starts if 0 <= s < frames} | {0})
    result = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else frames
        lo, hi = start + (CUT_GUARD if start else 0), end - 1 - (CUT_GUARD if end < frames else 0)
        window = differences[lo:hi] if hi - lo >= MIN_WINDOW else differences[start:max(start + 1, end - 1)]
        if window:
            result.append({"start": start, "end": end, "motion": sum(window) / len(window)})
    return result


_PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _frames(video, indexes):
    if not indexes:
        return []
    expr = "+".join(f"eq(n\\,{i})" for i in indexes)
    data = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(video), "-vf", f"select={expr}",
         "-fps_mode", "passthrough", "-frames:v", str(len(indexes)), "-f", "image2pipe", "-vcodec", "png", "-"],
        capture_output=True, check=True, timeout=TIMEOUT).stdout
    if not data:
        return []
    from PIL import Image
    return [Image.open(io.BytesIO(_PNG_SIG + part)).convert("L") for part in data.split(_PNG_SIG)[1:] if part]


def _frame(video, index):
    frames = _frames(video, [index])
    return frames[0] if frames else None


def border_verdict(video, frames):
    """('left/right' | 'top/bottom' | None, inconclusive note | None) from sampled frames."""
    from PIL import ImageStat
    indexes = sorted({round(k * (max(frames, 1) - 1) / (SAMPLES - 1)) for k in range(SAMPLES)})
    votes = {"left/right": [0, 0], "top/bottom": [0, 0]}
    sampled = 0
    for image in _frames(video, indexes):
        if image is None:
            continue
        sampled += 1
        w, h = image.size
        dx, dy = max(2, int(w * BORDER_BAND)), max(2, int(h * BORDER_BAND))
        for name, (a, b, inner) in {
                "left/right": ((0, 0, dx, h), (w - dx, 0, w, h), (dx * 2, 0, w - dx * 2, h)),
                "top/bottom": ((0, 0, w, dy), (0, h - dy, w, h), (0, dy * 2, w, h - dy * 2))}.items():
            sa, sb, si = (ImageStat.Stat(image.crop(box)) for box in (a, b, inner))
            if sa.stddev[0] < BORDER_STDDEV and sb.stddev[0] < BORDER_STDDEV and si.stddev[0] >= INTERIOR_STDDEV:
                votes[name][0 if min(sa.mean[0], sb.mean[0]) > DARK_MEAN else 1] += 1
    if not sampled:
        raise ValueError("no frames could be decoded")
    for name, (bright, dark) in votes.items():
        if bright * 5 >= sampled * 3:
            return name, None
        if (bright + dark) * 5 >= sampled * 3:
            return None, f"flat dark {name} edges (possibly a night scene; not treated as borders)"
    return None, None


def inspect_clip(video, frames, shot_starts=(0,), check_borders=True):
    """Measure the part of a clip the final video uses.

    Returns status 'pass', 'fail' or 'error'. Errors mean the clip could not be
    measured; they never trigger a re-render.
    """
    try:
        differences = frame_differences(video, frames)
        if len(differences) < max(2, frames // 2):
            raise ValueError(f"only {len(differences)} of {frames} frames could be measured")
        shots = shot_motion(differences, shot_starts, frames)
        border, note = border_verdict(video, frames) if check_borders else (None, None)
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        return {"status": "error", "problems": [], "error": f"could not inspect clip: {exc}"}
    frozen = [shot for shot in shots if shot["motion"] < FROZEN_MOTION]
    problems = []
    if frozen:
        seconds = sum(shot["end"] - shot["start"] for shot in frozen) / 24
        worst = min(shot["motion"] for shot in frozen)
        problems.append(f"near-still image in {len(frozen)} of {len(shots)} shots, about {seconds:.1f} s "
                        f"(motion {worst:.2f}, minimum {FROZEN_MOTION})")
    if border:
        problems.append(f"uniform {border} borders; the picture does not fill the frame")
    return {"status": "fail" if problems else "pass", "problems": problems,
            "motion": round(sum(differences) / len(differences), 3),
            "shot_motion": [round(shot["motion"], 3) for shot in shots],
            "border": border, **({"note": note} if note else {})}
