"""Reviewed fork features: media access, live updates and actionable failures."""
import io
import json
import subprocess
import sys
import tempfile
import time
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
from fastapi.testclient import TestClient

from mmv import runtime
from mmv.jobs import Jobs
from mmv.storage import Storage, write_json
from test_agent import LiveAppFixture
from webapp.mondo_web import create_app


class MediaAndDiagnosticsTests(unittest.TestCase):
    def test_song_preview_bytes_range_and_private_file_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Storage(temp)
            sound = io.BytesIO()
            with wave.open(sound, 'wb') as writer:
                writer.setparams((1, 2, 8000, 8000, 'NONE', 'not compressed'))
                writer.writeframes(b'\x00\x00' * 8000)
            data = sound.getvalue()
            with TestClient(create_app(temp), base_url='http://localhost') as client:
                response = client.post('/api/upload/song', files={'file': ('song.wav', data, 'audio/wav')})
                response.raise_for_status()
                path = '/api/uploads/song/' + response.json()['file']
                preview = client.get(path)
                self.assertEqual(preview.content, data)
                self.assertIn('audio/wav', preview.headers['content-type'])
                partial = client.get(path, headers={'Range': 'bytes=0-43'})
                self.assertEqual(partial.status_code, 206)
                self.assertEqual(partial.content, data[:44])
                (store.home / 'uploads/private.json').write_text('{"secret":true}')
                self.assertEqual(client.get('/api/uploads/song/private.json').status_code, 400)
                outside = store.home / 'outside.wav'
                outside.write_bytes(data)
                (store.home / 'uploads/escape.wav').symlink_to(outside)
                self.assertEqual(client.get('/api/uploads/song/escape.wav').status_code, 400)
                self.assertEqual(client.get('/api/uploads/song/missing.wav').status_code, 400)

    def test_named_service_errors_and_safe_endpoints(self):
        with patch.object(runtime, 'http_ok', return_value=False):
            with self.assertRaisesRegex(ValueError, 'ComfyUI.*comfy_launch'):
                runtime.start_service('', '', 'http://127.0.0.1:8188/system_stats', Path('comfy-service.log'))
            with self.assertRaisesRegex(ValueError, r'llama.cpp.*writer_launch'):
                runtime.start_service('', '', 'http://127.0.0.1:8080/v1/models', Path('writer-service.log'))
            with self.assertRaisesRegex(ValueError, r'llama.cpp.*JSON array'):
                runtime.start_service('{bad', '', 'http://127.0.0.1:8080/v1/models', Path('writer-service.log'))
        self.assertEqual(runtime.safe_endpoint('http://user:secret@localhost:8080/v1?key=hidden#secret'),
                         'http://localhost:8080/v1')
        self.assertEqual(runtime.identify_service(log='vision.log')[0], 'Vision service')
        self.assertEqual(runtime.identify_service(log='laya.log')[0], 'Laya')

    def test_command_failures_are_actionable_and_secret_redacted(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Storage(temp)
            store.save_key('MMV_WRITER_API_KEY', 'mock-secret-only')
            jobs = Jobs(store)
            seen = []
            unsubscribe = jobs.subscribe(lambda status, log: seen.append(status))
            jobs.start('test', lambda context: context.command([
                sys.executable, '-c', 'import sys; print("ValueError: Laya model missing mock-secret-only", flush=True); sys.exit(1)']))
            jobs.worker.join(timeout=10)
            self.assertFalse(jobs.worker.is_alive())
            status = jobs.status()
            self.assertEqual(status['state'], 'failed')
            self.assertIn('Laya model missing', status['message'])
            self.assertNotIn('mock-secret-only', status['message'])
            self.assertIn('[redacted]', status['message'])
            self.assertIn('finished', seen[-1])
            unsubscribe()
            with TestClient(create_app(temp), base_url='http://localhost') as client:
                run = store.home / 'runs' / status['id']
                (run / 'writer-service.log').write_text('Writer failed mock-secret-only')
                (run / 'comfy-service.log').write_text('Comfy startup failed mock-secret-only')
                log = client.get('/api/log/' + status['id']).json()['log']
                self.assertIn('Comfy startup failed', log)
                self.assertIn('Writer Service Output (llama.cpp)', log)
                self.assertNotIn('mock-secret-only', log)

    def test_optional_vocabulary_preserves_default_pool(self):
        from mmv.pipeline import load_vocabulary
        full = load_vocabulary()
        reduced = load_vocabulary('reduced_flashing')
        self.assertEqual(len(full['lighting']), 227)
        self.assertEqual(len(reduced['lighting']), 220)
        self.assertEqual(len(full['practical_effects']), 111)
        self.assertEqual(len(reduced['practical_effects']), 109)
        for key in full:
            if key not in ('lighting', 'practical_effects'):
                self.assertEqual(full[key], reduced[key])
        self.assertEqual(load_vocabulary(), full)
        with self.assertRaises(ValueError):
            load_vocabulary('unknown')

    def test_laya_auto_device_is_opt_in(self):
        from mmv.engine.validators.laya_semantic import LayaSemanticValidator
        fake_module = MagicMock()
        fake_module.RLAgent.return_value.cfg = {}
        for requested, cuda, mps, expected in [
            ('auto', True, True, 'cuda'), ('auto', False, True, 'mps'),
            ('auto', False, False, 'cpu'), ('cuda', False, False, 'cuda'),
            ('cpu', True, True, 'cpu'), ('mps', False, False, 'mps'),
            ('cuda_or_cpu', False, True, 'cpu'), ('cuda_or_cpu', True, False, 'cuda'),
            ('mps_or_cpu', False, False, 'cpu'), ('mps_or_cpu', False, True, 'mps')]:
            with self.subTest(requested=requested, cuda=cuda, mps=mps):
                torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: cuda),
                                        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: mps)))
                with patch.dict(sys.modules, {'rl_agent_api': fake_module, 'torch': torch}), \
                     patch('mmv.engine.validators.laya_semantic.resolve_model_dir', return_value=Path('/tmp/mock-laya')), \
                     patch('mmv.engine.validators.laya_semantic._model_dir_staged', return_value=True), \
                     patch.object(Storage, 'settings', return_value={'laya_device': requested}):
                    validator = LayaSemanticValidator()
                    validator._load_agent()
                    fake_module.RLAgent.assert_called_with(str(Path('/tmp/mock-laya')), device=expected)


class EventStreamTests(LiveAppFixture, unittest.TestCase):
    def test_stream_delivers_thread_updates_resume_status_and_unsubscribes(self):
        jobs = self.fixture.app.state.jobs
        run = self.home / 'runs' / 'event-test'
        write_json(run / 'request.json', {'backend': 'comfy_sdk_h3'})
        with httpx.stream('GET', self.url + '/api/events', timeout=5, trust_env=False) as response:
            self.assertEqual(response.status_code, 200)
            lines = response.iter_lines()
            self.assertEqual(next(lines), 'event: status')
            self.assertIn('"state":', next(lines))
            jobs.notify({'id': 'event-test', 'state': 'failed', 'message': 'Synthetic failure'}, 'Synthetic log')
            while True:
                line = next(lines)
                if line.startswith('data: ') and 'Synthetic failure' in line:
                    status = json.loads(line[6:])
                    self.assertTrue(status['can_resume'])
                    self.assertEqual(status['id'], 'event-test')
                    break
        deadline = time.monotonic() + 3
        while jobs.subscribers and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertEqual(jobs.subscribers, [])
