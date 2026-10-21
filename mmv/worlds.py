"""Worlds: persistent in-universe canon (a Universe Ledger) seeded by references and grown with review.

A world is private user data under `<home>/worlds/<id>/vNNNN.json`; every accepted change is a new version and nothing is
overwritten. A harvest never edits a world: it writes a proposal under `<home>/world-proposals/` that the user accepts or
rejects. This module owns its own prompt, payload and parser and does not touch the protected style/writer prompts.
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
import time
from pathlib import Path

from .storage import identifier, inside, read_json, write_json

WORLD_TABLES = ("settings", "lighting", "mechanisms", "costume", "practical_effects", "subject_types", "tonal_registers")
LIST_FIELDS = ("core_laws", "locations", "practices", "objects", "factions", "ecology_rules",
               "moral_ambiguities", "open_threads", "do_not_contradict")
SOURCE_TYPES = ("image", "video", "lore", "run")
POOL_MODES = ("append", "replace")
VIDEO_SUFFIXES = (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi")
LORE_SUFFIXES = (".txt", ".md")
LORE_BYTES = 60 * 1024
KEYFRAMES_PER_VIDEO = 8
KEYFRAMES_PER_RUN = 4
MAX_IMAGES = 24
MAX_LORE_FILES = 5
MAX_LIST = 40
MAX_POOL = 200
MAX_SUBJECTS = 40
MAX_SOURCES = 200

WORLD_HARVEST_PROMPT = """You are building the canon of a fictional world from the material below: pictures, lore text, and notes about
videos already made in it. Treat everything shown or written as REAL inside that world. Describe the world, not the material:
never mention cameras, crews, footage, frames, screens, prompts, video generation or viewers.

Read for rules, not decoration. Find the single system the places, people and objects are all organs of, the one rule that gives
and takes, the register in which the world is spoken of, and the period and place it implies. Name subjects the way the world
itself would (an occupation, a material, a local epithet); never "Subject 7" or "Specimen 404". Be specific and concrete.

