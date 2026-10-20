"""Instrument plans, references and worker guards use synthetic media, never GPU or paid services."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from mmv import instrument_assets as assets, instruments as inst, passage_plans, pipeline
from mmv.engine.plan import Segment, Shot, ShotPlan
from mmv.render import get_backend
from mmv.storage import Storage, read_json, write_json
from webapp.mondo_web import ProductionRequest, request_dict
from tests.test_public_app import picture
from tests.test_passage_prerequisites import capture, FIXTURE


def fixture():
    seg = Segment(0, 0, 48, 48, 48, 2, 'continuous', 0, 'verse', .5, 'movement', 2,
                  'daylight', 'wind', 'sealed lips', 0, 2,
                  [Shot(1, 0, 24, None, 'tracking', 'medium', .5), Shot(2, 24, 24, None, 'tracking', 'medium', .5)])
    cast = [{'actor_id': a, 'display_name': a.title(), 'picture_tag': f'<Picture {i+1}>'} for i, a in enumerate(('alice', 'bob'))]
    casting = {'roster': cast, 'segments': {'seg000': {'cast': cast}}}
    score = {'tempo_bpm': 120, 'beat_frames': [0, 12, 24, 36], 'beat_energy': [.8] * 4, 'downbeat_frames': [0]}
    request = {'kind': 'video', 'actors': ['alice', 'bob'], 'instrument_mode': 'perform',
               'instrument_assignments': {'alice': 'guitar', 'bob': 'keyboards'}, 'instrument_references': True}
    return seg, casting, score, request


def test_default_off_is_identical_and_bad_players_are_rejected():
    assert inst.clean({}) is None
    assert inst.clean({'instrument_mode': 'off', 'instrument_assignments': {'unknown': 'invalid'}}) is None
    assert not any(k.startswith('instrument_') for k in request_dict(ProductionRequest()))
    seg, casting, score, request = fixture()
    with pytest.raises(ValueError, match='selected cast actors'):
        inst.plan_passages([seg], casting, score, {**request, 'instrument_assignments': {'reference_1': 'bass'}})
    for change in ({'instrument_assignments': {}}, {'kind': 'ident'}, {'instrument_assignments': {'alice': 'flute'}}):
        with pytest.raises(ValueError):
            inst.plan_passages([seg], casting, score, {**request, **change})


def test_reference_order_tags_activity_and_budget_are_per_passage():
    seg, casting, score, request = fixture()
    paused = {**score, 'beat_energy': [0] * 4}
    performance = inst.plan_passages([seg], casting, score, request, part_scores={'piano': paused})
    passage = performance['passages']['seg000']
    assert passage['references'] == ['guitar']
    assert passage['performers'][0]['source'] == 'mix' and passage['performers'][0]['fallback']
    assert not passage['performers'][1]['active'] and passage['performers'][1]['source'] == 'stem'
    plan = ShotPlan('song.wav', 'fixture', 1, 24, 128, 72, 120, 48, [seg])
    extended = inst.apply_slots(plan, performance, 3)
    assert seg.ref_image_slots == 2 and extended.segments[0].ref_image_slots == 3
    tags = get_backend('local_h3').ref_tags(3, 0, 1)
    job = inst.job(passage, performance, tags)
    assert tags.music_tag == '<Audio 1>'  # H3 numbers audio separately from pictures.
    assert job['performers'][0]['picture_tag'] == '<Picture 1>'
    assert job['performers'][0]['instrument_picture_tag'] == '<Picture 3>'
    assert job['performers'][1]['instrument_picture_tag'] is None
    with pytest.raises(ValueError, match='2 actor references.*1 instrument'):
        inst.apply_slots(plan, performance, 2)
    # Actor not cast => no instrument; shared design occupies just one slot.
    casting['segments']['seg000']['cast'] = casting['roster'][:1]
    request['instrument_assignments']['alice'] = 'keyboards'
    only = inst.plan_passages([seg], casting, score, request, part_scores={'piano': paused})
    assert only['passages']['seg000']['references'] == []
    assert len(only['passages']['seg000']['performers']) == 1
    both = inst.plan_passages([seg], {**casting, 'segments': {'seg000': {'cast': casting['roster']}}}, score,
                              {**request, 'instrument_assignments': {'alice': 'bass', 'bob': 'bass'}})
    assert both['passages']['seg000']['references'] == ['bass']


def test_text_only_and_empty_stem_samples_do_not_invent_silence():
    seg, casting, score, request = fixture()
    performance = inst.plan_passages([seg], casting, score, {**request, 'instrument_references': False},
                                    part_scores={'guitar': {**score, 'beat_energy': []}})
    assert performance['passages']['seg000']['references'] == []
    assert performance['passages']['seg000']['performers'][0]['source'] == 'mix'
    assert performance['passages']['seg000']['performers'][0]['active']
    # Quiet whole-mix energy must never be promoted to a measured guitar pause.
    quiet = inst.plan_passages([seg], casting, {**score, 'beat_energy': [0] * 4}, request)
    guitar = quiet['passages']['seg000']['performers'][0]
    assert all(s['activity'] == 'unknown' and not s['paused'] for s in guitar['shots'])


def test_local_asset_import_preserves_original_checks_hash_and_never_overwrites(tmp_path, monkeypatch):
    monkeypatch.setattr(assets, 'BUNDLED', tmp_path / 'empty')
    store = Storage(tmp_path / 'home')
    assert not any(item['available'] for item in assets.catalog(store))
    data = picture()
    record = assets.import_sheet(store, 'guitar', data, license='test only', provenance='synthetic fixture')
    assert (store.home / 'instruments/guitar/original.image').read_bytes() == data
    assert (record['width'], record['height']) == (64, 80)
    current = assets.locate(store, 'guitar')
    with pytest.raises(ValueError, match='never overwrite'):
        assets.import_sheet(store, 'guitar', data, license='test', provenance='test')
    with pytest.raises(ValueError, match='license'):
        assets.import_sheet(store, 'bass', data, license='', provenance='test')
    inst.verify_assets({'assets': {'guitar': current}})
    (store.home / 'instruments/guitar/reference.png').write_bytes(b'changed')
    with pytest.raises(ValueError, match='checksum'):
        assets.locate(store, 'guitar')
    with pytest.raises(ValueError, match='changed'):
        inst.verify_assets({'assets': {'guitar': current}})


def test_asset_bytes_change_consent_fingerprint_and_plan_binding(tmp_path):
    path = tmp_path / 'reference.png'
    path.write_bytes(picture())
    performance = {'assets': {'guitar': {'path': str(path), 'sha256': assets.sha256(path)}}}
    prepared = {'references': [], 'instruments': performance}
    store = NS(home=tmp_path)
    request = {'backend': 'wavespeed', 'kind': 'video'}
    before = pipeline.fingerprint(store, request, prepared)
    path.write_bytes(b'changed')
    assert pipeline.fingerprint(store, request, prepared) != before
    prepared[passage_plans.KEY] = passage_plans.binding(prepared)
    assert passage_plans.verify(prepared)
    prepared['instruments']['assets'].clear()
    with pytest.raises(ValueError, match='digest mismatch'):
        passage_plans.verify(prepared)
    with pytest.raises(ValueError, match='no binding'):
        passage_plans.verify({'instruments': performance})


def test_guard_requires_each_players_own_action_and_reference_and_respects_pauses():
    seg, casting, score, request = fixture()
    paused = {**score, 'beat_energy': [0] * 4}
    performance = inst.plan_passages([seg], casting, score, request, part_scores={'piano': paused})
    passage = performance['passages']['seg000']
    tags = get_backend('local_h3').ref_tags(3, 0, 1)
    good = '<Subject 1> strums strings of the guitar <Picture 3> while fretting. <Subject 2> rests both hands without playing.'
    assert inst.problems('', [good, good], seg, passage, performance, tags) == []
    for bad in ('<Subject 1> stands near guitar <Picture 3>. <Subject 2> presses keys.',
                '<Subject 1> stands beside guitar pickups and strings <Picture 3>. <Subject 2> rests.',
                '<Subject 1> does not strum strings of <Picture 3>. <Subject 2> rests.',
                '<Subject 1> says "strum strings <Picture 3>". <Subject 2> rests.',
                '<Subject 1> stands, while <Subject 2> strums strings of <Picture 3>.',
                '<Subject 1> strums strings. <Subject 2> rests.',
                'The guitar is on the stage. The keyboard gleams.'):
        assert inst.problems('', [bad, bad], seg, passage, performance, tags)
    # A detail-only shot need not force a player into frame; a later shot still shows them.
    assert inst.problems('', ['The lights glow.', good], seg, passage, performance, tags) == []


def test_natural_phrasing_and_one_binding_then_same_instrument_pass_without_loosening():
    seg, casting, score, request = fixture()
    paused = {**score, 'beat_energy': [0] * 4}
    performance = inst.plan_passages([seg], casting, score, request, part_scores={'piano': paused})
    passage = performance['passages']['seg000']
    tags = get_backend('local_h3').ref_tags(3, 0, 1)
    rest = '<Subject 2> rests both hands without playing.'
    first = f'<Subject 1> leans in, right hand strikes the strings of the guitar <Picture 3>. {rest}'
    # Natural striking verb, no picture tag repeated: the same guitar is named in the later shot.
    later = f'<Subject 1> steps forward and the right hand strikes the guitar strings. {rest}'
    assert inst.problems('', [first, later], seg, passage, performance, tags) == []
    assert inst.problems('', [first, f'<Subject 1> hits the strings of the same guitar. {rest}'], seg, passage, performance, tags) == []
    assert inst.problems('', [first, f'<Subject 1> raking strings on the guitar <Picture 3>. {rest}'], seg, passage, performance, tags) == []
    # Never bound: the first visible shot must still cite the tag.
    assert any('connect' in e for e in inst.problems('', [later, first], seg, passage, performance, tags))
    # Later shots still need this player's own action, the instrument and no negation or other-player text.
    for bad in (f'<Subject 1> stands near the guitar. {rest}',
                f'<Subject 1> right hand strikes the strings. {rest}',
                f'<Subject 1> does not strike the guitar strings. {rest}',
                f'<Subject 1> stands, while <Subject 2> strikes the guitar strings. {rest}',
                f'<Subject 1> strikes the keys of the piano. {rest}'):
        assert inst.problems('', [first, bad], seg, passage, performance, tags), bad
    # Without a reference the pre-existing behaviour is unchanged: no instrument noun is demanded.
    plain = inst.plan_passages([seg], casting, score, {**request, 'instrument_references': False}, part_scores={'piano': paused})
    ptags = get_backend('local_h3').ref_tags(3, 0, 1)
    body = f'<Subject 1> strikes the strings. {rest}'
    assert inst.problems('', [body, body], seg, plain['passages']['seg000'], plain, ptags) == []


def test_guitar_and_keyboard_use_six_stem_cache_only(tmp_path, monkeypatch):
    from mmv import stems
    calls = []
    monkeypatch.setattr(stems, 'cached_dance_part', lambda store, digest, score, model, part: calls.append((model, part)))
    assert inst.cached_scores(NS(), 'hash', tmp_path / 'score.json', {'a': 'guitar', 'b': 'keyboards'}, 'standard', {}) == {}
    assert calls == [('htdemucs_6s', 'guitar'), ('htdemucs_6s', 'piano')]


def test_replay_rejects_changed_settings_even_when_no_reference_was_needed():
    seg, casting, score, request = fixture()
    performance = inst.plan_passages([seg], casting, score, {**request, 'instrument_references': False})
    inst.check_replay({**request, 'instrument_references': False}, performance)
    for changed in ({'instrument_mode': 'off'}, {'instrument_references': True},
                    {'instrument_assignments': {'alice': 'bass', 'bob': 'keyboards'}}):
        with pytest.raises(ValueError, match='saved plan'):
            inst.check_replay({**request, 'instrument_references': False, **changed}, performance)


def test_pronouns_and_continuing_play_do_not_escape_or_falsely_fail_checks():
    seg, casting, score, request = fixture()
    performance = inst.plan_passages([seg], casting, score, request, part_scores={'piano': {**score, 'beat_energy': [0] * 4}})
    passage = performance['passages']['seg000']
    tags = get_backend('local_h3').ref_tags(3, 0, 1)
    good = '<Subject 1> does not stop playing guitar strings of <Picture 3>. <Subject 2> holds both hands still.'
    assert not inst.problems('', [good, good], seg, passage, performance, tags)
    bad = '<Subject 1> strums strings of <Picture 3>. <Subject 2> rests. She presses keyboard keys.'
    assert any('must not play' in e for e in inst.problems('', [bad, good], seg, passage, performance, tags))
    assert any('ambiguous pronoun' in e for e in inst.problems('', [good, 'She strums guitar strings.'], seg, passage, performance, tags))


def test_instrument_worker_rules_tags_cache_and_singing_coexist(tmp_path, monkeypatch):
    settings = {'instrument_mode': 'perform', 'actors': ['fixture_actor'], 'instrument_assignments': {'fixture_actor': 'guitar'}}
    body = '<Subject 1> sings "hello world" while strumming strings of <Picture 2> and fretting the guitar.'
    actual, _, directory, *_ = capture(tmp_path, monkeypatch, 'lip_sync', instrument_settings=settings, body=body)
    call = actual['calls'][0]
    assert inst.RULES in call['system'] and 'instrument_performance' in call['job']
    assert call['job']['audio_tag'] == '<Audio 1>'
    assert call['job']['instrument_performance']['performers'][0]['instrument_picture_tag'] == '<Picture 2>'
    assert 'singing' in call['job']
    assert read_json(directory / 'prompts.json')['seg000']
    second, *_ = capture(tmp_path, monkeypatch, 'lip_sync', instrument_settings=settings, body=body)
    assert not second['calls']
    monkeypatch.setattr(inst, 'problems', lambda *a: ['instrument action missing'])
    with pytest.raises(ValueError, match='validation failed'):
        capture(tmp_path, monkeypatch, 'lip_sync', instrument_settings=settings, body=body)


def test_feedback_is_concrete_per_shot_and_names_wrong_instrument_gestures():
    seg, casting, score, request = fixture()
    performance = inst.plan_passages([seg], casting, score, request, part_scores={'piano': {**score, 'beat_energy': [0] * 4}})
    passage = performance['passages']['seg000']
    tags = get_backend('local_h3').ref_tags(3, 0, 1)
    rest = '<Subject 2> rests both hands without playing.'
    first = f'<Subject 1> right hand strums strings of the guitar <Picture 3> while the left hand frets. {rest}'
    keys = f'<Subject 1> presses keys of the guitar with both hands. {rest}'
    vague = f'<Subject 1> strikes the guitar and plays with vague hand movements. {rest}'
    found = inst.problems('', [first, keys], seg, passage, performance, tags)
    assert len(found) == 1 and found[0].startswith('Shot 2: <Subject 1> must visibly play the guitar')
    assert 'delete the non-guitar gesture in "<Subject 1> presses keys' in found[0] and 'strums the guitar strings' in found[0]
    plain = inst.problems('', [first, vague], seg, passage, performance, tags)
    assert len(plain) == 1 and 'delete' not in plain[0] and 'strings' in plain[0]
    block = inst.retry_feedback(found + found + plain)
    assert block.count('- Shot 2') == 2 and 'Rewrite just the named shots' in block and 'another instrument' in block
    assert block.count('\n- ') == 2
    assert len(inst.retry_feedback([f'Shot {n}: x' for n in range(30)]).splitlines()) <= 12


def test_narrow_guitar_repair_changes_only_unambiguous_active_action():
    seg, casting, score, request = fixture()
    performance = inst.plan_passages([seg], casting, score, request,
                                    part_scores={'piano': {**score, 'beat_energy': [0] * 4}})
    passage = performance['passages']['seg000']
    tags = get_backend('local_h3').ref_tags(3, 0, 1)
    first = '<Subject 1> strums guitar strings <Picture 3>. <Subject 2> rests both hands.'
    vague = '<Subject 1> strikes the guitar <Picture 3> with rapid hand movements. <Subject 2> rests both hands.'
    repaired, shots = inst.repair_shot_bodies([first, vague], seg, passage, performance, tags)
    assert shots == [2] and repaired[0] == first
    assert '<Subject 1> strums the guitar strings while fretting the neck <Picture 3>' in repaired[1]
    assert inst.problems('', repaired, seg, passage, performance, tags) == []
    wrong = '<Subject 1> plays the guitar <Picture 3>, pressing keyboard keys. <Subject 2> rests both hands.'
    assert inst.repair_shot_bodies([first, wrong], seg, passage, performance, tags) == ([first, wrong], [])
    quoted = '<Subject 1> says "I play the guitar" and holds still. <Subject 2> rests both hands.'
    assert inst.repair_shot_bodies([first, quoted], seg, passage, performance, tags) == ([first, quoted], [])
    negated = '<Subject 1> holds the guitar <Picture 3> without playing. <Subject 2> rests both hands.'
    assert inst.repair_shot_bodies([first, negated], seg, passage, performance, tags) == ([first, negated], [])


def test_worker_audits_surgical_guitar_repair_and_validates_result(tmp_path, monkeypatch):
    settings = {'instrument_mode': 'perform', 'actors': ['fixture_actor'],
                'instrument_assignments': {'fixture_actor': 'guitar'}}
    body = '<Subject 1> strikes the guitar <Picture 2> with fast hand movement.'
    actual, _, directory, *_ = capture(tmp_path, monkeypatch, 'sealed', instrument_settings=settings, body=body)
    assert len(actual['calls']) == 1
    receipt = read_json(directory / 'seg000.instrument-repair-1.json')
    assert receipt == {'shots': [1], 'action': inst.GUITAR_CONTACT}
    prompt = read_json(directory / 'prompts.json')['seg000']
    assert inst.GUITAR_CONTACT in prompt and body not in prompt
    assert '<Subject 1> strikes the guitar' in (directory / 'seg000.writer-1.json').read_text()


def test_worker_does_not_repair_wrong_instrument_gesture(tmp_path, monkeypatch):
    settings = {'instrument_mode': 'perform', 'actors': ['fixture_actor'],
                'instrument_assignments': {'fixture_actor': 'guitar'}}
    body = '<Subject 1> plays the guitar <Picture 2>, fingers pressing keyboard keys.'
    actual, _, directory, *_ = capture(tmp_path, monkeypatch, 'sealed', instrument_settings=settings,
                                        body=body, expect=ValueError, match='validation failed')
    assert len(actual['calls']) == 1
    assert not list(directory.glob('*.instrument-repair-*.json'))
    assert not read_json(directory / 'prompts.json', {})


def test_instrument_off_preserves_golden_worker(tmp_path, monkeypatch):
    import json
    actual, *_ = capture(tmp_path, monkeypatch, 'sealed', instrument_mode='off', instrument_assignments={'bad': 'bad'})
    assert actual == json.loads(FIXTURE.read_text())['sealed']
