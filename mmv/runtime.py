"""Original music-pipeline service lifecycle with portable, user-owned launches.

Only processes launched by this production are stopped. Existing services are
left under their operator's control; no studio preemption or port killing.
"""
import os, signal, subprocess, time, urllib.request, json
from pathlib import Path
processes = []
open_files = []

def http_ok(url, timeout=3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False

def wait_http(url, timeout=900, interval=2):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if http_ok(url):
            return True
        time.sleep(interval)
    return False

def start_process(cmd, cwd=None, log=None):
    if log:
        log.parent.mkdir(parents=True, exist_ok=True)
        f = open(log, "ab")
        open_files.append(f)
        out = f
    else:
        out = subprocess.DEVNULL
    p = subprocess.Popen(
        [str(x) for x in cmd],
        cwd=str(cwd) if cwd else None,
        stdout=out,
        stderr=out,
        **({"start_new_session":True} if os.name != "nt" else {"creationflags":subprocess.CREATE_NEW_PROCESS_GROUP}),
    )
    processes.append(p)
    return p

def stop_process(p):
    if p is None:
        return
    if p.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill","/PID",str(p.pid),"/T","/F"],capture_output=True,timeout=10)
        else:
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
    except Exception:
        pass
    try:
        p.wait(timeout=20)
    except Exception:
        try:
            if os.name == "nt": p.kill()
            else: os.killpg(os.getpgid(p.pid), signal.SIGKILL)
        except Exception:
            pass

def cleanup():
    for p in processes:
        stop_process(p)
    for f in open_files:
        try:
            f.close()
        except Exception:
            pass


def start_service(command_json, cwd, health_url, log):
    if http_ok(health_url):
        return None
    if not command_json:
        raise ValueError("Service is not running: " + health_url + ". Configure its launch command or start it before production.")
    command = json.loads(command_json)
    if not isinstance(command,list) or not command or any(not isinstance(x,str) or not x for x in command):
        raise ValueError("Service launch must be a JSON array of command arguments")
    process = start_process(command,cwd=cwd or None,log=log)
    deadline = time.time()+900
    while time.time()<deadline:
        if process.poll() is not None:
            raise ValueError("AI service stopped during startup; see " + str(log))
        if http_ok(health_url): return process
        time.sleep(2)
    stop_process(process)
    raise ValueError("AI service startup timed out; see " + str(log))
