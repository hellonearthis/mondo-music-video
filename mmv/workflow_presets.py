"""Bundled H3 workflow choices: a Settings picker and the agent interface share this list."""
from __future__ import annotations

import json
from pathlib import Path

CONFIG = Path(__file__).parent / "engine/config"
PRESETS = (
    ("standard", "H3 standard (20 steps)", "injection_map.json"),
    ("fasth3_int8", "FastH3 Omni INT8 (8 steps)", "fasth3_omniref_int8_map.json"),
    ("fasth3_bf16", "FastH3 Omni BF16 (8 steps)", "fasth3_omniref_bf16_map.json"),
)
DEFAULT_STEPS = 20


def workflow_presets():
    return [{"id": key, "name": name, "path": str(CONFIG / file)} for key, name, file in PRESETS]


def preset_path(preset_id):
    match = next((p["path"] for p in workflow_presets() if p["id"] == preset_id), None)
    if match is None:
        raise ValueError("Unknown workflow preset; choose one of: " + ", ".join(k for k, _, _ in PRESETS))
    return match


def map_steps(map_path):
    """Sampler steps the selected workflow map asks for (20 unless it sets default_steps)."""
    try:
        return int(json.loads(Path(map_path).read_text()).get("default_steps", DEFAULT_STEPS))
    except (OSError, ValueError, TypeError):
        return DEFAULT_STEPS


def _diffusion_model(map_path):
    """The UNET a bundled workflow map's own graph loads, or None."""
    try:
        workflow = Path(json.loads(Path(map_path).read_text())["workflow"])
        graph = json.loads((workflow if workflow.is_absolute() else CONFIG.parent / workflow).read_text())
        return next((node["inputs"]["unet_name"] for node in graph.values() if node.get("class_type") == "UNETLoader"), None)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def preset_for_model(unet_name):
    """The bundled preset built for this diffusion model (its graph and step count), or None."""
    return next((p for p in workflow_presets() if _diffusion_model(p["path"]) == unet_name), None)
