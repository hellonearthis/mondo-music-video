"""One active operation, cancellable child processes, and durable status."""
from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
import uuid

from .storage import identifier, read_json, write_json


class BusyError(ValueError):
    pass


class Cancelled(Exception):
    pass


class JobContext:
    def __init__(self, manager, record):
        self.manager, self.record = manager, record
        self.cancelled = threading.Event()
        self.log_path = manager.store.home / "runs" / record["id"] / "operation.log"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def check(self):
        if self.cancelled.is_set():
            raise Cancelled("Operation cancelled. Remote work already submitted may still be billed.")

    def update(self, message, progress=None, **fields):
        with self.manager.lock:
            self.record.update(message=message, **fields)
            if progress is not None:
                self.record["progress"] = progress
            write_json(self.manager.status_path, self.record)
            with self.log_path.open("a", encoding="utf-8") as stream:
                stream.write(message + "\n")

    def wait(self, seconds):
        if self.cancelled.wait(seconds):
            self.check()

    def command(self, argv, *, env=None, progress_path=None):
        self.check()
        kwargs = {"start_new_session": True} if os.name != "nt" else {
            "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        proc_env = {**os.environ, **(env or {}), "PYTHONIOENCODING": "utf-8"}
        with self.log_path.open("ab") as log:
            process = subprocess.Popen([str(x) for x in argv], stdout=log,
                                       stderr=log, env=proc_env, **kwargs)
            try:
                last_progress = None
                while process.poll() is None:
                    if progress_path and progress_path.exists():
                        current_progress = read_json(progress_path)
                        if current_progress != last_progress:
                            self.update(**current_progress)
                            last_progress = current_progress
                    if self.cancelled.wait(0.2):
                        if os.name == "nt":
                            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                           capture_output=True, timeout=10)
                        else:
                            os.killpg(process.pid, signal.SIGTERM)
                        try:
                            process.wait(timeout=30)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                        self.check()
                if process.returncode:
                    raise ValueError("Media command failed; see the operation log")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
        self.check()


class Jobs:
    def __init__(self, store):
        self.store = store
        self.lock = threading.RLock()
        self.active = None
        self.worker = None
        self.status_path = store.home / "operation.json"
        self.last = read_json(self.status_path, {"state": "idle"})
        if self.last.get("state") in ("running", "cancelling"):
            self.last.update(state="interrupted", message="Application stopped during this operation. "
                             "Check remote request IDs before generating again.")
            write_json(self.status_path, self.last)

    def require_idle(self):
        if self.active is not None:
            raise BusyError("An operation is active. Wait or cancel it; work is never queued.")

    def status(self):
        with self.lock:
            return dict(self.last)

    def start(self, kind, function, *, run_id=None):
        with self.lock:
            self.require_idle()
            record = {"id": identifier(run_id) if run_id else uuid.uuid4().hex, "kind": kind, "state": "running",
                      "message": "Starting", "progress": 0, "started": time.time()}
            context = JobContext(self, record)
            self.active, self.last = context, record
            write_json(self.status_path, record)

            def worker():
                try:
                    result = function(context)
                    context.check()
                    context.update("Complete", 100, state="complete", result=result)
                except Cancelled as exc:
                    context.update(str(exc), state="cancelled")
                except Exception as exc:
                    # Avoid exposing response bodies or credentials from external services.
                    message = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
                    for name in ("WAVESPEED_API_KEY", "MMV_WRITER_API_KEY", "MMV_VISION_API_KEY", "MMV_COMFY_API_KEY"):
                        secret = self.store.key(name)
                        if secret:
                            message = message.replace(secret, "[redacted]")
                    context.update(message, state="failed")
                finally:
                    with self.lock:
                        record["finished"] = time.time()
                        write_json(self.store.home / "runs" / record["id"] / "operation.json", record)
                        write_json(self.status_path, record)
                        self.active = None

            self.worker = threading.Thread(target=worker, daemon=True)
            self.worker.start()
            return dict(record)

    def cancel(self):
        with self.lock:
            if self.active:
                self.active.cancelled.set()
                self.active.update("Cancellation requested", state="cancelling")
            return dict(self.last)

    def shutdown(self):
        self.cancel()
        if self.worker:
            self.worker.join(timeout=10)
