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


def safe_endpoint(value):
    from urllib.parse import urlsplit, urlunsplit
    url = urlsplit(value)
    return urlunsplit((url.scheme, url.netloc.rsplit("@", 1)[-1], url.path, "", ""))


def identify_service(health_url=None, log=None, command_json=None):
    url_lower = str(health_url or "").lower()
    log_lower = str(log or "").lower()
    cmd_lower = str(command_json or "").lower()
    if "8188" in url_lower or "system_stats" in url_lower or "comfy" in url_lower or "comfy" in log_lower or "comfy" in cmd_lower:
        return "ComfyUI", "comfy_launch"
    if "vision" in url_lower or "vision" in log_lower or "vision" in cmd_lower:
        return "Vision service", "vision_url"
    if "laya" in url_lower or "laya" in log_lower or "laya" in cmd_lower:
        return "Laya", "laya_model_dir"
    if "8080" in url_lower or "8081" in url_lower or "models" in url_lower or "writer" in url_lower or "llama" in url_lower or "writer" in log_lower or "llama" in cmd_lower:
        return "llama.cpp (Writer)", "writer_launch"
    return "Service", "launch command"


def start_service(command_json, cwd, health_url, log, name=None, launch_setting=None):
    if http_ok(health_url):
        return None
    detected_name, detected_setting = identify_service(health_url, log, command_json)
    service_name = name or detected_name
    setting_name = launch_setting or detected_setting

    if not command_json:
        setting_hint = f" ({setting_name})" if setting_name and setting_name != "launch command" else ""
        raise ValueError(f"{service_name} service is not running: {safe_endpoint(health_url)}. Configure its launch command{setting_hint} or start it before production.")
    try:
        command = json.loads(command_json)
    except (ValueError, TypeError):
        raise ValueError(f"{service_name} launch ({setting_name}) must be a JSON array of command arguments") from None
    if not isinstance(command,list) or not command or any(not isinstance(x,str) or not x for x in command):
        setting_hint = f" ({setting_name})" if setting_name and setting_name != "launch command" else ""
        raise ValueError(f"{service_name} launch{setting_hint} must be a JSON array of command arguments")
    process = start_process(command,cwd=cwd or None,log=log)
    deadline = time.time()+900
    while time.time()<deadline:
        if process.poll() is not None:
            raise ValueError(f"{service_name} stopped during startup; see " + str(log))
        if http_ok(health_url): return process
        time.sleep(2)
    stop_process(process)
    raise ValueError(f"{service_name} startup timed out; see " + str(log))
