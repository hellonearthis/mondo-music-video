import random
import unittest

from mmv import quick_start
from mmv.starter_assets import ACTORS


class QuickStartPlanTests(unittest.TestCase):
    def plans(self, actors, styles=("daylight", "noir_bw"), count=300):
        return [quick_start.plan(actors, styles, random.Random(seed)) for seed in range(count)]

    def test_no_actors_runs_without_cast_or_dance(self):
        for plan in self.plans([]):
            self.assertEqual((plan["actors"], plan["dance_mode"], plan["dancers"]), ([], "off", []))
            self.assertTrue(plan["direction"])

    def test_starter_cast_preferred_and_variety(self):
        plans = self.plans(list(ACTORS) + ["private_one"])
        self.assertTrue(all(set(p["actors"]) <= set(ACTORS) for p in plans))
        self.assertTrue(any(not p["actors"] for p in plans))
        self.assertTrue(any(p["actors"] for p in plans))
        self.assertTrue(any(p["dance_mode"] == "group" for p in plans))
        self.assertTrue(all(len(p["actors"]) <= quick_start.MAX_CAST for p in plans))

    def test_dancers_are_the_cast_and_only_when_cast(self):
        for plan in self.plans(["a", "b"]):
            self.assertEqual(plan["dancers"], plan["actors"] if plan["dance_mode"] == "group" else [])
            self.assertEqual(plan["dance_mode"] == "group", bool(plan["dancers"]))

    def test_other_actors_used_when_no_starter_cast(self):
        self.assertTrue(any(p["actors"] for p in self.plans(["mine"])))

    def test_never_enables_instruments_or_subliminal(self):
        for plan in self.plans(list(ACTORS)):
            self.assertFalse({"instrument_mode", "subliminal", "subliminal_mode"} & set(plan))

    def test_style_comes_from_installed_styles(self):
        self.assertEqual({p["style_id"] for p in self.plans([], ("only",))}, {"only"})
        self.assertEqual(self.plans([], ())[0]["style_id"], "daylight")


if __name__ == "__main__":
    unittest.main()
