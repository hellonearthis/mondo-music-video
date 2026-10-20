"""
🪿 MAXIMUM GOOSE LABORATORY 🪿
backends.local_h3 — the local ComfyUI MiniMax H3 backend.

This is the extraction of the pipeline's original, hardcoded behaviour into
a declared backend. Every answer here delegates to the exact functions the
pipeline has always used — grid.snap_up, grid.duration_input_for,
grid.format_timestamp, grid.snap_resolution — so the extraction changes
nothing. That is the point: local_h3 is the rollback path and the DEFAULT,
and it stays the default unless the operator says otherwise.

The frame lattice (17n+5), the <Picture N>/<Audio N> tag grammar, the
megapixel resolution snap, and steps fixed at 20 are MiniMax H3 / local
workflow facts. They live here now, declared, instead of standing in the
planner as universal truths.

Reference ceilings mirror config/injection_map.json (image_refs.max 9,
video_refs.max 3, audio_refs.max 3). The injection map remains the
enforcement source when the graph is built; these declarations exist so
the planner and the GUI can know the ceilings without opening the map.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from .. import grid
from ..comfy import ComfyClient, RefTags, WorkflowBuilder, slice_audio
from .base import Backend, BackendError, TAG_SYNTAX_MINIMAX_H3


class LocalH3Backend(Backend):
    """Local MiniMax H3 through ComfyUI — the original pipeline, declared."""

    name = "local_h3"

    def capabilities(self) -> dict:
        return {
            "backend": "local_h3",
            "display_name": "Local MiniMax H3 (ComfyUI)",
            "frame_lattice": {
                "mode": "frames",
                "fps": grid.FPS,
                "formula": "17n+5",
                "step": grid.STEP,
                "offset": grid.OFFSET,
                "min_frames": grid.MIN_FRAMES,
                "max_frames_safe": grid.MAX_FRAMES_SAFE,
                "max_frames_hard": grid.MAX_FRAMES_HARD,
            },
            "max_reference_images": 9,
            "max_reference_videos": 3,
            "max_reference_audios": 3,
            "audio_conditioning": {
                "supported": True,
                "how": "comfyui_ref_audio_slice",
            },
            "field_audio": {
                "supported": True,
                "how": "comfyui_saveaudio",
            },
            "prompt_tag_syntax": TAG_SYNTAX_MINIMAX_H3,
            "max_prompt_chars": None,
            "resolution_mode": "megapixel_snap",
            "supports_seed": True,
            "steps": 20,
            "cost_per_generation": 0.0,
        }

    # Frames-mode lattice: delegate to the functions that have always owned
    # the math, so the backend and the graph can never disagree.

    def snap_gen_frames(self, musical_frames: int) -> int:
        return grid.snap_up(musical_frames)

    def duration_input_for(self, gen_frames: int) -> float:
        return grid.duration_input_for(gen_frames)

    def format_timestamp(self, frames: int) -> str:
        return grid.format_timestamp(frames)

    def snap_resolution(self, aspect_w: int, aspect_h: int,
                        megapixels: float) -> tuple[int, int]:
        return grid.snap_resolution(aspect_w, aspect_h, megapixels)

    def ref_tags(self, n_images: int, n_videos: int,
                 n_standalone_audio: int) -> RefTags:
        # Inherited dispatch would land in the same place; stated explicitly
        # because this grammar is the load-bearing H3 collision surface.
        return super().ref_tags(n_images, n_videos, n_standalone_audio)

    def open_render(self, **run) -> None:
        comfy_input = run.get("comfy_input")
        comfy_output = run.get("comfy_output")
        if not comfy_input or not comfy_output:
            raise BackendError(
                "local_h3 renders through ComfyUI and needs --comfy-input and "
                "--comfy-output.")

        selected_map_path = run.get("map_path")
        self._slug = run["slug"]
        self._steps = run.get("steps")
        self._timeout = float(run.get("timeout_s") or 7200.0)
        self._comfy_input = Path(comfy_input)
        self._comfy_output = Path(comfy_output)
        self._builder = WorkflowBuilder.load(selected_map_path, run.get("root"))
        self._client = ComfyClient(run.get("comfy_host"), run.get("comfy_port"))
        if not self._client.is_up():
            raise BackendError(
                f"ComfyUI not reachable at {run.get('comfy_host')}:"
                f"{run.get('comfy_port')}")

        self._comfy_input.mkdir(parents=True, exist_ok=True)
        self.stage_dir = self._comfy_input

        # actor_id -> filename as ComfyUI will see it. The house convention is
        # that each actor's sheets are already uniquely named inside their own
        # folder, so the clean name is kept and stays readable in the input
        # directory. The collision branch below is insurance, not routine: the
        # input folder is flat and a future crew hiring actors from elsewhere
        # has made no such promise.
        staged: dict[str, str] = {}
        claimed: dict[str, str] = {}
        for actor_id, sheet_path in run.get("cast_sheets") or []:
            src = Path(sheet_path).expanduser()
            if not src.exists():
                raise BackendError(
                    f"Reference sheet not found for {actor_id}: {src}")
            name = f"{self._slug}_{src.name}"
            if claimed.get(name, actor_id) != actor_id:
                name = f"{self._slug}_{actor_id}_{src.name}"
                print(f"Sheet filename collision resolved: {src.name} -> {name}")
            claimed[name] = actor_id
            dest = self._comfy_input / name
            shutil.copy2(src, dest)
            staged[actor_id] = dest.name
            print(f"Cast sheet wired: {actor_id} -> {dest.name}")

        subject = run.get("subject_image")
        if subject:
            src = Path(subject).expanduser()
            if not src.exists():
                raise BackendError(f"Subject image not found: {src}")
            dest = self._comfy_input / f"{self._slug}_{src.name}"
            shutil.copy2(src, dest)
            staged["subject"] = dest.name
            print(f"Subject image wired: {dest.name}")
        self._staged = staged

    def render_segment(self, **job) -> dict:
        seg_id = job["segment_id"]

        seg_out_dir = self._comfy_output / "mondo" / self._slug
        stale = [f for f in seg_out_dir.glob(f"{seg_id}_*") if f.is_file()]
        if stale:
            prev_dir = seg_out_dir / f"prev_{int(time.time())}"
            prev_dir.mkdir(parents=True, exist_ok=True)
            for f in stale:
                f.rename(prev_dir / f.name)
            print(f"   {seg_id}: quarantined {len(stale)} stale output(s) "
                  f"to {prev_dir.name}")

        clip = self._comfy_input / f"{self._slug}_{seg_id}.wav"
        slice_audio(job["song"], clip, job["audio_start_s"],
                    job["audio_end_s"] - job["audio_start_s"])

        images = []
        for key, _path in job.get("images") or []:
            name = self._staged.get(key)
            if name:
                images.append(name)

        build_kwargs = dict(
            prompt=job["prompt"],
            duration_input=job["duration_input"],
            seed=job["seed"],
            width=job["width"], height=job["height"],
            audio_files=[clip.name], image_files=images,
            steps=self._steps,
            video_prefix=f"mondo/{self._slug}/{seg_id}",
            audio_prefix=f"mondo/{self._slug}/{seg_id}_diegetic",
        )

        graph, _ = self._builder.build(**build_kwargs)

        print(f"   {seg_id}: {job['gen_frames']} frames ...", flush=True)
        entry = self._client.wait(self._client.queue(graph),
                                  timeout_s=self._timeout)
        found = ComfyClient.collect_outputs(entry)
        # The workflow saves into the subfolder mondo/<slug>/. ComfyUI's history
        # API returns just the filename, so we must reconstruct the full path
        # before returning it to the caller.
        return {
            "video": str(self._comfy_output / "mondo" / self._slug / found["video"][0]) if found["video"] else "",
            "audio": str(self._comfy_output / "mondo" / self._slug / found["audio"][0]) if found["audio"] else "",
        }
