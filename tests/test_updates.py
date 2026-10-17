"""Update transactions use local disposable Git repositories and mock pip only."""
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from mmv import updates
from mmv.storage import Storage, write_json, read_json
from webapp.mondo_web import create_app


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.remote = self.base / 'remote.git'
        subprocess.run(['git', 'init', '--bare', '--initial-branch=main', str(self.remote)], check=True, capture_output=True)
        self.writer = self.base / 'writer'
        subprocess.run(['git', 'clone', str(self.remote), str(self.writer)], check=True, capture_output=True)
        git(self.writer, 'config', 'user.email', 'test@example.invalid')
        git(self.writer, 'config', 'user.name', 'Update fixture')
        (self.writer / 'pyproject.toml').write_text('[project]\nname="mondo-music-video"\nversion="1.0.0"\n')
        (self.writer / 'app.txt').write_text('old')
        (self.writer / '.gitignore').write_text('data/\n')
        git(self.writer, 'add', '.')
        git(self.writer, 'commit', '-m', 'initial')
        git(self.writer, 'push', 'origin', 'main')
        self.local = self.base / 'local'
        subprocess.run(['git', 'clone', str(self.remote), str(self.local)], check=True, capture_output=True)
        self.head = git(self.local, 'rev-parse', 'HEAD')
        self.store = Storage(self.base / 'private')
        settings = self.store.settings()
        settings['auto_updates'] = True
        write_json(self.store.home / 'settings.json', settings)
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(updates, '_virtualenv', return_value=True))
        self.build = self.stack.enter_context(patch.object(updates, '_build_wheel', side_effect=lambda store, source, output: output / (source.name + '.whl')))
        self.install = self.stack.enter_context(patch.object(updates, '_install_wheel'))

    def tearDown(self):
        self.stack.close()
        self.temp.cleanup()

    def advance(self):
        (self.writer / 'app.txt').write_text('new')
        (self.writer / 'pyproject.toml').write_text('[project]\nname="mondo-music-video"\nversion="1.0.1"\n')
        git(self.writer, 'add', '.')
        git(self.writer, 'commit', '-m', 'update')
        git(self.writer, 'push', 'origin', 'main')
        return git(self.writer, 'rev-parse', 'HEAD')

    def check(self, **kwargs):
        return updates.startup_update(self.store, root=self.local, **kwargs)

    def test_default_is_notify_only_and_preference_roundtrips(self):
        store = Storage(self.base / 'defaults')
        self.assertFalse(store.settings()['auto_updates'])
        with TestClient(create_app(store.home), base_url='http://localhost') as client:
            settings = client.get('/api/settings').json()['settings']
            self.assertFalse(settings['auto_updates'])
            settings.pop('h3_models', None)
            settings['auto_updates'] = True
            client.put('/api/settings', json=settings).raise_for_status()
            self.assertTrue(client.get('/api/settings').json()['settings']['auto_updates'])
            settings['auto_updates'] = False
            client.put('/api/settings', json=settings).raise_for_status()
            self.assertFalse(client.get('/api/settings').json()['settings']['auto_updates'])

    def test_notify_mode_never_installs_or_changes_checkout(self):
        self.advance()
        result = self.check(automatic=False)
        self.assertEqual(result['state'], 'available')
        self.assertTrue(result['available'])
        self.assertEqual(result['available_version'], '1.0.1')
        self.assertEqual(git(self.local, 'rev-parse', 'HEAD'), self.head)
        self.install.assert_not_called()
        self.build.assert_not_called()

    def test_current_version_does_not_install(self):
        self.assertEqual(self.check()['state'], 'current')
        self.install.assert_not_called()

    def test_success_advances_once_preserves_private_data_and_restarts(self):
        target = self.advance()
        private = self.local / 'data/actors/private/actor.json'
        private.parent.mkdir(parents=True)
        private.write_text('private actor stays here')
        result = self.check()
        self.assertTrue(result['restart'])
        self.assertEqual(git(self.local, 'rev-parse', 'HEAD'), target)
        self.assertEqual((self.local / 'app.txt').read_text(), 'new')
        self.assertEqual(private.read_text(), 'private actor stays here')
        self.install.assert_called_once()
        with patch.dict(os.environ, {'MMV_UPDATE_RESTART_COMMIT': target}):
            result = self.check()
        self.assertEqual(result['state'], 'updated')
        self.assertFalse(result.get('restart', False))
        self.install.assert_called_once()

    def test_local_work_and_divergence_are_never_discarded(self):
        self.advance()
        (self.local / 'app.txt').write_text('local work')
        self.assertEqual(self.check()['state'], 'blocked')
        self.assertEqual((self.local / 'app.txt').read_text(), 'local work')
        git(self.local, 'config', 'user.email', 'test@example.invalid')
        git(self.local, 'config', 'user.name', 'Local developer')
        git(self.local, 'add', 'app.txt')
        git(self.local, 'commit', '-m', 'local branch work')
        self.assertIn('diverged', self.check()['message'])
        self.install.assert_not_called()

    def test_interrupted_production_defers_installation(self):
        self.advance()
        write_json(self.store.home / 'operation.json', {'state': 'running'})
        self.assertIn('interrupted production', self.check()['message'])
        self.install.assert_not_called()

    def test_ignored_collision_refuses_merge_and_recovers_package(self):
        self.advance()
        (self.writer / 'data').mkdir()
        (self.writer / 'data/private.txt').write_text('remote asset')
        git(self.writer, 'add', '-f', 'data/private.txt')
        git(self.writer, 'commit', '-m', 'collision fixture')
        git(self.writer, 'push', 'origin', 'main')
        (self.local / 'data').mkdir()
        (self.local / 'data/private.txt').write_text('local private asset')
        result = self.check()
        self.assertTrue(result['fatal'])
        self.assertEqual(git(self.local, 'rev-parse', 'HEAD'), self.head)
        self.assertEqual((self.local / 'data/private.txt').read_text(), 'local private asset')
        self.assertEqual(self.install.call_count, 2)
        self.assertTrue(self.install.call_args.kwargs['rollback'])

    def test_failed_install_recovers_and_stops_startup(self):
        self.advance()
        self.install.side_effect = [updates.UpdateError('failed install'), None]
        result = self.check()
        self.assertTrue(result['fatal'])
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(git(self.local, 'rev-parse', 'HEAD'), self.head)
        self.assertEqual(self.install.call_count, 2)

    def test_failed_preparation_leaves_old_install_usable(self):
        self.advance()
        self.build.side_effect = updates.UpdateError('build failed')
        self.assertEqual(self.check()['state'], 'unavailable')
        self.install.assert_not_called()
        self.assertEqual(git(self.local, 'rev-parse', 'HEAD'), self.head)

    def test_failed_recovery_stops_launch_and_checkout_is_unchanged(self):
        self.advance()
        self.install.side_effect = updates.UpdateError('mock installation error')
        result = self.check()
        self.assertTrue(result['fatal'])
        self.assertIn('recovery failed', result['message'])
        self.assertEqual(git(self.local, 'rev-parse', 'HEAD'), self.head)

    def test_configured_non_default_branch_and_remote_are_followed(self):
        git(self.writer, 'checkout', '-b', 'collaboration')
        git(self.writer, 'push', '-u', 'origin', 'collaboration')
        git(self.local, 'fetch', 'origin')
        git(self.local, 'checkout', '-b', 'collaboration', '--track', 'origin/collaboration')
        git(self.local, 'remote', 'rename', 'origin', 'collaborator')
        (self.writer / 'app.txt').write_text('collaboration update')
        git(self.writer, 'add', 'app.txt')
        git(self.writer, 'commit', '-m', 'branch update')
        git(self.writer, 'push')
        result = self.check(automatic=False)
        self.assertEqual(result['branch'], 'collaboration')
        self.assertEqual(result['available_commit'], git(self.writer, 'rev-parse', 'HEAD'))
        self.assertEqual(git(self.local, 'rev-parse', 'HEAD'), self.head)

    def test_installed_wheel_remembers_original_source(self):
        with patch.object(updates, '__file__', str(self.base / 'site-packages/mmv/updates.py')), \
             patch.object(updates.importlib.metadata, 'distribution', side_effect=updates.importlib.metadata.PackageNotFoundError):
            write_json(self.store.home / updates.STATUS_FILE, {'source_root': str(self.local)})
            self.assertEqual(updates.source_root(self.store), self.local)

    def test_offline_check_continues_and_detached_checkout_is_supported_manually(self):
        original = updates._git
        def offline(root, *args, **kwargs):
            if args[0] == 'fetch':
                raise subprocess.TimeoutExpired('git', 15)
            return original(root, *args, **kwargs)
        with patch.object(updates, '_git', side_effect=offline):
            self.assertEqual(self.check()['state'], 'unavailable')
        git(self.local, 'checkout', '--detach')
        self.assertEqual(self.check()['state'], 'blocked')
        self.install.assert_not_called()

    def test_checkout_lease_prevents_parallel_launcher_updates(self):
        with patch.object(updates, 'source_root', return_value=self.local):
            with updates.repository_session(self.store):
                with self.assertRaises(updates.UpdateError):
                    with updates.repository_session(self.store):
                        self.fail('A second launcher entered the same checkout')
            with updates.repository_session(self.store):
                pass

    def test_launcher_reexec_preserves_arguments_and_skip_marker(self):
        from mmv.setup import main
        class ExecCalled(Exception):
            pass
        args = ['--data-dir', str(self.store.home), 'serve', '--port', '8234']
        with patch.object(updates, 'source_root', return_value=self.local), \
             patch.object(updates, 'startup_update', return_value={
                 'message': 'Installed', 'restart': True, 'installed_commit': 'fixture-commit'}), \
             patch('mmv.setup.os.execve', side_effect=ExecCalled) as execute:
            with self.assertRaises(ExecCalled):
                main(args)
        self.assertEqual(execute.call_args.args[1][1:], ['-m', 'mmv.setup', *args])
        self.assertEqual(execute.call_args.args[2]['MMV_UPDATE_RESTART_COMMIT'], 'fixture-commit')

    def test_repository_link_and_status_hide_private_paths(self):
        self.assertEqual(updates.repository_link('git@github.com:someone/mmv.git'), 'https://github.com/someone/mmv')
        self.assertEqual(updates.repository_link('https://user:secret@github.com/someone/mmv.git?token=secret'), 'https://github.com/someone/mmv')
        self.assertIsNone(updates.repository_link('/private/local/repo'))
        write_json(self.store.home / updates.STATUS_FILE, {'state': 'available', 'available': True,
                   'message': 'Update available', 'source_root': '/private/source', 'repository_url': 'https://github.com/example/mmv'})
        with TestClient(create_app(self.store.home), base_url='http://localhost') as client:
            status = client.get('/api/update').json()
            self.assertTrue(status['available'])
            self.assertNotIn('source_root', status)

    def test_untracked_files_and_system_python_skip_install(self):
        self.advance()
        (self.local / 'uncommitted.txt').write_text('new work')
        self.assertEqual(self.check()['state'], 'blocked')
        (self.local / 'uncommitted.txt').unlink()
        with patch.object(updates, '_virtualenv', return_value=False):
            self.assertIn('virtual environment', self.check()['message'])
        self.install.assert_not_called()
