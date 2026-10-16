"""
🪿 MAXIMUM GOOSE LABORATORY 🪿
backends.base — the backend capability contract.

A backend is one renderer the pipeline can generate through: the local
ComfyUI MiniMax H3 install today, a hosted model behind an HTTP API
tomorrow. Each backend declares WHAT it can do in a capabilities dict and
answers HOW through a small set of methods. The planner asks; it no longer
knows. 17n+5 is a MiniMax H3 fact, not physics, and this module is where
that distinction becomes executable.

Required capability keys (validated by validate_capabilities):

  backend               registry name, e.g. "local_h3"
  display_name          human name for menus and the web GUI
  frame_lattice         how durations snap.
                        frames mode:
                          {"mode": "frames", "fps": 24, "formula": "17n+5",
                           "step": 17, "offset": 5, "min_frames": 5,
                           "max_frames_safe": 345, "max_frames_hard": 362}
                        seconds mode (hosted APIs that take whole seconds):
                          {"mode": "seconds", "fps": 24,
                           "allowed_seconds": [4, 5, ..., 15]}
  max_reference_images  reference images one generation accepts
  max_reference_videos  reference videos one generation accepts
  max_reference_audios  reference audio clips one generation accepts
  audio_conditioning    {"supported": bool, "how": str}
  prompt_tag_syntax     "minimax_h3"  -> <Picture N>/<Audio N> text tags
                        "none"        -> references ride as API fields only
  max_prompt_chars      int ceiling, or None when uncensused
  resolution_mode       "megapixel_snap" or "fixed_list"
  supports_seed         bool
  steps                 sampler steps where the backend exposes them.
                        Machine-facing only: NEVER surfaced in any menu,
                        card, or UI. Local H3 carries 20, carved in stone.
  cost_per_generation   float dollars per generation, 0.0 for local

Optional keys (v0.13.0, CHUNK 5a):

  resolutions           fixed_list backends: the named menu, first = default
  resolution_sizes      fixed_list backends: {name: short side in pixels}.
                        NOMINAL — it gives plan.json a width/height to record
                        and lets `mondo render` read the name back from the
                        plan. The provider decides the real pixel grid; these
                        numbers are never sent on the wire.
  min_reference_images  references a generation REQUIRES (0 when absent).
                        WaveSpeed's catalog refuses a request with no image
                        or video; declaring it lets `mondo render` refuse a
                        plan with empty slots before any upload or charge.
  key_provider          config key name for this backend's API key.
                        When absent, the backend's own name is used.
  field_audio           {"supported": bool, "how": str}, whether this backend hands back H3's own field audio as a separate per-segment file (renders.json "audio"); absent means it delivers none.
                        Consumers read the card dict, never the property.

capabilities() returns a FRESH dict on every call, so a caller scribbling
on one result can never poison the next reader.

Rendering (v0.13.0, CHUNK 5a): `mondo render` is ONE loop over
render_segment(), bracketed by open_render()/close_render(). The loop owns
the plan, the prompts, resume, the planner's slot-count contract and
renders.json; everything provider-specific — staging files into a ComfyUI
input folder, uploading to a hosted API, waiting on a queue or a poll —
lives behind those three calls. Task F's review gate falls naturally on the
render_segment() boundary: one segment, one call, one pause.
"""

from __future__ import annotations

import math

from ..comfy import RefTags, compute_ref_tags

REQUIRED_CAPABILITY_KEYS = (
    "backend",
    "display_name",
    "frame_lattice",
    "max_reference_images",
    "max_reference_videos",
    "max_reference_audios",
    "audio_conditioning",
    "prompt_tag_syntax",
    "max_prompt_chars",
    "resolution_mode",
    "supports_seed",
    "steps",
    "cost_per_generation",
)

LATTICE_MODE_FRAMES = "frames"
LATTICE_MODE_SECONDS = "seconds"

TAG_SYNTAX_MINIMAX_H3 = "minimax_h3"
TAG_SYNTAX_NONE = "none"
# Seedance reads its references as "@Image 1". The house writes, checks and
# stores the H3 grammar (<Picture 1>) for every tagged backend; a Seedance
# backend translates the finished prompt at the wire (seedance.to_seedance).
TAG_SYNTAX_SEEDANCE = "seedance"


class BackendError(Exception):
    """A backend was asked for something its capabilities cannot honour."""