Return ONLY one JSON object with exactly these keys:
"name": a short title for the world (a condition or a place, not a prop or a plot event)
"seed_sentence": one sentence stating the world's governing system
"core_laws": list of rules that always hold here
"subjects": list of {"designation": ..., "canon": one line of established fact}
"locations", "practices", "objects", "factions", "ecology_rules", "moral_ambiguities", "open_threads", "do_not_contradict": lists of short in-world statements
"pools": an object with the keys settings, lighting, mechanisms, costume, practical_effects, subject_types, tonal_registers; each
  value is {"include": [short terms in this world's own vocabulary], "exclude": [terms that never belong here]}. Settings are
  places, lighting is how they are lit, mechanisms are actions or processes, costume is wardrobe, practical_effects are
  in-camera atmosphere, subject_types are kinds of people or beings, tonal_registers are moods.
Keep every entry under 240 characters. Use empty lists where the material says nothing."""

GROW_RULES = """The world already exists (its current ledger is below). Return the COMPLETE updated ledger: keep every existing
entry unless the new material contradicts it, add what the new material establishes, and never invent facts the material does not support."""


# ---------- pure data ----------

def _text(value, limit, *, fit):
    if not isinstance(value, str):
        raise ValueError("World entries must be text")
    cleaned = re.sub(r"\s+", " ", value).strip()
    if len(cleaned) > limit:
        if not fit:
            raise ValueError(f"A world entry exceeds {limit} characters")
        cleaned = cleaned[:limit].rstrip()
    return cleaned


def _texts(values, limit, count, *, fit):
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError("World lists must be arrays")
    if len(values) > count and not fit:
        raise ValueError(f"A world list may hold at most {count} entries")
    cleaned = (_text(item, limit, fit=fit) for item in values[:count] if isinstance(item, str) or not fit)
    return list(dict.fromkeys(item for item in cleaned if item))


def _subjects(values, *, fit):
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError("World subjects must be an array")
    if len(values) > MAX_SUBJECTS and not fit:
        raise ValueError(f"A world may hold at most {MAX_SUBJECTS} subjects")
    result = {}
    for item in values[:MAX_SUBJECTS]:
        if not isinstance(item, dict):
            if fit:
                continue
            raise ValueError("Each world subject needs a designation and canon")
        name = _text(item.get("designation", ""), 120, fit=fit)
        if name:
            result[name] = _text(item.get("canon", ""), 400, fit=fit)
    return [{"designation": name, "canon": canon} for name, canon in result.items()]


def _pools(raw, *, fit):
    raw = raw if isinstance(raw, dict) else {}
    if not fit and any(key not in WORLD_TABLES for key in raw):
        raise ValueError("Unknown vocabulary category in a world")
    pools = {}
    for table in WORLD_TABLES:
        spec = raw.get(table) if isinstance(raw.get(table), dict) else {}
        pools[table] = {"include": _texts(spec.get("include"), 240, MAX_POOL, fit=fit),
                        "exclude": _texts(spec.get("exclude"), 240, MAX_POOL, fit=fit)}
    return pools


def _sources(values):
    result = []
    for item in values if isinstance(values, list) else []:
        if isinstance(item, dict) and item.get("type") in SOURCE_TYPES and isinstance(item.get("ref"), str):
            version = item.get("added_in_version")
            result.append({"type": item["type"], "ref": item["ref"][:200],
                           "added_in_version": version if isinstance(version, int) and version > 0 else 1})
    return result[-MAX_SOURCES:]


def normalize(raw, *, fit=False):
    """A clean ledger from untrusted data. `fit` trims model output to the limits; user data that exceeds them is rejected."""
    if not isinstance(raw, dict):
        raise ValueError("A world must be a JSON object")
    name = _text(raw.get("name", ""), 160, fit=fit)
    if not name:
        raise ValueError("A world needs a name")
    ledger = {"id": raw.get("id", ""), "name": name, "seed_sentence": _text(raw.get("seed_sentence", ""), 400, fit=fit),
              "subjects": _subjects(raw.get("subjects"), fit=fit), "pools": _pools(raw.get("pools"), fit=fit),
              "sources": _sources(raw.get("sources"))}
    for field in LIST_FIELDS:
        ledger[field] = _texts(raw.get(field), 400, MAX_LIST, fit=fit)
    return ledger


def _entries(ledger):
    """Every comparable fact of a ledger as {field: {entry: detail}}."""
    result = {field: {item: "" for item in ledger.get(field, [])} for field in LIST_FIELDS}
    result["subjects"] = {s["designation"]: s["canon"] for s in ledger.get("subjects", [])}
    for table in WORLD_TABLES:
        pool = ledger.get("pools", {}).get(table, {})
        result[f"{table} include"] = {item: "" for item in pool.get("include", [])}
        result[f"{table} exclude"] = {item: "" for item in pool.get("exclude", [])}
    return result


def diff(old, new):
    """Field-level changes between two ledgers: [{field, added, removed, changed}], empty fields omitted."""
    before, after = _entries(old or {}), _entries(new)
    changes = []
    for key in ("name", "seed_sentence"):
        if (old or {}).get(key, "") != new.get(key, ""):
            changes.append({"field": key, "added": [new.get(key, "")], "removed": [(old or {}).get(key, "")] if old else [],
                            "changed": []})
    for field in after:
        was, now = before.get(field, {}), after[field]
        added = [item for item in now if item not in was]
        removed = [item for item in was if item not in now]
        changed = [item for item in now if item in was and now[item] != was[item]]
        if added or removed or changed:
            changes.append({"field": field, "added": added, "removed": removed, "changed": changed})
    return changes


def custom_vocabulary(ledger, mode="replace"):
    """The existing custom_vocabulary request shape for a world's pools. `replace` confines a table to the world's terms;
    `append` adds them to the standard pool. A table the world says nothing about is left alone."""
    if mode not in POOL_MODES:
        raise ValueError("World pool mode must be 'append' or 'replace'")
    result = {}
    for table in WORLD_TABLES:
        pool = ledger.get("pools", {}).get(table, {})
        include, exclude = pool.get("include", []), pool.get("exclude", [])
        if include:
            result[table] = {"mode": mode, "add": include, "exclude": exclude}
        elif exclude:
            result[table] = {"mode": "append", "add": [], "exclude": exclude}
    return result


def summary(ledger):
    return {"id": ledger["id"], "name": ledger["name"], "version": ledger["version"], "seed_sentence": ledger["seed_sentence"],
            "updated": ledger.get("updated"), "sources": len(ledger.get("sources", [])),
            "terms": sum(len(p["include"]) for p in ledger["pools"].values())}


# ---------- store ----------

def worlds_dir(store):
    return store.home / "worlds"


def proposals_dir(store):
    return store.home / "world-proposals"


def _world_dir(store, world_id):
    """A world's folder, refusing links that point outside the worlds directory."""
    path = worlds_dir(store) / identifier(world_id)
    if path.is_symlink():
        raise ValueError("World not found")
    return path


def _version_files(directory):
    found = directory.glob("v[0-9][0-9][0-9][0-9]*.json") if directory.is_dir() else ()
    return sorted((path for path in found if path.stem[1:].isdigit() and not path.is_symlink()), key=lambda path: int(path.stem[1:]))


def versions(store, world_id):
    directory = _world_dir(store, world_id)
    return [{"version": int(path.stem[1:]), "updated": (read_json(path, {}) or {}).get("updated")}
            for path in _version_files(directory)]


def load(store, world_id, version=None):
    directory = _world_dir(store, world_id)
    files = _version_files(directory)
    if not files:
        raise ValueError("World not found")
    path = files[-1] if version is None else directory / f"v{int(version):04d}.json"
    ledger = read_json(path)
    if ledger is None:
        raise ValueError("World version not found")
    return ledger


def listing(store):
    root = worlds_dir(store)
    names = [path.name for path in sorted(root.iterdir()) if path.is_dir() and not path.is_symlink() and _version_files(path)] if root.is_dir() else []
    return [summary(load(store, name)) for name in names]


def _write_version(store, ledger):
    directory = worlds_dir(store) / ledger["id"]
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    write_json(directory / f"v{ledger['version']:04d}.json", ledger, private=True)
    return ledger


def _with_sources(current, version, new_sources):
    added = [{"type": kind, "ref": ref, "added_in_version": version} for kind, ref in new_sources]
    return _sources(list(current) + added)


def create(store, world_id, raw, *, models=None, fit=False, new_sources=()):
    world_id = identifier(world_id)
    if world_id == "proposals":
        raise ValueError("That ID is reserved; choose a different one")
    if (worlds_dir(store) / world_id).exists():
        raise ValueError("World already exists; choose a different ID")
    ledger = {**normalize(raw, fit=fit), "id": world_id, "version": 1, "created": time.time(), "updated": time.time(),
              "models": models or {}}
    ledger["sources"] = _with_sources([], 1, new_sources)
    return _write_version(store, ledger)


def revise(store, world_id, raw, *, models=None, fit=False, new_sources=()):
    """The next version of an existing world; earlier versions stay."""
    current = load(store, world_id)
    ledger = {**normalize({**raw, "sources": current.get("sources", [])}, fit=fit), "id": current["id"],
              "version": current["version"] + 1, "created": current["created"], "updated": time.time(),
              "models": models or current.get("models", {})}
    ledger["sources"] = _with_sources(current.get("sources", []), ledger["version"], new_sources)
    return _write_version(store, ledger)


def rollback(store, world_id, version):
    old = load(store, world_id, version)
    current = load(store, world_id)
    if old["version"] == current["version"]:
        raise ValueError("That is already the current version")
    return _write_version(store, {**old, "version": current["version"] + 1, "updated": time.time()})


def delete(store, world_id):
    directory = _world_dir(store, world_id)
    if not directory.is_dir():
        raise ValueError("World not found")
    for path in directory.iterdir():
        if path.is_symlink() or not path.is_file():
            raise ValueError("Cannot delete a world containing linked files")
        path.unlink()
    directory.rmdir()


# ---------- proposals ----------

def proposal_path(store, proposal_id):
    return inside(proposals_dir(store), identifier(proposal_id) + ".json")


def read_proposal(store, proposal_id):
    proposal = read_json(proposal_path(store, proposal_id))
    if proposal is None:
        raise ValueError("Proposal not found")
    return proposal


def list_proposals(store):
    root = proposals_dir(store)
    return [{key: item[key] for key in ("id", "world_id", "mode", "base_version", "created", "changes")}
            for item in (read_json(path, {}) for path in sorted(root.glob("*.json"))) if item] if root.is_dir() else []


def write_proposal(store, proposal_id, world_id, mode, base_version, proposed, sources, models):
    base = load(store, world_id) if mode == "grow" else None
    record = {"id": proposal_id, "world_id": world_id, "mode": mode, "base_version": base_version,
              "proposed": proposed, "sources": [{"type": kind, "ref": ref} for kind, ref in sources], "models": models,
              "changes": diff(base, proposed), "created": time.time()}
    proposals_dir(store).mkdir(parents=True, exist_ok=True, mode=0o700)
    write_json(proposal_path(store, proposal_id), record, private=True)
    return record


def accept(store, proposal_id):
    proposal = read_proposal(store, proposal_id)
    sources = [(item["type"], item["ref"]) for item in proposal["sources"]]
    if proposal["mode"] == "create":
        ledger = create(store, proposal["world_id"], proposal["proposed"], models=proposal["models"], new_sources=sources)
    else:
        if load(store, proposal["world_id"])["version"] != proposal["base_version"]:
            raise ValueError("The world changed after this proposal was made. Harvest again to refresh it")
        ledger = revise(store, proposal["world_id"], proposal["proposed"], models=proposal["models"], new_sources=sources)
    proposal_path(store, proposal_id).unlink()
    return ledger


def reject(store, proposal_id):
    path = proposal_path(store, proposal_id)
    if not path.is_file():
        raise ValueError("Proposal not found")
    path.unlink()


# ---------- harvest sources ----------

def _upload(store, name, suffixes, label):
    path = inside(store.home / "uploads", name)
    if path.suffix.lower() not in suffixes or not path.is_file():
        raise ValueError(f"World {label} '{name}' is not an uploaded {label} file")
    return path


def run_video(directory):
    """A finished run's video, confined to its own folder."""
    output = read_json(directory / "output.json", {})
    name = output.get("file") if isinstance(output, dict) else None
    if not isinstance(name, str) or not name:
        raise ValueError("That run has no finished video to read")
    path = inside(directory, name)
    if not path.is_file():
        raise ValueError("That run has no finished video to read")
    return path


def resolve_sources(store, request):
    """{'images': [...], 'videos': [...], 'lore': [...], 'runs': [(id, directory)]} validated against the budgets."""
    images = [_upload(store, name, (".png",), "image") for name in request.get("world_images", [])]
    videos = [_upload(store, name, VIDEO_SUFFIXES, "video") for name in request.get("world_videos", [])]
    lore = [_upload(store, name, LORE_SUFFIXES, "lore") for name in request.get("world_lore", [])]
    runs = []
    for run_id in request.get("world_runs", []):
        directory = inside(store.home / "runs", identifier(run_id))
        run_video(directory)
        runs.append((run_id, directory))
    if not (images or videos or lore or runs):
        raise ValueError("Choose at least one image, video, lore file or finished run")
    if len(images) + KEYFRAMES_PER_VIDEO * len(videos) + KEYFRAMES_PER_RUN * len(runs) > MAX_IMAGES:
        raise ValueError(f"Too many sources: a harvest reads at most {MAX_IMAGES} images "
                         f"({KEYFRAMES_PER_VIDEO} per video, {KEYFRAMES_PER_RUN} per finished run)")
    if len(lore) > MAX_LORE_FILES or any(path.stat().st_size > LORE_BYTES for path in lore):
        raise ValueError(f"Lore text is limited to {MAX_LORE_FILES} files of {LORE_BYTES // 1024} KB each")
    return {"images": images, "videos": videos, "lore": lore, "runs": runs}


def source_labels(store, sources):
    def label(path):
        meta = read_json(path.with_name(path.name + ".metadata.json"), {}) or {}
        return meta.get("name") or path.name
    return ([("image", label(p)) for p in sources["images"]] + [("video", label(p)) for p in sources["videos"]] +
            [("lore", label(p)) for p in sources["lore"]] + [("run", run_id) for run_id, _ in sources["runs"]])


def keyframes(video, count, destination, tag):
    """`count` evenly spaced PNG frames from a video, using the ffmpeg this app already requires."""
    from . import media
    length = media.duration(video)
    if not length or length <= 0:
        raise ValueError("Could not read the video length")
    destination.mkdir(parents=True, exist_ok=True)
    frames = []
    for index in range(count):
        target = destination / f"{tag}-{index:02d}.png"
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{(index + .5) * length / count:.3f}", "-i", str(video),
                        "-frames:v", "1", "-vf", "scale='min(1024,iw)':-2", str(target)], check=True, timeout=120)
        if target.is_file():
            frames.append(target)
    if not frames:
        raise ValueError("Could not read frames from the video")
    return frames


