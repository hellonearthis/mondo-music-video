"""Topaz Labs cloud video API (api.topazlabs.com): free estimate, then reserve, upload, poll and download.

Every network call goes through an injected `send(method, url, headers, body)` -> (status, headers, bytes), so
tests use a mock and the real transports (`send_http`, `download_http`) are the only code that touches the network."""
import ipaddress
import json
import math
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_URL = "https://api.topazlabs.com"
SEGMENT = 500_000_000
AGENT = {"User-Agent": "mondo-music-video (Topaz cloud client)"}  # Topaz refuses the default Python agent (403)
FAILED = ("failed", "canceled")
HINTS = {401: "check the Topaz API key", 402: "not enough Topaz credits", 413: "the video is too large"}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # never forward the API key to another host


def send_http(method, url, headers, body, timeout=300):
    request = urllib.request.Request(url, data=body, headers={**AGENT, **headers}, method=method)
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()
    except (OSError, urllib.error.URLError) as exc:
        raise ValueError("Topaz cloud service could not be reached") from exc


def download_http(url, destination, timeout=300):
    """Stream the finished video to disk; the signed URL belongs to storage, so no API key is sent."""
    request = urllib.request.Request(url, headers=AGENT, method="GET")
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout) as response, \
                Path(destination).open("wb") as out:
            while chunk := response.read(1 << 20):
                out.write(chunk)
    except (OSError, urllib.error.URLError) as exc:
        raise ValueError("Could not download the finished video from Topaz") from exc


class Slice:
    """A bounded, streaming view of a file for one PUT, so a large video is never held in memory."""
    def __init__(self, stream, start, end):
        stream.seek(start)
        self.stream, self.length, self.left = stream, end - start, end - start

    def read(self, count=-1):
        count = self.left if count is None or count < 0 else min(count, self.left)
        data = self.stream.read(count)
        self.left -= len(data)
        return data

    def __len__(self):
        return self.length


def safe_url(url):
    """Only public HTTPS storage URLs: a response can never point uploads or downloads at local services."""
    parsed = urllib.parse.urlsplit(str(url))
    host = parsed.hostname or ""
    try:
        private = not ipaddress.ip_address(host).is_global
    except ValueError:
        private = host == "localhost" or host.endswith((".local", ".internal", ".localhost")) or "." not in host
    if parsed.scheme != "https" or not host or private or parsed.username:
        raise ValueError("Topaz returned an unsafe transfer address; nothing was sent to it")
    return url


def endpoint(base):
    base = (base or API_URL).rstrip("/")
    if not base.startswith("https://") and not base.startswith(("http://127.0.0.1", "http://localhost")):
        raise ValueError("Topaz API URL must use HTTPS")
    return base


def rounded(value):
    return int(math.ceil(value / 4) * 4)


def filters(model, options):
    """The request's filter list: an upscale/enhance model with optional tuning, then optional interpolation."""
    chosen = []
    if model != "none":
        mode = options.get("mode", "Auto")
        chosen.append({"model": model, **({"auto": mode, **options.get("tuning", {})} if mode != "Auto" else {})})
    motion = options.get("interpolation")
    if motion:
        chosen.append({"model": motion["model"], **{k: motion[k] for k in ("fps", "slowmo", "duplicate") if motion.get(k)}})
    if not chosen:
        raise ValueError("Choose an upscale model, a frame interpolation model, or both")
    return chosen


def request_body(info, model, scale, options=None):
    options = options or {}
    chosen = filters(model, options)
    scale = scale if model != "none" else 1
    width, height = rounded(info["width"] * scale), rounded(info["height"] * scale)
    rate = max([info["frame_rate"]] + [f["fps"] for f in chosen if f.get("fps")])
    audio = {"audioTransfer": "Copy", "audioCodec": "AAC"} if info["has_audio"] else {"audioTransfer": "None"}
    encoder = ({"videoEncoder": "H264", "videoProfile": "High"} if max(width, height) <= 4096
               else {"videoEncoder": "H265", "videoProfile": "Main"})
    return {"source": {"container": "mp4", "size": info["size"], "duration": info["duration"],
                       "frameCount": info["frame_count"], "frameRate": info["frame_rate"],
                       "resolution": {"width": info["width"], "height": info["height"]}},
            "filters": chosen,
            "output": {"resolution": {"width": width, "height": height}, "frameRate": rate,
                       "container": "mp4", **encoder, **audio}}


def live_models(send, base):
    """Models Topaz accepts right now (public, free, no key); None when the service cannot say."""
    try:
        status, _, raw = send("GET", endpoint(base) + "/video/status", {"Accept": "application/json"}, None)
        models = json.loads(raw).get("supportedModels") if status < 400 else None
        return [m for m in models if isinstance(m, str)] if isinstance(models, list) else None
    except (ValueError, AttributeError):
        return None


