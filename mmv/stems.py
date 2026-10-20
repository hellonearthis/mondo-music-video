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
    'htdemucs_ft': ('drums', 'bass', 'other', 'vocals'),
    'htdemucs_6s': ('drums', 'bass', 'other', 'vocals', 'guitar', 'piano'),
}
DRIVERS = ('mix', 'drums', 'bass', 'vocals', 'other', 'guitar', 'piano')
INSTALL_HINT = 'pip install demucs'
# Measured about 1.2 GB for every model on a 4-minute track (it works in chunks); Demucs documents 3 GB as its minimum.
MIN_FREE_VRAM_BYTES = 3 * 1024 ** 3


QUALITIES = ('standard', 'high')


def model_for(driver, quality='standard'):
    """Guitar and piano need the 6-stem model; the other parts use the standard or the fine-tuned (high) model."""
    if driver not in DRIVERS or driver == 'mix':
        raise ValueError('Unknown instrument driver')
    if quality not in QUALITIES:
        raise ValueError('Stem quality is standard or high')
    if driver in ('guitar', 'piano'):
        return 'htdemucs_6s'
    return 'htdemucs_ft' if quality == 'high' else 'htdemucs'


def _root(store):
    return store.home / 'analysis' / 'stems'


def installed():
    return importlib.util.find_spec('demucs') is not None


_HARDWARE = {'at': 0.0, 'value': None}
SIZES = {'htdemucs': '81 MB', 'htdemucs_ft': '324 MB', 'htdemucs_6s': '53 MB'}
_GPU_PROBE = ('import json, torch; ok = torch.cuda.is_available(); free, total = torch.cuda.mem_get_info() if ok else (0, 0); '
              'print(json.dumps({"gpu": torch.cuda.get_device_name(0) if ok else None, "free": free, "total": total}))')


def _gpu():
    try:
        out = subprocess.run([sys.executable, '-c', _GPU_PROBE], capture_output=True, text=True, timeout=120).stdout
        return json.loads(out.strip().splitlines()[-1])
    except (ValueError, IndexError, subprocess.SubprocessError, OSError):
        return {'gpu': None, 'free': 0, 'total': 0}


def _ram_gb():
    try:
        import os
        return round(os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') / 1024 ** 3, 1)
    except (ValueError, OSError, AttributeError):
        return None


def hardware():
    """What this machine can handle for separation (GPU memory right now, system RAM); cached briefly."""
    if _HARDWARE['value'] is None or time.time() - _HARDWARE['at'] > 30:
        gpu = _gpu()
        _HARDWARE.update(at=time.time(), value={
            'gpu': gpu['gpu'], 'vram_free_gb': round(gpu['free'] / 1024 ** 3, 1),
            'vram_total_gb': round(gpu['total'] / 1024 ** 3, 1), 'ram_gb': _ram_gb()})
    return _HARDWARE['value']


def recommend(hw):
    """Plain-language advice an installer or agent can read to the user; measured figures from this project's tests."""
    gpu_ok = hw['vram_free_gb'] * 1024 ** 3 >= MIN_FREE_VRAM_BYTES
    notes = []
    if gpu_ok:
        notes.append(f"Separation will use the GPU ({hw['gpu']}, {hw['vram_free_gb']} GB free): about 8 s per 4-minute song "
                     "with the standard model, 17 s with high quality. It needs about 1.2 GB of VRAM.")
    else:
        notes.append('Separation will run on the CPU (no GPU with about 3 GB free): about 70 s per 4-minute song with the '
                     'standard model, and about 2.5 times that with high quality. It needs about 2 to 3.5 GB of RAM and no VRAM.')
    if hw['ram_gb'] is not None and hw['ram_gb'] < 6:
        notes.append(f"System RAM is {hw['ram_gb']} GB; separation can need up to 3.5 GB, so close other programs first.")
    notes.append('Standard quality (81 MB) is recommended for everyone: it matched the other models on drums and bass.')
    notes.append('High quality (324 MB, 2 to 3 times slower) was cleaner on some songs and no better on others; '
                 + ('worth offering on this machine.' if gpu_ok else 'on a CPU-only machine, offer it only if stray sounds bother the user.'))
    notes.append('The 6-stem model (53 MB) is needed only for guitar or piano; piano separation is the least reliable.')
    return {'device': 'cuda' if gpu_ok else 'cpu', 'quality': 'standard', 'notes': notes}


def status(store):
    markers = {name: read_json(_root(store) / f'{name}.ready', None) for name in MODELS}
    hw = hardware()
    return {'installed': installed(), 'install_command': INSTALL_HINT,
            'models': {name: {'ready': bool(markers[name]), 'stems': list(MODELS[name]), 'download': SIZES[name]}
                       for name in MODELS},
            'hardware': hw, 'recommendation': recommend(hw),
            'note': 'Optional add-on (Demucs, MIT). The model downloads once after you approve it; '
                    'nothing is installed or downloaded automatically.'}


def require_ready(store, driver, quality='standard'):
    model = model_for(driver, quality)
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
    return 'cuda' if _gpu()['free'] >= MIN_FREE_VRAM_BYTES else 'cpu'


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


def drive_score(store, song, score_path, digest, driver, quality='standard'):
    """The cached ScoreMap with energy and section labels taken from one stem; the beat grid stays from the mix."""
    from .engine.analyze import ScoreMap
    model = require_ready(store, driver, quality)
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


def cached_dance_part(store, digest, score_path, model, part):
    """Load one existing part, analyzing cached audio on CPU when necessary."""
    from .engine.analyze import ScoreMap
    audio = _root(store) / f'{digest}-{model}' / f'{part}.wav'
    cache = _root(store) / f'driven-{digest}-{model}-{part}.json'
    if not cache.is_file() and audio.is_file():
        with tempfile.TemporaryDirectory(dir=_root(store)) as temp:
            target = Path(temp) / 'score.json'
            analyzed = subprocess.run([sys.executable, '-m', 'mmv.worker', 'drive', str(score_path),
                                       str(audio), str(target)], capture_output=True, text=True, timeout=1800)
            if analyzed.returncode:
                return None
            target.replace(cache)
    return ScoreMap.from_json(cache) if cache.is_file() else None


def cached_dance_scores(store, digest, score_path, quality='standard', edits=None):
    """Use existing stems only, apply grid edits to copies, and fall back on unreadable analysis."""
    from dataclasses import asdict
    from .score_edit import apply_score_edits
    model = model_for('drums', quality)
    result = {}
    for part in ('drums', 'bass', 'vocals'):
        try:
            score = cached_dance_part(store, digest, score_path, model, part)
        except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
            score = None
        if score is not None:
            result[part] = asdict(apply_score_edits(score, edits))
    return result
