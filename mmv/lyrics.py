"""Optional lyrics detection: transcribe the vocals (or the mix) to timed words, group them into lines,
and align pasted lyrics to what was heard. The speech model is an optional add-on that is never
installed or downloaded automatically; detection and alignment are free local analysis.
"""
from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from .storage import read_json, write_json

WORKER = Path(__file__).with_name('lyrics_worker.py')
INSTALL_HINT = 'pip install openai-whisper'
# File names are whisper's own; large-v3 was measured at 3,087,371,615 bytes. The others are approximate.
MODELS = {
    'tiny': {'file': 'tiny.pt', 'download': 'about 75 MB'},
    'base': {'file': 'base.pt', 'download': 'about 145 MB'},
    'small': {'file': 'small.pt', 'download': 'about 470 MB'},
    'medium': {'file': 'medium.pt', 'download': 'about 1.5 GB'},
    'large-v3': {'file': 'large-v3.pt', 'download': 'about 3.1 GB'},
}
DEFAULT_MODEL = 'large-v3'
# GPU memory each model needs: large-v3 measured at about 10.2 GB; the others are the figures in Whisper's own README.
VRAM_GB = {'tiny': 1.0, 'base': 1.0, 'small': 2.0, 'medium': 5.0, 'large-v3': 10.3}
VRAM_HEADROOM_GB = 1.0
GAP_SECONDS = 0.9
MIN_MATCH = 0.5               # below this share of recognised words a line's timing is only a guess
GUESS_SECONDS = 3.0           # a line with no recognised words is given at most this window, never the whole gap
MAX_LINE_WORDS = 10
MAX_LINE_SECONDS = 8.0
_PROBE = {'python': None, 'at': 0.0, 'ok': False}


def python_exe():
    """The interpreter that runs Whisper: MMV_LYRICS_PYTHON (an existing Whisper environment) or this one."""
    return os.environ.get('MMV_LYRICS_PYTHON') or sys.executable


def model_dir():
    return Path(os.environ.get('MMV_WHISPER_DIR') or Path.home() / '.cache' / 'whisper')


def available():
    exe = python_exe()
    if _PROBE['python'] != exe or time.time() - _PROBE['at'] > 60:
        try:
            ok = subprocess.run([exe, '-c', 'import whisper'], capture_output=True, timeout=120).returncode == 0
        except (OSError, subprocess.SubprocessError):
            ok = False
        _PROBE.update(python=exe, at=time.time(), ok=ok)
    return _PROBE['ok']


def pick_device(model):
    """The GPU only when the model fits in the memory free right now (with headroom), otherwise the CPU."""
    from . import stems
    return 'cuda' if stems._gpu()['free'] / 1024 ** 3 >= VRAM_GB[model] + VRAM_HEADROOM_GB else 'cpu'


def recommend(hw):
    """Plain-language advice for an installer or agent. Measured: large-v3 about 10.2 GB VRAM and 46 s (GPU) or
    164 s (CPU) for a 60 s clip. Smaller models were not tested on singing, so none is recommended for accuracy."""
    free = hw['vram_free_gb']
    fits = [name for name in MODELS if free >= VRAM_GB[name] + VRAM_HEADROOM_GB]
    notes = []
    if 'large-v3' in fits:
        notes.append(f"The most accurate model (large-v3, 3.1 GB) fits on this GPU ({hw['gpu']}, {free} GB free): about 46 s per minute "
                     'of song including loading. It needs about 10 GB of VRAM, so close or unload ComfyUI models first.')
        model, device = 'large-v3', 'cuda'
    else:
        model, device = 'large-v3', 'cpu'
        notes.append('large-v3 needs about 10 GB of free VRAM, which this machine does not have free, so it would run on the '
                     'CPU: about 3 minutes per minute of song, with no VRAM use. That is slow but is the accurate option measured.')
        if fits:
            notes.append(f"Smaller models fit the free GPU memory (up to {fits[-1]}) and are much faster, but their accuracy "
                         'on singing has not been measured; offer them only if the wait matters.')
    if hw.get('ram_gb') is not None and hw['ram_gb'] < 8:
        notes.append(f"System RAM is {hw['ram_gb']} GB; large-v3 on CPU needs several GB.")
    notes.append('Detection is optional and free; run it on the isolated vocals when the stems add-on is installed '
                 '(it was correct on stems and wrong on one full mix in testing).')
    return {'model': model, 'device': device, 'notes': notes}


