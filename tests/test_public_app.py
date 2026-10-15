"""Public boundary and complete mocked-renderer productions with real media assembly."""
import hashlib
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


class MockService(BaseHTTPRequestHandler):
    requests = []
    video = b""
    hold = False

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
        if self.path == "/media/upload/binary":
            self.reply({"data": {"download_url": "https://example.invalid/reference"}})
            return
        body = json.loads(data)
        type(self).requests.append((self.path, body))
        if self.path == "/prompt":
            self.reply({"prompt_id": "local-test", "node_errors": {}})
        elif self.path == "/chat/completions":
            self.reply({"choices": [{"message": {"content": "Soft teal light, flowing fabric, patient camera movement."}}]})
        elif self.path == "/queue":
            self.reply({})
        else:
            self.reply({"data": {"id": "hosted-test"}})

    def do_GET(self):
        if self.path.startswith("/view") or self.path == "/video.mp4":
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(self.video)))
            self.end_headers()
            self.wfile.write(self.video)
        elif self.path.startswith("/history/"):
            self.reply({} if self.hold else {"local-test": {"status": {"status_str": "success"},
                        "outputs": {"2": {"videos": [{"filename": "mock.mp4", "subfolder": "", "type": "output"}]}}}})
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
        self.graph = self.home / "test-workflow.json"
        self.mapping = self.home / "test-map.json"
        write_json(self.graph, {"1": {"class_type": "TestReference", "inputs": {
            "prompt": "", "duration": 5, "width": 128, "height": 72, "seed": 1, "filename_prefix": "test"}},
            "2": {"class_type": "SaveVideo", "inputs": {"video": ["1", 0]}}})
        write_json(self.mapping, {"reference_node": "1", "output_node": "2", "inputs": {
            name: ["1", "filename_prefix" if name == "video_prefix" else name]
            for name in ("prompt", "duration", "width", "height", "seed", "video_prefix")}})
        (self.home / "comfy-input").mkdir()
        settings = self.store.settings()
        settings.update(comfy_url=self.url, comfy_input=str(self.home / "comfy-input"), workflow_path=str(self.graph),
                        workflow_map_path=str(self.mapping), vision_url=self.url, vision_model="test")
        self.client.put("/api/settings", json=settings).raise_for_status()
        MockService.requests = []
        MockService.hold = False

    def tearDown(self):
        if self.app.state.jobs.active:
            self.app.state.jobs.cancel()
            self.wait()
        self.client.close()
        self.temp.cleanup()

    def song_upload(self):
        response = self.client.post("/api/upload/song", files={"file": ("test.wav", self.song, "audio/wav")})
        response.raise_for_status()
        return response.json()["file"]

    def wait(self, timeout=25):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.client.get("/api/status").json()
            if status["state"] not in ("running", "cancelling") and self.app.state.jobs.active is None:
                return status
            time.sleep(.05)
        self.fail("Operation did not finish")

    def start(self, request, consent=True):
        quote = self.client.post("/api/quote", json=request)
        quote.raise_for_status()
        start = self.client.post("/api/start", json={"quote_id": quote.json()["id"], "consent": consent})
        return quote, start

    def test_version_matches_package_and_readme(self):
        import tomllib
        root = Path(__file__).resolve().parents[1]
        project = tomllib.loads((root / "pyproject.toml").read_text())
        self.assertEqual(api_version()["version"], "0.1.1")
        self.assertEqual(project["project"]["version"], MGL_APP_VERSION)
        self.assertIn("0.1.1", (root / "README.md").read_text())
        self.assertEqual(self.client.get("/api/version").json(), api_version())

    def test_full_local_video_real_assembly(self):
        quote, start = self.start({"song": self.song_upload(), "direction": "A sunlit coast", "title": "Coast"})
        start.raise_for_status()
        self.assertEqual(quote.json()["estimate_usd"], 0)
        status = self.wait()
        self.assertEqual(status["state"], "complete", status)
        output = self.client.get("/api/outputs").json()[0]
        self.assertAlmostEqual(output["duration"], 1.1, delta=.09)
        self.assertEqual(self.client.get("/api/media/" + output["file"]).status_code, 200)
        self.assertTrue((self.home / "runs" / start.json()["id"] / "requests.json").exists())
        self.assertTrue(read_json(self.home / "runs" / start.json()["id"] / "consent.json")["accepted"])
        graph = next(body["prompt"] for path, body in MockService.requests if path == "/prompt")
        self.assertIn("<Audio 1>", graph["1"]["inputs"]["prompt"])

    def test_paid_consent_and_hosted_full_video(self):
        self.store.save_key("WAVESPEED_API_KEY", "mock-only-key")
        image = self.client.post("/api/upload/reference", files={"file": ("ref.png", picture())}).json()["file"]
        request = {"song": self.song_upload(), "backend": "wavespeed", "references": [image], "direction": "Ocean waves"}
        with patch.object(render, "BASE", self.url):
            quote, rejected = self.start(request, consent=False)
            self.assertEqual(rejected.status_code, 400)
            self.assertEqual(MockService.requests, [])
            self.assertEqual(quote.json()["estimate_usd"], .40)
            accepted = self.client.post("/api/start", json={"quote_id": quote.json()["id"], "consent": True})
            accepted.raise_for_status()
            result = self.wait()
        self.assertEqual(result["state"], "complete", result)
        submissions = [body for path, body in MockService.requests if path.endswith("/reference-to-video")]
        self.assertEqual(len(submissions), 1)
        self.assertEqual(submissions[0]["duration"], 4)
        self.assertEqual(len(submissions[0]["reference_images"]), 1)

    def test_ident_and_attached_credits(self):
        quote, start = self.start({"kind": "ident", "title": "Studio", "direction": "Sunlight", "ident_seconds": 4})
        start.raise_for_status()
        self.assertEqual(quote.json()["clips"], 1)
        self.assertEqual(self.wait()["state"], "complete")
        ident = self.client.get("/api/outputs").json()[0]["file"]
        _, start = self.start({"song": self.song_upload(), "start_ident": ident, "end_ident": ident, "direction": "Coast"})
        start.raise_for_status()
        status = self.wait()
        self.assertEqual(status["state"], "complete", status)
        self.assertAlmostEqual(status["result"]["duration"], 9.1, delta=.15)

    def test_harvest_end_to_end(self):
        image = self.client.post("/api/upload/reference", files={"file": ("ref.png", picture())}).json()["file"]
        _, start = self.start({"kind": "harvest", "style_id": "teal", "title": "Teal", "references": [image]})
        start.raise_for_status()
        status = self.wait()
        self.assertEqual(status["state"], "complete", status)
        self.assertIn("Soft teal", self.store.style("teal")["direction"])

    def test_cancel_and_no_queue(self):
        MockService.hold = True
        _, start = self.start({"song": self.song_upload()})
        start.raise_for_status()
        deadline = time.monotonic() + 5
        while not any(path == "/prompt" for path, body in MockService.requests) and time.monotonic() < deadline:
            time.sleep(.03)
        self.assertEqual(self.client.post("/api/quote", json={"song": "anything"}).status_code, 409)
        self.assertEqual(self.client.put("/api/settings", json=self.store.settings()).status_code, 409)
        self.client.post("/api/cancel").raise_for_status()
        self.assertEqual(self.wait()["state"], "cancelled")
        self.assertTrue(any(path == "/queue" and body == {"delete": ["local-test"]} for path, body in MockService.requests))

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

    def test_seedance_payload_and_cost(self):
        self.store.save_key("WAVESPEED_API_KEY", "mock-only-key")
        with patch.object(render, "BASE", self.url):
            quote, started = self.start({"song": self.song_upload(), "backend": "seedance_2_5",
                                         "resolution": "480p", "direction": "Sunlit coast"})
            started.raise_for_status()
            self.assertEqual(quote.json()["estimate_usd"], .72)
            result = self.wait()
        self.assertEqual(result["state"], "complete", result)
        submissions = [body for path, body in MockService.requests if path.endswith("seedance-2.5/text-to-video")]
        self.assertEqual(len(submissions), 1)
        self.assertIn("@Audio 1", submissions[0]["prompt"])
        self.assertNotIn("reference_images", submissions[0])

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

    def test_missing_models_and_api_key_fail_before_generation(self):
        self.graph.unlink()
        response = self.client.post("/api/quote", json={"song": self.song_upload()})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(MockService.requests, [])
        with patch.dict(os.environ, {"WAVESPEED_API_KEY": ""}):
            response = self.client.post("/api/quote", json={"song": "missing", "backend": "seedance_2", "resolution": "480p"})
            self.assertEqual(response.status_code, 400)


class UtilityTests(unittest.TestCase):
    def test_music_plan_covers_song_and_local_grid(self):
        for seconds in (.1, 1, 8, 14.1, 61.3, 180):
            for backend in render.CATALOG:
                segments = media.plan(seconds, backend, bpm=123)
                self.assertEqual(sum(x["frames"] for x in segments), max(1, __import__("math").ceil(seconds * 24)))
                for segment in segments:
                    self.assertGreaterEqual(segment["gen_frames"], segment["frames"])
                    if backend == "local_h3":
                        self.assertEqual((segment["gen_frames"] - 5) % 17, 0)
                        self.assertEqual(segment["duration"], segment["gen_frames"] / 24)

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


if __name__ == "__main__":
    unittest.main()
