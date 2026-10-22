"""Deterministic contextual vocabulary selection and tangent juxtaposition: pure, no services, no real data."""
import copy
from dataclasses import dataclass

from mmv import vocab_select as vs
from mmv.pipeline import load_vocabulary


def test_select_term_is_deterministic_and_position_bound():
    table = [f"t{i}" for i in range(20)]
    assert vs.select_term(table, 7, 1, 2) == vs.select_term(table, 7, 1, 2)
    assert len({vs.select_term(table, 7, 1, shot) for shot in range(40)}) > 5
    assert vs.select_term([], 7, 0, 0) == ''


def test_contextual_vocabulary_is_pure_stable_and_narrowed():
    vocab = {'settings': ['archive stairwell', 'beach at noon', 'records annex', 'forest glade',
                          'carceral cell', 'desert road', 'harbor pier', 'office cubicle'],
             'camera_by_energy': {'0': 'static'}}
    before = copy.deepcopy(vocab)
    first = vs.contextual_vocabulary(vocab, 3, ['a clerk in an archive records office'])
    assert vocab == before
    assert first == vs.contextual_vocabulary(vocab, 3, ['a clerk in an archive records office'])
    assert len(first['settings']) == 4 and set(first['settings']) <= set(vocab['settings'])
    assert {'archive stairwell', 'records annex', 'office cubicle'} <= set(first['settings'])
    assert first['camera_by_energy'] == vocab['camera_by_energy']


def test_seed_changes_tiebreaks_but_never_empties_a_table():
    vocab = load_vocabulary('full')
    a, b = vs.contextual_vocabulary(vocab, 1), vs.contextual_vocabulary(vocab, 2)
    for name in vs.ROTATION_TABLES:
        if isinstance(vocab.get(name), list):
            assert a[name] and b[name] and len(a[name]) <= len(vocab[name])
    assert any(a[n] != b[n] for n in vs.ROTATION_TABLES if isinstance(vocab.get(n), list))


def test_resolve_cluster_departure_tangents_and_mirrors():
    # Low energy remains firmly at the core anchor
    world, dep = vs.resolve_cluster_departure("Industrial Decay", energy=0.2, kappa=0.2, seed=42, section_idx=0, shot_idx=0)
    assert world == "Industrial Decay"
    assert dep == "core"

    # High energy + high kappa triggers tangent, opposite, or mirror departure
    departures = [
        vs.resolve_cluster_departure("Industrial Decay", energy=0.95, kappa=0.9, seed=seed, section_idx=1, shot_idx=i)
        for seed in range(5) for i in range(4)
    ]
    departure_types = {d[1] for d in departures}
    clusters = {d[0] for d in departures}

    assert "core" not in departure_types
    assert {"tangent", "opposite", "mirror"} & departure_types
    # Clinical / Medical is the tangent for Industrial Decay
    assert "Clinical / Medical" in clusters or "Brutalist Concrete" in clusters or "Pastoral Nature" in clusters


@dataclass
class DummyShot:
    n: int
    energy: float
    vocab: dict


@dataclass
class DummySegment:
    energy: float
    shots: list


def test_apply_contextual_shot_vocabulary():
    shots = [DummyShot(n=1, energy=0.2, vocab={}), DummyShot(n=2, energy=0.9, vocab={})]
    segments = [DummySegment(energy=0.8, shots=shots)]
    vocab = {
        "settings": ["concrete vault", "operating room", "rust mill"],
        "mechanisms": ["hydraulic piston", "scalpel tray", "clock gear"],
    }
    thematic_worlds = {
        "mode": "guided",
        "activeWorlds": ["Industrial Decay"],
        "juxtapositionSlider": 80,
    }

    refined = vs.apply_contextual_shot_vocabulary(segments, vocab, seed=123, thematic_worlds=thematic_worlds)
    assert len(refined) == 1
    # Check that shot vocab has been deterministically populated
    assert "setting" in refined[0].shots[0].vocab
    assert "mechanism" in refined[0].shots[0].vocab
    # Higher energy shot 2 should have departure metadata
    assert "juxtaposition_departure" in refined[0].shots[1].vocab
