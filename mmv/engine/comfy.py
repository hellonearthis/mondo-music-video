"""
ComfyUI workflow construction and job submission.

We never synthesize a graph from scratch. You export a known-good API-format
workflow from your own install; this module does targeted parameter injection
into it via config/injection_map.json. When Comfy updates a node, you
re-export and edit the map — no code changes.

The one structural thing it does do is add and remove reference loaders,
because montage Type 1 needs one image and Types 2/3 need none, and a dangling
`ref_images.ref_image_0` socket pointed at a stale file is worse than absent.

Reference tag numbering is computed, never assumed. H3 presents references in
a fixed order — images, then videos (each soundtrack's <Audio j> emitted just
ahead of its <Video k>), then standalone audio — so wiring a reference video
later silently renumbers your music from <Audio 1> to <Audio 2>. Nothing
errors; it just generates against the wrong sound. So the tag map comes out of
this module and goes into the prompt, rather than being written by hand.
"""
from __future__ import annotations

import copy
import json
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RefTags:
    """Resolved 1-based prompt tags for the references actually wired."""
    images: list[str]
    videos: list[str]
    audios: list[str]

    @property
    def music_tag(self) -> str:
        if not self.audios:
            raise ValueError("no audio reference wired")
        return self.audios[-1]


def compute_ref_tags(n_images: int, n_videos: int, n_standalone_audio: int) -> RefTags:
    """Work out the prompt tags for a given reference wiring.

    Each reference video contributes its own soundtrack tag, emitted before
    the video, and those consume <Audio> indices ahead of standalone clips.
    """
    images = [f"<Picture {i + 1}>" for i in range(n_images)]
    videos = [f"<Video {i + 1}>" for i in range(n_videos)]

    audio_i = 0
    for _ in range(n_videos):
        audio_i += 1

    audios = [f"<Audio {audio_i + i + 1}>" for i in range(n_standalone_audio)]
    return RefTags(images=images, videos=videos, audios=audios)


