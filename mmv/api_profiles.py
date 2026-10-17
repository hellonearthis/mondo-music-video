"""Private, named API configurations. Selecting a profile never calls a provider."""
from __future__ import annotations

from urllib.parse import urlsplit

from .storage import DEFAULTS, identifier, read_json, write_json

FIELDS = {
    "writer": ("writer_url", "writer_model", "writer_mode", "writer_call_estimate", "writer_launch"),
    "vision": ("vision_url", "vision_model", "vision_call_estimate"),
    "video": ("backend",),
}
KEYS = {"writer": "MMV_WRITER_API_KEY", "vision": "MMV_VISION_API_KEY", "video": "WAVESPEED_API_KEY"}


def records(store):
    return read_json(store.home / "api-profiles.json", {})


def public_profiles(store):
    return [{"name": name, "role": item["role"], "settings": item["settings"],
             "key_configured": bool(item.get("key"))}
            for name, item in sorted(records(store).items())]


def selected(store, settings, role):
    name = settings.get(role + "_api_profile", "")
    if not name:
        return None
    item = records(store).get(name)
    if not item or item["role"] != role:
        raise ValueError(f"Saved {role} API profile is missing or has a different role")
    return item


def resolve(store, settings):
    result = dict(settings)
    for role in FIELDS:
        item = selected(store, result, role)
        if item:
            result.update(item["settings"])
    return result


def save_settings(store, settings):
    """Retain manual settings so deselecting a profile restores the prior setup."""
    previous = {**DEFAULTS, **read_json(store.home / "settings.json", {})}
    result = dict(settings)
    for role, fields in FIELDS.items():
        selection = role + "_api_profile"
        if result.get(selection) or previous.get(selection):
            for field in fields:
                result[field] = previous[field]
    result.pop("h3_models", None)
    write_json(store.home / "settings.json", result)


def save_profile(store, name, role, config, key=""):
    identifier(name)
    if role not in FIELDS:
        raise ValueError("Choose writer, vision or video")
    if not isinstance(config, dict) or set(config) - set(FIELDS[role]):
        raise ValueError("Profile contains settings outside its selected role")
    # Use the public application's validation without making any network call.
    from webapp.mondo_web import Settings
    settings = Settings(**{**store.settings(), **config}).model_dump()
    if role in ("writer", "vision"):
        if not settings[role + "_model"]:
            raise ValueError("Choose a model before saving an API profile")
        url = urlsplit(settings[role + "_url"])
        if url.query or url.fragment:
            raise ValueError("API profile URLs cannot contain query parameters or fragments")
        if url.scheme == "http" and url.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError("Remote API profiles require HTTPS")
        if role == "writer":
            if settings["writer_mode"] != "api":
                raise ValueError("Writer API profiles require writer_mode=api")
            settings["writer_launch"] = ""
    elif settings["backend"] not in ("wavespeed", "seedance_2", "seedance_2_5"):
        raise ValueError("Choose a supported hosted video backend before saving a video API profile")
    if not isinstance(key, str) or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise ValueError("Invalid API key format")
    all_profiles = records(store)
    if name in all_profiles:
        raise ValueError("Profile name already exists; choose a new name to preserve the existing account")
    all_profiles[name] = {"role": role, "settings": {k: settings[k] for k in FIELDS[role]}, "key": key}
    write_json(store.home / "api-profiles.json", all_profiles, private=True)
    return next(p for p in public_profiles(store) if p["name"] == name)


def activate(store, name):
    item = records(store).get(name)
    if not item:
        raise ValueError("Unknown API profile")
    from webapp.mondo_web import Settings
    settings = store.settings()
    settings[item["role"] + "_api_profile"] = name
    settings = Settings(**resolve(store, settings)).model_dump()
    save_settings(store, settings)
    return {"name": name, "role": item["role"], "active": True}
