#!/usr/bin/env python3
"""Cluster Mondo vocabulary terms from embeddings.

Layout: pure functions do all the maths (vectors in, plain data out); the only
side effects are the HTTP embedder and the JSON read/write wrappers at the bottom.
The embedder is a plain callable, so tests inject a fake one (no network).

Serve an embedding model first (CPU is fine; Qwen3-Embedding needs last-token pooling):
    llama-server -hf Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0 --embeddings \
        --pooling last --port 8092 -ngl 0

Build clusters:
    python cluster_vocab.py build --vocab vocab.json --out clusters.json

Read the clusters (no embedder needed) to check they make sense:
    python cluster_vocab.py inspect --clusters clusters.json

Assign new terms (user datasets / harvest runs) without re-clustering:
    python cluster_vocab.py assign --clusters clusters.json \
        --table lighting --terms "raking slit-scan halogen"

Sync style vector sidecars (.emb.json):
    python cluster_vocab.py styles --dir data/styles

Assumes vocab.json is {table: [terms]} or {"tables": {table: [terms]}}.
Requires numpy and scikit-learn (requests only for the HTTP embedder).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

Embedder = Callable[[List[str]], np.ndarray]
Item = Tuple[str, str]  # (table, term)

# Only the dimensions kappa binds (spec 6.3) plus the themes pool. Film-technical
# axes (camera, shot scales, tonal_registers, footage_anchors) belong to the Style,
# not to the world a term lives in, so they stay out of the clustering.
POOLS = ["settings", "lighting", "mechanisms", "costume",
         "practical_effects", "themes"]
FORMAT_VERSION = 1


# --------------------------------------------------------------------------- #
# Pure functions
# --------------------------------------------------------------------------- #
def unit(v: np.ndarray) -> np.ndarray:
    """L2-normalize rows; zero rows stay zero instead of becoming NaN."""
    v = np.asarray(v, dtype=np.float32)
    n = np.linalg.norm(v, axis=1, keepdims=True)
    return v / np.where(n == 0, 1.0, n)


def embed_text(table: str, term: str, prefix: bool) -> str:
    return f"{table}: {term}" if prefix else term


def center_by_category(x: np.ndarray, categories: Sequence[str]
                       ) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
    """Subtract each category's mean vector, then re-normalize.

    A shared "lighting:" prefix pulls every lighting term toward the same
    region, so clustering can end up grouping by table instead of by theme.
    Removing the per-category mean cancels that offset. Categories with fewer
    than two terms are left alone (no mean to remove).
    """
    cats = np.asarray(categories)
    out = x.copy()
    means: Dict[str, np.ndarray] = {}
    for c in sorted(set(categories)):
        idx = cats == c
        if idx.sum() < 2:
            continue
        means[c] = x[idx].mean(axis=0)
        out[idx] = x[idx] - means[c]
    return unit(out), means


def choose_k(x: np.ndarray, k_min: int, k_max: int, seed: int) -> int:
    """Pick k by cosine silhouette; ties go to the smaller k."""
    hi = min(k_max, len(x) - 1)
    lo = min(k_min, hi)
    best_score, best_k = -2.0, lo
    for k in range(lo, hi + 1):
        labels = KMeans(k, n_init=10, random_state=seed).fit_predict(x)
        score = silhouette_score(x, labels, metric="cosine")
        if score > best_score:
            best_score, best_k = score, k
    return best_k


def cluster(x: np.ndarray, k: int, seed: int) -> Tuple[np.ndarray, np.ndarray]:
    """KMeans on unit vectors -> (labels, unit centroids). Deterministic per seed."""
    km = KMeans(k, n_init=10, random_state=seed).fit(x)
    return km.labels_, unit(km.cluster_centers_)


def centroid_distances(centroids: np.ndarray) -> np.ndarray:
    return 1.0 - centroids @ centroids.T


def calibrate(dist: np.ndarray, adjacent_pct: float, opposed_pct: float
              ) -> Dict[str, float]:
    """Distance cut-offs from the real pairwise distribution (no fixed 0.3/0.7)."""
    off = dist[~np.eye(len(dist), dtype=bool)]
    return {
        "adjacent_max": float(np.percentile(off, adjacent_pct)),
        "opposed_min": float(np.percentile(off, opposed_pct)),
        "d_max": float(off.max()),
    }


def table_counts(labels: Sequence[int], tables_of_items: Sequence[str],
                 tables: Sequence[str], k: int) -> np.ndarray:
    counts = np.zeros((k, len(tables)), dtype=int)
    col = {t: j for j, t in enumerate(tables)}
    for lab, t in zip(labels, tables_of_items):
        counts[int(lab), col[t]] += 1
    return counts


def table_purity(counts: np.ndarray) -> float:
    """Share of terms sitting in their cluster's dominant table.

    ~1/len(tables) means themes are mixed across tables (what we want);
    near 1.0 means clusters are really just the tables again.
    """
    total = counts.sum()
    return float(counts.max(axis=1).sum() / total) if total else 0.0


def exemplars(items: Sequence[Item], x: np.ndarray, labels: Sequence[int],
              centroids: np.ndarray, n: int) -> Dict[str, Dict[str, List[str]]]:
    """The n terms closest to their centroid, per cluster and table."""
    sims = np.einsum("ij,ij->i", x, centroids[np.asarray(labels)])
    out: Dict[str, Dict[str, List[str]]] = {}
    for idx in np.argsort(-sims, kind="stable"):
        table, term = items[idx]
        bucket = out.setdefault(str(int(labels[idx])), {}).setdefault(table, [])
        if len(bucket) < n:
            bucket.append(term)
    return out


def format_inspect(model: dict) -> str:
    """Human-readable cluster report: exemplars per table, so you can sanity-check themes."""
    lines = [f"k={model['k']}  table_purity={model['table_purity']:.2f}  "
             f"adjacent<={model['adjacent_max']:.3f}  opposed>={model['opposed_min']:.3f}"]
    empty = {(e["cluster"], e["table"]) for e in model.get("empty_cells", [])}
    for c in sorted(model.get("exemplars", {}), key=int):
        lines.append(f"\n== cluster {c} ==")
        for table, terms in model["exemplars"][c].items():
            lines.append(f"  {table}: " + "; ".join(terms))
        missing = sorted(t for (cc, t) in empty if cc == int(c))
        if missing:
            lines.append("  (empty: " + ", ".join(missing) + ")")
    return "\n".join(lines)


def build_model(items: Sequence[Item], vectors: np.ndarray, *, k: int = 0,
                k_min: int = 8, k_max: int = 24, seed: int = 1234,
                adjacent_pct: float = 15.0, opposed_pct: float = 85.0,
                center: bool = True, prefix: bool = True,
                embed_model: str = "", n_exemplars: int = 5) -> dict:
    """Items + their raw embeddings -> a JSON-serializable cluster model."""
    tables = list(dict.fromkeys(t for t, _ in items))
    cats = [t for t, _ in items]
    x = unit(vectors)
    means: Dict[str, np.ndarray] = {}
    if center:
        x, means = center_by_category(x, cats)
    k = k or choose_k(x, k_min, k_max, seed)
    labels, cent = cluster(x, k, seed)
    dist = centroid_distances(cent)
    counts = table_counts(labels, cats, tables, k)
    assignments: Dict[str, Dict[str, int]] = {t: {} for t in tables}
    for (t, term), lab in zip(items, labels):
        assignments[t][term] = int(lab)
    return {
        "format_version": FORMAT_VERSION,
        "embed_model": embed_model, "seed": seed, "k": int(k),
        "centered": center, "prefix": prefix,
        "percentiles": {"adjacent": adjacent_pct, "opposed": opposed_pct},
        **calibrate(dist, adjacent_pct, opposed_pct),
        "table_purity": table_purity(counts),
        "centroids": cent.tolist(),
        "category_means": {c: m.tolist() for c, m in means.items()},
        "cluster_table_counts": {t: counts[:, j].tolist() for j, t in enumerate(tables)},
        "empty_cells": [{"cluster": int(c), "table": t}
                        for c in range(k) for j, t in enumerate(tables)
                        if counts[c, j] == 0],
        "exemplars": exemplars(items, x, labels, cent, n_exemplars),
        "assignments": assignments,
    }


def assign_vectors(model: dict, table: str, vectors: np.ndarray) -> List[int]:
    """Nearest centroid for new terms, using the same centering as the build."""
    x = unit(vectors)
    mean = model.get("category_means", {}).get(table)
    if model.get("centered") and mean is not None:
        x = unit(x - np.asarray(mean, dtype=np.float32))
    cent = np.asarray(model["centroids"], dtype=np.float32)
    return [int(i) for i in (x @ cent.T).argmax(axis=1)]


# --------------------------------------------------------------------------- #
# Side-effect boundary: HTTP embedder, JSON files, CLI
# --------------------------------------------------------------------------- #
def file_sha256(path: str) -> str:
    """Compute deterministic SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def http_embedder(url: str, model: str, batch: int = 64, timeout: int = 120) -> Embedder:
    """OpenAI-compatible /embeddings client (e.g. llama-server --embeddings)."""
    import requests

    def embed(texts: List[str]) -> np.ndarray:
        out: List[List[float]] = []
        for i in range(0, len(texts), batch):
            r = requests.post(f"{url.rstrip('/')}/embeddings",
                              json={"model": model, "input": texts[i:i + batch]},
                              timeout=timeout)
            r.raise_for_status()
            data = sorted(r.json()["data"], key=lambda d: d["index"])
            out += [d["embedding"] for d in data]
        return np.asarray(out, dtype=np.float32)

    return embed


