"""Local ComfyUI and WaveSpeed render clients for the public edition."""
from __future__ import annotations

import copy
import json
import math
import mimetypes
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from .jobs import Cancelled
from .storage import inside, write_json

# Provider documentation checked 2026-10-15; estimates are displayed, not guarantees.
CATALOG = {
    "local_h3": {"name": "Local H3 / ComfyUI", "rates": {}, "resolutions": ["768p"]},
    "wavespeed": {"name": "WaveSpeed H3", "path": "minimax/h3/reference-to-video",
                  "rates": {"768p": .10, "2k": .14}, "resolutions": ["768p", "2k"]},
    "seedance_2": {"name": "Seedance 2.0 / WaveSpeed", "path": "bytedance/seedance-2.0/text-to-video",
                   "rates": {"480p": .12, "720p": .24, "1080p": .60, "4k": 1.20},
                   "resolutions": ["480p", "720p", "1080p", "4k"]},
    "seedance_2_5": {"name": "Seedance 2.5 / WaveSpeed", "path": "bytedance/seedance-2.5/text-to-video",
                     "rates": {"480p": .18, "720p": .36, "1080p": .90, "4k": 1.80},
                     "resolutions": ["480p", "720p", "1080p", "4k"]},
}
BASE = "https://api.wavespeed.ai/api/v3"


def request_json(url, body=None, *, key="", timeout=30, raw=None, content_type=None):
    headers = {"Accept": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    data = raw
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    elif content_type:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.load(response)
        if not isinstance(result, dict):
            raise ValueError("Service returned an unexpected response")
        return result
    except urllib.error.HTTPError as exc:
        # Provider error bodies may echo prompts or credentials. Keep them out of logs.
        raise ValueError(f"Service rejected the request (HTTP {exc.code}); check its settings/dashboard") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ValueError("Service connection failed or timed out. A submitted remote job may still run; "
                         "check its dashboard before trying again") from None
    except json.JSONDecodeError:
        raise ValueError("Service did not return JSON") from None
