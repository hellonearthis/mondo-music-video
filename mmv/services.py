"""Live service health, availability and processing activity probe for Mondo."""
from __future__ import annotations

import concurrent.futures
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

_last_probe_time = 0.0
_cached_probe_home = None
_cached_probe_results = None
_CACHE_TTL_SECONDS = 2.5


def check_services(store, active_job=None, force: bool = False) -> dict:
    global _last_probe_time, _cached_probe_home, _cached_probe_results
    now = time.time()

    if (force or _cached_probe_results is None or _cached_probe_home != store.home
            or (now - _last_probe_time > _CACHE_TTL_SECONDS)):
        _cached_probe_results = _probe_raw_services(store)
        _cached_probe_home = store.home
        _last_probe_time = now

    return _evaluate_service_activity(store, _cached_probe_results, active_job)


def _launch_problem(raw) -> str | None:
    """None when raw is a usable JSON argv launch command, otherwise why it is not (empty means unset)."""
    if not raw:
        return "not set"
    try:
        argv = json.loads(raw)
    except (ValueError, TypeError):
        return "is not valid JSON"
    if not isinstance(argv, list) or not argv or any(not isinstance(a, str) or not a for a in argv):
        return "must be a JSON array of non-empty command arguments"
    return None


def _probe_comfy(settings: dict, opener: urllib.request.OpenerDirector) -> dict:
    comfy_url = (settings.get("comfy_url") or "").rstrip("/")
    comfy = {
        "url": comfy_url,
        "available": False,
        "device": "",
        "queue_running": 0,
        "queue_pending": 0,
        "backend": settings.get("backend", "local_h3"),
        "has_launch": _launch_problem(settings.get("comfy_launch")) is None,
        "launch_problem": _launch_problem(settings.get("comfy_launch")),
        "error": None,
    }
    if comfy_url:
        try:
            req = urllib.request.Request(f"{comfy_url}/system_stats", headers={"Accept": "application/json"})
            with opener.open(req, timeout=0.35) as resp:
                if resp.status == 200:
                    comfy["available"] = True
                    try:
                        stats = json.load(resp)
                        devices = stats.get("devices", [])
                        gpu_names = [d.get("name") for d in devices if isinstance(d, dict) and d.get("name")]
                        if gpu_names:
                            comfy["device"] = gpu_names[0]
                    except Exception:
                        pass
                    try:
                        q_req = urllib.request.Request(f"{comfy_url}/queue", headers={"Accept": "application/json"})
                        with opener.open(q_req, timeout=0.25) as q_resp:
                            queue = json.load(q_resp)
                            comfy["queue_running"] = len(queue.get("queue_running", []))
                            comfy["queue_pending"] = len(queue.get("queue_pending", []))
                    except Exception:
                        pass
        except Exception as exc:
            comfy["available"] = False
            comfy["error"] = str(exc)
    return comfy


def _probe_writer(settings: dict, opener: urllib.request.OpenerDirector) -> dict:
    writer_mode = settings.get("writer_mode", "local")
    writer_url = (settings.get("writer_url") or "").rstrip("/")
    writer_model = settings.get("writer_model") or ""
    writer = {
        "mode": writer_mode,
        "url": writer_url,
        "model": writer_model,
        "available": False,
        "slots_processing": 0,
        "has_launch": _launch_problem(settings.get("writer_launch")) is None,
        "launch_problem": _launch_problem(settings.get("writer_launch")),
        "error": None,
    }
    if writer_mode == "api":
        writer["available"] = bool(writer_url and writer_model)
    elif writer_url:
        try:
            req = urllib.request.Request(f"{writer_url}/models", headers={"Accept": "application/json"})
            with opener.open(req, timeout=0.35) as resp:
                if resp.status == 200:
                    writer["available"] = True
                    try:
                        base = writer_url.rsplit("/v1", 1)[0]
                        h_req = urllib.request.Request(f"{base}/health", headers={"Accept": "application/json"})
                        with opener.open(h_req, timeout=0.25) as h_resp:
                            h_data = json.load(h_resp)
                            writer["slots_processing"] = h_data.get("slots_processing", 0)
                    except Exception:
                        pass
        except Exception as exc:
            writer["available"] = False
            writer["error"] = str(exc)
    return writer


