"""Public boundary and complete mocked-renderer productions with real media assembly."""
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import threading
import time
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import oap
from fastapi.testclient import TestClient
from PIL import Image

from mmv import actors, media, render
from mmv.jobs import Jobs, BusyError
from mmv.setup import SessionLock, doctor, download_models
from mmv.storage import Storage, inside, read_json, write_json
from webapp.mondo_web import api_version, create_app, MGL_APP_VERSION


def picture():
    data = io.BytesIO()
    Image.new("RGB", (64, 80), "teal").save(data, "PNG")
    return data.getvalue()


from mock_comfy_v2 import ComfyV2Mixin, reset_v2


class MockService(ComfyV2Mixin, BaseHTTPRequestHandler):
    requests = []
    video = b""
    hold = False
    invalid_writer = False

    def log_message(self, *args):
        pass

    def reply(self, value):
        data = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.v2_post(data):
            return
        if self.path == "/media/upload/binary":
            self.reply({"data": {"download_url": "https://example.invalid/reference"}})
            return
        body = json.loads(data)
        type(self).requests.append((self.path, body))
        if self.path == "/prompt":
            graph = body["prompt"]
            prefix = graph["148"]["inputs"]["filename_prefix"]
            target = self.server.output / (prefix + "_00001.mp4")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self.video)
            self.server.last_filename = target.name
            self.reply({"prompt_id": "local-test", "node_errors": {}})
        elif self.path == "/chat/completions":
            system = body["messages"][0].get("content", "") if len(body["messages"]) > 1 else ""
            user = body["messages"][-1]["content"]
            if isinstance(user, list):
                content = json.dumps({"style_card":"Soft teal light", "aesthetic_directives":"Soft teal light and textured paper, with patient camera movement."})
            elif user.startswith("TEXT:"):
                title = user.splitlines()[0][6:]
                content = 'The words "' + title + '" emerge in brushed metal with continuous motion, then hold motionless and legible. Silent scene, no musical score.'
            else:
                job = json.loads(user)
                text = "The fully clothed performer moves through warm light as wind lifts the fabric of a blue jacket. Reflections trace shifting patterns across nearby glass while the camera follows with deliberate rhythmic motion and the scene remains grounded in a coherent physical space. The subject stays recognizable and each movement carries the energy of the music through precise visible changes in posture and light. "
                content = json.dumps({"segment_id":job["segment_id"], "style_opening":"Cinematic daylight photography with expressive movement.",
                    "subject_definitions":[], "summary":"A fully clothed performer in sunlight.", "retention_analysis":[],
                    "shot_bodies":[text * 3 + " Subject Rigging: lips firmly sealed shut, jaw completely relaxed, to prevent any facial babbling or lip-sync hallucinations." for shot in job["shots"]], "overall_soundscape":"Wind and quiet footsteps.", "non_diegetic_music":"N/A"})
            if self.invalid_writer: content = "{}"
            self.reply({"choices":[{"message":{"content":content}}]})
        elif self.path == "/queue":
            self.reply({})
        else:
            self.reply({"data": {"id": "hosted-test"}})

    def do_GET(self):
        if self.v2_get():
            return
        if self.path.startswith("/view") or self.path == "/video.mp4":
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(self.video)))
            self.end_headers()
            self.wfile.write(self.video)
        elif self.path.startswith("/object_info/"):
            self.reply(self.server.object_info.get(self.path.rsplit('/', 1)[-1], {}))
        elif self.path.startswith("/history/"):
            self.reply({} if self.hold else {"local-test": {"status": {"status_str": "success"},
                        "outputs": {"2": {"videos": [{"filename": self.server.last_filename, "subfolder": "", "type": "output"}]}}}})
        elif self.path.startswith("/predictions/"):
            self.reply({"data": {"status": "completed", "outputs": [f"http://127.0.0.1:{self.server.server_port}/video.mp4"]}})
        else:
            self.reply({})


class PublicAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media_temp = tempfile.TemporaryDirectory()
        directory = Path(cls.media_temp.name)
        video, song = directory / "test.mp4", directory / "test.wav"
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i",
                        "color=c=teal:s=128x72:r=24:d=6", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)], check=True)
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i",
                        "sine=frequency=440:duration=1.1", str(song)], check=True)
        cls.song = song.read_bytes()
        MockService.video = video.read_bytes()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), MockService)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.media_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.app = create_app(self.home, test_hosts=True)
        self.client = TestClient(self.app)
        self.store = self.app.state.store
        (self.home / "comfy-input").mkdir()
        (self.home / "comfy-output").mkdir()
        self.server.output = self.home / "comfy-output"
        settings = self.store.settings()
        settings.update(comfy_url=self.url, comfy_input=str(self.home / "comfy-input"), comfy_output=str(self.home / "comfy-output"),
                        laya_model_dir=os.environ.get("MMV_TEST_LAYA_MODEL_DIR", str(self.home / "models/laya")), laya_device="cuda",
                        writer_url=self.url, writer_model="fixture-writer", vision_url=self.url, vision_model="fixture-vision")
        if not os.environ.get("MMV_TEST_LAYA_MODEL_DIR"):
            model = self.home / "models/laya"
            (model / "tokenizer").mkdir(parents=True)
            (model / "encoder").mkdir()
            for name in ("model.safetensors", "rl_agent_config.json", "encoder/config.json"):
                (model / name).write_text("fixture")
            from mmv.jobs import JobContext
            original_command = JobContext.command
            def test_command(context, argv, **kwargs):
                if "mmv.worker" in argv and "produce" in argv:
                    argv = ["mock_laya_worker" if x == "mmv.worker" else x for x in argv]
                    env = os.environ.copy()
                    env["PYTHONPATH"] = str(Path(__file__).parent) + os.pathsep + env.get("PYTHONPATH", "")
                    kwargs["env"] = env
                return original_command(context, argv, **kwargs)
            self.worker_patch = patch("mmv.jobs.JobContext.command",test_command)
            self.worker_patch.start()
        self.client.put("/api/settings", json=settings).raise_for_status()
        reset_v2(self.server)
        self.server.object_info = {}
        MockService.requests = []
        MockService.hold = False
        MockService.invalid_writer = False

    def tearDown(self):
        if hasattr(self,"worker_patch"): self.worker_patch.stop()
        if self.app.state.jobs.active:
            self.app.state.jobs.cancel()
            self.wait()
        self.client.close()
        self.temp.cleanup()

    def song_upload(self):
        response = self.client.post("/api/upload/song", files={"file": ("test.wav", self.song, "audio/wav")})
        response.raise_for_status()
        return response.json()["file"]

    def wait(self, timeout=90):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.client.get("/api/status").json()
            if status["state"] not in ("running", "cancelling") and self.app.state.jobs.active is None:
                if status["state"] == "failed":
                    print((self.home / "runs" / status["id"] / "operation.log").read_text())
                return status
            time.sleep(.05)
        self.fail("Operation did not finish")

    def start(self, request, consent=True):
        quote = self.client.post("/api/quote", json=request)
        quote.raise_for_status()
        start = self.client.post("/api/start", json={"quote_id": quote.json()["id"], "consent": consent})
        return quote, start

    def configure_sdk(self):
        settings = self.store.settings()
        settings.update(comfy_sdk_url=self.url, comfy_input='', comfy_output='')
        self.client.put('/api/settings', json=settings).raise_for_status()
        self.store.save_key('MMV_COMFY_API_KEY', 'fake-proxy-token')

    @unittest.skipUnless(importlib.util.find_spec('comfy_sdk'), 'optional official SDK not installed')
    def test_sdk_production_transfers_media_and_assembles(self):
        self.configure_sdk()
        actors.create_actor(self.store, 'blue', 'Blue', 'Blue jacket', picture())
        quote, started = self.start({'backend': 'comfy_sdk_h3', 'song': self.song_upload(), 'actors': ['blue']})
        started.raise_for_status()
        status = self.wait()
        self.assertEqual(status['state'], 'complete')
        self.assertEqual(quote.json()['estimate_usd'], 0)
        self.assertEqual(len(self.server.v2_submits), 1)
        headers, body = self.server.v2_submits[0]
        self.assertEqual(headers['Authorization'], 'Bearer fake-proxy-token')
        self.assertTrue(headers['Idempotency-Key'])
        graph = body['workflow']
        self.assertEqual(graph['124']['inputs']['steps'], 20)
        ref_node = graph['136']['inputs']
        image_loader = graph[ref_node['ref_images.ref_image_0'][0]]
        audio_loader = graph[ref_node['ref_audios.ref_audio_0'][0]]
        for loader, widget in [(image_loader, 'image'), (audio_loader, 'audio')]:
            asset_ref = loader['inputs'][widget]
            self.assertEqual(asset_ref['__type'], 'core/ASSET')
            self.assertIn(asset_ref['info']['id'], self.server.v2_assets)
        self.assertEqual(len(self.server.v2_assets), 2)
        run = self.home / 'runs' / status['id']
        self.assertTrue((run / 'music-video.mp4').is_file())
        self.assertAlmostEqual(media.duration(run / 'music-video.mp4'), 1.1, delta=.08)
        self.assertFalse((run / 'untrusted.mp4').exists())
        receipt = read_json(next((run / 'renders').glob('*/comfy-request.json')))
        self.assertEqual(receipt['job_id'], self.server.v2_ids[0])
        self.assertNotIn('fake-proxy-token', json.dumps(receipt))
        self.assertNotIn('fake-proxy-token', self.client.get('/api/settings').text)

    @unittest.skipUnless(importlib.util.find_spec('comfy_sdk'), 'optional official SDK not installed')
    def test_sdk_download_failure_resumes_without_generation_or_writer(self):
        self.configure_sdk()
        self.server.v2_download_fail = True
        _, started = self.start({'backend': 'comfy_sdk_h3', 'song': self.song_upload()})
        started.raise_for_status()
        status = self.wait()
        self.assertEqual(status['state'], 'failed')
        before = len(MockService.requests)
        self.server.v2_download_fail = False
        original = self.store.settings()
        changed = {**original, 'writer_model': 'changed-model'}
        self.client.put('/api/settings', json=changed).raise_for_status()
        stale = self.client.post('/api/resume/quote', json={'run_id': status['id']})
        self.assertEqual(stale.status_code, 400)
        self.client.put('/api/settings', json=original).raise_for_status()
        quote = self.client.post('/api/resume/quote', json={'run_id': status['id']})
        quote.raise_for_status()
        self.assertEqual(self.client.post('/api/start', json={'quote_id': quote.json()['id'], 'consent': False}).status_code, 400)
        resumed = self.client.post('/api/start', json={'quote_id': quote.json()['id'], 'consent': True})
        resumed.raise_for_status()
        self.assertEqual(resumed.json()['id'], status['id'])
        self.assertEqual(self.wait()['state'], 'complete')
        self.assertEqual(len(self.server.v2_submits), 1)
        self.assertEqual(len(MockService.requests), before)

    @unittest.skipUnless(importlib.util.find_spec('comfy_sdk'), 'optional official SDK not installed')
    def test_sdk_ambiguous_submission_is_never_retried(self):
        self.configure_sdk()
        self.server.v2_drop = True
        _, started = self.start({'backend': 'comfy_sdk_h3', 'song': self.song_upload()})
        started.raise_for_status()
        status = self.wait()
        self.assertEqual(status['state'], 'failed')
        self.assertEqual(len(self.server.v2_submits), 1)
        receipt = read_json(next((self.home / 'runs' / status['id'] / 'renders').glob('*/comfy-request.json')))
        self.assertEqual(receipt['state'], 'unknown')
        quote = self.client.post('/api/resume/quote', json={'run_id': status['id']})
        self.assertEqual(quote.status_code, 400)
        self.assertIn('unknown', quote.json()['detail'])
        self.assertEqual(len(self.server.v2_submits), 1)

    @unittest.skipUnless(importlib.util.find_spec('comfy_sdk'), 'optional official SDK not installed')
    def test_sdk_queue_full_does_not_trigger_hidden_sdk_retry(self):
        self.configure_sdk()
        self.server.v2_reject = True
        _, started = self.start({'backend': 'comfy_sdk_h3', 'song': self.song_upload()})
        started.raise_for_status()
        self.assertEqual(self.wait()['state'], 'failed')
        self.assertEqual(len(self.server.v2_submits), 1)

    @unittest.skipUnless(importlib.util.find_spec('comfy_sdk'), 'optional official SDK not installed')
    def test_sdk_cancels_only_recorded_job(self):
        self.configure_sdk()
        self.server.v2_hold = True
        _, started = self.start({'backend': 'comfy_sdk_h3', 'song': self.song_upload()})
        started.raise_for_status()
        deadline = time.monotonic() + 30
        receipt = self.home / 'runs' / started.json()['id'] / 'renders/seg000/comfy-request.json'
        while time.monotonic() < deadline:
            if read_json(receipt, {}).get('job_id'):
                break
            time.sleep(.05)
        self.assertTrue(read_json(receipt, {}).get('job_id'))
        self.client.post('/api/cancel').raise_for_status()
        self.assertEqual(self.wait()['state'], 'cancelled')
        self.assertEqual(self.server.v2_cancels, self.server.v2_ids)
        self.assertEqual(len(self.server.v2_submits), 1)

    @unittest.skipUnless(importlib.util.find_spec('comfy_sdk'), 'optional official SDK not installed')
    def test_sdk_oap_rejection_happens_before_upload_or_submit(self):
        self.configure_sdk()
        actors.create_actor(self.store, 'blue', 'Blue', '', picture())
        content = {key: 'none' for key in oap.CONTENT_ENUMS}
        content['nudity'] = 'explicit'
        response = self.client.post('/api/quote', json={'backend': 'comfy_sdk_h3',
            'song': self.song_upload(), 'actors': ['blue'], 'content': content})
        self.assertEqual(response.status_code, 400)
        self.assertIn('exceeds rider', response.json()['detail'])
        self.assertEqual(self.server.v2_assets, {})
        self.assertEqual(self.server.v2_submits, [])

    @unittest.skipUnless(importlib.util.find_spec('comfy_sdk'), 'optional official SDK not installed')
    def test_sdk_known_job_timeout_recovers_without_resubmission(self):
        from mmv.engine.backends.base import BackendError
        self.configure_sdk()
        self.server.v2_hold = True
        song = self.home / 'song.wav'
        song.write_bytes(self.song)
        backend = render.get_backend('comfy_sdk_h3')
        from mmv.pipeline import ENGINE
        backend.open_render(out_dir=self.home / 'recovery', comfy_sdk_url=self.url,
                            map_path=ENGINE / 'config/injection_map.json', root=ENGINE, timeout_s=.01)
        job = dict(segment_id='seg000', index=0, slug='timeout-test', prompt='A sunlit coast.',
                   gen_frames=39, duration_input=1.625, width=128, height=72, seed=0,
                   images=[], song=str(song), audio_start_s=0, audio_end_s=1.1)
        try:
            with self.assertRaisesRegex(BackendError, 'timed out'):
                backend.render_segment(**job)
            self.server.v2_hold = False
            result = backend.render_segment(**job)
            self.assertTrue(Path(result['video']).is_file())
            self.assertEqual(len(self.server.v2_submits), 1)
            # Even a changed seed cannot repurpose a saved receipt for a new submission.
            with self.assertRaisesRegex(BackendError, 'different inputs'):
                backend.render_segment(**{**job, 'seed': 1})
            self.assertEqual(len(self.server.v2_submits), 1)
        finally:
            backend.close_render()

    @unittest.skipUnless(importlib.util.find_spec('comfy_sdk'), 'optional official SDK not installed')
    def test_sdk_rejects_followup_links_to_another_origin(self):
        from mmv.comfy_sdk import SdkSession
        session = SdkSession(self.url, 'fake-proxy-token')
        try:
            with self.assertRaisesRegex(ValueError, 'outside the configured local endpoint'):
                session.low.raw_request('GET', 'https://example.invalid/api/v2/jobs/fake')
        finally:
            session.close()

    def test_sdk_settings_refuse_nonlocal_or_credential_urls(self):
        for url in ['https://cloud.comfy.org', 'http://127.0.0.1:8189?token=secret',
                    'http://secret@localhost:8189', 'http://localhost:8189/path']:
            settings = self.store.settings()
            settings['comfy_sdk_url'] = url
            self.assertEqual(self.client.put('/api/settings', json=settings).status_code, 422)

    def test_version_matches_package_and_readme(self):
        import tomllib
        root = Path(__file__).resolve().parents[1]
        project = tomllib.loads((root / "pyproject.toml").read_text())
        self.assertEqual(api_version()["version"], "1.0.16")
        self.assertEqual(project["project"]["version"], MGL_APP_VERSION)
        self.assertIn("1.0.16", (root / "README.md").read_text())
        self.assertEqual(self.client.get("/api/version").json(), api_version())

    def test_uploaded_song_preview_endpoint(self):
        up = self.client.post("/api/upload/song", files={"file": ("track.wav", self.song, "audio/wav")})
        self.assertEqual(up.status_code, 200)
        uploaded_name = up.json()["file"]
        res = self.client.get(f"/api/uploads/song/{uploaded_name}")
        self.assertEqual(res.status_code, 200)
        self.assertIn("audio/wav", res.headers["content-type"])
        self.assertEqual(res.content, self.song)
        missing = self.client.get("/api/uploads/song/nonexistent.wav")
        self.assertEqual(missing.status_code, 400)

    def test_project_persistence_api(self):
        project = {
            "panel": "video",
            "forms": {"video-form": {"title": "My Track", "backend": "local_h3"}},
            "files": {"video-form": {"song": "test.wav", "references": []}},
            "details_open": True,
            "log_open": False
        }
        res = self.client.put("/api/project", json=project)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["ok"])
        got = self.client.get("/api/project").json()
        self.assertEqual(got["panel"], "video")
        self.assertEqual(got["forms"]["video-form"]["title"], "My Track")
        self.assertTrue(got["details_open"])

    def test_clear_log_endpoint(self):
        studio_log = self.home / "studio.log"
        studio_log.write_text("historical error line\n", encoding="utf-8")
        self.assertIn("historical error", self.client.get("/api/log/latest").json()["log"])
        res = self.client.post("/api/log/clear")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "cleared"})

    def test_sse_events_and_jobs_subscription(self):
        notifications = []
        unsub = self.app.state.jobs.subscribe(lambda st, log: notifications.append((st, log)))
        self.app.state.jobs.notify({"state": "test_state"}, log_line="test_line")
        unsub()
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0][0]["state"], "test_state")
        self.assertEqual(notifications[0][1], "test_line")

        with self.client.stream("GET", "/api/events") as response:
            self.assertEqual(response.status_code, 200)
            self.assertIn("text/event-stream", response.headers["content-type"])
            lines = []
            for line in response.iter_lines():
                if line:
                    lines.append(line)
                if len(lines) >= 2:
                    break
            self.assertEqual(lines[0], "event: status")
            self.assertIn('"state":', lines[1])
        self.assertEqual(self.client.get("/api/log/latest").json()["log"], "No operation or server log recorded yet.")
        self.assertEqual(studio_log.read_text(encoding="utf-8"), "")

    def test_clear_cache_endpoint(self):
        cache_dir = self.home / "cache" / "prompts"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "test_prompt.json").write_text('{"prompt": "test"}', encoding="utf-8")
        self.assertTrue((cache_dir / "test_prompt.json").is_file())
        res = self.client.post("/api/cache/clear")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "cleared")
        self.assertEqual(res.json()["count"], 1)
        self.assertFalse((cache_dir / "test_prompt.json").exists())
        self.assertTrue((self.home / "cache_cleared.json").is_file())

    def test_empty_song_returns_friendly_error(self):
        res = self.client.post("/api/quote", json={"kind": "video", "song": "", "direction": "test"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("Upload a song first", res.json()["detail"])
        studio_log = (self.home / "studio.log").read_text(encoding="utf-8")
        self.assertIn("Preview failed (video): Upload a song first", studio_log)

    def test_passage_recovery_requires_matching_system(self):
        from types import SimpleNamespace
        from mmv.worker import find_cached_passage_prompt
        cache = self.home / "cache" / "prompts"
        cache.mkdir(parents=True, exist_ok=True)
        runs = self.home / "runs"
        previous = runs / "previous"
        (previous / "writer_jobs").mkdir(parents=True)
        job = {"segment_id": "seg000", "shots": []}
        write_json(previous / "writer_jobs/seg000.json", job)
        write_json(previous / "prompts.json", {"seg000": "validated old prompt"})
        (previous / "writer_system.md").write_text("old direction", encoding="utf-8")
        seg = SimpleNamespace(segment_id="seg000")
        self.assertIsNone(find_cached_passage_prompt(cache, runs, "new direction", job, seg, None))
        self.assertEqual(find_cached_passage_prompt(cache, runs, "old direction", job, seg, None),
                         "validated old prompt")
        # Matching saved prompts remain reusable after the fallback populated the cache.
        self.assertEqual(find_cached_passage_prompt(cache, None, "old direction", job, seg, None),
                         "validated old prompt")

    def test_production_supplies_public_actor_metadata(self):
        actors.create_actor(self.store, "blue", "Blue", "Distinctive blue jacket", picture())
        _, started = self.start({"song": self.song_upload(), "actors": ["blue"]})
        started.raise_for_status()
        self.assertEqual(self.wait()["state"], "complete")
        system = (self.home / "runs" / started.json()["id"] / "writer_system.md").read_text(encoding="utf-8")
        self.assertIn("CAST MEMBER: Blue", system)
        self.assertIn("Distinctive blue jacket", system)

    def test_prompt_caching_and_resumption(self):
        song = self.song_upload()
        quote, started = self.start({"song": song, "direction": "A sunlit coast", "title": "Coast"})
        started.raise_for_status()
        status = self.wait()
        self.assertEqual(status["state"], "complete")
        run_1 = self.home / "runs" / started.json()["id"]
        prompts_1 = read_json(run_1 / "prompts.json")
        self.assertTrue(bool(prompts_1))

        # Second production reuses cached prompts
        quote2, started2 = self.start({"song": song, "direction": "A sunlit coast", "title": "Coast", "reuse_prompts": True})
        started2.raise_for_status()
        status2 = self.wait()
        self.assertEqual(status2["state"], "complete")
        run_2 = self.home / "runs" / started2.json()["id"]
        prompts_2 = read_json(run_2 / "prompts.json")
        self.assertEqual(prompts_1, prompts_2)
        log_text = (run_2 / "operation.log").read_text(encoding="utf-8")
        self.assertIn("resumed from cache", log_text)

    def test_instrumental_and_lip_sync_validation(self):
        from mmv.engine.schema import validate_prompt, RIGGING_TAIL
        from mmv.engine.plan import Segment, Shot
        from mmv.engine.comfy import compute_ref_tags

        seg = Segment(
            index=0,
            song_start_frame=0,
            musical_frames=120,
            gen_frames=120,
            trim_frames=0,
            duration_input=5.0,
            montage_type="standard",
            section_index=0,
            section_label="mid",
            energy=0.5,
            thematic_anchor=None,
            ref_image_slots=0,
            footage_anchor="",
            practical_effects="",
            rigging="",
            audio_slice_start_s=0.0,
            audio_slice_end_s=5.0,
            shots=[Shot(n=1, start_frame=0, frames=120, cut_time=None, camera="static", shot_scale="medium", energy=0.5)],
        )
        tags = compute_ref_tags(0, 0, 1)

        from mmv.engine.schema import WriterResponse, assemble_prompt
        resp = WriterResponse(
            segment_id="seg000",
            style_opening="Cinematic daylight photography with expressive movement.",
            subject_definitions=[],
            summary="A performer in sunlight.",
            retention_analysis=[],
            shot_bodies=["The performer moves gracefully through a bright courtyard under sunlight. <Audio 1>"],
            overall_soundscape="Gentle instrumental music.",
            non_diegetic_music="N/A",
        )
        prompt_without_rigging = assemble_prompt(seg, resp, tags)

        # When silent_mouths is False (e.g. instrumental / no lyrics), missing rigging tail is permitted
        problems_instrumental = validate_prompt(prompt_without_rigging, seg, tags, strict_words=False, silent_mouths=False)
        self.assertEqual(problems_instrumental, [])

        # When silent_mouths is True, prompt without rigging tail triggers validation error
        problems_vocal = validate_prompt(prompt_without_rigging, seg, tags, strict_words=False, silent_mouths=True)
        self.assertIn("Subject Rigging block is missing (lip-sync suppression)", problems_vocal)

        # Auto-injection before overall_soundscape fixes the validation failure
        soundscape_pos = prompt_without_rigging.find("\noverall_soundscape:")
        remediated = prompt_without_rigging[:soundscape_pos].rstrip() + f" {RIGGING_TAIL}\n" + prompt_without_rigging[soundscape_pos:]
        problems_fixed = validate_prompt(remediated, seg, tags, strict_words=False, silent_mouths=True)
        self.assertEqual(problems_fixed, [])

        # End-to-end production run without lyrics completes cleanly
        quote, started = self.start({"song": self.song_upload(), "direction": "Warm light", "title": "Instrumental", "lyrics": ""})
        started.raise_for_status()
        status = self.wait()
        self.assertEqual(status["state"], "complete")
    def test_original_pipeline_real_assembly(self):
        quote, started = self.start({"song":self.song_upload(), "direction":"A sunlit coast", "title":"Coast"})
        started.raise_for_status()
        status = self.wait()
        self.assertEqual(status["state"], "complete", status)
        run = self.home / "runs" / started.json()["id"]
        self.assertTrue((run / "score.json").is_file())
        plan = read_json(run / "plan.json")
        self.assertEqual(quote.json()["analysis"]["shots"], sum(len(s["shots"]) for s in plan["segments"]))
        self.assertAlmostEqual(media.duration(run / "music-video.mp4"), plan["total_frames"]/24, delta=.08)
        prompts = read_json(run / "prompts.json")
        self.assertIn("subject_definitions:", next(iter(prompts.values())))
        self.assertIn("<Audio 1>", next(iter(prompts.values())))
        graph = next(b["prompt"] for path,b in MockService.requests if path == "/prompt")
        self.assertEqual(graph["124"]["inputs"]["steps"], 20)
        self.assertNotIn("115", graph)
        self.assertTrue(read_json(run / "consent.json")["accepted"])

    def test_ident_and_harvest(self):
        _, started = self.start({"kind":"ident", "title":"Studio", "ident_seconds":4})
        started.raise_for_status(); self.assertEqual(self.wait()["state"], "complete")
        image = self.client.post("/api/upload/reference", files={"file":("ref.png",picture())}).json()["file"]
        _, started = self.start({"kind":"harvest", "style_id":"teal", "title":"Teal", "references":[image]})
        started.raise_for_status(); status=self.wait(); self.assertEqual(status["state"], "complete", status)
        self.assertIn("Soft teal", self.store.style("teal")["style_card"])

    def test_deleted_timing_inputs_are_rejected(self):
        for name,value in (("bpm",120),("segment_seconds",8)):
            self.assertEqual(self.client.post("/api/quote",json={name:value}).status_code,422)
        html=self.client.get("/").text
        self.assertNotIn('name="bpm"',html)
        self.assertNotIn('name="segment_seconds"',html)

    def test_api_writer_requires_cost_and_no_implicit_render(self):
        settings=self.store.settings();settings.update(writer_mode="api",writer_call_estimate=0)
        self.client.put("/api/settings",json=settings).raise_for_status()
        response=self.client.post("/api/quote",json={"song":self.song_upload()})
        self.assertEqual(response.status_code,400)
        self.assertEqual(MockService.requests,[])

    def test_hosted_original_adapters_and_consent(self):
        self.store.save_key("WAVESPEED_API_KEY","mock-only-key")
        image=self.client.post("/api/upload/reference",files={"file":("ref.png",picture())}).json()["file"]
        song=self.song_upload()
        with patch.dict(os.environ,{"WAVESPEED_BASE_URL":self.url}):
            for backend,resolution,cost in (("wavespeed","768p",.4),("seedance_2_5","480p",.72)):
                MockService.requests=[]
                quote,rejected=self.start({"song":song,"backend":backend,"resolution":resolution,"references":[image]},consent=False)
                self.assertEqual(rejected.status_code,400)
                self.assertEqual(MockService.requests,[])
                self.assertEqual(quote.json()["estimate_usd"],cost)
                started=self.client.post("/api/start",json={"quote_id":quote.json()["id"],"consent":True})
                started.raise_for_status();status=self.wait();self.assertEqual(status["state"],"complete",status)
                submissions=[body for path,body in MockService.requests if path.endswith("/reference-to-video") or path.endswith("/text-to-video")]
                self.assertEqual(len(submissions),1)
                self.assertIn("subject_definitions:",read_json(self.home/"runs"/started.json()["id"]/"prompts.json")["seg000"])
                receipt=read_json(self.home/"runs"/started.json()["id"]/"renders.json")["seg000"]
                self.assertEqual(receipt["request_id"],"hosted-test")

    def test_failed_writer_never_renders(self):
        MockService.invalid_writer=True
        _,started=self.start({"song":self.song_upload()});started.raise_for_status()
        status=self.wait();self.assertEqual(status["state"],"failed")
        self.assertFalse(any(path=="/prompt" for path,body in MockService.requests))
        self.assertEqual(sum(path=="/chat/completions" for path,body in MockService.requests),3)

    def test_cancel_own_render_and_no_queue(self):
        MockService.hold=True
        _,started=self.start({"song":self.song_upload()});started.raise_for_status()
        deadline=time.monotonic()+15
        while time.monotonic()<deadline and not any(path=="/prompt" for path,body in MockService.requests): time.sleep(.05)
        self.assertTrue(any(path=="/prompt" for path,body in MockService.requests))
        self.assertEqual(self.client.post("/api/quote",json={"song":"anything"}).status_code,409)
        self.client.post("/api/cancel").raise_for_status()
        self.assertEqual(self.wait()["state"],"cancelled")
        self.assertTrue(any(path=="/queue" and body=={"delete":["local-test"]} for path,body in MockService.requests))

    def test_stale_preview_rejected(self):
        quote = self.client.post("/api/quote", json={"song": self.song_upload()}).json()
        settings = self.store.settings()
        settings["vision_model"] = "changed"
        self.client.put("/api/settings", json=settings).raise_for_status()
        rejected = self.client.post("/api/start", json={"quote_id": quote["id"], "consent": True})
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("changed", rejected.json()["detail"])

    def test_actor_signed_oap_round_trip_and_no_overwrite(self):
        response = self.client.post("/api/actors", data={"actor_id": "blue", "name": "Blue", "description": "Blue jacket"},
                                    files={"reference": ("ref.png", picture())})
        response.raise_for_status()
        package = self.client.post("/api/actors/blue/export")
        package.raise_for_status()
        uploaded = self.client.post("/api/upload/oap", files={"file": ("blue.oap", package.content)}).json()["file"]
        inspection = self.client.get("/api/oap/inspect/" + uploaded).json()
        self.assertTrue(inspection["verification"]["signature_valid"])
        self.assertFalse(inspection["verification"]["agent_known"])
        data = {"filename": uploaded, "actor_id": "blue_copy"}
        self.assertEqual(self.client.post("/api/oap/import", data=data).status_code, 400)
        data["accept_unknown"] = "true"
        imported = self.client.post("/api/oap/import", data=data)
        imported.raise_for_status()
        self.assertEqual(self.client.post("/api/actors/blue_copy/export").content, package.content)
        self.assertEqual(self.client.post("/api/oap/import", data=data).status_code, 400)
        self.assertNotIn("voice", imported.json())

    def test_oap_tamper_and_unsafe_archive_rejected(self):
        actor = actors.create_actor(self.store, "blue", "Blue", "", picture())
        path = actors.export_actor(self.store, "blue")
        corrupt = self.home / "corrupt.oap"
        with zipfile.ZipFile(path) as source, zipfile.ZipFile(corrupt, "w") as target:
            for member in source.infolist():
                target.writestr(member, b"tampered" if member.filename.endswith(".png") else source.read(member))
        with self.assertRaises(ValueError):
            actors.package_info(corrupt)
        with zipfile.ZipFile(corrupt, "w") as target:
            target.writestr("../escape", "unsafe")
            target.writestr("manifest.json", "{}")
        with self.assertRaisesRegex(ValueError, "unsafe"):
            actors.package_info(corrupt)

    def test_actor_rider_conflict_blocks_preview(self):
        actors.create_actor(self.store, "blue", "Blue", "", picture())
        content = {key: "none" for key in oap.CONTENT_ENUMS}
        content["nudity"] = "explicit"
        response = self.client.post("/api/quote", json={"song": self.song_upload(), "actors": ["blue"], "content": content})
        self.assertEqual(response.status_code, 400)
        self.assertIn("exceeds rider", response.json()["detail"])

    def test_credentials_not_returned_or_copied_into_settings(self):
        self.client.put("/api/key", json={"name": "WAVESPEED_API_KEY", "value": "private-example"}).raise_for_status()
        self.assertNotIn("private-example", self.client.get("/api/settings").text)
        if os.name != "nt":
            self.assertEqual((self.home / "secrets.json").stat().st_mode & 0o777, 0o600)

    def test_image_metadata_removed(self):
        data = io.BytesIO()
        image = Image.new("RGB", (20, 20), "teal")
        exif = Image.Exif()
        exif[0x010E] = "private metadata"
        image.save(data, "JPEG", exif=exif)
        destination = self.home / "clean.png"
        actors.clean_image(data.getvalue(), destination)
        with Image.open(destination) as clean:
            self.assertFalse(clean.getexif())


    def test_topaz_direct_export_command_and_original_preserved(self):
        _, started = self.start({"song": self.song_upload()})
        started.raise_for_status()
        self.assertEqual(self.wait()["state"], "complete")
        source = self.client.get("/api/outputs").json()[0]["file"]
        original = (self.home / "runs" / source).read_bytes()
        executable = self.home / "topaz-ffmpeg"
        executable.write_text("test fixture")
        models = self.home / "topaz-models"
        models.mkdir()
        (models / "ahq-12.json").write_text("{}")
        settings = self.store.settings()
        settings.update(topaz_executable=str(executable), topaz_models=str(models))
        self.client.put("/api/settings", json=settings).raise_for_status()
        commands = []

        def fake_command(context, argv, **kwargs):
            commands.append(argv)
            Path(argv[-1]).write_bytes(MockService.video)

        with patch("mmv.jobs.JobContext.command", fake_command):
            self.client.post("/api/upscale", json={"source": source, "model": "ahq-12", "scale": 2}).raise_for_status()
            result = self.wait()
        self.assertEqual(result["state"], "complete", result)
        self.assertTrue(any("tvai_up=model=ahq-12:scale=2" in str(x) for x in commands[0]))
        self.assertEqual((self.home / "runs" / source).read_bytes(), original)
        self.assertEqual(self.client.get("/api/outputs").json()[0]["kind"], "upscale")

    def test_security_and_private_features_absent(self):
        self.assertEqual(self.client.post("/api/cancel", headers={"Origin": "https://other.invalid"}).status_code, 403)
        for endpoint in ("/api/queue", "/api/vault/status", "/api/film", "/api/micro-drama/new", "/mondo_web.py"):
            self.assertEqual(self.client.get(endpoint).status_code, 404)
        response = self.client.get("/")
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        self.assertEqual(self.client.get("/", headers={"Host": "other.invalid"}).status_code, 400)
        self.assertEqual(self.client.get("/api/media/abc/secrets.json").status_code, 400)

    def test_invalid_settings_and_nonfinite_input(self):
        settings = self.store.settings()
        settings["vision_url"] = "file:///etc/passwd"
        self.assertEqual(self.client.put("/api/settings", json=settings).status_code, 422)
        self.assertEqual(self.client.post("/api/quote", json={"bpm": 0}).status_code, 422)
        self.assertEqual(self.client.post("/api/quote", json={"content": {"nudity": "invented"}}).status_code, 422)
        self.assertEqual(self.client.post("/api/quote", json={"kind": "film"}).status_code, 422)

    def install_test_h3_models(self):
        for category, name in [('vae', 'test_video_vae.safetensors'),
                               ('diffusion_models', 'test_diffusion.safetensors')]:
            folder = self.home / 'models' / category
            folder.mkdir(parents=True, exist_ok=True)
            (folder / name).write_text('test fixture; not real weights')

    def custom_h3_workflow(self):
        from mmv.pipeline import ENGINE
        graph = read_json(ENGINE / 'workflows/h3_ref2video_audionodeadded.json')
        graph['127']['inputs']['unet_name'] = 'my-current-model.safetensors'
        graph['127']['inputs']['weight_dtype'] = 'operator-precision'
        graph['custom-node'] = {'class_type': 'OperatorCustomNode', 'inputs': {'note': 'preserve me'}}
        # Loader IDs are not required to match the bundled graph.
        graph['527'] = graph.pop('127')
        for node in graph.values():
            for key, value in node['inputs'].items():
                if isinstance(value, list) and value and value[0] == '127':
                    node['inputs'][key] = ['527', *value[1:]]
        path = self.home / 'operator-graph.json'
        write_json(path, graph)
        mapping = read_json(ENGINE / 'config/injection_map.json')
        mapping.update(workflow=str(path), operator_note='preserve bindings too')
        map_path = self.home / 'operator-map.json'
        write_json(map_path, mapping)
        return graph, mapping, map_path

    def test_model_change_preserves_active_custom_graph_and_map(self):
        self.install_test_h3_models()
        graph, mapping, map_path = self.custom_h3_workflow()
        settings = self.store.settings()
        settings['workflow_map_path'] = str(map_path)
        self.client.put('/api/settings', json=settings).raise_for_status()
        response = self.client.get('/api/settings').json()
        self.assertEqual(response['settings']['h3_models']['diffusion_model'], 'my-current-model.safetensors')
        # A normal settings save must retain the selected map and model.
        self.client.put('/api/settings', json=response['settings']).raise_for_status()
        self.assertEqual(self.store.settings()['workflow_map_path'], str(map_path))
        settings = response['settings']
        settings['h3_models'] = {'diffusion_model': 'test_diffusion.safetensors'}
        self.client.put('/api/settings', json=settings).raise_for_status()
        saved_map = read_json(Path(self.store.settings()['workflow_map_path']))
        saved_graph = read_json(Path(saved_map['workflow']))
        expected = json.loads(json.dumps(graph))
        expected['527']['inputs']['unet_name'] = 'test_diffusion.safetensors'
        self.assertEqual(saved_graph, expected)
        self.assertEqual({**saved_map, 'workflow': mapping['workflow']}, mapping)
        # Keep the operator-owned sources intact, including precision and added nodes.
        self.assertEqual(read_json(Path(mapping['workflow'])), graph)
        self.assertEqual(read_json(map_path), mapping)

    def test_ambiguous_model_loaders_are_not_silently_selected(self):
        self.install_test_h3_models()
        graph, mapping, map_path = self.custom_h3_workflow()
        graph['another-loader'] = {'class_type': 'UNETLoader', 'inputs': {'unet_name': 'second-model.safetensors'}}
        write_json(Path(mapping['workflow']), graph)
        settings = {**self.store.settings(), 'workflow_map_path': str(map_path)}
        self.client.put('/api/settings', json=settings).raise_for_status()
        self.assertNotIn('diffusion_model', self.client.get('/api/settings').json()['settings']['h3_models'])
        settings['h3_models'] = {'diffusion_model': 'test_diffusion.safetensors'}
        response = self.client.put('/api/settings', json=settings)
        self.assertEqual(response.status_code, 400)
        self.assertIn('unambiguous', response.json()['detail'])
        self.assertEqual(read_json(Path(mapping['workflow'])), graph)

    def test_new_workflow_path_is_not_overridden_on_save(self):
        _, _, map_path = self.custom_h3_workflow()
        settings = self.client.get('/api/settings').json()['settings']
        settings.pop('h3_models')  # Browser submits only explicit model changes.
        settings['workflow_map_path'] = str(map_path)
        self.client.put('/api/settings', json=settings).raise_for_status()
        self.assertEqual(self.store.settings()['workflow_map_path'], str(map_path))

    def test_model_discovery_falls_back_per_category(self):
        self.install_test_h3_models()
        self.server.object_info = {'VAELoader': {'VAELoader': {'input': {'required': {
            'vae_name': [['live-video-vae.safetensors']]}}}}}
        info = self.client.get('/api/settings').json()['h3_models_installed']
        self.assertEqual(info['video_vae'], ['live-video-vae.safetensors'])
        self.assertIn('test_diffusion.safetensors', info['diffusion_model'])

    def test_unavailable_or_unsafe_model_selections_do_not_change_settings(self):
        before = self.store.settings()
        for models, status in [({'diffusion_model': 'not-installed.safetensors'}, 400),
                               ({'diffusion_model': '../private.safetensors'}, 422),
                               ({'unknown_role': 'test.safetensors'}, 422)]:
            request = {**before, 'h3_models': models}
            self.assertEqual(self.client.put('/api/settings', json=request).status_code, status)
            self.assertEqual(self.store.settings(), before)

    def test_h3_model_settings_roundtrip(self):
        self.install_test_h3_models()
        res = self.client.get("/api/settings")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("settings", body)
        self.assertIn("h3_models", body["settings"])
        self.assertIn("h3_models_installed", body)
        self.assertIn("video_vae", body["settings"]["h3_models"])
        self.assertIn("diffusion_model", body["settings"]["h3_models"])

        settings = self.store.settings()
        settings["h3_models"] = {
            "video_vae": "test_video_vae.safetensors",
            "diffusion_model": "test_diffusion.safetensors",
        }
        self.client.put("/api/settings", json=settings).raise_for_status()

        updated = self.client.get("/api/settings").json()
        self.assertEqual(updated["settings"]["h3_models"]["video_vae"], "test_video_vae.safetensors")
        self.assertEqual(updated["settings"]["h3_models"]["diffusion_model"], "test_diffusion.safetensors")

    def test_browse_fs(self):
        res = self.client.get("/api/fs/browse")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("current", data)
        self.assertIn("drives", data)
        self.assertIn("folders", data)

        sub = self.home / "subfolder_test"
        sub.mkdir()
        file_path = sub / "test.json"
        file_path.write_text("{}")

        res_folder = self.client.get(f"/api/fs/browse?path={self.home}&mode=folder")
        self.assertEqual(res_folder.status_code, 200)
        folder_names = [f["name"] for f in res_folder.json()["folders"]]
        self.assertIn("subfolder_test", folder_names)

        res_file = self.client.get(f"/api/fs/browse?path={sub}&mode=file&ext=.json")
        self.assertEqual(res_file.status_code, 200)
        file_names = [f["name"] for f in res_file.json()["files"]]
        self.assertIn("test.json", file_names)


class UtilityTests(unittest.TestCase):

    def test_windows_json_read_retries_only_permission_errors(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        path = Mock()
        path.exists.return_value = True
        path.read_text.side_effect = [PermissionError('transient lock'), '{"ok": true}']
        with patch('mmv.storage.os', SimpleNamespace(name='nt')), patch('mmv.storage.time.sleep'):
            self.assertEqual(read_json(path), {'ok': True})
        self.assertEqual(path.read_text.call_count, 2)
        path.read_text.side_effect = PermissionError('not transient on POSIX')
        with patch('mmv.storage.os', SimpleNamespace(name='posix')):
            with self.assertRaises(PermissionError):
                read_json(path)


    def test_single_session_and_interrupted_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Storage(temp)
            with SessionLock(store.home):
                with self.assertRaises(ValueError):
                    with SessionLock(store.home):
                        pass
            write_json(store.home / "operation.json", {"state": "running", "id": "old"})
            jobs = Jobs(store)
            self.assertEqual(jobs.status()["state"], "interrupted")

    def test_model_download_consent_integrity_and_path_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Storage(temp)
            manifest = store.home / "manifest.json"
            data = b"small fixture, not an AI model"
            entry = {"name": "Test fixture", "url": "https://example.invalid/model", "license_url": "https://example.invalid/license",
                     "sha256": hashlib.sha256(data).hexdigest(), "destination": "test/model.gguf", "size_bytes": len(data)}
            write_json(manifest, {"models": [entry]})
            with patch("builtins.input", return_value="no"), patch("urllib.request.urlopen") as network:
                download_models(store, manifest)
                network.assert_not_called()
            response = io.BytesIO(data)
            response.url = entry["url"]
            with patch("builtins.input", return_value="yes"), patch("urllib.request.urlopen", return_value=response):
                download_models(store, manifest)
            self.assertEqual((store.home / "models/test/model.gguf").read_bytes(), data)
            entry["destination"] = "../../escape"
            write_json(manifest, {"models": [entry]})
            with self.assertRaises(ValueError):
                download_models(store, manifest)

    def test_inside_rejects_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                inside(Path(temp), "../secrets")

    def test_corrupt_model_download_never_activated(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Storage(temp)
            manifest = store.home / "manifest.json"
            write_json(manifest, {"models": [{"name": "Corrupt fixture", "url": "https://example.invalid/model",
                       "license_url": "https://example.invalid/license", "sha256": "0" * 64,
                       "destination": "model.gguf"}]})
            response = io.BytesIO(b"not matching the checksum")
            response.url = "https://example.invalid/model"
            with patch("builtins.input", return_value="yes"), patch("urllib.request.urlopen", return_value=response):
                with self.assertRaisesRegex(ValueError, "integrity"):
                    download_models(store, manifest)
            self.assertFalse((store.home / "models/model.gguf").exists())
            self.assertTrue((store.home / "models/model.gguf.partial").exists())

    def test_invalid_manifest_rejected_before_any_download(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Storage(temp)
            manifest = store.home / "manifest.json"
            write_json(manifest, {"models": [{"name": "Invalid", "url": "http://example.invalid/file"}]})
            with patch("urllib.request.urlopen") as network:
                with self.assertRaises(ValueError):
                    download_models(store, manifest)
                network.assert_not_called()

    def test_service_error_reporting_identifies_comfyui_and_launch_key(self):
        from mmv import runtime
        with patch.object(runtime, "http_ok", return_value=False):
            with self.assertRaises(ValueError) as ctx:
                runtime.start_service("", "", "http://127.0.0.1:8188/system_stats", Path("/tmp/comfy-service.log"))
            msg = str(ctx.exception)
            self.assertIn("ComfyUI service is not running", msg)
            self.assertIn("http://127.0.0.1:8188/system_stats", msg)
            self.assertIn("comfy_launch", msg)

    def test_service_error_reporting_identifies_llama_and_launch_key(self):
        from mmv import runtime
        with patch.object(runtime, "http_ok", return_value=False):
            with self.assertRaises(ValueError) as ctx:
                runtime.start_service("", "", "http://127.0.0.1:8080/v1/models", Path("/tmp/writer-service.log"))
            msg = str(ctx.exception)
            self.assertIn("llama.cpp", msg)
            self.assertIn("http://127.0.0.1:8080/v1/models", msg)
            self.assertIn("writer_launch", msg)

    def test_service_identification_vision_and_laya(self):
        from mmv import runtime
        name, key = runtime.identify_service(health_url="http://127.0.0.1:8080/v1/chat/completions", log="/tmp/vision.log")
        self.assertIn("Vision", name)
        name, key = runtime.identify_service(health_url=None, log="/tmp/laya.log")
        self.assertIn("Laya", name)

    def test_operation_log_endpoint_includes_comfy_log(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Storage(temp)
            run_dir = store.home / "runs" / "test_run"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "operation.log").write_text("Starting pipeline\n", encoding="utf-8")
            (run_dir / "comfy-service.log").write_text("ComfyUI startup output log", encoding="utf-8")
            (run_dir / "writer-service.log").write_text("llama-server output log", encoding="utf-8")
            app = create_app(store.home, test_hosts=True)
            client = TestClient(app)
            res = client.get("/api/log/test_run")
            self.assertEqual(res.status_code, 200)
            log_text = res.json()["log"]
            self.assertIn("--- ComfyUI Service Output ---", log_text)
            self.assertIn("ComfyUI startup output log", log_text)
            self.assertIn("--- Writer Service Output (llama.cpp) ---", log_text)
            self.assertIn("llama-server output log", log_text)


if __name__ == "__main__":
    unittest.main()