class Backend:
    """One renderer, described by its capabilities and asked through methods.

    Subclasses implement capabilities() and, for frames-mode lattices, the
    frame math. Seconds-mode math is generic and lives here, so a hosted
    backend that takes whole seconds inherits correct snapping for free.
    """

    name: str = "abstract"

    # ------------------------------------------------------------------ #
    # Declaration                                                        #
    # ------------------------------------------------------------------ #

    def capabilities(self) -> dict:
        """A fresh dict describing this backend. Subclasses must override."""
        raise NotImplementedError(f"{type(self).__name__} declares no capabilities")

    def validate_capabilities(self) -> None:
        """Fail loudly if a backend ships an incomplete declaration."""
        caps = self.capabilities()
        missing = [k for k in REQUIRED_CAPABILITY_KEYS if k not in caps]
        if missing:
            raise BackendError(
                f"Backend '{self.name}' capability declaration is missing: "
                f"{', '.join(missing)}"
            )
        lat = caps["frame_lattice"]
        mode = lat.get("mode")
        if mode not in (LATTICE_MODE_FRAMES, LATTICE_MODE_SECONDS):
            raise BackendError(
                f"Backend '{self.name}' frame_lattice mode must be "
                f"'{LATTICE_MODE_FRAMES}' or '{LATTICE_MODE_SECONDS}', "
                f"got {mode!r}"
            )
        if "fps" not in lat:
            raise BackendError(f"Backend '{self.name}' frame_lattice needs fps")
        if mode == LATTICE_MODE_FRAMES and "max_frames_safe" not in lat:
            raise BackendError(
                f"Backend '{self.name}' frames lattice needs max_frames_safe"
            )
        if mode == LATTICE_MODE_SECONDS and not lat.get("allowed_seconds"):
            raise BackendError(
                f"Backend '{self.name}' seconds lattice needs allowed_seconds"
            )

    # ------------------------------------------------------------------ #
    # Derived views the planner reads                                    #
    # ------------------------------------------------------------------ #

    def _lattice(self) -> dict:
        return self.capabilities()["frame_lattice"]

    @property
    def fps(self) -> int:
        return int(self._lattice()["fps"])

    @property
    def max_gen_frames(self) -> int:
        """The planner's segment ceiling: the longest span one generation
        can cover. Frames-mode backends declare it directly; seconds-mode
        backends derive it from their longest allowed duration."""
        lat = self._lattice()
        if lat["mode"] == LATTICE_MODE_FRAMES:
            return int(lat["max_frames_safe"])
        return int(max(lat["allowed_seconds"])) * int(lat["fps"])

    # ------------------------------------------------------------------ #
    # Duration — the planner asks, the backend answers                   #
    # ------------------------------------------------------------------ #

    def snap_gen_frames(self, musical_frames: int) -> int:
        """Snap a musical span UP to the nearest duration this backend can
        generate, in frames at self.fps. Always upward, so assembly can
        always trim back to the musical span.

        Seconds-mode math is generic and lives here. Frames-mode formulas
        are model facts and live in the subclass.
        """
        lat = self._lattice()
        if lat["mode"] == LATTICE_MODE_SECONDS:
            fps = int(lat["fps"])
            allowed = sorted(int(s) for s in lat["allowed_seconds"])
            need = max(1, int(musical_frames))
            target_s = max(allowed[0], math.ceil(need / fps))
            if target_s > allowed[-1]:
                raise BackendError(
                    f"Backend '{self.name}' cannot generate "
                    f"{need} frames ({need / fps:.2f}s); its longest "
                    f"duration is {allowed[-1]}s. The planner ceiling "
                    f"(max_gen_frames) should have prevented this."
                )
            for s in allowed:
                if s >= target_s:
                    return s * fps
            raise BackendError(f"Backend '{self.name}' allowed_seconds is empty")
        raise NotImplementedError(
            f"Backend '{self.name}' uses a frames lattice and must implement "
            f"snap_gen_frames itself"
        )

    def duration_input_for(self, gen_frames: int) -> float:
        """The value the renderer's duration field receives for a snapped
        frame count. Seconds-mode: the whole-second duration. Frames-mode:
        subclass-defined (local H3 feeds frames/24 so the graph's own snap
        becomes a no-op)."""
        lat = self._lattice()
        if lat["mode"] == LATTICE_MODE_SECONDS:
            fps = int(lat["fps"])
            allowed = {int(s) for s in lat["allowed_seconds"]}
            if gen_frames % fps != 0 or (gen_frames // fps) not in allowed:
                raise BackendError(
                    f"{gen_frames} frames is not a whole allowed second for "
                    f"backend '{self.name}'"
                )
            return float(gen_frames // fps)
        raise NotImplementedError(
            f"Backend '{self.name}' uses a frames lattice and must implement "
            f"duration_input_for itself"
        )

    def format_timestamp(self, frames: int) -> str:
        """Frame index -> cut-time string, MM:SS.mmm, at this backend's fps.
        Emitted from absolute frame indices so timestamps never drift by
        accumulation."""
        if frames < 0:
            raise ValueError("negative frame index")
        total_ms = round(frames * 1000 / self.fps)
        minutes, rem_ms = divmod(total_ms, 60_000)
        seconds, ms = divmod(rem_ms, 1000)
        return f"{minutes:02d}:{seconds:02d}.{ms:03d}"

    # ------------------------------------------------------------------ #
    # Resolution                                                         #
    # ------------------------------------------------------------------ #

    def snap_resolution(self, aspect_w: int, aspect_h: int,
                        megapixels: float) -> tuple[int, int]:
        """Width/height for an aspect ratio at a pixel budget. Only
        meaningful for resolution_mode 'megapixel_snap'; fixed-list
        backends choose from capabilities()['resolutions'] instead."""
        raise BackendError(
            f"Backend '{self.name}' (resolution_mode="
            f"{self.capabilities().get('resolution_mode')!r}) does not snap "
            f"resolutions by megapixel budget"
        )

    @property
    def min_reference_images(self) -> int:
        """References one generation REQUIRES. 0 unless declared."""
        return int(self.capabilities().get("min_reference_images") or 0)

    @property
    def key_provider(self) -> str:
        """Config key name for this backend's API key. Defaults to backend name."""
        return str(self.capabilities().get("key_provider") or self.name)

    @property
    def delivers_field_audio(self) -> bool:
        """Whether this backend hands back H3's own field audio as a separate
        per-segment file. Reads the card dict: absent or unsupported means none."""
        return bool((self.capabilities().get("field_audio") or {}).get("supported"))

    def default_resolution(self) -> str | None:
        """The named resolution a fixed-list backend uses when none is
        asked for: the first entry of capabilities()['resolutions']. None
        for megapixel backends, which have no names to choose from."""
        caps = self.capabilities()
        if caps.get("resolution_mode") != "fixed_list":
            return None
        names = list(caps.get("resolutions") or [])
        return str(names[0]) if names else None

    def plan_resolution(self, aspect_w: int, aspect_h: int, *,
                        megapixels: float | None = None,
                        resolution: str | None = None) -> tuple[int, int]:
        """The one doorway the planner uses for width/height (v0.13.0).

        megapixel_snap backends answer from the pixel budget exactly as they
        always have: this calls snap_resolution with the same arguments, so
        a plan made with no --resolution is byte-identical to before. A
        named resolution handed to such a backend is refused, not ignored.

        fixed_list backends answer from a NAMED resolution (default: the
        first in their menu) through named_resolution_size(). The numbers
        are nominal bookkeeping for plan.json; the provider decides the true
        pixel grid and the name, not the numbers, goes on the wire.
        """
        caps = self.capabilities()
        if caps.get("resolution_mode") == "fixed_list":
            names = [str(n) for n in (caps.get("resolutions") or [])]
            name = str(resolution) if resolution else self.default_resolution()
            if name not in names:
                raise BackendError(
                    f"Backend '{self.name}' offers resolutions "
                    f"{', '.join(names) or '(none declared)'}; {name!r} is "
                    f"not one of them.")
            return self.named_resolution_size(aspect_w, aspect_h, name)
        if resolution:
            raise BackendError(
                f"Backend '{self.name}' snaps its resolution by megapixels "
                f"and takes no named resolution; drop --resolution "
                f"{resolution!r} and set --megapixels instead.")
        if megapixels is None:
            raise BackendError(
                f"Backend '{self.name}' needs a megapixel budget to plan")
        return self.snap_resolution(aspect_w, aspect_h, megapixels)

    def named_resolution_size(self, aspect_w: int, aspect_h: int,
                              resolution: str) -> tuple[int, int]:
        """Nominal (width, height) for a named resolution at an aspect.
        Generic: capabilities()['resolution_sizes'] maps each name to its
        SHORT side in pixels and the long side follows the aspect, rounded
        to an even number. A fixed-list backend without that table must
        override this."""
        sizes = self.capabilities().get("resolution_sizes") or {}
        short = sizes.get(str(resolution))
        if not short:
            raise BackendError(
                f"Backend '{self.name}' declares no pixel size for "
                f"resolution {resolution!r} (capabilities.resolution_sizes)")
        short = int(short)
        long_ = int(round(short * max(aspect_w, aspect_h)
                          / min(aspect_w, aspect_h)))
        long_ += long_ % 2
        return (long_, short) if aspect_w >= aspect_h else (short, long_)

    def resolution_name_for(self, width: int, height: int) -> str | None:
        """Invert named_resolution_size: which menu entry produced this
        plan's nominal size? None for megapixel backends. BackendError when
        a fixed-list backend is handed a plan it did not make, which is the
        stale-plan hazard caught before a single upload."""
        caps = self.capabilities()
        if caps.get("resolution_mode") != "fixed_list":
            return None
        short = min(int(width), int(height))
        for name, px in (caps.get("resolution_sizes") or {}).items():
            if int(px) == short:
                return str(name)
        names = ", ".join(str(n) for n in (caps.get("resolutions") or []))
        raise BackendError(
            f"This plan's {width}x{height} matches none of backend "
            f"'{self.name}' resolutions ({names}); it was planned for "
            f"another backend. Re-plan with --rerun.")

    # ------------------------------------------------------------------ #
    # Price                                                              #
    # ------------------------------------------------------------------ #

    def cost_for(self, seconds: float, resolution: str | None = None,
                 images: int = 0) -> float:
        """Dollars for ONE generation of `seconds` at `resolution` with
        `images` reference images. Default: the card's flat
        cost_per_generation. Backends that bill by the second override it,
        so every money gate prints what will actually be charged."""
        return float(self.capabilities().get("cost_per_generation") or 0.0)

    # ------------------------------------------------------------------ #
    # Prompt tag grammar                                                 #
    # ------------------------------------------------------------------ #

    def ref_tags(self, n_images: int, n_videos: int,
                 n_standalone_audio: int) -> RefTags:
        """The prompt tags a generation with this reference wiring uses.
        Tag-free backends (references as API fields) return empty tags and
        the writer contract never cites a picture."""
        syntax = self.capabilities()["prompt_tag_syntax"]
        if syntax in (TAG_SYNTAX_MINIMAX_H3, TAG_SYNTAX_SEEDANCE):
            return compute_ref_tags(n_images, n_videos, n_standalone_audio)
        if syntax == TAG_SYNTAX_NONE:
            return RefTags(images=[], videos=[], audios=[])
        raise BackendError(
            f"Backend '{self.name}' declares unknown prompt_tag_syntax "
            f"{syntax!r}"
        )

    # ------------------------------------------------------------------ #
    # Generation                                                         #
    # ------------------------------------------------------------------ #

    def generate(self, **request):
        """The PROVIDER primitive: one request to one renderer, in that
        renderer's own vocabulary. WaveSpeed implements it against its API
        (and mgl_wavespeed_probe.py / mgl_test_wavespeed.py call it
        directly). The pipeline does not call generate(); it calls
        render_segment(), which each backend adapts onto whatever primitive
        it has — local_h3 onto a ComfyUI graph, WaveSpeed onto generate()."""
        raise NotImplementedError(
            f"Backend '{self.name}' has no provider primitive generate(); "
            f"the pipeline renders through render_segment()."
        )

    # ------------------------------------------------------------------ #
    # Rendering — the pipeline's per-segment contract (v0.13.0, 5a)     #
    # ------------------------------------------------------------------ #

    def open_render(self, **run) -> None:
        """Once per run, before the loop. Keyword arguments the loop sends:

          slug            the run slug
          out_dir         Path the backend may keep run-local files under
                          (runs/<slug>/renders_<backend>/); created on demand
          cast_sheets     [(actor_id, absolute sheet path), ...] in casting
                          order — every reference the run will cite
          subject_image   absolute path or None (the no-casting single ref)
          song            absolute path of the source audio
          steps, timeout_s
          comfy_host, comfy_port, comfy_input, comfy_output, map_path, root
                          (local_h3 machinery; hosted backends ignore them)

        A backend reads the keys it needs and ignores the rest. Refuse by
        raising BackendError with the sentence the operator should read;
        `mondo render` prints it to stderr and exits 2, touching nothing.
        """
        raise NotImplementedError(
            f"Backend '{self.name}' cannot render: open_render() is not "
            f"implemented."
        )

    def render_segment(self, **job) -> dict:
        """Once per segment, in plan order. Keyword arguments:

          segment_id, index, slug
          prompt           the validated prompt text for this segment
          duration_input   what the planner recorded for THIS backend
          gen_frames, width, height
          seed             already offset per segment by the loop
          images           [(key, absolute path), ...] in slot order; key is
                           the actor_id, or "subject" for --subject-image
          song, audio_start_s, audio_end_s
                           the backend slices its own audio clip — into a
                           ComfyUI input folder, or a staging dir to upload

        Returns this segment's renders.json entry: at least
          {"video": <path or "">, "audio": <path or "">}
        local_h3 returns exactly those two keys, so a local renders.json is
        byte-identical to v0.12.0; hosted backends add "backend",
        "request_id" and "cost" so every clip carries its provenance.
        The loop writes renders.json after every segment, so resume works
        the same way for every backend."""
        raise NotImplementedError(
            f"Backend '{self.name}' cannot render: render_segment() is not "
            f"implemented."
        )

    def close_render(self) -> None:
        """After the loop, success or failure. Default: nothing to release."""
        return None
