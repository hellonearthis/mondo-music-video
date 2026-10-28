"""Segment take history, single-passage reroll rendering, and final video re-encoding."""
from __future__ import annotations

import random
import re
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

from .storage import Storage, identifier, inside, read_json, write_json

TAKES_FILE = "takes.json"
FINAL_TAKES_FILE = "final_takes.json"
SEGMENT_ID_RE = re.compile(r"seg\d{3,4}")
TAKE_ID_RE = re.compile(r"take\d{1,4}")
# Only free renderers may reroll: a paid passage needs its own quote and consent, which reroll does not offer.
REROLL_BACKENDS = ("local_h3",)


def reroll_block(request: dict) -> str | None:
    """Why this production's passages cannot be rerolled, or None when they can."""
    if request.get("backend", "local_h3") not in REROLL_BACKENDS:
        return "Reroll is available for the local H3 renderer only; other renderers can submit paid jobs and need a new preview and consent."
    return None


def validate_segment_id(segment_id: str) -> str:
    if not SEGMENT_ID_RE.fullmatch(segment_id or ""):
        raise ValueError("Invalid passage ID")
    return segment_id


def validate_take_id(take_id: str) -> str:
    if not TAKE_ID_RE.fullmatch(take_id or ""):
        raise ValueError("Invalid take ID")
    return take_id


def _takes_view(directory: Path, plan: dict, request: dict, renders: dict) -> tuple[dict, bool]:
    """Recorded takes with each rendered passage's original clip as take 1. Pure: returns (takes, changed)."""
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
                "created_at": got.get("created_at") or _mtime(directory / "renders.json"),
                "render": got,
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

    return {"segments": segments}, changed or not (directory / TAKES_FILE).is_file()


def _mtime(path: Path) -> float:
    return path.stat().st_mtime if path.exists() else time.time()


def _ensure_takes_initialized(directory: Path, plan: dict, request: dict, renders: dict) -> dict:
    """The takes record, saved when it was missing or stale. Only actions that change takes call this."""
    takes, changed = _takes_view(directory, plan, request, renders)
    if changed:
        write_json(directory / TAKES_FILE, takes)
    return takes


def get_segment_takes(store: Storage, run_id: str) -> dict:
    """Takes for a run (derived outputs resolve to their origin run). Read-only: nothing is written."""
    from .score_view import _origin_run, _run_files
    origin = _origin_run(store, run_id)
    directory = inside(store.home / "runs", identifier(origin))
    plan, _, renders = _run_files(store, origin)
    request = read_json(directory / "request.json", {})
    return _takes_view(directory, plan, request, renders)[0]


def get_final_takes(store: Storage, run_id: str) -> dict:
    """Final assembled video versions for a run. Read-only: the original is listed until a re-encode saves it."""
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
    # The take's own render record replaces the passage entry, so no seed or receipt of another take lingers.
    renders[segment_id] = chosen.get("render") or {"video": chosen["video"], "audio": chosen.get("audio", ""), "seed": chosen.get("seed")}
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
    if blocked := reroll_block(request):
        raise ValueError(blocked)

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

    # Replay the production's own prepared settings, as the original render did; later setting changes do not apply.
    settings = prepared.get("settings") or {}
    if not settings.get("workflow_map_path"):
        raise ValueError("Saved production settings are missing; cannot reroll passage")
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

    next_num = max((int(t["id"][4:]) for t in existing_takes if TAKE_ID_RE.fullmatch(t.get("id", ""))), default=0) + 1
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
        # The original run's render-graph.json and local-request.json stay as recovery records; each take keeps its own.
        def record_queue(client, graph):
            write_json(directory / f"render-graph-{render_seg_id}.json", graph)
            prompt_id = original_queue(client, graph)
            write_json(directory / f"local-request-{render_seg_id}.json", {"prompt_id": prompt_id})
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

    render = {**result, "seed": seed, "take_id": take_id}
    new_take = {
        "id": take_id,
        "label": f"Take {next_num} (seed {seed})",
        "seed": seed,
        "video": result["video"],
        "audio": result.get("audio", ""),
        "created_at": time.time(),
        "render": render,
    }
    existing_takes.append(new_take)
    seg_takes["active_take"] = take_id
    write_json(directory / TAKES_FILE, takes_data)
    renders[segment_id] = render
    write_json(directory / "renders.json", renders)
    progress(f"Completed {segment_id} {take_id}", 100)
    return {
        "run_id": directory.name,
        "segment_id": segment_id,
        "active_take": take_id,
        "take": new_take,
    }


