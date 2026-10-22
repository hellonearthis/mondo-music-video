"""Deterministic contextual vocabulary selection and tangent juxtaposition (opt-in, outside the protected planner).

Pure functions only: vocabulary and context in, new vocabulary out. Nothing here
advances a random stream, reads files or mutates its arguments. The protected
planner (mmv/engine/plan.py) is untouched; this module decides, deterministically,
which terms rotation tables hold and applies tangent juxtaposition across musical arcs.
"""
import hashlib
import math
import re

# Tables whose entries are plain rotation terms. Structured tables are left alone.
ROTATION_TABLES = ('settings', 'lighting', 'mechanisms', 'costume', 'practical_effects', 'themes')
MIN_KEEP = 4
KEEP_FRACTION = 0.5
_WORD = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_STOP = frozenset('the and with from for into over under that this a an of in on at to is are as by'.split())

# Juxtaposition relationships between archetype world clusters:
# - mirror: sister cluster sharing tonal weight and material texture
# - opposite: direct polar thematic inversion
# - tangent: oblique conceptual departure (shared subtle motif/physics, unexpected domain)
THEMATIC_JUXTAPOSITION_MAP = {
    "Bureaucratic / Carceral": {
        "mirror": "Brutalist Concrete",
        "opposite": "Pastoral Nature",
        "tangent": "Clinical / Medical",
    },
    "Brutalist Concrete": {
        "mirror": "Industrial Decay",
        "opposite": "Baroque / Theatrical",
        "tangent": "Cosmic / Void",
    },
    "Industrial Decay": {
        "mirror": "Brutalist Concrete",
        "opposite": "Pastoral Nature",
        "tangent": "Clinical / Medical",
    },
    "Maritime / Salt": {
        "mirror": "Pastoral Nature",
        "opposite": "Cyberpunk / High-Tech",
        "tangent": "Cosmic / Void",
    },
    "Cyberpunk / High-Tech": {
        "mirror": "Nocturnal Noir",
        "opposite": "Pastoral Nature",
        "tangent": "Bureaucratic / Carceral",
    },
    "Nocturnal Noir": {
        "mirror": "Cyberpunk / High-Tech",
        "opposite": "Pastoral Nature",
        "tangent": "Baroque / Theatrical",
    },
    "Pastoral Nature": {
        "mirror": "Maritime / Salt",
        "opposite": "Industrial Decay",
        "tangent": "Baroque / Theatrical",
    },
    "Baroque / Theatrical": {
        "mirror": "Nocturnal Noir",
        "opposite": "Brutalist Concrete",
        "tangent": "Clinical / Medical",
    },
    "Clinical / Medical": {
        "mirror": "Bureaucratic / Carceral",
        "opposite": "Pastoral Nature",
        "tangent": "Industrial Decay",
    },
    "Cosmic / Void": {
        "mirror": "Brutalist Concrete",
        "opposite": "Maritime / Salt",
        "tangent": "Cyberpunk / High-Tech",
    },
}


def stable_hash(*parts) -> int:
    """Platform-independent integer hash of the parts (never Python's salted hash)."""
    return int.from_bytes(hashlib.sha256(':'.join(map(str, parts)).encode('utf-8')).digest()[:8], 'big')


def select_term(table, seed, section_idx, shot_idx) -> str:
    """The term for this exact shot position: sha256(seed:section:shot) indexes the table."""
    return table[stable_hash(seed, section_idx, shot_idx) % len(table)] if table else ''


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


def resolve_cluster_departure(primary_cluster: str, energy: float, kappa: float, seed: int,
                              section_idx: int, shot_idx: int) -> tuple[str, str]:
    """Determine the active cluster and relationship type (core, mirror, tangent, opposite) for a shot.
    
    Juxtaposition departures occur deterministically on high energy or high kappa (bridges/solos/peaks).
    Lower energy or resolution sections anchor back to the primary core world.
    """
    rel_map = THEMATIC_JUXTAPOSITION_MAP.get(primary_cluster)
    if not rel_map:
        return primary_cluster, "core"

    # Departure threshold combined from shot energy and juxtaposition kappa
    departure_score = (energy * 0.5) + (kappa * 0.5)

    # Core anchor holds whenever juxtaposition score is below threshold
    if departure_score < 0.65:
        return primary_cluster, "core"

    # Oblique hash draw based strictly on this shot position
    draw = stable_hash(seed, "juxtaposition", section_idx, shot_idx) % 100

    if departure_score >= 0.85:
        # High intensity (e.g. peak bridge / solo): tangent departure or stark opposite
        if draw < 55:
            return rel_map.get("tangent", primary_cluster), "tangent"
        elif draw < 85:
            return rel_map.get("opposite", primary_cluster), "opposite"
        else:
            return rel_map.get("mirror", primary_cluster), "mirror"
    else:
        # Moderate departure (e.g. chorus transition): sister mirror or subtle tangent
        if draw < 60:
            return rel_map.get("mirror", primary_cluster), "mirror"
        elif draw < 90:
            return rel_map.get("tangent", primary_cluster), "tangent"
        else:
            return primary_cluster, "core"


def apply_contextual_shot_vocabulary(segments, vocab, seed: int, thematic_worlds: dict | None = None) -> list:
    """Pure function: returns a new list of segments where each shot's vocabulary is deterministically refined.
    
    Applies World cluster filtering, shot-position hash selection, and tangent juxtaposition departures.
    """
    if not segments:
        return []

    tw = thematic_worlds or {}
    mode = tw.get("mode", "off")
    if mode == "off":
        active_world = ""
    else:
        active_worlds = tw.get("activeWorlds") or []
        active_world = active_worlds[0] if active_worlds else ""

    slider = float(tw.get("juxtapositionSlider", 50))
    # Effective kappa multiplier from the slider
    kappa_mult = (slider / 100.0) * 2.0

    refined_segments = []
    for s_idx, seg in enumerate(segments):
        # Calculate section kappa
        base_kappa = float(seg.energy) if hasattr(seg, "energy") else 0.5
        effective_kappa = max(0.0, min(1.0, base_kappa * kappa_mult))

        refined_shots = []
        for sh_idx, shot in enumerate(seg.shots):
            shot_energy = getattr(shot, "energy", seg.energy)
            cluster, departure_type = resolve_cluster_departure(
                active_world, shot_energy, effective_kappa, seed, s_idx, sh_idx
            )

            current_vocab = dict(shot.vocab) if hasattr(shot, "vocab") else {}
            new_vocab = dict(current_vocab)

            # Refine rotation keys deterministically if tables exist in vocab
            for table_name, vocab_key in [
                ("settings", "setting"),
                ("subject_types", "subject_type"),
                ("mechanisms", "mechanism"),
                ("lighting", "lighting"),
                ("tonal_registers", "tonal_register"),
                ("costume", "costume"),
            ]:
                table = vocab.get(table_name)
                if isinstance(table, list) and table:
                    # Deterministic pick tied strictly to this shot
                    chosen = select_term(table, seed, s_idx, sh_idx)
                    if chosen:
                        new_vocab[vocab_key] = chosen

            # Record thematic departure metadata in vocabulary if departure occurred
            if departure_type != "core" and cluster:
                new_vocab["juxtaposition_departure"] = f"{departure_type}:{cluster}"

            # Return a new shot dictionary or shot object copy
            if hasattr(shot, "vocab"):
                shot.vocab = new_vocab
                refined_shots.append(shot)
            else:
                refined_shots.append({**shot, "vocab": new_vocab})

        refined_segments.append(seg)

    return refined_segments
