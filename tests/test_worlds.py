"""Worlds: ledger data, private store and versions, review of harvest proposals, and the mocked-vision harvest."""
import json
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from fastapi.testclient import TestClient

from mmv import package_export, worlds
from mmv.api_profiles import save_settings
from mmv.storage import Storage
from webapp.mondo_web import ProductionRequest, create_app, request_dict, with_world
from test_public_app import picture

LEDGER = {
    "name": "Salt Archive", "seed_sentence": "A filing system that processes people like paper.",
    "core_laws": ["The record outlives the person"], "practices": ["Stamping the wound as a form"],
    "subjects": [{"designation": "the Graft Clerk", "canon": "Stamps wounds as forms"}],
    "pools": {"settings": {"include": ["a basement archive", "a lamplit registry"], "exclude": ["beach"]},
              "costume": {"include": ["grey smock"]}, "lighting": {"exclude": ["neon"]}},
}


class WorldDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def test_normalize_rejects_oversize_user_data_but_trims_model_output(self):
        with self.assertRaises(ValueError):
            worlds.normalize({**LEDGER, "core_laws": ["x" * 401]})
        with self.assertRaises(ValueError):
            worlds.normalize({**LEDGER, "pools": {"nonsense": {"include": ["a"]}}})
        with self.assertRaises(ValueError):
            worlds.normalize({"seed_sentence": "no name"})
        trimmed = worlds.normalize({**LEDGER, "core_laws": ["x" * 900, "x" * 900, 5], "pools": {"nonsense": {}}}, fit=True)
        self.assertEqual(len(trimmed["core_laws"]), 1)
        self.assertEqual(len(trimmed["core_laws"][0]), 400)
        self.assertEqual(set(trimmed["pools"]), set(worlds.WORLD_TABLES))

    def test_growing_merges_additions_and_an_echoed_ledger_changes_nothing(self):
        base = worlds.normalize({**LEDGER, "id": "salt"})
        self.assertEqual(worlds.diff(base, worlds.grow(base, worlds.normalize(LEDGER))), [])
        reply = worlds.normalize({
            "name": "Renamed By The Model", "seed_sentence": "",
            "core_laws": ["the record outlives the person", "Ink is never dry"],
            "subjects": [{"designation": "The Graft Clerk", "canon": ""}, {"designation": "the Ink Warden", "canon": "Keeps the wells"},
                         {"designation": "the Graft Clerk", "canon": "Stamps wounds as forms and files the scars"}],
            "pools": {"settings": {"include": ["A Basement Archive", "a flooded vault"]}, "lighting": {"exclude": ["Neon", "daylight"]}}})
        grown = worlds.grow(base, reply)
        self.assertEqual((grown["name"], grown["seed_sentence"]), (base["name"], base["seed_sentence"]))
        self.assertEqual(grown["core_laws"], ["The record outlives the person", "Ink is never dry"])
        self.assertEqual([(s["designation"], s["canon"]) for s in grown["subjects"]],
                         [("the Graft Clerk", "Stamps wounds as forms and files the scars"), ("the Ink Warden", "Keeps the wells")])
        self.assertEqual(grown["pools"]["settings"]["include"], ["a basement archive", "a lamplit registry", "a flooded vault"])
        self.assertEqual(grown["pools"]["lighting"]["exclude"], ["neon", "daylight"])
        self.assertEqual({item["field"] for item in worlds.diff(base, grown)},
                         {"core_laws", "subjects", "settings include", "lighting exclude"})
        crowded = worlds.normalize({**LEDGER, "core_laws": [f"law {n}" for n in range(worlds.MAX_LIST)]})
        self.assertEqual(worlds.grow(crowded, worlds.normalize({**LEDGER, "core_laws": ["one more"]}))["core_laws"], crowded["core_laws"])

    def test_editing_makes_the_next_version_from_a_known_base_and_keeps_sources(self):
        worlds.create(self.store, "salt", LEDGER, new_sources=[("lore", "a.md")])
        edited = {**LEDGER, "name": "Salt Archive II", "core_laws": ["A new law"]}
        preview = worlds.preview_edit(self.store, "salt", edited)
        self.assertEqual(preview["version"], 1)
        self.assertEqual({item["field"]: (item["added"], item["removed"]) for item in preview["changes"] if item["field"] == "core_laws"},
                         {"core_laws": (["A new law"], ["The record outlives the person"])})
        self.assertEqual(worlds.load(self.store, "salt")["version"], 1)
        saved = worlds.edit(self.store, "salt", edited, 1)
        self.assertEqual((saved["version"], saved["name"], saved["core_laws"]), (2, "Salt Archive II", ["A new law"]))
        self.assertEqual(saved["sources"], [{"type": "lore", "ref": "a.md", "added_in_version": 1}])
        self.assertEqual(worlds.load(self.store, "salt", 1)["core_laws"], LEDGER["core_laws"])
        with self.assertRaisesRegex(ValueError, "changed after you opened"):
            worlds.edit(self.store, "salt", edited, 1)
        with self.assertRaisesRegex(ValueError, "Nothing was changed"):
            worlds.edit(self.store, "salt", edited, 2)
        with self.assertRaises(ValueError):
            worlds.edit(self.store, "salt", {**edited, "core_laws": ["x" * 401]}, 2)
        self.assertEqual(worlds.load(self.store, "salt")["version"], 2)

    def test_pools_become_the_existing_custom_vocabulary_shape(self):
        ledger = worlds.normalize(LEDGER)
        replace = worlds.custom_vocabulary(ledger, "replace")
        self.assertEqual(replace["settings"], {"mode": "replace", "add": ["a basement archive", "a lamplit registry"], "exclude": ["beach"]})
        self.assertEqual(replace["lighting"], {"mode": "append", "add": [], "exclude": ["neon"]})
        self.assertNotIn("mechanisms", replace)
        self.assertEqual(worlds.custom_vocabulary(ledger, "append")["costume"]["mode"], "append")
        with self.assertRaises(ValueError):
            worlds.custom_vocabulary(ledger, "pin")

    def test_pools_are_accepted_by_the_real_vocabulary_loader(self):
        from mmv.pipeline import apply_vocabulary_overrides
        base = {table: ["stock one", "stock two", "beach", "neon"] for table in worlds.WORLD_TABLES}
        result = apply_vocabulary_overrides(base, worlds.custom_vocabulary(worlds.normalize(LEDGER), "replace"))
        self.assertEqual(result["settings"], ["a basement archive", "a lamplit registry"])
        self.assertNotIn("neon", result["lighting"])
        self.assertEqual(result["mechanisms"], base["mechanisms"])

    def test_versions_diff_rollback_and_delete(self):
        first = worlds.create(self.store, "salt", LEDGER, new_sources=[("lore", "a.txt")])
        self.assertEqual(first["version"], 1)
        self.assertEqual(first["sources"], [{"type": "lore", "ref": "a.txt", "added_in_version": 1}])
        second = worlds.revise(self.store, "salt", {**LEDGER, "core_laws": ["Nothing leaves unfiled"]}, new_sources=[("image", "b.png")])
        self.assertEqual([item["added_in_version"] for item in second["sources"]], [1, 2])
        changes = {item["field"]: item for item in worlds.diff(first, second)}
        self.assertEqual(changes["core_laws"]["added"], ["Nothing leaves unfiled"])
        self.assertEqual(changes["core_laws"]["removed"], ["The record outlives the person"])
        restored = worlds.rollback(self.store, "salt", 1)
        self.assertEqual(restored["version"], 3)
        self.assertEqual(restored["core_laws"], first["core_laws"])
        self.assertEqual([item["version"] for item in worlds.versions(self.store, "salt")], [1, 2, 3])
        with self.assertRaises(ValueError):
            worlds.rollback(self.store, "salt", 3)
        with self.assertRaises(ValueError):
            worlds.create(self.store, "salt", LEDGER)
        with self.assertRaises(ValueError):
            worlds.create(self.store, "proposals", LEDGER)
        worlds.delete(self.store, "salt")
        self.assertEqual(worlds.listing(self.store), [])
        (self.store.home / "worlds" / "empty").mkdir(parents=True)
        self.assertEqual(worlds.listing(self.store), [])

    def test_linked_world_folders_are_refused_and_records_are_private(self):
        import os, stat
        worlds.create(self.store, "salt", LEDGER)
        record = self.store.home / "worlds" / "salt" / "v0001.json"
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(record.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(record.parent.stat().st_mode), 0o700)
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (outside / "v0001.json").write_text(json.dumps({**worlds.normalize(LEDGER), "id": "linked", "version": 1}))
        os.symlink(outside, self.store.home / "worlds" / "linked")
        for call in (worlds.load, worlds.versions, worlds.delete):
            with self.assertRaises(ValueError):
                call(self.store, "linked")
        self.assertEqual([item["id"] for item in worlds.listing(self.store)], ["salt"])
        worlds.write_proposal(self.store, "p-one", "salt", "grow", 1, {**worlds.normalize(LEDGER), "id": "salt"}, [], {})
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE((self.store.home / "world-proposals" / "p-one.json").stat().st_mode), 0o600)

    def test_version_numbers_past_9999_stay_in_order(self):
        worlds.create(self.store, "salt", LEDGER)
        directory = self.store.home / "worlds" / "salt"
        (directory / "v0001.json").rename(directory / "v9999.json")
        nine = {**json.loads((directory / "v9999.json").read_text()), "version": 9999}
        (directory / "v9999.json").write_text(json.dumps(nine))
        self.assertEqual(worlds.revise(self.store, "salt", LEDGER)["version"], 10000)
        self.assertEqual(worlds.revise(self.store, "salt", LEDGER)["version"], 10001)
        self.assertEqual([item["version"] for item in worlds.versions(self.store, "salt")], [9999, 10000, 10001])
        self.assertEqual(worlds.load(self.store, "salt")["version"], 10001)

    def test_proposals_apply_only_when_accepted_and_only_if_the_world_is_unchanged(self):
        worlds.create(self.store, "salt", LEDGER)
        proposed = {**worlds.normalize(LEDGER), "id": "salt", "core_laws": ["Nothing leaves unfiled"]}
        worlds.write_proposal(self.store, "p-one", "salt", "grow", 1, proposed, [("image", "x.png")], {"vision": "m"})
        self.assertEqual(worlds.load(self.store, "salt")["version"], 1)
        self.assertEqual(worlds.list_proposals(self.store)[0]["id"], "p-one")
        worlds.revise(self.store, "salt", LEDGER)
        with self.assertRaises(ValueError):
            worlds.accept(self.store, "p-one")
        worlds.write_proposal(self.store, "p-two", "salt", "grow", 2, proposed, [("image", "x.png")], {"vision": "m"})
        accepted = worlds.accept(self.store, "p-two")
        self.assertEqual((accepted["version"], accepted["core_laws"]), (3, ["Nothing leaves unfiled"]))
        worlds.reject(self.store, "p-one")
        self.assertEqual(worlds.list_proposals(self.store), [])

    def test_shared_receipts_and_packages_never_carry_a_world(self):
        receipt = {"kind": "video", "world_id": "salt", "world_pool_mode": "replace", "custom_vocabulary": {"settings": {}}, "seed": 1,
                   "nested": {"world_id": "salt", "custom_vocabulary": {"a": 1}}}
        public = package_export.public_instrument_receipt(receipt)
        self.assertEqual(public, {"kind": "video", "seed": 1, "nested": {}})
        own = {"kind": "video", "custom_vocabulary": {"settings": {}}}
        self.assertEqual(package_export.public_instrument_receipt(own), own)
        root = Path(__file__).resolve().parents[1]
        manifest = (root / "MANIFEST.in").read_text()
        for private in ("prune worlds", "prune world-proposals", "prune data"):
            self.assertIn(private, manifest)
        gitignore = (root / ".gitignore").read_text().split()
        self.assertIn("worlds/", gitignore)
        self.assertIn("world-proposals/", gitignore)
        self.assertIn("*.world.json", gitignore)


