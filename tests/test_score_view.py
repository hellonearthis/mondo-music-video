"""Musical score view: offsets, cut classification and refusal cases from saved run artifacts."""
import unittest

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
