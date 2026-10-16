"""
🪿 MAXIMUM GOOSE LABORATORY 🪿
seedance.py — rate-card-backed Seedance 2 and Seedance 2.5 renderers.

The two concrete backends are registered by name, but they are only offered
when a valid rate card is staged. The rate card is the single source of truth
for model path, price, durations, aspect ratios, resolutions, reference
ceilings, and wire field names. Nothing is hard-coded here.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from . import keys
from .base import Backend, BackendError, TAG_SYNTAX_SEEDANCE
from ..comfy import slice_audio
from .wavespeed import (
    TERMINAL_BAD,
    TERMINAL_OK,
    _http,
    _looks_like_drift,
    _parse_json,
    base_url,
    result_url,
    upload_file,
    wavespeed_ref_tags,
)

KEY_PROVIDER = "wavespeed"
RATE_CARD_ENV = "SEEDANCE_RATE_CARD"

RATE_CARD_NAMES = ("seedance_2", "seedance_2_5")

REQUIRED_ENTRY_KEYS = (
    "source",
    "display_name",
    "model_path",
    "cost_per_generation",
    "price_per_second",
    "allowed_seconds",
    "aspect_ratios",
    "resolutions",
    "resolution_sizes",
    "max_reference_images",
    "max_reference_videos",
    "max_reference_audios",
    "min_reference_images",
    "supports_seed",
    "max_prompt_chars",
    "fields",
)

REQUIRED_FIELD_ROLES = ("prompt", "duration", "images")
OPTIONAL_FIELD_ROLES = ("aspect_ratio", "resolution", "audios", "seed")
ALLOWED_FIELD_ROLES = REQUIRED_FIELD_ROLES + OPTIONAL_FIELD_ROLES

RATE_CARD_MISSING = (
    "SEEDANCE RATE CARD MISSING. Nothing was rendered or charged."
)
RATE_CARD_UNREADABLE = (
    "SEEDANCE RATE CARD UNREADABLE. Nothing was rendered or charged."
)
RATE_CARD_REFUSED = (
    "SEEDANCE RATE CARD REFUSED (missing keys / unknown keys / "
    "unmapped required role). Nothing was rendered or charged."
)
PRICE_NOT_CONFIRMED = (
    "SEEDANCE PRICE NOT CONFIRMED. Nothing was rendered or charged."
)
REQUEST_REFUSED = (
    "SEEDANCE REQUEST REFUSED. Nothing was uploaded or charged."
)
SCHEMA_DRIFT = (
    "POSSIBLE SCHEMA DRIFT (Seedance). Nothing was rendered or charged."
)


def _rate_card_path() -> Path:
    env = os.environ.get(RATE_CARD_ENV)
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[1] / "config" / "seedance_rate_card.json"


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_entry(entry: dict[str, Any]) -> str | None:
    if set(entry.keys()) != set(REQUIRED_ENTRY_KEYS):
        return RATE_CARD_REFUSED

    if not _is_nonempty_str(entry["source"]):
        return RATE_CARD_REFUSED
    if not _is_nonempty_str(entry["display_name"]):
        return RATE_CARD_REFUSED
    if not _is_nonempty_str(entry["model_path"]):
        return RATE_CARD_REFUSED

    if not _is_number(entry["cost_per_generation"]):
        return PRICE_NOT_CONFIRMED
    if float(entry["cost_per_generation"]) <= 0.0:
        return PRICE_NOT_CONFIRMED

    # WaveSpeed bills Seedance by the second, per resolution. Every offered
    # resolution must carry a positive rate; cost_per_generation stays the
    # CEILING (the longest clip at the dearest resolution).
    rates = entry["price_per_second"]
    if not isinstance(rates, dict):
        return PRICE_NOT_CONFIRMED
    if not all(_is_number(v) and float(v) > 0.0 for v in rates.values()):
        return PRICE_NOT_CONFIRMED
    if not all(r in rates for r in entry.get("resolutions") or []):
        return PRICE_NOT_CONFIRMED

    allowed_seconds = entry["allowed_seconds"]
    if not isinstance(allowed_seconds, list) or not allowed_seconds:
        return RATE_CARD_REFUSED
    if not all(_is_int(x) and x > 0 for x in allowed_seconds):
        return RATE_CARD_REFUSED

    aspect_ratios = entry["aspect_ratios"]
    if not isinstance(aspect_ratios, list) or not aspect_ratios:
        return RATE_CARD_REFUSED
    if not all(_is_nonempty_str(x) for x in aspect_ratios):
        return RATE_CARD_REFUSED

    resolutions = entry["resolutions"]
    if not isinstance(resolutions, list) or not resolutions:
        return RATE_CARD_REFUSED
    if not all(_is_nonempty_str(x) for x in resolutions):
        return RATE_CARD_REFUSED

    resolution_sizes = entry["resolution_sizes"]
    if not isinstance(resolution_sizes, dict):
        return RATE_CARD_REFUSED
    if not all(_is_int(v) and v > 0 for v in resolution_sizes.values()):
        return RATE_CARD_REFUSED
    if not all(r in resolution_sizes for r in resolutions):
        return RATE_CARD_REFUSED

    for key in (
        "max_reference_images",
        "max_reference_videos",
        "max_reference_audios",
        "min_reference_images",
    ):
        if not _is_int(entry[key]) or entry[key] < 0:
            return RATE_CARD_REFUSED

    if not isinstance(entry["supports_seed"], bool):
        return RATE_CARD_REFUSED

    max_prompt_chars = entry["max_prompt_chars"]
    if max_prompt_chars is not None and not _is_int(max_prompt_chars):
        return RATE_CARD_REFUSED

    fields = entry["fields"]
    if not isinstance(fields, dict):
        return RATE_CARD_REFUSED
    if not all(k in ALLOWED_FIELD_ROLES for k in fields):
        return RATE_CARD_REFUSED
    for role in REQUIRED_FIELD_ROLES:
        if role not in fields or not _is_nonempty_str(fields[role]):
            return RATE_CARD_REFUSED
    for role in OPTIONAL_FIELD_ROLES:
        if role in fields and not _is_nonempty_str(fields[role]):
            return RATE_CARD_REFUSED

    return None


def load_rate_card() -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Read the Seedance rate card. Never raises.

    Returns (entries, refusals). A name appears in entries only when its
    entry is valid; otherwise it appears in refusals with a stable sentence.
    """
    path = _rate_card_path()

    if not path.exists():
        return {}, {name: RATE_CARD_MISSING for name in RATE_CARD_NAMES}

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return {}, {name: RATE_CARD_UNREADABLE for name in RATE_CARD_NAMES}

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}, {name: RATE_CARD_UNREADABLE for name in RATE_CARD_NAMES}

    if not isinstance(data, dict):
        return {}, {name: RATE_CARD_REFUSED for name in RATE_CARD_NAMES}

    entries: dict[str, dict[str, Any]] = {}
    refusals: dict[str, str] = {}

    for name in RATE_CARD_NAMES:
        entry = data.get(name)
        if not isinstance(entry, dict):
            refusals[name] = RATE_CARD_REFUSED
            continue
        refusal = _validate_entry(entry)
        if refusal:
            refusals[name] = refusal
        else:
            entries[name] = entry

    return entries, refusals