def status(store):
    from . import stems
    hw = stems.hardware()
    cached = {name: (model_dir() / info['file']).is_file() for name, info in MODELS.items()}
    return {'available': available(), 'python': python_exe(), 'install_command': INSTALL_HINT,
            'models': {name: {'cached': cached[name], 'download': info['download'], 'vram_gb': VRAM_GB[name]}
                       for name, info in MODELS.items()},
            'hardware': hw, 'recommendation': recommend(hw),
            'note': 'Optional add-on (openai-whisper, MIT). Detection works best on the isolated vocals stem. '
                    'Nothing is installed or downloaded automatically; you can edit every detected line.'}


def require_ready(model):
    if model not in MODELS:
        raise ValueError('Unknown speech model')
    if not available():
        raise ValueError(f'Lyrics detection needs the optional Whisper add-on. Install it with "{INSTALL_HINT}" '
                         'or point MMV_LYRICS_PYTHON at a Python that already has it.')
    if not (model_dir() / MODELS[model]['file']).is_file():
        raise ValueError(f'The {model} speech model is not downloaded yet ({MODELS[model]["download"]}); approve its '
                         'one-time download first.')


def _cache(store):
    folder = store.home / 'analysis' / 'lyrics'
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def transcribe(store, song, digest, model, context=None, use_vocals=True):
    """Timed words for a song (cached). Uses the vocals stem when the stems add-on is ready."""
    require_ready(model)
    source, audio = 'mix', Path(song)
    if use_vocals:
        from . import stems
        if stems.installed() and read_json(stems._root(store) / 'htdemucs.ready', None):
            if context:
                context.update('Separating the vocals…', 10)
            audio, source = stems.separate(store, song, digest, 'htdemucs') / 'vocals.wav', 'vocals stem'
    cache = _cache(store) / f'{digest}-{source.split()[0]}-{model}.json'
    if not cache.is_file():
        if context:
            context.update(f'Listening to the {source} with {model}…', 40)
        temp = cache.with_suffix('.tmp')
        result = subprocess.run([python_exe(), str(WORKER), str(audio), str(temp), model, str(model_dir()), pick_device(model)],
                                capture_output=True, text=True, timeout=3600)
        if result.returncode:
            raise ValueError('Lyrics detection failed: ' + result.stderr[-600:])
        temp.replace(cache)
    data = read_json(cache, {})
    return {**data, 'source': source, 'lines': group_lines(data.get('words', []))}


def group_lines(words):
    """Group timed words into lyric lines at pauses, sentence ends and length limits."""
    lines, current = [], []

    def close():
        if current:
            lines.append({'start': round(current[0]['start'], 2), 'end': round(current[-1]['end'], 2),
                          'text': ' '.join(w['word'] for w in current)})
            current.clear()

    for word in words:
        if current and (word['start'] - current[-1]['end'] >= GAP_SECONDS or len(current) >= MAX_LINE_WORDS
                        or word['end'] - current[0]['start'] > MAX_LINE_SECONDS):
            close()
        current.append(word)
        if re.search(r'[.!?]$', word['word']) and len(current) >= 3:
            close()
    close()
    return [line for line in lines if line['end'] - line['start'] >= 0.25]


def _norm(text):
    return re.findall(r"[a-z0-9']+", text.lower())


def parse_lyrics(text):
    """Read Suno sections and backing vocals, retaining instrumental entries without timing them."""
    if len(text) > 16000:
        raise ValueError('Lyrics must be at most 16000 characters')
    entries, section, kind = [], None, 'sung'
    for line in text.splitlines():
        markers = re.findall(r'\[([^\[\]]*)\]', line)
        for label in markers:
            label = ' '.join(label.strip().lower().split())
            section = label[:40]
            # Whole words only, and a voice word wins: "[Vocal Solo]" is sung, "[Guitar Solo]" is not.
            kind = 'instrumental' if (re.search(r'\b(instrumental|solo|interlude|break|drop|beat)\b', label)
                                      and not re.search(r'\b(vocals?|voice|sing|singing|choir|spoken|rap)\b', label)) else 'sung'
        line = re.sub(r'\[[^\[\]]*\]', '', line).strip()
        if not line:
            continue
        backing = bool(re.fullmatch(r'\([^()]*\)', line))
        line = line.replace('(', '').replace(')', '').strip()
        if line:
            entries.append({'text': line, 'section': section, 'kind': kind, 'backing': backing})
    if not entries:
        raise ValueError('Paste at least one line of lyrics')
    return entries