def _probe_laya(settings: dict) -> dict:
    laya_dir_str = settings.get("laya_model_dir") or ""
    laya_dir = Path(laya_dir_str).expanduser() if laya_dir_str else None
    laya_device = settings.get("laya_device", "cuda")
    laya_staged = False
    if laya_dir and laya_dir.exists():
        laya_staged = all(
            (laya_dir / name).exists()
            for name in ("model.safetensors", "rl_agent_config.json", "tokenizer", "encoder/config.json")
        )
    return {
        "model_dir": str(laya_dir) if laya_dir else "",
        "device": laya_device,
        "available": laya_staged,
    }


def _probe_vision(settings: dict, opener: urllib.request.OpenerDirector) -> dict:
    vision_url = (settings.get("vision_url") or "").rstrip("/")
    vision_model = settings.get("vision_model") or ""
    vision = {
        "url": vision_url,
        "model": vision_model,
        "available": False,
        "error": None,
    }
    if vision_url:
        try:
            req = urllib.request.Request(f"{vision_url}/models", headers={"Accept": "application/json"})
            with opener.open(req, timeout=0.3) as resp:
                if resp.status == 200:
                    vision["available"] = True
        except Exception as exc:
            vision["available"] = False
            vision["error"] = str(exc)
    return vision


def _probe_vision_quality(settings: dict, opener: urllib.request.OpenerDirector) -> dict:
    """The quality-check vision model: launched on its own port from writer_launch, separate from style harvest."""
    from .vision_check import vision_command
    from .vision_stage import VISION_PORT
    url = f"http://127.0.0.1:{VISION_PORT}"
    quality = {"url": url, "model": "mmv-vision", "available": False, "port_in_use": False,
               "launchable": False, "error": None}
    try:
        vision_command(settings.get("writer_launch") or "", VISION_PORT)
        quality["launchable"] = True
    except ValueError as exc:
        quality["error"] = str(exc)
    try:
        with opener.open(urllib.request.Request(f"{url}/health"), timeout=0.3) as resp:
            quality["port_in_use"] = resp.status == 200
        if quality["port_in_use"]:
            with opener.open(urllib.request.Request(f"{url}/v1/models"), timeout=0.3) as resp:
                quality["available"] = any(isinstance(m, dict) and m.get("id") == quality["model"]
                                           for m in json.load(resp).get("data") or [])
    except Exception:
        pass
    return quality


def _probe_raw_services(store) -> dict:
    settings = store.settings()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    writer_url = (settings.get("writer_url") or "").rstrip("/")
    vision_url = (settings.get("vision_url") or "").rstrip("/")
    writer_mode = settings.get("writer_mode", "local")
    shared_vision = bool(vision_url and vision_url == writer_url and writer_mode == "local")

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        f_quality = executor.submit(_probe_vision_quality, settings, opener)
        f_comfy = executor.submit(_probe_comfy, settings, opener)
        f_writer = executor.submit(_probe_writer, settings, opener)
        f_vision = None if shared_vision else executor.submit(_probe_vision, settings, opener)

        comfy = f_comfy.result()
        writer = f_writer.result()
        if shared_vision:
            vision = {
                "url": vision_url,
                "model": settings.get("vision_model") or "",
                "available": writer["available"],
                "error": writer["error"],
            }
        else:
            vision = f_vision.result()

    laya = _probe_laya(settings)
    return {
        "comfy": comfy,
        "writer": writer,
        "laya": laya,
        "vision": vision,
        "vision_quality": f_quality.result(),
    }


