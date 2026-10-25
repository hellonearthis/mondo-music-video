"""Required-engine readiness and status against fake localhost HTTP services; no models are launched."""
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace as NS

import pytest

from mmv import runtime, services, vision_stage


@contextmanager
def fake_server(routes):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = routes.get(self.path.split('?')[0])
            self.send_response(200 if body is not None else 404)
            self.end_headers()
            self.wfile.write(json.dumps(body if body is not None else {}).encode())

        def log_message(self, *args):
            pass

    server = HTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f'http://127.0.0.1:{server.server_address[1]}'
    finally:
        server.shutdown()
        server.server_close()


def models(*ids):
    return {'data': [{'id': i} for i in ids]}


DEAD = 'http://127.0.0.1:9'  # discard port: nothing listens, connection refused


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Launchable local writer (model + sibling mmproj), idle ComfyUI and a dead style-harvest endpoint."""
    (tmp_path / 'model-Q4.gguf').write_bytes(b'')
    (tmp_path / 'mmproj-model-f16.gguf').write_bytes(b'')
    (tmp_path / 'laya').mkdir()
    for name in ('model.safetensors', 'rl_agent_config.json'):
        (tmp_path / 'laya' / name).write_text('')
    (tmp_path / 'laya' / 'tokenizer').mkdir()
    (tmp_path / 'laya' / 'encoder').mkdir()
    (tmp_path / 'laya' / 'encoder' / 'config.json').write_text('')
    settings = {'writer_mode': 'local', 'writer_url': DEAD + '/v1', 'writer_model': 'w',
                'writer_launch': json.dumps(['llama-server', '-m', str(tmp_path / 'model-Q4.gguf'), '--port', '8081']),
                'comfy_url': DEAD, 'comfy_launch': json.dumps(['python', 'main.py']),
                'vision_url': DEAD + '/v1', 'vision_model': 'harvest', 'laya_model_dir': str(tmp_path / 'laya')}
    monkeypatch.setattr(services, '_last_probe_time', 0.0)
    return NS(home=tmp_path, settings=lambda: settings), settings


def quality_port(monkeypatch, url):
    monkeypatch.setattr(vision_stage, 'VISION_PORT', int(url.rsplit(':', 1)[1]))


def video(**extra):
    return {'kind': 'video', 'backend': 'local_h3', 'vision_quality_check': True, **extra}


def test_launchable_quality_vision_is_not_blocked_by_dead_harvest_endpoint(env, monkeypatch):
    store, _ = env
    quality_port(monkeypatch, DEAD)
    # Reported failure: the dead style-harvest endpoint (vision_url) used to block a launchable quality check.
    assert services.check_required_services(store, video()) == []
    status = services.check_services(store, force=True)
    assert status['vision']['available'] is False and status['vision_quality']['has_launch'] is True
    assert 'starts it when the vision check runs' in status['vision_quality']['detail']


def test_vision_check_off_does_not_look_at_vision(env):
    store, settings = env
    settings['writer_launch'] = ''
    settings['writer_mode'] = 'api'
    assert services.check_required_services(store, {**video(), 'vision_quality_check': False}) == []


@pytest.mark.parametrize('launch, text', [('', 'writer_launch is not set|launch must be|JSON argv'),
                                           ('not json', 'JSON argv'),
                                           (json.dumps(['llama-server', '-m', '/nowhere/x.gguf']), 'mmproj')])
def test_invalid_quality_launch_still_blocks_with_a_settings_error(env, monkeypatch, launch, text):
    store, settings = env
    quality_port(monkeypatch, DEAD)
    settings['writer_launch'] = launch
    errors = services.check_required_services(store, video(), resume=True)
    assert len(errors) == 1 and 'writer_launch' in errors[0]
    assert 'start your vision model' not in errors[0]
    assert any(part in errors[0] for part in text.split('|'))


def test_occupied_quality_port_blocks_and_is_never_claimed(env, monkeypatch):
    store, _ = env
    with fake_server({'/health': {}, '/v1/models': models('someone-elses-model')}) as url:
        quality_port(monkeypatch, url)
        errors = services.check_required_services(store, video(), resume=True)
        assert len(errors) == 1 and 'another service' in errors[0] and 'never stops' in errors[0]
        status = services.check_services(store, force=True)['vision_quality']
        assert status['available'] is False and status['port_in_use'] is True


def test_matching_running_quality_vision_is_reused(env, monkeypatch):
    store, _ = env
    with fake_server({'/health': {}, '/v1/models': models('mmv-vision')}) as url:
        quality_port(monkeypatch, url)
        assert services.check_required_services(store, video(), resume=True) == []
        status = services.check_services(store, force=True)['vision_quality']
        assert status['available'] is True and status['activity'] == 'sleeping'
        assert 'ready' in status['detail'] and 'never stopped' not in status['detail']


def test_style_harvest_stays_independent_of_launch_settings(env, monkeypatch):
    store, settings = env
    quality_port(monkeypatch, DEAD)
    settings['writer_launch'] = ''  # nothing to derive a vision launch from, so an offline vision server is an error
    errors = services.check_required_services(store, {'kind': 'harvest'})
    assert len(errors) == 1 and 'style harvesting' in errors[0] and 'could not start it' in errors[0]
    with fake_server({'/v1/models': models('harvest')}) as url:
        settings['vision_url'] = url + '/v1'
        settings['writer_launch'] = ''  # harvest never needs the quality launch
        assert services.check_required_services(store, {'kind': 'harvest'}) == []


def test_offline_but_launchable_writer_and_comfy_are_accepted(env, monkeypatch):
    store, _ = env
    quality_port(monkeypatch, DEAD)
    assert services.check_required_services(store, {'kind': 'video', 'backend': 'local_h3'}) == []
    status = services.check_services(store, force=True)
    assert status['writer']['available'] is False and 'starts it when needed' in status['writer']['detail']
    assert 'starts it when needed' in status['comfy']['detail']


@pytest.mark.parametrize('key, label', [('writer_launch', 'Prompt Writer'), ('comfy_launch', 'ComfyUI')])
@pytest.mark.parametrize('bad, why', [('', 'not set'), ('{oops', 'not valid JSON'), ('["ok", ""]', 'non-empty'),
                                      ('"python main.py"', 'JSON array')])
def test_unusable_launch_for_offline_role_names_the_setting(env, monkeypatch, key, label, bad, why):
    store, settings = env
    quality_port(monkeypatch, DEAD)
    settings[key] = bad
    errors = [e for e in services.check_required_services(store, {'kind': 'ident', 'backend': 'local_h3'}) if label in e]
    assert len(errors) == 1 and key in errors[0] and why in errors[0]
    assert 'Please start' not in errors[0]


def test_running_role_needs_no_launch_command(env):
    store, settings = env
    settings['comfy_launch'] = ''
    with fake_server({'/system_stats': {'devices': []}, '/queue': {}}) as comfy:
        settings['comfy_url'] = comfy
        errors = services.check_required_services(store, {'kind': 'ident', 'backend': 'local_h3'}, resume=True)
        assert errors == []


def test_resume_skips_writer_and_laya_but_keeps_comfy_and_quality_checks(env, monkeypatch):
    store, settings = env
    quality_port(monkeypatch, DEAD)
    settings.update(writer_launch='', laya_model_dir='/nowhere', comfy_launch='')
    errors = services.check_required_services(store, video(), resume=True)
    assert len(errors) == 2 and 'ComfyUI' in errors[0] and 'Vision quality check' in errors[1]
    assert len(services.check_required_services(store, video(), resume=False)) == 4


def test_api_writer_is_configured_not_online(env):
    store, settings = env
    settings.update(writer_mode='api', writer_url='https://api.example.invalid/v1', writer_model='m')
    status = services.check_services(store, force=True)['writer']
    assert status['available'] is True and status['activity'] == 'configured'
    assert 'not probed' in status['detail']
    assert services.check_required_services(store, {'kind': 'ident', 'backend': 'api'}) == []


def test_serves_model_matches_alias_only():
    with fake_server({'/v1/models': models('a', 'mmv-vision')}) as url:
        assert runtime.serves_model(url + '/v1', 'mmv-vision') is True
        assert runtime.serves_model(url + '/v1', 'other') is False
    assert runtime.serves_model(DEAD + '/v1', 'mmv-vision', timeout=0.5) is False
