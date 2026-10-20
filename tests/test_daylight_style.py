import json
import tempfile
import unittest
from pathlib import Path

from mmv.storage import DEFAULT_STYLE, LEGACY_DEFAULT_STYLE, Storage, write_json

AXES = ("INK ECONOMY", "TONAL STRUCTURE", "SURFACE", "EDGE BEHAVIOUR", "LIGHT LOGIC", "DEPTH STRATEGY",
        "COMPOSITION GRAMMAR", "SCALE RELATIONSHIP", "PROVENANCE MARKERS", "TYPOGRAPHY", "MOTION IMPLICATION")


class DaylightStyleContent(unittest.TestCase):
    def test_fits_style_api_bounds(self):
        self.assertRegex(DEFAULT_STYLE["id"], r"^[a-z0-9][a-z0-9_-]{0,63}$")
        self.assertTrue(1 <= len(DEFAULT_STYLE["name"]) <= 160)
        self.assertTrue(1 <= len(DEFAULT_STYLE["direction"]) <= 8000)
        self.assertLessEqual(len(DEFAULT_STYLE["style_card"]), 16000)
        self.assertEqual(set(DEFAULT_STYLE), {"id", "name", "direction", "style_card"})

    def test_card_covers_all_eleven_axes(self):
        card = DEFAULT_STYLE["style_card"]
        for number, axis in enumerate(AXES, 1):
            self.assertIn(f"{number} {axis}:", card)

    def test_direction_has_sections_of_public_presets(self):
        direction = DEFAULT_STYLE["direction"]
        for heading in ("TONAL STRUCTURE", "SURFACE.", "EDGE BEHAVIOUR.", "LIGHT LOGIC.", "DEPTH STRATEGY.",
                        "COMPOSITION GRAMMAR.", "PROVENANCE MARKERS.", "MOTION IMPLICATION.", "ANTI-TROPE MANDATE.",
                        "CAMERA AND FRAMING.", "CONTENT BOUNDARY."):
            self.assertIn(heading, direction)
        self.assertTrue(direction.startswith("Aesthetic directives"))
        for heading in ('FREE AXES:', 'BORROWABLE MOTIFS:'):
            self.assertIn(heading, DEFAULT_STYLE['style_card'])
        self.assertNotIn('SUBJECT RIGGING', direction)
        self.assertNotIn('lip-sync hallucinations', direction)

    def test_keeps_character_and_content_bounds(self):
        direction = DEFAULT_STYLE["direction"].lower()
        for word in ("natural light", "rich", "clear", "rhythmic", "fully clothed", "no nudity", "sexual imagery", "blood", "violence"):
            self.assertIn(word, direction)

    def test_no_contributor_handles(self):
        text = json.dumps(DEFAULT_STYLE).lower()
        for handle in ("hellonearthis", "hodgemann", "@"):
            self.assertNotIn(handle, text)


class DaylightMigration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "home"

    def path(self):
        return self.home / "styles/daylight.json"

    def test_fresh_home_gets_rich_default(self):
        Storage(self.home)
        self.assertEqual(json.loads(self.path().read_text()), DEFAULT_STYLE)

    def test_exact_legacy_factory_file_is_upgraded(self):
        write_json(self.path(), LEGACY_DEFAULT_STYLE)
        Storage(self.home)
        self.assertEqual(json.loads(self.path().read_text()), DEFAULT_STYLE)

    def test_customized_files_are_preserved(self):
        variants = [
            {**LEGACY_DEFAULT_STYLE, "name": "My Daylight"},
            {**LEGACY_DEFAULT_STYLE, "direction": LEGACY_DEFAULT_STYLE["direction"] + " Extra."},
            {**LEGACY_DEFAULT_STYLE, "style_card": "custom card"},
            {**DEFAULT_STYLE, "direction": "edited"},
        ]
        for variant in variants:
            with self.subTest(variant=variant):
                write_json(self.path(), variant)
                Storage(self.home)
                self.assertEqual(json.loads(self.path().read_text()), variant)

    def test_unreadable_file_is_left_alone(self):
        self.path().parent.mkdir(parents=True)
        self.path().write_text("{not json", encoding="utf-8")
        Storage(self.home)
        self.assertEqual(self.path().read_text(), "{not json")

    def test_removed_default_is_not_resurrected(self):
        self.home.mkdir()
        write_json(self.home / "removed-assets.json", {"actors": [], "styles": ["daylight"]})
        Storage(self.home)
        self.assertFalse(self.path().exists())

    def test_upgrade_is_idempotent(self):
        write_json(self.path(), LEGACY_DEFAULT_STYLE)
        Storage(self.home)
        first = self.path().read_text()
        Storage(self.home)
        self.assertEqual(self.path().read_text(), first)


if __name__ == "__main__":
    unittest.main()
