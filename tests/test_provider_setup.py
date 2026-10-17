import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from mmv.provider_setup import NoRedirect, inspect_writer


class ProviderSetupTests(unittest.TestCase):
    def response(self, payload):
        return io.BytesIO(json.dumps(payload).encode())

    def test_listing_is_get_only_and_does_not_claim_inference(self):
        with patch.dict(os.environ, {"TEST_PROVIDER_KEY": "private-value"}), patch(
                "mmv.provider_setup.urllib.request.build_opener") as factory:
            factory.return_value.open.return_value = self.response(
                {"data": [{"id": "chat-b"}, {"id": "chat-a"}, {"id": "chat-a"}]})
            result = inspect_writer("https://example.test/v1/", key_env="TEST_PROVIDER_KEY")
            req = factory.return_value.open.call_args.args[0]
            self.assertEqual(req.get_method(), "GET")
            self.assertEqual(req.full_url, "https://example.test/v1/models")
            self.assertIsNone(req.data)
            self.assertEqual(result["model_ids"], ["chat-a", "chat-b"])
            self.assertFalse(result["inference_verified"])
            self.assertFalse(result["generation_submitted"])
            self.assertNotIn("private-value", json.dumps(result))

    def test_unsafe_urls_rejected_before_network(self):
        for url in ("http://remote.test/v1", "https://user:secret@example.test/v1",
                    "https://example.test/v1?key=secret", "file:///tmp/models",
                    "https://example.test:bad/v1", "https://example.test/v1#secret"):
            with self.subTest(url=url), patch("urllib.request.build_opener") as factory:
                with self.assertRaises(ValueError):
                    inspect_writer(url)
                factory.assert_not_called()

    def test_missing_key_rejected_before_network(self):
        with patch.dict(os.environ, {}, clear=True), patch("urllib.request.build_opener") as factory:
            with self.assertRaises(ValueError):
                inspect_writer("https://example.test/v1", key_env="MISSING")
            factory.assert_not_called()

    def test_invalid_responses_and_errors_do_not_echo_body(self):
        for raw in (b"secret-invalid-json", b'{"data": []}', b'{"models": []}',
                    b"x" * (2 * 1024 * 1024 + 1)):
            with self.subTest(length=len(raw)), patch("urllib.request.build_opener") as factory:
                factory.return_value.open.return_value = io.BytesIO(raw)
                with self.assertRaises(ValueError) as exc:
                    inspect_writer("http://127.0.0.1:8080/v1")
                self.assertNotIn("secret-invalid-json", str(exc.exception))
        with patch("urllib.request.build_opener") as factory:
            factory.return_value.open.side_effect = urllib.error.HTTPError(
                "https://example.test", 401, "secret-body", {}, None)
            with self.assertRaisesRegex(ValueError, "HTTP 401") as exc:
                inspect_writer("https://example.test/v1")
            self.assertNotIn("secret-body", str(exc.exception))

    def test_redirects_never_forward_credentials(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.test"))

    def test_cli_against_mock_service_without_creating_application_data(self):
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                requests.append((self.path, self.headers.get('Authorization')))
                if self.path == '/redirect/models':
                    self.send_response(302)
                    self.send_header('Location', '/v1/models')
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(b'{"data":[{"id":"mock-chat"}]}')

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as temporary:
                home = Path(temporary) / 'unused-data'
                for path, expected in (('/v1', 0), ('/redirect', 1)):
                    result = subprocess.run([sys.executable, '-m', 'mmv.setup',
                        '--data-dir', str(home), 'inspect-api',
                        f'http://127.0.0.1:{server.server_port}{path}', '--key-env', 'MOCK_KEY'],
                        env={**os.environ, 'MOCK_KEY': 'mock-secret'},
                        capture_output=True, text=True, timeout=15)
                    self.assertEqual(result.returncode, expected, result.stderr)
                    self.assertNotIn('mock-secret', result.stdout + result.stderr)
                    self.assertFalse(home.exists())
                    if expected == 0:
                        self.assertEqual(json.loads(result.stdout)['model_ids'], ['mock-chat'])
                self.assertEqual(requests, [('/v1/models', 'Bearer mock-secret'),
                                            ('/redirect/models', 'Bearer mock-secret')])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