# ---------------------------------------------------------------------------
# The model's shape. The house writes, checks and stores every tagged prompt
# in its own grammar (<Picture 1>, <Subject 1>, <Audio 1>, and for a music
# segment the six labelled fields with [Shot N] markers). Seedance reads a
# prompt best as a summary, then a timeline, then consistency notes
# (WaveSpeed's Seedance docs, 2026-10-14). to_seedance() reshapes the
# finished prompt just before the submit and keeps the house's <Picture N>
# tags; the PROVIDER's tag grammar is applied after it, by the transport
# (wavespeed.wavespeed_ref_tags). Model shape and provider grammar stay apart,
# so Seedance through another provider needs only that provider's tags.
# ---------------------------------------------------------------------------

_FIELD_NAMES = ("subject_definitions", "summary", "retention_analysis",
                "detailed_description", "overall_soundscape", "non_diegetic_music")
_SHOT_RE = re.compile(r"\[Shot (\d+)\]\s*(?:At (\d+):(\d+(?:\.\d+)?),\s*)?")


def _tags(text: str) -> str:
    """The house-only names the model never sees: <Subject N> -> Subject N,
    and (Seedance gets no audio reference here) <Audio N> -> the music it
    stood for. <Picture N> and <Video N> stay for the provider to bind."""
    text = re.sub(r"<Subject (\d+)>", r"Subject \1", text)
    return re.sub(r"<Audio \d+>", "the music", text)


