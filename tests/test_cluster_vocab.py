"""Unit tests for cluster_vocab. No network, no real services: the embedder is faked."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cluster_vocab as cv  # noqa: E402


def synthetic(per_group=20, offset=3.0, seed=0):
    """Two tables x two themes; a big per-table offset mimics a shared prefix."""
    rng = np.random.default_rng(seed)
    dim = 16
    e = np.eye(dim, dtype=np.float32)
    themes = {"t1": e[0], "t2": e[1]}
    offsets = {"settings": offset * e[2], "lighting": offset * e[3]}
    items, vecs, truth = [], [], []
    for table in offsets:
        for tname, tvec in themes.items():
            for i in range(per_group):
                items.append((table, f"{tname} {table} {i}"))
                vecs.append(offsets[table] + tvec + 0.05 * rng.normal(size=dim))
                truth.append(tname)
    return items, np.asarray(vecs, dtype=np.float32), truth


def test_unit_keeps_zero_rows_finite():
    out = cv.unit(np.array([[0.0, 0.0], [3.0, 4.0]]))
    assert np.isfinite(out).all()
    assert np.allclose(out[1], [0.6, 0.8])


def test_centering_stops_clusters_collapsing_into_tables():
    items, vecs, _ = synthetic()
    raw = cv.build_model(items, vecs, k=2, center=False)
    ctr = cv.build_model(items, vecs, k=2, center=True)
    assert raw["table_purity"] > 0.95      # clusters == tables
    assert ctr["table_purity"] < 0.65      # clusters == themes, spread across tables


def test_centered_clusters_follow_themes():
    items, vecs, truth = synthetic()
    model = cv.build_model(items, vecs, k=2, center=True)
    labels = [model["assignments"][t][term] for t, term in items]
    for theme in ("t1", "t2"):
        got = {lab for lab, tr in zip(labels, truth) if tr == theme}
        assert len(got) == 1


def test_build_is_deterministic():
    items, vecs, _ = synthetic()
    a = cv.build_model(items, vecs, k=2, seed=7)
    b = cv.build_model(items, vecs, k=2, seed=7)
    assert a == b


def test_choose_k_stays_in_bounds():
    items, vecs, _ = synthetic()
    x, _ = cv.center_by_category(cv.unit(vecs), [t for t, _ in items])
    k = cv.choose_k(x, 2, 6, seed=1)
    assert 2 <= k <= 6


def test_calibrate_orders_percentiles():
    rng = np.random.default_rng(1)
    cent = cv.unit(rng.normal(size=(10, 8)))
    cal = cv.calibrate(cv.centroid_distances(cent), 15, 85)
    assert cal["adjacent_max"] <= cal["opposed_min"] <= cal["d_max"]


def test_empty_cells_reported():
    items = [("settings", f"a{i}") for i in range(6)] + [("costume", f"b{i}") for i in range(2)]
    rng = np.random.default_rng(2)
    vecs = np.vstack([rng.normal(size=(6, 8)) + 5, rng.normal(size=(2, 8)) - 5]).astype(np.float32)
    model = cv.build_model(items, vecs, k=2, center=False)
    assert model["empty_cells"]            # costume cannot fill both clusters


def test_assign_reproduces_build_labels():
    items, vecs, _ = synthetic()
    model = cv.build_model(items, vecs, k=2, center=True)
    idx = [i for i, (t, _) in enumerate(items) if t == "lighting"]
    got = cv.assign_vectors(model, "lighting", vecs[idx])
    want = [model["assignments"]["lighting"][items[i][1]] for i in idx]
    assert got == want


def test_cli_build_and_assign_with_fake_embedder(tmp_path):
    items, vecs, _ = synthetic(per_group=12)
    lookup = {cv.embed_text(t, s, True): v for (t, s), v in zip(items, vecs)}
    fake = lambda texts: np.asarray([lookup[x] for x in texts], dtype=np.float32)  # noqa: E731
    vocab = {}
    for t, s in items:
        vocab.setdefault(t, []).append(s)
    (tmp_path / "vocab.json").write_text(json.dumps({"tables": vocab}))
    args = SimpleNamespace(vocab=str(tmp_path / "vocab.json"), out=str(tmp_path / "c.json"),
                           tables=["settings", "lighting"], k=2, k_min=2, k_max=4, seed=1,
                           adjacent_pct=15.0, opposed_pct=85.0, no_center=False,
                           no_prefix=False, embed_url="x", model="fake", exemplars=3, force=False)
    model = cv.run_build(args, embed=fake)
    assert json.loads((tmp_path / "c.json").read_text())["k"] == model["k"] == 2
    a = SimpleNamespace(clusters=str(tmp_path / "c.json"), table="lighting",
                        terms=[items[-1][1]], embed_url="x", model="")
    assert cv.run_assign(a, embed=fake) == [model["assignments"]["lighting"][items[-1][1]]]


def test_default_tables_exclude_film_technical_axes():
    for technical in ("tonal_registers", "footage_anchors", "shot_scales", "camera_by_energy"):
        assert technical not in cv.POOLS
    assert {"settings", "lighting", "mechanisms", "costume", "practical_effects"} <= set(cv.POOLS)


def test_exemplars_are_closest_to_centroid_and_capped():
    items, vecs, _ = synthetic()
    model = cv.build_model(items, vecs, k=2, n_exemplars=3)
    for tables in model["exemplars"].values():
        for terms in tables.values():
            assert 0 < len(terms) <= 3
    # exemplar terms really belong to the cluster they are listed under
    for cluster_id, tables in model["exemplars"].items():
        for table, terms in tables.items():
            assert all(model["assignments"][table][term] == int(cluster_id) for term in terms)


def test_inspect_report_lists_clusters_and_tables():
    items, vecs, _ = synthetic()
    text = cv.format_inspect(cv.build_model(items, vecs, k=2, n_exemplars=2))
    assert "== cluster 0 ==" in text and "== cluster 1 ==" in text
    assert "settings:" in text and "lighting:" in text


def test_build_caching_and_change_detection(tmp_path):
    items, vecs, _ = synthetic(per_group=6)
    lookup = {cv.embed_text(t, s, True): v for (t, s), v in zip(items, vecs)}
    call_count = 0

    def counting_fake(texts):
        nonlocal call_count
        call_count += 1
        return np.asarray([lookup[x] for x in texts], dtype=np.float32)

    vocab_file = tmp_path / "vocab.json"
    out_file = tmp_path / "clusters.json"
    vocab = {"tables": {"settings": [s for t, s in items if t == "settings"]}}
    vocab_file.write_text(json.dumps(vocab))

    args = SimpleNamespace(vocab=str(vocab_file), out=str(out_file),
                           tables=["settings"], k=2, k_min=2, k_max=4, seed=1,
                           adjacent_pct=15.0, opposed_pct=85.0, no_center=False,
                           no_prefix=False, embed_url="x", model="fake", exemplars=3, force=False)

    # First run: should call embedder
    m1 = cv.run_build(args, embed=counting_fake)
    assert call_count == 1
    assert "source_vocab_sha256" in m1

    # Second run without changes: should skip embedder
    m2 = cv.run_build(args, embed=counting_fake)
    assert call_count == 1  # No additional call!
    assert m2["source_vocab_sha256"] == m1["source_vocab_sha256"]

    # Third run with force=True: should call embedder
    args.force = True
    m3 = cv.run_build(args, embed=counting_fake)
    assert call_count == 2
    args.force = False

    # Fourth run: modify vocab file -> should call embedder
    vocab["tables"]["settings"].append("brand new setting term")
    lookup["settings: brand new setting term"] = np.ones(16, dtype=np.float32)
    vocab_file.write_text(json.dumps(vocab))
    m4 = cv.run_build(args, embed=counting_fake)
    assert call_count == 3
    assert m4["source_vocab_sha256"] != m1["source_vocab_sha256"]


def test_style_digest_extraction():
    from mmv.style_embed import extract_style_digest

    style_with_card = {
        "id": "noir_test",
        "name": "Noir Test",
        "direction": "fallback direction",
        "style_card": (
            "NAME: Noir Test\n"
            "CRAFT: Chiaroscuro lighting with deep Venetian blind shadows; 35mm grain\n"
            "GRAMMAR: Locked-off tripod framing; slow push-ins\n"
            "FREE AXES: Color palette; location architecture\n"
        )
    }
    digest = extract_style_digest(style_with_card)
    assert digest == "style: Chiaroscuro lighting with deep Venetian blind shadows; 35mm grain; Locked-off tripod framing; slow push-ins"

    style_simple = {
        "id": "simple_look",
        "name": "Simple Look",
        "direction": "Handheld vintage 16mm warm tones"
    }
    assert extract_style_digest(style_simple) == "style: Handheld vintage 16mm warm tones"


def test_style_sidecar_sync_and_change_detection(tmp_path):
    from mmv.style_embed import sync_style_file, sync_styles_directory

    call_count = 0
    def fake_embed(texts):
        nonlocal call_count
        call_count += 1
        return np.ones((len(texts), 16), dtype=np.float32)

    style_path = tmp_path / "sun_bleach.json"
    style_path.write_text(json.dumps({
        "id": "sun_bleach",
        "name": "Sun Bleached",
        "direction": "Overexposed harsh midday sunlight on dusty concrete"
    }))

    # 1. First sync: creates sidecar and calls embedder
    status, sidecar = sync_style_file(style_path, embed=fake_embed)
    assert status == "updated"
    assert call_count == 1
    assert (tmp_path / "sun_bleach.emb.json").is_file()
    assert sidecar["dims"] == 16
    assert sidecar["normalized"] is True

    # 2. Second sync: unchanged source -> skips embedder
    status2, sidecar2 = sync_style_file(style_path, embed=fake_embed)
    assert status2 == "skipped"
    assert call_count == 1

    # 3. Edit style direction -> re-embeds and updates
    style_path.write_text(json.dumps({
        "id": "sun_bleach",
        "name": "Sun Bleached",
        "direction": "Overexposed harsh midday sunlight with anamorphic horizontal flares"
    }))
    status3, sidecar3 = sync_style_file(style_path, embed=fake_embed)
    assert status3 == "updated"
    assert call_count == 2
    assert sidecar3["embed_text_sha256"] != sidecar["embed_text_sha256"]

    # 4. Directory sync
    res = sync_styles_directory(tmp_path, embed=fake_embed)
    assert res["skipped"] == 1
    assert res["updated"] == 0
    assert call_count == 2
