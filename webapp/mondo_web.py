"""Mondo Music Video: a focused public server, independent of the private studio."""
from __future__ import annotations

import math
import secrets
import time
import uuid
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import oap
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator

from mmv import actors, production
from mmv.jobs import BusyError, Jobs
from mmv.render import CATALOG
from mmv.storage import DEFAULTS, Storage, identifier, inside, read_json, write_json

MGL_APP_VERSION = "1.0.0"
WEB = Path(__file__).parent


def api_version():
    return {"name": "Mondo Music Video", "version": MGL_APP_VERSION}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ProductionRequest(StrictModel):
    kind: Literal["video", "ident", "harvest"] = "video"
    title: str = Field(default="", max_length=160)
    song: str = Field(default="", max_length=128)
    backend: Literal["local_h3", "wavespeed", "seedance_2", "seedance_2_5"] = "local_h3"
    resolution: Literal["480p", "720p", "768p", "1080p", "2k", "4k"] = "768p"
    aspect: Literal["16:9", "9:16", "1:1", "4:3", "3:4", "21:9"] = "16:9"
    direction: str = Field(default="", max_length=6000)
    style_id: str = Field(default="daylight", max_length=64)
    actors: list[str] = Field(default_factory=list, max_length=9)
    references: list[str] = Field(default_factory=list, max_length=9)
    content: dict[str, str] = Field(default_factory=lambda: {key: "none" for key in oap.CONTENT_ENUMS})
    beats_per_bar: int = Field(default=4, ge=2, le=12)
    bars_per_phrase: int = Field(default=8, ge=1, le=32)
    seed: int = Field(default=0, ge=0, le=2147483647)
    megapixels: float = Field(default=.6, ge=.15, le=4)
    conceptual_theme: str = Field(default="", max_length=2000)
    lyrics: str = Field(default="", max_length=16000)
    silent_mouths: bool = True
    ref_policy: Literal["fragmentation", "single_subject", "all"] = "all"
    casting_policy: Literal["random", "rotate", "section"] = "random"
    ensemble_mode: Literal["off", "always", "mixed"] = "off"
    on_screen: int = Field(default=1, ge=1, le=9)
    ident_mode: Literal["standard", "harvest", "scenographic"] = "standard"
    ident_seconds: float = Field(default=5, ge=4, le=12)
    start_ident: str = Field(default="", max_length=128)
    end_ident: str = Field(default="", max_length=128)

    @field_validator("content")
    @classmethod
    def valid_content(cls, value):
        if set(value) != set(oap.CONTENT_ENUMS) or any(value[k] not in levels for k, levels in oap.CONTENT_ENUMS.items()):
            raise ValueError("Choose a valid OAP content rating for each category")
        return value


class StartRequest(StrictModel):
    quote_id: str
    consent: bool = False


class Settings(StrictModel):
    backend: Literal["local_h3", "wavespeed", "seedance_2", "seedance_2_5"] = "local_h3"
    comfy_url: str = "http://127.0.0.1:8188"
    comfy_input: str = ""
    comfy_output: str = ""
    workflow_map_path: str = DEFAULTS["workflow_map_path"]
    writer_url: str = "http://127.0.0.1:8080/v1"
    writer_model: str = ""
    writer_mode: Literal["local", "api"] = "local"
    writer_call_estimate: float = Field(default=0, ge=0, le=100)
    writer_launch: str = ""
    writer_cwd: str = ""
    comfy_launch: str = ""
    comfy_cwd: str = ""
    laya_model_dir: str = ""
    laya_device: Literal["cpu", "cuda", "mps"] = "cuda"
    vision_url: str = "http://127.0.0.1:8080/v1"
    vision_model: str = ""
    vision_key_env: Literal["MMV_VISION_API_KEY"] = "MMV_VISION_API_KEY"
    vision_call_estimate: float = Field(default=0, ge=0, le=100)
    topaz_executable: str = ""
    topaz_models: str = ""

    @field_validator("writer_launch", "comfy_launch")
    @classmethod
    def valid_launch(cls, value):
        if value:
            import json
            try: command = json.loads(value)
            except (ValueError,TypeError): raise ValueError("Use a JSON array of command arguments")
            if not isinstance(command,list) or not command or any(not isinstance(x,str) or not x for x in command):
                raise ValueError("Use a nonempty JSON array of command arguments")
        return value

    @field_validator("comfy_url", "vision_url", "writer_url")
    @classmethod
    def valid_url(cls, value):
        url = urlparse(value)
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password:
            raise ValueError("Use an HTTP(S) service URL without embedded credentials")
        return value.rstrip("/")


class KeyRequest(StrictModel):
    name: Literal["WAVESPEED_API_KEY", "MMV_WRITER_API_KEY", "MMV_VISION_API_KEY"]
    value: str = Field(max_length=1000)


