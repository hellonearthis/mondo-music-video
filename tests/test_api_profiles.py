import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from mmv.api_profiles import activate, public_profiles, save_profile, save_settings
from mmv.jobs import BusyError
from mmv.storage import Storage
from webapp.mondo_web import create_app


class ApiProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Storage(Path(self.temp.name))

    def writer(self, name, key):
        return save_profile(self.store, name, 'writer', {
            'writer_url': f'https://{name}.example/v1', 'writer_model': name,
            'writer_mode': 'api', 'writer_call_estimate': .15}, key)

    def test_multiple_accounts_and_roles_keep_separate_credentials_and_manual_defaults(self):
        original = self.store.settings()
        self.store.save_key('MMV_WRITER_API_KEY', 'manual-secret')
        self.writer('writer-a', 'secret-a')
        self.writer('writer-b', 'secret-b')
        save_profile(self.store, 'vision-a', 'vision', {
            'vision_url': 'https://vision.example/v1', 'vision_model': 'vision'}, 'vision-secret')
        save_profile(self.store, 'video-a', 'video', {'backend': 'wavespeed'}, 'video-secret')
        self.assertEqual(self.store.settings(), original)
        activate(self.store, 'writer-a')
        activate(self.store, 'vision-a')
        activate(self.store, 'video-a')
        with patch.dict(os.environ, {'MMV_WRITER_API_KEY': 'unrelated-env-secret'}):
            self.assertEqual(self.store.key('MMV_WRITER_API_KEY'), 'secret-a')
        activate(self.store, 'writer-b')
        self.assertEqual(self.store.settings()['writer_model'], 'writer-b')
        self.assertEqual(self.store.key('MMV_WRITER_API_KEY'), 'secret-b')
        self.assertEqual(self.store.key('MMV_VISION_API_KEY'), 'vision-secret')
        self.assertEqual(self.store.key(), 'video-secret')
        self.store.save_key('MMV_WRITER_API_KEY', 'updated-b')
        activate(self.store, 'writer-a')
        self.assertEqual(self.store.key('MMV_WRITER_API_KEY'), 'secret-a')
        state = self.store.settings()
        state.update(writer_api_profile='', vision_api_profile='', video_api_profile='')
        save_settings(self.store, state)
        self.assertEqual(self.store.settings(), original)
        self.assertEqual(self.store.key('MMV_WRITER_API_KEY'), 'manual-secret')
        public = json.dumps(public_profiles(self.store))
        for secret in ('secret-a', 'secret-b', 'vision-secret', 'video-secret', 'updated-b'):
            self.assertNotIn(secret, public)
        self.assertIn('updated-b', self.store.secret_values())
        if os.name != 'nt':
            self.assertEqual(stat.S_IMODE((self.store.home / 'api-profiles.json').stat().st_mode), 0o600)

    def test_invalid_profiles_do_not_replace_accounts_or_cross_roles(self):
        self.writer('writer-a', 'secret-a')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.writer('writer-a', 'changed')
        for role, config in (
            ('writer', {'writer_url': 'https://example.test/v1?key=secret', 'writer_mode': 'api', 'writer_model': 'x'}),
            ('writer', {'writer_mode': 'local', 'writer_model': 'x'}),
            ('video', {'backend': 'local_h3'}),
            ('vision', {'backend': 'wavespeed'}),
            ('writer', None),
        ):
            with self.subTest(role=role, config=config), self.assertRaises(ValueError):
                save_profile(self.store, 'bad', role, config)
        settings = self.store.settings()
        settings['vision_api_profile'] = 'writer-a'
        from mmv.api_profiles import resolve
        with self.assertRaises(ValueError):
            resolve(self.store, settings)

    def test_settings_api_selects_profiles_and_restores_manual_settings(self):
        self.writer('writer-a', 'secret-a')
        app = create_app(self.store.home, test_hosts=True)
        with TestClient(app) as client:
            original = client.get('/api/settings').json()['settings']
            response = client.put('/api/settings', json={**original, 'writer_api_profile': 'writer-a'})
            self.assertEqual(response.status_code, 200, response.text)
            data = client.get('/api/settings')
            self.assertEqual(data.json()['settings']['writer_model'], 'writer-a')
            self.assertNotIn('secret-a', data.text)
            self.assertTrue(data.json()['keys']['MMV_WRITER_API_KEY'])
            response = client.post('/api/api-profiles', json={'name': 'copy-a', 'role': 'writer'})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertNotIn('secret-a', response.text)
            current = client.get('/api/settings').json()['settings']
            response = client.put('/api/settings', json={**current, 'writer_api_profile': ''})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(client.get('/api/settings').json()['settings'], original)
            (self.store.home / 'studio.log').write_text('Previous inactive account: secret-a')
            log = client.get('/api/log/latest')
            self.assertNotIn('secret-a', log.text)
            self.assertIn('[redacted]', log.text)
            with patch.object(app.state.jobs, 'require_idle', side_effect=BusyError('busy')):
                self.assertEqual(client.post('/api/api-profiles', json={'name': 'blocked', 'role': 'writer'}).status_code, 409)
                self.assertEqual(client.put('/api/settings', json={**original, 'writer_api_profile': 'writer-a'}).status_code, 409)
                self.assertEqual(client.delete('/api/api-profiles/copy-a').status_code, 409)
                self.assertEqual(client.post('/api/api-profiles/copy-a/activate').status_code, 409)
                self.assertEqual(client.patch('/api/settings', json={'auto_updates': True}).status_code, 409)
                self.assertEqual(client.post('/api/starter-assets', json={'accept_starter_signer': True}).status_code, 409)

    def test_agent_cli_can_save_list_and_activate_without_echoing_key(self):
        config = self.store.home / 'input.json'
        config.write_text(json.dumps({'writer_url': 'https://writer.example/v1',
            'writer_model': 'chat', 'writer_mode': 'api', 'writer_call_estimate': .1}))
        commands = [ ['save-api-profile', 'account-one', '--role', 'writer', '--config', str(config), '--key-env', 'TEST_PROFILE_KEY'],
                     ['list-api-profiles'], ['use-api-profile', 'account-one'] ]
        for command in commands:
            result = subprocess.run([sys.executable, '-m', 'mmv.setup', '--data-dir', str(self.store.home), *command],
                env={**os.environ, 'TEST_PROFILE_KEY': 'private-cli-key'}, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('private-cli-key', result.stdout + result.stderr)
        self.assertEqual(self.store.key('MMV_WRITER_API_KEY'), 'private-cli-key')