def slice_audio(
    src: str | Path,
    dest: str | Path,
    start_s: float,
    duration_s: float,
    *,
    sample_rate: int = 44100,
) -> Path:
    """Cut the exact passage a segment will be scored against.

    Each generation hears only its own slice, so the model is reacting to the
    bars it is actually covering rather than the whole track.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", f"{start_s:.6f}", "-t", f"{duration_s:.6f}",
        "-i", str(src),
        "-ar", str(sample_rate), "-ac", "2",
        str(dest),
    ]
    subprocess.run(cmd, check=True)
    return dest


class WorkflowBuilder:
    def __init__(self, injection_map: dict, workflow: dict):
        self.map = injection_map
        self.base = workflow

    @classmethod
    def load(cls, map_path: str | Path, root: str | Path | None = None) -> "WorkflowBuilder":
        map_path = Path(map_path)
        m = json.loads(map_path.read_text())
        root = Path(root) if root else map_path.parent.parent
        wf = json.loads((root / m["workflow"]).read_text())
        return cls(m, wf)

    def build(
        self,
        *,
        prompt: str,
        duration_input: float,
        seed: int,
        width: int,
        height: int,
        audio_files: list[str],
        image_files: list[str] | None = None,
        steps: int | None = None,
        video_prefix: str | None = None,
        audio_prefix: str | None = None,
        lora_strength: float | None = None,
    ) -> tuple[dict, RefTags]:
        """Produce a ready-to-queue API-format graph plus its resolved tags."""
        g = copy.deepcopy(self.base)
        image_files = image_files or []
        ref_node = self.map["reference_node"]

        for nid in self.map.get("prune_nodes", []):
            g.pop(nid, None)

        def put(key: str, value):
            t = self.map["targets"].get(key)
            if t and t["node"] in g:
                g[t["node"]]["inputs"][t["field"]] = value

        put("prompt", prompt)
        put("duration_input", float(duration_input))
        put("seed", int(seed))
        put("width", int(width))
        put("height", int(height))
        if steps is not None:
            put("steps", int(steps))
        if video_prefix:
            put("video_prefix", video_prefix)
            put("savevideo_prefix", video_prefix)
        if audio_prefix:
            put("audio_prefix", audio_prefix)
        if lora_strength is not None:
            put("lora_strength", float(lora_strength))

        for spec_key in ("image_refs", "audio_refs", "video_refs"):
            spec = self.map.get(spec_key)
            if not spec:
                continue
            prefix = spec["socket_prefix"]
            for k in [k for k in g[ref_node]["inputs"] if k.startswith(prefix)]:
                linked = g[ref_node]["inputs"].pop(k)
                if isinstance(linked, list) and linked[0] in g:
                    tmpl = spec.get("template_node")
                    if linked[0] != tmpl:
                        g.pop(linked[0], None)
            tmpl = spec.get("template_node")
            if tmpl:
                g.pop(tmpl, None)

        next_id = int(self.map.get("node_id_base", 9000))

        def add_loader(spec: dict, filename: str, slot: int) -> None:
            nonlocal next_id
            nid = str(next_id)
            next_id += 1
            g[nid] = {
                "inputs": {spec["loader_field"]: filename},
                "class_type": spec["loader_class"],
                "_meta": {"title": f"{spec['loader_class']} {slot}"},
            }
            g[ref_node]["inputs"][f"{spec['socket_prefix']}{slot}"] = [nid, 0]

        img_spec = self.map["image_refs"]
        for i, f in enumerate(image_files[: img_spec["max"]]):
            add_loader(img_spec, f, i)

        aud_spec = self.map["audio_refs"]
        for i, f in enumerate(audio_files[: aud_spec["max"]]):
            add_loader(aud_spec, f, i)

        tags = compute_ref_tags(
            n_images=min(len(image_files), img_spec["max"]),
            n_videos=0,
            n_standalone_audio=min(len(audio_files), aud_spec["max"]),
        )
        return g, tags


class ComfyClient:
    """Minimal ComfyUI API client: queue a graph, wait, collect outputs."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8188, client_id: str | None = None):
        self.base = f"http://{host}:{port}"
        self.client_id = client_id or str(uuid.uuid4())

    def _post(self, path: str, payload: dict) -> dict:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{self.base}{path}", data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            raise RuntimeError(f"ComfyUI HTTP {e.code}: {body}") from e

    def _get(self, path: str) -> dict | None:
        try:
            with urllib.request.urlopen(f"{self.base}{path}", timeout=60) as r:
                return json.loads(r.read())
        except (TimeoutError, urllib.error.URLError, OSError) as e:
            print(f"[comfy] _get {path} transient error: {e}")
            return None
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            raise RuntimeError(f"ComfyUI HTTP {e.code}: {body}") from e

    def is_up(self) -> bool:
        try:
            res = self._get("/system_stats")
            return res is not None
        except Exception:
            return False

    def queue(self, graph: dict) -> str:
        res = self._post("/prompt", {"prompt": graph, "client_id": self.client_id})
        if "prompt_id" not in res:
            raise RuntimeError(f"ComfyUI rejected the graph: {res}")
        return res["prompt_id"]

    def wait(self, prompt_id: str, *, poll_s: float = 2.0, timeout_s: float = 7200) -> dict:
        """Block until the job appears in history. Generations are long; the
        default ceiling is two hours per segment."""
        started = time.time()
        while True:
            hist = self._get(f"/history/{prompt_id}")
            if hist and prompt_id in hist:
                entry = hist[prompt_id]
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    raise RuntimeError(f"generation failed: {status}")
                return entry
            if time.time() - started > timeout_s:
                raise TimeoutError(f"{prompt_id} exceeded {timeout_s}s")
            time.sleep(poll_s)

    @staticmethod
    def collect_outputs(entry: dict) -> dict[str, list[str]]:
        """Pull produced filenames out of a history entry, by kind."""
        found: dict[str, list[str]] = {"video": [], "audio": [], "image": []}
        for node_out in entry.get("outputs", {}).values():
            for key in ("gifs", "videos", "video"):
                for item in node_out.get(key, []) or []:
                    if isinstance(item, dict) and item.get("filename"):
                        found["video"].append(item["filename"])
            for item in node_out.get("audio", []) or []:
                if isinstance(item, dict) and item.get("filename"):
                    found["audio"].append(item["filename"])
            for item in node_out.get("images", []) or []:
                if isinstance(item, dict) and item.get("filename"):
                    found["image"].append(item["filename"])
        return found