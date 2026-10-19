import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

import httpx

from mmv.comfy_sdk import wait_for_job
from mmv.engine.backends.base import BackendError
from mmv.storage import read_json


class WaitForJobTests(unittest.TestCase):
    def remote(self, steps):
        remote = NS(status='running', steps=list(steps))
        def refresh():
            step = remote.steps.pop(0)
            if isinstance(step, Exception):
                raise step
            remote.status = step
        remote.refresh = refresh
        return remote

    def test_a_status_check_that_times_out_does_not_end_the_job(self):
        remote = self.remote([httpx.ReadTimeout('timed out'), httpx.ConnectError('busy'), 'running', 'succeeded'])
        with tempfile.TemporaryDirectory() as tmp:
            path, record = Path(tmp) / 'receipt.json', {}
            wait_for_job(remote, record, path, pause=0, retry_pause=0)
            self.assertEqual((remote.status, read_json(path)['state']), ('succeeded', 'succeeded'))

    def test_no_limit_by_default_and_an_explicit_limit_still_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'receipt.json'
            wait_for_job(self.remote(['running'] * 50 + ['succeeded']), {}, path, pause=0)
            with self.assertRaisesRegex(BackendError, 'timed out'):
                wait_for_job(self.remote(['running'] * 5), {}, path, timeout=0.01, pause=0.02)

    def test_other_errors_are_not_swallowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                wait_for_job(self.remote([ValueError('bad')]), {}, Path(tmp) / 'r.json', pause=0)


if __name__ == '__main__':
    unittest.main()
