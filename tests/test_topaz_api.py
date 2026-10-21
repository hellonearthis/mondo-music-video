import json
import tempfile
import unittest
from pathlib import Path

from mmv import topaz_api

INFO = {"width": 1920, "height": 1080, "frame_rate": 30.0, "frame_count": 300, "duration": 10.0,
        "size": 10, "has_audio": True}


class Context:
    def __init__(self):
        self.messages = []

    def check(self):
        pass

    def wait(self, seconds):
        pass

    def update(self, message, progress=None):
        self.messages.append(message)


def scripted(replies, calls):
    def send(method, url, headers, body):
        calls.append((method, url.split("topazlabs.com")[-1]))
        return replies.get((method, calls[-1][1].split("/")[-1]), (200, {}, b"{}"))
    return send


class TopazApiTests(unittest.TestCase):
    def test_request_body_rounds_and_picks_encoder(self):
        body = topaz_api.request_body(INFO, "prob-4", 2)
        self.assertEqual(body["output"]["resolution"], {"width": 3840, "height": 2160})
        self.assertEqual(body["output"]["videoEncoder"], "H264")
        wide = topaz_api.request_body(INFO, "prob-4", 4)
        self.assertEqual(wide["output"]["videoEncoder"], "H265")
        silent = topaz_api.request_body({**INFO, "has_audio": False, "width": 1001}, "prob-4", 1)
        self.assertEqual(silent["output"]["audioTransfer"], "None")
        self.assertEqual(silent["output"]["resolution"]["width"], 1004)

    def test_frame_rate_and_tuning_options(self):
        options = {"mode": "Manual", "tuning": {"details": 0.3},
                   "interpolation": {"model": "apo-8", "fps": 60, "slowmo": 2, "duplicate": True}}
        body = topaz_api.request_body(INFO, "prob-4", 2, options)
        self.assertEqual(body["filters"], [{"model": "prob-4", "auto": "Manual", "details": 0.3},
                                           {"model": "apo-8", "fps": 60, "slowmo": 2, "duplicate": True}])
        self.assertEqual(body["output"]["frameRate"], 60)
        retime = topaz_api.request_body(INFO, "none", 4, {"interpolation": {"model": "chr-2", "slowmo": 4}})
        self.assertEqual(retime["output"]["resolution"], {"width": 1920, "height": 1080})
        self.assertEqual(retime["filters"], [{"model": "chr-2", "slowmo": 4}])
        auto = topaz_api.request_body(INFO, "prob-4", 2, {"tuning": {"details": 0.3}})
        self.assertEqual(auto["filters"], [{"model": "prob-4"}], "Auto mode sends no tuning")
        with self.assertRaises(ValueError):
            topaz_api.request_body(INFO, "none", 1, {})

    def test_live_models_and_catalog(self):
        from mmv import topaz_models
        send = lambda *a: (200, {}, b'{"supportedModels": ["prob-4", "apo-8", "new-1"]}')
        live = topaz_api.live_models(send, "")
        catalog = topaz_models.catalog(live)
        ids = [m["id"] for g in catalog["upscale"] for m in g["models"]]
        self.assertEqual(ids, ["prob-4", "new-1"])
        self.assertEqual([m["id"] for m in catalog["interpolation"]], ["apo-8"])
        self.assertIsNone(topaz_api.live_models(lambda *a: (500, {}, b""), ""))
        self.assertTrue(topaz_models.catalog()["upscale"])

    def test_segments_cover_the_file(self):
        spans = topaz_api.segments(1_200_000_000, 3)
        self.assertEqual(spans, [(0, 500_000_000), (500_000_000, 1_000_000_000), (1_000_000_000, 1_200_000_000)])

    def test_endpoint_requires_https(self):
        with self.assertRaises(ValueError):
            topaz_api.endpoint("http://example.invalid")
        self.assertEqual(topaz_api.endpoint(""), topaz_api.API_URL)

    def test_http_error_is_explained_without_key(self):
        send = lambda *a: (402, {}, b'{"message": "no credits"}')
        with self.assertRaisesRegex(ValueError, "not enough Topaz credits"):
            topaz_api.call(send, "", "secret-key", "PATCH", "/video/x/accept")

    def test_failure_after_reserve_cancels_and_never_retries_accept(self):
        calls = []
        estimate = json.dumps({"requestId": "r1", "estimates": {"cost": [1, 2], "time": [1, 2]}}).encode()
        send = scripted({("POST", ""): (200, {}, estimate),
                         ("GET", "status"): (200, {}, b'{"status": "failed", "errorCode": "PROCESSING_FAILURE"}'),
                         ("PATCH", "accept"): (202, {}, b'{"urls": ["https://u.invalid/1"]}')}, calls)
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "in.mp4"
            source.write_bytes(b"0123456789")
            with self.assertRaisesRegex(ValueError, "PROCESSING_FAILURE"):
                topaz_api.run(send, lambda *a: None, "", "k", source, Path(folder) / "out.mp4", INFO, "prob-4", 2, 2,
                              Context(), interval=0)
        self.assertEqual(calls.count(("PATCH", "/video/r1/accept")), 1)
        self.assertIn(("DELETE", "/video/r1"), calls)

    def test_price_above_approval_reserves_nothing(self):
        calls = []
        estimate = json.dumps({"requestId": "r1", "estimates": {"cost": [5, 9], "time": [1, 2]}}).encode()
        send = scripted({("POST", ""): (200, {}, estimate)}, calls)
        with self.assertRaisesRegex(ValueError, "Nothing was reserved"):
            topaz_api.run(send, None, "", "k", "x", "y", INFO, "prob-4", 2, 3, Context())
        self.assertEqual([c[0] for c in calls], ["POST"])

    def test_status_line_uses_topaz_message_and_dedupes(self):
        queued = {"status": "initializing", "message": "Queued - waiting for resources", "progress": 0,
                  "estimates": {"time": [1188, 1260]}}
        self.assertEqual(topaz_api.describe(queued),
                         "Queued - waiting for resources (0%, about 21 min once running)")
        self.assertEqual(topaz_api.describe({"status": "processing", "progress": 40.2}), "Processing (40%)")
        replies = iter([queued, queued, {**queued, "status": "processing", "message": "Processing", "progress": 5},
                        {"status": "complete", "download": {"url": "https://d.example/x"}}])
        send = lambda *a: (200, {}, json.dumps(next(replies)).encode())
        context = Context()
        self.assertEqual(topaz_api.wait_complete(send, "", "k", "r1", context, interval=0, limit=0), "https://d.example/x")
        self.assertEqual(len(context.messages), 2, "an unchanged status is not logged again")

    def test_unsafe_transfer_urls_are_refused(self):
        for url in ("http://good.example/x", "https://127.0.0.1/x", "https://localhost/x", "https://10.0.0.5/x",
                    "https://user@good.example/x", "https://intranet/x"):
            with self.assertRaises(ValueError, msg=url):
                topaz_api.safe_url(url)
        self.assertEqual(topaz_api.safe_url("https://bucket.s3.amazonaws.com/x?sig=1"), "https://bucket.s3.amazonaws.com/x?sig=1")

    def test_slice_streams_only_its_range(self):
        import io
        part = topaz_api.Slice(io.BytesIO(b"0123456789"), 2, 6)
        self.assertEqual((len(part), part.read(3), part.read(), part.read()), (4, b"234", b"5", b""))


if __name__ == "__main__":
    unittest.main()
