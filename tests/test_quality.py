"""Motion/framing quality gates: clip measurement, prompt rules and production retry policy."""
import importlib.util
import os
import subprocess
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import test_public_app as public_fixtures
from mmv import quality
from mmv.storage import read_json
from test_public_app import MockService, picture


def clip(path, *filters, source="testsrc2=s=128x72:r=24:d=4"):
    graph = [x for x in filters if x]
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", source,
                    *(["-vf", ",".join(graph)] if graph else []), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    str(path)], check=True)
    return path


class ClipInspectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.temp.name)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_moving_full_frame_passes(self):
        result = quality.inspect_clip(clip(self.dir / "moving.mp4"), 96)
        self.assertEqual((result["status"], result["border"]), ("pass", None))

    def test_frozen_white_pillarbox_fails_both_checks(self):
        path = clip(self.dir / "frozen.mp4", "noise=alls=6:allf=0", "pad=128:72:16:0:white",
                    source="color=c=teal:s=96x72:r=24:d=4")
        result = quality.inspect_clip(path, 96)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["border"], "left/right")
        self.assertTrue(any("near-still" in p for p in result["problems"]))
        self.assertEqual(quality.inspect_clip(path, 96, check_borders=False)["border"], None)

    def test_one_frozen_shot_inside_a_moving_passage_fails(self):
        moving = clip(self.dir / "a.mp4", source="testsrc2=s=128x72:r=24:d=2")
        still = clip(self.dir / "b.mp4", "noise=alls=6:allf=0", source="color=c=gray:s=128x72:r=24:d=2")
        joined = self.dir / "joined.mp4"
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(moving), "-i", str(still),
                        "-filter_complex", "[0:v][1:v]concat=n=2:v=1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        str(joined)], check=True)
        whole = quality.inspect_clip(joined, 96)
        per_shot = quality.inspect_clip(joined, 96, shot_starts=[0, 48])
        self.assertEqual(whole["status"], "pass")
        self.assertEqual(per_shot["status"], "fail")
        self.assertIn("1 of 2 shots, about 2.0 s", per_shot["problems"][0])

    def test_dark_flat_edges_are_inconclusive_not_borders(self):
        path = clip(self.dir / "night.mp4", "pad=128:72:16:0:black", source="testsrc2=s=96x72:r=24:d=4")
        result = quality.inspect_clip(path, 96)
        self.assertEqual((result["status"], result["border"]), ("pass", None))
        self.assertIn("night scene", result["note"])

    def test_unreadable_clip_is_an_error_not_a_failure(self):
        missing = quality.inspect_clip(self.dir / "missing.mp4", 96)
        self.assertEqual((missing["status"], missing["problems"]), ("error", []))


class PromptRuleTests(unittest.TestCase):
    static = types.SimpleNamespace(shots=[{"n": 1, "camera": "The camera holds a static shot"}])
    moving = types.SimpleNamespace(shots=[{"n": 1, "camera": "The camera pushes in with small amplitude"}])

    def prompt(self, text, camera="The camera holds a static shot"):
        return f"summary:\nx\ndetailed_description:\n[Shot 1] {camera}. {text}\noverall_soundscape: rain"

    def test_rejects_declared_still_images_and_motionless_static_shots(self):
        frozen = self.prompt("The subject remains motionless. The overall composition is static.")
        self.assertEqual(len(quality.prompt_problems(frozen, self.static)), 2)
        self.assertTrue(quality.prompt_problems(self.prompt("A motionless composition of a chair."), self.static))
        self.assertTrue(quality.prompt_problems(self.prompt("She stands still in the room."), self.static))

    def test_accepts_motion_elsewhere_negations_and_moving_cameras(self):
        for text in ("She stands still while rain streams past her.", "Crisp detail, no motion blur.",
                     "Full frame without black bars; leaves drift."):
            self.assertEqual(quality.prompt_problems(self.prompt(text), self.static), [], text)
        pushin = self.prompt("She remains stationary.", "The camera pushes in with small amplitude")
        self.assertEqual(quality.prompt_problems(pushin, self.moving), [])

    def test_framing_devices_unless_the_director_asks(self):
        text = self.prompt("A projected film flickers on a screen; leaves drift.")
        self.assertTrue(quality.prompt_problems(text, self.static))
        self.assertEqual(quality.prompt_problems(text, self.static, "a projected film look"), [])
        forbidding = "No letterboxing or black bars; fill the frame"
        self.assertFalse(quality.framing_requested(forbidding))
        self.assertTrue(quality.prompt_problems(text, self.static, forbidding))


class ProductionRetryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        public_fixtures.PublicAppTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        public_fixtures.PublicAppTests.tearDownClass()

    def setUp(self):
        self.fixture = public_fixtures.PublicAppTests("test_version_matches_package_and_readme")
        self.fixture.setUp()
        self.frozen = public_fixtures.PublicAppTests.frozen_video

    def tearDown(self):
        MockService.queued_videos = []
        self.fixture.tearDown()

    def produce(self, **request):
        quote, started = self.fixture.start({"song": self.fixture.song_upload(), **request})
        started.raise_for_status()
        status = self.fixture.wait()
        self.assertEqual(status["state"], "complete", status)
        run = self.fixture.home / "runs" / status["id"]
        return run, read_json(run / "quality.json"), read_json(run / "output.json")

    def test_free_local_render_retries_once_with_new_seed(self):
        MockService.queued_videos = [self.frozen]
        run, report, output = self.produce()
        entry = report["seg000"]
        self.assertEqual((entry["status"], entry["used"]), ("retried_ok", "seg000-r1"))
        self.assertEqual([a["status"] for a in entry["attempts"]], ["fail", "pass"])
        self.assertEqual(entry["attempts"][1]["seed"] - entry["attempts"][0]["seed"], 7919)
        self.assertEqual(sum(path == "/prompt" for path, _ in MockService.requests), 2)
        self.assertNotIn("quality_warnings", output)

    def test_persistent_failure_is_assembled_with_a_visible_warning(self):
        MockService.queued_videos = [self.frozen, self.frozen]
        run, report, output = self.produce()
        self.assertEqual(report["seg000"]["status"], "fail")
        self.assertEqual(sum(path == "/prompt" for path, _ in MockService.requests), 2)
        self.assertIn("near-still", output["quality_warnings"][0])
        listed = self.fixture.client.get("/api/outputs").json()[0]
        self.assertIn("near-still", listed["quality_warnings"][0])

    def stage(self, clips, retry_clips, vision=None, backend_name="local_h3", cost=0.0, inspect=None, directory=None):
        """Run the batched stage on two fake passages; returns (chosen stems, report, render calls)."""
        from mmv import worker
        calls = []
        temp = None if directory else tempfile.TemporaryDirectory()
        directory = Path(directory or temp.name)
        try:
            paths = {}
            for name, data in {"good": self.good, "frozen": self.frozen}.items():
                paths[name] = directory / (name + ".mp4")
                paths[name].write_bytes(data)
            segs = [types.SimpleNamespace(segment_id=f"seg00{i}", index=i, trim_frames=96, duration_input=4.0,
                                          shots=[types.SimpleNamespace(start_frame=0)]) for i in range(2)]
            rendered = {seg.segment_id: {"video": str(paths[clips[i]])} for i, seg in enumerate(segs)}
            def render_passage(seg, segment_id, seed):
                calls.append((segment_id, seed))
                return {"video": str(paths[retry_clips[seg.index]])}
            backend = types.SimpleNamespace(cost_for=lambda seconds: cost)
            context = patch("mmv.quality.inspect_clip", inspect) if inspect else patch.dict(os.environ, {})
            with context:
                chosen = worker.run_quality_stage(directory, backend, {"backend": backend_name, "direction": "", "seed": 10},
                                                  types.SimpleNamespace(segments=segs), rendered, render_passage,
                                                  lambda *a: None, vision)
            report = read_json(directory / "quality.json")
            return {k: Path(v["video"]).stem for k, v in chosen.items()}, report, calls
        finally:
            if temp:
                temp.cleanup()

    @property
    def good(self):
        return public_fixtures.MockService.video

    class FakeVision:
        def __init__(self, verdicts):
            self.verdicts, self.events = verdicts, []

        def judge(self, items):
            self.events.append(("judge", [attempt["segment_id"] for _, attempt, _ in items]))
            return {attempt["segment_id"]: self.verdicts.get(attempt["segment_id"], {"status": "pass", "problems": [], "retry": False})
                    for _, attempt, _ in items}

        def prepare_render(self):
            self.events.append(("prepare_render",))

    def test_batch_retries_every_failure_after_all_checks(self):
        used, report, calls = self.stage(["frozen", "frozen"], ["good", "frozen"])
        self.assertEqual(calls, [("seg000-r1", 10 + 7919), ("seg001-r1", 11 + 7919)])
        self.assertEqual(used, {"seg000": "good", "seg001": "frozen"})
        self.assertEqual((report["seg000"]["status"], report["seg001"]["status"]), ("retried_ok", "fail"))
        self.assertEqual(report["seg001"]["used"], "seg001")
        self.assertIn("near-still", report["seg001"]["warning"])

    def test_vision_rejected_original_is_replaced_by_a_judged_retry(self):
        fail = {"status": "fail", "problems": ["projected film frame in 3 frames"], "retry": True}
        vision = self.FakeVision({"seg001": fail})
        used, report, calls = self.stage(["frozen", "good"], ["good", "good"], vision=vision)
        # Pixel retry first (seg000), then one swap back for the vision retry (seg001), then its judgment.
        self.assertEqual([c[0] for c in calls], ["seg000-r1", "seg001-r1"])
        self.assertEqual(vision.events, [("judge", ["seg000-r1", "seg001"]), ("prepare_render",), ("judge", ["seg001-r1"])])
        self.assertEqual(used, {"seg000": "good", "seg001": "good"})
        self.assertEqual((report["seg001"]["used"], report["seg001"]["status"]), ("seg001-r1", "retried_ok"))
        self.assertNotIn("warning", report["seg001"])

    def test_vision_retry_that_is_also_rejected_keeps_the_original(self):
        fail = {"status": "fail", "problems": ["projected film frame"], "retry": True}
        vision = self.FakeVision({"seg001": fail, "seg001-r1": dict(fail, problems=["projected film frame", "text"])})
        used, report, calls = self.stage(["good", "good"], ["good", "good"], vision=vision)
        self.assertEqual(report["seg001"]["used"], "seg001")
        self.assertEqual(report["seg001"]["status"], "vision_fail")
        self.assertIn("vision: projected film frame", report["seg001"]["warning"])

    def test_vision_warnings_never_retry_and_paid_renderers_skip_vision_retries(self):
        warn = {"status": "warn", "problems": ["possible distortion"], "retry": False}
        vision = self.FakeVision({"seg000": warn})
        used, report, calls = self.stage(["good", "good"], ["good", "good"], vision=vision)
        self.assertEqual(calls, [])
        self.assertEqual(report["seg000"]["status"], "ok")
        self.assertIn("vision: possible distortion", report["seg000"]["warning"])
        fail = {"status": "fail", "problems": ["border"], "retry": True}
        used, report, calls = self.stage(["good", "good"], ["good", "good"], vision=self.FakeVision({"seg000": fail}),
                                         backend_name="wavespeed", cost=0.4)
        self.assertEqual(calls, [])

    def test_resume_recovers_spent_retries_and_reuses_saved_verdicts(self):
        with tempfile.TemporaryDirectory() as temp:
            fail = {"status": "fail", "problems": ["projected film frame"], "retry": True}
            first = self.FakeVision({"seg001": fail})
            self.stage(["frozen", "good"], ["good", "good"], vision=first, directory=temp)
            real, count = quality.inspect_clip, []
            def flaky(video, *args, **kwargs):
                count.append(video)
                return {"status": "error", "problems": [], "error": "decoder busy"}
            again = self.FakeVision({"seg001": fail})
            used, report, calls = self.stage(["frozen", "good"], ["good", "good"], vision=again, inspect=flaky, directory=temp)
        # Unchanged clips reuse saved measurements and verdicts: no new inspection or vision call.
        self.assertEqual(count, [])
        self.assertEqual([c[0] for c in calls], ["seg000-r1", "seg001-r1"])
        self.assertEqual(again.events, [])
        self.assertEqual(used, {"seg000": "good", "seg001": "good"})

    def test_paid_or_unlisted_renderers_never_retry(self):
        for name, cost in (("wavespeed", 0.4), ("seedance_2", 0.0), ("local_h3", 0.7)):
            used, report, calls = self.stage(["frozen", "good"], ["good", "good"], backend_name=name, cost=cost)
            self.assertEqual(calls, [], name)
            self.assertIn("not re-rendered automatically", report["seg000"]["warning"])

    def test_unmeasurable_retry_never_replaces_a_measured_attempt(self):
        real, count = quality.inspect_clip, []
        def flaky(video, *args, **kwargs):
            count.append(video)
            return real(video, *args, **kwargs) if len(count) <= 2 else {
                "status": "error", "problems": [], "error": "could not inspect clip: decoder timeout"}
        used, report, calls = self.stage(["frozen", "good"], ["good", "good"], inspect=flaky)
        self.assertEqual(used["seg000"], "frozen")
        self.assertEqual((report["seg000"]["used"], report["seg000"]["status"]), ("seg000", "fail"))
        self.assertIn("decoder timeout", report["seg000"]["warning"])

    def test_clean_render_is_not_resubmitted(self):
        run, report, output = self.produce()
        self.assertEqual(report["seg000"]["status"], "ok")
        self.assertEqual(sum(path == "/prompt" for path, _ in MockService.requests), 1)

    def test_paid_renderer_is_never_resubmitted(self):
        self.fixture.store.save_key("WAVESPEED_API_KEY", "mock-only-key")
        image = self.fixture.client.post("/api/upload/reference", files={"file": ("ref.png", picture())}).json()["file"]
        original, MockService.video = MockService.video, self.frozen
        try:
            with patch.dict(os.environ, {"WAVESPEED_BASE_URL": self.fixture.url}):
                run, report, output = self.produce(backend="wavespeed", resolution="768p", references=[image])
        finally:
            MockService.video = original
        submissions = [p for p, _ in MockService.requests if p.endswith("/reference-to-video")]
        self.assertEqual(len(submissions), 1)
        self.assertEqual(len(report["seg000"]["attempts"]), 1)
        self.assertIn("not re-rendered automatically", output["quality_warnings"][0])

    @unittest.skipUnless(importlib.util.find_spec("comfy_sdk"), "optional official SDK not installed")
    def test_sdk_retry_has_its_own_receipt_and_job(self):
        self.fixture.configure_sdk()
        MockService.queued_videos = [self.frozen]
        run, report, output = self.produce(backend="comfy_sdk_h3")
        self.assertEqual(report["seg000"]["status"], "retried_ok")
        self.assertEqual(len(self.fixture.server.v2_submits), 2)
        receipts = {p.parent.name: read_json(p) for p in (run / "renders").glob("*/comfy-request.json")}
        self.assertEqual(set(receipts), {"seg000", "seg000-r1"})
        self.assertNotEqual(receipts["seg000"]["job_id"], receipts["seg000-r1"]["job_id"])

    def test_ident_is_not_gated(self):
        MockService.queued_videos = [self.frozen]
        quote, started = self.fixture.start({"kind": "ident", "title": "Goose", "ident_seconds": 5})
        started.raise_for_status()
        status = self.fixture.wait()
        self.assertEqual(status["state"], "complete", status)
        self.assertFalse((self.fixture.home / "runs" / status["id"] / "quality.json").exists())


if __name__ == "__main__":
    unittest.main()
