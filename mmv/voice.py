"""Voice and actor gender check for lip sync: a suggestion only, never a block.

The vocals stem is classified by its median sung pitch and each actor by the words of their description. A warning is
raised only when both are clear and they disagree; anything uncertain stays silent."""
import json
import re
import subprocess
import sys

MALE_BELOW_HZ = 165.0
FEMALE_ABOVE_HZ = 250.0
MIN_VOICED_SECONDS = 3.0
MIN_VOICED_FRAMES = 40
MAX_ANALYSIS_SECONDS = 150.0
LOUD_FRACTION = 0.25

_FEMALE = re.compile(r"\b(female|woman|women|girl|lady|she|her|hers|herself|actress)\b", re.I)
_MALE = re.compile(r"\b(male|man|men|boy|gentleman|he|him|his|himself)\b", re.I)


def classify_pitch(median_hz, voiced_seconds):
    """'male', 'female' or None (unsure) from the median sung fundamental and how much voiced audio backs it."""
    if median_hz is None or voiced_seconds < MIN_VOICED_SECONDS:
        return None
    return 'male' if median_hz < MALE_BELOW_HZ else 'female' if median_hz > FEMALE_ABOVE_HZ else None


def estimate_voice(stem_path):
    """{'gender', 'median_hz', 'voiced_seconds'} for a vocals stem (reads audio; run away from the request thread)."""
    import librosa
    import numpy as np

    y, sr = librosa.load(str(stem_path), sr=22050, mono=True, duration=MAX_ANALYSIS_SECONDS)
    hop = 512
    f0, voiced, _ = librosa.pyin(y, fmin=65.0, fmax=1000.0, sr=sr, hop_length=hop)
    rms = librosa.feature.rms(y=y, hop_length=hop)[0][:f0.size]
    loud = rms > LOUD_FRACTION * np.percentile(rms, 95)       # stem bleed is quiet and drags the median around
    pitches = f0[voiced & np.isfinite(f0) & loud]
    seconds = float(pitches.size * hop / sr)
    median = float(np.median(pitches)) if pitches.size >= MIN_VOICED_FRAMES else None
    return {'gender': classify_pitch(median, seconds), 'median_hz': median, 'voiced_seconds': seconds}


def actor_gender(description):
    """'male', 'female' or None from an actor's description: the pronoun and noun counts must clearly favor one side."""
    text = description or ''
    female, male = len(_FEMALE.findall(text)), len(_MALE.findall(text))
    return 'female' if female >= 2 and female >= 2 * male else 'male' if male >= 2 and male >= 2 * female else None


def check_singer(voice_gender, genders, singer):
    """Plan-level result: {'warn': bool, 'voice', 'singer', 'suggested'}.

    `genders` maps actor id to 'male'/'female'/None. Warns only when the voice and the chosen singer are both clear and
    different; `suggested` is the first actor (in cast order) whose gender matches the voice, or None."""
    singer_gender = genders.get(singer)
    warn = bool(voice_gender and singer_gender and voice_gender != singer_gender)
    suggested = next((actor for actor, gender in genders.items() if gender == voice_gender), None) if warn else None
    return {'warn': warn, 'voice': voice_gender, 'singer': singer_gender, 'suggested': suggested}


def cached_voice(store, digest, quality='standard'):
    """The voice estimate for an already separated vocals stem (cached), or None. Never starts a separation."""
    from .stems import QUALITIES, _root, model_for
    for q in sorted(QUALITIES, key=lambda name: name != quality):
        model = model_for('vocals', q)
        stem, cache = _root(store) / f'{digest}-{model}' / 'vocals.wav', _root(store) / f'voice-{digest}-{model}.json'
        if cache.is_file():
            return json.loads(cache.read_text(encoding='utf-8'))
        if stem.is_file():
            temp = cache.with_suffix('.tmp')
            try:
                done = subprocess.run([sys.executable, '-m', 'mmv.worker', 'voice', str(stem), str(temp)],
                                      capture_output=True, text=True, timeout=600)
            except subprocess.SubprocessError:
                return None
            if done.returncode:
                return None
            temp.replace(cache)
            return json.loads(cache.read_text(encoding='utf-8'))
    return None


def voice_check(store, digest, request, lip_sync):
    """The preview's voice/gender check for a lip-sync production, or None when it has nothing to say or cannot tell
    (no vocals stem yet, an unsure voice, or no actor whose gender is clear)."""
    if not lip_sync or not lip_sync.get('singer'):
        return None
    estimate = cached_voice(store, digest, request.get('stem_quality') or 'standard')
    if not estimate or not estimate.get('gender'):
        return None
    genders = {actor_id: actor_gender((store.actor(actor_id) or {}).get('description')) for actor_id in lip_sync.get('actors', {})}
    result = check_singer(estimate['gender'], genders, lip_sync['singer'])
    names = lip_sync.get('actors', {})
    return {**result, 'genders': genders, 'median_hz': round(estimate['median_hz'] or 0), 'singer_name': names.get(lip_sync['singer']),
            'suggested_name': names.get(result['suggested'])}
