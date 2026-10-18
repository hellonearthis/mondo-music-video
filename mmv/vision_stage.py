"""GPU hand-off between the renderer and the local vision model for the quality stage.

Implements the `vision` hook of worker.run_quality_stage. ComfyUI is stopped only
when this production launched it; a service MMV did not start is never stopped.
If the vision model cannot start, every passage gets an error verdict and the
production completes on the pixel checks alone, with a visible note.
"""
from __future__ import annotations

import json

from . import runtime

VISION_PORT = 8083


class VisionStage:
    def __init__(self, settings, directory, plan, framing_allowed, comfy_process, restart_comfy, progress):
        self.settings, self.directory, self.progress = settings, directory, progress
        self.by_id = {seg.segment_id: seg for seg in plan.segments}
        self.framing_allowed = framing_allowed
        # A handle exists only when this production launched ComfyUI; None means not running or external.
        self.comfy_process, self.restart_comfy = comfy_process, restart_comfy
        self.process, self.failure, self.started = None, None, False

    def _start(self):
        if self.started or self.failure:
            return
        from .vision_check import vision_command
        try:
            command = vision_command(self.settings['writer_launch'], VISION_PORT)
            self.model = command[command.index('--alias') + 1] if '--alias' in command else 'vision'
            if runtime.http_ok(f'http://127.0.0.1:{VISION_PORT}/health'):
                raise ValueError(f'Vision port {VISION_PORT} is already in use; close that service before production')
            if self.comfy_process is not None:
                self.progress('Stopping ComfyUI to free the GPU for the vision check', 81)
                runtime.stop_process(self.comfy_process)
                self.comfy_process = None
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
                f'http://127.0.0.1:{VISION_PORT}/v1', self.model, framing_allowed=self.framing_allowed)
        return verdicts

    def prepare_render(self):
        self.close()
        self.started = False
        if self.restart_comfy is not None:
            self.progress('Restarting ComfyUI to re-render passages flagged by the vision check', 78)
            self.comfy_process = self.restart_comfy()

    def close(self):
        # Stops only the vision server this stage launched.
        runtime.stop_process(self.process)
        self.process = None
        self.started = False

    def note(self):
        return self.failure
