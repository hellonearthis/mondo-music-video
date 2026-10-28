"""Segment take history, single-passage reroll rendering, and final video re-encoding."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

from .storage import Storage, identifier, inside, read_json, write_json

TAKES_FILE = "takes.json"
PROMPT_TAKES_FILE = "prompt_takes.json"
FINAL_TAKES_FILE = "final_takes.json"
SEGMENT_ID_RE = re.compile(r"seg\d{3,4}")
TAKE_ID_RE = re.compile(r"take\d{1,4}")
PROMPT_TAKE_ID_RE = re.compile(r"prompt\d{1,4}")


def validate_segment_id(segment_id: str) -> str:
    if not SEGMENT_ID_RE.fullmatch(segment_id or ""):
        raise ValueError("Invalid passage ID")
    return segment_id


def validate_take_id(take_id: str) -> str:
    if not TAKE_ID_RE.fullmatch(take_id or ""):
        raise ValueError("Invalid take ID")
    return take_id


def validate_prompt_take_id(prompt_take_id: str) -> str:
    if not PROMPT_TAKE_ID_RE.fullmatch(prompt_take_id or ""):
        raise ValueError("Invalid prompt take ID")
    return prompt_take_id


def _ensure_prompt_takes_initialized(directory: Path, plan: dict, prompts: dict) -> dict:
    ptakes = read_json(directory / PROMPT_TAKES_FILE, {})
    if not isinstance(ptakes, dict):
        ptakes = {}
    segments = ptakes.get("segments")
    if not isinstance(segments, dict):
        segments = {}
    changed = False

    by_id = {f"seg{seg['index']:03d}": seg for seg in (plan.get("segments") or [])}
    all_sids = list(by_id.keys()) or sorted(prompts.keys())
    prompts_mtime = (directory / "prompts.json").stat().st_mtime if (directory / "prompts.json").exists() else time.time()

    for sid in all_sids:
        entry = segments.get(sid)
        prompt_text = prompts.get(sid)
        if not isinstance(prompt_text, str) or not prompt_text:
            continue
        if not isinstance(entry, dict) or not isinstance(entry.get("takes"), list) or not entry["takes"]:
            p1 = {
                "id": "prompt1",
                "label": "Prompt 1 (original)",
                "prompt": prompt_text,
                "char_count": len(prompt_text),
                "created_at": prompts_mtime,
            }
            segments[sid] = {"active_take": "prompt1", "takes": [p1]}
            changed = True
        else:
            matching = next((t["id"] for t in entry["takes"] if t.get("prompt") == prompt_text), None)
            if matching and entry.get("active_take") != matching:
                entry["active_take"] = matching
                changed = True
            elif not entry.get("active_take"):
                entry["active_take"] = entry["takes"][-1]["id"]
                changed = True

    result = {"version": 1, "segments": segments}
    if changed or not (directory / PROMPT_TAKES_FILE).is_file():
        write_json(directory / PROMPT_TAKES_FILE, result)
    return result


def get_prompt_takes(store: Storage, run_id: str) -> dict:
    """Return initialized prompt_takes structure for a run."""
    from .score_view import _origin_run, _run_files
    origin = _origin_run(store, run_id)
    directory = inside(store.home / "runs", identifier(origin))
    plan, prompts, _ = _run_files(store, origin)
    return _ensure_prompt_takes_initialized(directory, plan, prompts)


def select_prompt_take(store: Storage, run_id: str, segment_id: str, prompt_take_id: str) -> dict:
    """Select an existing prompt version for a segment and update prompts.json to point to it."""
    from .score_view import _origin_run, _run_files
    from . import passage_plans
    segment_id = validate_segment_id(segment_id)
    prompt_take_id = validate_prompt_take_id(prompt_take_id)
    origin = _origin_run(store, run_id)
    directory = inside(store.home / "runs", identifier(origin))
    plan, prompts, _ = _run_files(store, origin)
    ptakes_data = _ensure_prompt_takes_initialized(directory, plan, prompts)
    seg_entry = ptakes_data["segments"].get(segment_id)
    if not seg_entry or not seg_entry.get("takes"):
        raise ValueError(f"No prompt takes recorded for passage {segment_id}")
    chosen = next((t for t in seg_entry["takes"] if t.get("id") == prompt_take_id), None)
    if not chosen or not isinstance(chosen.get("prompt"), str):
        raise ValueError(f"Prompt version {prompt_take_id} not found for passage {segment_id}")

    seg_entry["active_take"] = prompt_take_id
    write_json(directory / PROMPT_TAKES_FILE, ptakes_data)

    prompts[segment_id] = chosen["prompt"]
    write_json(directory / "prompts.json", prompts)
    prepared = read_json(directory / "prepared.json", {})
    if prepared:
        try:
            passage_plans.bind_prompts(directory, prepared, prompts)
        except Exception:
            pass

    return {
        "run_id": origin,
        "segment_id": segment_id,
        "active_prompt_take": prompt_take_id,
        "prompt_take": chosen,
        "prompt": chosen["prompt"],
        "char_count": len(chosen["prompt"]),
    }


def save_edited_prompt_take(store: Storage, run_id: str, segment_id: str, prompt_text: str) -> dict:
    """Save a manually edited prompt for a segment as a new prompt take while preserving all earlier versions."""
    from .score_view import _origin_run, _run_files
    from . import passage_plans
    segment_id = validate_segment_id(segment_id)
    cleaned = str(prompt_text or "").strip()
    if not cleaned:
        raise ValueError("Prompt text cannot be empty")
    if len(cleaned) > 64000:
        raise ValueError("Prompt text exceeds maximum length (64,000 characters)")

    origin = _origin_run(store, run_id)
    directory = inside(store.home / "runs", identifier(origin))
    plan, prompts, _ = _run_files(store, origin)
    ptakes_data = _ensure_prompt_takes_initialized(directory, plan, prompts)
    seg_entry = ptakes_data["segments"].setdefault(segment_id, {"active_take": "", "takes": []})
    existing_takes = seg_entry["takes"]
    next_num = len(existing_takes) + 1
    prompt_take_id = f"prompt{next_num}"

    new_ptake = {
        "id": prompt_take_id,
        "label": f"Prompt {next_num} (edited)",
        "prompt": cleaned,
        "char_count": len(cleaned),
        "created_at": time.time(),
    }
    existing_takes.append(new_ptake)
    seg_entry["active_take"] = prompt_take_id
    write_json(directory / PROMPT_TAKES_FILE, ptakes_data)

    prompts[segment_id] = cleaned
    write_json(directory / "prompts.json", prompts)
    prepared = read_json(directory / "prepared.json", {})
    if prepared:
        try:
            passage_plans.bind_prompts(directory, prepared, prompts)
        except Exception:
            pass

    return {
        "run_id": origin,
        "segment_id": segment_id,
        "active_prompt_take": prompt_take_id,
        "prompt_take": new_ptake,
        "prompt_takes": existing_takes,
        "prompt": cleaned,
        "char_count": len(cleaned),
    }


def _ensure_takes_initialized(directory: Path, plan: dict, request: dict, renders: dict) -> dict:
    takes = read_json(directory / TAKES_FILE, {})
    if not isinstance(takes, dict):
        takes = {}
    segments = takes.get("segments")
    if not isinstance(segments, dict):
        segments = {}
    base_seed = int(request.get("seed") or 42)
    changed = False

    by_id = {f"seg{seg['index']:03d}": seg for seg in (plan.get("segments") or [])}
    all_sids = list(by_id.keys()) or sorted(renders.keys())

    for sid in all_sids:
        entry = segments.get(sid)
        got = renders.get(sid)
        if not isinstance(got, dict) or not got.get("video"):
            continue
        seg = by_id.get(sid, {"index": int(sid[3:]) if sid[3:].isdigit() else 0})
        if not isinstance(entry, dict) or not isinstance(entry.get("takes"), list) or not entry["takes"]:
            take1 = {
                "id": "take1",
                "label": "Take 1 (original)",
                "seed": got.get("seed", base_seed + seg["index"]),
                "video": got["video"],
                "audio": got.get("audio", ""),
                "created_at": got.get("created_at") or (directory / "renders.json").stat().st_mtime if (directory / "renders.json").exists() else time.time(),
            }
            segments[sid] = {"active_take": "take1", "takes": [take1]}
            changed = True
        else:
            # Ensure active_take points to a valid take or matches renders.json
            current_video = got.get("video")
            matching = next((t["id"] for t in entry["takes"] if t.get("video") == current_video), None)
            if matching and entry.get("active_take") != matching:
                entry["active_take"] = matching
                changed = True
            elif not entry.get("active_take"):
                entry["active_take"] = entry["takes"][-1]["id"]
                changed = True

    result = {"segments": segments}
    if changed or not (directory / TAKES_FILE).is_file():
        write_json(directory / TAKES_FILE, result)
    return result


def get_segment_takes(store: Storage, run_id: str) -> dict:
    """Return initialized takes structure for a run (resolving derived outputs to their origin run)."""
    from .score_view import _origin_run, _run_files
    origin = _origin_run(store, run_id)
    directory = inside(store.home / "runs", identifier(origin))
    plan, _, renders = _run_files(store, origin)
    request = read_json(directory / "request.json", {})
    return _ensure_takes_initialized(directory, plan, request, renders)


def get_final_takes(store: Storage, run_id: str) -> dict:
    """Return final assembled video takes for a run."""
    from .score_view import _origin_run
    origin = _origin_run(store, run_id)
    directory = inside(store.home / "runs", identifier(origin))
    output = read_json(directory / "output.json", {})
    final_file = output.get("file") or ("ident.mp4" if output.get("kind") == "ident" else "music-video.mp4")
    records = read_json(directory / FINAL_TAKES_FILE, {})
    if not isinstance(records, dict) or not isinstance(records.get("takes"), list) or not records["takes"]:
        if (directory / final_file).is_file():
            initial = {
                "id": "final1",
                "label": "Version 1 (original)",
                "file": final_file,
                "created_at": (directory / final_file).stat().st_mtime,
            }
            records = {"active": final_file, "takes": [initial]}
            write_json(directory / FINAL_TAKES_FILE, records)
        else:
            records = {"active": final_file, "takes": []}
    return records


def select_segment_take(store: Storage, run_id: str, segment_id: str, take_id: str) -> dict:
    """Select an existing take for a segment and update renders.json to point to it."""
    from .score_view import _origin_run, _run_files, _clip_roots, _recorded_clip
    segment_id = validate_segment_id(segment_id)
    take_id = validate_take_id(take_id)
    origin = _origin_run(store, run_id)
    directory = inside(store.home / "runs", identifier(origin))
    plan, _, renders = _run_files(store, origin)
    request = read_json(directory / "request.json", {})
    takes_data = _ensure_takes_initialized(directory, plan, request, renders)
    seg_entry = takes_data["segments"].get(segment_id)
    if not seg_entry or not seg_entry.get("takes"):
        raise ValueError(f"No takes recorded for passage {segment_id}")
    chosen = next((t for t in seg_entry["takes"] if t.get("id") == take_id), None)
    if not chosen:
        raise ValueError(f"Take {take_id} not found for passage {segment_id}")
    roots = _clip_roots(store)
    clip_path = _recorded_clip({"temp": chosen}, "temp", roots)
    if clip_path is None:
        raise ValueError(f"The video file for {take_id} is no longer available on disk")
    seg_entry["active_take"] = take_id
    write_json(directory / TAKES_FILE, takes_data)
    renders[segment_id] = {
        **(renders.get(segment_id) if isinstance(renders.get(segment_id), dict) else {}),
        "video": chosen["video"],
        "audio": chosen.get("audio", ""),
    }
    write_json(directory / "renders.json", renders)
    return {
        "run_id": origin,
        "segment_id": segment_id,
        "active_take": take_id,
        "take": chosen,
        "clip_url": f"/api/outputs/{origin}/clips/{segment_id}?take={take_id}",
    }


def reroll_segment_worker(home: Path, directory: Path, segment_id: str, seed: int | None = None) -> dict:
    """Render a single passage with a fresh seed in the worker process, preserving all previous takes."""
    import os
    os.environ["MMV_HOME"] = str(home)
    store = Storage(home)
    segment_id = validate_segment_id(segment_id)
    request = read_json(directory / "request.json", {})
    prepared = read_json(directory / "prepared.json", {})
    prompts = read_json(directory / "prompts.json", {})
    plan_dict = read_json(directory / "plan.json", {}) or prepared.get("plan") or {}
    renders = read_json(directory / "renders.json", {})

    if not request or not prepared or not plan_dict:
        raise ValueError("Saved production plan or request is missing; cannot reroll passage")
    if not prompts.get(segment_id):
        raise ValueError(f"No saved prompt for passage {segment_id}")

    from .engine import actor, casting, assemble
    from .engine.plan import ShotPlan
    from . import instruments, runtime
    from .render import get_backend
    from .pipeline import ENGINE
    from .worker import require_renderer_handoff, render_timeout, map_steps

    plan_path = directory / "plan.json"
    if not plan_path.is_file():
        write_json(plan_path, plan_dict)
    plan = ShotPlan.from_json(plan_path)
    plan.slug = "mmv-" + directory.name

    seg = next((s for s in plan.segments if s.segment_id == segment_id), None)
    if seg is None:
        raise ValueError(f"Passage {segment_id} is not in this production's plan")

    def progress(message: str, value: int):
        print(message, flush=True)
        write_json(directory / "progress.json", {"message": message, "progress": value})

    settings = {**prepared.get("settings", {}), **store.settings()}
    backend_name = request.get("backend", "local_h3")
    backend = get_backend(backend_name)

    roster = (prepared.get("casting") or {}).get("roster", [])
    actor_records = {}
    for member in roster:
        record = store.actor(member["actor_id"]) or {}
        actor_records[member["actor_id"]] = {
            **record,
            "display_name": member["display_name"],
            "reference_sheets": [member["sheet"]],
            "visual_contract": record.get("visual_contract") or {
                "default_sheet": member["sheet"],
                "sheets": {member["sheet"]: {"canonical_summary": record.get("description", "")}},
            },
        }
    actor.load_actor_meta = lambda actor_id: actor_records[actor_id]

    instrument_plan = prepared.get("instruments") or None
    instrument_passages = (instrument_plan or {}).get("passages", {})
    if instrument_plan:
        instruments.check_replay(request, instrument_plan)
        instruments.verify_assets(instrument_plan)

    takes_data = _ensure_takes_initialized(directory, plan_dict, request, renders)
    seg_takes = takes_data["segments"].setdefault(segment_id, {"active_take": "", "takes": []})
    existing_takes = seg_takes["takes"]
    used_seeds = {t.get("seed") for t in existing_takes if t.get("seed") is not None}

    if seed is None:
        candidate = random.randint(100000, 2147483000)
        while candidate in used_seeds:
            candidate = random.randint(100000, 2147483000)
        seed = candidate

    next_num = len(existing_takes) + 1
    take_id = f"take{next_num}"
    render_seg_id = f"{segment_id}_{take_id}"

    progress(f"Preparing renderer for {segment_id} ({take_id}, seed {seed})", 10)
    if backend_name == "local_h3":
        require_renderer_handoff(settings)
        runtime.start_service(
            settings["comfy_launch"],
            settings["comfy_cwd"],
            settings["comfy_url"].rstrip("/") + "/system_stats",
            directory / "comfy-service.log",
            name="ComfyUI",
            launch_setting="comfy_launch",
        )

    sheets = casting.sheet_paths(prepared["casting"]) if prepared.get("casting") else {}
    if instrument_plan:
        sheets = {**sheets, **{"__instrument_" + kind: asset["path"] for kind, asset in instrument_plan["assets"].items()}}

    url = urlparse(settings["comfy_url"])
    if backend_name == "local_h3":
        from .engine.comfy import ComfyClient
        original_queue = ComfyClient.queue
        def record_queue(client, graph):
            write_json(directory / "render-graph.json", graph)
            prompt_id = original_queue(client, graph)
            write_json(directory / "local-request.json", {"prompt_id": prompt_id})
            return prompt_id
        ComfyClient.queue = record_queue

    backend.open_render(
        slug=plan.slug,
        out_dir=directory / "renders",
        cast_sheets=list(sheets.items()),
        subject_image=None,
        song=None,
        steps=map_steps(settings["workflow_map_path"]),
        timeout_s=render_timeout(backend_name, settings.get("render_timeout_minutes", 120)),
        comfy_host=url.hostname,
        comfy_port=url.port or 8188,
        comfy_input=settings["comfy_input"],
        comfy_output=settings["comfy_output"],
        map_path=settings["workflow_map_path"],
        root=ENGINE,
        comfy_sdk_url=settings["comfy_sdk_url"],
        comfy_sdk_key=store.key("MMV_COMFY_API_KEY"),
        clip_quality=request.get("clip_quality") or "standard",
    )
    try:
        song = inside(store.home / "uploads", request["song"]) if request.get("kind", "video") == "video" else directory / "silence.wav"
        if request.get("kind") == "ident" and not song.is_file():
            subprocess.run(
                ["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", str(seg.gen_frames / 24), str(song)],
                check=True,
            )
        images = [(member["actor_id"], sheets[member["actor_id"]]) for member in casting.cast_for(prepared.get("casting"), seg.segment_id)]
        if instrument_plan:
            images += instruments.images(instrument_passages[seg.segment_id], instrument_plan)
        if len(images) != seg.ref_image_slots:
            raise ValueError("Original cast/reference-slot contract disagrees; refusing render")

        progress(f"Rendering {segment_id} take {next_num} (seed {seed})", 35)
        result = backend.render_segment(
            segment_id=render_seg_id,
            index=seg.index,
            slug=plan.slug,
            prompt=prompts[seg.segment_id],
            duration_input=seg.duration_input,
            gen_frames=seg.gen_frames,
            width=plan.width,
            height=plan.height,
            seed=seed,
            images=images,
            song=str(song),
            audio_start_s=seg.audio_slice_start_s,
            audio_end_s=seg.audio_slice_end_s,
        )
        video = result.get("video")
        if not video or not Path(video).is_file() or assemble.probe_frames(video) < seg.trim_frames:
            raise ValueError("Renderer returned a missing or short clip; refusing incomplete take")
    finally:
        backend.close_render()

    new_take = {
        "id": take_id,
        "label": f"Take {next_num} (seed {seed})",
        "seed": seed,
        "video": result["video"],
        "audio": result.get("audio", ""),
        "created_at": time.time(),
    }
    existing_takes.append(new_take)
    seg_takes["active_take"] = take_id
    write_json(directory / TAKES_FILE, takes_data)

    renders[segment_id] = {
        **result,
        "seed": seed,
        "take_id": take_id,
    }
    write_json(directory / "renders.json", renders)
    progress(f"Completed {segment_id} {take_id}", 100)
    return {
        "run_id": directory.name,
        "segment_id": segment_id,
        "active_take": take_id,
        "take": new_take,
    }


def reroll_prompt_worker(home: Path, directory: Path, segment_id: str) -> dict:
    """Re-write and validate a single passage's prompt in the worker process, preserving all previous prompt takes."""
    os.environ["MMV_HOME"] = str(home)
    store = Storage(home)
    segment_id = validate_segment_id(segment_id)
    request = read_json(directory / "request.json", {})
    prepared = read_json(directory / "prepared.json", {})
    prompts = read_json(directory / "prompts.json", {})
    plan_dict = read_json(directory / "plan.json", {}) or prepared.get("plan") or {}

    if not request or not prepared or not plan_dict:
        raise ValueError("Saved production plan or request is missing; cannot reroll prompt")

    from .engine import style, actor, casting
    from .engine.plan import ShotPlan
    from .engine.schema import WriterResponse, build_writer_request, assemble_prompt, validate_prompt, ValidationError, RIGGING_TAIL
    from .engine.writer import call_llm
    from . import quality, instruments, runtime, gpu_memory, writer_usage, storyboard, passage_plans
    from .dance import is_blocking as dance_blocking
    from .instruments import is_blocking as instrument_blocking
    from .render import get_backend
    from .worker import blocking_for, _compact_writer_job, _compact_ident_prompt
    from .writer_json import MAX_FREE_RETRIES, draft_feedback, escape_control_characters, is_broken_json

    plan_path = directory / "plan.json"
    if not plan_path.is_file():
        write_json(plan_path, plan_dict)
    plan = ShotPlan.from_json(plan_path)
    plan.slug = "mmv-" + directory.name

    seg = next((s for s in plan.segments if s.segment_id == segment_id), None)
    if seg is None:
        raise ValueError(f"Passage {segment_id} is not in this production's plan")

    def progress(message: str, value: int):
        print(message, flush=True)
        write_json(directory / "progress.json", {"message": message, "progress": value})

    settings = {**prepared.get("settings", {}), **store.settings()}
    backend_name = request.get("backend", "local_h3")
    backend = get_backend(backend_name)

    ctx_size = writer_usage.launch_context(settings)

    def llm(system: str, user: str, label: str | None = None) -> str:
        captured = {}
        ok, text, error = writer_usage.observe(
            lambda: call_llm(None, system, user, 0.7, 4096, 900, profile=(settings, store.key("MMV_WRITER_API_KEY"))),
            captured,
        )
        if not ok:
            mode = "local llama.cpp" if settings.get("writer_mode") == "local" else "API writer"
            endpoint = runtime.safe_endpoint(settings.get("writer_url", ""))
            err_str = str(error or "")
            if any(term in err_str.lower() for term in ("connection refused", "winerror 10061", "offline", "unreachable", "failed to establish", "connection error", "target machine actively refused")):
                raise ValueError(f"Prompt Writer is offline or unreachable ({mode} at {endpoint}): {error}. Please ensure the writer service is running.")
            raise ValueError(f"Writer ({mode} at {endpoint}) failed: {error or 'Writer returned no output'}")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"Writer ({settings.get('writer_model') or 'llama.cpp'}) returned empty text")
        if line := writer_usage.usage_line(captured, ctx_size, label):
            print(line, flush=True)
        return text

    ptakes_data = _ensure_prompt_takes_initialized(directory, plan_dict, prompts)
    seg_ptakes = ptakes_data["segments"].setdefault(segment_id, {"active_take": "", "takes": []})
    existing_ptakes = seg_ptakes["takes"]
    next_num = len(existing_ptakes) + 1
    prompt_take_id = f"prompt{next_num}"

    style_dir = directory / "style"
    style_dir.mkdir(exist_ok=True)
    (style_dir / "aesthetic.md").write_text(prepared["style"]["direction"], encoding="utf-8")
    (style_dir / "style_card.md").write_text(prepared["style"].get("style_card", prepared["style"]["direction"]), encoding="utf-8")

    roster = (prepared.get("casting") or {}).get("roster", [])
    actor_records = {}
    for member in roster:
        record = store.actor(member["actor_id"]) or {}
        actor_records[member["actor_id"]] = {
            **record,
            "display_name": member["display_name"],
            "reference_sheets": [member["sheet"]],
            "visual_contract": record.get("visual_contract") or {
                "default_sheet": member["sheet"],
                "sheets": {member["sheet"]: {"canonical_summary": record.get("description", "")}},
            },
        }
    actor.load_actor_meta = lambda actor_id: actor_records[actor_id]

    mouth_mode = request.get("mouth_mode") or ("sealed" if request.get("silent_mouths", True) else "natural")
    effective_silent_mouths = mouth_mode in ("sealed", "lip_sync")
    singing_plan = ((prepared.get("lipsync") or {}).get("passages") or {}) if mouth_mode == "lip_sync" else {}
    instrument_plan = prepared.get("instruments") or None
    instrument_passages = (instrument_plan or {}).get("passages", {})
    if instrument_plan:
        instruments.check_replay(request, instrument_plan)
        instruments.verify_assets(instrument_plan)
    dance_plan = prepared.get("dance") or None
    dance_passages = ((dance_plan or {}).get("passages") or {}) if request.get("kind", "video") == "video" else {}
    cast_block = actor.cast_writer_block([a["actor_id"] for a in roster], silent_mouths=effective_silent_mouths)
    content = request.get("content") or {}
    restrictions = [name for name in ("nudity", "blood", "violence", "sexual") if content.get({"blood": "blood_gore", "sexual": "sexual_content"}.get(name, name), "none") == "none"]
    if all(value == "none" for value in content.values()):
        restrictions = ["nudity", "blood", "violence", "sexual"]

    if backend_name in ("local_h3", "comfy_sdk_h3") and settings.get("comfy_url") and runtime.http_ok(settings["comfy_url"].rstrip("/") + "/system_stats"):
        from .comfy_memory import release_cached_models
        progress("Releasing ComfyUI model memory for prompt generation", 5)
        release_cached_models(settings["comfy_url"])

    gpu_before_writer = gpu_memory.gpu_memory()
    writer_process = None
    validator = None
    try:
        if settings.get("writer_mode") == "local":
            if not runtime.http_ok(settings["writer_url"].rstrip("/") + "/models"):
                try:
                    command = json.loads(settings["writer_launch"])
                    need = gpu_memory.gguf_need_bytes(command) if isinstance(command, list) else None
                except (ValueError, TypeError, AttributeError):
                    need = None
                if need and gpu_before_writer and gpu_before_writer[0] < need:
                    raise ValueError(
                        f"Not enough free GPU memory to start the writer: "
                        f"{gpu_memory.gib(gpu_before_writer[0])} free, about {gpu_memory.gib(need)} needed."
                    )
            progress("Starting music-video writer", 15)
            writer_process = runtime.start_service(
                settings["writer_launch"],
                settings["writer_cwd"],
                settings["writer_url"].rstrip("/") + "/models",
                directory / "writer-service.log",
                name="llama.cpp (Writer)",
                launch_setting="writer_launch",
            )

        if request.get("kind") == "ident":
            system = style.compose_ident_prompt()
            if request.get("compact_prompts"):
                system = _compact_ident_prompt(system, request["ident_mode"])
            message = style.build_ident_writer_message(
                request["title"],
                request["ident_seconds"],
                request["ident_mode"],
                style_card=prepared["style"].get("style_card", prepared["style"]["direction"]),
                ident_notes=storyboard.ident_notes(request["direction"], prepared.get("storyboard"), seg.segment_id),
            )
            progress(f"Writing new ident prompt ({prompt_take_id})", 45)
            raw = llm(system, message, label=f"ident-{prompt_take_id}").strip()
            if raw.startswith("```"):
                raw = "\n".join(raw.splitlines()[1:-1]).strip()
            if request["title"] not in raw:
                raise ValueError("Ident writer omitted the exact requested title")
            prompt = raw
        else:
            from .engine.validators import LayaSemanticValidator
            validator = LayaSemanticValidator()
            override, why = gpu_memory.laya_device_choice(
                settings.get("laya_device", "cuda"),
                gpu_memory.laya_need_bytes(settings.get("laya_model_dir") or ""),
                gpu_memory.gpu_memory(),
            )
            if override:
                os.environ["MMV_LAYA_DEVICE_OVERRIDE"] = override
            progress(why, 25)
            progress("Loading Laya prompt reviewer", 30)
            try:
                validator._load_agent()
            except Exception as exc:
                raise ValueError(f"Laya semantic validator failed to load: {exc}") from exc

            system = style.compose_writer_prompt(
                str(style_dir),
                actor_block=cast_block,
                restrictions=restrictions,
                silent_mouths=effective_silent_mouths,
                lyrics=request.get("lyrics") or None,
                direction=request.get("direction") or None,
            )
            system += quality.WRITER_RULES
            system_singing = cast_block_singing = None
            if any(item.get("singing") for item in singing_plan.values()):
                from . import lipsync
                cast_block_singing = actor.cast_writer_block([a["actor_id"] for a in roster], silent_mouths=False)
                system_singing = style.compose_writer_prompt(
                    str(style_dir),
                    actor_block=cast_block_singing,
                    restrictions=restrictions,
                    silent_mouths=False,
                    lyrics=request.get("lyrics") or None,
                    direction=request.get("direction") or None,
                )
                system_singing += "\n\n" + lipsync.SINGING_RULES + quality.WRITER_RULES
            system_dance = system_singing_dance = None
            if any(item.get("dancing") for item in dance_passages.values()):
                from . import dance
                tail = quality.WRITER_RULES
                system_dance = system[:-len(tail)] + "\n\n" + dance.writer_rules(dance_plan) + tail
                if system_singing is not None:
                    system_singing_dance = system_singing[:-len(tail)] + "\n\n" + dance.writer_rules(dance_plan) + " " + dance.DANCE_SINGER_SENTENCE + tail

            tags = backend.ref_tags(seg.ref_image_slots, 0, 1)
            sing = singing_plan.get(seg.segment_id) or {}
            singing = bool(sing.get("singing")) and system_singing is not None
            seg_silent = effective_silent_mouths and not singing
            dpass = dance_passages.get(seg.segment_id) or {}
            dancing = bool(dpass.get("dancing")) and system_dance is not None
            seg_system = (system_singing_dance if dancing else system_singing) if singing else (system_dance if dancing else system)
            ipass = instrument_passages.get(seg.segment_id) or {}
            performing = bool(ipass.get("performers"))
            if performing:
                tail = quality.WRITER_RULES
                seg_system = seg_system[:-len(tail)] + "\n\n" + instruments.RULES + tail
            seg_cast_block = cast_block_singing if singing else cast_block
            cast_entries = casting.cast_for(prepared["casting"], seg.segment_id)
            if singing:
                from . import lipsync
                cast_entries = lipsync.with_singer_lines(cast_entries, sing["actor_id"], sing["lines"])
            job = build_writer_request(plan, seg, tags, cast_entries, silent_mouths=seg_silent)
            if singing:
                job["singing"] = {
                    "actor_id": sing["actor_id"],
                    "picture_tag": sing["picture_tag"],
                    "lines": sing["lines"],
                    "shots": lipsync.shot_lyrics(seg, sing["lines"]),
                }
            if dancing:
                from . import dance
                job["dance"] = dance.job(dpass, dance_plan)
            if performing:
                job["instrument_performance"] = instruments.job(ipass, instrument_plan, tags)
            if prepared.get("storyboard"):
                job["storyboard"] = storyboard.writer_context(prepared["storyboard"], seg.segment_id)
            if request.get("conceptual_theme"):
                job["conceptual_theme"] = request["conceptual_theme"]

            dance_blocks, instrument_blocks = blocking_for(request, dance_blocking), blocking_for(request, instrument_blocking)
            progress(f"Writing new prompt for {seg.segment_id} ({prompt_take_id})", 45)

            feedback, soft_fallback = "", None
            if existing_ptakes and existing_ptakes[-1].get("prompt"):
                feedback = "\n\nWrite a fresh, distinct variation for each shot body while strictly obeying all structural, style, and rigging rules."
            compact = bool(request.get("compact_prompts"))
            attempts = (4 if singing or dancing or performing else 3) if settings.get("writer_mode") == "local" else 1
            attempt = call = free_retries = 0
            prompt = None
            while attempt < attempts:
                tag = f"{seg.segment_id}-{prompt_take_id} (attempt {call + 1})" if call else f"{seg.segment_id}-{prompt_take_id}"
                if compact:
                    raw = llm(seg_system, _compact_writer_job(job) + feedback, label=tag)
                else:
                    raw = llm(seg_system + feedback, json.dumps(job, indent=2), label=tag)
                (directory / f"{seg.segment_id}.{prompt_take_id}.writer-{call + 1}.json").write_text(raw, encoding="utf-8")
                instrument_problems, advice, draft_bodies = [], [], None
                try:
                    response = WriterResponse.parse(escape_control_characters(raw), seg.segment_id)
                    if performing:
                        bodies, repaired_shots = instruments.repair_shot_bodies(response.shot_bodies, seg, ipass, instrument_plan, tags)
                        if repaired_shots:
                            response = replace(response, shot_bodies=bodies)
                    draft_bodies = response.shot_bodies
                    prompt = assemble_prompt(seg, response, tags)
                    if singing:
                        from . import lipsync
                        prompt = lipsync.swap_audio_sentence(prompt, tags.music_tag)
                    if seg_silent and RIGGING_TAIL.rstrip(".").lower() not in prompt.lower():
                        soundscape_pos = prompt.find("\noverall_soundscape:")
                        if soundscape_pos > 0:
                            prompt = prompt[:soundscape_pos].rstrip() + f" {RIGGING_TAIL}\n" + prompt[soundscape_pos:]
                        else:
                            prompt = prompt.rstrip() + f" {RIGGING_TAIL}\n"
                    found_instruments = instruments.problems(prompt, response.shot_bodies, seg, ipass, instrument_plan, tags) if performing else []
                    found_dance = dance.dance_problems(prompt, response.shot_bodies, seg, dpass, dance_plan) if dancing else []
                    instrument_problems = list(filter(instrument_blocks, found_instruments))
                    advice = [x for x in found_instruments if not instrument_blocks(x)] + [x for x in found_dance if not dance_blocks(x)]
                    problems = (
                        validate_prompt(prompt, seg, tags, strict_words=False, silent_mouths=seg_silent)
                        + quality.prompt_problems(prompt, seg, request.get("direction"))
                        + (lipsync.lipsync_problems(prompt, response.shot_bodies, seg, sing, *lipsync.cast_refs(cast_entries, sing["actor_id"])) if singing else [])
                        + list(filter(dance_blocks, found_dance))
                        + instrument_problems
                    )
                except (ValidationError, TypeError, AttributeError, KeyError) as exc:
                    prompt = None
                    problems = [str(exc)]

                if dancing and prompt is not None and problems and all(dance.is_soft(x) for x in problems) and soft_fallback is None:
                    soft_fallback = (prompt, problems)
                if dancing and problems and attempt == attempts - 1 and soft_fallback is not None:
                    prompt, _ = soft_fallback
                    problems = []
                if not problems:
                    progress(f"Laya reviewing {seg.segment_id} ({prompt_take_id})", 75)
                    state = {
                        "slug": plan.slug,
                        "backend": request.get("backend"),
                        "restrictions": {x: True for x in restrictions},
                        "lyrics_flavor": (" / ".join(item["text"] for item in sing["lines"]) if singing else request.get("lyrics")),
                        "director_direction": request.get("direction"),
                        "style_digest": prepared["style"].get("style_card", prepared["style"]["direction"]),
                        "cast_digest": seg_cast_block,
                    }
                    laya_resp, problems = validator.run_clipboard(prompt, seg, tags, silent_mouths=seg_silent, state=state)
                    write_json(directory / f"{seg.segment_id}.{prompt_take_id}.laya-response-{call + 1}.json", laya_resp)
                if not problems:
                    break
                write_json(directory / f"{seg.segment_id}.{prompt_take_id}.validation-{call + 1}.json", problems)
                call += 1
                if prompt is None and is_broken_json(problems) and free_retries < MAX_FREE_RETRIES:
                    free_retries += 1
                    continue
                attempt += 1
                if instrument_problems:
                    others = [x for x in problems if x not in instrument_problems]
                    feedback = (("\n\nCorrect these validation failures in your next response:\n" + validator.format_retry_feedback(others)) if others else "") + instruments.retry_feedback(instrument_problems)
                else:
                    feedback = "\n\nCorrect these validation failures in your next response:\n" + validator.format_retry_feedback(problems)
                if draft_bodies is not None and (dancing or performing):
                    feedback += draft_feedback(draft_bodies)
            else:
                raise ValueError(f"{seg.segment_id}: prompt validation failed after {attempts} attempts.")
    finally:
        if validator is not None:
            validator._agent = None
            del validator
        if writer_process is not None:
            progress("Stopping music-video writer", 90)
        runtime.stop_confirmed(writer_process, "Music-video writer")

    new_ptake = {
        "id": prompt_take_id,
        "label": f"Prompt {next_num} (reroll)",
        "prompt": prompt,
        "char_count": len(prompt),
        "created_at": time.time(),
    }
    existing_ptakes.append(new_ptake)
    seg_ptakes["active_take"] = prompt_take_id
    write_json(directory / PROMPT_TAKES_FILE, ptakes_data)

    prompts[segment_id] = prompt
    write_json(directory / "prompts.json", prompts)
    try:
        passage_plans.bind_prompts(directory, prepared, prompts)
    except Exception:
        pass

    progress(f"Completed {segment_id} {prompt_take_id}", 100)
    return {
        "run_id": directory.name,
        "segment_id": segment_id,
        "active_prompt_take": prompt_take_id,
        "prompt_take": new_ptake,
        "prompt": prompt,
        "char_count": len(prompt),
    }


