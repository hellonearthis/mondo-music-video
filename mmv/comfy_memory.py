"""Release an idle ComfyUI's cached models without owning or stopping its process."""
from __future__ import annotations

import json
import math
import time
import urllib.request

from .render import request_json

# CUDA contexts and small custom-node allocations can remain after model/cache release.
MAX_RESERVED_BYTES = 256 * 1024 * 1024


class UnmeasurableDevice(ValueError):
    """ComfyUI released its models, but this device type cannot report whether the memory came back."""


def require_idle(base_url):
    queue = request_json(base_url + '/queue', timeout=5)
    if any(not isinstance(queue.get(key), list) for key in ('queue_running', 'queue_pending')):
        raise ValueError('ComfyUI did not report its queue state; model memory was left alone')
    if queue['queue_running'] or queue['queue_pending']:
        raise ValueError('ComfyUI has another running or queued job; Mondo left its models loaded. '
                         'Wait for that job to finish or stop ComfyUI yourself, then try again')


def memory_released(stats):
    devices = stats.get('devices')
    if not isinstance(devices, list):
        raise ValueError('ComfyUI did not report device memory after model release')
    for device in devices:
        if not isinstance(device, dict):
            raise ValueError('ComfyUI returned invalid device memory information')
        if device.get('type') == 'cpu':
            continue
        if device.get('type') in ('mps', 'privateuseone'):
            # ComfyUI reports system RAM here, not a model-allocation measurement.
            raise UnmeasurableDevice('ComfyUI does not report model-memory release for this device')
        reserved = device.get('torch_vram_total')
        if type(reserved) not in (int, float) or not math.isfinite(reserved) or reserved < 0:
            raise ValueError('ComfyUI did not report reserved model memory after release')
        if reserved > MAX_RESERVED_BYTES:
            return False
        if 'cudaMallocAsync' in device.get('name', ''):
            # PyTorch reservation counters can stay zero with this allocator even
            # while models occupy VRAM. Confirm driver-reported headroom as well.
            total, free = device.get('vram_total'), device.get('vram_free')
            if any(type(value) not in (int, float) or not math.isfinite(value) for value in (total, free)) or total <= 0 or not 0 <= free <= total:
                raise ValueError('ComfyUI did not report driver memory after model release')
            if free < total * .9:
                return False
    return True


def release_cached_models(base_url, timeout=120):
    """One /free request, then confirm queue/memory state before another model starts.

    ComfyUI acknowledges /free before its worker unloads models. Its empty HTTP
    response is intentional; a successful POST alone is not a completed handoff.
    """
    base_url = base_url.rstrip('/')
    require_idle(base_url)
    request = urllib.request.Request(base_url + '/free',
        data=json.dumps({'unload_models': True, 'free_memory': True}).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(request, timeout=10) as response:
        response.read()
    deadline = time.monotonic() + timeout
    while True:
        require_idle(base_url)
        if memory_released(request_json(base_url + '/system_stats', timeout=5)):
            return
        if time.monotonic() >= deadline:
            raise ValueError('ComfyUI has not released its model memory, so the next model was not started. '
                             'Close other programs using ComfyUI or restart it, then try again')
        time.sleep(.25)
