"""Asynchronous ComfyUI /free handoff with an empty response; no real model or service calls."""
import io
import json
from unittest.mock import Mock

import pytest

from mmv import comfy_memory as memory, runtime
from tests.test_vision_stage import Proc, stage, items

IDLE = {'queue_running': [], 'queue_pending': []}


def stats(reserved):
    return {'devices': [{'type': 'cuda', 'torch_vram_total': reserved}]}


def test_waits_for_asynchronous_memory_release_after_empty_success_response(monkeypatch):
    values = iter([IDLE, IDLE, stats(10_000_000_000), IDLE, stats(0)])
    get = Mock(side_effect=lambda *a, **k: next(values))
    post = Mock(return_value=io.BytesIO(b''))
    monkeypatch.setattr(memory, 'request_json', get)
    monkeypatch.setattr(memory.urllib.request, 'urlopen', post)
    monkeypatch.setattr(memory.time, 'sleep', Mock())
    memory.release_cached_models('http://127.0.0.1:8188/')
    request = post.call_args.args[0]
    assert request.method == 'POST' and request.full_url.endswith('/free')
    assert json.loads(request.data) == {'unload_models': True, 'free_memory': True}
    post.assert_called_once()
    assert [call.args[0].rsplit('/', 1)[-1] for call in get.call_args_list] == ['queue', 'queue', 'system_stats', 'queue', 'system_stats']


@pytest.mark.parametrize('queue', [{}, {'queue_running': [], 'queue_pending': None},
    {'queue_running': [['other job']], 'queue_pending': []}, {'queue_running': [], 'queue_pending': [['other job']]}])
def test_unknown_or_busy_queue_is_never_unloaded(monkeypatch, queue):
    monkeypatch.setattr(memory, 'request_json', Mock(return_value=queue))
    post = Mock()
    monkeypatch.setattr(memory.urllib.request, 'urlopen', post)
    with pytest.raises(ValueError):
        memory.release_cached_models('http://127.0.0.1:8188')
    post.assert_not_called()


def test_busy_queue_race_never_starts_a_vision_model(stage, monkeypatch):
    stage.comfy_process = None
    stage.external_comfy = True
    stage.settings['comfy_url'] = 'http://127.0.0.1:8188'
    monkeypatch.setattr(memory, 'request_json', Mock(side_effect=[IDLE, {'queue_running': [['other job']], 'queue_pending': []}]))
    monkeypatch.setattr(memory.urllib.request, 'urlopen', Mock(return_value=io.BytesIO(b'')))
    result = stage.judge(items())
    assert result['seg000-r1']['status'] == 'error'
    assert 'another running or queued job' in stage.note()
    runtime.start_service.assert_not_called()
    runtime.stop_process.assert_not_called()


def test_no_vision_model_is_started_until_memory_release_is_confirmed(stage, monkeypatch):
    stage.comfy_process = None
    stage.external_comfy = True
    stage.settings['comfy_url'] = 'http://127.0.0.1:8188'
    monkeypatch.setattr(memory, 'request_json', Mock(side_effect=lambda url, **k: IDLE if url.endswith('/queue') else stats(10_000_000_000)))
    post = Mock(return_value=io.BytesIO(b''))
    monkeypatch.setattr(memory.urllib.request, 'urlopen', post)
    monkeypatch.setattr(memory.time, 'monotonic', Mock(side_effect=[0, 120]))
    stage.judge(items())
    stage.judge(items())  # Failure is recorded; no unload/start retry loop.
    assert 'not released' in stage.note()
    post.assert_called_once()
    runtime.start_service.assert_not_called()
    runtime.stop_process.assert_not_called()


def test_external_comfy_stays_running_across_vision_retry_batches(stage, monkeypatch):
    events = []
    stage.comfy_process = None
    stage.external_comfy = True
    stage.settings['comfy_url'] = 'http://127.0.0.1:8188'
    stage.restart_comfy.side_effect = lambda: events.append('reuse-comfy')
    monkeypatch.setattr('mmv.vision_stage.release_cached_models', lambda url: events.append('release-comfy'))
    runtime.start_service.side_effect = lambda *a, **k: events.append('start-vision') or Proc('qwen')
    runtime.stop_process.side_effect = lambda process: events.append(('stop', process))
    stage.judge(items())
    stage.prepare_render()
    stage.judge(items())
    stage.close()
    assert events == ['release-comfy', 'start-vision', ('stop', 'qwen'), 'reuse-comfy',
                      'release-comfy', 'start-vision', ('stop', 'qwen')]


@pytest.mark.parametrize('bad', [{}, {'devices': [None]}, stats(-1), stats(float('nan')), stats('unknown')])
def test_missing_or_invalid_memory_stats_are_not_a_confirmed_handoff(bad):
    with pytest.raises(ValueError):
        memory.memory_released(bad)


def test_async_allocator_zero_reservation_is_not_evidence_of_free_model_memory():
    device = {'type': 'cuda', 'name': 'cuda:0 GPU : cudaMallocAsync', 'torch_vram_total': 0,
              'vram_total': 24_000_000_000, 'vram_free': 2_000_000_000}
    assert not memory.memory_released({'devices': [device]})
    assert memory.memory_released({'devices': [{**device, 'vram_free': 23_000_000_000}]})
    with pytest.raises(ValueError, match='driver memory'):
        memory.memory_released({'devices': [{**device, 'vram_free': None}]})


def test_system_ram_metrics_are_not_mistaken_for_gpu_model_release():
    with pytest.raises(ValueError, match='this device'):
        memory.memory_released({'devices': [{'type': 'mps', 'torch_vram_total': 32_000_000_000}]})


def test_fresh_worker_releases_cached_renderer_before_prompt_preparation(tmp_path, monkeypatch):
    from tests.test_passage_prerequisites import capture
    monkeypatch.setattr(runtime, 'http_ok', Mock(return_value=True))
    release = Mock()
    monkeypatch.setattr(memory, 'release_cached_models', release)
    actual, *_ = capture(tmp_path, monkeypatch, 'sealed', backend='local_h3', vision_quality_check=True,
                         prepared_settings={'comfy_url': 'http://127.0.0.1:8188'})
    release.assert_called_once_with('http://127.0.0.1:8188')
    assert actual['calls']


def test_busy_renderer_stops_before_spending_a_writer_call(tmp_path, monkeypatch):
    from tests.test_passage_prerequisites import capture
    monkeypatch.setattr(runtime, 'http_ok', Mock(return_value=True))
    release = Mock(side_effect=ValueError('another running or queued job'))
    monkeypatch.setattr(memory, 'release_cached_models', release)
    with pytest.raises(ValueError, match='another running or queued job'):
        capture(tmp_path, monkeypatch, 'sealed', backend='local_h3', vision_quality_check=True,
                prepared_settings={'comfy_url': 'http://127.0.0.1:8188'})
    assert not list((tmp_path / 'run').glob('*.writer-*.json'))