def run_vocabulary(directory):
    """The vocabulary a finished run actually used, per table, from its saved plan."""
    plan = read_json(directory / "plan.json", {}) or {}
    used = {}
    for segment in plan.get("segments", []) if isinstance(plan, dict) else []:
        for shot in segment.get("shots", []):
            for key, value in (shot.get("vocab") or {}).items():
                if isinstance(value, str):
                    used.setdefault(key, [])
                    if value not in used[key]:
                        used[key].append(value)
    return {key: values[:40] for key, values in used.items()}


# ---------- model call ----------

def build_payload(sources, base, direction, frames):
    """Chat content: the prompt, optional current ledger, lore and run notes as text, then every image."""
    parts = [WORLD_HARVEST_PROMPT]
    if base:
        parts += [GROW_RULES, "CURRENT LEDGER:\n" + json.dumps({k: base[k] for k in (
            "name", "seed_sentence", "subjects", "pools", *LIST_FIELDS)}, ensure_ascii=False)]
    if direction.strip():
        parts.append("DIRECTION FROM THE OWNER:\n" + direction.strip())
    for path in sources["lore"]:
        parts.append(f"LORE TEXT ({path.name}):\n" + path.read_text(encoding="utf-8", errors="replace")[:LORE_BYTES])
    for run_id, directory in sources["runs"]:
        parts.append(f"A VIDEO ALREADY MADE IN THIS WORLD ({run_id}); what it used, by category:\n" +
                     json.dumps(run_vocabulary(directory), ensure_ascii=False))
    content = [{"type": "text", "text": "\n\n".join(parts)}]
    for path in frames:
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        content.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + data}})
    return content


