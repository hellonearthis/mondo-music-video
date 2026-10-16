"""Local agent client shared by the optional MCP server and the shell helper."""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("The local application redirected the request; verify MMV_URL")


class AgentClient:
    def __init__(self, base_url=None):
        parsed = urllib.parse.urlparse(base_url or os.environ.get("MMV_URL", "http://127.0.0.1:8091"))
        if (parsed.scheme not in ("http", "https") or parsed.hostname not in ("127.0.0.1", "localhost", "::1")
                or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
            raise ValueError("MMV_URL must be a localhost HTTP(S) URL without credentials, path or query")
        try:
            if parsed.port is not None and not 1 <= parsed.port <= 65535:
                raise ValueError("Invalid port")
        except ValueError:
            raise ValueError("MMV_URL has an invalid port") from None
        self.base = urllib.parse.urlunparse(parsed._replace(path="")).rstrip("/")
        # Never send local media or tool calls through an environment-configured proxy.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def _open(self, method, path, *, data=None, content_type=None, content_length=None):
        if not path.startswith("/api/") or ".." in path or "://" in path:
            raise ValueError("Unsupported application route")
        headers = {"Accept": "application/json"}
        if content_type:
            headers["Content-Type"] = content_type
        if content_length is not None:
            headers["Content-Length"] = str(content_length)
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            return self.opener.open(request, timeout=120)
        except urllib.error.HTTPError as exc:
            try:
                message = json.loads(exc.read()).get("detail", f"HTTP {exc.code}")
            except (ValueError, AttributeError):
                message = f"HTTP {exc.code}"
            raise ValueError(str(message)) from None
        except (urllib.error.URLError, TimeoutError):
            raise ValueError("Cannot reach Mondo Music Video. Start the local app and verify MMV_URL. "
                             "After a submission timeout, check status and saved request IDs before retrying.") from None

    def _json(self, method, path, payload=None):
        data = json.dumps(payload, allow_nan=False).encode() if payload is not None else None
        with self._open(method, path, data=data, content_type="application/json" if data is not None else None) as response:
            return json.load(response)

    def inspect(self, kind="status"):
        if kind not in ("status", "version", "catalog", "actors", "styles", "outputs", "settings"):
            raise ValueError("Unknown inspection kind")
        result = self._json("GET", "/api/" + kind)
        if kind == "outputs":
            for output in result:
                output["play_url"] = self.base + "/api/media/" + urllib.parse.quote(output["file"], safe="/")
        return result

    def preview(self, request):
        if not isinstance(request, dict) or request.get("kind", "video") not in ("video", "ident", "harvest"):
            raise ValueError("Preview requires a music video, ident or harvest request object")
        return self._json("POST", "/api/quote", request)

    def start(self, quote_id, consent=False):
        if consent is not True:
            raise ValueError("Review the preview and obtain user authorization before starting")
        return self._json("POST", "/api/start", {"quote_id": quote_id, "consent": True})

    def preview_resume(self, run_id):
        return self._json("POST", "/api/resume/quote", {"run_id": run_id})

    def cancel(self):
        return self._json("POST", "/api/cancel")

    def log(self, run_id):
        return self._json("GET", "/api/log/" + urllib.parse.quote(run_id, safe=""))

    def _multipart(self, route, fields, file_field=None, path=None):
        boundary = "mmvagent" + uuid.uuid4().hex
        head = b""
        for name, value in fields.items():
            head += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n").encode()
        if path is not None:
            path = Path(path).expanduser().resolve()
            if not path.is_file() or path.stat().st_size > 256 * 1024 * 1024:
                raise ValueError("Select an existing media file under 256 MB")
            filename = "media" + path.suffix
            head += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; "
                     f"filename=\"{filename}\"\r\nContent-Type: "
                     f"{mimetypes.guess_type(filename)[0] or 'application/octet-stream'}\r\n\r\n").encode()
        tail = ("\r\n" if path is not None else "") + f"--{boundary}--\r\n"
        tail = tail.encode()

        def chunks():
            yield head
            if path is not None:
                with path.open("rb") as stream:
                    while chunk := stream.read(1024 * 1024):
                        yield chunk
            yield tail

        length = len(head) + len(tail) + (path.stat().st_size if path is not None else 0)
        with self._open("POST", route, data=chunks(), content_type="multipart/form-data; boundary=" + boundary,
                        content_length=length) as response:
            return json.load(response)

    def upload(self, kind, path):
        if kind not in ("song", "reference", "oap"):
            raise ValueError("Choose song, reference or oap")
        return self._multipart("/api/upload/" + kind, {}, "file", path)

    def create_actor(self, actor_id, name, description, reference_path):
        return self._multipart("/api/actors", {"actor_id": actor_id, "name": name, "description": description},
                               "reference", reference_path)

    def create_style(self, style_id, name, direction):
        return self._json("POST", "/api/styles", {"id": style_id, "name": name, "direction": direction})

    def inspect_oap(self, filename, allow_unsigned=False):
        return self._json("GET", "/api/oap/inspect/" + urllib.parse.quote(filename, safe="") +
                          "?allow_unsigned=" + str(bool(allow_unsigned)).lower())

    def import_oap(self, filename, actor_id="", allow_unsigned=False, accept_unknown=False):
        return self._multipart("/api/oap/import", {"filename": filename, "actor_id": actor_id,
                               "allow_unsigned": str(bool(allow_unsigned)).lower(),
                               "accept_unknown": str(bool(accept_unknown)).lower()})

    def _save(self, method, route, destination):
        destination = Path(destination).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive create preserves existing files and gives each interrupted export a visible artifact.
        with destination.open("xb") as stream:
            try:
                with self._open(method, route) as response:
                    while chunk := response.read(1024 * 1024):
                        stream.write(chunk)
            except Exception:
                stream.close()
                if destination.stat().st_size == 0:
                    destination.unlink()
                raise
        return {"file": str(destination), "bytes": destination.stat().st_size}

    def download(self, output_file, destination):
        return self._save("GET", "/api/media/" + urllib.parse.quote(output_file, safe="/"), destination)

    def export_oap(self, actor_id, destination):
        return self._save("POST", "/api/actors/" + urllib.parse.quote(actor_id, safe="") + "/export", destination)

    def upscale(self, source, model="ahq-12", scale=2):
        return self._json("POST", "/api/upscale", {"source": source, "model": model, "scale": scale})


