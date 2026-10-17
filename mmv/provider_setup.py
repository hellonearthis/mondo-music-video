"""Explicit, read-only API discovery for installation agents."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward installation credentials to a different endpoint.
        return None


def inspect_writer(url, *, key_env=None):
    """GET only the supplied service's /models; never submit a generation."""
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme not in ("https", "http") or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("Use an HTTP(S) API base URL without credentials, query or fragment")
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("Remote API discovery requires HTTPS; HTTP is allowed only on loopback")
    # Validate malformed ports before issuing a request.
    try:
        parsed.port
    except ValueError:
        raise ValueError("Invalid API port") from None
    headers = {"Accept": "application/json"}
    if key_env:
        key = os.environ.get(key_env, "")
        if not key:
            raise ValueError("The named API key environment variable is empty or missing")
        if any(ord(c) < 33 or ord(c) > 126 for c in key):
            raise ValueError("Invalid API key format")
        headers["Authorization"] = "Bearer " + key
    endpoint = url.rstrip("/") + "/models"
    request = urllib.request.Request(endpoint, headers=headers, method="GET")
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=15) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("Model listing exceeds the 2 MiB discovery limit")
        payload = json.loads(raw)
    except urllib.error.HTTPError as exc:
        raise ValueError(f"Model discovery returned HTTP {exc.code}; check the base URL and credentials. "
                         "Redirects are not followed; no generation was submitted") from None
    except (OSError, urllib.error.URLError):
        raise ValueError("Model discovery could not connect; no generation was submitted") from None
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError("Model discovery did not return valid JSON") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("Expected an OpenAI-compatible model listing with a data array")
    ids = sorted({item["id"] for item in payload["data"]
                  if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]})
    if not ids:
        raise ValueError("The service did not advertise any model IDs")
    return {"base_url": url.rstrip("/"), "model_ids": ids,
            "generation_submitted": False, "inference_verified": False,
            "next_step": "Choose a chat-capable model using the provider documentation; configure "
                         "writer_url, writer_model, writer_mode=api and a per-call cost estimate. "
                         "A model listing does not verify chat or video compatibility."}
