"""Public production paths: song, visual direction, clips, and a final video."""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

from . import actors, media
from .render import Renderer, estimate, preflight, request_json
from .storage import identifier, inside, write_json


def dimensions(aspect):
    return {"16:9": (1280, 720), "9:16": (720, 1280), "1:1": (960, 960),
            "4:3": (1152, 864), "3:4": (864, 1152), "21:9": (1344, 576)}[aspect]


def references(store, request):
    refs, descriptions = actors.check_cast(store, request.get("actors", []), request["content"])
    for image in request.get("references", []):
        path = inside(store.home / "uploads", image)
        if path.suffix != ".png" or not path.is_file():
            raise ValueError("Reference image not found")
        refs.append(path)
    return refs, descriptions


def prepare(store, request):
    if not shutil.which("ffmpeg"):
        raise ValueError("FFmpeg is missing. Run the setup doctor")
    settings = store.settings()
    kind = request["kind"]
    if kind == "harvest":
        if not settings["vision_model"]:
            raise ValueError("Configure your vision service model in Settings before harvesting")
        if not request.get("references"):
            raise ValueError("Choose reference images to harvest")
        for image in request["references"]:
            path = inside(store.home / "uploads", image)
            if path.suffix != ".png" or not path.exists():
                raise ValueError("Harvest reference image missing")
        identifier(request["style_id"])
        if (store.home / "styles" / (request["style_id"] + ".json")).exists():
            raise ValueError("That style ID already exists")
        return {"settings": settings, "segments": [], "estimate": settings["vision_call_estimate"],
                "seconds": 0, "references": [], "descriptions": []}
    refs, descriptions = references(store, request)
    preflight(settings, request["backend"], request["resolution"], refs, store.key())
    if kind == "video":
        song = inside(store.home / "uploads", request["song"])
        if not song.is_file():
            raise ValueError("Upload a song first")
        seconds = media.duration(song)
        if seconds > 3600:
            raise ValueError("Songs must be under one hour")
        style = store.style(request["style_id"])
        for name in ("start_ident", "end_ident"):
            if request.get(name):
                ident = inside(store.home / "runs", request[name])
                if ident.name != "ident.mp4" or not ident.is_file():
                    raise ValueError("Choose a completed ident")
    else:
        seconds, style = request["ident_seconds"], store.style(request["style_id"])
    segments = media.plan(seconds, request["backend"],
                          seconds if kind == "ident" else request["segment_seconds"],
                          request.get("bpm") if kind == "video" else None)
    return {"settings": settings, "segments": segments, "style": style,
            "estimate": estimate(request["backend"], request["resolution"], segments, len(refs)),
            "references": refs, "descriptions": descriptions, "seconds": seconds}


