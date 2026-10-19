"""Worker boundary golden recordings: no services, GPU, or production media."""
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest
from mmv import worker, pipeline
from mmv.storage import read_json, write_json
from mmv.engine.plan import Shot, Segment, ShotPlan
from webapp.mondo_web import ProductionRequest, request_dict

FIXTURE = Path(__file__).parent / 'fixtures' / 'passage_worker_golden.json'

class StopBeforeRender(Exception):
    pass


def capture(tmp_path, monkeypatch, mode, *, reject_cached=None, dance_settings=None, body=None, **request_fields):
    home, directory = tmp_path / 'home', tmp_path / 'run'
    directory.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('MMV_HOME', str(home))
    request = request_dict(ProductionRequest(backend='wavespeed', mouth_mode=mode))
    request.update(request_fields)  # Future worker fields; API still rejects them until BONK step 1.
    seg = Segment(0, 0, 48, 48, 48, 2, 'continuous', 0, 'verse', .5, 'movement', 1,
                  'daylight', 'wind', 'sealed lips', 0, 2,
                  [Shot(1, 0, 48, None, 'tracking', 'medium', .5, {})])
    plan = ShotPlan('song.wav', 'fixture', 1, 24, 128, 72, 120, 48, [seg])
    member = {'actor_id': 'fixture_actor', 'display_name': 'Fixture Actor', 'sheet': 'fixture.png',
              'sheet_path': 'fixture.png', 'picture_tag': '<Picture 1>'}
    singing = {'singing': True, 'actor_id': 'fixture_actor', 'picture_tag': '<Picture 1>',
               'lines': [{'start': 0, 'end': 2, 'text': 'hello world'}]}
    prepared = {'settings': {'writer_mode': 'api'}, 'plan': asdict(plan), 'score': {},
                'casting': {'roster': [member], 'segments': {'seg000': {'cast': [member]}}},
                'style': {'direction': 'Soft daylight and moving fabric.'},
                'lipsync': {'passages': {'seg000': singing}} if mode == 'lip_sync' else None}
    if dance_settings:
        from mmv import dance
        prepared['dance'] = dance.plan_passages([seg], prepared['casting'], {'tempo_bpm': 120.0, 'beats_per_bar': 4,
                                                'beat_frames': [0, 12, 24, 36], 'downbeat_frames': [0]}, dance_settings,
                                                singer='fixture_actor' if mode == 'lip_sync' else None)
    write_json(directory / 'request.json', request)
    write_json(directory / 'prepared.json', prepared)
    monkeypatch.setattr(worker, 'Storage', Mock(return_value=NS(home=home, key=lambda *a: '', actor=lambda *a: {'description': 'Blue jacket'})))
    # Actual composition, job construction, response parsing and assembly; record validator calls.
    trace, calls = [], []
    def writer(_unused, system, user, *args, **kwargs):
        calls.append({'system': system, 'job': json.loads(user)})
        return True, json.dumps({'style_opening': 'Daylight photography.', 'shot_bodies': [
            body or '<Subject 1> sings "hello world" while moving through the light.'], 'overall_soundscape': 'Wind.'}), ''
    monkeypatch.setattr('mmv.engine.writer.call_llm', writer)
    def check(name):
        def validate(*args, **kwargs):
            trace.append({'name': name, 'prompt': args[0], 'silent_mouths': kwargs.get('silent_mouths')})
            if name == reject_cached and sum(c['name'] == name for c in trace) == 1:
                return ['rejected cached prompt']
            return []
        return validate
    monkeypatch.setattr('mmv.engine.schema.validate_prompt', check('schema'))
    monkeypatch.setattr('mmv.quality.prompt_problems', check('quality'))
    monkeypatch.setattr('mmv.lipsync.lipsync_problems', check('singing'))
    validator = Mock()
    validator.run_clipboard.side_effect = lambda *a, **kw: (check('laya')(*a, **kw), [])
    validator.last_clipboard_request = {}
    validator.format_retry_feedback.side_effect = lambda problems: '; '.join(problems)
    monkeypatch.setattr('mmv.engine.validators.LayaSemanticValidator', Mock(return_value=validator))
    monkeypatch.setattr('mmv.runtime.stop_process', lambda *a: (_ for _ in ()).throw(StopBeforeRender()))
    with pytest.raises(StopBeforeRender):
        worker.run(home, directory)
    cache = sorted((home / 'cache' / 'prompts').glob('*.json'))
    return {'calls': calls, 'validation': trace, 'cache_keys': [p.stem for p in cache]}, home, directory, request, prepared


