"""Portable setup, environment checks and verified opt-in model downloads."""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from .storage import Storage, default_home, inside, write_json


def doctor(store):
    settings = store.settings()
    import importlib.util
    report = {"platform": platform.system(), "architecture": platform.machine(),
              "python": platform.python_version(), "data_directory": str(store.home),
              "ffmpeg": shutil.which("ffmpeg"), "ffprobe": shutil.which("ffprobe"),
              "local_workflow_configured": bool(settings["workflow_map_path"]),
              "comfy_sdk_installed": importlib.util.find_spec("comfy_sdk") is not None,
              "comfy_sdk_url": settings["comfy_sdk_url"],
              "comfy_input": settings["comfy_input"], "comfy_output": settings["comfy_output"],
              "writer_configured": bool(settings["writer_model"]), "writer_launch_configured": bool(settings["writer_launch"]),
              "laya_model_directory": settings["laya_model_dir"], "laya_device": settings["laya_device"],
              "laya_files_present": all((Path(settings["laya_model_dir"]) / name).exists() for name in
                 ("model.safetensors", "rl_agent_config.json", "tokenizer/tokenizer.json", "encoder/config.json")), "api_key_configured": bool(store.key()),
              "topaz_configured": bool(settings["topaz_executable"])}
    gpu = shutil.which("nvidia-smi")
    if gpu:
        try:
            result = subprocess.run([gpu, "--query-gpu=name,memory.total", "--format=csv,noheader"],
                                    capture_output=True, text=True, timeout=10)
            report["nvidia_gpu"] = result.stdout.strip() if result.returncode == 0 else "Detection unavailable"
        except (OSError, subprocess.TimeoutExpired):
            report["nvidia_gpu"] = "Detection unavailable"
    report["support"] = "OS detection only; consult docs/PLATFORMS.md for verified capabilities"
    return report


def configure_standard_graph(store, settings, ask):
    engine = Path(__file__).parent / "engine"
    directory = store.home / "config"
    directory.mkdir(exist_ok=True)
    graph_path = directory / "h3-standard.json"
    graph = json.loads(graph_path.read_text() if graph_path.exists() else (engine / "workflows/h3_ref2video_audionodeadded.json").read_text())
    comfy_dir = Path(settings["comfy_input"]).expanduser().parent
    for node_id, folder, field, label in (
        ("119", "vae", "vae_name", "H3 video VAE filename"),
        ("120", "vae", "vae_name", "H3 audio VAE filename"),
        ("127", "diffusion_models", "unet_name", "H3 reference-to-video model filename"),
        ("128", "text_encoders", "clip_name", "H3 text encoder filename"),
    ):
        current = graph[node_id]["inputs"][field]
        model_dir = comfy_dir / "models" / folder
        if not (model_dir / current).is_file():
            found = sorted(str(x.relative_to(model_dir)) for x in model_dir.rglob("*.safetensors")) if model_dir.is_dir() else []
            if found: print(label + " — installed: " + ", ".join(found[:15]))
        graph[node_id]["inputs"][field] = ask(label, current)
    write_json(graph_path, graph)
    mapping = json.loads((engine / "config/injection_map.json").read_text())
    mapping["workflow"] = str(graph_path)
    map_path = directory / "h3-injection-map.json"
    write_json(map_path, mapping)
    settings["workflow_map_path"] = str(map_path)


