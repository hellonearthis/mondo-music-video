"""Conservative GPU-memory policy for model hand-offs; measurement is separate from decisions.

Unknown memory is never treated as room to overlap. Estimates add fixed reserves to
the staged model files; they are deliberately generous, not exact.
"""
from __future__ import annotations

import json
import math
import os
import struct
import subprocess
import sys
import time
from pathlib import Path

MIB = 1 << 20
GIB = 1 << 30
# Laya runs in fp32 weights, with a CUDA context, activations for a 2048-token batch and spare room.
LAYA_RESERVE = 2 * GIB
VISION_RESERVE = GIB
# What a stopped model may still leave resident (CUDA contexts, allocator slack) before we call the GPU "not released".
RELEASE_TOLERANCE = GIB


def gib(value):
    return f'{value / GIB:.1f} GiB'


def parse_nvidia_smi(text):
    """'index, free MiB, total MiB' lines -> {index: (free_bytes, total_bytes)}; malformed lines are ignored."""
    found = {}
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(',')]
        if (len(parts) == 3 and all(p.isdigit() for p in parts)
                and 0 <= int(parts[1]) <= int(parts[2]) and int(parts[2]) > 0):
            found[int(parts[0])] = (int(parts[1]) * MIB, int(parts[2]) * MIB)
    return found


def visible_index(environ):
    """GPU index CUDA will use first: None when CUDA_VISIBLE_DEVICES hides all GPUs or names them by UUID."""
    value = environ.get('CUDA_VISIBLE_DEVICES')
    if value is None:
        return 0
    first = value.split(',')[0].strip()
    return int(first) if first.isdigit() else None


def gpu_memory(run=subprocess.run, environ=os.environ):
    """(free_bytes, total_bytes) of the GPU CUDA would use, or None when it cannot be measured."""
    index = visible_index(environ)
    if index is None:
        return None
    try:
        out = run(['nvidia-smi', '--query-gpu=index,memory.free,memory.total', '--format=csv,noheader,nounits'],
                  capture_output=True, text=True, timeout=10, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_nvidia_smi(out).get(index)


def safetensors_params(path):
    """Parameter count from the safetensors header alone (no tensors are loaded); None if unreadable."""
    try:
        with open(path, 'rb') as stream:
            (length,) = struct.unpack('<Q', stream.read(8))
            if length > 64 * MIB:      # not a safetensors header
                return None
            header = json.loads(stream.read(length))
        total = 0
        for name, entry in header.items():
            if name != '__metadata__':
                shape = entry['shape']
                if not isinstance(shape, list) or any(type(dim) is not int or dim < 0 for dim in shape):
                    return None
                total += math.prod(shape)
        return total
    except (OSError, ValueError, struct.error, KeyError, TypeError, AttributeError):
        return None


def laya_need_bytes(model_dir):
    """fp32 weights counted from the staged checkpoint plus the reserve; twice the file size if the header is unreadable."""
    weights = Path(model_dir) / 'model.safetensors'
    params = safetensors_params(weights)
    if params is not None:
        return params * 4 + LAYA_RESERVE
    try:
        return weights.stat().st_size * 2 + LAYA_RESERVE
    except OSError:
        return LAYA_RESERVE * 4


def gguf_need_bytes(command):
    """Model plus projector file sizes from a llama-server argv, plus the reserve; None if no file is readable.

    With zero offloaded language layers, still reserve room for a supplied projector.
    """
    paths, i, cpu_layers = [], 0, False
    while i < len(command):
        option, sep, value = command[i].partition('=')
        takes = option in ('-m', '--model', '--mmproj', '-ngl', '--n-gpu-layers', '--gpu-layers')
        if takes and not sep and i + 1 < len(command):
            i += 1
            value = command[i]
        if option in ('-ngl', '--n-gpu-layers', '--gpu-layers') and value == '0':
            cpu_layers = True
        if option in ('-m', '--model', '--mmproj') and value:
            paths.append((option, Path(value).expanduser()))
        i += 1
    if cpu_layers:
        paths = [(option, path) for option, path in paths if option == '--mmproj']
        if not paths:
            return 0
    sizes = []
    for _, path in paths:
        try:
            sizes.append(path.stat().st_size)
        except OSError:
            pass
    return sum(sizes) + VISION_RESERVE if sizes else None


def laya_device_choice(configured, need, memory, platform=sys.platform):
    """(override, message) for the Laya device. override None keeps the configured device; 'cpu' replaces it.

    Unmeasurable memory means CPU, including unified-memory GPUs.
    """
    configured = str(configured or 'cuda')
    if configured == 'cpu':
        return None, 'Laya prompt reviewer will use the CPU (set in Settings)'
    if configured in ('mps', 'mps_or_cpu') or (configured == 'auto' and platform == 'darwin' and memory is None):
        memory = None  # NVIDIA measurements cannot establish Apple GPU headroom.
    if memory is None:
        return 'cpu', ('Laya prompt reviewer will use the CPU: GPU memory could not be measured, '
                       'so the GPU is not shared with the writer')
    free, total = memory
    if free >= need:
        return None, (f'Laya prompt reviewer will use the GPU: {gib(free)} of {gib(total)} free, '
                      f'about {gib(need)} needed')
    return 'cpu', (f'Laya prompt reviewer will use the CPU: only {gib(free)} of {gib(total)} GPU memory is free '
                   f'and it needs about {gib(need)}')


def wait_for_room(need, read=None, timeout=30, interval=2, sleep=None, clock=None):
    """(enough, memory): polls while a stopped model's memory returns. Unmeasurable memory gives (None, None)."""
    read, sleep, clock = read or gpu_memory, sleep or time.sleep, clock or time.monotonic   # looked up at call time
    deadline = clock() + timeout
    while True:
        now = read()
        if now is None:
            return None, None
        if now[0] >= need or clock() >= deadline:
            return now[0] >= need, now
        sleep(interval)


def wait_released(baseline, read=None, timeout=60, interval=2, sleep=None, clock=None):
    """After a model stops: True once free memory is back within tolerance of the baseline.

    A missing baseline or reading cannot be verified and returns None; False means still held after the timeout.
    """
    if baseline is None:
        return None
    read, sleep, clock = read or gpu_memory, sleep or time.sleep, clock or time.monotonic
    deadline = clock() + timeout
    while True:
        now = read()
        if now is None:
            return None
        if now[0] >= baseline[0] - RELEASE_TOLERANCE:
            return True
        if clock() >= deadline:
            return False
        sleep(interval)