@pytest.mark.parametrize('mode', ['sealed', 'natural', 'lip_sync'])
def test_worker_golden(tmp_path, monkeypatch, mode):
    actual, *_ = capture(tmp_path, monkeypatch, mode)
    expected = json.loads(FIXTURE.read_text())[mode]
    assert actual == expected


@pytest.mark.parametrize('mode', ['sealed', 'natural', 'lip_sync'])
def test_off_fields_preserve_worker(tmp_path, monkeypatch, mode):
    actual, *_ = capture(tmp_path, monkeypatch, mode, dance_mode='off', dancers=[], dance_direction='ignored')
    assert actual == json.loads(FIXTURE.read_text())[mode]


def test_legacy_quote_fingerprints():
    store = NS(home=Path('/unused'))
    recorded = json.loads(FIXTURE.read_text())['fingerprints']
    for fields, expected in recorded:
        request = request_dict(ProductionRequest(backend='wavespeed', **fields))
        assert pipeline.fingerprint(store, request, {'references': [], 'lipsync': None}) == expected


def test_singing_cache_reuses_effective_system_and_checks_hit(tmp_path, monkeypatch):
    first, home, directory, *_ = capture(tmp_path, monkeypatch, 'lip_sync')
    second, *_ = capture(tmp_path, monkeypatch, 'lip_sync')
    assert not second['calls']
    assert [c['name'] for c in second['validation']] == ['schema', 'singing', 'quality']
    assert read_json(directory / 'prompts.json')['seg000'] == first['validation'][0]['prompt']


@pytest.mark.parametrize('source', ['cache', 'run'])
@pytest.mark.parametrize('rejection', ['problems', 'exception'])
def test_cache_hook_rejects_bad_hits(tmp_path, source, rejection):
    cache, runs = tmp_path / 'cache', tmp_path / 'runs'
    cache.mkdir()
    seg = NS(segment_id='seg000')
    if source == 'cache':
        worker.save_cached_passage_prompt(cache, 'system', {}, 'bad', 'seg000', validators_version='dance-v1')
    else:
        run = runs / 'old'
        (run / 'writer_jobs').mkdir(parents=True)
        write_json(run / 'writer_jobs' / 'seg000.json', {})
        (run / 'writer_system.md').write_text('system')
        write_json(run / 'prompts.json', {'seg000': 'bad'})
    def reject(prompt):
        assert prompt == 'bad'
        if rejection == 'exception':
            raise ValueError('invalid body')
        return ['missing choreography']
    assert worker.find_cached_passage_prompt(cache, runs, 'system', {}, seg, None,
                                             extra_validators=[reject], validators_version='dance-v1') is None


def test_cache_version_is_opt_in_and_clear_time_still_applies(tmp_path):
    job = {'segment_id': 'seg000'}
    old = hashlib.sha256(('validated-v2\nsystem\n---\n' + json.dumps(job, sort_keys=True)).encode()).hexdigest()
    assert worker.passage_cache_key('system', job) == old
    assert worker.passage_cache_key('system', job, 'dance-v1') != old
    worker.save_cached_passage_prompt(tmp_path, 'system', job, 'ok', 'seg000')
    seg = NS(segment_id='seg000')
    assert worker.find_cached_passage_prompt(tmp_path, None, 'system', job, seg, None) == 'ok'
    assert worker.find_cached_passage_prompt(tmp_path, None, 'system', job, seg, None, validators_version='dance-v1') is None
    assert worker.find_cached_passage_prompt(tmp_path, None, 'system', job, seg, None, cleared_at=1e20) is None


@pytest.mark.parametrize('validator', ['schema', 'singing', 'quality'])
def test_singing_cache_failure_returns_to_validated_writer_path(tmp_path, monkeypatch, validator):
    capture(tmp_path, monkeypatch, 'lip_sync')
    result, *_ = capture(tmp_path, monkeypatch, 'lip_sync', reject_cached=validator)
    assert len(result['calls']) == 1
    assert [c['name'] for c in result['validation']][-4:] == ['schema', 'quality', 'singing', 'laya']
