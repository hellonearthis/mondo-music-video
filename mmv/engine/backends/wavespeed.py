"""
🪿 MAXIMUM GOOSE LABORATORY 🪿
backends.wavespeed — MiniMax H3 through WaveSpeed's hosted API.

THE LOCKED SCHEMA (verified from the operator's catalog recon, 2026-08-19,
model page https://wavespeed.ai/models/minimax/h3/reference-to-video):

  prompt            string   REQUIRED
  reference_images  string[] 0..9 URLs   }  at least one image or
  reference_videos  string[] 0..3 URLs   }  video is required
  reference_audios  string[] 0..3 URLs      audio cannot be provided alone
  aspect_ratio      enum     21:9 | 16:9 | 4:3 | 1:1 | 3:4 | 9:16  (default 16:9)
  resolution        enum     768p | 2k                             (default 768p)
  duration          integer  4..15 seconds                         (default 5)

  base price: $0.70 per generation (catalog figure; printed before every
  submit — the operator fires paid renders, never this module on its own).

Every outbound payload is validated against SCHEMA before it leaves the
building (assert_request). If the server rejects a request with anything
that smells like a field/validation complaint, the error is raised with a
SCHEMA DRIFT banner so catalog changes surface loudly instead of as a
mystery 400 three hundred videos from now.

THE API SHAPE (from WaveSpeed's public docs; the one part no sandbox test
can verify, so every path is env-overridable and mgl_wavespeed_probe.py
exists to confirm against the live service before any money moves):

  submit   POST {WAVESPEED_BASE_URL}/{model_path}
           Authorization: Bearer <key>, JSON body   -> data.id
  poll     GET  {WAVESPEED_BASE_URL}/predictions/{id}/result
           -> data.status in created|processing|completed|failed,
              data.outputs = [urls] on completed, data.error on failed
  upload   POST {WAVESPEED_BASE_URL}/{WAVESPEED_UPLOAD_PATH}
           multipart field "file"                   -> data.download_url

  WAVESPEED_BASE_URL     default https://api.wavespeed.ai/api/v3
  WAVESPEED_UPLOAD_PATH  default media/upload/binary
  WAVESPEED_RESULT_PATH  default predictions/{id}/result

References are URLs on the wire. resolve_refs() passes http(s) URLs
through untouched and uploads local files (cast sheets, audio slices)
through the upload endpoint first. Combination rules are enforced BEFORE
any upload happens, so an invalid wiring costs nothing.

Credentials come from backends.keys (env -> keyring -> encrypted file) and
never appear in logs, errors, or argv: everything user-visible passes
through keys.redact().
"""

from __future__ import annotations

import json
import re
import mimetypes
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from . import keys
from ..comfy import slice_audio
from .base import Backend, BackendError, TAG_SYNTAX_MINIMAX_H3

PROVIDER = "wavespeed"
MODEL_PATH = "minimax/h3/reference-to-video"

DEFAULT_BASE_URL = "https://api.wavespeed.ai/api/v3"
DEFAULT_UPLOAD_PATH = "media/upload/binary"
DEFAULT_RESULT_PATH = "predictions/{id}/result"

ASPECT_RATIOS = ("21:9", "16:9", "4:3", "1:1", "3:4", "9:16")
RESOLUTIONS = ("768p", "2k")
DURATION_MIN, DURATION_MAX = 4, 15
MAX_IMAGES, MAX_VIDEOS, MAX_AUDIOS = 9, 3, 3

# WaveSpeed bills H3 by the second of video, per resolution (catalog page,
# read 2026-10-14): $0.10/s at 768p, $0.14/s at 2k. The first FREE_IMAGES
# reference images ride free; each one past that is EXTRA_IMAGE_PRICE.
# COST_PER_GENERATION is the CEILING of one generation (the longest clip at
# the dearest resolution with every image slot filled), for any gate that
# cannot know the clip's length.
PRICE_PER_SECOND = {"768p": 0.10, "2k": 0.14}
FREE_IMAGES, EXTRA_IMAGE_PRICE = 5, 0.05
COST_PER_GENERATION = round(DURATION_MAX * max(PRICE_PER_SECOND.values())
                            + (MAX_IMAGES - FREE_IMAGES) * EXTRA_IMAGE_PRICE, 2)

