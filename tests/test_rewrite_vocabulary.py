"""A rewrite's vocabulary passes see the passage's real position, and other passages stay as they were."""
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

from mmv.engine.plan import Segment, Shot, STANDARD, VocabSampler
from mmv import takes, vocab_select
from mmv.storage import read_json, write_json


def table(prefix):
    return [f"{prefix}{n}" for n in range(12)]


VOCAB = {name: table(name) for name in ("settings", "subject_types", "mechanisms", "lighting", "tonal_registers", "costume",
                                         "footage_anchors", "practical_effects", "rigging")}


def segment(index):
    shot = mock.Mock(spec=Shot, vocab={"setting": "settings0", "subject_type": "subject_types0", "mechanism": "mechanisms0",
                                        "lighting": "lighting0", "tonal_register": "tonal_registers0", "costume": "costume0"}, energy=.5)
    return mock.Mock(spec=Segment, index=index, montage_type=STANDARD, energy=.5, thematic_anchor=None, footage_anchor="footage_anchors0",
                     practical_effects="practical_effects0", rigging="rigging0", shots=[shot])


class ReplanTests(unittest.TestCase):
    def replan(self, request, index=1):
        segments = [segment(0), segment(1)]
        before = deepcopy(segments[0].shots[0].vocab)
        with mock.patch("mmv.pipeline.load_vocabulary", return_value=deepcopy(VOCAB)):
            takes.replan_segment_vocabulary(mock.Mock(), request, segments, index, 77)
        self.assertEqual(segments[0].shots[0].vocab, before, "other passages stay")
        return segments[index]

    def test_draws_new_terms_and_keeps_rigging(self):
        seg = self.replan({})
        self.assertNotEqual(seg.shots[0].vocab["setting"], "settings0")
        self.assertNotEqual(seg.footage_anchor, "footage_anchors0")
        self.assertEqual(seg.rigging, "rigging0")

    def test_energy_pass_uses_the_passage_position_in_the_whole_list(self):
        seen = []
        real = vocab_select.apply_energy_scaled_vocabulary
        def spy(segments, vocab, seed):
            seen.append(len(segments))
            return real(segments, vocab, seed)
        with mock.patch("mmv.vocab_select.apply_energy_scaled_vocabulary", spy), \
             mock.patch("mmv.vocab_select.contextual_vocabulary", lambda vocab, seed, context: vocab):
            self.replan({"vocab_selection": "contextual"})
        self.assertEqual(seen, [2])

    def test_a_one_term_pool_repeats_rather_than_failing(self):
        sampler = VocabSampler({"settings": ["only"]}, 1, {"settings": ["only"]})
        self.assertEqual(sampler.pick("settings"), "only")


class SavedVocabularyTests(unittest.TestCase):
    def test_every_saved_plan_copy_changes_for_that_passage_only(self):
        passage = lambda i: {"index": i, "thematic_anchor": None, "footage_anchor": "a", "practical_effects": "b", "shots": [{"start": 0, "vocab": {"setting": "old"}}]}
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            segments = [passage(0), passage(1)]
            write_json(directory / "plan.json", {"slug": "x", "segments": segments})
            write_json(directory / "prepared.json", {"plan": {"slug": "y", "segments": segments}, "segments": segments})
            new = {"thematic_anchor": "m", "footage_anchor": "c", "practical_effects": "d", "shots": [{"setting": "new"}]}
            takes.save_passage_vocabulary(directory, "seg001", new)
            prepared, plan = read_json(directory / "prepared.json"), read_json(directory / "plan.json")
            for copy in (plan["segments"], prepared["plan"]["segments"], prepared["segments"]):
                self.assertEqual(copy[0], segments[0])
                self.assertEqual(takes.passage_vocabulary(copy[1]), new)
                self.assertEqual(copy[1]["shots"][0]["start"], 0)
            self.assertEqual((plan["slug"], prepared["plan"]["slug"]), ("x", "y"))

    def test_identical_text_keeps_the_active_version_and_a_missing_plan_file_falls_back(self):
        segments = [{"index": 0, "thematic_anchor": None, "footage_anchor": "a", "practical_effects": "b", "shots": [{"vocab": {"setting": "s"}}]}]
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            write_json(directory / "prepared.json", {"plan": {"segments": segments}, "segments": segments})
            self.assertEqual(takes._current_vocabulary(directory, "seg000")["shots"], [{"setting": "s"}])
            takes.save_passage_vocabulary(directory, "seg000", {"thematic_anchor": None, "footage_anchor": "c", "practical_effects": "d", "shots": [{"setting": "n"}]})
            self.assertEqual(read_json(directory / "plan.json")["segments"][0]["footage_anchor"], "c")
            write_json(directory / takes.PROMPT_TAKES_FILE, {"segments": {"seg000": {"active_take": "prompt4", "takes": [
                {"id": "prompt1", "prompt": "same"}, {"id": "prompt4", "prompt": "same"}]}}})
            view, _ = takes._prompt_takes_view(directory, {"segments": segments}, {"seg000": "same"})
            self.assertEqual(view["segments"]["seg000"]["active_take"], "prompt4")


if __name__ == "__main__":
    unittest.main()