def load_pools(path: str, tables: Sequence[str]) -> Dict[str, List[str]]:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    raw = raw.get("tables", raw)
    return {t: [s.strip() for s in raw[t] if s.strip()] for t in tables if t in raw}


def run_build(a: argparse.Namespace, embed: Optional[Embedder] = None) -> dict:
    source_sha = file_sha256(a.vocab)
    force = getattr(a, "force", False)

    # Change-detection: test if source vocab changed before contacting embedder
    if not force and os.path.isfile(a.out):
        try:
            with open(a.out, encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("source_vocab_sha256") == source_sha:
                print(f"[clusters] Source vocabulary unchanged (sha256: {source_sha[:12]}...). "
                      f"Clusters are up to date -> {a.out} (skipped embedder wake-up).")
                return cached
        except Exception:
            pass

    print(f"[clusters] Source vocabulary modified or new (sha256: {source_sha[:12]}...). "
          f"Waking embedder on {a.embed_url} to process clusters...")
    embed = embed or http_embedder(a.embed_url, a.model)
    pools = load_pools(a.vocab, a.tables)
    items = [(t, s) for t, terms in pools.items() for s in terms]
    vectors = embed([embed_text(t, s, not a.no_prefix) for t, s in items])
    n_ex = getattr(a, "exemplars", 5)
    model = build_model(items, vectors, k=a.k, k_min=a.k_min, k_max=a.k_max,
                        seed=a.seed, adjacent_pct=a.adjacent_pct,
                        opposed_pct=a.opposed_pct, center=not a.no_center,
                        prefix=not a.no_prefix, embed_model=a.model,
                        n_exemplars=n_ex)
    model["source_vocab_sha256"] = source_sha
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(model, f, indent=1, ensure_ascii=False)
    print(f"[clusters] Processed {len(items)} terms across {len(pools)} tables into k={model['k']} clusters: "
          f"adjacent<={model['adjacent_max']:.3f} opposed>={model['opposed_min']:.3f} table_purity={model['table_purity']:.2f} -> {a.out}")
    return model


def run_assign(a: argparse.Namespace, embed: Optional[Embedder] = None) -> List[int]:
    with open(a.clusters, encoding="utf-8") as f:
        model = json.load(f)
    embed = embed or http_embedder(a.embed_url, a.model or model["embed_model"])
    vectors = embed([embed_text(a.table, s, model["prefix"]) for s in a.terms])
    labels = assign_vectors(model, a.table, vectors)
    for term, lab in zip(a.terms, labels):
        print(f"{lab}\t{term}")
    return labels


def run_inspect(a: argparse.Namespace) -> str:
    with open(a.clusters, encoding="utf-8") as f:
        text = format_inspect(json.load(f))
    print(text)
    return text


def run_styles(a: argparse.Namespace, embed: Optional[Embedder] = None) -> dict:
    from mmv.style_embed import sync_style_file, sync_styles_directory
    model_name = a.model or "Qwen3-Embedding-0.6B-GGUF:Q8_0"
    embed = embed or http_embedder(a.embed_url, model_name)
    if getattr(a, "style", None):
        status, sidecar = sync_style_file(a.style, embed=embed, model=model_name, force=a.force)
        return {"status": status, "sidecar": sidecar}
    return sync_styles_directory(a.dir, embed=embed, model=model_name, force=a.force)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--embed-url", default="http://127.0.0.1:8092/v1")
    p.add_argument("--model", default="")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--vocab", required=True)
    b.add_argument("--out", default="clusters.json")
    b.add_argument("--tables", nargs="+", default=POOLS)
    b.add_argument("-k", type=int, default=0, help="fixed k; 0 = choose by silhouette")
    b.add_argument("--k-min", type=int, default=8)
    b.add_argument("--k-max", type=int, default=24)
    b.add_argument("--seed", type=int, default=1234)
    b.add_argument("--adjacent-pct", type=float, default=15.0)
    b.add_argument("--opposed-pct", type=float, default=85.0)
    b.add_argument("--no-center", action="store_true",
                   help="skip per-category mean subtraction")
    b.add_argument("--no-prefix", action="store_true",
                   help="embed bare terms without the 'table: ' prefix")
    b.add_argument("--exemplars", type=int, default=5,
                   help="terms per table shown for each cluster in `inspect`")
    b.add_argument("--force", action="store_true",
                   help="force re-clustering even if source vocab is unchanged")
    b.set_defaults(fn=run_build)
    i = sub.add_parser("inspect")
    i.add_argument("--clusters", required=True)
    i.set_defaults(fn=run_inspect)
    s = sub.add_parser("assign")
    s.add_argument("--clusters", required=True)
    s.add_argument("--table", required=True)
    s.add_argument("--terms", nargs="+", required=True)
    s.set_defaults(fn=run_assign)
    st = sub.add_parser("styles", help="sync .emb.json embedding sidecars for styles")
    st.add_argument("--dir", default="data/styles", help="directory of style JSON cards")
    st.add_argument("--style", help="path to a single style JSON card")
    st.add_argument("--force", action="store_true", help="force re-embedding even if digest matches")
    st.set_defaults(fn=run_styles)
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    args.fn(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