class StyleRequest(StrictModel):
    id: str
    name: str = Field(min_length=1, max_length=160)
    direction: str = Field(min_length=1, max_length=8000)


class UpscaleRequest(StrictModel):
    source: str
    model: str = Field(default="ahq-12", pattern=r"^[a-z][a-z0-9]*-\d+$")
    scale: Literal[2, 4] = 2


def create_app(home=None, *, test_hosts=False):
    store = Storage(home)
    jobs = Jobs(store)
    quotes = {}
    @asynccontextmanager
    async def lifespan(app):
        yield
        await asyncio.to_thread(jobs.shutdown)

    app = FastAPI(title="Mondo Music Video", version=MGL_APP_VERSION, lifespan=lifespan)
    app.state.store, app.state.jobs = store, jobs
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]"] +
                       (["testserver"] if test_hosts else []))

    @app.middleware("http")
    async def origin_guard(request: Request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
                return JSONResponse({"detail": "Cross-origin changes are not allowed"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' blob:; " \
            "media-src 'self' blob:; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        return response

    @app.exception_handler(ValueError)
    async def value_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409 if isinstance(exc, BusyError) else 400)

    @app.get("/")
    def index():
        return FileResponse(WEB / "index.html")

    @app.get("/app.js")
    def javascript():
        return FileResponse(WEB / "app.js", media_type="text/javascript")

    @app.get("/style.css")
    def css():
        return FileResponse(WEB / "style.css", media_type="text/css")

    app.get("/api/version")(api_version)

    @app.get("/api/status")
    def status():
        return jobs.status()

    @app.post("/api/cancel")
    def cancel():
        return jobs.cancel()

    @app.get("/api/catalog")
    def catalog():
        return {"backends": CATALOG, "ratings": oap.CONTENT_ENUMS, "price_checked": "2026-10-15",
                "oap_version": oap.OAP_VERSION}

    @app.get("/api/settings")
    def get_settings():
        return {"settings": store.settings(), "keys": {name: bool(store.key(name)) for name in
                ("WAVESPEED_API_KEY", "MMV_WRITER_API_KEY", "MMV_VISION_API_KEY")}}

    @app.put("/api/settings")
    def settings(value: Settings):
        with jobs.lock:
            jobs.require_idle()
            write_json(store.home / "settings.json", value.model_dump())
        return {"ok": True}

    @app.put("/api/key")
    def key(value: KeyRequest):
        with jobs.lock:
            jobs.require_idle()
            store.save_key(value.name, value.value)
        return {"configured": bool(store.key(value.name))}

    @app.post("/api/upload/{kind}")
    def upload(kind: Literal["song", "reference", "oap"], file: UploadFile = File(...)):
        limit = {"song": 256, "reference": 25, "oap": 128}[kind] * 1024 * 1024
        suffix = Path(file.filename or "").suffix.lower()
        if kind == "song" and suffix not in (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".aiff"):
            raise ValueError("Choose a supported audio file")
        name = uuid.uuid4().hex + (suffix if kind == "song" else ".png" if kind == "reference" else ".oap")
        target = store.home / "uploads" / name
        # Serialize mutations with operation startup so quoted inputs remain stable.
        with jobs.lock:
            jobs.require_idle()
            if kind == "reference":
                data = file.file.read(limit + 1)
                actors.clean_image(data, target)
            else:
                size = 0
                try:
                    with target.open("xb") as stream:
                        while chunk := file.file.read(1024 * 1024):
                            size += len(chunk)
                            if size > limit:
                                raise ValueError("File exceeds upload size limit")
                            stream.write(chunk)
                    if not size:
                        raise ValueError("File is empty")
                except Exception:
                    target.unlink(missing_ok=True)
                    raise
        return {"file": name, "name": file.filename}

    @app.get("/api/actors")
    def list_actors():
        return [read_json(path) for path in sorted((store.home / "actors").glob("*/actor.json"))]

    @app.post("/api/actors")
    def add_actor(actor_id: str = Form(...), name: str = Form(...), description: str = Form(""),
                  reference: UploadFile = File(...)):
        if len(name) > 160 or len(description) > 6000:
            raise ValueError("Actor name or description is too long")
        with jobs.lock:
            jobs.require_idle()
            return actors.create_actor(store, actor_id, name, description, reference.file.read(25 * 1024 * 1024 + 1))

    @app.get("/api/actors/{actor_id}/reference")
    def actor_reference(actor_id: str):
        record = store.actor(actor_id)
        if not record:
            raise ValueError("Actor not found")
        return FileResponse(inside(store.home / "actors" / actor_id, record["reference"]), media_type="image/png")

    @app.post("/api/actors/{actor_id}/export")
    def export_actor(actor_id: str):
        with jobs.lock:
            jobs.require_idle()
            path = actors.export_actor(store, actor_id)
        return FileResponse(path, filename=actor_id + ".oap", media_type="application/octet-stream")

    @app.get("/api/oap/inspect/{filename}")
    def inspect_package(filename: str, allow_unsigned: bool = False):
        path = inside(store.home / "uploads", filename)
        if path.suffix != ".oap" or not path.is_file():
            raise ValueError("OAP upload not found")
        manifest, verification = actors.package_info(path, allow_unsigned=allow_unsigned)
        return {"manifest": manifest, "verification": verification}

    @app.post("/api/oap/import")
    def import_package(filename: str = Form(...), actor_id: str = Form(""),
                       allow_unsigned: bool = Form(False), accept_unknown: bool = Form(False)):
        path = inside(store.home / "uploads", filename)
        if path.suffix != ".oap" or not path.is_file():
            raise ValueError("OAP upload not found")
        with jobs.lock:
            jobs.require_idle()
            return actors.import_actor(store, path, actor_id, allow_unsigned=allow_unsigned, accept_unknown=accept_unknown)

    @app.get("/api/styles")
    def styles():
        return [read_json(path) for path in sorted((store.home / "styles").glob("*.json"))]

    @app.post("/api/styles")
    def add_style(value: StyleRequest):
        path = store.home / "styles" / (identifier(value.id) + ".json")
        with jobs.lock:
            jobs.require_idle()
            if path.exists():
                raise ValueError("Style already exists; use a different ID")
            write_json(path, value.model_dump())
        return value.model_dump()

    @app.post("/api/quote")
    def quote(value: ProductionRequest):
        with jobs.lock:
            jobs.require_idle()
            request = value.model_dump()
            prepared = production.prepare(store, request)
            for expired in [key for key, item in quotes.items() if item["expires"] < time.time()]:
                quotes.pop(expired)
            if len(quotes) > 100:
                quotes.clear()
            quote_id = secrets.token_urlsafe(24)
            quotes[quote_id] = {"request": request, "fingerprint": production.fingerprint(store, request, prepared),
                                "expires": time.time() + 600}
            return {"id": quote_id, "estimate_usd": prepared["estimate"], "clips": len(prepared["segments"]),
                    "seconds": prepared["seconds"], "analysis": prepared.get("analysis"),
                    "segments": prepared["segments"], "writer_estimate_usd": prepared.get("writer_estimate", 0),
                    "paid": prepared["estimate"] > 0 if request["kind"] != "harvest"
                    else prepared["estimate"] > 0,
                    "note": "Estimate only. Check provider pricing. Uploaded references/audio are sent to your chosen provider. "
                    "Cancellation cannot undo charges for submitted work."}

    @app.post("/api/start")
    def start(value: StartRequest):
        with jobs.lock:
            jobs.require_idle()
            quoted = quotes.get(value.quote_id)
            if not quoted or quoted["expires"] < time.time():
                raise ValueError("Preview expired. Request a new preview")
            if not value.consent:
                raise ValueError("Review and accept the preview before starting")
            request = quoted["request"]
            prepared = production.prepare(store, request)
            if production.fingerprint(store, request, prepared) != quoted["fingerprint"]:
                raise ValueError("Inputs or settings changed. Request a new preview")
            prepared["consent"] = {"accepted": True, "accepted_at": time.time(),
                                   "estimate_usd": prepared["estimate"], "quote_id": value.quote_id,
                                   "fingerprint": quoted["fingerprint"]}
            quotes.pop(value.quote_id)
            return jobs.start(request["kind"], lambda context: production.produce(store, request, prepared, context))

    @app.get("/api/outputs")
    def outputs():
        result = []
        for path in sorted((store.home / "runs").glob("*/output.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            record = read_json(path)
            result.append({**record, "file": path.parent.name + "/" + record["file"]})
        return result

    @app.get("/api/media/{run_id}/{filename}")
    def media_file(run_id: str, filename: str, download: bool = False):
        directory = store.home / "runs" / identifier(run_id)
        record = read_json(directory / "output.json", {})
        if filename != record.get("file") or Path(filename).suffix != ".mp4":
            raise ValueError("Output not found")
        return FileResponse(inside(directory, filename), media_type="video/mp4", filename=filename if download else None)

    @app.get("/api/log/{run_id}")
    def operation_log(run_id: str):
        path = store.home / "runs" / identifier(run_id) / "operation.log"
        if not path.exists():
            return {"log": ""}
        with path.open("rb") as stream:
            stream.seek(max(0, path.stat().st_size - 32000))
            text = stream.read().decode(errors="replace")
        return {"log": text}

    @app.post("/api/upscale")
    def upscale(value: UpscaleRequest):
        with jobs.lock:
            jobs.require_idle()
            return jobs.start("upscale", lambda context: production.upscale(store, value.source, value.model, value.scale, context))

    return app