class VisionMock(BaseHTTPRequestHandler):
    bodies = []
    reply_text = json.dumps({**LEDGER, "name": "Mock World"})

    def log_message(self, *args):
        pass

    def send_json(self, value):
        data = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.send_json({"data": [{"id": "fixture-vision"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        type(self).bodies.append(body)
        self.send_json({"choices": [{"message": {"content": type(self).reply_text}}]})


class WorldApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media = tempfile.TemporaryDirectory()
        cls.video = Path(cls.media.name) / "clip.mp4"
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=128x72:r=24:d=4",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(cls.video)], check=True)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), VisionMock)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.media.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.app = create_app(self.home, test_hosts=True)
        self.client = TestClient(self.app)
        self.store = self.app.state.store
        settings = self.store.settings()
        settings.update(vision_url=self.url, vision_model="fixture-vision")
        save_settings(self.store, settings)
        VisionMock.bodies = []
        VisionMock.reply_text = json.dumps({**LEDGER, "name": "Mock World"})

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def wait(self, timeout=60):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.client.get("/api/status").json()
            if status["state"] not in ("running", "cancelling") and self.app.state.jobs.active is None:
                return status
            time.sleep(.05)
        self.fail("Operation did not finish")

    def upload(self, kind, name, data):
        response = self.client.post(f"/api/upload/{kind}", files={"file": (name, data)})
        response.raise_for_status()
        return response.json()["file"]

    def harvest(self, **fields):
        quote = self.client.post("/api/quote", json={"kind": "world_harvest", **fields})
        if quote.status_code != 200:
            return quote, None
        return quote, self.client.post("/api/start", json={"quote_id": quote.json()["id"], "consent": True})

    def test_manual_world_crud_and_export(self):
        created = self.client.post("/api/worlds", json={"id": "salt", **LEDGER})
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual([item["id"] for item in self.client.get("/api/worlds").json()], ["salt"])
        self.assertEqual(self.client.get("/api/worlds/salt").json()["subjects"][0]["designation"], "the Graft Clerk")
        self.assertEqual(self.client.get("/api/worlds/salt/versions").json(), [{"version": 1, "updated": created.json()["updated"]}])
        self.assertEqual(self.client.get("/api/worlds/salt/export").json()["name"], "Salt Archive")
        self.assertEqual(self.client.post("/api/worlds", json={"id": "salt", **LEDGER}).status_code, 400)
        self.assertEqual(self.client.post("/api/worlds", json={"id": "Bad Id", **LEDGER}).status_code, 400)
        self.assertEqual(self.client.delete("/api/worlds/salt").status_code, 200)
        self.assertEqual(self.client.get("/api/worlds/salt").status_code, 400)

    def test_a_video_request_draws_its_vocabulary_from_the_chosen_world(self):
        self.client.post("/api/worlds", json={"id": "salt", **LEDGER}).raise_for_status()
        plain = request_dict(ProductionRequest())
        self.assertNotIn("world_id", plain)
        self.assertNotIn("world_images", plain)
        self.assertEqual(with_world(self.store, plain), plain)
        chosen = with_world(self.store, request_dict(ProductionRequest(world_id="salt", custom_vocabulary={"mechanisms": {"mode": "append", "add": ["mine"]}})))
        self.assertEqual(chosen["custom_vocabulary"]["settings"]["mode"], "replace")
        self.assertEqual(chosen["custom_vocabulary"]["mechanisms"]["add"], ["mine"])
        appended = with_world(self.store, request_dict(ProductionRequest(world_id="salt", world_pool_mode="append")))
        self.assertEqual(appended["custom_vocabulary"]["settings"]["mode"], "append")
        with self.assertRaises(ValueError):
            with_world(self.store, request_dict(ProductionRequest(world_id="missing")))
        self.assertNotIn("world_id", request_dict(ProductionRequest(kind="ident", world_id="salt")))

    def test_create_from_mixed_sources_then_review_accept_and_grow(self):
        image = self.upload("reference", "place.png", picture())
        clip = self.upload("video", "clip.mp4", self.video.read_bytes())
        lore = self.upload("lore", "lore.md", b"The archive never closes.")
        quote, started = self.harvest(world_id="salt", world_mode="create", world_images=[image], world_videos=[clip], world_lore=[lore],
                                      direction="keep it damp")
        started.raise_for_status()
        status = self.wait()
        self.assertEqual(status["state"], "complete", status)
        self.assertEqual(self.client.get("/api/worlds").json(), [])
        proposals = self.client.get("/api/worlds/proposals").json()
        self.assertEqual((proposals[0]["world_id"], proposals[0]["mode"], proposals[0]["base_version"]), ("salt", "create", 0))
        content = VisionMock.bodies[0]["messages"][0]["content"]
        self.assertEqual(len([part for part in content if part["type"] == "image_url"]), 1 + worlds.KEYFRAMES_PER_VIDEO)
        self.assertIn("The archive never closes.", content[0]["text"])
        self.assertIn("keep it damp", content[0]["text"])
        accepted = self.client.post(f"/api/worlds/proposals/{proposals[0]['id']}/accept")
        self.assertEqual(accepted.status_code, 200, accepted.text)
        world = accepted.json()
        self.assertEqual((world["version"], world["name"]), (1, "Mock World"))
        self.assertEqual({item["type"] for item in world["sources"]}, {"image", "video", "lore"})
        self.assertEqual(self.client.get("/api/worlds/proposals").json(), [])

        VisionMock.reply_text = json.dumps({**LEDGER, "name": "Mock World", "core_laws": LEDGER["core_laws"] + ["Nothing leaves unfiled"]})
        _, started = self.harvest(world_id="salt", world_mode="grow", world_images=[image])
        started.raise_for_status()
        self.assertEqual(self.wait()["state"], "complete")
        grow = self.client.get("/api/worlds/proposals").json()[0]
        self.assertIn("CURRENT LEDGER", VisionMock.bodies[-1]["messages"][0]["content"][0]["text"])
        added = [item for change in grow["changes"] for item in change["added"]]
        self.assertEqual(added, ["Nothing leaves unfiled"])
        self.assertEqual(self.client.get("/api/worlds/salt").json()["version"], 1)
        self.assertEqual(self.client.delete(f"/api/worlds/proposals/{grow['id']}").status_code, 200)
        self.assertEqual(self.client.get("/api/worlds/salt/versions").json()[0]["version"], 1)

    def test_growing_from_new_lore_adds_only_what_the_model_returns_and_echoing_adds_nothing(self):
        self.client.post("/api/worlds", json={"id": "salt", **LEDGER}).raise_for_status()
        lore = self.upload("lore", "backstory.txt", b"The Ink Warden keeps the wells under the registry.")

        def grow_proposal(reply):
            VisionMock.reply_text = json.dumps(reply)
            _, started = self.harvest(world_id="salt", world_mode="grow", world_lore=[lore], direction="add the wardens")
            started.raise_for_status()
            self.assertEqual(self.wait()["state"], "complete")
            listed = self.client.get("/api/worlds/proposals").json()[-1]
            proposal = self.client.get(f"/api/worlds/proposals/{listed['id']}").json()
            self.client.delete(f"/api/worlds/proposals/{listed['id']}").raise_for_status()
            return proposal

        echoed = grow_proposal(LEDGER)
        prompt = VisionMock.bodies[-1]["messages"][0]["content"][0]["text"]
        self.assertIn("Return ONLY what the new material adds", prompt)
        self.assertIn("The Ink Warden keeps the wells", prompt)
        self.assertEqual(echoed["changes"], [])
        grown = grow_proposal({"subjects": [{"designation": "the Ink Warden", "canon": "Keeps the wells under the registry"}],
                               "locations": ["The wells under the registry"]})
        self.assertEqual({item["field"] for item in grown["changes"]}, {"subjects", "locations"})
        self.assertEqual(grown["proposed"]["name"], "Salt Archive")
        self.assertEqual(grown["proposed"]["core_laws"], LEDGER["core_laws"])

    def test_the_edit_routes_preview_then_save_and_refuse_a_stale_or_foreign_edit(self):
        self.client.post("/api/worlds", json={"id": "salt", **LEDGER}).raise_for_status()
        edit = {**LEDGER, "core_laws": ["Ink is never dry"], "base_version": 1}
        self.assertEqual(self.client.put("/api/worlds/salt", json={**edit, "base_version": None}).status_code, 422)
        preview = self.client.post("/api/worlds/salt/edit-preview", json=edit)
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertIn("core_laws", [item["field"] for item in preview.json()["changes"]])
        self.assertEqual(self.client.get("/api/worlds/salt").json()["version"], 1)
        self.assertEqual(self.client.put("/api/worlds/salt", json={**edit, "id": "other"}).status_code, 400)
        saved = self.client.put("/api/worlds/salt", json=edit)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual((saved.json()["version"], saved.json()["core_laws"]), (2, ["Ink is never dry"]))
        self.assertEqual([item["version"] for item in self.client.get("/api/worlds/salt/versions").json()], [1, 2])
        self.assertEqual(self.client.put("/api/worlds/salt", json=edit).status_code, 400)
        self.assertEqual(self.client.put("/api/worlds/missing", json=edit).status_code, 400)

    def test_a_finished_run_can_seed_a_world(self):
        run = self.home / "runs" / "my_video"
        run.mkdir(parents=True)
        (run / "final.mp4").write_bytes(self.video.read_bytes())
        (run / "output.json").write_text(json.dumps({"file": "final.mp4", "duration": 4}))
        (run / "plan.json").write_text(json.dumps({"segments": [{"shots": [{"vocab": {"setting": "a basement archive", "lighting": "candlelight"}}]}]}))
        _, started = self.harvest(world_id="salt", world_mode="create", world_runs=["my_video"])
        started.raise_for_status()
        self.assertEqual(self.wait()["state"], "complete")
        content = VisionMock.bodies[0]["messages"][0]["content"]
        self.assertIn("a basement archive", content[0]["text"])
        self.assertEqual(len([part for part in content if part["type"] == "image_url"]), worlds.KEYFRAMES_PER_RUN)

    def test_two_finished_runs_with_the_same_file_name_each_supply_their_own_frames(self):
        for name, color in (("first", "red"), ("second", "blue")):
            run = self.home / "runs" / name
            run.mkdir(parents=True)
            subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={color}:s=64x48:r=24:d=2",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(run / "final.mp4")], check=True)
            (run / "output.json").write_text(json.dumps({"file": "final.mp4", "duration": 2}))
        _, started = self.harvest(world_id="salt", world_mode="create", world_runs=["first", "second"])
        started.raise_for_status()
        self.assertEqual(self.wait()["state"], "complete")
        images = [part["image_url"]["url"] for part in VisionMock.bodies[0]["messages"][0]["content"] if part["type"] == "image_url"]
        self.assertEqual(len(images), 2 * worlds.KEYFRAMES_PER_RUN)
        self.assertEqual(len(set(images)), 2)

    def test_harvest_requests_are_validated_and_always_need_consent(self):
        image = self.upload("reference", "place.png", picture())
        for fields in ({"world_id": "salt", "world_mode": "create"},
                       {"world_id": "salt", "world_mode": "grow", "world_images": [image]},
                       {"world_id": "salt", "world_mode": "create", "world_images": ["missing.png"]},
                       {"world_id": "salt", "world_mode": "create", "world_runs": ["nope"]},
                       {"world_mode": "create", "world_images": [image]}):
            self.assertEqual(self.harvest(**fields)[0].status_code, 400, fields)
        videos = [self.upload("video", f"c{n}.mp4", self.video.read_bytes()) for n in range(3)]
        too_many = self.harvest(world_id="salt", world_mode="create", world_videos=videos, world_images=[image])[0]
        self.assertEqual(too_many.status_code, 400)
        self.assertIn("at most 24", too_many.json()["detail"])
        quote = self.client.post("/api/quote", json={"kind": "world_harvest", "world_id": "salt", "world_mode": "create", "world_images": [image]})
        self.assertEqual(self.client.post("/api/start", json={"quote_id": quote.json()["id"], "consent": False}).status_code, 400)
        self.assertEqual(self.client.post("/api/upload/lore", files={"file": ("a.exe", b"x")}).status_code, 400)
        self.assertEqual(self.client.post("/api/upload/lore", files={"file": ("a.txt", b"x" * (worlds.LORE_BYTES + 1))}).status_code, 400)
        self.assertEqual(self.client.post("/api/upload/video", files={"file": ("a.txt", b"x")}).status_code, 400)

    def test_garbled_model_output_creates_no_proposal(self):
        image = self.upload("reference", "place.png", picture())
        VisionMock.reply_text = "I cannot help with that."
        _, started = self.harvest(world_id="salt", world_mode="create", world_images=[image])
        started.raise_for_status()
        self.assertEqual(self.wait()["state"], "failed")
        self.assertEqual(self.client.get("/api/worlds/proposals").json(), [])


if __name__ == "__main__":
    unittest.main()