def _fields(prompt: str) -> dict[str, str] | None:
    """The six labelled fields of a house music prompt, or None for prose."""
    if not prompt.lstrip().startswith("subject_definitions:"):
        return None
    out, key, buf = {}, None, []
    for line in prompt.splitlines():
        name = line.strip().rstrip(":")
        if line.strip().endswith(":") and name in _FIELD_NAMES:
            if key:
                out[key] = "\n".join(buf).strip()
            key, buf = name, []
        else:
            buf.append(line)
    if key:
        out[key] = "\n".join(buf).strip()
    return out


def _seconds(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".") + "s"


def to_seedance(prompt: str, seconds: float | None = None) -> str:
    """One house prompt in Seedance's grammar. A music segment becomes
    summary, cast, look, a timeline of its shots, and sound notes; prose (a
    channel, an ident) keeps its words and only its tags change."""
    fields = _fields(prompt)
    if fields is None:
        return _tags(prompt).strip()
    cast = [ln.strip() for ln in fields.get("subject_definitions", "").splitlines()
            if ln.strip() and "<Audio" not in ln]
    detailed = fields.get("detailed_description", "")
    marks = list(_SHOT_RE.finditer(detailed))
    look = (detailed[:marks[0].start()] if marks else detailed).strip()
    shots = []
    for i, m in enumerate(marks):
        start = float(m.group(2)) * 60 + float(m.group(3)) if m.group(2) else 0.0
        body = detailed[m.end():marks[i + 1].start() if i + 1 < len(marks) else None].strip()
        shots.append((start, body))
    lines = [_tags(fields.get("summary", "")).strip(), ""]
    if cast:
        lines += ["Cast: " + " ".join(_tags(c) for c in cast), ""]
    if look:
        lines += ["Look: " + _tags(look), ""]
    if shots:
        lines.append("Timeline:")
        for i, (start, body) in enumerate(shots):
            end = shots[i + 1][0] if i + 1 < len(shots) else seconds
            span = (f"{_seconds(start)}–{_seconds(end)}" if end is not None
                    else f"from {_seconds(start)}")
            lines.append(f"{span}: {_tags(body)}")
        lines.append("")
    sound = _tags(fields.get("overall_soundscape", "")).strip()
    notes = "Keep every subject's face, build and costume identical from shot to shot."
    if sound:
        notes += f" Sound: {sound}"
    lines += [notes + " No subtitles. No background music."]
    return "\n".join(lines).strip()


def rate_card_ready(name: str) -> bool:
    entries, _ = load_rate_card()
    return name in entries


def rate_card_refusal(name: str) -> str:
    _, refusals = load_rate_card()
    return refusals.get(name, RATE_CARD_MISSING)


