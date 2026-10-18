"""Sandbox-safe orchestration checks: synthetic files and mocked services only."""
import json
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import pytest

from mmv import pipeline, runtime, worker
from mmv.storage import read_json, write_json
from mmv.vision_stage import VisionStage
from webapp.mondo_web import ProductionRequest


@pytest.fixture
def stage(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, 'http_ok', Mock(return_value=False))
    monkeypatch.setattr(runtime, 'stop_process', Mock())
    monkeypatch.setattr(runtime, 'start_service', Mock(return_value='qwen'))
    monkeypatch.setattr('mmv.vision_check.vision_command', Mock(return_value=['llama-server', '--alias', 'mmv-vision']))
    monkeypatch.setattr('mmv.vision_check.judge_clip', Mock(return_value={'status': 'pass', 'problems': [], 'retry': False}))
    plan = NS(segments=[NS(segment_id='seg000', index=0, trim_frames=48, shots=[NS(start_frame=0)])])
    return VisionStage({'writer_launch': '[]'}, tmp_path, plan, False, 'comfy', Mock(return_value='comfy2'), Mock())


def items():
    return [('seg000', {'segment_id': 'seg000-r1'}, {'video': 'clip.mp4'})]


def test_swap_order_relaunch_and_second_judgment(stage):
    events = []
    runtime.stop_process.side_effect = lambda p: events.append(('stop', p))
    runtime.start_service.side_effect = lambda *a, **k: events.append(('start', 'qwen')) or 'qwen'
    stage.restart_comfy.side_effect = lambda: events.append(('start', 'comfy2')) or 'comfy2'
    assert stage.judge(items())['seg000-r1']['status'] == 'pass'
    stage.judge(items())  # no extra swap within the batch
    stage.prepare_render()
    stage.judge(items())
    stage.close()
    assert events == [('stop', 'comfy'), ('start', 'qwen'), ('stop', 'qwen'),
                      ('start', 'comfy2'), ('stop', 'comfy2'), ('start', 'qwen'), ('stop', 'qwen')]
    from mmv.vision_check import judge_clip
    assert judge_clip.call_args.args == ('clip.mp4', 48, [0], 'http://127.0.0.1:8083/v1', 'mmv-vision')
    assert judge_clip.call_args.kwargs == {'framing_allowed': False}


def test_no_renderer_handle_never_stops_external_comfy(stage):
    stage.comfy_process = None
    stage.restart_comfy = None
    stage.judge(items())
    stage.prepare_render()
    assert runtime.stop_process.call_args_list[0].args == ('qwen',)
    assert runtime.stop_process.call_count == 1


@pytest.mark.parametrize('error', [ValueError('startup failed'), OSError('missing executable')])
def test_start_failure_is_warning_only_and_not_retried(stage, error):
    runtime.start_service.side_effect = error
    verdict = stage.judge(items())['seg000-r1']
    assert verdict['status'] == 'error' and verdict['retry'] is False
    assert 'Vision check could not run' in stage.note()
    stage.judge(items())
    assert runtime.start_service.call_count == 1
    stage.close()


def test_invalid_command_keeps_renderer_running(stage):
    with patch('mmv.vision_check.vision_command', side_effect=ValueError('missing mmproj')):
        assert stage.judge(items())['seg000-r1']['status'] == 'error'
    runtime.stop_process.assert_not_called()


def test_occupied_vision_service_is_not_used_or_stopped(stage):
    runtime.http_ok.return_value = True
    assert stage.judge(items())['seg000-r1']['status'] == 'error'
    assert 'already in use' in stage.note()
    runtime.stop_process.assert_not_called()
    runtime.start_service.assert_not_called()


def test_startup_race_does_not_use_external_vision_server(stage):
    runtime.start_service.return_value = None
    assert stage.judge(items())['seg000-r1']['status'] == 'error'
    assert 'external service' in stage.note()
    stage.close()
    assert all(c.args[0] in ('comfy', None) for c in runtime.stop_process.call_args_list)