def fingerprint(store, request, prepared):
    digest = hashlib.sha256(json.dumps({"request": request, "settings": prepared["settings"],
                                       "style": prepared.get("style")}, sort_keys=True).encode())
    files = list(prepared["references"])
    for actor_id in request.get("actors", []):
        digest.update(json.dumps(store.actor(actor_id), sort_keys=True).encode())
    for name in ("song",):
        if request.get(name):
            files.append(inside(store.home / "uploads", request[name]))
    if request["kind"] == "harvest":
        files.extend(inside(store.home / "uploads", x) for x in request["references"])
    for name in ("start_ident", "end_ident"):
        if request.get(name):
            files.append(inside(store.home / "runs", request[name]))
    if request["backend"] == "local_h3" and request["kind"] != "harvest":
        files.extend(Path(prepared["settings"][name]).expanduser() for name in ("workflow_path", "workflow_map_path"))
    for path in files:
        digest.update(str(path).encode())
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def produce(store, request, prepared, context):
    directory = context.log_path.parent
    write_json(directory / "request.json", request)
    write_json(directory / "consent.json", prepared["consent"])
    if request["kind"] == "harvest":
        content = [{"type": "text", "text": "Describe the visual style of these references for a music video. "
                   "Discuss palette, lighting, texture, composition, camera and movement. "
                   "Do not identify people. Return only a reusable style description, under 400 words."}]
        for image in request["references"]:
            encoded = base64.b64encode(inside(store.home / "uploads", image).read_bytes()).decode()
            content.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + encoded}})
        settings = prepared["settings"]
        context.update("Reading visual references", 10)
        response = request_json(settings["vision_url"].rstrip("/") + "/chat/completions",
                                {"model": settings["vision_model"], "messages": [{"role": "user", "content": content}],
                                 "max_tokens": 700, "temperature": .4},
                                key=store.key(settings["vision_key_env"]), timeout=180)
        context.check()
        try:
            direction = response["choices"][0]["message"]["content"].strip()
            if not direction:
                raise ValueError("Empty vision response")
        except (KeyError, IndexError, AttributeError) as exc:
            raise ValueError("Vision service returned no style description") from exc
        style = {"id": request["style_id"], "name": request["title"] or request["style_id"], "direction": direction[:8000]}
        write_json(store.home / "styles" / (request["style_id"] + ".json"), style)
        return {"style": style["id"]}
    renderer = Renderer(prepared["settings"], request["backend"], request["resolution"],
                        prepared["references"], context, key=store.key())
    renderer.aspect = request["aspect"]
    width, height = dimensions(request["aspect"])
    song = directory / "silence.wav" if request["kind"] == "ident" else inside(store.home / "uploads", request["song"])
    if request["kind"] == "ident":
        context.command(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i",
                         "anullsrc=r=44100:cl=stereo", "-t", str(prepared["seconds"]), song])
    clips, prompts = [], []
    movements = ["Wide establishing composition, gentle lateral camera movement.",
                 "Medium view, expressive subject movement, camera slowly approaches.",
                 "Close detail, shallow depth of field, restrained camera motion.",
                 "Wide view, moving camera revealing the environment."]
    for index, segment in enumerate(prepared["segments"]):
        context.check()
        context.update(f"Generating clip {index + 1} of {len(prepared['segments'])}",
                       5 + int(75 * index / len(prepared["segments"])))
        audio = directory / f"audio-{index:04d}.wav"
        media.slice_song(context, song, audio, segment["start"], segment["gen_frames"] / 24)
        prompt = "\n".join([request["direction"], prepared["style"]["direction"],
                            *prepared["descriptions"], movements[index % len(movements)],
                            "Follow the rhythm of the reference audio. No dialogue or lip sync.",
                            "Content limits: " + json.dumps(request["content"])])
        if prepared["references"]:
            prompt += "\n" + " ".join(f"<Picture {i+1}> preserves that subject's appearance."
                                       for i in range(len(prepared["references"])))
        prompt += "\n<Audio 1> provides the rhythm."
        if request["kind"] == "ident":
            prompt += "\nAnimated production ident. Display this title: " + request["title"]
        if request["backend"].startswith("seedance"):
            prompt = re.sub(r"<Picture (\d+)>", r"@Image \1", prompt).replace("<Audio 1>", "@Audio 1")
        prompts.append(prompt)
        write_json(directory / "prompts.json", prompts)
        clips.append(renderer.render(prompt, segment, audio, width, height, index))
    context.update("Assembling final video", 85)
    if request["kind"] == "ident":
        output = directory / "ident.mp4"
        context.command(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", clips[0],
                         "-t", str(prepared["seconds"]), "-an", "-c:v", "libx264", "-crf", "18",
                         "-pix_fmt", "yuv420p", "-movflags", "+faststart", output])
    else:
        output = media.assemble(context, clips, prepared["segments"], song, directory, width, height,
                                start_ident=inside(store.home / "runs", request["start_ident"]) if request.get("start_ident") else None,
                                end_ident=inside(store.home / "runs", request["end_ident"]) if request.get("end_ident") else None)
    measured = media.duration(output)
    write_json(directory / "output.json", {"file": output.name, "duration": measured, "kind": request["kind"],
                                            "title": request["title"] or output.stem})
    return {"file": context.record["id"] + "/" + output.name, "duration": measured}


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