# v0.13.0 (CHUNK 5a). NOMINAL short side per named resolution: the number
# plan.json records as width/height so `mondo render` can read the name back
# out of the plan. WaveSpeed decides the real pixel grid; only the NAME is
# ever sent. "2k" is taken as 1440 short side (QHD usage); if the catalog
# says otherwise, change this one line — nothing downstream is measured
# against it, assembly works from the clips that actually arrive.
RESOLUTION_SHORT_SIDE = {"768p": 768, "2k": 1440}

# Catalog rule, also enforced in resolve_refs(): a request needs at least one
# reference image or video. Declared so `mondo render` can refuse a plan with
# empty reference slots before any upload or charge.
MIN_REFERENCE_IMAGES = 1

SCHEMA = {
    "prompt": {"type": str, "required": True},
    "reference_images": {"type": list, "max_items": MAX_IMAGES},
    "reference_videos": {"type": list, "max_items": MAX_VIDEOS},
    "reference_audios": {"type": list, "max_items": MAX_AUDIOS},
    "aspect_ratio": {"type": str, "enum": ASPECT_RATIOS},
    "resolution": {"type": str, "enum": RESOLUTIONS},
    "duration": {"type": int, "min": DURATION_MIN, "max": DURATION_MAX},
}

TERMINAL_OK = "completed"
TERMINAL_BAD = "failed"
_DRIFT_HINTS = ("field", "unknown", "invalid", "validation", "unexpected",
                "schema", "parameter", "enum")


