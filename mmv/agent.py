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

AGENT_SETTINGS = {
    "auto_updates", "backend", "writer_url", "writer_model", "writer_mode", "writer_call_estimate",
    "vision_url", "vision_model", "vision_call_estimate", "laya_model_dir", "laya_device", "h3_models",
    "writer_api_profile", "vision_api_profile", "video_api_profile", "comfy_url", "comfy_sdk_url",
}


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
        if kind not in ("status", "version", "catalog", "actors", "styles", "vocabularies", "vocabulary", "stems", "lyrics", "outputs", "settings", "update", "agreements"):
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

    def detect_lyrics(self, song, model="large-v3", use_vocals=True):
        """Start free local lyrics detection for an uploaded song; poll status, the lines arrive in its result."""
        return self._json("POST", "/api/lyrics/detect", {"song": song, "model": model, "use_vocals": bool(use_vocals)})

    def align_lyrics(self, song, text, model="large-v3"):
        """Time pasted lyric lines against a song that detect_lyrics has already listened to."""
        return self._json("POST", "/api/lyrics/align", {"song": song, "text": text, "model": model})

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
            filename = path.name if route == '/api/upload/song' else 'media' + path.suffix
            filename = filename.replace('"', '_').replace('\r', '_').replace('\n', '_').replace('\\', '_')
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
        if kind not in ("song", "reference", "oap", "agreement"):
            raise ValueError("Choose song, reference, oap or agreement")
        return self._multipart("/api/upload/" + kind, {}, "file", path)

    def create_actor(self, actor_id, name, description, reference_path):
        return self._multipart("/api/actors", {"actor_id": actor_id, "name": name, "description": description},
                               "reference", reference_path)

    def create_style(self, style_id, name, direction, style_card=None):
        payload = {"id": style_id, "name": name, "direction": direction}
        if style_card:
            payload["style_card"] = style_card
        return self._json("POST", "/api/styles", payload)

    def export_style(self, style_id, destination=None):
        path = "/api/styles/" + urllib.parse.quote(style_id, safe="") + "/export"
        with self._open("GET", path) as response:
            content = response.read()
        if destination is not None:
            dest = Path(destination)
            if dest.is_dir():
                dest = dest / f"{style_id}.json"
            dest.write_bytes(content)
            return {"saved": str(dest), "bytes": len(content)}
        return json.loads(content.decode("utf-8"))

    def import_style(self, style_id, name, direction, style_card=None, overwrite=False):
        payload = {
            "id": style_id,
            "name": name,
            "direction": direction,
            "overwrite": bool(overwrite),
        }
        if style_card:
            payload["style_card"] = style_card
        return self._json("POST", "/api/styles/import", payload)

    def save_vocabulary(self, vocab_id, name, tables, description="", base_profile="full"):
        return self._json("POST", "/api/vocabularies", {
            "id": vocab_id, "name": name, "description": description,
            "base_profile": base_profile, "tables": tables,
        })

    def delete_actor(self, actor_id, confirm=False):
        if confirm is not True:
            raise ValueError("Deleting an actor requires explicit user authorization; set confirm only after that authorization")
        return self._json("DELETE", "/api/actors/" + urllib.parse.quote(actor_id, safe=""))

    def delete_style(self, style_id, confirm=False):
        if confirm is not True:
            raise ValueError("Deleting a style requires explicit user authorization; set confirm only after that authorization")
        return self._json("DELETE", "/api/styles/" + urllib.parse.quote(style_id, safe=""))

    def delete_vocabulary(self, vocab_id, confirm=False):
        if confirm is not True:
            raise ValueError("Deleting a vocabulary preset requires explicit user authorization; set confirm only after that authorization")
        return self._json("DELETE", "/api/vocabularies/" + urllib.parse.quote(vocab_id, safe=""))

    def select_api_profile(self, name):
        return self._json("POST", "/api/api-profiles/" + urllib.parse.quote(name, safe="") + "/activate")

    def add_api_profile(self, name, role, settings, key_env=""):
        payload = {"name": name, "role": role, "settings": settings}
        if key_env:
            key = os.environ.get(key_env, "")
            if not key:
                raise ValueError("The named API key environment variable is empty or missing")
            if len(key) > 1000 or any(ord(c) < 33 or ord(c) > 126 for c in key):
                raise ValueError("Invalid API key format")
            payload["key"] = key
        return self._json("POST", "/api/api-profiles", payload)

    def remove_api_profile(self, name, confirm=False):
        if confirm is not True:
            raise ValueError("Removing an API profile and stored key requires explicit user authorization")
        return self._json("DELETE", "/api/api-profiles/" + urllib.parse.quote(name, safe=""))

    def update_settings(self, changes):
        if not isinstance(changes, dict) or set(changes) - AGENT_SETTINGS:
            raise ValueError("Use supported service/model/profile/update preferences; executable commands and credentials require setup or the GUI")
        return self._json("PATCH", "/api/settings", changes)

    def install_starter_assets(self, accept_starter_signer=False, restore_removed=False):
        return self._json("POST", "/api/starter-assets", {
            "accept_starter_signer": accept_starter_signer, "restore_removed": restore_removed})

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

    def export_oap(self, actor_id, destination, tier="full", reference_clearance="cast"):
        query = urllib.parse.urlencode({"tier": tier, "reference_clearance": reference_clearance})
        return self._save("POST", "/api/actors/" + urllib.parse.quote(actor_id, safe="") + "/export?" + query, destination)

    def create_agreement(self, actor_id, agreement_id, title, offer, currency, character="",
                         role_description="", content=None, notes=""):
        payload = {"actor_id": actor_id, "agreement_id": agreement_id, "title": title, "offer": offer,
                   "currency": currency, "character": character, "role_description": role_description,
                   "notes": notes}
        if content is not None:
            payload["content"] = content
        return self._json("POST", "/api/agreements", payload)

    def sign_agreement(self, agreement_id, role, confirm=False):
        if not confirm:
            raise ValueError("Signing a role agreement commits this studio to its terms; obtain explicit user "
                             "authorization for this agreement and role, then set confirm")
        return self._json("POST", "/api/agreements/" + urllib.parse.quote(agreement_id, safe="") + "/sign",
                          {"role": role})

    def verify_agreement(self, agreement_id):
        return self._json("GET", "/api/agreements/" + urllib.parse.quote(agreement_id, safe="") + "/verify")

    def export_agreement(self, agreement_id, destination):
        return self._save("POST", "/api/agreements/" + urllib.parse.quote(agreement_id, safe="") + "/bundle",
                          destination)

    def import_agreement(self, filename):
        return self._multipart("/api/agreements/import", {"filename": filename})

    def music_score(self, output_file):
        run_id = str(output_file).split("/")[0]
        return self._json("GET", "/api/outputs/" + urllib.parse.quote(run_id, safe="") + "/score")

    def export_package(self, run_id, zip_it=False, allow_private_actors=False):
        """Copy a finished production into an editing package under the app's data folder (never published)."""
        return self._json("POST", "/api/outputs/" + urllib.parse.quote(run_id, safe="") + "/package",
                          {"zip": bool(zip_it), "allow_private_actors": bool(allow_private_actors)})

    def caption_fonts(self):
        return self._json("GET", "/api/captions/fonts")

    def caption_video(self, source, lyric_lines=None, style="classic", position="bottom", size="medium",
                      color="", outline_color="", font=""):
        return self._json("POST", "/api/captions", {"source": source, "lyric_lines": lyric_lines or [], "style": style,
                                                    "position": position, "size": size, "color": color,
                                                    "outline_color": outline_color, "font": font})

    def upscale(self, source, model="ahq-12", scale=2):
        return self._json("POST", "/api/upscale", {"source": source, "model": model, "scale": scale})