def parse_response(text):
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("The model did not return a world")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        raise ValueError("The model returned a world that could not be read; try again") from None
    return normalize({**data, "id": ""}, fit=True)


def harvest(home, directory):
    """Worker entry: read the saved request, call the configured vision model, write a proposal. Never edits a world."""
    from .storage import Storage
    from .render import request_json
    store = Storage(home)
    request = read_json(directory / "request.json")
    prepared = read_json(directory / "prepared.json")
    settings = prepared["settings"]
    sources = resolve_sources(store, request)
    progress = lambda message, value: (print(message, flush=True),
                                       write_json(directory / "progress.json", {"message": message, "progress": value}))
    progress("Reading the references", 10)
    frames = list(sources["images"])
    for number, video in enumerate(sources["videos"]):
        frames += keyframes(video, KEYFRAMES_PER_VIDEO, directory / "frames", f"video{number}")
    for number, (_, run_directory) in enumerate(sources["runs"]):
        frames += keyframes(run_video(run_directory), KEYFRAMES_PER_RUN, directory / "frames", f"run{number}")
    mode, world_id = request["world_mode"], request["world_id"]
    base = load(store, world_id) if mode == "grow" else None
    progress("Asking the vision model to read the world", 30)
    try:
        response = request_json(settings["vision_url"].rstrip("/") + "/chat/completions",
                                {"model": settings["vision_model"], "temperature": .4, "max_tokens": 6000,
                                 "messages": [{"role": "user", "content": build_payload(
                                     sources, base, request.get("direction", ""), frames)}]},
                                key=store.key("MMV_VISION_API_KEY"), timeout=900)
        proposed = parse_response(response["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError):
        raise ValueError("The vision model returned an unexpected response") from None
    if mode == "create" and request.get("title", "").strip():
        proposed["name"] = request["title"].strip()[:160]
    progress("Preparing the proposal for your review", 90)
    write_proposal(store, directory.name, world_id, mode, base["version"] if base else 0, {**proposed, "id": world_id},
                   source_labels(store, sources), {"vision": settings["vision_model"]})
    write_json(directory / "result.json", {"proposal": directory.name, "world": world_id, "mode": mode})


if __name__ == "__main__":
    if sys.argv[1:2] != ["harvest"]:
        sys.exit(2)
    harvest(Path(sys.argv[2]), Path(sys.argv[3]))
