"""
🪿 MAXIMUM GOOSE LABORATORY 🪿
validators.laya_semantic — the Laya decision-model adapter.

Laya (convaiinnovations/laya) is a multilingual, NON-AUTOREGRESSIVE
decision model: a ModernBERT-large backbone (395M) plus a from-scratch
decision head (2 transformer layers, an option-marker scorer, an
act/escalate head; 421M total). It does not generate text — it fills out
a typed clipboard of questions (choice / score / noul) in ONE forward
pass, scoring every option at its own [MASK] token. Because it can only
select among provided options it cannot hallucinate a critique; because
it was trained with RLCD against strictly proper scoring rules, its
probabilities are honest — it never bluffs about confidence.

THE CLIPBOARD (wire format, semantic_validator_handoff_v0.1):
build_clipboard_request() assembles the Request JSON — clip_version,
validator, run, state, questions — with clean keys (the knowledge-dump
rendering carried trailing-space artifacts; the house JSON rule says
normalize). The forward pass answers it; parse_laya_answers() normalizes
the package's raw answers into the Response wire shape (expected_level /
distribution / selected / probabilities / confidence).

THE PRECISION DECISION (handoff, locked): the full verbatim prompt rides
the state — no digest, ever. The model card's 512-token budget is a
training convention, not an architectural wall: the encoder natively
supports 8192 positions (max_position_embeddings). LAYA_MAX_LEN raises
the per-question sequence ceiling so the whole detailed_description
reaches the attention. If calibration drifts at this length during
empirical testing, the pivot is per-section validation — never a lossy
digest.

TRANSPORT: the checkout's own inference modules (rl_common.py +
rl_agent_api.py), vendored BYTE-IDENTICAL under validators/laya/ — the
scene_detection.py promotion precedent; the receipt rides laya/VENDOR.md.
Heavy machinery imports lazily INSIDE the seam: construction stays cheap,
the registry doorway stays fast, and a venv without the dependencies
refuses with a named sentence instead of dying at import time.

CONSEQUENCES (the declared ones, skill + handoff): visual_density at or
below its action_on max (2) triggers the corrective retry loop;
restriction_adherence != safe triggers it; structural_completeness
supplies the retry note's failure mode; style_adherence and
narrative_fidelity are RECORDED ONLY at this step — no consequence is
declared for them yet, and this adapter never invents one.

VRAM REALITY: validation runs in the write phase while the writer server
is resident. Laya is ~1 GB in bf16; if the GPU is tight,
MONDO_LAYA_DEVICE=cpu keeps the model on CPU — slower than the 33 ms GPU
figure, and one forward pass per segment is not latency-critical.
"""

from __future__ import annotations

import math
import os
import sys
import time
from pathlib import Path

from .base import KIND_SEMANTIC, ValidatorError, ValidatorProfile

CLIP_VERSION = 1

# THE PRECISION DECISION (handoff): feed the full verbatim prompt. The
# encoder's max_position_embeddings is 8192 (harvested config fact); 512
# is the training convention. If calibration drifts at this length during
# empirical testing, pivot to per-section validation — never a digest.
LAYA_MAX_LEN = 2048

# Retry trigger for visual density — the clipboard's action_on declares
# {"max": 2, "then": "retry"}: levels 1 or 2 enter the corrective loop.
DENSITY_RETRY_MAX_LEVEL = 2

# DIRECTOR RULING (2026-10-13, channel surf Step 7 finding): Laya rejects only
# when it is sure. Confidence is the package's own 1 - normalized entropy
# (0 = a uniform guess, 1 = certain); 0.25 is roughly a 60% top answer among
# five options. A density or restriction verdict below the floor is recorded
# in the response but carries no consequence. An answer that reports no
# confidence at all (older response shapes) is judged exactly as before.
DECISION_CONFIDENCE_FLOOR = 0.25

# The clipboard, as data (wire format; keys normalized per the house JSON
# rule). Order matters: it is the state the model reads.
CLIPBOARD_QUESTIONS = (
    {
        "id": "visual_density",
        "type": "score",
        "text": "Rate the visual density and pacing of this prompt for "
                "the requested number of shots.",
        "levels": {
            "1": "Too sparse; will render as static, under-described frames",
            "2": "Under-described for the shot count",
            "3": "Balanced; appropriate density per shot",
            "4": "Rich and well-paced",
            "5": "Overstuffed; will confuse the renderer",
        },
        "action_on": {"max": 2, "then": "retry"},
    },
    {
        "id": "structural_completeness",
        "type": "choice",
        "text": "Which core cinematic element is most lacking in this "
                "prompt?",
        "options": [
            "complete",
            "missing_subject",
            "missing_action",
            "missing_camera_framing",
            "missing_lighting_atmosphere",
        ],
    },
    {
        "id": "style_adherence",
        "type": "choice",
        "text": "Does this prompt's aesthetic align with the style card?",
        "options": ["strong_match", "weak_match", "contradicts_style"],
    },
    {
        "id": "restriction_adherence",
        "type": "choice",
        "text": "Does this prompt violate any active content restriction?",
        "options": [
            "safe",
            "violates_nudity",
            "violates_gore",
            "violates_violence",
            "violates_sexual_content",
        ],
    },

)