def align_lines(text, words):
    """Time pasted lyric lines against recognised words; lines that cannot be matched are interpolated and flagged."""
    entries = [entry for entry in parse_lyrics(text) if entry['kind'] == 'sung']
    rows = [entry['text'] for entry in entries]
    if not rows:
        raise ValueError('Paste at least one line of lyrics')
    heard = [(_norm(w['word']), w) for w in words]
    heard = [(tokens[0], w) for tokens, w in heard if tokens]
    wanted = [(i, token) for i, row in enumerate(rows) for token in _norm(row)]
    if not heard or not wanted:
        raise ValueError('No words were recognised in the song, so the lyrics cannot be timed')
    matcher = difflib.SequenceMatcher(None, [t for _, t in wanted], [t for t, _ in heard], autojunk=False)
    hits = {}
    for a, b, size in matcher.get_matching_blocks():
        for k in range(size):
            hits.setdefault(wanted[a + k][0], []).append(heard[b + k][1])
    if sum(len(v) for v in hits.values()) / len(wanted) < 0.3:
        raise ValueError('The pasted lyrics do not match what was heard in the song; check the text or the song.')
    result = []
    for i, row in enumerate(rows):
        matched = hits.get(i, [])
        total = len(_norm(row))
        if matched:
            ratio = len(matched) / total
            result.append({'start': matched[0]['start'], 'end': matched[-1]['end'], 'text': row,
                           'timing': 'matched' if ratio >= MIN_MATCH else 'uncertain', 'matched': round(ratio, 2)})
        else:
            result.append({'start': None, 'end': None, 'text': row, 'timing': 'interpolated', 'matched': 0.0})
    # Interpolate unmatched lines between their timed neighbours, keeping order monotonic.
    i = 0
    while i < len(result):
        if result[i]['start'] is not None:
            i += 1
            continue
        j = i
        while j < len(result) and result[j]['start'] is None:
            j += 1
        low = result[i - 1]['end'] if i > 0 else 0.0
        high = result[j]['start'] if j < len(result) else low + 3.0 * (j - i)
        step = min(GUESS_SECONDS, max(high - low, 0.1 * (j - i)) / (j - i))
        for k in range(i, j):
            result[k]['start'], result[k]['end'] = round(low + step * (k - i), 2), round(low + step * (k - i + 1), 2)
        i = j
    for k, item in enumerate(result):
        item.update(section=entries[k]['section'], backing=entries[k]['backing'])
        if item['end'] <= item['start']:
            item['end'] = round(item['start'] + 0.5, 2)
        if k and item['start'] < result[k - 1]['end']:
            item['start'] = result[k - 1]['end']
            item['end'] = max(item['end'], round(item['start'] + 0.5, 2))
    return result


def song_digest(path, beats_per_bar=4):
    """The same key the analysis and stems caches use for a song, so cached stems are reused."""
    import hashlib
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        hashlib.file_digest(stream, lambda: digest)
    digest.update(str(beats_per_bar).encode())
    return digest.hexdigest()


def cached_words(store, digest, model):
    """Words from an earlier detection (vocals stem preferred), or None."""
    for source in ('vocals', 'mix'):
        data = read_json(_cache(store) / f'{digest}-{source}-{model}.json', None)
        if data and data.get('words'):
            return {**data, 'source': 'vocals stem' if source == 'vocals' else 'mix'}
    return None


def prepare_model(store, model, context):
    """Download one speech model once (explicit approval is the caller's responsibility)."""
    if model not in MODELS:
        raise ValueError('Unknown speech model')
    if not available():
        raise ValueError(f'Install the optional Whisper add-on first: {INSTALL_HINT}')
    context.update(f'Downloading the {model} speech model (one time)…', 5)
    context.command([python_exe(), '-c',
                     'import sys, whisper; whisper.load_model(sys.argv[1], device="cpu", download_root=sys.argv[2])',
                     model, str(model_dir())])
    if not (model_dir() / MODELS[model]['file']).is_file():
        raise ValueError('The speech model did not download')
    return {'model': model}