def main(argv=None):
    parser = argparse.ArgumentParser(description="Operate a running local Mondo Music Video app")
    parser.add_argument("--url", default=None, help="Local app URL (or MMV_URL)")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "version", "catalog", "actors", "styles", "vocabularies", "vocabulary", "stems", "lyrics", "outputs", "settings", "update", "agreements", "cancel"):
        sub.add_parser(name)
    upload = sub.add_parser("upload")
    upload.add_argument("kind", choices=("song", "reference", "oap", "agreement"))
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
    for name in ("delete-actor", "delete-style", "delete-vocabulary"):
        delete = sub.add_parser(name)
        delete.add_argument("id")
        delete.add_argument("--confirm", action="store_true")
    profile = sub.add_parser("select-api-profile")
    profile.add_argument("name")
    download = sub.add_parser("download")
    download.add_argument("output_file")
    download.add_argument("destination")
    export_style = sub.add_parser("export-style")
    export_style.add_argument("id")
    export_style.add_argument("--destination", default=None)
    import_style = sub.add_parser("import-style")
    import_style.add_argument("file", help="Path to style JSON file")
    import_style.add_argument("--overwrite", action="store_true")
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
        elif args.command == "delete-actor":
            result = client.delete_actor(args.id, args.confirm)
        elif args.command == "delete-style":
            result = client.delete_style(args.id, args.confirm)
        elif args.command == "delete-vocabulary":
            result = client.delete_vocabulary(args.id, args.confirm)
        elif args.command == "select-api-profile":
            result = client.select_api_profile(args.name)
        elif args.command == "export-style":
            result = client.export_style(args.id, args.destination)
        elif args.command == "import-style":
            data = json.loads(Path(args.file).read_text(encoding="utf-8"))
            result = client.import_style(
                data["id"],
                data["name"],
                data["direction"],
                style_card=data.get("style_card"),
                overwrite=args.overwrite,
            )
        else:
            result = client.inspect(args.command)
        print(json.dumps(result, indent=2, allow_nan=False))
    except (ValueError, OSError) as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
