#!/usr/bin/env python3
"""Lint Mondo vocabulary tables with Laya typed decisions (choice questions).

Two checks:
  table_membership  Is each term in the table it belongs to? (settings, lighting, ...)
  tonal_split       Which entries of tonal_registers are really theme tags?

Laya's base checkpoints are near chance zero-shot on typed decisions (see its model
card, "Honest Limits"), so nothing is trusted until `eval` has scored the model on
terms YOU labelled. `lint` only runs a check whose eval beat the majority-class
baseline and found a confidence threshold that reaches the target precision.

1) Hand-label ~100 terms in gold.json:
     {"table_membership": {"raking halogen": "lighting", ...},
      "tonal_split":      {"carceral": "theme", "crushed blacks": "register", ...}}
2) python lint_vocab.py eval --gold gold.json --out eval.json
3) python lint_vocab.py lint --vocab vocab.json --eval eval.json --out lint.json

Backends: in-process `laya.Router` (default) or a running `laya-serve` (--backend http).
If laya.load() hangs, set USE_TF=0. Sampling terms: one state per term, one question.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from typing import Callable, Dict, List, Optional, Sequence, Tuple

# (state, questions) -> {question_name: {"choice": str, "confidence": float, ...}}
Classifier = Callable[[str, dict], dict]
Pred = Tuple[str, str, float]  # (term, predicted label, confidence)

MEMBERSHIP_TABLES = {
    "settings": "a physical place or environment where a scene is set",
    "lighting": "how a scene is lit: light sources, quality, direction or colour",
    "mechanisms": "a physical action or mechanical event involving objects",
    "costume": "clothing, uniforms or worn items",
    "practical_effects": "an in-camera physical effect such as smoke, sparks, rain or fire",
    "themes": "an abstract subject domain or thematic world",
}
TONAL_SPLIT = {
    "register": "a photographic or grading quality: palette, contrast, grain, tone",
    "theme": "a subject domain or setting tag, such as legal, military or industrial",
}
TASKS = {
    "table_membership": {"type": "choice",
                         "instructions": "Which vocabulary table does this film term belong to?",
                         "criteria": MEMBERSHIP_TABLES},
    "tonal_split": {"type": "choice",
                    "instructions": "Is this term a photographic register or a subject theme tag?",
                    "criteria": TONAL_SPLIT},
}


# --------------------------------------------------------------------------- #
# Pure functions
# --------------------------------------------------------------------------- #
def extract(answer: dict) -> Tuple[str, float]:
    """Pull (label, confidence) from one Laya answer; fail loudly on a new shape."""
    label, conf = answer.get("choice"), answer.get("confidence")
    if label is None or conf is None:
        raise ValueError(f"unexpected Laya answer (need 'choice' and 'confidence'): {answer!r}")
    return str(label), float(conf)


def predict(classify: Classifier, task: str, terms: Sequence[str]) -> List[Pred]:
    question = {task: TASKS[task]}
    return [(t, *extract(classify(t, question)[task])) for t in terms]


def accuracy(correct: Sequence[bool]) -> float:
    return sum(correct) / len(correct) if correct else 0.0


def majority_baseline(labels: Sequence[str]) -> float:
    return max(Counter(labels).values()) / len(labels) if labels else 0.0


def pick_threshold(conf: Sequence[float], correct: Sequence[bool],
                   target: float = 0.9, min_n: int = 10) -> Optional[float]:
    """Lowest confidence cut-off whose kept predictions reach the target precision."""
    for t in sorted(set(conf)):
        kept = [ok for c, ok in zip(conf, correct) if c >= t]
        if len(kept) >= min_n and sum(kept) / len(kept) >= target:
            return t
    return None


def ece(conf: Sequence[float], correct: Sequence[bool], bins: int = 10) -> float:
    n, total = len(conf), 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, c in enumerate(conf) if lo <= c < hi or (b == bins - 1 and c == 1.0)]
        if idx:
            acc = sum(correct[i] for i in idx) / len(idx)
            mean_conf = sum(conf[i] for i in idx) / len(idx)
            total += len(idx) / n * abs(acc - mean_conf)
    return total


def evaluate(preds: Sequence[Pred], gold: Dict[str, str],
             target: float = 0.9, min_n: int = 10) -> dict:
    correct = [label == gold[t] for t, label, _ in preds]
    conf = [c for _, _, c in preds]
    acc, base = accuracy(correct), majority_baseline(list(gold.values()))
    threshold = pick_threshold(conf, correct, target, min_n)
    confusion: Dict[str, Dict[str, int]] = {}
    for t, label, _ in preds:
        confusion.setdefault(gold[t], {}).setdefault(label, 0)
        confusion[gold[t]][label] += 1
    return {"n": len(preds), "accuracy": acc, "majority_baseline": base,
            "ece": ece(conf, correct), "target_precision": target,
            "threshold": threshold, "usable": acc > base and threshold is not None,
            "confusion": confusion}


def flag_membership(items: Sequence[Tuple[str, str]], preds: Dict[str, Tuple[str, float]],
                    threshold: float) -> dict:
    """items = (table, term). Flag confident disagreements; count the uncertain rest."""
    flagged, agree, uncertain = [], 0, 0
    for table, term in items:
        label, conf = preds[term]
        if conf < threshold:
            uncertain += 1
        elif label == table:
            agree += 1
        else:
            flagged.append({"term": term, "in": table, "predicted": label,
                            "confidence": round(conf, 3)})
    return {"agree": agree, "uncertain": uncertain, "flagged": flagged}


def flag_themes(preds: Sequence[Pred], threshold: float) -> dict:
    """Entries of tonal_registers that Laya confidently calls theme tags."""
    themes = [{"term": t, "confidence": round(c, 3)}
              for t, label, c in preds if label == "theme" and c >= threshold]
    return {"likely_theme_tags": themes,
            "uncertain": sum(1 for _, _, c in preds if c < threshold),
            "checked": len(preds)}


# --------------------------------------------------------------------------- #
# Side-effect boundary: classifiers, files, CLI
# --------------------------------------------------------------------------- #
def router_classifier(device: Optional[str] = None) -> Classifier:
    from laya import Router  # pip install laya

    router = Router(preload=True, **({"device": device} if device else {}))
    return lambda state, questions: router.predict(state, questions)["answers"]


def http_classifier(url: str, timeout: int = 30) -> Classifier:
    """laya-serve, POST /v1/systemone. Response shape ASSUMED to match Router's `answers`."""
    import requests

    key = os.environ.get("LAYA_API_KEY")
    headers = {"Authorization": f"Bearer {key}"} if key else {}

    def classify(state: str, questions: dict) -> dict:
        r = requests.post(f"{url.rstrip('/')}/v1/systemone", headers=headers, timeout=timeout,
                          json={"state": state, "questions": questions})
        r.raise_for_status()
        return r.json()["answers"]

    return classify