def base_url() -> str:
    return os.environ.get("WAVESPEED_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def upload_url() -> str:
    path = os.environ.get("WAVESPEED_UPLOAD_PATH", DEFAULT_UPLOAD_PATH)
    return f"{base_url()}/{path.strip('/')}"


def wavespeed_ref_tags(text: str) -> str:
    """The WaveSpeed platform's reference grammar: uploads are bound in the
    prompt by type and order as "@Image 1" / "@Video 1" (the house writes
    <Picture 1> / <Video 1>). A property of this transport, not of any one
    model: a Seedance (or H3) render through another provider would use that
    provider's grammar instead."""
    text = re.sub(r"<Picture (\d+)>", r"@Image \1", text)
    return re.sub(r"<Video (\d+)>", r"@Video \1", text)


def result_url(request_id: str) -> str:
    tmpl = os.environ.get("WAVESPEED_RESULT_PATH", DEFAULT_RESULT_PATH)
    return f"{base_url()}/{tmpl.strip('/').format(id=request_id)}"


def submit_url() -> str:
    return f"{base_url()}/{MODEL_PATH}"


class WaveSpeedError(BackendError):
    """A remote-side refusal or failure, already redacted."""

    def __init__(self, message: str, *, status: int | None = None,
                 body: str = ""):
        self.status = status
        self.body = keys.redact(body or "")
        super().__init__(keys.redact(message))


def assert_request(payload: dict) -> None:
    """Validate a payload against the LOCKED schema. Loud on any deviation,
    including keys the catalog never defined — if this fires on a payload
    the code built, the catalog and this module have drifted apart."""
    unknown = sorted(set(payload) - set(SCHEMA))
    if unknown:
        raise WaveSpeedError(
            f"Payload carries field(s) not in the locked WaveSpeed schema: "
            f"{', '.join(unknown)}. If the catalog gained fields, update "
            f"SCHEMA in backends/wavespeed.py and re-verify with "
            f"mgl_wavespeed_probe.py. (SCHEMA DRIFT guard)"
        )
    for field, spec in SCHEMA.items():
        if spec.get("required") and field not in payload:
            raise WaveSpeedError(f"Required field missing: {field}")
        if field not in payload:
            continue
        value = payload[field]
        if spec["type"] is int:
            if isinstance(value, bool) or not isinstance(value, int):
                raise WaveSpeedError(f"{field} must be an integer, "
                                     f"got {value!r}")
        elif not isinstance(value, spec["type"]):
            raise WaveSpeedError(
                f"{field} must be {spec['type'].__name__}, got {value!r}")
        if "enum" in spec and value not in spec["enum"]:
            raise WaveSpeedError(
                f"{field} must be one of {', '.join(spec['enum'])}; "
                f"got {value!r}")
        if "max_items" in spec:
            if len(value) > spec["max_items"]:
                raise WaveSpeedError(
                    f"{field} accepts at most {spec['max_items']} item(s); "
                    f"got {len(value)}")
            for item in value:
                if not isinstance(item, str) or not item.startswith(
                        ("http://", "https://")):
                    raise WaveSpeedError(
                        f"{field} entries must be http(s) URLs; got {item!r}")
        if "min" in spec and value < spec["min"]:
            raise WaveSpeedError(f"{field} minimum is {spec['min']}; "
                                 f"got {value}")
        if "max" in spec and value > spec["max"]:
            raise WaveSpeedError(f"{field} maximum is {spec['max']}; "
                                 f"got {value}")

    if not payload.get("prompt", "").strip():
        raise WaveSpeedError("prompt must be a non-empty string")
    n_img = len(payload.get("reference_images", []))
    n_vid = len(payload.get("reference_videos", []))
    n_aud = len(payload.get("reference_audios", []))
    if n_img + n_vid == 0:
        raise WaveSpeedError(
            "At least one reference image or reference video is required "
            "(catalog rule). Audio alone cannot carry a generation.")
    if n_aud and not (n_img or n_vid):
        raise WaveSpeedError("Audio cannot be provided alone (catalog rule).")


def _looks_like_drift(status: int, body: str) -> bool:
    if status not in (400, 422):
        return False
    lowered = body.lower()
    return any(h in lowered for h in _DRIFT_HINTS)


def _http(method: str, url: str, *, api_key: str | None = None,
          json_body: dict | None = None, raw_body: bytes | None = None,
          content_type: str | None = None,
          timeout: float = 60.0) -> tuple[int, bytes]:
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode()
        headers["Content-Type"] = "application/json"
    elif raw_body is not None:
        data = raw_body
        headers["Content-Type"] = content_type or "application/octet-stream"
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except urllib.error.URLError as e:
        raise WaveSpeedError(
            f"Could not reach WaveSpeed at {url}: {e.reason}. "
            f"Network down, or WAVESPEED_BASE_URL misconfigured.") from None


def _parse_json(body: bytes, *, context: str) -> dict:
    try:
        return json.loads(body.decode() or "{}")
    except Exception:
        raise WaveSpeedError(
            f"{context}: response was not JSON: "
            f"{body[:300].decode(errors='replace')!r}") from None


def upload_file(path: str | Path, *, api_key: str,
                timeout: float = 120.0) -> str:
    """Push one local file through the upload endpoint, return its URL."""
    p = Path(path).expanduser()
    if not p.exists():
        raise WaveSpeedError(f"Reference file not found: {p}")
    boundary = f"mgl{uuid.uuid4().hex}"
    mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    head = (f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; '
            f'filename="{p.name}"\r\n'
            f"Content-Type: {mime}\r\n\r\n").encode()
    tail = f"\r\n--{boundary}--\r\n".encode()
    status, body = _http(
        "POST", upload_url(), api_key=api_key,
        raw_body=head + p.read_bytes() + tail,
        content_type=f"multipart/form-data; boundary={boundary}",
        timeout=timeout)
    if status != 200:
        raise WaveSpeedError(
            f"Upload of {p.name} refused (HTTP {status}). "
            f"{body[:300].decode(errors='replace')}",
            status=status, body=body.decode(errors="replace"))
    data = _parse_json(body, context=f"upload {p.name}").get("data") or {}
    url = data.get("download_url") or data.get("url")
    if not url:
        raise WaveSpeedError(
            f"Upload of {p.name} returned no download_url; "
            f"body: {body[:300].decode(errors='replace')}")
    return url


def probe_auth(*, api_key: str | None = None) -> tuple[bool, str]:
    """Zero-cost credential check: an authenticated GET against the result
    endpoint with a placeholder id. 401/403 means the key was rejected;
    404 (or a JSON not-found) means the key was accepted and the job simply
    does not exist — which is the point. Anything else is reported raw."""
    if api_key is None:
        api_key, source = keys.get_api_key(PROVIDER)
    status, body = _http("GET", result_url("mgl-auth-probe"),
                         api_key=api_key, timeout=30.0)
    text = body[:300].decode(errors="replace")
    if status in (401, 403):
        return False, (f"Key REJECTED (HTTP {status}). Check the stored key "
                       f"with mgl_keys.py show {PROVIDER}.")
    if status == 404 or (status == 200 and "not" in text.lower()):
        return True, f"Key accepted (HTTP {status} on a probe id, as expected)."
    return True, (f"Endpoint answered HTTP {status}: {keys.redact(text)} — "
                  f"key not rejected; verify paths with the docs if this "
                  f"looks wrong.")


class WaveSpeedH3Backend(Backend):
    """MiniMax H3, same model as the local install, rented by the second.

    Same 24 fps, same <Picture N> prompt grammar, same reference ceilings —
    but durations are whole seconds 4..15 and resolution is a fixed menu,
    which is exactly what the capability contract exists to express.
    """

    name = PROVIDER

    # Upload memo for one render run: a cast sheet cited by fourteen segments
    # is uploaded once, not fourteen times. None outside open_render/
    # close_render, so the probe and the test-suite see no caching at all.
    _url_cache: dict | None = None

    def capabilities(self) -> dict:
        return {
            "backend": PROVIDER,
            "display_name": "WaveSpeed MiniMax H3 (remote API)",
            "frame_lattice": {
                "mode": "seconds",
                "fps": 24,
                "allowed_seconds": list(range(DURATION_MIN, DURATION_MAX + 1)),
            },
            "max_reference_images": MAX_IMAGES,
            "max_reference_videos": MAX_VIDEOS,
            "max_reference_audios": MAX_AUDIOS,
            "audio_conditioning": {
                "supported": True,
                "how": "reference_audio_urls",
            },
            "prompt_tag_syntax": TAG_SYNTAX_MINIMAX_H3,
            "max_prompt_chars": None,
            "resolution_mode": "fixed_list",
            "resolutions": list(RESOLUTIONS),
            "resolution_sizes": dict(RESOLUTION_SHORT_SIDE),
            "min_reference_images": MIN_REFERENCE_IMAGES,
            "supports_seed": False,
            "steps": None,
            "cost_per_generation": COST_PER_GENERATION,
            "price_per_second": dict(PRICE_PER_SECOND),
        }

    def cost_for(self, seconds: float, resolution: str | None = None,
                 images: int = 0) -> float:
        """Billed whole seconds (never under the shortest clip) at the
        resolution's rate, plus every reference image past the free ones."""
        rate = PRICE_PER_SECOND.get(str(resolution or RESOLUTIONS[0]))
        if rate is None:
            return COST_PER_GENERATION
        billed = max(int(-(-float(seconds) // 1)), DURATION_MIN)
        extra = max(0, int(images) - FREE_IMAGES) * EXTRA_IMAGE_PRICE
        return round(rate * billed + extra, 2)

    # -------------------------------------------------------------- #
    # Plan-time facts read back out of the plan (CHUNK 5a)           #
    # -------------------------------------------------------------- #

    def nearest_aspect(self, width: int, height: int) -> str:
        """plan.json records width/height, not the aspect string; the
        catalog wants one of ASPECT_RATIOS. Pick the closest ratio — for a
        plan this backend made the match is exact."""
        ratio = float(width) / float(height)

        def _r(a: str) -> float:
            w, h = (int(x) for x in a.split(":"))
            return w / h

        return min(ASPECT_RATIOS, key=lambda a: abs(_r(a) - ratio))

    # -------------------------------------------------------------- #
    # Request shaping                                                #
    # -------------------------------------------------------------- #

    def aspect_ratio_for(self, aspect: str) -> str:
        a = str(aspect).strip().replace(" ", "")
        if a not in ASPECT_RATIOS:
            raise WaveSpeedError(
                f"Aspect {aspect!r} is not offered by WaveSpeed H3; "
                f"choose one of {', '.join(ASPECT_RATIOS)}.")
        return a

    def resolve_refs(self, images=(), videos=(), audios=(), *,
                     api_key: str) -> tuple[list[str], list[str], list[str]]:
        """Local paths become uploaded URLs; URLs pass through. All
        combination rules are enforced BEFORE any upload spends time."""
        def _prevalidate(name, seq, ceiling):
            seq = list(seq or ())
            if len(seq) > ceiling:
                raise WaveSpeedError(
                    f"{name}: {len(seq)} supplied, ceiling is {ceiling}.")
            return seq

        images = _prevalidate("reference images", images, MAX_IMAGES)
        videos = _prevalidate("reference videos", videos, MAX_VIDEOS)
        audios = _prevalidate("reference audios", audios, MAX_AUDIOS)
        if not images and not videos:
            raise WaveSpeedError(
                "At least one reference image or video is required "
                "(catalog rule) — nothing was uploaded.")
        if audios and not (images or videos):
            raise WaveSpeedError("Audio cannot be provided alone "
                                 "(catalog rule) — nothing was uploaded.")

        cache = self._url_cache   # a dict only between open_render/close_render

        def _to_url(entry) -> str:
            s = str(entry)
            if s.startswith(("http://", "https://")):
                return s
            if cache is not None and s in cache:
                return cache[s]
            url = upload_file(s, api_key=api_key)
            if cache is not None:
                cache[s] = url
            return url

        return ([_to_url(x) for x in images],
                [_to_url(x) for x in videos],
                [_to_url(x) for x in audios])

    def build_request(self, *, prompt: str, duration_input: float,
                      aspect: str = "16:9", resolution: str = "768p",
                      image_urls=(), video_urls=(), audio_urls=()) -> dict:
        seconds = int(duration_input)
        if seconds != duration_input:
            raise WaveSpeedError(
                f"duration_input {duration_input!r} is not a whole second; "
                f"plan against this backend so durations land on its "
                f"lattice.")
        payload = {
            "prompt": prompt,
            "aspect_ratio": self.aspect_ratio_for(aspect),
            "resolution": str(resolution),
            "duration": seconds,
        }
        if image_urls:
            payload["reference_images"] = list(image_urls)
        if video_urls:
            payload["reference_videos"] = list(video_urls)
        if audio_urls:
            payload["reference_audios"] = list(audio_urls)
        assert_request(payload)
        return payload

    # -------------------------------------------------------------- #
    # The one generation call                                        #
    # -------------------------------------------------------------- #

    def generate(self, *, prompt: str, duration_input: float,
                 aspect: str = "16:9", resolution: str = "768p",
                 images=(), videos=(), audios=(),
                 out_dir: str | Path | None = None,
                 name_prefix: str = "wavespeed",
                 timeout_s: float = 900.0, poll_s: float = 3.0,
                 api_key: str | None = None, quiet: bool = False) -> dict:
        """Submit one generation, poll to a terminal state, download the
        video when out_dir is given. Prints the cost line BEFORE submitting;
        this module never fires money on its own initiative — a human
        called it."""
        if api_key is None:
            api_key, source = keys.get_api_key(PROVIDER)
            if not quiet:
                print(f"WaveSpeed key loaded from {source}.")

        image_urls, video_urls, audio_urls = self.resolve_refs(
            images, videos, audios, api_key=api_key)
        payload = self.build_request(
            prompt=prompt, duration_input=duration_input, aspect=aspect,
            resolution=resolution, image_urls=image_urls,
            video_urls=video_urls, audio_urls=audio_urls)

        cost = self.cost_for(payload["duration"], payload["resolution"], len(image_urls))
        if not quiet:
            print(f"→ WaveSpeed {MODEL_PATH}: 1 generation × "
                  f"${cost:.2f} = ${cost:.2f} "
                  f"({payload['duration']}s @ {payload['resolution']}, "
                  f"{payload['aspect_ratio']})")

        status, body = _http("POST", submit_url(), api_key=api_key,
                             json_body=payload, timeout=60.0)
        text = body.decode(errors="replace")
        if status in (401, 403):
            raise WaveSpeedError(
                f"WaveSpeed rejected the API key (HTTP {status}). "
                f"Run mgl_wavespeed_probe.py --auth to check credentials.",
                status=status, body=text)
        if _looks_like_drift(status, text):
            raise WaveSpeedError(
                f"POSSIBLE SCHEMA DRIFT — WaveSpeed refused a payload that "
                f"passes the locked schema (HTTP {status}). Server said: "
                f"{text[:400]}\nCompare the model page against SCHEMA in "
                f"backends/wavespeed.py before rendering anything else.",
                status=status, body=text)
        if status != 200:
            raise WaveSpeedError(
                f"Submit failed (HTTP {status}): {text[:400]}",
                status=status, body=text)

        data = _parse_json(body, context="submit").get("data") or {}
        request_id = data.get("id")
        if not request_id:
            raise WaveSpeedError(
                f"Submit returned no request id; body: {text[:300]}")
        if not quiet:
            print(f"   request {request_id} accepted; polling…")

        deadline = time.monotonic() + timeout_s
        outputs: list[str] = []
        while True:
            if time.monotonic() > deadline:
                raise WaveSpeedError(
                    f"Timed out after {timeout_s:.0f}s waiting on request "
                    f"{request_id}; it may still complete — check the "
                    f"WaveSpeed dashboard before resubmitting.")
            status, body = _http("GET", result_url(request_id),
                                 api_key=api_key, timeout=30.0)
            if status != 200:
                raise WaveSpeedError(
                    f"Poll failed (HTTP {status}): "
                    f"{body[:300].decode(errors='replace')}",
                    status=status, body=body.decode(errors="replace"))
            data = _parse_json(body, context="poll").get("data") or {}
            state = (data.get("status") or "").lower()
            if state == TERMINAL_OK:
                outputs = list(data.get("outputs") or [])
                break
            if state == TERMINAL_BAD:
                raise WaveSpeedError(
                    f"Request {request_id} FAILED on WaveSpeed's side: "
                    f"{data.get('error') or 'no error text supplied'}")
            time.sleep(poll_s)

        if not outputs:
            raise WaveSpeedError(
                f"Request {request_id} completed but returned no outputs.")

        video_path = None
        if out_dir is not None:
            out_dir = Path(out_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            video_path = out_dir / f"{name_prefix}_{request_id}.mp4"
            v_status, v_body = _http("GET", outputs[0], timeout=300.0)
            if v_status != 200:
                raise WaveSpeedError(
                    f"Output download failed (HTTP {v_status}) from "
                    f"{outputs[0]}")
            video_path.write_bytes(v_body)
            if not quiet:
                print(f"   video saved: {video_path}")

        return {
            "backend": PROVIDER,
            "request_id": request_id,
            "status": TERMINAL_OK,
            "outputs": outputs,
            "video": str(video_path) if video_path else None,
            "cost": cost,
        }

    # -------------------------------------------------------------- #
    # The pipeline's render contract (CHUNK 5a) -> generate()        #
    # -------------------------------------------------------------- #

    def open_render(self, **run) -> None:
        """Resolve the key once, upload every reference sheet once, and
        refuse anything refusable before a single second is rented.
        mondo_master's pre-flight has already printed the total and taken
        consent by the time this runs; this only checks and prepares."""
        self._slug = run["slug"]
        self._out_dir = Path(run.get("out_dir") or f"renders_{PROVIDER}")
        self._out_dir.mkdir(parents=True, exist_ok=True)
        self.stage_dir = self._out_dir / "stage"
        self.stage_dir.mkdir(parents=True, exist_ok=True)
        self._timeout = float(run.get("timeout_s") or 900.0)

        self._api_key, source = keys.get_api_key(PROVIDER)
        print(f"WaveSpeed key loaded from {source}.")

        refs = [str(Path(p).expanduser()) for _, p in (run.get("cast_sheets") or [])]
        if run.get("subject_image"):
            refs.append(str(Path(run["subject_image"]).expanduser()))
        missing = [p for p in refs if not Path(p).exists()]
        if missing:
            raise WaveSpeedError(
                f"Reference sheet not found: {missing[0]} — nothing uploaded.")

        self._url_cache = {}
        for p in dict.fromkeys(refs):          # each distinct sheet exactly once
            self._url_cache[p] = upload_file(p, api_key=self._api_key)
            print(f"Reference uploaded: {Path(p).name}")

    def render_segment(self, **job) -> dict:
        seg_id = job["segment_id"]
        clip = self.stage_dir / f"{self._slug}_{seg_id}.wav"
        slice_audio(job["song"], clip, job["audio_start_s"],
                    job["audio_end_s"] - job["audio_start_s"])

        images = [str(Path(p).expanduser()) for _, p in (job.get("images") or [])]
        print(f"   {seg_id}: {job['gen_frames']} frames "
              f"({int(job['duration_input'])}s) ...", flush=True)
        res = self.generate(
            prompt=job["prompt"],
            duration_input=job["duration_input"],
            aspect=self.nearest_aspect(job["width"], job["height"]),
            resolution=self.resolution_name_for(job["width"], job["height"]),
            images=images, audios=[str(clip)],
            out_dir=self._out_dir, name_prefix=seg_id,
            timeout_s=self._timeout, api_key=self._api_key,
        )
        return {
            "video": res.get("video") or "",
            "audio": "",                     # H3 returns one mp4; no separate stem
            "backend": PROVIDER,
            "request_id": res.get("request_id"),
            "cost": float(res.get("cost") or 0.0),
        }

    def close_render(self) -> None:
        self._url_cache = None
