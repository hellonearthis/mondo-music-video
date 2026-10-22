import json
import unittest
from pathlib import Path

from mmv.engine.comfy import WorkflowBuilder
from mmv.workflow_presets import map_steps, preset_path, workflow_presets

ENGINE = Path(__file__).resolve().parent.parent / "mmv/engine"
EXPECTED = {
    "fasth3_int8": ("fasth3_omniref_8step_pruned_int8_convrot.safetensors",
                    "qwen3vl_32b_h3_ultra_uncensored_heretic_int8_convrot.safetensors"),
    "fasth3_bf16": ("fasth3_omniref_8step_pruned_bf16.safetensors",
                    "qwen3vl_32b_h3_ultra_uncensored_heretic_bf16.safetensors"),
}


class WorkflowPresetTests(unittest.TestCase):
    def test_presets_build_with_expected_models_and_steps(self):
        for key, (unet, clip) in EXPECTED.items():
            path = preset_path(key)
            self.assertEqual(map_steps(path), 8)
            graph, _ = WorkflowBuilder.load(path, ENGINE).build(
                prompt="p", duration_input=8, seed=1, width=896, height=704,
                image_files=["a.png"], audio_files=["s.wav"], steps=map_steps(path))
            nodes = {n["class_type"]: n["inputs"] for n in graph.values()}
            self.assertEqual(nodes["UNETLoader"]["unet_name"], unet)
            self.assertEqual(nodes["CLIPLoader"]["clip_name"], clip)
            self.assertEqual(nodes["BasicScheduler"]["steps"], 8)
            self.assertFalse(any("Lora" in n["class_type"] for n in graph.values()))
            for node in graph.values():
                for value in node["inputs"].values():
                    if isinstance(value, list):
                        self.assertIn(str(value[0]), graph)

    def test_standard_stays_twenty_steps(self):
        self.assertEqual(map_steps(preset_path("standard")), 20)
        self.assertEqual(len(workflow_presets()), 3)
        with self.assertRaises(ValueError):
            preset_path("nope")


if __name__ == "__main__":
    unittest.main()