def _evaluate_service_activity(store, probed: dict, active_job=None) -> dict:
    active_message = (active_job.get("message") or "") if active_job else ""
    active_state = (active_job.get("state") or "") if active_job else ""
    is_job_running = active_state in ("running", "cancelling")
    active_lower = active_message.lower()

    # ComfyUI
    comfy_raw = probed.get("comfy", {})
    comfy_avail = comfy_raw.get("available", False)
    if not comfy_avail:
        comfy_activity = "offline"
        comfy_detail = f"Offline at {comfy_raw.get('url') or 'unconfigured'}" + (
            " · Mondo starts it when needed" if comfy_raw.get("has_launch") else "")
    else:
        q_run = comfy_raw.get("queue_running", 0)
        is_rendering = is_job_running and any(w in active_lower for w in ("render", "opening renderer", "comfy"))
        if q_run > 0 or is_rendering:
            comfy_activity = "processing"
            comfy_detail = f"Actively rendering ({q_run} in queue)" if q_run else "Actively rendering"
        else:
            comfy_activity = "sleeping"
            dev_str = comfy_raw.get("device") or "GPU"
            comfy_detail = f"Sleeping (ready) · {dev_str}"

    comfy_status = {
        "id": "comfy",
        "name": "ComfyUI",
        "role": "Video Renderer",
        "url": comfy_raw.get("url", ""),
        "available": comfy_avail,
        "has_launch": bool(comfy_raw.get("has_launch")),
        "launch_problem": comfy_raw.get("launch_problem"),
        "activity": comfy_activity,
        "detail": comfy_detail,
        "device": comfy_raw.get("device", ""),
        "backend": comfy_raw.get("backend", "local_h3"),
    }

    # llama.cpp / Writer
    writer_raw = probed.get("writer", {})
    writer_avail = writer_raw.get("available", False)
    writer_mode = writer_raw.get("mode", "local")
    writer_model = writer_raw.get("model", "")
    if writer_mode == "api":
        if is_job_running and any(w in active_lower for w in ("writer", "writing", "ident prompt")):
            writer_activity = "processing"
            writer_detail = f"Actively generating prompts ({writer_model})"
        else:
            # An API profile is only configured; it is never probed here, so it is not announced as online.
            writer_activity = "configured" if writer_avail else "offline"
            writer_detail = f"External API configured, not probed ({writer_model})" if writer_avail else "API key or model unconfigured"
    else:
        if not writer_avail:
            writer_activity = "offline"
            writer_detail = f"Offline at {writer_raw.get('url') or 'unconfigured'}" + (
                " · Mondo starts it when needed" if writer_raw.get("has_launch") else "")
        else:
            is_writing = is_job_running and any(w in active_lower for w in ("writer", "writing", "ident prompt"))
            if writer_raw.get("slots_processing", 0) > 0 or is_writing:
                writer_activity = "processing"
                writer_detail = f"Actively generating prompts ({writer_model or 'local LLM'})"
            else:
                writer_activity = "sleeping"
                writer_detail = f"Sleeping (idle) · {writer_model or 'llama-server'}"

    writer_status = {
        "id": "writer",
        "name": "llama.cpp",
        "role": "Prompt Writer",
        "url": writer_raw.get("url", ""),
        "available": writer_avail,
        "has_launch": bool(writer_raw.get("has_launch")),
        "launch_problem": writer_raw.get("launch_problem"),
        "activity": writer_activity,
        "detail": writer_detail,
        "model": writer_model,
        "mode": writer_mode,
    }

    # Laya
    laya_raw = probed.get("laya", {})
    laya_avail = laya_raw.get("available", False)
    laya_dev = laya_raw.get("device", "cuda")
    if not laya_avail:
        laya_activity = "missing"
        laya_detail = "Model files not staged (download needed)"
    else:
        if is_job_running and any(w in active_lower for w in ("laya", "reviewing")):
            laya_activity = "processing"
            laya_detail = f"Actively reviewing prompt passage ({laya_dev})"
        else:
            laya_activity = "sleeping"
            laya_detail = f"Sleeping (ready) · device: {laya_dev}"

    laya_status = {
        "id": "laya",
        "name": "Laya",
        "role": "Prompt Reviewer",
        "available": laya_avail,
        "activity": laya_activity,
        "detail": laya_detail,
        "device": laya_dev,
        "model_dir": laya_raw.get("model_dir", ""),
    }

    # Vision
    vision_raw = probed.get("vision", {})
    vision_avail = vision_raw.get("available", False)
    vision_url = vision_raw.get("url", "")
    vision_model = vision_raw.get("model", "")
    if not vision_avail:
        vision_activity = "offline"
        vision_detail = f"Offline at {vision_url}" if vision_url else "Not configured"
    else:
        if is_job_running and "harvest" in active_lower:
            vision_activity = "processing"
            vision_detail = "Actively harvesting visual style"
        else:
            vision_activity = "sleeping"
            vision_detail = f"Sleeping (ready) · {vision_model or 'multimodal'}"

    vision_status = {
        "id": "vision",
        "name": "Vision",
        "role": "Style Harvester",
        "url": vision_url,
        "available": vision_avail,
        "activity": vision_activity,
        "detail": vision_detail,
        "model": vision_model,
    }

    # Quality vision runs on its own port from the writer launch; it is not the style-harvest endpoint above.
    quality_raw = probed.get("vision_quality", {})
    quality_avail = quality_raw.get("available", False)
    if quality_avail:
        quality_activity = "processing" if is_job_running and "vision check" in active_lower else "sleeping"
        quality_detail = f"Running and ready at {quality_raw.get('url')}"
    elif quality_raw.get("port_in_use"):
        quality_activity, quality_detail = "offline", f"{quality_raw.get('url')} is used by another service"
    elif quality_raw.get("launchable"):
        quality_activity, quality_detail = "offline", "Offline · Mondo starts it when the vision check runs"
    else:
        quality_activity = "missing"
        quality_detail = f"Cannot be launched: {quality_raw.get('error') or 'writer_launch not set'}"

    quality_status = {
        "id": "vision_quality",
        "name": "Vision",
        "role": "Quality Check",
        "url": quality_raw.get("url", ""),
        "available": quality_avail,
        "has_launch": bool(quality_raw.get("launchable")),
        "port_in_use": bool(quality_raw.get("port_in_use")) and not quality_avail,
        "error": quality_raw.get("error"),
        "activity": quality_activity,
        "detail": quality_detail,
        "model": quality_raw.get("model", ""),
    }

    return {
        "comfy": comfy_status,
        "writer": writer_status,
        "laya": laya_status,
        "vision": vision_status,
        "vision_quality": quality_status,
    }


