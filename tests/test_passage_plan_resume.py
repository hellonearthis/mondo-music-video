"""Adversarial saved-plan replay without GPU, writer or renderer services."""
from copy import deepcopy
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest
from mmv import pipeline, passage_plans as pp, worker
from mmv.storage import read_json, write_json
from webapp.mondo_web import ProductionRequest


def saved_run(tmp_path):
    saved = {'lipsync': {'passages': {'seg000': {'singing': True, 'lines': ['original']}}},
             'dance': {'version': 1, 'passages': {'seg000': {'dancing': True}}}}
    saved[pp.KEY] = pp.binding(saved)
    write_json(tmp_path / 'prepared.json', saved)
    write_json(tmp_path / 'prompts.json', {'seg000': 'validated original'})
    pp.bind_prompts(tmp_path, saved, {'seg000': 'validated original'})
    return saved


def test_restore_saved_decisions_and_recheck_current_inputs(tmp_path, monkeypatch):
    saved = saved_run(tmp_path)
    current = {'settings': {'changed': True}, 'lipsync': {'passages': 'new planner'}, 'dance': None}
    replayed = pp.restore(current, saved)
    assert replayed['lipsync'] == saved['lipsync']
    assert replayed['dance'] == saved['dance']
    assert replayed['settings'] == current['settings']
    replayed['lipsync']['passages'].clear()
    assert saved['lipsync']['passages']  # never mutate the saved object
    prepare = Mock(return_value=current)
    monkeypatch.setattr(pipeline, 'prepare', prepare)
    assert pipeline.prepare_resume(NS(), {}, tmp_path) == current
    prepare.assert_called_once_with(prepare.call_args.args[0], {}, saved_prepared=saved)


@pytest.mark.parametrize('mutation', ['plan', 'dance', 'version', 'digest', 'null', 'prompts', 'missing_manifest'])
def test_mismatch_stops_before_preparation_or_worker(tmp_path, monkeypatch, mutation):
    saved = saved_run(tmp_path)
    if mutation == 'plan': saved['lipsync']['passages'].clear()
    if mutation == 'dance': saved['dance']['version'] = 9
    if mutation == 'version': saved[pp.KEY]['version'] = 999
    if mutation == 'digest': saved[pp.KEY]['digest'] = 'wrong'
    if mutation == 'null': saved[pp.KEY] = None
    if mutation == 'prompts': write_json(tmp_path / 'prompts.json', {'seg000': 'changed'})
    if mutation == 'missing_manifest': (tmp_path / 'passage-plan-prompts.json').unlink()
    write_json(tmp_path / 'prepared.json', saved)
    prepare = Mock()
    monkeypatch.setattr(pipeline, 'prepare', prepare)
    with pytest.raises(ValueError, match='digest mismatch'):
        pipeline.prepare_resume(NS(), {}, tmp_path)
    prepare.assert_not_called()
    # Direct worker resume also refuses before loading the engine or rendering.
    write_json(tmp_path / 'request.json', {})
    monkeypatch.setattr(worker, 'Storage', Mock())
    monkeypatch.setenv('MMV_HOME', str(tmp_path))
    with pytest.raises(ValueError, match='digest mismatch'):
        worker.run(tmp_path, tmp_path, resume=True)


def test_produce_checks_before_overwriting_or_launching(tmp_path):
    saved = saved_run(tmp_path)
    current = {**saved, 'lipsync': {'passages': 'changed'}}
    command = Mock()
    with pytest.raises(ValueError, match='digest mismatch'):
        pipeline.produce(NS(), {}, current, NS(log_path=tmp_path / 'log', command=command), resume=True)
    command.assert_not_called()
    assert read_json(tmp_path / 'prepared.json') == saved


def test_legacy_without_metadata_replans_unchanged(tmp_path, monkeypatch):
    saved = {'lipsync': {'passages': 'old'}}
    write_json(tmp_path / 'prepared.json', saved)
    current = {'lipsync': {'passages': 'today'}}
    assert pp.restore(current, saved) is current
    assert not pp.verify(saved)
    monkeypatch.setattr(pipeline, 'prepare', Mock(return_value=current))
    assert pipeline.prepare_resume(NS(), {}, tmp_path) == current


def test_binding_metadata_does_not_change_fingerprint():
    request = ProductionRequest(backend='wavespeed').model_dump()
    prepared = {'references': [], 'lipsync': {'passages': {}}}
    assert pipeline.fingerprint(NS(), request, prepared) == pipeline.fingerprint(NS(), request,
        {**prepared, pp.KEY: pp.binding(prepared)})