# Human labels and deterministic corrective notes for the retry voice.
# The writer LLM reads a cinematic note, not a math error.
FAILURE_MODE_LABELS = {
    "missing_subject": "Missing Subject",
    "missing_action": "Missing Action",
    "missing_camera_framing": "Missing Camera/Framing",
    "missing_lighting_atmosphere": "Missing Lighting/Atmosphere",
}


def _failure_mode_note(mode, shot_count):
    """Deterministic corrective note per failure mode — authored feedback,
    never a model-generated critique."""
    if mode == "missing_subject":
        return "Name a concrete subject in every shot."
    if mode == "missing_action":
        return "Give every shot a concrete action or movement."
    if mode == "missing_camera_framing":
        return f"The {shot_count} shots lack distinct camera movements."
    if mode == "missing_lighting_atmosphere":
        return "State the lighting and atmosphere of every shot."
    return ""


def _word_window(shot_count):
    """The shot-count-scaled word window, the schema.py math verbatim
    (validate_prompt / build_writer_request). The heuristic profile
    enforces it; the clipboard carries it so Laya weighs density against
    the same numbers."""
    shot_count = max(1, int(shot_count))
    min_words = max(150, int(shot_count * 55))
    max_words = max(900, int(shot_count * 100))
    max_words = min(1500, max_words)
    min_words = min(min_words, max_words)
    return {"min": min_words, "max": max_words}


def _two_option_confidence(p):
    """Jev-style confidence for a noul answer: 1 - normalized binary
    entropy of [1-p, p]. The package's own confidence_from_probs formula
    for k=2, recomputed here because the package omits it for noul."""
    p = min(max(float(p), 0.0), 1.0)
    ent = 0.0
    for x in (p, 1.0 - p):
        if x > 0.0:
            ent -= x * math.log(x)
    return round(1.0 - ent / math.log(2), 4)


def resolve_model_dir():
    from ...storage import Storage
    return Path(Storage().settings()["laya_model_dir"]).expanduser()


def _model_dir_staged(model_dir):
    return (
        (model_dir / "model.safetensors").exists()
        and (model_dir / "rl_agent_config.json").exists()
        and (model_dir / "tokenizer").is_dir()
        and (model_dir / "encoder" / "config.json").exists()
    )


