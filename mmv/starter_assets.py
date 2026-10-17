"""Install only the expressly public starter assets, without replacing user work."""
from __future__ import annotations

import hashlib
import json
import sysconfig
from pathlib import Path

from . import actors
from .storage import identifier, read_json, write_json

ACTORS = ("animal_pig", "robobabe1", "henchman_1", "human_female_casual_01")
STYLES = ("sun_bleach", "nature_doc", "industrial_decay", "noir_bw", "gel_wash_psych", "crt_1990s")
SIGNER = "zeWRTBjOgu5KkU685MyeZ8WKp5etnzZW9f99pRcODIk"


def removed(store):
    return read_json(store.home / "removed-assets.json", {"actors": [], "styles": []})


def mark_removed(store, kind, asset_id):
    state = removed(store)
    state.setdefault(kind, [])
    if asset_id not in state[kind]:
        state[kind].append(asset_id)
    write_json(store.home / "removed-assets.json", state, private=True)


def asset_directory():
    checkout = Path(__file__).resolve().parent.parent / "examples"
    installed = Path(sysconfig.get_path("data")) / "share/mondo-music-video/examples"
    for root in (checkout, installed):
        if (root / "starter-cast/manifest.json").is_file() and (root / "style-presets/manifest.json").is_file():
            return root
    raise ValueError("Bundled starter assets are missing; reinstall from the official source or wheel")


def install(store, *, accept_signer=False, restore=False, root=None):
    root = Path(root) if root is not None else asset_directory()
    prepared = []
    actor_packages = []
    # Check the complete allowlisted bundle before changing any user assets.
    for kind, folder, allowed, suffix in (
        ("actors", "starter-cast", ACTORS, ".oap"),
        ("styles", "style-presets", STYLES, ".json"),
    ):
        directory = root / folder
        entries = read_json(directory / "manifest.json")[kind]
        if len(entries) != len(allowed) or {e["id"] for e in entries} != set(allowed):
            raise ValueError("Starter manifest does not match the public asset allowlist")
        for entry in entries:
            asset_id = identifier(entry["id"])
            if entry["file"] != asset_id + suffix:
                raise ValueError("Unexpected starter asset filename")
            source = directory / entry["file"]
            data = source.read_bytes()
            if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise ValueError("Starter asset checksum failed: " + asset_id)
            if kind == "actors":
                manifest, verification = actors.package_info(source)
                if (not verification.get("signature_valid") or manifest["agent"].get("public_key") != SIGNER
                        or manifest["identity"]["actor_id"] != asset_id):
                    raise ValueError("Unexpected starter actor identity or signer")
                actor_packages.append({"id": asset_id, "name": manifest["identity"].get("display_name", asset_id),
                                       "signer": SIGNER, "rider": manifest.get("rider", {})})
            else:
                style = json.loads(data)
                if style.get("id") != asset_id or not style.get("name") or not style.get("direction"):
                    raise ValueError("Invalid starter style")
            prepared.append((kind, asset_id, source, data))
    state = removed(store)
    style_ids = {read_json(path, {}).get("id") for path in (store.home / "styles").glob("*.json")}
    report = {"installed": [], "preserved": [], "removed": [], "pending_signer": []}
    report["starter_signer"] = SIGNER
    report["actor_packages"] = actor_packages
    for kind, asset_id, source, data in prepared:
        label = kind + "/" + asset_id
        target = store.home / kind / (asset_id if kind == "actors" else asset_id + ".json")
        if target.exists() or target.is_symlink() or (kind == "styles" and asset_id in style_ids):
            report["preserved"].append(label)
        elif not restore and asset_id in state.get(kind, []):
            report["removed"].append(label)
        elif kind == "actors" and not accept_signer:
            report["pending_signer"].append(label)
        else:
            if kind == "actors":
                actors.import_actor(store, source, asset_id, accept_unknown=True)
            else:
                with target.open("xb") as stream:
                    stream.write(data)
            report["installed"].append(label)
            if restore and asset_id in state.get(kind, []):
                state[kind].remove(asset_id)
    if restore:
        write_json(store.home / "removed-assets.json", state, private=True)
    return report
