import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(script, home, *args):
    env = {**os.environ, 'MMV_HOME': str(home)}
    return subprocess.run(['bash', str(ROOT / script), *args], capture_output=True, text=True, env=env, timeout=60)


class StartScriptTests(unittest.TestCase):
    def test_scripts_parse(self):
        for name in ('start.sh', 'stop.sh', 'start.command', 'stop.command'):
            self.assertEqual(subprocess.run(['bash', '-n', str(ROOT / name)]).returncode, 0, name)

    def test_stop_without_a_pid_file_says_how_to_stop_and_fails(self):
        with tempfile.TemporaryDirectory() as home:
            done = run('stop.sh', home)
            self.assertEqual(done.returncode, 1)
            self.assertIn('Ctrl+C', done.stderr)

    def test_stop_cleans_up_a_dead_pid_and_never_signals_other_processes(self):
        with tempfile.TemporaryDirectory() as home:
            pid = Path(home) / 'server.pid'
            sleeper = subprocess.Popen(['sleep', '30'])
            try:
                pid.write_text(str(sleeper.pid))                      # alive, but not a Mondo process
                done = run('stop.sh', home)
                self.assertIn('not running', done.stdout)
                self.assertIsNone(sleeper.poll())                     # the unrelated process was left alone
                self.assertFalse(pid.exists())
            finally:
                sleeper.kill()
                sleeper.wait()
            pid.write_text('999999')
            self.assertEqual(run('stop.sh', home).returncode, 0)

    def test_start_needs_an_install(self):
        with tempfile.TemporaryDirectory() as copy:
            (Path(copy) / 'start.sh').write_text((ROOT / 'start.sh').read_text())
            done = subprocess.run(['bash', str(Path(copy) / 'start.sh')], capture_output=True, text=True, timeout=30)
            self.assertEqual(done.returncode, 1)
            self.assertIn('install.sh', done.stderr)


if __name__ == '__main__':
    unittest.main()


class PortabilityTests(unittest.TestCase):
    def test_scripts_avoid_linux_only_and_bash4_only_constructs(self):
        text = (ROOT / 'start.sh').read_text() + (ROOT / 'stop.sh').read_text()
        self.assertNotIn('/proc/', text)                          # macOS has no /proc
        import re
        for array in ('MMV_ARGS', 'MMV_DATA'):                     # bash 3.2 treats a bare empty array as unset under set -u
            self.assertIsNone(re.search(r'(?<!\+)"\$\{' + array + r'\[@\]\}"', text), array)
            self.assertIn('${' + array + '[@]+"${' + array + '[@]}"}', text)
        self.assertIn('Library/Application Support', text)       # the app's data folder on a Mac
        for name in ('start.command', 'stop.command'):
            self.assertTrue(os.access(ROOT / name, os.X_OK), name)
