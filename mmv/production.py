"""Music-video pipeline and optional Topaz export (installed program or Topaz cloud API)."""
import os, re, subprocess
from pathlib import Path
from . import media, topaz_api, topaz_models
from .pipeline import prepare, prepare_resume, fingerprint, produce
from .storage import inside, write_json

def completed_output(store, source):
    path = inside(store.home / "runs", source)
    if not path.is_file() or path.suffix != ".mp4":
        raise ValueError("Completed video not found")
    from .storage import read_json
    if read_json(path.parent / "output.json", {}).get("file") != path.name:
        raise ValueError("Choose a completed output for upscale")
    return path


def finish_upscale(destination, source, context):
    measured = media.duration(destination)
    write_json(destination.parent / "output.json", {"file": destination.name, "duration": measured,
               "kind": "upscale", "title": "Topaz upscale", "source": source})
    return {"file": context.record["id"] + "/" + destination.name, "duration": measured}


def check_choice(model, scale, cloud=False):
    if cloud and model == "none":
        return
    if not re.fullmatch(r"[a-z][a-z0-9]*-\d+(\.\d+)?", model) or scale not in ((1, 2, 4) if cloud else (2, 4)):
        raise ValueError("Choose a Topaz model ID and scale 2 or 4" + (" (1 to only enhance)" if cloud else ""))


def cloud_key(store):
    key = store.key("MMV_TOPAZ_API_KEY")
    if not key:
        raise ValueError("Save a Topaz API key in Settings (MMV_TOPAZ_API_KEY) to use the Topaz cloud")
    return key


def upscale_models(send=None):
    """The model catalog, narrowed to what Topaz accepts right now when its public status list is reachable."""
    send = send or topaz_api.send_http
    return topaz_models.catalog(topaz_api.live_models(send, topaz_api.API_URL))


def upscale_estimate(store, source, model, scale, options=None, send=None):
    """Free: ask Topaz to price the job. Nothing is reserved or processed."""
    check_choice(model, scale, cloud=True)
    info = media.video_info(completed_output(store, source))
    return topaz_api.estimate(send or topaz_api.send_http, topaz_api.API_URL, cloud_key(store), info, model, scale, options)


def upscale(store, source, model, scale, context, max_credits=None, send=None, fetch=None, options=None):
    cloud = store.settings().get("topaz_backend") == "cloud"
    check_choice(model, scale, cloud)
    if cloud:
        return upscale_cloud(store, source, model, scale, context, max_credits, send, fetch, options)
    if options:
        raise ValueError("Frame rate and tuning options need the Topaz cloud service")
    return upscale_local(store, source, model, scale, context)


def upscale_cloud(store, source, model, scale, context, max_credits, send, fetch, options=None):
    if not max_credits or max_credits <= 0:
        raise ValueError("Topaz cloud credits are paid: get an estimate and approve it first")
    path, key = completed_output(store, source), cloud_key(store)
    destination = context.log_path.parent / "upscaled.mp4"
    limit = float(store.settings().get("render_timeout_minutes") or 0) * 60
    topaz_api.run(send or topaz_api.send_http, fetch or topaz_api.download_http, topaz_api.API_URL, key, path, destination, media.video_info(path), model, scale,
                  max_credits, context, limit=limit, options=options)
    return finish_upscale(destination, source, context)


def upscale_local(store, source, model, scale, context):
    settings = store.settings()
    executable = Path(settings["topaz_executable"]).expanduser()
    if not executable.is_file():
        raise ValueError("Configure the installed Topaz FFmpeg executable in Settings")
    models = Path(settings["topaz_models"]).expanduser()
    if not (models / (model + ".json")).is_file():
        raise ValueError("Topaz model is not installed in the configured model directory")
    path = completed_output(store, source)
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
    return finish_upscale(destination, source, context)
