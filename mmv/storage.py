"""Portable application data and atomic records. No studio imports."""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path


def default_home() -> Path:
    if os.environ.get("MMV_HOME"):
        return Path(os.environ["MMV_HOME"]).expanduser().resolve()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library/Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return base / "mondo-music-video"


def write_json(path: Path, value, *, private=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".mmv-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600 if private else 0o644) if hasattr(os, "fchmod") else None
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(10):
            try:
                os.replace(name, path)
                break
            except PermissionError:
                if attempt == 9 or os.name != "nt":
                    raise
                time.sleep(0.02)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    for attempt in range(10):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except PermissionError:
            if attempt == 9 or os.name != "nt":
                raise
            time.sleep(0.02)
    return default


def identifier(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value):
        raise ValueError("Use 1–64 lowercase letters, numbers, underscores or hyphens")
    return value


def inside(root: Path, relative: str) -> Path:
    result = (root / relative).resolve()
    if not result.is_relative_to(root.resolve()) or result == root.resolve():
        raise ValueError("Path is outside its data directory")
    return result


DEFAULT_STYLE = {
    "id": "daylight", "name": "Daylight Cinema",
    "direction": "Expressive music-video photography, natural light, rich color, "
                 "clear compositions and rhythmic movement. Fully clothed subjects; "
                 "no nudity, sexual imagery, blood or violence.",
}

DEFAULTS = {
    "backend": "local_h3", "comfy_url": "http://127.0.0.1:8188",
    "workflow_map_path": str(Path(__file__).parent / "engine/config/injection_map.json"),
    "comfy_input": "", "comfy_output": "", "comfy_sdk_url": "http://127.0.0.1:8189",
    "writer_url": "http://127.0.0.1:8080/v1", "writer_model": "", "writer_mode": "local", "writer_call_estimate": 0.0,
    "writer_launch": "", "writer_cwd": "", "comfy_launch": "", "comfy_cwd": "",
    "laya_model_dir": "", "laya_device": "cuda",
    "vision_url": "http://127.0.0.1:8080/v1", "vision_model": "",
    "vision_key_env": "MMV_VISION_API_KEY", "vision_call_estimate": 0.0,
    "topaz_executable": "", "topaz_models": "",
}


class Storage:
    def __init__(self, home=None):
        self.home = Path(home or default_home()).resolve()
        for name in ("actors", "styles", "uploads", "runs", "exports", "models", "cache"):
            (self.home / name).mkdir(parents=True, exist_ok=True)
        if not (self.home / "styles/daylight.json").exists():
            write_json(self.home / "styles/daylight.json", DEFAULT_STYLE)

    def settings(self):
        settings = {**DEFAULTS, **{k:v for k,v in read_json(self.home / "settings.json", {}).items() if k in DEFAULTS}}
        if not settings["workflow_map_path"] or not Path(settings["workflow_map_path"]).is_file():
            settings["workflow_map_path"] = DEFAULTS["workflow_map_path"]
        if not settings["laya_model_dir"]:
            settings["laya_model_dir"] = str(self.home / "models/laya")
        return settings

    def key(self, name="WAVESPEED_API_KEY"):
        return os.environ.get(name) or read_json(self.home / "secrets.json", {}).get(name, "")

    def save_key(self, name, value):
        if name not in ("WAVESPEED_API_KEY", "MMV_WRITER_API_KEY", "MMV_VISION_API_KEY", "MMV_COMFY_API_KEY"):
            raise ValueError("Unknown credential")
        secrets = read_json(self.home / "secrets.json", {})
        if value:
            secrets[name] = value
        else:
            secrets.pop(name, None)
        write_json(self.home / "secrets.json", secrets, private=True)

    def actor(self, actor_id):
        return read_json(self.home / "actors" / identifier(actor_id) / "actor.json")

    def style(self, style_id):
        result = read_json(self.home / "styles" / (identifier(style_id) + ".json"))
        if result is None:
            raise ValueError("Style not found")
        return result
