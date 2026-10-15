"""Local ComfyUI and WaveSpeed render clients for the public edition."""
from __future__ import annotations

import copy
import json
import math
import mimetypes
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from .jobs import Cancelled
from .storage import inside, write_json

# Provider documentation checked 2026-10-15; estimates are displayed, not guarantees.
CATALOG = {
    "local_h3": {"name": "Local H3 / ComfyUI", "rates": {}, "resolutions": ["768p"]},
    "wavespeed": {"name": "WaveSpeed H3", "path": "minimax/h3/reference-to-video",
                  "rates": {"768p": .10, "2k": .14}, "resolutions": ["768p", "2k"]},
    "seedance_2": {"name": "Seedance 2.0 / WaveSpeed", "path": "bytedance/seedance-2.0/text-to-video",
                   "rates": {"480p": .12, "720p": .24, "1080p": .60, "4k": 1.20},
                   "resolutions": ["480p", "720p", "1080p", "4k"]},
    "seedance_2_5": {"name": "Seedance 2.5 / WaveSpeed", "path": "bytedance/seedance-2.5/text-to-video",
                     "rates": {"480p": .18, "720p": .36, "1080p": .90, "4k": 1.80},
                     "resolutions": ["480p", "720p", "1080p", "4k"]},
}
BASE = "https://api.wavespeed.ai/api/v3"


def request_json(url, body=None, *, key="", timeout=30, raw=None, content_type=None):
    headers = {"Accept": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    data = raw
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    elif content_type:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.load(response)
        if not isinstance(result, dict):
            raise ValueError("Service returned an unexpected response")
        return result
    except urllib.error.HTTPError as exc:
        # Provider error bodies may echo prompts or credentials. Keep them out of logs.
        raise ValueError(f"Service rejected the request (HTTP {exc.code}); check its settings/dashboard") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ValueError("Service connection failed or timed out. A submitted remote job may still run; "
                         "check its dashboard before trying again") from None
    except json.JSONDecodeError:
        raise ValueError("Service did not return JSON") from None


def download(url, destination, context):
    if urllib.parse.urlparse(url).scheme not in ("http", "https"):
        raise ValueError("Service returned an unsupported download URL")
    partial = destination.with_suffix(destination.suffix + ".partial")
    try:
        with urllib.request.urlopen(url, timeout=30) as response, partial.open("wb") as stream:
            while True:
                context.check()
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                stream.write(chunk)
        partial.replace(destination)
    except (urllib.error.URLError, TimeoutError):
        raise ValueError("Media download failed; the generated output may remain on the provider dashboard") from None


def upload(path, key, context):
    context.check()
    boundary = "mmv" + uuid.uuid4().hex
    filename = "reference" + path.suffix
    head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            f"filename=\"{filename}\"\r\nContent-Type: "
            f"{mimetypes.guess_type(filename)[0] or 'application/octet-stream'}\r\n\r\n").encode()
    data = head + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    result = request_json(BASE + "/media/upload/binary", key=key, raw=data,
                          content_type="multipart/form-data; boundary=" + boundary, timeout=120)
    result = result.get("data", result)
    url = result.get("download_url") or result.get("url")
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError("Upload returned no valid download URL")
    context.check()
    return url


def estimate(backend, resolution, segments, images):
    if backend == "local_h3":
        return 0.0
    card = CATALOG[backend]
    if resolution not in card["rates"]:
        raise ValueError("Unsupported resolution for this backend")
    surcharge = max(0, images - 5) * .05 if backend == "wavespeed" else 0
    return round(sum(s["duration"] * card["rates"][resolution] + surcharge for s in segments), 2)


def preflight(settings, backend, resolution, references, key):
    if backend not in CATALOG or resolution not in CATALOG[backend]["resolutions"]:
        raise ValueError("Choose a supported backend and resolution")
    if len(references) > 9:
        raise ValueError("Renderer supports at most nine actor/reference images")
    if backend == "local_h3":
        for name in ("workflow_path", "workflow_map_path"):
            if not settings[name] or not Path(settings[name]).expanduser().is_file():
                raise ValueError("Local rendering needs an API workflow and its public binding map in Settings")
        load_workflow(settings)
        if not settings["comfy_input"] or not Path(settings["comfy_input"]).expanduser().is_dir():
            raise ValueError("Choose your ComfyUI input directory in Settings")
    elif not key:
        raise ValueError("Set your WaveSpeed API key in Settings or WAVESPEED_API_KEY")
    if backend == "wavespeed" and not references:
        raise ValueError("WaveSpeed H3 needs at least one actor or reference image")


def load_workflow(settings):
    try:
        graph = json.loads(Path(settings["workflow_path"]).expanduser().read_text(encoding="utf-8"))
        mapping = json.loads(Path(settings["workflow_map_path"]).expanduser().read_text(encoding="utf-8"))
        for name in ("prompt", "duration", "width", "height", "seed", "video_prefix"):
            node, field = mapping["inputs"][name]
            if not isinstance(graph[str(node)]["inputs"], dict) or field not in graph[str(node)]["inputs"]:
                raise ValueError("Missing input binding")
        reference_node = graph[str(mapping["reference_node"])]["inputs"]
        if not isinstance(reference_node, dict):
            raise ValueError("Missing reference node")
        output = mapping["output_node"]
        if str(output) not in graph:
            raise ValueError("Missing output node")
        return graph, mapping
    except (KeyError, TypeError, OSError, ValueError) as exc:
        raise ValueError("Invalid local workflow or binding map; see docs/LOCAL_MODELS.md") from exc


