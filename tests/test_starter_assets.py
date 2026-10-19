import json
import shutil
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from mmv.jobs import BusyError
from mmv.starter_assets import ACTORS, STYLES, install
from mmv.storage import Storage, write_json
from webapp.mondo_web import create_app


class StarterAssetsTests(unittest.TestCase):
    @unittest.skipIf(os.name == 'nt', 'POSIX shell installer')
    def test_shell_installer_runs_starter_step_and_respects_explicit_opt_out(self):
        root = Path(self.temp.name) / 'installer'
        (root / '.venv/bin').mkdir(parents=True)
        shutil.copyfile(self.source.parent / 'install.sh', root / 'install.sh')
        log = root / 'calls.jsonl'
        stub = root / '.venv/bin/python'
        stub.write_text('#!' + sys.executable + '\nimport json,sys\n'
            + 'with open(' + repr(str(log)) + ', "a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n')
        stub.chmod(0o755)
        env = {**os.environ, 'MMV_PYTHON': str(stub)}
        for args, expect_starters in (
            (['--accept-starter-signer', '--non-interactive'], True),
            (['--non-interactive', '--skip-starter-assets'], False),
        ):
            log.write_text('')
            result = subprocess.run(['bash', str(root / 'install.sh'), *args], env=env,
                capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            starter = [call for call in calls if 'install-starter-assets' in call]
            self.assertEqual(bool(starter), expect_starters)
            if starter:
                self.assertIn('--accept-starter-signer', starter[0])
                self.assertIn('--non-interactive', starter[0])
            self.assertIn(['-m', 'mmv.setup', 'doctor'], calls)
            self.assertNotIn(['-m', 'mmv.setup', 'configure'], calls)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Storage(Path(self.temp.name) / 'data')
        self.source = Path(__file__).resolve().parent.parent / 'examples'

    def test_fresh_install_preserves_original_packages_and_existing_changes(self):
        report = install(self.store, accept_signer=True)
        self.assertEqual(len(report['installed']), 10)
        self.assertFalse(report['pending_signer'])
        for actor_id in ACTORS:
            record = self.store.actor(actor_id)
            self.assertTrue(record['oap']['signature_valid'])
            self.assertEqual((self.store.home / 'actors' / actor_id / 'original.oap').read_bytes(),
                (self.source / 'starter-cast' / (actor_id + '.oap')).read_bytes())
        path = self.store.home / 'styles/noir_bw.json'
        path.write_text(json.dumps({'id': 'noir_bw', 'name': 'My edited noir', 'direction': 'Custom'}))
        original = path.read_bytes()
        report = install(self.store, accept_signer=True)
        self.assertEqual(len(report['preserved']), 10)
        self.assertFalse(report['installed'])
        self.assertEqual(path.read_bytes(), original)

    def test_actor_import_requires_signer_acceptance_but_styles_install(self):
        report = install(self.store)
        self.assertEqual(len(report['installed']), 6)
        self.assertEqual(len(report['pending_signer']), 4)
        self.assertFalse(list((self.store.home / 'actors').iterdir()))
        report = install(self.store, accept_signer=True)
        self.assertEqual(len(report['installed']), 4)

    def test_corrupt_bundle_refused_before_any_import(self):
        source = Path(self.temp.name) / 'examples'
        def _link_or_copy(src, dst):
            try:
                os.link(src, dst)
            except OSError:
                shutil.copy2(src, dst)
        shutil.copytree(self.source / 'starter-cast', source / 'starter-cast', copy_function=_link_or_copy)
        shutil.copytree(self.source / 'style-presets', source / 'style-presets')
        (source / 'style-presets/noir_bw.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            install(self.store, accept_signer=True, root=source)
        self.assertFalse(list((self.store.home / 'actors').iterdir()))
        self.assertEqual(len(list((self.store.home / 'styles').iterdir())), 1)

    def test_gui_deletion_survives_restart_and_install_until_explicit_restore(self):
        install(self.store, accept_signer=True)
        app = create_app(self.store.home, test_hosts=True)
        exported = self.store.home / 'exports/keep.oap'
        exported.write_bytes(b'previous export')
        with TestClient(app) as client:
            for path in ('/api/actors/animal_pig', '/api/styles/noir_bw', '/api/styles/daylight'):
                with patch.object(app.state.jobs, 'require_idle', side_effect=BusyError('busy')):
                    self.assertEqual(client.delete(path).status_code, 409)
                result = client.delete(path)
                self.assertEqual(result.status_code, 200, result.text)
            self.assertFalse(self.store.actor('animal_pig'))
            self.assertEqual(exported.read_bytes(), b'previous export')
        restarted = Storage(self.store.home)
        self.assertFalse((restarted.home / 'styles/daylight.json').exists())
        report = install(restarted, accept_signer=True)
        self.assertEqual(set(report['removed']), {'actors/animal_pig', 'styles/noir_bw'})
        self.assertFalse(restarted.actor('animal_pig'))
        report = install(restarted, accept_signer=True, restore=True)
        self.assertEqual(set(report['installed']), {'actors/animal_pig', 'styles/noir_bw'})

    def test_existing_style_id_in_another_file_and_linked_assets_are_preserved(self):
        write_json(self.store.home / 'styles/custom.json', {'id': 'noir_bw', 'name': 'Custom', 'direction': 'Custom'})
        report = install(self.store, accept_signer=True)
        self.assertIn('styles/noir_bw', report['preserved'])
        self.assertFalse((self.store.home / 'styles/noir_bw.json').exists())
        try:
            (self.store.home / 'actors/alias').symlink_to(self.store.home / 'actors/animal_pig', target_is_directory=True)
            (self.store.home / 'styles/alias.json').symlink_to(self.store.home / 'styles/sun_bleach.json')
        except OSError:
            self.skipTest('symlinks unavailable')
        with TestClient(create_app(self.store.home, test_hosts=True)) as client:
            self.assertEqual(client.delete('/api/actors/alias').status_code, 400)
            self.assertEqual(client.delete('/api/styles/alias').status_code, 400)
            self.assertEqual(client.delete('/api/actors/missing').status_code, 400)
            self.assertEqual(client.delete('/api/styles/missing').status_code, 400)
        self.assertTrue(self.store.actor('animal_pig'))
        self.assertTrue((self.store.home / 'styles/sun_bleach.json').exists())
