"""GPU hand-off between the renderer and the local vision model for the quality stage.

Implements the `vision` hook of worker.run_quality_stage. ComfyUI is stopped (and
its exit confirmed) only when this production launched it; an existing service
releases cached models through its API while idle and stays running. The renderer
leaves the GPU before any vision model is reused or started, a model that is
started needs verified free memory, and a vision server this stage did not start
is never stopped, so re-rendering is skipped rather than sharing the GPU with it.
If the vision model cannot start, every passage gets an error verdict and the
production completes on the pixel checks alone, with a visible note.
"""
from __future__ import annotations

import json

from . import gpu_memory, runtime
from .comfy_memory import release_cached_models

VISION_PORT = 8083


class VisionStage:
    def __init__(self, settings, directory, plan, framing_allowed, comfy_process, restart_comfy, progress, compact=False):
        self.compact = compact
        self.settings, self.directory, self.progress = settings, directory, progress
        self.by_id = {seg.segment_id: seg for seg in plan.segments}
        self.framing_allowed = framing_allowed
        # A handle exists only when this production launched ComfyUI; None means not running or external.
        self.comfy_process, self.restart_comfy = comfy_process, restart_comfy
        self.external_comfy = comfy_process is None and restart_comfy is not None
        self.process, self.failure, self.started = None, None, False
        # reused: a vision server already running outside this stage. skipped: why vision re-renders were not done.
        self.reused, self.skipped, self.baseline = False, None, None

    def _release_renderer(self):
        # The renderer's models leave the GPU before any vision model is reused or started.
        if self.comfy_process is not None:
            self.progress('Stopping ComfyUI to free the GPU for the vision check', 81)
            runtime.stop_confirmed(self.comfy_process, 'ComfyUI')
            self.comfy_process = None
        elif self.external_comfy:
            self.progress('Releasing ComfyUI model memory for the vision check', 81)
            release_cached_models(self.settings['comfy_url'])

    def _require_room(self, command):
        need = gpu_memory.gguf_need_bytes(command)
        if not need:
            return
        enough, memory = gpu_memory.wait_for_room(need)
        if enough is False:
            raise ValueError(f'Not enough free GPU memory for the vision model: {gpu_memory.gib(memory[0])} of '
                             f'{gpu_memory.gib(memory[1])} free, about {gpu_memory.gib(need)} needed. '
                             'Close other programs using the GPU or turn the vision check off')

    def _start(self):
        if self.started or self.failure:
            return
        from .vision_check import vision_command
        try:
            running = runtime.http_ok(f'http://127.0.0.1:{VISION_PORT}/health')
            self.model = 'mmv-vision'      # the alias vision_command always sets
            if running:
                # Anything but our own alias is left alone, before the renderer is touched; no launch command is needed.
                if not runtime.serves_model(f'http://127.0.0.1:{VISION_PORT}/v1', self.model):
                    raise ValueError(f'Vision port {VISION_PORT} is already in use by another service; '
                                     'close it or free the port before production')
            else:
                command = vision_command(self.settings['writer_launch'], VISION_PORT)
            self._release_renderer()
            if running:
                # Not launched by this stage, so it is never stopped, and the renderer must not share the GPU with it later.
                self.progress('Using the vision model that is already running', 81)
                self.reused = self.started = True
                return
            self.baseline = gpu_memory.gpu_memory()
            self._require_room(command)
            self.progress('Starting the local vision model', 81)
            self.process = runtime.start_service(json.dumps(command), self.settings.get('writer_cwd'),
                                                 f'http://127.0.0.1:{VISION_PORT}/health',
                                                 self.directory / 'vision-service.log', name='Vision model',
                                                 launch_setting='writer_launch')
            if self.process is None:
                raise ValueError(f'Vision port {VISION_PORT} was taken by an external service during startup')
            self.started = True
        except (ValueError, OSError) as exc:
            self.failure = f'Vision check could not run: {exc}'

    def judge(self, items):
        self._start()
        if self.failure:
            return {attempt['segment_id']: {'status': 'error', 'problems': [self.failure], 'retry': False}
                    for _, attempt, _ in items}
        from .vision_check import judge_clip
        verdicts = {}
        for number, (segment_id, attempt, result) in enumerate(items):
            seg = self.by_id[segment_id]
            self.progress(f'Vision check of passage {seg.index+1} ({number+1} of {len(items)})', 82)
            verdicts[attempt['segment_id']] = judge_clip(
                result['video'], seg.trim_frames, [shot.start_frame for shot in seg.shots],
                f'http://127.0.0.1:{VISION_PORT}/v1', self.model, framing_allowed=self.framing_allowed, compact=self.compact)
        return verdicts

    def _refuse_rerender(self, reason):
        self.skipped = f'Passages flagged by the vision check were not re-rendered: {reason}'
        self.progress(self.skipped, 78)
        return False

    def prepare_render(self):
        """True when the renderer may use the GPU again. False means a re-render would share it with a vision model."""
        if self.reused:
            return self._refuse_rerender('a vision model that Mondo did not start is still using the GPU. '
                                         'Stop it, then render again to allow the re-render')
        process = self.process
        self.close()
        if process is not None and process.poll() is None:
            return self._refuse_rerender('the vision model did not exit; stop it by hand to free the GPU')
        if gpu_memory.wait_released(self.baseline) is False:
            return self._refuse_rerender('GPU memory was not released after the vision model stopped')
        if self.restart_comfy is not None:
            self.progress('Restarting ComfyUI to re-render passages flagged by the vision check', 78)
            self.comfy_process = self.restart_comfy()
            self.external_comfy = self.comfy_process is None
        return True

    def close(self):
        # Stops only the vision server this stage launched; a reused running server is left alone.
        runtime.stop_process(self.process)
        if self.process is not None and self.process.poll() is None:
            self.failure = 'Vision model did not exit; GPU handoff was stopped'
            return  # Retain ownership so later cleanup can retry stopping this process.
        self.process = None
        self.started = False

    def note(self):
        return self.failure