def test_close_allows_fresh_start(stage):
    stage.judge(items())
    stage.close()
    stage.judge(items())
    assert runtime.start_service.call_count == 2


def test_request_flag_default_and_opt_in():
    assert ProductionRequest().vision_quality_check is False
    assert ProductionRequest(vision_quality_check=True).model_dump()['vision_quality_check'] is True


@pytest.mark.parametrize('backend_name', ['local_h3', 'comfy_sdk_h3'])
@pytest.mark.parametrize('problem', ['mmproj', 'launch', 'running'])
def test_preview_diagnostics_before_analysis(tmp_path, monkeypatch, problem, backend_name):
    settings = {'writer_model': 'test', 'writer_mode': 'local', 'laya_model_dir': str(tmp_path),
                'comfy_input': str(tmp_path), 'comfy_output': str(tmp_path), 'workflow_map_path': 'unused',
                'comfy_url': 'http://127.0.0.1:8188', 'comfy_launch': '[]', 'writer_launch': '[]',
                'comfy_sdk_url': 'http://127.0.0.1:8189'}
    store = NS(settings=lambda: settings, key=lambda *a: '')
    monkeypatch.setattr('mmv.comfy_sdk.require_sdk', Mock())
    monkeypatch.setattr('mmv.comfy_sdk.check_proxy', Mock())
    monkeypatch.setattr('mmv.engine.validators.laya_semantic._model_dir_staged', lambda p: True)
    monkeypatch.setattr('mmv.render.get_backend', Mock())
    monkeypatch.setattr(pipeline, 'references', lambda *a: ([], []))
    monkeypatch.setattr(pipeline.shutil, 'which', lambda s: s)
    monkeypatch.setattr('mmv.engine.comfy.WorkflowBuilder.load', Mock())
    monkeypatch.setattr(runtime, 'http_ok', Mock(return_value=problem == 'running'))
    command = Mock(side_effect=ValueError('missing mmproj')) if problem == 'mmproj' else Mock(return_value=[])
    monkeypatch.setattr('mmv.vision_check.vision_command', command)
    if problem == 'launch':
        settings['comfy_launch'] = ''
    match = {'mmproj': 'missing mmproj', 'launch': 'launch command', 'running': 'already running'}[problem]
    with pytest.raises(ValueError, match=match):
        pipeline.prepare(store, ProductionRequest(vision_quality_check=True, backend=backend_name).model_dump())