class Renderer:
    def __init__(self, settings, backend, resolution, references, context, key=""):
        self.settings, self.backend, self.resolution = settings, backend, resolution
        self.references, self.context, self.key = references, context, key
        self.cache = {}
        self.requests = []
        self.directory = context.log_path.parent

    def render(self, prompt, segment, audio, width, height, index):
        self.context.check()
        if self.backend == "local_h3":
            return self.local(prompt, segment, audio, width, height, index)
        for path in [*self.references, audio]:
            if str(path) not in self.cache:
                self.cache[str(path)] = upload(path, self.key, self.context)
        payload = {"prompt": prompt, "duration": int(segment["duration"]),
                   "aspect_ratio": self.aspect, "resolution": self.resolution,
                   "reference_audios": [self.cache[str(audio)]]}
        if self.references:
            payload["reference_images"] = [self.cache[str(path)] for path in self.references]
        self.context.check()
        data = request_json(BASE + "/" + CATALOG[self.backend]["path"], payload, key=self.key, timeout=60)
        data = data.get("data", data)
        request_id = data.get("id")
        if not isinstance(request_id, str) or not request_id:
            raise ValueError("Submission returned no request ID. Check the provider dashboard before retrying")
        self.requests.append({"backend": self.backend, "id": request_id})
        write_json(self.directory / "requests.json", self.requests)
        self.context.update("Remote request accepted: " + request_id, requests=list(self.requests))
        deadline = time.monotonic() + 3600
        while time.monotonic() < deadline:
            self.context.check()
            data = request_json(BASE + "/predictions/" + urllib.parse.quote(request_id, safe="") + "/result",
                                key=self.key).get("data", {})
            status = data.get("status")
            if status == "completed":
                outputs = data.get("outputs") or []
                if not outputs or not isinstance(outputs[0], str):
                    raise ValueError("Remote job completed without a video output")
                destination = self.directory / f"generated-{index:04d}.mp4"
                download(outputs[0], destination, self.context)
                return destination
            if status in ("failed", "cancelled", "timeout", "deleted"):
                raise ValueError("Remote generation ended with status: " + status)
            self.context.wait(2)
        raise ValueError("Remote generation timed out; check saved request IDs before submitting again")

    def local(self, prompt, segment, audio, width, height, index):
        base = self.settings["comfy_url"].rstrip("/")
        graph, mapping = load_workflow(self.settings)

        def stage(path):
            filename = self.context.record["id"] + "-" + path.name
            destination = Path(self.settings["comfy_input"]).expanduser() / filename
            shutil.copyfile(path, destination)
            return filename

        values = {"prompt": prompt, "duration": segment["duration"], "width": width, "height": height,
                  "seed": int(uuid.uuid4().hex[:8], 16),
                  "video_prefix": "mmv/" + self.context.record["id"] + f"/clip-{index:04d}"}
        for name, value in values.items():
            node, field = mapping["inputs"][name]
            graph[str(node)]["inputs"][field] = value
        node = str(mapping["reference_node"])
        inputs = graph[node]["inputs"]
        for name in list(inputs):
            if name.startswith(("ref_images.ref_image_", "ref_audios.ref_audio_", "ref_videos.ref_video_")):
                del inputs[name]
        next_id = max([int(x) for x in graph if str(x).isdigit()] + [9000]) + 1
        for kind, paths, loader, field in (("images", self.references, "LoadImage", "image"),
                                            ("audios", [audio], "LoadAudio", "audio")):
            for slot, path in enumerate(paths):
                if str(path) not in self.cache:
                    self.cache[str(path)] = stage(path)
                reference_id = str(next_id)
                next_id += 1
                graph[reference_id] = {"class_type": loader, "inputs": {field: self.cache[str(path)]}}
                singular = "image" if kind == "images" else "audio"
                inputs[f"ref_{kind}.ref_{singular}_{slot}"] = [reference_id, 0]
        self.context.check()
        response = request_json(base + "/prompt", {"prompt": graph, "client_id": self.context.record["id"]})
        prompt_id = response.get("prompt_id")
        if not prompt_id or response.get("node_errors"):
            raise ValueError("ComfyUI rejected the workflow; check installed nodes and models")
        self.requests.append({"backend": "local_h3", "id": prompt_id})
        write_json(self.directory / "requests.json", self.requests)
        self.context.update("Local generation accepted: " + prompt_id, requests=list(self.requests))
        deadline = time.monotonic() + 7200
        try:
            while time.monotonic() < deadline:
                self.context.check()
                history = request_json(base + "/history/" + urllib.parse.quote(prompt_id, safe=""))
                if prompt_id in history:
                    entry = history[prompt_id]
                    if entry.get("status", {}).get("status_str") == "error":
                        raise ValueError("ComfyUI generation failed; check its console")
                    output = entry.get("outputs", {}).get(str(mapping["output_node"]), {})
                    videos = output.get("gifs") or output.get("videos") or output.get("images") or []
                    if not videos:
                        raise ValueError("Local workflow returned no video from its configured output node")
                    video = videos[0]
                    query = urllib.parse.urlencode({key: video.get(key, "") for key in ("filename", "subfolder", "type")})
                    destination = self.directory / f"generated-{index:04d}.mp4"
                    download(base + "/view?" + query, destination, self.context)
                    return destination
                self.context.wait(2)
        except Cancelled:
            # Delete only our pending submission; global /interrupt could stop someone else's work.
            request_json(base + "/queue", {"delete": [prompt_id]})
            raise
        raise ValueError("Local rendering timed out. Inspect ComfyUI before starting another generation")
