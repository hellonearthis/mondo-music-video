"""Unfinished-run manager and finished-video deletion, with rendered-clip safeguards."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from webapp.mondo_web import create_app


def make_run(home, name, *, finished=False, clips=0):
    run = Path(home) / "runs" / name
    (run / "renders").mkdir(parents=True)
    (run / "request.json").write_text(json.dumps({"title": name, "kind": "video", "backend": "local_h3"}))
    for index in range(clips):
        (run / "renders" / f"seg{index:03d}.mp4").write_bytes(b"clip")
    if finished:
        (run / "output.json").write_text("{}")
    return run


class UnfinishedRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.client = TestClient(create_app(self.home, test_hosts=True))

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def test_listing_excludes_finished_and_counts_clips(self):
        make_run(self.home, "draft")
        make_run(self.home, "partial", clips=2)
        make_run(self.home, "done", finished=True)
        listed = {row["id"]: row for row in self.client.get("/api/runs/unfinished").json()}
        self.assertEqual(set(listed), {"draft", "partial"})
        self.assertEqual(listed["partial"]["rendered_clips"], 2)

    def test_run_size_cache_expires_when_nested_file_changes(self):
        run = make_run(self.home, "draft")
        with patch("webapp.mondo_web.time.monotonic", return_value=100):
            first = self.client.get("/api/runs/unfinished").json()[0]["size_mb"]
            (run / "renders" / "new.bin").write_bytes(b"x" * 1048576)
            cached = self.client.get("/api/runs/unfinished").json()[0]["size_mb"]
        with patch("webapp.mondo_web.time.monotonic", return_value=106):
            refreshed = self.client.get("/api/runs/unfinished").json()[0]["size_mb"]
        self.assertEqual(cached, first)
        self.assertGreater(refreshed, first)

    def test_single_purge_needs_confirmation_when_clips_exist(self):
        run = make_run(self.home, "partial", clips=1)
        refused = self.client.delete("/api/runs/unfinished/partial")
        self.assertGreaterEqual(refused.status_code, 400)
        self.assertTrue(run.is_dir())
        self.assertEqual(self.client.delete("/api/runs/unfinished/partial?confirm_rendered=true").status_code, 200)
        self.assertFalse(run.exists())

    def test_purge_all_keeps_runs_with_clips_and_finished_videos(self):
        draft, partial, done = make_run(self.home, "draft"), make_run(self.home, "partial", clips=3), make_run(self.home, "done", finished=True)
        result = self.client.post("/api/runs/unfinished/purge").json()
        self.assertEqual(result, {"purged_count": 1, "kept_with_clips": 1})
        self.assertFalse(draft.exists())
        self.assertTrue(partial.is_dir() and done.is_dir())

    def test_finished_purge_endpoint_refuses_completed_video(self):
        done = make_run(self.home, "done", finished=True)
        self.assertGreaterEqual(self.client.delete("/api/runs/unfinished/done").status_code, 400)
        self.assertTrue(done.is_dir())

    def test_output_deletion_removes_only_finished_runs(self):
        done, draft = make_run(self.home, "done", finished=True), make_run(self.home, "draft")
        self.assertEqual(self.client.delete("/api/outputs/done").status_code, 200)
        self.assertGreaterEqual(self.client.delete("/api/outputs/draft").status_code, 400)
        self.assertFalse(done.exists())
        self.assertTrue(draft.is_dir())


if __name__ == "__main__":
    unittest.main()
