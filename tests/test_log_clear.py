import tempfile, unittest
from pathlib import Path

from fastapi.testclient import TestClient

from webapp.mondo_web import create_app


class LogClearTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.app = create_app(self.home, test_hosts=True)
        self.client = TestClient(self.app)
        self.run = self.home / "runs" / "active_run"
        self.run.mkdir(parents=True)

    def set_state(self, state):
        self.app.state.jobs.last = {"id": "active_run", "state": state}

    def log(self):
        return self.client.get("/api/log/active_run").json()["log"]

    def test_clear_during_run_hides_old_output_and_survives_completion(self):
        (self.run / "operation.log").write_text("before clear\n")
        (self.run / "writer-service.log").write_text("old writer line\n")
        self.set_state("running")
        self.assertIn("before clear", self.log())
        self.client.post("/api/log/clear")
        self.assertNotIn("before clear", self.log())
        self.assertNotIn("old writer line", self.log())
        with (self.run / "operation.log").open("a") as f:
            f.write("after clear\n")
        self.assertIn("after clear", self.log())
        self.assertNotIn("before clear", self.log())
        self.set_state("succeeded")
        (self.run / "operation.json").write_text('{"state": "succeeded"}')
        self.assertIn("after clear", self.log())
        self.assertNotIn("before clear", self.log())

    def test_old_validation_reports_stay_hidden_after_clear(self):
        report = self.run / "seg000.validation-1.json"
        report.write_text('{"errors": ["old problem"]}')
        self.set_state("running")
        self.client.post("/api/log/clear")
        self.assertNotIn("old problem", self.log())


if __name__ == "__main__":
    unittest.main()
