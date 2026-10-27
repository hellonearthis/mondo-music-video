import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from mmv import vision_service as vs


@pytest.fixture
def models(tmp_path):
    (tmp_path / 'Qwen-27B-Q4_K_M.gguf').write_bytes(b'x')
    (tmp_path / 'mmproj-Qwen-27B-f16.gguf').write_bytes(b'x')
    return tmp_path


def settings(models, **extra):
    writer = [sys.executable, '-m', str(models / 'Qwen-27B-Q4_K_M.gguf'), '--port', '8081', '--alias', 'writer']
    return {'vision_url': 'http://127.0.0.1:8080/v1', 'vision_model': 'qwen-vision', 'vision_launch': '',
            'writer_launch': json.dumps(writer), 'writer_cwd': '', **extra}


def test_plan_derives_from_writer_with_vision_alias_and_url_port(models):
    command = vs.launch_plan(settings(models))
    assert command[command.index('--alias') + 1] == 'qwen-vision'
    assert command[command.index('--port') + 1] == '8080'
    assert command[command.index('--mmproj') + 1].endswith('mmproj-Qwen-27B-f16.gguf')
    assert command[command.index('-c') + 1] == str(vs.HARVEST_CONTEXT)


def test_saved_vision_launch_wins(models):
    assert vs.launch_plan(settings(models, vision_launch=json.dumps([sys.executable, '--x']))) == [sys.executable, '--x']


@pytest.mark.parametrize('url', ['https://api.example.com/v1', 'http://192.168.1.5:8080/v1', 'http://127.0.0.1/v1'])
def test_only_local_urls_with_a_port_are_launched(models, url):
    with pytest.raises(ValueError, match='local address'):
        vs.launch_plan(settings(models, vision_url=url))


def test_plan_needs_model_name_and_a_derivable_command(models):
    with pytest.raises(ValueError, match='vision model'):
        vs.launch_plan(settings(models, vision_model=''))
    with pytest.raises(ValueError, match='Vision launch command'):
        vs.launch_plan(settings(models, writer_launch=''))


def test_running_reuses_a_live_server_and_never_stops_it(models, tmp_path):
    with mock.patch.object(vs.runtime, 'http_ok', return_value=True), \
         mock.patch.object(vs.runtime, 'start_service') as start, mock.patch.object(vs.runtime, 'stop_process') as stop:
        with vs.running(settings(models), tmp_path, lambda *a: None):
            pass
    start.assert_not_called()
    stop.assert_called_once_with(None)


def test_running_starts_then_stops_what_it_started_even_on_failure(models, tmp_path):
    proc = SimpleNamespace()
    with mock.patch.object(vs.runtime, 'http_ok', return_value=False), \
         mock.patch.object(vs.gpu_memory, 'wait_for_room', return_value=(True, (10, 20))), \
         mock.patch.object(vs.runtime, 'start_service', return_value=proc) as start, \
         mock.patch.object(vs.runtime, 'stop_process') as stop:
        with pytest.raises(RuntimeError):
            with vs.running(settings(models), tmp_path, lambda *a: None):
                raise RuntimeError('job failed')
    assert start.call_args.args[2] == 'http://127.0.0.1:8080/v1/models'
    stop.assert_called_once_with(proc)


def test_running_refuses_when_gpu_memory_is_short(models, tmp_path):
    with mock.patch.object(vs.runtime, 'http_ok', return_value=False), \
         mock.patch.object(vs.gpu_memory, 'wait_for_room', return_value=(False, (1 << 30, 24 << 30))), \
         mock.patch.object(vs.runtime, 'start_service') as start:
        with pytest.raises(ValueError, match='Not enough free GPU memory'):
            with vs.running(settings(models), tmp_path, lambda *a: None):
                pass
    start.assert_not_called()


def test_for_request_only_wraps_vision_kinds(models, tmp_path):
    ctx = SimpleNamespace(log_path=tmp_path / 'log', update=print)
    with mock.patch.object(vs, 'running') as running:
        vs.for_request({'kind': 'video'}, {}, ctx)
        running.assert_not_called()
        vs.for_request({'kind': 'world_harvest'}, {'settings': settings(models)}, ctx)
        running.assert_called_once()


def test_missing_server_program_is_reported(models):
    with pytest.raises(ValueError, match='not found'):
        vs.launch_plan(settings(models, vision_launch='["/nonexistent/llama-server"]'))


def test_harvest_text_stores_structured_vision_replies_as_text():
    from mmv.worker import harvest_text
    assert harvest_text({"CRAFT": "film grain", "PALETTE": ["teal", "rust"]}) == 'CRAFT: film grain\nPALETTE: ["teal", "rust"]'
    assert harvest_text(["one", "two"]) == "one\ntwo"
    assert harvest_text(None) == "" and harvest_text("plain") == "plain"
