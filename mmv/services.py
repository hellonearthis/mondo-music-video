"""Live service health, availability and processing activity probe for Mondo."""
from __future__ import annotations

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


def _probe_raw_services(store) -> dict:
    settings = store.settings()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    results = {}

    # 1. ComfyUI
    comfy_url = (settings.get("comfy_url") or "").rstrip("/")
    comfy = {
        "url": comfy_url,
        "available": False,
        "device": "",
        "queue_running": 0,
        "queue_pending": 0,
        "backend": settings.get("backend", "local_h3"),
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
    results["comfy"] = comfy

    # 2. llama.cpp / Writer
    writer_mode = settings.get("writer_mode", "local")
    writer_url = (settings.get("writer_url") or "").rstrip("/")
    writer_model = settings.get("writer_model") or ""
    writer = {
        "mode": writer_mode,
        "url": writer_url,
        "model": writer_model,
        "available": False,
        "slots_processing": 0,
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
    results["writer"] = writer

    # 3. Laya Semantic Validator
    laya_dir_str = settings.get("laya_model_dir") or ""
    laya_dir = Path(laya_dir_str).expanduser() if laya_dir_str else None
    laya_device = settings.get("laya_device", "cuda")
    laya_staged = False
    if laya_dir and laya_dir.exists():
        laya_staged = all(
            (laya_dir / name).exists()
            for name in ("model.safetensors", "rl_agent_config.json", "tokenizer", "encoder/config.json")
        )
    results["laya"] = {
        "model_dir": str(laya_dir) if laya_dir else "",
        "device": laya_device,
        "available": laya_staged,
    }

    # 4. Vision Service
    vision_url = (settings.get("vision_url") or "").rstrip("/")
    vision_model = settings.get("vision_model") or ""
    vision = {
        "url": vision_url,
        "model": vision_model,
        "available": False,
        "error": None,
    }
    if vision_url:
        if vision_url == writer_url and writer_mode == "local":
            vision["available"] = writer["available"]
            vision["error"] = writer["error"]
        else:
            try:
                req = urllib.request.Request(f"{vision_url}/models", headers={"Accept": "application/json"})
                with opener.open(req, timeout=0.3) as resp:
                    if resp.status == 200:
                        vision["available"] = True
            except Exception as exc:
                vision["available"] = False
                vision["error"] = str(exc)
    results["vision"] = vision

    return results


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
        comfy_detail = f"Offline at {comfy_raw.get('url') or 'unconfigured'}"
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
            writer_activity = "sleeping" if writer_avail else "offline"
            writer_detail = f"External API ready ({writer_model})" if writer_avail else "API key or model unconfigured"
    else:
        if not writer_avail:
            writer_activity = "offline"
            writer_detail = f"Offline at {writer_raw.get('url') or 'unconfigured'}"
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

    return {
        "comfy": comfy_status,
        "writer": writer_status,
        "laya": laya_status,
        "vision": vision_status,
    }
