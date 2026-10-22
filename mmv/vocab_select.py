"""Deterministic contextual vocabulary selection (opt-in, outside the protected planner).

Pure functions only: vocabulary and context in, new vocabulary out. Nothing here
advances a random stream, reads files or mutates its arguments. The protected
planner (mmv/engine/plan.py) is untouched; this module decides which terms the
rotation tables hold before planning. Based on a contribution by hellonearthis.
"""
import hashlib
import math
import re

# Tables whose entries are plain rotation terms. Structured tables are left alone.
ROTATION_TABLES = ('settings', 'lighting', 'mechanisms', 'costume', 'practical_effects')
MIN_KEEP = 4
KEEP_FRACTION = 0.5
_WORD = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_STOP = frozenset('the and with from for into over under that this a an of in on at to is are as by'.split())


def stable_hash(*parts) -> int:
    """Platform-independent integer hash of the parts (never Python's salted hash)."""
    return int.from_bytes(hashlib.sha256(':'.join(map(str, parts)).encode('utf-8')).digest()[:8], 'big')


def context_words(*texts) -> frozenset:
    """Lower-cased content words from any mix of strings and string lists."""
    flat = (t for item in texts for t in ([item] if isinstance(item, str) else (item or [])) if isinstance(t, str))
    return frozenset(w for t in flat for w in _WORD.findall(t.lower()) if len(w) > 2 and w not in _STOP)


def affinity(term, words) -> int:
    """How many context words the term shares (whole words and hyphen parts)."""
    parts = {p for w in _WORD.findall(term.lower()) for p in (w, *w.split('-'))}
    return len(parts & words)


def rank_table(table, seed, name, words, keep=None) -> list:
    """Most in-context terms first, ties broken by a seeded hash; keep a coherent subset."""
    keep = keep if keep is not None else max(MIN_KEEP, math.ceil(len(table) * KEEP_FRACTION))
    ranked = sorted(dict.fromkeys(table), key=lambda t: (-affinity(t, words), stable_hash(seed, name, t)))
    return ranked[:max(1, min(keep, len(ranked)))]


def contextual_vocabulary(vocab, seed, context=(), tables=ROTATION_TABLES) -> dict:
    """A new vocabulary whose rotation tables are narrowed to the context and ordered by hash."""
    words = context_words(*context)
    return {**vocab, **{name: rank_table(vocab[name], seed, name, words)
                        for name in tables if isinstance(vocab.get(name), list) and vocab[name]}}


# World juxtaposition: on high-energy shots, borrow terms from a contrast world. Adapted from a contribution by
# hellonearthis (mirror / opposite / tangent departures); the contrast worlds are the owner's own Worlds, not fixed archetypes.
ROLES = ('mirror', 'opposite', 'tangent')
DEPARTURE_KEYS = {'setting': 'settings', 'lighting': 'lighting', 'mechanism': 'mechanisms', 'tonal_register': 'tonal_registers'}
# The role a draw lands on may have no world chosen; the next configured role takes it, so the chance of staying home is unchanged.
ROLE_FALLBACK = {'mirror': ('mirror', 'tangent', 'opposite'), 'tangent': ('tangent', 'opposite', 'mirror'),
                 'opposite': ('opposite', 'tangent', 'mirror')}
DEPARTURE_THRESHOLD = 0.65
PEAK_THRESHOLD = 0.85


def departure_score(shot_energy, segment_energy, strength) -> float:
    """Half the shot's own energy, half the passage's energy scaled by the strength slider (50 = unscaled)."""
    return 0.5 * shot_energy + 0.5 * max(0.0, min(1.0, segment_energy * strength / 50.0))


def pick_role(score, draw):
    """The contrast role for a draw in 0-99, or None to stay in the main world. Calm passages never depart."""
    if score < DEPARTURE_THRESHOLD:
        return None
    if score >= PEAK_THRESHOLD:
        return 'tangent' if draw < 55 else 'opposite' if draw < 85 else 'mirror'
    return 'mirror' if draw < 60 else 'tangent' if draw < 90 else None


def _borrowed(vocab, terms, role, seed, segment_idx, position, held) -> dict:
    """The shot vocabulary with this role's terms swapped into slots the shot already has (no keys are added)."""
    def term(key, table):
        pos = 0 if held and key != 'lighting' else position
        return terms[table][stable_hash(seed, 'world', role, key, segment_idx, pos) % len(terms[table])]
    return {**vocab, **{key: term(key, table) for key, table in DEPARTURE_KEYS.items()
                        if key in vocab and terms.get(table)}}


def plan_world_departures(segments, departures, seed, strength=50) -> dict:
    """{(segment index, shot index): (role, new shot vocab)} for shots that depart. Pure: reads the plan, changes nothing.

    `departures` maps role -> {table: [terms]} (a role with no world is absent). A passage whose shots share one setting
    (the planner holds it steady) decides once for the whole passage, so that setting stays steady; a passage anchored to
    a thematic mechanism keeps that mechanism."""
    def decide(s_idx, sh_idx, shot_energy, seg):
        role = pick_role(departure_score(shot_energy, seg.energy, strength),
                         stable_hash(seed, 'juxtaposition', s_idx, sh_idx) % 100)
        return next((r for r in ROLE_FALLBACK[role] if r in departures), None) if role else None
    result = {}
    for s_idx, seg in enumerate(segments):
        held = len({sh.vocab.get('setting') for sh in seg.shots}) <= 1
        role_once = decide(s_idx, 0, seg.energy, seg) if held else None
        for sh_idx, shot in enumerate(seg.shots):
            role = role_once if held else decide(s_idx, sh_idx, shot.energy, seg)
            if role:
                terms = departures[role]
                if seg.thematic_anchor:
                    terms = {t: v for t, v in terms.items() if t != 'mechanisms'}
                new = _borrowed(shot.vocab, terms, role, seed, s_idx, sh_idx, held)
                if new != shot.vocab:
                    result[(s_idx, sh_idx)] = (role, new)
    return result