def reassemble_final_video(store: Storage, run_id: str, context, selected_takes: dict | None = None) -> dict:
    """Re-encode the final music video using the active (or specified) takes from original clips, preserving all previous final videos."""
    from .score_view import _origin_run, _run_files
    from . import final_assembly, subliminal, captions
    from .media import duration

    origin = _origin_run(store, run_id)
    directory = inside(store.home / "runs", identifier(origin))
    request = read_json(directory / "request.json", {})
    prepared = read_json(directory / "prepared.json", {})
    plan, _, renders = _run_files(store, origin)
    if not plan.get("segments") or not renders:
        raise ValueError("Original assembly sources are unavailable; cannot reassemble video")

    takes_data = _ensure_takes_initialized(directory, plan, request, renders)
    if selected_takes and isinstance(selected_takes, dict):
        for sid, tid in selected_takes.items():
            if sid in takes_data["segments"] and tid:
                select_segment_take(store, origin, sid, tid)
        _, _, renders = _run_files(store, origin)
        takes_data = read_json(directory / TAKES_FILE, takes_data)

    output_record = read_json(directory / "output.json", {})
    final_name = output_record.get("file") or ("ident.mp4" if request.get("kind") == "ident" else "music-video.mp4")
    final_path = directory / final_name

    # Preserve existing final video takes before re-encoding
    final_takes = get_final_takes(store, origin)
    if final_path.is_file():
        # Ensure Take 1 is backed up as a dedicated file if not already archived
        if len(final_takes["takes"]) == 1 and final_takes["takes"][0]["file"] == final_name:
            backup_v1 = f"{Path(final_name).stem}-v1.mp4"
            if not (directory / backup_v1).is_file():
                shutil.copy2(final_path, directory / backup_v1)
            final_takes["takes"][0]["file"] = backup_v1

    context.update("Re-assembling frame-exact final video from selected passage takes", 25)
    output = final_assembly.assemble(store, directory, request, plan, renders)

    if request.get("kind") == "video" and prepared.get("subliminal"):
        context.update("Applying subliminal version from selected passage clips", 75)
        try:
            subliminal.apply_to_run(store, directory, prepared["subliminal"])
        except Exception:
            pass

    if request.get("kind") == "video" and (prepared.get("captions") or {}).get("cues"):
        context.update("Applying lyric captions from selected passage clips", 85)
        try:
            captions.apply_to_run(directory, prepared["captions"])
        except Exception:
            pass

    next_v = len(final_takes["takes"]) + 1
    version_file = f"{Path(final_name).stem}-v{next_v}.mp4"
    shutil.copy2(output, directory / version_file)

    active_summary = {
        sid: entry.get("active_take", "take1")
        for sid, entry in takes_data.get("segments", {}).items()
    }
    new_final_take = {
        "id": f"final{next_v}",
        "label": f"Version {next_v} ({time.strftime('%H:%M:%S')})",
        "file": version_file,
        "created_at": time.time(),
        "segment_takes": active_summary,
    }
    final_takes["takes"].append(new_final_take)
    final_takes["active"] = final_name
    write_json(directory / FINAL_TAKES_FILE, final_takes)

    measured = duration(output)
    output_record.update({
        "file": output.name,
        "duration": measured,
        "final_takes": [t["file"] for t in final_takes["takes"] if t.get("file")],
    })
    write_json(directory / "output.json", output_record)
    context.update("Re-assembly complete", 100)
    return {
        "file": f"{origin}/{output.name}",
        "version_file": f"{origin}/{version_file}",
        "duration": measured,
        "final_take": new_final_take,
        "final_takes": final_takes["takes"],
    }