@pytest.mark.parametrize('legacy', [False, True])
def test_real_prepare_skips_only_saved_passage_planner(tmp_path, monkeypatch, legacy):
    from mmv.engine.analyze import ScoreMap, Section
    from mmv.engine.plan import ShotPlan, Segment, Shot
    from mmv.storage import Storage
    store = Storage(tmp_path / 'home')
    (store.home / 'uploads' / 'song.wav').write_bytes(b'synthetic song')
    settings = {**store.settings(), 'writer_model': 'mock', 'writer_mode': 'api', 'writer_call_estimate': .01}
    monkeypatch.setattr(store, 'settings', lambda: settings)
    monkeypatch.setattr(store, 'key', lambda *args: 'mock key')
    monkeypatch.setattr('mmv.engine.validators.laya_semantic._model_dir_staged', lambda *a: True)
    monkeypatch.setattr(pipeline, 'references', lambda *a: ([], []))
    monkeypatch.setattr(pipeline.subprocess, 'run', Mock(return_value=NS(returncode=0)))
    score = ScoreMap('synthetic', 48, 22050, 120, 4, sections=[Section(0, 48, 0, .5, 'mid')])
    monkeypatch.setattr(ScoreMap, 'from_json', Mock(return_value=score))
    seg = Segment(0, 0, 48, 48, 48, 2, 'continuous', 0, 'mid', .5, 'movement', 0,
                  'daylight', 'wind', 'sealed lips', 0, 2, [Shot(1, 0, 48, None, 'tracking', 'medium', .5)])
    plan = ShotPlan('song.wav', 'fixture', 1, 24, 128, 72, 120, 48, [seg])
    structure_planner = Mock(return_value=plan)
    monkeypatch.setattr('mmv.engine.plan.plan', structure_planner)
    lip_planner = Mock(return_value={'passages': {'seg000': {'singing': False, 'reason': 'new planner'}}})
    monkeypatch.setattr('mmv.lipsync.plan_passages', lip_planner)
    backend = Mock(max_gen_frames=1000, min_reference_images=0)
    backend.capabilities.return_value = {'max_reference_images': 3}
    backend.plan_resolution.return_value = (128, 72)
    backend.cost_for.return_value = 0
    monkeypatch.setattr('mmv.render.get_backend', lambda *a: backend)
    request = ProductionRequest(backend='wavespeed', song='song.wav', mouth_mode='lip_sync').model_dump()
    saved = saved_run(tmp_path)
    if legacy:
        saved.pop(pp.KEY)
        saved.pop('dance', None)                      # a pre-dance run has no dance plan; a dance plan without its binding is refused
    result = pipeline.prepare(store, request, saved_prepared=saved)
    structure_planner.assert_called_once()  # current input/structure checks remain active
    if legacy:
        lip_planner.assert_called_once()
        assert result['lipsync'] == lip_planner.return_value
    else:
        lip_planner.assert_not_called()
        assert result['lipsync'] == saved['lipsync']
        assert result['dance'] == saved['dance']


def test_web_resume_quote_and_start_all_replay_saved_plan(tmp_path, monkeypatch):
    # Call the actual route functions without a socket server or ASGI transport.
    from webapp.mondo_web import create_app, ResumeRequest, StartRequest
    from mmv import production
    app = create_app(tmp_path / 'home', test_hosts=True)
    directory = app.state.store.home / 'runs' / 'resume-test'
    directory.mkdir()
    saved = saved_run(directory)
    request = ProductionRequest(backend='comfy_sdk_h3').model_dump()
    write_json(directory / 'request.json', request)
    write_json(directory / 'consent.json', {'accepted': True, 'fingerprint': 'unchanged'})
    preparations = []
    def prepare(store, req, *, saved_prepared=None):
        preparations.append(deepcopy(saved_prepared))
        return pp.restore({'references': [], 'segments': [{'index': 0}], 'seconds': 2,
                           'estimate': 0, 'plan': {}, 'score': {}}, saved_prepared)
    monkeypatch.setattr(pipeline, 'prepare', prepare)
    monkeypatch.setattr(production, 'fingerprint', lambda *a: 'unchanged')
    monkeypatch.setattr('webapp.mondo_web.score_view.build_score', lambda *a: {})
    launch = Mock(return_value={'id': 'resume-test'})
    monkeypatch.setattr(app.state.jobs, 'start', launch)
    routes = {r.path: r.endpoint for r in app.routes if hasattr(r, 'endpoint')}
    quote = routes['/api/resume/quote'](ResumeRequest(run_id='resume-test'))
    assert len(preparations) == 2  # eligibility check and the actual quote
    assert all(p == saved for p in preparations)
    with pytest.raises(ValueError, match='accept the preview'):
        routes['/api/start'](StartRequest(quote_id=quote['id'], consent=False))
    launch.assert_not_called()
    result = routes['/api/start'](StartRequest(quote_id=quote['id'], consent=True))
    assert result['id'] == 'resume-test'
    assert preparations == [saved, saved, saved]
    assert launch.call_args.kwargs['run_id'] == 'resume-test'


@pytest.mark.parametrize('active', [True, False])
def test_produce_stores_binding_only_for_new_active_plans(tmp_path, active):
    prepared = {'references': [], 'consent': {'accepted': True},
                'lipsync': {'passages': {}} if active else None}
    write_json(tmp_path / 'output.json', {'file': 'video.mp4', 'duration': 2})
    context = NS(log_path=tmp_path / 'log', record={'id': 'test'}, update=Mock(), command=Mock())
    pipeline.produce(NS(home=tmp_path), {'kind': 'video'}, prepared, context)
    saved = read_json(tmp_path / 'prepared.json')
    assert (pp.KEY in saved) is active
    if active:
        assert pp.verify(saved)
    assert '--resume' not in context.command.call_args.args[0]


def test_produce_resume_keeps_saved_plan_and_prompt_binding(tmp_path):
    saved = saved_run(tmp_path)
    manifest = read_json(tmp_path / 'passage-plan-prompts.json')
    current = {**saved, 'references': [], 'consent': {'accepted': True}}
    write_json(tmp_path / 'output.json', {'file': 'video.mp4', 'duration': 2})
    context = NS(log_path=tmp_path / 'log', record={'id': 'test'}, update=Mock(), command=Mock())
    pipeline.produce(NS(home=tmp_path), {'kind': 'video'}, current, context, resume=True)
    assert read_json(tmp_path / 'prepared.json')['lipsync'] == saved['lipsync']
    assert read_json(tmp_path / 'passage-plan-prompts.json') == manifest
    assert context.command.call_args.args[0][-1] == 'resume'


def test_a_saved_dance_plan_without_its_binding_is_refused():
    with pytest.raises(ValueError, match='no binding'):
        pp.verify({'dance': {'version': 1, 'passages': {}}})
    assert pp.verify({'lipsync': None}) is False                            # a genuinely legacy preparation still resumes as before