@pytest.fixture
def production(tmp_path, monkeypatch):
    """Exercise worker.run's real vision wiring and output diagnostics, resuming saved prompts."""
    home, directory = tmp_path / 'home', tmp_path / 'run'
    directory.mkdir()
    (home / 'uploads').mkdir(parents=True)
    (home / 'uploads' / 'song.wav').write_bytes(b'synthetic song')
    request = ProductionRequest(backend='comfy_sdk_h3', song='song.wav', vision_quality_check=True).model_dump()
    settings = {'comfy_launch': '[]', 'comfy_cwd': '', 'comfy_url': 'http://127.0.0.1:8188',
                'comfy_input': '', 'comfy_output': '', 'workflow_map_path': '', 'comfy_sdk_url': '', 'writer_launch': '[]'}
    prepared = {'settings': settings, 'plan': {}, 'score': {}, 'casting': {}, 'style': {'direction': 'test'}}
    write_json(directory / 'request.json', request)
    write_json(directory / 'prepared.json', prepared)
    write_json(directory / 'prompts.json', {'seg000': 'validated test prompt'})
    seg = NS(segment_id='seg000', index=0, gen_frames=48, trim_frames=48, shots=[NS(start_frame=0)],
             ref_image_slots=0, duration_input=2, audio_slice_start_s=0, audio_slice_end_s=2)
    plan = NS(segments=[seg], width=128, height=72, total_frames=48, to_json=Mock())
    monkeypatch.setattr('mmv.engine.plan.ShotPlan.from_json', Mock(return_value=plan))
    monkeypatch.setattr(worker, 'Storage', Mock(return_value=NS(home=home, key=lambda *a: '')))
    monkeypatch.setattr('mmv.engine.actor.cast_writer_block', Mock(return_value=''))
    monkeypatch.setattr('mmv.engine.casting.cast_for', Mock(return_value=[]))
    video = tmp_path / 'synthetic.mp4'
    video.write_bytes(b'synthetic media; decoders mocked')
    backend = Mock()
    backend.render_segment.return_value = {'video': str(video)}
    backend.cost_for.return_value = 0
    monkeypatch.setattr('mmv.render.get_backend', Mock(return_value=backend))
    monkeypatch.setattr('mmv.engine.assemble.probe_frames', Mock(return_value=48))
    monkeypatch.setattr('mmv.engine.assemble.assemble_run', Mock(return_value={'video': str(video)}))
    monkeypatch.setattr('mmv.media.duration', Mock(return_value=2))
    monkeypatch.setattr('mmv.quality.inspect_clip', Mock(return_value={'status': 'pass', 'problems': []}))
    monkeypatch.setattr(runtime, 'http_ok', Mock(return_value=False))
    monkeypatch.setattr(runtime, 'start_service', Mock(return_value='owned'))
    monkeypatch.setattr(runtime, 'stop_process', Mock())
    monkeypatch.setattr('mmv.vision_check.vision_command', Mock(return_value=['llama-server', '--alias', 'test']))
    monkeypatch.setattr('mmv.vision_check.judge_clip', Mock(return_value={'status': 'pass', 'problems': [], 'retry': False}))
    monkeypatch.setenv('MMV_HOME', str(home))  # restore worker's process-local env mutation
    return home, directory, backend


def test_worker_external_comfy_skip_note_and_vision_json(production):
    home, directory, backend = production
    runtime.start_service.return_value = None
    worker.run(home, directory, resume=True)
    report = read_json(directory / 'vision.json')
    assert report['requested'] and not report['ran']
    assert 'already running outside Mondo' in report['note']
    assert read_json(directory / 'output.json')['quality_warnings'][0] == report['note']
    runtime.stop_process.assert_not_called()
    backend.render_segment.assert_called_once()


def test_worker_sdk_launch_and_success_report(production):
    home, directory, backend = production
    worker.run(home, directory, resume=True)
    assert read_json(directory / 'vision.json') == {'requested': True, 'ran': True, 'note': None}
    assert [c.kwargs['name'] for c in runtime.start_service.call_args_list] == ['ComfyUI', 'Vision model']
    assert 'quality_warnings' not in read_json(directory / 'output.json')
    assert read_json(directory / 'quality.json')['seg000']['attempts'][0]['vision']['status'] == 'pass'


def test_worker_vision_failure_completes_with_warning(production):
    home, directory, backend = production
    runtime.start_service.side_effect = ['owned', ValueError('Qwen failed')]
    worker.run(home, directory, resume=True)
    assert 'Qwen failed' in read_json(directory / 'vision.json')['note']
    assert 'Qwen failed' in read_json(directory / 'output.json')['quality_warnings'][0]
    backend.render_segment.assert_called_once()


def test_worker_flag_off_does_not_launch_sdk_comfy(production):
    home, directory, backend = production
    request = read_json(directory / 'request.json')
    request['vision_quality_check'] = False
    write_json(directory / 'request.json', request)
    worker.run(home, directory, resume=True)
    runtime.start_service.assert_not_called()
    assert read_json(directory / 'vision.json') == {'requested': False}


@pytest.mark.parametrize('external', [True, False])
def test_worker_saves_vision_diagnostics_even_if_quality_stage_fails(production, external):
    home, directory, backend = production
    runtime.start_service.return_value = None if external else 'owned'
    with patch.object(worker, 'run_quality_stage', side_effect=ValueError('interrupted checks')):
        with pytest.raises(ValueError, match='interrupted checks'):
            worker.run(home, directory, resume=True)
    report = read_json(directory / 'vision.json')
    assert report['ran'] is False
    if external:
        assert 'outside Mondo' in report['note']
    backend.close_render.assert_called_once()