def make_classifier(a: argparse.Namespace) -> Classifier:
    return http_classifier(a.url) if a.backend == "http" else router_classifier(a.device)


def load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)


def load_pools(path: str, tables: Sequence[str]) -> Dict[str, List[str]]:
    raw = load_json(path)
    raw = raw.get("tables", raw)
    return {t: [s.strip() for s in raw[t] if s.strip()] for t in tables if t in raw}


def run_eval(a: argparse.Namespace, classify: Optional[Classifier] = None) -> dict:
    classify = classify or make_classifier(a)
    report = {}
    for task, gold in load_json(a.gold).items():
        preds = predict(classify, task, list(gold))
        report[task] = evaluate(preds, gold, a.target_precision, a.min_n)
        r = report[task]
        print(f"{task}: n={r['n']} acc={r['accuracy']:.2f} baseline={r['majority_baseline']:.2f} "
              f"ece={r['ece']:.2f} threshold={r['threshold']} usable={r['usable']}")
    save_json(a.out, report)
    return report


def run_lint(a: argparse.Namespace, classify: Optional[Classifier] = None) -> dict:
    evals = load_json(a.eval)
    pools = load_pools(a.vocab, list(MEMBERSHIP_TABLES) + ["tonal_registers"])
    out: dict = {}
    classify = None if not any(evals.get(t, {}).get("usable") for t in TASKS) else (
        classify or make_classifier(a))

    def gate(task: str) -> Optional[float]:
        e = evals.get(task, {})
        if e.get("usable"):
            return e["threshold"]
        out[task] = {"skipped": f"not validated (accuracy {e.get('accuracy', 'n/a')} vs "
                                f"baseline {e.get('majority_baseline', 'n/a')}); fine-tune or "
                                f"use another classifier"}
        return None

    th = gate("table_membership")
    if th is not None:
        items = [(t, s) for t in MEMBERSHIP_TABLES for s in pools.get(t, [])]
        by_term = {t: (l, c) for t, l, c in predict(classify, "table_membership",
                                                   sorted({s for _, s in items}))}
        out["table_membership"] = flag_membership(items, by_term, th)
    th = gate("tonal_split")
    if th is not None:
        out["tonal_split"] = flag_themes(
            predict(classify, "tonal_split", pools.get("tonal_registers", [])), th)
    save_json(a.out, out)
    for task, r in out.items():
        print(task, r.get("skipped") or {k: (len(v) if isinstance(v, list) else v)
                                         for k, v in r.items()})
    return out


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--backend", choices=["router", "http"], default="router")
    p.add_argument("--url", default="http://127.0.0.1:8000", help="laya-serve base URL")
    p.add_argument("--device", default=None, help="e.g. cuda or cpu (router backend)")
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("eval")
    e.add_argument("--gold", required=True)
    e.add_argument("--out", default="eval.json")
    e.add_argument("--target-precision", type=float, default=0.9)
    e.add_argument("--min-n", type=int, default=10)
    e.set_defaults(fn=run_eval)
    l = sub.add_parser("lint")
    l.add_argument("--vocab", required=True)
    l.add_argument("--eval", required=True)
    l.add_argument("--out", default="lint.json")
    l.set_defaults(fn=run_lint)
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    args.fn(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())