def configure(store):
    settings = store.settings()
    print("Mondo Music Video setup — no models or actors are bundled.")
    print("Data directory:", store.home)

    def ask(label, old=""):
        answer = input(f"{label} [{old}]: ").strip()
        return answer or old

    choices = ("local_h3", "comfy_sdk_h3", "wavespeed", "seedance_2", "seedance_2_5")
    backend = ask("Default renderer (local_h3, comfy_sdk_h3, wavespeed, seedance_2, seedance_2_5)", settings["backend"])
    if backend not in choices:
        raise ValueError("Unknown renderer")
    settings["backend"] = backend
    if backend == "local_h3":
        settings["comfy_url"] = ask("ComfyUI service URL", settings["comfy_url"])
        candidates = [Path.home() / "ComfyUI/input", Path.home() / "Documents/ComfyUI/input"]
        detected = next((str(x) for x in candidates if x.is_dir()), "")
        settings["comfy_input"] = ask("ComfyUI input folder", settings["comfy_input"] or detected)
        settings["comfy_output"] = ask("ComfyUI output folder", settings["comfy_output"] or str(Path(settings["comfy_input"]).parent / "output"))
        configure_standard_graph(store, settings, ask)
        comfy_dir = str(Path(settings["comfy_input"]).expanduser().parent)
        comfy_python = ask("Python executable for your existing ComfyUI installation (blank: manage service yourself)")
        if comfy_python:
            settings["comfy_launch"] = json.dumps([comfy_python, "main.py"])
            settings["comfy_cwd"] = comfy_dir
    elif backend == "comfy_sdk_h3":
        from .comfy_sdk import require_sdk, validate_proxy_url
        require_sdk()
        settings["comfy_sdk_url"] = validate_proxy_url(ask("Local Comfy API proxy URL", settings["comfy_sdk_url"]))
        token = getpass.getpass("Proxy bearer token (blank keeps existing token): ").strip()
        if token:
            store.save_key("MMV_COMFY_API_KEY", token)
        configure_standard_graph(store, settings, ask)
    else:
        key = getpass.getpass("WaveSpeed API key (blank keeps an existing key): ").strip()
        if key:
            store.save_key("WAVESPEED_API_KEY", key)
    settings["laya_model_dir"] = ask("Laya model folder (model.safetensors, config, tokenizer, encoder)", settings["laya_model_dir"])
    import torch
    detected_device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
    settings["laya_device"] = ask("Laya device (cuda, mps, cpu)", detected_device)
    settings["writer_url"] = ask("Music-video writer service URL (/v1)", settings["writer_url"])
    settings["writer_model"] = ask("Music-video writer model name", settings["writer_model"])
    settings["writer_mode"] = ask("Writer service type (local or api)", settings["writer_mode"])
    if settings["writer_mode"] == "local":
        executable = ask("llama-server executable (blank: manage service yourself)")
        if executable:
            model_path = ask("Writer GGUF path")
            url = urllib.parse.urlparse(settings["writer_url"])
            port = url.port or 8080
            settings["writer_launch"] = json.dumps([executable, "-m", model_path, "--alias", settings["writer_model"],
                "-ngl", "all", "-np", "1", "-fa", "on", "--cache-type-k", "q4_0", "--cache-type-v", "q4_0",
                "--jinja", "--no-context-shift", "--port", str(port), "-c", "65536", "--reasoning", "off", "--temp", "0.7"])
    if settings["writer_mode"] == "api":
        settings["writer_call_estimate"] = float(ask("Estimated writer cost per call, USD", str(settings["writer_call_estimate"])))
        key = getpass.getpass("Writer API key (blank keeps existing): ").strip()
        if key: store.save_key("MMV_WRITER_API_KEY", key)
    settings["vision_url"] = ask("Optional OpenAI-compatible vision service URL", settings["vision_url"])
    settings["vision_model"] = ask("Vision model name (blank until configured)", settings["vision_model"])
    # Use the same validation as the web configuration; nothing launches services here.
    from webapp.mondo_web import Settings
    write_json(store.home / "settings.json", Settings(**settings).model_dump())
    if not doctor(store)["laya_files_present"] and ask("Download the pinned Laya files after reviewing their terms? (yes/no)", "no").lower() == "yes":
        download_models(store, Path(__file__).parent / "engine/config/laya-download.json")
    print(json.dumps(doctor(store), indent=2))
    print("Start with: mondo-music-video serve")


def download_models(store, manifest_path):
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    entries = manifest.get("models")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Manifest needs a nonempty models list")
    # Validate every entry before any request or download.
    for entry in entries:
        if not isinstance(entry, dict) or not all(entry.get(x) for x in ("name", "url", "sha256", "destination", "license_url")):
            raise ValueError("Each model needs name, HTTPS URL, SHA-256, destination and license URL")
        if not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            raise ValueError("Model needs a full lowercase SHA-256 digest")
        if any(urllib.parse.urlparse(entry[x]).scheme != "https" for x in ("url", "license_url")):
            raise ValueError("Model and license URLs must use HTTPS")
        inside(store.home / "models", entry["destination"])
    for entry in entries:
        target = inside(store.home / "models", entry["destination"])
        print(f"\nModel: {entry['name']}\nSource: {entry['url']}\nLicense: {entry['license_url']}\nDestination: {target}")
        print("Download size:", entry.get("size_bytes", "not specified; confirm at the source"))
        if input("Have you reviewed the terms and do you want this download? Type yes: ").strip().lower() != "yes":
            print("Skipped")
            continue
        if target.exists():
            raise ValueError("Destination already exists; existing models are never overwritten")
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(target.suffix + ".partial")
        if partial.exists():
            raise ValueError("A partial download exists. Inspect/remove it before retrying")
        digest, size = hashlib.sha256(), 0
        with urllib.request.urlopen(entry["url"], timeout=30) as response, partial.open("xb") as stream:
            if urllib.parse.urlparse(response.url).scheme != "https":
                raise ValueError("Download redirected outside HTTPS")
            while chunk := response.read(1024 * 1024):
                stream.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        if digest.hexdigest() != entry["sha256"] or (entry.get("size_bytes") is not None and size != entry["size_bytes"]):
            raise ValueError("Download integrity check failed. Partial file retained; model was not activated")
        partial.rename(target)
        print("Verified download:", target)


class SessionLock:
    """Prevent two launcher instances from operating on the same data directory."""
    def __init__(self, home):
        self.path = home / "session.lock"
        self.stream = None

    def __enter__(self):
        self.stream = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self.stream.seek(0)
                if not self.stream.read(1):
                    self.stream.write(b"0")
                    self.stream.flush()
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            raise ValueError("Mondo Music Video is already using this data directory") from None
        return self

    def __exit__(self, *args):
        self.stream.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Mondo Music Video setup and launcher")
    parser.add_argument("--data-dir", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("configure")
    sub.add_parser("doctor")
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8091)
    sub.add_parser("download-laya")
    models = sub.add_parser("download-models")
    models.add_argument("manifest")
    args = parser.parse_args(argv)
    store = Storage(args.data_dir)
    try:
        if args.command == "doctor":
            print(json.dumps(doctor(store), indent=2))
        else:
            with SessionLock(store.home):
                if args.command == "configure":
                    configure(store)
                elif args.command == "download-laya":
                    download_models(store, Path(__file__).parent / "engine/config/laya-download.json")
                elif args.command == "download-models":
                    download_models(store, args.manifest)
                elif args.command == "serve":
                    import uvicorn
                    from webapp.mondo_web import create_app
                    uvicorn.run(create_app(store.home), host="127.0.0.1", port=args.port, workers=1)
    except (ValueError, OSError) as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
