"""
🪿 MAXIMUM GOOSE LABORATORY 🪿
validators.base — the validator profile contract.

A validator judges a composed writer prompt BEFORE it may be queued for
rendering. Two voices join the pipeline through this contract:

  heuristic      the deterministic extraction of the schema.py logic —
                 shot-count-scaled word windows, the 12000-character
                 context budget, the SEALED LIPS rigging check. The
                 DEFAULT and the rollback path.
  semantic       a non-autoregressive decision model (Laya) that reads
                 the full prompt and fills out a typed clipboard of
                 questions in one forward pass, answering with honest
                 calibrated probabilities instead of generated text.

The contract mirrors mondo.backends and mondo.llms: a profile declares
WHAT it is in a capabilities dict, construction validates the
declaration at the doorway, and capabilities() returns a FRESH dict on
every call so a caller scribbling on one result can never poison the
next reader.

Required capability keys (validated at construction):

  validator                   registry name, e.g. "heuristic"
  display_name                human name for menus and the GUI
  kind                        "heuristic" or "semantic"
  latency_ms                  expected forward pass time in ms
                              (0 for the deterministic checks)
  cost_per_call               dollars, 0.0 for local. The GUI must show
                              API costs in big text before any paid run.
  supports_narrative_fidelity bool — True when the validator can check
                              Layer 2 Breakdown intent (short-film stage)

Sequencing rule (same as backends and llms): declare it in
capabilities, teach the pipeline/GUI to read the declaration, only then
implement per-provider behaviour. `heuristic` stays the default until
the Director says otherwise; a new validator must never become the
default silently.
"""

from __future__ import annotations

KIND_HEURISTIC = "heuristic"
KIND_SEMANTIC = "semantic"

KINDS = (KIND_HEURISTIC, KIND_SEMANTIC)


class ValidatorError(Exception):
    """A validator profile is unknown, incomplete, or cannot serve the
    request."""


class ValidatorProfile:
    """The contract every validator profile honours.

    Subclasses declare their facts as class attributes. Construction
    validates the declaration so an incomplete profile fails loudly at
    the doorway, not mid-write as a KeyError.
    """

    validator = None                    # registry name
    display_name = None                 # human name for menus and the GUI
    kind = None                         # KIND_HEURISTIC or KIND_SEMANTIC
    latency_ms = None                   # expected forward pass time (ms)
    cost_per_call = None                # dollars; 0.0 for local
    supports_narrative_fidelity = None  # bool

    REQUIRED = (
        "validator",
        "display_name",
        "kind",
        "latency_ms",
        "cost_per_call",
        "supports_narrative_fidelity",
    )

    def __init__(self):
        missing = [k for k in self.REQUIRED if getattr(self, k, None) is None]
        if missing:
            raise ValidatorError(
                f"Validator profile '{self.validator or '?'}' is missing "
                f"declarations: {', '.join(missing)}"
            )
        if self.kind not in KINDS:
            raise ValidatorError(
                f"Validator profile '{self.validator}' kind must be "
                f"'{KIND_HEURISTIC}' or '{KIND_SEMANTIC}', got {self.kind!r}"
            )
        try:
            latency = float(self.latency_ms)
        except (TypeError, ValueError):
            latency = -1.0
        if latency < 0:
            raise ValidatorError(
                f"Validator profile '{self.validator}' latency_ms must be "
                f"a number of milliseconds >= 0, got {self.latency_ms!r}"
            )
        try:
            cost = float(self.cost_per_call)
        except (TypeError, ValueError):
            cost = -1.0
        if cost < 0:
            raise ValidatorError(
                f"Validator profile '{self.validator}' cost_per_call must "
                f"be dollars >= 0.0, got {self.cost_per_call!r}"
            )
        if not isinstance(self.supports_narrative_fidelity, bool):
            raise ValidatorError(
                f"Validator profile '{self.validator}' "
                f"supports_narrative_fidelity must be a bool, got "
                f"{self.supports_narrative_fidelity!r}"
            )

    def capabilities(self) -> dict:
        """A FRESH dict on every call; a caller mutating the result cannot
        poison the next reader (the backends discipline)."""
        return {
            "validator": self.validator,
            "display_name": self.display_name,
            "kind": self.kind,
            "latency_ms": self.latency_ms,
            "cost_per_call": self.cost_per_call,
            "supports_narrative_fidelity": self.supports_narrative_fidelity,
        }

    def validate_prompt(self, prompt, segment, tags, *, strict_words=True,
                        silent_mouths=True, state=None) -> list[str]:
        """Judge one composed prompt. Returns a list of problems; an empty
        list means the prompt may be queued.

        prompt          the assembled six-field prompt text
        segment         the planner's segment (shot count, cut times, ...)
        tags            the wired reference tags for this segment
        strict_words    False (--lax) skips the word and budget checks
        silent_mouths   True requires the sealed-lips rigging phrase
        state           optional run-level facts for semantic validators
                        (style/cast digests, restrictions, lyrics flavor,
                        director's direction, breakdown beat); the
                        heuristic validator ignores it

        The shape mirrors mondo.schema.validate_prompt, which the
        heuristic profile delegates to — the byte-identity seam.
        """
        raise NotImplementedError(
            f"Validator '{self.validator}' does not implement "
            f"validate_prompt()."
        )

    def format_retry_feedback(self, problems) -> str:
        """The one-line reason string for a failed segment. It rides the
        cli REJECTED line and the master's corrective retry feedback —
        the writer LLM reads it on the retry. The heuristic voice is the
        math error; a semantic voice composes a cinematic note."""
        raise NotImplementedError(
            f"Validator '{self.validator}' does not implement "
            f"format_retry_feedback()."
        )