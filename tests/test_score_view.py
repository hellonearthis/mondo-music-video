"""Musical score view: offsets, cut classification and refusal cases from saved run artifacts."""
import json
import unittest
from pathlib import Path

import test_public_app as public_fixtures
from mmv.storage import write_json


class ScoreViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        public_fixtures.PublicAppTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        public_fixtures.PublicAppTests.tearDownClass()

    def setUp(self):
        self.fixture = public_fixtures.PublicAppTests("test_version_matches_package_and_readme")
        self.fixture.setUp()
        self.client, self.home = self.fixture.client, self.fixture.home

    def tearDown(self):
        self.fixture.tearDown()

    def run_dir(self, run_id, kind="video", duration=4.0, request=None, analysis=True):
        directory = self.home / "runs" / run_id
        write_json(directory / "output.json", {"file": "music-video.mp4", "duration": duration, "kind": kind,
                                              "title": "Fixture"})
        write_json(directory / "request.json", request or {})
        if analysis:
            write_json(directory / "score.json", {
                "tempo_bpm": 120.0, "beats_per_bar": 4, "beat_frames": [0, 12, 24, 36, 48, 60, 72, 84],
                "downbeat_frames": [0, 48], "beat_energy": [.1, .2, .3, .4, .9, .9, .8, .7],
                "sections": [{"start_frame": 0, "end_frame": 48, "label": "low", "energy": .2},
                             {"start_frame": 48, "end_frame": 96, "label": "peak", "energy": .85}]})
            write_json(directory / "plan.json", {"fps": 24, "total_frames": 96, "segments": [
                {"index": 0, "song_start_frame": 0, "trim_frames": 48, "montage_type": "standard",
                 "section_label": "low", "energy": .2,
                 "shots": [{"start_frame": 0, "frames": 48, "camera": "slow push", "shot_scale": "wide shot"}]},
                {"index": 1, "song_start_frame": 48, "trim_frames": 48,
                 "montage_type": "type1_single_subject_fragmentation", "section_label": "peak", "energy": .85,
                 "shots": [{"start_frame": 0, "frames": 12, "shot_scale": "close-up"},
                           {"start_frame": 12, "frames": 18, "shot_scale": "extreme close-up"},
                           {"start_frame": 30, "frames": 18, "shot_scale": "medium shot"}]}]})
        return directory

    def test_score_in_video_seconds_with_cut_classification(self):
        self.run_dir("song")
        score = self.client.get("/api/outputs/song/score").json()
        self.assertEqual((score["offset"], score["song_end"], score["tempo_bpm"]), (0.0, 4.0, 120.0))
        self.assertEqual([b["time"] for b in score["beats"] if b["downbeat"]], [0.0, 2.0])
        low, peak = score["passages"]
        self.assertEqual((low["grammar"], low["start"], low["end"], low["beats"]), ("Standard", 0.0, 2.0, 4))
        self.assertEqual(peak["grammar"], "Single-subject fragmentation")
        self.assertTrue(peak["on_downbeat"])
        self.assertEqual([(s["start"], s["cut"]) for s in peak["shots"]],
                         [(2.0, "passage"), (2.5, "beat"), (3.25, "split")])
        self.assertNotIn("song", str(score.get("source")))
        self.assertNotIn(str(self.home), str(score))

    def test_opening_ident_shifts_song_clock(self):
        self.run_dir("ident_run", kind="ident", duration=1.5, analysis=False)
        self.run_dir("with_ident", duration=5.5, request={"start_ident": "ident_run/music-video.mp4"})
        score = self.client.get("/api/outputs/with_ident/score").json()
        self.assertEqual((score["offset"], score["song_end"]), (1.5, 5.5))
        self.assertEqual(score["passages"][1]["start"], 3.5)

    def test_saved_source_timing_survives_deleted_ident_metadata(self):
        directory = self.run_dir('source-timing', request={'start_ident': 'gone/ident.mp4'})
        write_json(directory / 'assembly-source.json', {'song_start_frame': 36, 'fps': 24})
        score = self.client.get('/api/outputs/source-timing/score').json()
        self.assertEqual((score['offset'], score['song_end']), (1.5, 5.5))

    def test_refuses_idents_missing_analysis_and_unsafe_ids(self):
        self.run_dir("ident_only", kind="ident", analysis=False)
        self.run_dir("no_analysis", analysis=False)
        for run_id, message in (("ident_only", "only for completed music videos"),
                                ("no_analysis", "no saved musical analysis"),
                                ("missing", "only for completed music videos")):
            response = self.client.get(f"/api/outputs/{run_id}/score")
            self.assertEqual(response.status_code, 400, run_id)
            self.assertIn(message, response.json()["detail"])
        self.assertIn(self.client.get("/api/outputs/..%2Fsecrets/score").status_code, (400, 404))


if __name__ == "__main__":
    unittest.main()