def reassemble_final_video(store: Storage, run_id: str, context, selected_takes: dict | None = None) -> dict:
    """Re-encode the final music video using the active (or specified) takes from original clips, preserving all previous final videos."""
    from .score_view import _origin_run, _run_files, _clip_roots, _recorded_clip
    from . import final_assembly, subliminal, captions
    from .media import duration

    origin = _origin_run(store, run_id)
    directory = inside(store.home / "runs", identifier(origin))
    request = read_json(directory / "request.json", {})
    prepared = read_json(directory / "prepared.json", {})
    plan, _, renders = _run_files(store, origin)
    if not plan.get("segments") or not renders:
        raise ValueError("Original assembly sources are unavailable; cannot reassemble video")

    # Every choice is checked first and saved only after the new video is assembled, so a refusal or failure changes nothing.
    takes_data = _takes_view(directory, plan, request, renders)[0]
    renders = dict(renders)
    for sid, tid in (selected_takes or {}).items():
        seg_entry = takes_data["segments"].get(validate_segment_id(sid)) or {}
        chosen = next((t for t in seg_entry.get("takes") or [] if t.get("id") == validate_take_id(tid)), None)
        if chosen is None:
            raise ValueError(f"Take {tid} not found for passage {sid}")
        if _recorded_clip({"t": chosen}, "t", _clip_roots(store)) is None:
            raise ValueError(f"The video file for {tid} is no longer available on disk")
        seg_entry["active_take"] = tid
        renders[sid] = chosen.get("render") or {"video": chosen["video"], "audio": chosen.get("audio", ""), "seed": chosen.get("seed")}

    output_record = read_json(directory / "output.json", {})
    final_name = output_record.get("file") or ("ident.mp4" if request.get("kind") == "ident" else "music-video.mp4")
    final_path = directory / final_name
    if not final_path.is_file() and not (directory / FINAL_TAKES_FILE).is_file():
        raise ValueError(f"The finished video {final_name} is missing; restore it so the original version is kept before re-encoding")

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
    write_json(directory / TAKES_FILE, takes_data)
    write_json(directory / "renders.json", renders)

    # Each variant is assembled from the original clips, as in the first production; a failed effect is reported, not hidden.
    warnings, effects = [], {}
    if request.get("kind") == "video" and prepared.get("subliminal"):
        context.update("Applying subliminal version from selected passage clips", 75)
        try:
            effects["subliminal"] = subliminal.apply_to_run(store, directory, prepared["subliminal"])
        except Exception as exc:
            warnings.append("The subliminal flashes could not be added, so this version is the clean one: " + str(exc)[:200])

    if request.get("kind") == "video" and (prepared.get("captions") or {}).get("cues"):
        context.update("Applying lyric captions from selected passage clips", 85)
        try:
            effects["captions"] = captions.apply_to_run(directory, prepared["captions"])
        except Exception as exc:
            effects["captions"] = {"burn_error": str(exc)}
        if burn_error := effects["captions"].get("burn_error"):
            warnings.append("The lyric captions could not be burned in, so this version has none: " + burn_error[:200])

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
        **({"warnings": warnings} if warnings else {}),
    }
    final_takes["takes"].append(new_final_take)
    final_takes["active"] = final_name
    write_json(directory / FINAL_TAKES_FILE, final_takes)

    measured = duration(output)
    for key in ("subliminal", "captions", "reassembly_warnings"):
        output_record.pop(key, None)
    output_record.update({
        "file": output.name,
        "duration": measured,
        "final_takes": [t["file"] for t in final_takes["takes"] if t.get("file")],
        **{key: value for key, value in effects.items() if value},
        **({"reassembly_warnings": warnings} if warnings else {}),
    })
    write_json(directory / "output.json", output_record)
    context.update("Re-assembly complete", 100)
    return {
        "file": f"{origin}/{output.name}",
        "version_file": f"{origin}/{version_file}",
        "duration": measured,
        "final_take": new_final_take,
        "final_takes": final_takes["takes"],
        "warnings": warnings,
    }
