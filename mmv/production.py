"""Music-video pipeline and optional installed Topaz export."""
import os, re, subprocess
from pathlib import Path
from . import media
from .pipeline import prepare, fingerprint, produce
from .storage import inside, write_json

def upscale(store, source, model, scale, context):
    if not re.fullmatch(r"[a-z][a-z0-9]*-\d+", model) or scale not in (2, 4):
        raise ValueError("Choose a Topaz model ID and scale 2 or 4")
    settings = store.settings()
    executable = Path(settings["topaz_executable"]).expanduser()
    if not executable.is_file():
        raise ValueError("Configure the installed Topaz FFmpeg executable in Settings")
    models = Path(settings["topaz_models"]).expanduser()
    if not (models / (model + ".json")).is_file():
        raise ValueError("Topaz model is not installed in the configured model directory")
    path = inside(store.home / "runs", source)
    if not path.is_file() or path.suffix != ".mp4":
        raise ValueError("Completed video not found")
    from .storage import read_json
    if read_json(path.parent / "output.json", {}).get("file") != path.name:
        raise ValueError("Choose a completed output for upscale")
    destination = context.log_path.parent / "upscaled.mp4"
    convert = lambda p: str(p)
    env = os.environ.copy()
    if str(executable).lower().endswith(".exe") and os.name != "nt":
        def convert(p):
            return subprocess.run(["wslpath", "-w", str(p)], check=True, capture_output=True,
                                  text=True, timeout=10).stdout.strip()
        env["WSLENV"] = ":".join(filter(None, [env.get("WSLENV", ""), "TVAI_MODEL_DIR", "TVAI_MODEL_DATA_DIR"]))
    env["TVAI_MODEL_DIR"] = convert(models)
    env["TVAI_MODEL_DATA_DIR"] = convert(models)
    context.update("Upscaling finished video", 10)
    context.command([executable, "-nostdin", "-n", "-i", convert(path), "-map", "0:v:0", "-map", "0:a?",
                     "-vf", f"tvai_up=model={model}:scale={scale}:device=0:download=1", "-c:v", "libx264",
                     "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart",
                     convert(destination)], env=env)
    measured = media.duration(destination)
    write_json(destination.parent / "output.json", {"file": destination.name, "duration": measured,
               "kind": "upscale", "title": "Topaz upscale", "source": source})
    return {"file": context.record["id"] + "/" + destination.name, "duration": measured}