def call(send, base, key, method, path, payload=None):
    headers = {"X-API-Key": key, "Accept": "application/json"}
    body = None if payload is None else json.dumps(payload).encode()
    if body is not None:
        headers["Content-Type"] = "application/json"
    status, _, raw = send(method, endpoint(base) + path, headers, body)
    try:
        value = json.loads(raw) if raw else {}
    except ValueError:
        value = {}
    if status >= 400:
        detail = str(value.get("message") or value.get("error") or "")[:200].replace(key, "[redacted]") \
            if isinstance(value, dict) else ""
        raise ValueError(f"Topaz cloud service refused the request (HTTP {status}{': ' + detail if detail else ''}); "
                         f"{HINTS.get(status, 'check the details above')}")
    return value


def estimate(send, base, key, info, model, scale, options=None):
    """Create a request. Free: nothing is reserved or processed until it is accepted."""
    body = request_body(info, model, scale, options)
    created = call(send, base, key, "POST", "/video/", body)
    cost, seconds = created["estimates"]["cost"], created["estimates"]["time"]
    return {"request_id": created["requestId"], "credits": [cost[0], cost[1]], "seconds": [seconds[0], seconds[1]],
            "output": body["output"]["resolution"], "frame_rate": body["output"]["frameRate"]}


def segments(size, count):
    """Byte ranges for a multi-part upload: one 500 MB segment per URL, larger when the URL cap binds."""
    step = max(SEGMENT, math.ceil(size / count))
    return [(i * step, min(size, (i + 1) * step)) for i in range(count)]


def upload(send, urls, path, size, check=lambda: None):
    """PUT the file to the issued URLs; returns the [{partNum, eTag}] list the completion call needs."""
    spans = [(0, size)] if len(urls) == 1 else segments(size, len(urls))
    results = []
    with Path(path).open("rb") as stream:
        for number, (url, (start, end)) in enumerate(zip(urls, spans), 1):
            check()
            body = Slice(stream, start, end)
            status, headers, _ = send("PUT", safe_url(url), {"Content-Type": "video/mp4", "Content-Length": str(len(body))}, body)
            if status >= 300:
                raise ValueError(f"Upload of part {number} failed (HTTP {status})")
            tag = {k.lower(): v for k, v in headers.items()}.get("etag", "")
            results.append({"partNum": number, "eTag": tag if len(urls) > 1 else "unused"})
    return results


def describe(status):
    """A plain status line: Topaz's own message ("Queued - waiting for resources"), progress and its time estimate."""
    state, percent = status.get("status", ""), round(status.get("progress") or 0)
    text = status.get("message") or state.capitalize()
    seconds = (status.get("estimates") or {}).get("time") or []
    minutes = f", about {max(1, round(seconds[-1] / 60))} min once running" if seconds and percent == 0 else ""
    return f"{text} ({percent}%{minutes})"


def wait_complete(send, base, key, request_id, context, *, interval, limit):
    """Poll status until complete; returns the signed download URL. Read-only, so polling never costs credits."""
    waited, last = 0, None
    while True:
        context.check()
        status = call(send, base, key, "GET", f"/video/{request_id}/status")
        state, percent = status.get("status", ""), round(status.get("progress") or 0)
        if state == "complete":
            return status["download"]["url"]
        if state in FAILED:
            raise ValueError(f"Topaz {state}: {status.get('errorCode') or status.get('message') or 'no reason given'}")
        shown = f"Topaz cloud: {describe(status)}"
        if shown != last:
            context.update(shown, min(95, 15 + round(percent * 0.8)))
            last = shown
        if limit and waited >= limit:
            raise ValueError("Topaz cloud processing exceeded the configured time limit")
        context.wait(interval)
        waited += interval


def run(send, fetch, base, key, source, destination, info, model, scale, max_credits, context, *, interval=5, limit=0,
        options=None):
    """Estimate again, refuse if dearer than approved, then reserve, upload, process and download.

    The reservation (accept) is the only paid step and is never retried. Any failure before the result is ready
    asks Topaz to cancel so unused credits are refunded; the request id is logged for a manual cancel."""
    quote = estimate(send, base, key, info, model, scale, options)
    request_id, credits = quote["request_id"], quote["credits"]
    if credits[1] > max_credits:
        raise ValueError(f"Topaz now estimates {credits[0]}-{credits[1]} credits, more than the {max_credits} you "
                         "approved. Nothing was reserved; review the new estimate and approve again")
    context.update(f"Reserving up to {credits[1]} Topaz credits (request {request_id})", 10)
    try:
        accepted = call(send, base, key, "PATCH", f"/video/{request_id}/accept")
        context.update("Uploading to Topaz cloud", 12)
        results = upload(send, accepted["urls"], source, info["size"], context.check)
        call(send, base, key, "PATCH", f"/video/{request_id}/complete-upload", {"uploadResults": results})
        url = wait_complete(send, base, key, request_id, context, interval=interval, limit=limit)
    except BaseException:
        context.update(f"Stopping; asking Topaz to cancel request {request_id} and refund unused credits")
        try:
            call(send, base, key, "DELETE", f"/video/{request_id}")
        except ValueError as exc:
            context.update(f"Cancel request failed ({exc}); cancel {request_id} in the Topaz account if needed")
        raise
    context.update(f"Downloading the upscaled video (Topaz request {request_id}, kept 7 days)", 96)
    fetch(safe_url(url), destination)
    return {"request_id": request_id, "credits": credits}
