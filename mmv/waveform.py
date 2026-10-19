"""Bounded waveform peaks for the score editor, computed with ffmpeg so the browser never decodes the song."""
from __future__ import annotations

import subprocess

import numpy as np

SAMPLE_RATE = 2000
MAX_SECONDS = 3600
MAX_PEAKS = 4000


def waveform_peaks(path, *, peaks=MAX_PEAKS):
    command = ['ffmpeg', '-v', 'error', '-t', str(MAX_SECONDS), '-i', str(path), '-vn', '-ac', '1',
               '-ar', str(SAMPLE_RATE), '-f', 's16le', '-']
    result = subprocess.run(command, capture_output=True, timeout=120)
    if result.returncode or not result.stdout:
        raise ValueError('The song could not be decoded for the waveform')
    samples = np.abs(np.frombuffer(result.stdout[:len(result.stdout) // 2 * 2], dtype=np.int16).astype(np.float32)) / 32768.0
    buckets = max(1, min(peaks, len(samples) // 8))
    edges = np.linspace(0, len(samples), buckets + 1, dtype=int)
    values = [float(samples[a:b].max()) if b > a else 0.0 for a, b in zip(edges[:-1], edges[1:])]
    top = max(values) or 1.0
    return {'duration': round(len(samples) / SAMPLE_RATE, 3), 'peaks': [round(v / top, 3) for v in values]}