class LayaSemanticValidator(ValidatorProfile):
    """The local Laya decision model. Registered for selection; NEVER a
    default. Construction is cheap — the checkpoint load is lazy inside
    the seam, so the registry doorway never waits on a model."""

    validator = "laya_semantic"
    display_name = "Laya Semantic (decision model, local)"
    kind = KIND_SEMANTIC
    latency_ms = 33
    cost_per_call = 0.0
    supports_narrative_fidelity = False

    def __init__(self):
        super().__init__()
        self._agent = None
        self._model_dir = None

    # ------------------------------------------------------------ the seam
    def _load_agent(self):
        """LAZY LOAD — the named seam. Imports the vendored inference
        modules and loads the checkpoint the first time a prompt is
        judged. Every failure rung is a loud ValidatorError naming the
        problem and stating nothing was judged; a Laya failure NEVER
        falls back to the heuristic silently — rollback is the
        Director's explicit choice."""
        if self._agent is not None:
            return self._agent
        model_dir = resolve_model_dir()
        if not _model_dir_staged(model_dir):
            raise ValidatorError(
                f"LAYA MODEL MISSING: {model_dir} is not staged — it needs "
                "model.safetensors, rl_agent_config.json, tokenizer/, and "
                "encoder/config.json. Configure your Laya model folder in Settings. "
                "Nothing was judged or rendered.")
        # README fact: transformers probes TensorFlow at import, and the
        # abseil runtime can deadlock model construction when TF is present.
        os.environ.setdefault("USE_TF", "0")
        vendor_dir = Path(__file__).resolve().parent / "laya"
        if str(vendor_dir) not in sys.path:
            sys.path.insert(0, str(vendor_dir))
        try:
            import rl_agent_api
        except ImportError as e:
            raise ValidatorError(
                f"LAYA DEPENDENCIES MISSING: the vendored inference modules "
                f"failed to import ({e}) — torch and numpy must be "
                "importable. Nothing was judged.") from e
        import torch
        from ...storage import Storage
        device = Storage().settings()["laya_device"]
        if device == "auto":
            if torch.cuda.is_available():
                device = "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"
        elif device in ("cuda_or_cpu", "mps_or_cpu"):
            if device == "cuda_or_cpu":
                device = "cuda" if torch.cuda.is_available() else "cpu"
            else:
                device = "mps" if hasattr(torch.backends, "mps") and torch.backends.mps.is_available() else "cpu"
        self.device = device
        try:
            agent = rl_agent_api.RLAgent(str(model_dir), device=device)
        except ImportError as e:
            raise ValidatorError(
                f"LAYA DEPENDENCIES MISSING: {e} — install transformers and "
                "safetensors into the mondo venv before selecting "
                "laya_semantic. Nothing was judged.") from e
        except Exception as e:
            raise ValidatorError(
                f"LAYA LOAD FAILED: {model_dir} refused to load: {e}. "
                "Nothing was judged.") from e
        # THE PRECISION DECISION: raise the per-question sequence ceiling
        # from the 512-token training convention. system_one reads the cfg
        # at call time, so the override rides every forward pass.
        agent.cfg["max_len"] = LAYA_MAX_LEN
        self._agent = agent
        self._model_dir = model_dir
        return agent

    # ---------------------------------------------------------- clipboard
    def build_clipboard_request(self, prompt, segment, tags, *,
                                strict_words=True, silent_mouths=True,
                                state=None):
        """The Request JSON (wire format). `state` carries the run-level
        facts the master pipeline knows (slug, backend, restrictions,
        style/cast digests, lyrics flavor, director's direction, breakdown
        beat); everything absent is omitted, never guessed."""
        state = dict(state or {})
        shot_count = max(1, len(getattr(segment, "shots", None) or []))
        clip_state = {
            "kind": "writer_prompt",
            "shot_count": shot_count,
            "word_window": _word_window(shot_count),
            "silent_mouths": bool(silent_mouths),
        }
        if state.get("restrictions") not in (None, {}, []):
            clip_state["restrictions"] = dict(state["restrictions"])
        for key in ("style_digest", "cast_digest"):
            if state.get(key):
                clip_state[key] = str(state[key])
        # THE PRECISION DECISION: the full verbatim prompt, no digest.
        clip_state["prompt_text"] = str(prompt)
        for key in ("lyrics_flavor", "director_direction"):
            if state.get(key):
                clip_state[key] = str(state[key])
        questions = []
        for q in CLIPBOARD_QUESTIONS:
            if (q.get("gated_on") == "run_has_breakdown"
                    and not clip_state.get("breakdown_beat")):
                continue
            questions.append(dict(q))
        return {
            "clip_version": CLIP_VERSION,
            "validator": self.validator,
            "run": {
                "slug": str(state.get("slug") or ""),
                "segment_id": str(getattr(segment, "segment_id", "") or ""),
                "backend": str(state.get("backend") or ""),
            },
            "state": clip_state,
            "questions": questions,
        }

    @staticmethod
    def _jev_questions(questions):
        """Clipboard questions -> the package's Jev request shape
        {id: {type, instructions, criteria}}. Score criteria ride as the
        level texts in level order; choice criteria as the bare option
        keys — each option is scored at its own [MASK] marker."""
        out = {}
        for q in questions:
            if q["type"] == "score":
                levels = q["levels"]
                out[q["id"]] = {
                    "type": "score",
                    "instructions": q["text"],
                    "criteria": [levels[str(i)]
                                 for i in range(1, len(levels) + 1)],
                }
            elif q["type"] == "choice":
                out[q["id"]] = {
                    "type": "choice",
                    "instructions": q["text"],
                    "criteria": list(q["options"]),
                }
            else:  # noul
                out[q["id"]] = {
                    "type": "noul",
                    "instructions": q["text"],
                }
        return out

    @staticmethod
    def parse_laya_answers(raw_answers, questions):
        """Raw package answers -> the Response wire shape. The package
        indexes score levels from 0 ('level 0: ...'); the wire rubric is
        1-based, so expected_level = package score + 1 and distribution
        keys shift up by one."""
        answers = {}
        for q in questions:
            raw = (raw_answers or {}).get(q["id"])
            if raw is None:
                continue
            if q["type"] == "score":
                probs = raw.get("probabilities") or {}
                answers[q["id"]] = {
                    "expected_level": round(
                        float(raw.get("score", 0.0)) + 1.0, 4),
                    "distribution": {str(int(k) + 1): float(v)
                                     for k, v in probs.items()},
                    "confidence": float(raw.get("confidence", 0.0)),
                }
            elif q["type"] == "choice":
                answers[q["id"]] = {
                    "selected": raw.get("choice"),
                    "probabilities": dict(raw.get("probabilities") or {}),
                    "confidence": float(raw.get("confidence", 0.0)),
                }
            else:  # noul
                p = float(raw.get("noul", 0.0))
                answers[q["id"]] = {
                    "probability": p,
                    "confidence": _two_option_confidence(p),
                }
        return answers

    # ---------------------------------------------------------- judgment
    def decide(self, response, clip):
        """Answers -> problems, by the DECLARED consequences only.
        visual_density at or below its action_on max and
        restriction_adherence != safe trigger the corrective retry loop —
        but only at or above DECISION_CONFIDENCE_FLOOR (a guess abstains);
        structural_completeness names the failure mode in the retry note.
        style_adherence and narrative_fidelity are recorded in the
        response but enforce nothing at this step — no consequence is
        declared for them yet, and this adapter never invents one."""
        problems = []
        answers = response.get("answers") or {}
        shot_count = int(clip["state"]["shot_count"])

        def sure(answer):
            conf = (answer or {}).get("confidence")
            return conf is None or float(conf) >= DECISION_CONFIDENCE_FLOOR

        action_max = DENSITY_RETRY_MAX_LEVEL
        for q in clip["questions"]:
            if q["id"] == "visual_density":
                action_max = int((q.get("action_on") or {}).get(
                    "max", DENSITY_RETRY_MAX_LEVEL))
                break

        density = answers.get("visual_density")
        if density and sure(density):
            # Half-up rounding to the displayed rubric level: 2.3 -> 2.
            level = int(float(density.get("expected_level", 0.0)) + 0.5)
            if level <= action_max:
                note = (f"Semantic Validator rejected: Visual density "
                        f"scored {level}/5.")
                mode = (answers.get("structural_completeness") or {}).get(
                    "selected")
                if mode and mode != "complete":
                    label = FAILURE_MODE_LABELS.get(mode, mode)
                    note += f" Primary failure mode: {label}."
                    extra = _failure_mode_note(mode, shot_count)
                    if extra:
                        note += " " + extra
                problems.append(note)

        restriction = answers.get("restriction_adherence") or {}
        selected = restriction.get("selected")
        if selected and selected != "safe" and sure(restriction):
            problems.append(
                "Semantic Validator rejected: restriction adherence "
                f"selected '{selected}' — the prompt violates an active "
                "content boundary.")
        return problems

    def run_clipboard(self, prompt, segment, tags, *, strict_words=True,
                      silent_mouths=True, state=None):
        """Build the clipboard, run ONE forward pass, normalize the
        answers. Returns (response_dict, problems). Step 6's wiring may
        call this directly to receipt the full response as a run
        artifact; the contract method validate_prompt returns only the
        problems."""
        agent = self._load_agent()
        clip = self.build_clipboard_request(
            prompt, segment, tags, strict_words=strict_words,
            silent_mouths=silent_mouths, state=state)
        self.last_clipboard_request = clip
        t0 = time.time()
        try:
            result = agent.system_one(clip["state"],
                                      self._jev_questions(clip["questions"]))
        except Exception as e:
            raise ValidatorError(
                f"LAYA FORWARD PASS FAILED: {e}. The prompt was not "
                "judged; nothing was queued.") from e
        response = {
            "segment_id": clip["run"]["segment_id"],
            "latency_ms": int(round((time.time() - t0) * 1000)),
            "answers": self.parse_laya_answers(
                result.get("answers") or {}, clip["questions"]),
        }
        return response, self.decide(response, clip)

    # ---------------------------------------------------------- contract
    def validate_prompt(self, prompt, segment, tags, *, strict_words=True,
                        silent_mouths=True, state=None) -> list[str]:
        """The contract method. The deterministic regex checks stay in
        the heuristic profile (house rule); Laya owns semantic quality
        only."""
        _response, problems = self.run_clipboard(
            prompt, segment, tags, strict_words=strict_words,
            silent_mouths=silent_mouths, state=state)
        return problems

    def format_retry_feedback(self, problems) -> str:
        """The cinematic note rides the REJECTED line exactly as the
        heuristic's math error does — the master's retry machinery reads
        the same shape either way."""
        return "; ".join(problems)