"""Deterministic contextual vocabulary selection: pure, no services, no real data."""
import copy

from mmv import vocab_select as vs
from mmv.pipeline import load_vocabulary


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
    assert vocab is not None
    a, b = vs.contextual_vocabulary(vocab, 1), vs.contextual_vocabulary(vocab, 2)
    for name in vs.ROTATION_TABLES:
        if isinstance(vocab.get(name), list):
            assert a[name] and b[name] and len(a[name]) <= len(vocab[name])
    assert any(a[n] != b[n] for n in vs.ROTATION_TABLES if isinstance(vocab.get(n), list))


def _segment(index, energy, montage, shot_vocabs, anchor=None):
    from mmv.engine.plan import Segment, Shot
    shots = [Shot(n=i + 1, start_frame=0, frames=24, cut_time=None, camera='', shot_scale='', energy=energy, vocab=dict(v))
             for i, v in enumerate(shot_vocabs)]
    return Segment(index=index, song_start_frame=0, musical_frames=0, gen_frames=0, trim_frames=0, duration_input=0.0,
                   montage_type=montage, section_index=0, section_label='', energy=energy, thematic_anchor=anchor,
                   ref_image_slots=0, footage_anchor='', practical_effects='', rigging='', audio_slice_start_s=0.0,
                   audio_slice_end_s=0.0, shots=shots)


DEPARTURES = {role: {'settings': [f'{role} place {i}' for i in range(6)], 'lighting': [f'{role} light {i}' for i in range(6)],
                     'mechanisms': [f'{role} device {i}' for i in range(6)]} for role in vs.ROLES}


def test_pick_role_calm_stays_home_and_peak_departs():
    assert all(vs.pick_role(vs.departure_score(0.3, 0.4, 50), d) is None for d in range(100))
    assert {vs.pick_role(0.95, d) for d in range(100)} == {'tangent', 'opposite', 'mirror'}
    assert {vs.pick_role(0.7, d) for d in range(100)} == {'mirror', 'tangent', None}
    assert vs.departure_score(0.9, 0.9, 0) < vs.departure_score(0.9, 0.9, 100)


def test_departures_are_pure_deterministic_and_keep_slots():
    rotating = [{'setting': 'a', 'subject_type': 's', 'mechanism': 'm', 'lighting': 'l', 'costume': 'c'},
                {'setting': 'b', 'subject_type': 's', 'mechanism': 'm', 'lighting': 'l', 'costume': 'c'}]
    segments = [_segment(0, 0.95, 'chaotic', rotating), _segment(1, 0.2, 'chaotic', rotating)]
    before = copy.deepcopy(segments)
    first = vs.plan_world_departures(segments, DEPARTURES, 5, 100)
    assert segments == before and first == vs.plan_world_departures(segments, DEPARTURES, 5, 100)
    assert first and all(s_idx == 0 for s_idx, _ in first)           # the calm passage never departs
    for (s_idx, sh_idx), (role, vocab) in first.items():
        assert set(vocab) == set(rotating[0])                           # no keys added
        assert vocab['subject_type'] == 's' and vocab['costume'] == 'c' # cast-facing slots untouched
        assert vocab['setting'].startswith(role)
    assert vs.plan_world_departures(segments, {}, 5, 100) == {}


def test_held_passage_keeps_one_setting_and_anchor_mechanism():
    held = [{'setting': 'a', 'mechanism': 'm', 'lighting': f'l{i}'} for i in range(4)]
    result = vs.plan_world_departures([_segment(0, 1.0, 'standard', held, anchor='clock')], DEPARTURES, 9, 100)
    assert len(result) == 4 and len({v['setting'] for _, v in result.values()}) == 1
    assert {v['mechanism'] for _, v in result.values()} == {'m'}


def test_single_configured_role_still_departs_at_moderate_energy():
    shots = [{'setting': f's{i}', 'lighting': 'l'} for i in range(8)]
    segments = [_segment(i, 0.75, 'chaotic', shots) for i in range(6)]
    result = vs.plan_world_departures(segments, {'opposite': DEPARTURES['opposite']}, 3, 50)
    assert result and {role for role, _ in result.values()} == {'opposite'}


def test_select_term_for_energy_scales_pool_depth():
    table = [f'term_{i}' for i in range(20)]
    low_picks = {vs.select_term_for_energy(table, 0.0, seed=7, section_idx=0, shot_idx=i) for i in range(50)}
    high_picks = {vs.select_term_for_energy(table, 1.0, seed=7, section_idx=0, shot_idx=i) for i in range(50)}
    # At energy 0.0, min_ratio=0.20 confines choices to the first 4 terms (20% of 20)
    assert low_picks <= set(table[:4])
    # At energy 1.0, full pool is accessible, including terms beyond index 4
    assert any(p in set(table[4:]) for p in high_picks)
    assert vs.select_term_for_energy([], 0.5, 7, 0, 0) == ''


def test_apply_energy_scaled_vocabulary_stacks_at_high_energy_and_preserves_anchors():
    vocab = {
        'settings': [f'place_{i}' for i in range(10)],
        'mechanisms': [f'mech_{i}' for i in range(10)],
        'lighting': [f'light_{i}' for i in range(10)],
    }
    calm_shots = [{'setting': 's0', 'mechanism': 'm0', 'lighting': 'l0'},
                  {'setting': 's1', 'mechanism': 'm1', 'lighting': 'l1'}]
    peak_shots = [{'setting': 's0', 'mechanism': 'm0', 'lighting': 'l0'},
                  {'setting': 's1', 'mechanism': 'm1', 'lighting': 'l1'}]
    anchored_shots = [{'setting': 's0', 'mechanism': 'anchor_mech', 'lighting': 'l0'}]

    segments = [
        _segment(0, 0.15, 'chaotic', calm_shots),
        _segment(1, 0.90, 'chaotic', peak_shots),
        _segment(2, 0.90, 'standard', anchored_shots, anchor='anchor_mech'),
    ]
    before = copy.deepcopy(segments)
    updates = vs.apply_energy_scaled_vocabulary(segments, vocab, seed=42)
    assert segments == before  # Pure: does not mutate input segments

    # Calm segment (index 0) draws single terms from the top 20-35% slice (no comma stacking)
    assert ',' not in updates[(0, 0)]['mechanism']
    assert updates[(0, 0)]['setting'] in vocab['settings'][:4]

    # High-energy segment (index 1, energy 0.90 >= 0.80) stacks secondary mechanism/lighting tags
    assert ',' in updates[(1, 0)]['mechanism'] or ',' in updates[(1, 1)]['mechanism']
    assert ',' in updates[(1, 0)]['lighting'] or ',' in updates[(1, 1)]['lighting']

    # Anchored segment (index 2) preserves its thematic_anchor mechanism
    assert updates[(2, 0)]['mechanism'] == 'anchor_mech'