class SeedanceBackend(Backend):
    """Shared Seedance transport and rate-card-backed capability shape."""

    name = ""

    def __init__(self) -> None:
        super().__init__()
        entries, _ = load_rate_card()
        entry = entries.get(self.name)
        if entry is None:
            raise BackendError(rate_card_refusal(self.name))

        self._entry = entry
        self._model_path = str(entry["model_path"])
        self._cost = float(entry["cost_per_generation"])
        self._rates = {str(k): float(v) for k, v in entry["price_per_second"].items()}
        self._fields = dict(entry["fields"])
        self._allowed_seconds = sorted(int(x) for x in entry["allowed_seconds"])
        self._aspect_ratios = list(entry["aspect_ratios"])
        self._resolutions = list(entry["resolutions"])
        self._resolution_sizes = dict(entry["resolution_sizes"])
        self._max_prompt_chars = entry["max_prompt_chars"]
        self._max_reference_images = int(entry["max_reference_images"])
        self._max_reference_videos = int(entry["max_reference_videos"])
        self._max_reference_audios = int(entry["max_reference_audios"])
        self._min_reference_images = int(entry["min_reference_images"])
        self._supports_seed = bool(entry["supports_seed"])
        self._audio_supported = (
            "audios" in self._fields and self._max_reference_audios >= 1
        )

    def capabilities(self) -> dict[str, Any]:
        return {
            "backend": self.name,
            "display_name": self._entry["display_name"],
            "frame_lattice": {
                "mode": "seconds",
                "fps": 24,
                "allowed_seconds": list(self._allowed_seconds),
            },
            "max_reference_images": self._max_reference_images,
            "max_reference_videos": self._max_reference_videos,
            "max_reference_audios": self._max_reference_audios,
            "min_reference_images": self._min_reference_images,
            "audio_conditioning": {
                "supported": self._audio_supported,
                "how": "reference_audio_urls",
            },
            "prompt_tag_syntax": TAG_SYNTAX_SEEDANCE,
            "max_prompt_chars": self._max_prompt_chars,
            "resolution_mode": "fixed_list",
            "resolutions": list(self._resolutions),
            "resolution_sizes": dict(self._resolution_sizes),
            "supports_seed": self._supports_seed,
            "steps": None,
            "cost_per_generation": self._cost,
            "price_per_second": dict(self._rates),
            "key_provider": KEY_PROVIDER,
            "aspect_ratios": list(self._aspect_ratios),
            "fields": dict(self._fields),
        }

    def cost_for(self, seconds: float, resolution: str | None = None,
                 images: int = 0) -> float:
        """WaveSpeed's per-second rate for the resolution, times the billed
        seconds (Seedance bills whole seconds, never under its shortest)."""
        name = str(resolution) if resolution else self.default_resolution()
        rate = self._rates.get(str(name))
        if rate is None:
            return self._cost
        billed = max(int(-(-float(seconds) // 1)), min(self._allowed_seconds))
        return round(rate * billed, 2)

    def nearest_aspect(self, width: int, height: int) -> str:
        """plan.json records width/height; the API wants one of the card's
        aspect ratios. The closest one (exact for a plan this backend made)."""
        ratio = float(width) / float(height)

        def _r(a: str) -> float:
            w, h = (int(x) for x in a.split(":"))
            return w / h

        return min(self._aspect_ratios, key=lambda a: abs(_r(a) - ratio))

    def _submit_url(self) -> str:
        return f"{base_url()}/{self._model_path}"

    def _is_url(self, value: str) -> bool:
        return value.startswith("http://") or value.startswith("https://")

    def _validate_request(
        self,
        *,
        prompt: str,
        duration_input: float,
        images: list[str],
        audios: list[str] | None,
        aspect_ratio: str | None,
        resolution: str | None,
        seed: int | None,
    ) -> int:
        if not isinstance(prompt, str) or not prompt.strip():
            raise BackendError(REQUEST_REFUSED)

        if self._max_prompt_chars is not None and len(prompt) > int(self._max_prompt_chars):
            raise BackendError(REQUEST_REFUSED)

        if len(images) < self._min_reference_images:
            raise BackendError(REQUEST_REFUSED)
        if len(images) > self._max_reference_images:
            raise BackendError(REQUEST_REFUSED)

        duration = int(duration_input)
        if float(duration_input) != float(duration):
            raise BackendError(REQUEST_REFUSED)
        if duration not in self._allowed_seconds:
            raise BackendError(REQUEST_REFUSED)

        if aspect_ratio is not None and aspect_ratio not in self._aspect_ratios:
            raise BackendError(REQUEST_REFUSED)

        if resolution is not None and resolution not in self._resolutions:
            raise BackendError(REQUEST_REFUSED)

        audios = audios or []
        if audios and not self._audio_supported:
            raise BackendError(REQUEST_REFUSED)
        if len(audios) > self._max_reference_audios:
            raise BackendError(REQUEST_REFUSED)

        if seed is not None:
            if not self._supports_seed:
                raise BackendError(REQUEST_REFUSED)
            if not _is_int(seed):
                raise BackendError(REQUEST_REFUSED)

        return duration

    def _build_payload(
        self,
        *,
        prompt: str,
        duration: int,
        image_urls: list[str],
        audio_urls: list[str],
        aspect_ratio: str | None,
        resolution: str | None,
        seed: int | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            self._fields["prompt"]: prompt,
            self._fields["duration"]: duration,
            self._fields["images"]: image_urls,
        }

        if aspect_ratio is not None and "aspect_ratio" in self._fields:
            payload[self._fields["aspect_ratio"]] = aspect_ratio

        if resolution is not None and "resolution" in self._fields:
            payload[self._fields["resolution"]] = resolution

        if audio_urls and "audios" in self._fields:
            payload[self._fields["audios"]] = audio_urls

        if seed is not None and "seed" in self._fields:
            payload[self._fields["seed"]] = seed

        return payload

    # Upload memo for one render run (the WaveSpeed H3 shape): a sheet cited
    # by many segments is uploaded once. None outside open/close_render.
    _url_cache: dict | None = None

    def _upload_if_needed(self, value: str, *, api_key: str) -> str:
        if self._is_url(value):
            return value
        cache = self._url_cache
        if cache is not None and value in cache:
            return cache[value]
        try:
            url = upload_file(value, api_key=api_key)
        except Exception:
            raise BackendError(REQUEST_REFUSED)
        if cache is not None:
            cache[value] = url
        return url

    def generate(
        self,
        *,
        prompt: str,
        duration_input: float,
        images: list[str],
        audios: list[str] | None = None,
        aspect_ratio: str | None = None,
        resolution: str | None = None,
        seed: int | None = None,
        out_dir: str | Path,
        poll_s: float = 1.0,
        timeout_s: float = 600.0,
        quiet: bool = False,
        api_key: str | None = None,
        name_prefix: str | None = None,
    ) -> dict[str, Any]:
        if api_key is None:
            api_key, _ = keys.get_api_key(KEY_PROVIDER)

        duration = self._validate_request(
            prompt=prompt,
            duration_input=duration_input,
            images=images,
            audios=audios,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            seed=seed,
        )

        image_urls = [self._upload_if_needed(x, api_key=api_key) for x in images]
        audio_urls = [self._upload_if_needed(x, api_key=api_key) for x in (audios or [])]

        payload = self._build_payload(
            prompt=prompt,
            duration=duration,
            image_urls=image_urls,
            audio_urls=audio_urls,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            seed=seed,
        )

        cost = self.cost_for(duration, resolution)
        if not quiet:
            res_name = resolution or self.default_resolution()
            print(
                f"→ WaveSpeed {self._model_path}: 1 generation × "
                f"${cost:.2f} = ${cost:.2f} ({duration}s @ {res_name}"
                + (f", {aspect_ratio})" if aspect_ratio else ")")
            )

        status, body = _http(
            "POST",
            self._submit_url(),
            api_key=api_key,
            json_body=payload,
        )

        if _looks_like_drift(status, body.decode("utf-8", errors="replace")):
            raise BackendError(SCHEMA_DRIFT)

        if status < 200 or status >= 300:
            raise BackendError(REQUEST_REFUSED)

        data = _parse_json(body, context="Seedance submit")
        request_id = str(data.get("data", {}).get("id", ""))
        if not request_id:
            raise BackendError(REQUEST_REFUSED)

        deadline = time.time() + float(timeout_s)
        while True:
            status, body = _http(
                "GET",
                result_url(request_id),
                api_key=api_key,
            )

            if _looks_like_drift(status, body.decode("utf-8", errors="replace")):
                raise BackendError(SCHEMA_DRIFT)

            if status < 200 or status >= 300:
                raise BackendError(REQUEST_REFUSED)

            data = _parse_json(body, context="Seedance result")
            state = str(data.get("data", {}).get("status", ""))

            if state == TERMINAL_OK:
                outputs = data.get("data", {}).get("outputs", [])
                if not outputs:
                    raise BackendError(REQUEST_REFUSED)
                video_url = str(outputs[0])
                break

            if state == TERMINAL_BAD:
                raise BackendError(REQUEST_REFUSED)

            if time.time() >= deadline:
                raise BackendError(REQUEST_REFUSED)

            time.sleep(float(poll_s))

        status, video_bytes = _http("GET", video_url)
        if status < 200 or status >= 300:
            raise BackendError(REQUEST_REFUSED)

        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        video_path = out_dir / f"{name_prefix or self.name}_{request_id}.mp4"
        video_path.write_bytes(video_bytes)

        return {
            "status": TERMINAL_OK,
            "request_id": request_id,
            "video": str(video_path),
            "cost": cost,
        }

    # -------------------------------------------------------------- #
    # The pipeline's render contract -> generate()                   #
    # -------------------------------------------------------------- #

    def open_render(self, **run) -> None:
        """Resolve the key once and upload every reference sheet once,
        refusing a missing sheet before a single second is rented. The
        money gate has already printed the price and taken consent."""
        self._slug = run["slug"]
        self._out_dir = Path(run.get("out_dir") or f"renders_{self.name}")
        self._out_dir.mkdir(parents=True, exist_ok=True)
        self.stage_dir = self._out_dir / "stage"
        self._timeout = float(run.get("timeout_s") or 900.0)
        self._api_key, source = keys.get_api_key(KEY_PROVIDER)
        print(f"WaveSpeed key loaded from {source}.")
        refs = [str(Path(p).expanduser()) for _, p in (run.get("cast_sheets") or [])]
        if run.get("subject_image"):
            refs.append(str(Path(run["subject_image"]).expanduser()))
        missing = [p for p in refs if not Path(p).exists()]
        if missing:
            raise BackendError(
                f"Reference sheet not found: {missing[0]} — nothing uploaded.")
        self._url_cache = {}
        for p in dict.fromkeys(refs):          # each distinct sheet exactly once
            self._upload_if_needed(p, api_key=self._api_key)
            print(f"Reference uploaded: {Path(p).name}")

    def render_segment(self, **job) -> dict:
        seg_id = job["segment_id"]
        seconds = int(job["duration_input"])
        images = [str(Path(p).expanduser()) for _, p in (job.get("images") or [])]
        audios = []
        if self._audio_supported and job.get("song"):
            clip = self.stage_dir / f"{self._slug}_{seg_id}.wav"
            slice_audio(job["song"], clip, job["audio_start_s"],
                        job["audio_end_s"] - job["audio_start_s"])
            audios = [str(clip)]
        resolution = self.resolution_name_for(job["width"], job["height"])
        print(f"   {seg_id}: {seconds}s @ {resolution} ...", flush=True)
        res = self.generate(
            prompt=wavespeed_ref_tags(to_seedance(job["prompt"], seconds)),
            duration_input=job["duration_input"],
            images=images, audios=audios,
            aspect_ratio=self.nearest_aspect(job["width"], job["height"]),
            resolution=resolution,
            seed=job.get("seed") if self._supports_seed else None,
            out_dir=self._out_dir, name_prefix=seg_id,
            timeout_s=self._timeout, api_key=self._api_key,
        )
        return {
            "video": res.get("video") or "",
            "audio": "",                     # one mp4 with its own sound
            "backend": self.name,
            "request_id": res.get("request_id"),
            "cost": float(res.get("cost") or 0.0),
        }

    def close_render(self) -> None:
        self._url_cache = None


class Seedance2Backend(SeedanceBackend):
    name = "seedance_2"


class Seedance25Backend(SeedanceBackend):
    name = "seedance_2_5"