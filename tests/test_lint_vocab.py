"""Unit tests for lint_vocab. No Laya, no network: the classifier is faked."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import lint_vocab as lv  # noqa: E402


def fake_classify(state, questions):
    task = next(iter(questions))
    if task == "table_membership":
        if "lamp" in state:
            ans = ("lighting", 0.95)
        elif "room" in state:
            ans = ("settings", 0.92)
        else:
            ans = ("costume", 0.55)
    else:
        if "carceral" in state:
            ans = ("theme", 0.96)
        else:
            ans = ("register", 0.7)
    return {task: {"choice": ans[0], "confidence": ans[1]}}


def test_extract_requires_choice_and_confidence():
    assert lv.extract({"choice": "billing", "confidence": 0.94}) == ("billing", 0.94)
    with pytest.raises(ValueError):
        lv.extract({"choice": "billing"})


def test_baseline_and_accuracy():
    assert lv.majority_baseline(["a", "a", "b", "a"]) == 0.75
    assert lv.accuracy([True, False, True, True]) == 0.75


def test_pick_threshold_lowest_that_reaches_target():
    conf = [0.5] * 10 + [0.9] * 10
    correct = [False] * 10 + [True] * 10
    assert lv.pick_threshold(conf, correct, target=0.9, min_n=10) == 0.9
    assert lv.pick_threshold([0.5] * 20, [False] * 20, target=0.9, min_n=10) is None


def test_ece_zero_when_confident_and_right():
    assert lv.ece([1.0, 1.0, 1.0], [True, True, True]) == 0.0


def test_evaluate_not_usable_when_below_baseline():
    gold = {f"t{i}": "a" for i in range(9)}
    gold["x"] = "b"                                   # baseline 0.9
    preds = [(t, "b", 0.99) for t in gold]            # always wrong on 9 of 10
    r = lv.evaluate(preds, gold)
    assert r["accuracy"] < r["majority_baseline"] and not r["usable"]


def test_flag_membership_only_flags_confident_disagreements():
    items = [("settings", "grey room"), ("settings", "sodium lamp"), ("settings", "mystery")]
    preds = {"grey room": ("settings", 0.92), "sodium lamp": ("lighting", 0.95),
             "mystery": ("costume", 0.55)}
    r = lv.flag_membership(items, preds, threshold=0.8)
    assert r["agree"] == 1 and r["uncertain"] == 1
    assert [f["term"] for f in r["flagged"]] == ["sodium lamp"]


def test_flag_themes():
    preds = [("carceral", "theme", 0.96), ("film grain", "register", 0.7), ("odd", "theme", 0.4)]
    r = lv.flag_themes(preds, threshold=0.8)
    assert [t["term"] for t in r["likely_theme_tags"]] == ["carceral"]
    assert r["uncertain"] == 2


def test_eval_then_lint_end_to_end(tmp_path):
    gold = {"table_membership": {f"room {i}": "settings" for i in range(8)}
            | {f"lamp {i}": "lighting" for i in range(8)}}
    (tmp_path / "gold.json").write_text(json.dumps(gold))
    ev = SimpleNamespace(gold=str(tmp_path / "gold.json"), out=str(tmp_path / "eval.json"),
                         target_precision=0.9, min_n=10)
    report = lv.run_eval(ev, classify=fake_classify)
    assert report["table_membership"]["usable"]

    vocab = {"tables": {"settings": ["grey room", "sodium lamp"], "lighting": ["lamp glow"],
                        "tonal_registers": ["carceral", "film grain"]}}
    (tmp_path / "vocab.json").write_text(json.dumps(vocab))
    # tonal_split was never evaluated, so it must be skipped rather than trusted
    ln = SimpleNamespace(vocab=str(tmp_path / "vocab.json"), eval=str(tmp_path / "eval.json"),
                         out=str(tmp_path / "lint.json"))
    out = lv.run_lint(ln, classify=fake_classify)
    assert [f["term"] for f in out["table_membership"]["flagged"]] == ["sodium lamp"]
    assert "skipped" in out["tonal_split"]