def main(argv=None):
    parser = argparse.ArgumentParser(description="Operate a running local Mondo Music Video app")
    parser.add_argument("--url", default=None, help="Local app URL (or MMV_URL)")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "version", "catalog", "actors", "styles", "outputs", "settings", "cancel"):
        sub.add_parser(name)
    upload = sub.add_parser("upload")
    upload.add_argument("kind", choices=("song", "reference", "oap"))
    upload.add_argument("path")
    preview = sub.add_parser("preview")
    preview.add_argument("request_file", help="JSON production request file")
    resume = sub.add_parser("preview-resume")
    resume.add_argument("run_id")
    start = sub.add_parser("start")
    start.add_argument("quote_id")
    start.add_argument("--consent", action="store_true")
    log = sub.add_parser("log")
    log.add_argument("run_id")
    download = sub.add_parser("download")
    download.add_argument("output_file")
    download.add_argument("destination")
    args = parser.parse_args(argv)
    try:
        client = AgentClient(args.url)
        if args.command == "upload":
            result = client.upload(args.kind, args.path)
        elif args.command == "preview":
            result = client.preview(json.loads(Path(args.request_file).read_text(encoding="utf-8")))
        elif args.command == "preview-resume":
            result = client.preview_resume(args.run_id)
        elif args.command == "start":
            result = client.start(args.quote_id, args.consent)
        elif args.command == "log":
            result = client.log(args.run_id)
        elif args.command == "download":
            result = client.download(args.output_file, args.destination)
        elif args.command == "cancel":
            result = client.cancel()
        else:
            result = client.inspect(args.command)
        print(json.dumps(result, indent=2, allow_nan=False))
    except (ValueError, OSError) as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
