"""GPU hand-off policy with fake measurements, synthetic files and mock processes; no GPU, model or service is touched."""
import json
import os
import struct
import subprocess
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from mmv import gpu_memory as g, runtime, worker
from mmv.storage import Storage, read_json
from tests.conftest import REAL_GPU_MEMORY
from tests.test_passage_prerequisites import capture
from tests.test_vision_stage import Proc, stage, items

GIB = g.GIB


def smi(text):
    return Mock(return_value=NS(stdout=text))


class Stuck:
    """A process that ignores every stop request."""
    pid = 42

    def poll(self):
        return None


def clock_ticks(monkeypatch, step):
    ticks = iter(range(0, 10_000_000, step))
    monkeypatch.setattr(g.time, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(g.time, 'sleep', lambda s: None)


def memory_is(monkeypatch, value):
    monkeypatch.setattr(g, 'gpu_memory', lambda *a, **k: value)


def test_reader_picks_the_visible_gpu_and_parses_mib():
    out = '0, 1000, 8000\n1, 2000, 24000\n'
    assert REAL_GPU_MEMORY(smi(out), {}) == (1000 * g.MIB, 8000 * g.MIB)
    assert REAL_GPU_MEMORY(smi(out), {'CUDA_VISIBLE_DEVICES': '1,0'}) == (2000 * g.MIB, 24000 * g.MIB)


@pytest.mark.parametrize('environ', [{'CUDA_VISIBLE_DEVICES': ''}, {'CUDA_VISIBLE_DEVICES': '-1'},
                                     {'CUDA_VISIBLE_DEVICES': 'GPU-1234-abcd'}, {'CUDA_VISIBLE_DEVICES': '7'}])
def test_hidden_uuid_or_missing_gpu_is_unknown(environ):
    assert REAL_GPU_MEMORY(smi('0, 1000, 8000\n'), environ) is None


@pytest.mark.parametrize('failure', [FileNotFoundError(), subprocess.CalledProcessError(9, 'nvidia-smi'),
                                     subprocess.TimeoutExpired('nvidia-smi', 10)])
def test_reader_failures_are_unknown_never_free(failure):
    assert REAL_GPU_MEMORY(Mock(side_effect=failure), {}) is None
    assert REAL_GPU_MEMORY(smi('garbage\n[N/A], [N/A], [N/A]\n'), {}) is None


def write_safetensors(path, shapes):
    header = {name: {'dtype': 'BF16', 'shape': shape, 'data_offsets': [0, 0]} for name, shape in shapes.items()}
    header['__metadata__'] = {'format': 'pt'}
    blob = json.dumps(header).encode()
    path.write_bytes(struct.pack('<Q', len(blob)) + blob)


def test_laya_estimate_counts_fp32_parameters_from_the_staged_header(tmp_path):
    write_safetensors(tmp_path / 'model.safetensors', {'a': [1000, 1000], 'b': [500]})
    assert g.laya_need_bytes(tmp_path) == 1_000_500 * 4 + g.LAYA_RESERVE


def test_laya_estimate_falls_back_to_double_file_size_then_to_a_large_reserve(tmp_path):
    (tmp_path / 'model.safetensors').write_bytes(b'x' * 1000)
    assert g.laya_need_bytes(tmp_path) == 2000 + g.LAYA_RESERVE
    assert g.laya_need_bytes(tmp_path / 'missing') == g.LAYA_RESERVE * 4


def test_vision_estimate_sums_model_and_projector_files(tmp_path):
    (tmp_path / 'm.gguf').write_bytes(b'x' * 3000)
    (tmp_path / 'p.gguf').write_bytes(b'x' * 500)
    command = ['llama-server', '-m', str(tmp_path / 'm.gguf'), f'--mmproj={tmp_path / "p.gguf"}', '--port', '8083']
    assert g.gguf_need_bytes(command) == 3500 + g.VISION_RESERVE
    assert g.gguf_need_bytes([*command, '-ngl', '0']) == 500 + g.VISION_RESERVE
    assert g.gguf_need_bytes(['llama-server', '-m', str(tmp_path / 'm.gguf'), '-ngl', '0']) == 0
    assert g.gguf_need_bytes(['llama-server', '-m', str(tmp_path / 'gone.gguf')]) is None


@pytest.mark.parametrize('configured, free, expected', [
    ('cuda', 3, 'cpu'),           # insufficient
    ('cuda', 12, None),           # ample: stays on the GPU
    ('auto', 3, 'cpu'),
    ('cuda_or_cpu', 3, 'cpu'),
    ('cuda', 4, None),            # exactly enough
])
def test_laya_device_choice_uses_measured_headroom(configured, free, expected):
    override, message = g.laya_device_choice(configured, 4 * GIB, (free * GIB, 16 * GIB))
    assert override == expected
    assert ('CPU' in message) == (expected == 'cpu') and 'GiB' in message


@pytest.mark.parametrize('configured', ['cuda', 'auto', 'cuda_or_cpu'])
def test_unknown_gpu_memory_is_never_safe_to_overlap(configured):
    override, message = g.laya_device_choice(configured, 4 * GIB, None, platform='linux')
    assert override == 'cpu' and 'could not be measured' in message


@pytest.mark.parametrize('configured, memory, platform', [
    ('cpu', (64 * GIB, 64 * GIB), 'linux'), ('cpu', None, 'linux')])
def test_cpu_settings_are_never_rewritten(configured, memory, platform):
    override, _ = g.laya_device_choice(configured, 4 * GIB, memory, platform)
    assert override is None


def test_wait_for_room_polls_until_memory_returns_or_time_runs_out():
    readings = iter([(1 * GIB, 8 * GIB), (2 * GIB, 8 * GIB), (6 * GIB, 8 * GIB)])
    clock = iter(range(100))
    assert g.wait_for_room(5 * GIB, lambda: next(readings), sleep=lambda s: None,
                           clock=lambda: next(clock)) == (True, (6 * GIB, 8 * GIB))
    clock = iter(range(0, 100, 20))
    enough, memory = g.wait_for_room(5 * GIB, lambda: (1 * GIB, 8 * GIB), timeout=30, sleep=lambda s: None,
                                     clock=lambda: next(clock))
    assert enough is False and memory == (1 * GIB, 8 * GIB)
    assert g.wait_for_room(5 * GIB, lambda: None) == (None, None)


def test_wait_released_needs_a_baseline_and_tolerates_context_overhead():
    base = (10 * GIB, 12 * GIB)
    assert g.wait_released(None, lambda: (1, 2)) is None
    assert g.wait_released(base, lambda: None) is None
    assert g.wait_released(base, lambda: (9.5 * GIB, 12 * GIB)) is True
    clock = iter(range(0, 1000, 30))
    assert g.wait_released(base, lambda: (4 * GIB, 12 * GIB), timeout=60, sleep=lambda s: None,
                           clock=lambda: next(clock)) is False


def test_storage_override_is_ephemeral_and_never_written(tmp_path, monkeypatch):
    store = Storage(tmp_path)
    assert store.settings()['laya_device'] == 'cuda'
    monkeypatch.setenv('MMV_LAYA_DEVICE_OVERRIDE', 'cpu')
    assert store.settings()['laya_device'] == 'cpu'
    assert read_json(tmp_path / 'settings.json', {}).get('laya_device') is None
    for ignored in ('cuda', 'rm -rf'):               # only the safe downgrade is accepted
        monkeypatch.setenv('MMV_LAYA_DEVICE_OVERRIDE', ignored)
        assert store.settings()['laya_device'] == 'cuda'


# --- worker: the effective Laya choice is made and announced before the protected loader runs -------------------------

def laya_settings(tmp_path, device='cuda', params=1_000_000_000):
    model_dir = tmp_path / 'laya'
    model_dir.mkdir(exist_ok=True)
    write_safetensors(model_dir / 'model.safetensors', {'w': [params]})
    return {'laya_device': device, 'laya_model_dir': str(model_dir)}


def worker_output(tmp_path, monkeypatch, capsys, memory, **settings):
    memory_is(monkeypatch, memory)
    capture(tmp_path, monkeypatch, 'sealed', prepared_settings=laya_settings(tmp_path, **settings))
    return capsys.readouterr().out


def test_worker_insufficient_vram_uses_cpu_before_load_and_keeps_settings(tmp_path, monkeypatch, capsys):
    # About 4 GB of fp32 weights plus the 2 GiB reserve; only 3 GiB is free.
    out = worker_output(tmp_path, monkeypatch, capsys, (3 * GIB, 24 * GIB))
    assert 'will use the CPU: only 3.0 GiB of 24.0 GiB GPU memory is free' in out
    assert out.index('will use the CPU') < out.index('Loading Laya prompt reviewer')
    assert os.environ['MMV_LAYA_DEVICE_OVERRIDE'] == 'cpu'
    # What the unchanged protected loader reads through Storage.settings():
    assert Storage(tmp_path / 'home').settings()['laya_device'] == 'cpu'
    assert read_json(tmp_path / 'home' / 'settings.json', {}).get('laya_device') is None


def test_worker_ample_vram_keeps_the_gpu(tmp_path, monkeypatch, capsys):
    out = worker_output(tmp_path, monkeypatch, capsys, (20 * GIB, 24 * GIB))
    assert 'will use the GPU: 20.0 GiB of 24.0 GiB free' in out
    assert os.environ['MMV_LAYA_DEVICE_OVERRIDE'] == ''
    assert Storage(tmp_path / 'home').settings()['laya_device'] == 'cuda'


def test_worker_unknown_vram_uses_cpu(tmp_path, monkeypatch, capsys):
    out = worker_output(tmp_path, monkeypatch, capsys, None)
    assert 'GPU memory could not be measured' in out
    assert os.environ['MMV_LAYA_DEVICE_OVERRIDE'] == 'cpu'


@pytest.mark.parametrize('device', ['cpu'])
def test_worker_leaves_cpu_settings_alone(tmp_path, monkeypatch, capsys, device):
    out = worker_output(tmp_path, monkeypatch, capsys, (1 * GIB, 8 * GIB), device=device)
    assert os.environ['MMV_LAYA_DEVICE_OVERRIDE'] == ''
    assert f'will use {"the CPU" if device == "cpu" else device}' in out


# --- general renderer release before the writer and Laya --------------------------------------------------------------

@pytest.mark.parametrize('backend, vision, released', [
    ('local_h3', False, True), ('local_h3', True, True),
    ('comfy_sdk_h3', True, True), ('comfy_sdk_h3', False, False), ('wavespeed', False, False)])
def test_cached_renderer_is_released_for_local_gpu_production(tmp_path, monkeypatch, backend, vision, released):
    from mmv import comfy_memory
    monkeypatch.setattr(runtime, 'http_ok', Mock(return_value=True))
    release = Mock()
    monkeypatch.setattr(comfy_memory, 'release_cached_models', release)
    capture(tmp_path, monkeypatch, 'sealed', backend=backend, vision_quality_check=vision,
            prepared_settings={'comfy_url': 'http://127.0.0.1:8188'})
    assert release.called is released


def test_unmeasurable_device_and_busy_queue_both_stop_before_model_load(tmp_path, monkeypatch, capsys):
    from mmv import comfy_memory
    monkeypatch.setattr(runtime, 'http_ok', Mock(return_value=True))
    settings = {'comfy_url': 'http://x:8188'}
    monkeypatch.setattr(comfy_memory, 'release_cached_models',
                        Mock(side_effect=comfy_memory.UnmeasurableDevice('no memory report')))
    capture(tmp_path, monkeypatch, 'sealed', backend='local_h3', prepared_settings=settings,
            expect=ValueError, match='no memory report')
    assert 'Loading Laya' not in capsys.readouterr().out
    monkeypatch.setattr(comfy_memory, 'release_cached_models',
                        Mock(side_effect=ValueError('another running or queued job')))
    with pytest.raises(ValueError, match='another running or queued job'):
        capture(tmp_path, monkeypatch, 'sealed', backend='local_h3', prepared_settings=settings)


# --- prompt -> render: the owned writer must really exit and its memory must return -----------------------------------

LOCAL_WRITER = {'writer_mode': 'local', 'writer_launch': '[]', 'writer_cwd': '', 'writer_url': 'http://x/v1'}


def test_stop_confirmed_requires_an_actual_exit(monkeypatch):
    monkeypatch.setattr(runtime, 'stop_process', Mock())     # the signal "succeeded" but the process lives on
    with pytest.raises(ValueError, match='Music-video writer .*did not exit'):
        runtime.stop_confirmed(Stuck(), 'Music-video writer')
    runtime.stop_confirmed(Proc('gone'), 'x')
    runtime.stop_confirmed(None, 'x')


def test_writer_that_does_not_exit_blocks_rendering(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, 'start_service', Mock(return_value=Stuck()))
    capture(tmp_path, monkeypatch, 'sealed', prepared_settings=LOCAL_WRITER, stop_process=Mock(),
            expect=ValueError, match='Music-video writer .*did not exit')


def test_writer_memory_that_never_returns_blocks_rendering(tmp_path, monkeypatch):
    readings = iter([(10 * GIB, 12 * GIB)] + [(2 * GIB, 12 * GIB)] * 50)
    monkeypatch.setattr(g, 'gpu_memory', lambda *a, **k: next(readings))
    clock_ticks(monkeypatch, 30)
    monkeypatch.setattr(runtime, 'start_service', Mock(return_value=Proc('writer')))
    capture(tmp_path, monkeypatch, 'sealed', prepared_settings=LOCAL_WRITER, stop_process=Mock(),
            expect=ValueError, match='GPU memory was not released')


# --- render -> vision -> re-render -----------------------------------------------------------------------------------

@pytest.fixture
def small_model(tmp_path, monkeypatch):
    (tmp_path / 'm.gguf').write_bytes(b'x' * 8 * 1024)
    monkeypatch.setattr('mmv.vision_check.vision_command',
                        Mock(return_value=['llama-server', '-m', str(tmp_path / 'm.gguf')]))


def test_vision_refuses_known_insufficient_memory_and_starts_nothing(stage, small_model, monkeypatch):
    memory_is(monkeypatch, (GIB // 2, 8 * GIB))
    clock_ticks(monkeypatch, 40)
    assert stage.judge(items())['seg000-r1']['status'] == 'error'
    assert 'Not enough free GPU memory for the vision model' in stage.note()
    runtime.start_service.assert_not_called()
    assert [c.args[0] for c in runtime.stop_process.call_args_list] == ['comfy']   # only the Mondo-owned renderer stopped


def test_vision_starts_when_memory_is_ample_or_unknown(stage, small_model, monkeypatch):
    memory_is(monkeypatch, (20 * GIB, 24 * GIB))
    assert stage.judge(items())['seg000-r1']['status'] == 'pass'
    stage.close()
    memory_is(monkeypatch, None)      # everything Mondo owns is already stopped
    assert stage.judge(items())['seg000-r1']['status'] == 'pass'


def test_external_renderer_must_release_before_a_running_vision_server_is_reused(stage, monkeypatch):
    stage.comfy_process, stage.external_comfy = None, True
    stage.settings['comfy_url'] = 'http://127.0.0.1:8188'
    monkeypatch.setattr('mmv.vision_stage.release_cached_models',
                        Mock(side_effect=ValueError('another running or queued job')))
    runtime.http_ok.return_value = runtime.serves_model.return_value = True
    assert stage.judge(items())['seg000-r1']['status'] == 'error'
    assert 'another running or queued job' in stage.note()
    assert not stage.started and not stage.reused


def test_owned_renderer_that_will_not_exit_blocks_the_vision_model(stage, monkeypatch):
    stage.comfy_process = Stuck()
    monkeypatch.setattr(runtime, 'stop_confirmed', Mock(side_effect=ValueError('ComfyUI (process 42) did not exit')))
    assert stage.judge(items())['seg000-r1']['status'] == 'error'
    assert 'ComfyUI (process 42) did not exit' in stage.note()
    runtime.start_service.assert_not_called()


def test_rerender_waits_for_vision_memory_and_is_skipped_if_it_never_returns(stage, monkeypatch):
    stage.judge(items())
    stage.baseline = (10 * GIB, 12 * GIB)
    memory_is(monkeypatch, (2 * GIB, 12 * GIB))
    clock_ticks(monkeypatch, 30)
    assert stage.prepare_render() is False
    assert 'GPU memory was not released after the vision model stopped' in stage.skipped
    stage.restart_comfy.assert_not_called()


def test_rerender_is_skipped_if_the_owned_vision_model_will_not_exit(stage):
    stage.judge(items())
    stage.process = Stuck()
    assert stage.prepare_render() is False
    assert 'did not exit' in stage.skipped
    stage.restart_comfy.assert_not_called()


def test_rerender_restarts_the_renderer_when_everything_stopped(stage):
    stage.judge(items())
    assert stage.prepare_render() is True and stage.skipped is None
    stage.restart_comfy.assert_called_once()


def test_quality_stage_skips_vision_retries_when_the_renderer_may_not_share_the_gpu(tmp_path, monkeypatch):
    seg = NS(segment_id='seg000', index=0, trim_frames=48, duration_input=2, shots=[NS(start_frame=0)])
    render, vision = Mock(), Mock()
    vision.judge.return_value = {'seg000': {'status': 'fail', 'problems': ['borders'], 'retry': True}}
    vision.prepare_render.return_value = False
    monkeypatch.setattr('mmv.quality.inspect_clip', Mock(return_value={'status': 'pass', 'problems': []}))
    monkeypatch.setattr(worker, '_sha256', lambda p: 'abc')
    out = worker.run_quality_stage(tmp_path, NS(cost_for=lambda s: 0), {'backend': 'local_h3', 'seed': 1, 'direction': ''},
                                   NS(segments=[seg]), {'seg000': {'video': 'clip.mp4'}}, render, Mock(), vision)
    render.assert_not_called()
    assert out == {'seg000': {'video': 'clip.mp4'}}
    assert 'vision: borders' in read_json(tmp_path / 'quality.json')['seg000']['warning']


@pytest.mark.parametrize('configured', ['mps', 'mps_or_cpu', 'auto'])
def test_unmeasured_apple_gpu_never_shares_with_writer(configured):
    override, message = g.laya_device_choice(configured, 4 * GIB, None, platform='darwin')
    assert override == 'cpu' and 'could not be measured' in message


def test_inconsistent_driver_memory_is_unknown():
    assert REAL_GPU_MEMORY(smi('0, 9000, 8000'), {}) is None
    assert REAL_GPU_MEMORY(smi('0, 0, 0'), {}) is None


def test_writer_is_not_launched_with_insufficient_measured_room(tmp_path, monkeypatch):
    (tmp_path / 'writer.gguf').write_bytes(b'weights')
    memory_is(monkeypatch, (GIB // 2, 8 * GIB))
    monkeypatch.setattr(runtime, 'http_ok', Mock(return_value=False))
    start = Mock()
    monkeypatch.setattr(runtime, 'start_service', start)
    settings = {**LOCAL_WRITER, 'writer_launch': json.dumps(['llama-server', '-m', str(tmp_path / 'writer.gguf')])}
    capture(tmp_path, monkeypatch, 'sealed', prepared_settings=settings,
            expect=ValueError, match='Not enough free GPU memory to start the writer')
    start.assert_not_called()


def test_failed_vision_stop_retains_owned_process_for_cleanup(stage):
    stuck = Stuck()
    stage.process = stuck
    stage.close()
    assert stage.process is stuck and 'did not exit' in stage.note()


@pytest.mark.parametrize('external', ['writer', 'vision'])
def test_external_gpu_model_prevents_renderer_handoff(monkeypatch, external):
    monkeypatch.setattr(runtime, 'serves_model', lambda *a: external == 'vision')
    monkeypatch.setattr(runtime, 'http_ok', lambda *a: external == 'writer')
    with pytest.raises(ValueError, match='overlapping GPU models'):
        worker.require_renderer_handoff(LOCAL_WRITER)


def test_cpu_writer_does_not_block_renderer_handoff(monkeypatch):
    monkeypatch.setattr(runtime, 'serves_model', lambda *a: False)
    monkeypatch.setattr(runtime, 'http_ok', lambda *a: True)
    worker.require_renderer_handoff({**LOCAL_WRITER, 'writer_launch': '["llama-server", "-ngl", "0"]'})