@pytest.mark.parametrize('backend_name,cost,expected_retries', [('local_h3', 0, 1), ('comfy_sdk_h3', 0, 1),
                                                               ('wavespeed', 0, 0), ('local_h3', .4, 0)])
def test_batched_vision_retry_budget_and_paid_guard(tmp_path, monkeypatch, backend_name, cost, expected_retries):
    """Pixel failures spend their budget before vision; other passages may retry once."""
    paths = {}
    for name in ('a', 'b', 'a-r1', 'b-r1'):
        paths[name] = tmp_path / (name + '.mp4')
        paths[name].write_bytes(name.encode())
    segs = [NS(segment_id=name, index=i, trim_frames=48, duration_input=2, shots=[NS(start_frame=0)])
            for i, name in enumerate(('a', 'b'))]
    events = []
    def inspect(video, *args):
        events.append(('pixel', video.stem))
        return {'status': 'fail' if video.stem == 'a' else 'pass', 'problems': ['frozen'] if video.stem == 'a' else []}
    monkeypatch.setattr('mmv.quality.inspect_clip', inspect)
    def render(seg, segment_id, seed):
        events.append(('render', segment_id))
        return {'video': paths[segment_id]}
    def judge(items):
        events.append(('judge', [a['segment_id'] for _, a, _ in items]))
        return {a['segment_id']: {'status': 'fail', 'problems': ['projected frame'], 'retry': True}
                for _, a, _ in items}
    vision = NS(judge=judge, prepare_render=lambda: events.append(('prepare',)))
    args = (tmp_path, NS(cost_for=lambda s: cost), {'backend': backend_name, 'seed': 5, 'direction': ''},
            NS(segments=segs), {name: {'video': paths[name]} for name in ('a', 'b')}, render, Mock(), vision)
    worker.run_quality_stage(*args)
    report = read_json(tmp_path / 'quality.json')
    assert sum(e == ('render', 'a-r1') for e in events) == expected_retries
    assert sum(e == ('render', 'b-r1') for e in events) == expected_retries
    if expected_retries:
        assert events.index(('render', 'a-r1')) < next(i for i, e in enumerate(events) if e[0] == 'judge')
        assert events.index(('prepare',)) < events.index(('render', 'b-r1'))
        assert len(report['a']['attempts']) == len(report['b']['attempts']) == 2
        assert report['a']['used'] == 'a-r1'  # pixel pass beats pixel fail, even with vision failure
        events.clear()
        worker.run_quality_stage(*args)
        assert all(e[0] not in ('pixel', 'judge', 'prepare') for e in events)
        assert events == [('render', 'a-r1'), ('render', 'b-r1')]  # receipt recovery, no new budget
    else:
        assert not any(e[0] in ('render', 'prepare') for e in events)


def test_agent_preview_preserves_vision_flag_with_mock_transport():
    import io
    from mmv.agent import AgentClient
    client = AgentClient()
    client.opener.open = Mock(return_value=io.BytesIO(b'{"id":"reviewed-quote"}'))
    assert client.preview({'vision_quality_check': True}) == {'id': 'reviewed-quote'}
    request = client.opener.open.call_args.args[0]
    assert request.method == 'POST' and request.selector == '/api/quote'
    assert json.loads(request.data)['vision_quality_check'] is True


def test_mcp_discovery_documents_vision_flag():
    import asyncio
    pytest.importorskip('mcp')
    from mmv.mcp_server import create_server
    async def check():
        with patch('mmv.mcp_server.AgentClient') as client:
            client.return_value.preview.return_value = {'id': 'reviewed-quote'}
            server = create_server()
            tools = await server.list_tools()
            assert len(tools) == 30
            preview = next(t for t in tools if t.name == 'preview_production')
            assert 'vision_quality_check' in preview.description
            assert 'paid re-renders require consent' in preview.description
            client.return_value.preview.assert_not_called()
    asyncio.run(check())