class PassageBreakdownTests(ScoreViewTests):
    def test_prompts_trimmed_length_and_recorded_clips_only(self):
        directory = self.run_dir("prompts1")
        write_json(directory / "prompts.json", {"seg000": "A wide coast at dawn.", "seg001": "Close on the hands."})
        clip = directory / "clips" / "seg000.mov"
        clip.parent.mkdir()
        clip.write_bytes(b"fixture")
        write_json(directory / "renders.json", {"seg000": {"video": str(clip)},
                                                "seg001": {"video": str(directory / "missing.mp4")}})
        data = self.client.get("/api/outputs/prompts1/prompts").json()
        first, second = data["segments"]
        self.assertEqual((first["prompt"], first["duration"], first["trim_frames"]), ("A wide coast at dawn.", 2.0, 48))
        self.assertEqual(first["shots"][0]["shot_scale"], "wide shot")
        self.assertEqual(first["clip_url"], "/api/outputs/prompts1/clips/seg000")
        self.assertFalse(second["has_clip"])
        self.assertIsNone(second["clip_url"])
        served = self.client.get(first["clip_url"])
        self.assertEqual((served.status_code, served.content), (200, b"fixture"))
        self.assertTrue(served.headers["content-type"].startswith("video/quicktime"))
        self.assertGreaterEqual(self.client.get("/api/outputs/prompts1/clips/seg001").status_code, 400)
        self.assertGreaterEqual(self.client.get("/api/outputs/prompts1/clips/..%2Frenders").status_code, 400)

    def test_only_video_files_recorded_for_the_passage_are_served(self):
        directory = self.run_dir("prompts2")
        write_json(directory / "renders.json", {"seg000": {"video": str(directory / "output.json")}})
        self.assertFalse(self.client.get("/api/outputs/prompts2/prompts").json()["segments"][0]["has_clip"])
        self.assertGreaterEqual(self.client.get("/api/outputs/prompts2/clips/seg000").status_code, 400)
        self.assertGreaterEqual(self.client.get("/api/outputs/no-such-run/prompts").status_code, 400)

    def test_clips_outside_data_and_comfy_output_are_refused(self):
        import tempfile
        directory = self.run_dir("prompts3")
        with tempfile.TemporaryDirectory() as outside:
            clip = Path(outside) / "seg000.mp4"
            clip.write_bytes(b"elsewhere")
            write_json(directory / "renders.json", {"seg000": {"video": str(clip)}})
            self.assertFalse(self.client.get("/api/outputs/prompts3/prompts").json()["segments"][0]["has_clip"])
            self.assertGreaterEqual(self.client.get("/api/outputs/prompts3/clips/seg000").status_code, 400)
            settings_file = self.home / "settings.json"
            saved = settings_file.read_text() if settings_file.exists() else None
            try:
                write_json(settings_file, {**(json.loads(saved) if saved else {}), "comfy_output": outside})
                self.assertEqual(self.client.get("/api/outputs/prompts3/clips/seg000").content, b"elsewhere")
            finally:
                settings_file.write_text(saved) if saved is not None else settings_file.unlink()

    def test_captioned_output_shows_its_source_passages(self):
        source = self.run_dir("prompts4")
        write_json(source / "prompts.json", {"seg000": "Original prompt.", "seg001": "Second."})
        captioned = self.home / "runs" / "captioned4"
        write_json(captioned / "output.json", {"file": "captioned.mp4", "kind": "captioned", "title": "With captions",
                                               "source": "prompts4/music-video.mp4"})
        data = self.client.get("/api/outputs/captioned4/prompts").json()
        self.assertEqual((data["run_id"], data["source_run_id"], data["title"]), ("captioned4", "prompts4", "With captions"))
        self.assertEqual(data["segments"][0]["prompt"], "Original prompt.")

    def test_vision_guide_and_single_style(self):
        guide = self.client.get("/api/vision/guide").json()
        self.assertIn("Style Harvest Vision", guide["markdown"])
        self.assertIn("09. Settings", guide["markdown"])
        write_json(self.home / "styles" / "coastal.json", {"id": "coastal", "name": "Coastal", "direction": "Salt light."})
        self.assertEqual(self.client.get("/api/styles/coastal").json()["name"], "Coastal")
        self.assertGreaterEqual(self.client.get("/api/styles/missing").status_code, 400)

    def test_passage_takes_initialization_and_selection(self):
        directory = self.run_dir("takes_run")
        write_json(directory / "prompts.json", {"seg000": "Coastline.", "seg001": "Hands."})
        clips_dir = directory / "clips"
        clips_dir.mkdir()
        clip1 = clips_dir / "seg000_take1.mp4"
        clip2 = clips_dir / "seg000_take2.mp4"
        clip1.write_bytes(b"take-one-bytes")
        clip2.write_bytes(b"take-two-bytes")
        write_json(directory / "renders.json", {"seg000": {"video": str(clip1)}})
        data = self.client.get("/api/outputs/takes_run/prompts").json()
        seg0 = data["segments"][0]
        self.assertEqual(seg0["active_take"], "take1")
        self.assertEqual(len(seg0["takes"]), 1)
        self.assertEqual(seg0["takes"][0]["id"], "take1")

        # Add a second take and select it
        takes_path = directory / "takes.json"
        takes_record = json.loads(takes_path.read_text(encoding="utf-8"))
        takes_record["segments"]["seg000"]["takes"].append({
            "id": "take2",
            "label": "Take 2 (seed 999)",
            "seed": 999,
            "video": str(clip2),
            "audio": "",
        })
        write_json(takes_path, takes_record)

        res = self.client.post("/api/outputs/takes_run/takes/seg000", json={"take_id": "take2"})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["active_take"], "take2")

        # Verify specific take clip endpoint and updated default clip
        self.assertEqual(self.client.get("/api/outputs/takes_run/clips/seg000?take=take1").content, b"take-one-bytes")
        self.assertEqual(self.client.get("/api/outputs/takes_run/clips/seg000?take=take2").content, b"take-two-bytes")
        self.assertEqual(self.client.get("/api/outputs/takes_run/clips/seg000").content, b"take-two-bytes")