def check_required_services(store, request: dict, resume: bool = False) -> list[str]:
    """Verify that all engines required for the requested production are available.

    Returns a list of human-readable error messages explaining which engine is offline
    and how to start or configure it. Returns empty list if all required engines are ready.
    """
    services = check_services(store, force=True)
    kind = request.get("kind", "video")
    backend = request.get("backend", "local_h3")
    errors = []

    if kind == "harvest":
        vision = services.get("vision", {})
        if not vision.get("available"):
            endpoint = vision.get("url") or "unconfigured"
            errors.append(
                f"Vision engine is offline or unreachable ({endpoint}). "
                "Multimodal style harvesting requires a running vision model or API configuration in Settings."
            )
        return errors

    # Video and ident need Prompt Writer (unless resuming)
    if not resume:
        writer = services.get("writer", {})
        if not writer.get("available") and not writer.get("has_launch"):
            mode = writer.get("mode", "local")
            endpoint = writer.get("url") or "unconfigured"
            if mode == "local":
                errors.append(
                    f"Prompt Writer (llama.cpp) is offline at {endpoint} and cannot be started by Mondo: "
                    f"writer_launch {writer.get('launch_problem') or 'is not usable'}. "
                    "Set writer_launch in Settings to a JSON array that starts llama-server, or start the server yourself."
                )
            else:
                errors.append(
                    f"Prompt Writer API is offline or unconfigured at {endpoint}. "
                    "Production cannot generate passage prompts without it. "
                    "Please configure a valid API key and model in Settings."
                )

    # Video needs Laya prompt reviewer (unless resuming)
    if kind == "video" and not resume:
        laya = services.get("laya", {})
        if not laya.get("available"):
            errors.append(
                "Laya prompt reviewer models are missing or incomplete. "
                "Stage the required model files (model.safetensors, rl_agent_config.json, tokenizer, encoder/config.json) "
                "or configure laya_model_dir in Settings before starting production."
            )

    # ComfyUI is needed for local_h3 backend
    if backend == "local_h3":
        comfy = services.get("comfy", {})
        if not comfy.get("available") and not comfy.get("has_launch"):
            endpoint = comfy.get("url") or "unconfigured"
            errors.append(
                f"ComfyUI video renderer is offline at {endpoint} and cannot be started by Mondo: "
                f"comfy_launch {comfy.get('launch_problem') or 'is not usable'}. "
                "Set comfy_launch in Settings to a JSON array that starts ComfyUI, or start it yourself."
            )

    # Quality vision is launched by Mondo on its own port from writer_launch; style harvest uses another endpoint.
    if kind == "video" and request.get("vision_quality_check"):
        quality = services.get("vision_quality", {})
        if not quality.get("available") and not quality.get("has_launch"):
            errors.append(
                f"Vision quality check cannot start its model: {quality.get('error') or 'writer_launch is not set'}. "
                "Fix writer_launch in Settings (local -m model with one matching mmproj*.gguf beside it) or turn the check off."
            )
        elif quality.get("port_in_use"):
            errors.append(
                f"Vision quality check needs {quality.get('url')} but another service is using it. "
                "Close that service or turn the check off; Mondo never stops processes it did not start."
            )

    return errors

