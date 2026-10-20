import json, unittest, urllib.request
from unittest import mock

from mmv import writer_usage


class FakeResponse:
    def __init__(self, body): self.body = body
    def read(self): return json.dumps(self.body).encode()
    def __enter__(self): return self
    def __exit__(self, *exc): return False


class WriterUsageTests(unittest.TestCase):
    def test_launch_context(self):
        self.assertEqual(writer_usage.launch_context({'writer_launch': json.dumps(['srv', '-c', '16384'])}), 16384)
        self.assertEqual(writer_usage.launch_context({'writer_launch': json.dumps(['--ctx-size', '8192'])}), 8192)
        for bad in ('', 'not json', json.dumps(['-c', 'x']), json.dumps(['-c', '100']), json.dumps(['-c'])):
            self.assertIsNone(writer_usage.launch_context({'writer_launch': bad}))

    def test_usage_line(self):
        captured = {'usage': {'prompt_tokens': 1000, 'completion_tokens': 500}, 'timings': {'predicted_per_second': 42.4}}
        self.assertEqual(writer_usage.usage_line(captured, 10000, 'seg000'),
                         '   [tokens] seg000: 1,000 prompt + 500 generated = 1,500 total — 15% context used, 42 t/s')
        self.assertNotIn('context used', writer_usage.usage_line(captured, None))
        self.assertEqual(writer_usage.usage_line({}, 8192), '')

    def test_observe_taps_without_changing_response_and_restores_urlopen(self):
        original = urllib.request.urlopen
        body = {'choices': [], 'usage': {'prompt_tokens': 3, 'completion_tokens': 4}}
        captured = {}
        with mock.patch('urllib.request.urlopen', lambda *a, **k: FakeResponse(body)) as fake:
            def call():
                with urllib.request.urlopen('http://x') as r:
                    return json.loads(r.read())
            self.assertEqual(writer_usage.observe(call, captured), body)
            self.assertIs(urllib.request.urlopen, fake)
        self.assertEqual(captured['usage'], body['usage'])
        self.assertIs(urllib.request.urlopen, original)

    def test_observe_restores_urlopen_when_call_raises(self):
        before = urllib.request.urlopen
        with self.assertRaises(RuntimeError):
            writer_usage.observe(lambda: (_ for _ in ()).throw(RuntimeError('x')), {})
        self.assertIs(urllib.request.urlopen, before)


if __name__ == '__main__':
    unittest.main()
