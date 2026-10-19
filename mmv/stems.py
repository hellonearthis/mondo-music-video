"""Optional instrument analysis: separate a song into stems and let one stem drive the plan's energy.

Stems are analysis input only; the finished video keeps the original audio. The separator
(Demucs) is an optional add-on that is never installed or downloaded automatically: the model
download happens only after an explicit approval, and a marker file records it. Separation runs
in a subprocess and is cached per song and model.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

from .storage import read_json, write_json

MODELS = {
    'htdemucs': ('drums', 'bass', 'other', 'vocals'),
    'htdemucs_6s': ('drums', 'bass', 'other', 'vocals', 'guitar', 'piano'),
}
DRIVERS = ('mix', 'drums', 'bass', 'vocals', 'other', 'guitar', 'piano')
INSTALL_HINT = 'pip install demucs'
# Measured about 1.2 GB for every model on a 4-minute track (it works in chunks); Demucs documents 3 GB as its minimum.
MIN_FREE_VRAM_BYTES = 3 * 1024 ** 3


def model_for(driver):
    if driver not in DRIVERS or driver == 'mix':
        raise ValueError('Unknown instrument driver')
    return 'htdemucs_6s' if driver in ('guitar', 'piano') else 'htdemucs'


def _root(store):
    return store.home / 'analysis' / 'stems'


def installed():
    return importlib.util.find_spec('demucs') is not None


def status(store):
    markers = {name: read_json(_root(store) / f'{name}.ready', None) for name in MODELS}
    return {'installed': installed(), 'install_command': INSTALL_HINT,
            'models': {name: {'ready': bool(markers[name]), 'stems': list(MODELS[name])} for name in MODELS},
            'note': 'Optional add-on (Demucs, MIT). The model downloads once after you approve it; '
                    'nothing is installed or downloaded automatically.'}


def require_ready(store, driver):
    model = model_for(driver)
    if not installed():
        raise ValueError(f'Instrument analysis needs the optional Demucs add-on. Install it with "{INSTALL_HINT}" '
                         'in this app\'s environment, then set up the stem model in the score editor.')
    if not read_json(_root(store) / f'{model}.ready', None):
        raise ValueError(f'Set up the {model} stem model first (a one-time download you approve in the score editor).')
    return model


def prepare_model(store, model, context):
    """Download the stem model once (explicit approval is the caller's responsibility)."""
    if model not in MODELS:
        raise ValueError('Unknown stem model')
    if not installed():
        raise ValueError(f'Install the optional Demucs add-on first: {INSTALL_HINT}')
    context.update(f'Downloading the {model} stem model (one time)…', 5)
    context.command([sys.executable, '-c',
                     'import sys; from demucs.pretrained import get_model; get_model(sys.argv[1])', model])
    _root(store).mkdir(parents=True, exist_ok=True)
    write_json(_root(store) / f'{model}.ready', {'model': model, 'prepared': time.time()})
    return {'model': model}


def pick_device():
    """CUDA only when a GPU has about 3 GB free right now, otherwise CPU (slower, but uses no VRAM)."""
    probe = ('import torch; print(torch.cuda.mem_get_info()[0] if torch.cuda.is_available() else 0)')
    try:
        free = int(subprocess.run([sys.executable, '-c', probe], capture_output=True, text=True,
                                  timeout=120).stdout.strip() or 0)
    except (ValueError, subprocess.SubprocessError):
        free = 0
    return 'cuda' if free >= MIN_FREE_VRAM_BYTES else 'cpu'


def separate(store, song, digest, model):
    """Stems for this song and model, cached; returns the directory holding one wav per stem."""
    cache = _root(store) / f'{digest}-{model}'
    if all((cache / f'{stem}.wav').is_file() for stem in MODELS[model]):
        return cache
    cache.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache.parent) as temp:
        result = subprocess.run([sys.executable, '-m', 'demucs.separate', '-n', model, '-d', pick_device(),
                                 '--filename', '{stem}.{ext}', '-o', temp, str(song)],
                                capture_output=True, text=True, timeout=3600)
        if result.returncode:
            raise ValueError('Stem separation failed: ' + result.stderr[-800:])
        produced = Path(temp) / model
        if not all((produced / f'{stem}.wav').is_file() for stem in MODELS[model]):
            raise ValueError('Stem separation did not produce every stem')
        if cache.exists():
            shutil.rmtree(cache)
        shutil.move(str(produced), str(cache))
    return cache


def drive_score(store, song, score_path, digest, driver):
    """The cached ScoreMap with energy and section labels taken from one stem; the beat grid stays from the mix."""
    from .engine.analyze import ScoreMap
    model = require_ready(store, driver)
    cache = _root(store) / f'driven-{digest}-{model}-{driver}.json'
    if not cache.is_file():
        stems = separate(store, song, digest, model)
        temp = cache.with_suffix('.tmp')
        result = subprocess.run([sys.executable, '-m', 'mmv.worker', 'drive', str(score_path),
                                 str(stems / f'{driver}.wav'), str(temp)], capture_output=True, text=True, timeout=1800)
        if result.returncode:
            raise ValueError('Instrument analysis failed: ' + result.stderr[-800:])
        temp.replace(cache)
    return ScoreMap.from_json(cache)


def driven_score(score, stem_path):
    """Pure analysis step (run in a worker process): per-beat energy and section ranking from a stem."""
    import librosa
    import numpy as np
    from .engine.analyze import _label_sections
    from .engine.grid import FPS

    y, sr = librosa.load(str(stem_path), sr=22050, mono=True)
    rms = librosa.feature.rms(y=y)[0]
    times = librosa.times_like(rms, sr=sr)
    raw = np.asarray([float(rms[int(np.argmin(np.abs(times - b / FPS)))]) for b in score.beat_frames])
    if raw.size:
        low, high = np.percentile(raw, 5), np.percentile(raw, 95)
        energy = [float(x) for x in np.clip((raw - low) / max(high - low, 1e-9), 0.0, 1.0)]
    else:
        energy = []
    sections = []
    for section in score.sections:
        inner = [e for b, e in zip(score.beat_frames, energy) if section.start_frame <= b < section.end_frame]
        sections.append(replace(section, energy=float(np.mean(inner)) if inner else section.energy))
    for section, label in zip(sections, _label_sections(np.array([s.energy for s in sections]))):
        section.label = label
    return replace(score, beat_energy=energy, sections=sections)
