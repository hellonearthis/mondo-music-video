"""Tests for semantic world vector clustering, percentile calibration, and Gaussian dissonance (kappa)."""
import copy
import numpy as np

from mmv import vocab_select as vs
from mmv import world_vectors as wv


def test_prefix_domain_term_formats_canonical_domains():
    assert wv.prefix_domain_term("settings", "subterranean maglev platform") == "setting: subterranean maglev platform"
    assert wv.prefix_domain_term("lighting", "raking slit-scan halogen") == "lighting: raking slit-scan halogen"
    assert wv.prefix_domain_term("mechanisms", "hydraulic airlock cycling") == "mechanism: hydraulic airlock cycling"
    assert wv.prefix_domain_term("Practical Effects", "cold breath mist") == "practical_effect: cold breath mist"


def test_compute_cluster_centroid_and_percentile_calibration():
    centroids = {
        name: wv.compute_cluster_centroid(pools)
        for name, pools in wv.BUILTIN_THEMATIC_WORLDS.items()
    }
    assert len(centroids) == 10
    for vec in centroids.values():
        assert abs(float(np.linalg.norm(vec)) - 1.0) < 1e-6

    cal = wv.calibrate_distance_matrix(centroids)
    assert 0.0 < cal["p15"] < cal["p85"] <= cal["d_max"]
    for name_a in centroids:
        assert cal["calibrated"][name_a][name_a] == 0.0
        for name_b in centroids:
            val = cal["calibrated"][name_a][name_b]
            assert 0.0 <= val <= 1.0


def test_gaussian_cluster_weights_peak_near_target_distance():
    dist_map = {
        "Base": {"Base": 0.0, "Adj": 0.15, "Mid": 0.55, "Opp": 0.90},
    }
    low_w = wv.gaussian_cluster_weights("Base", dist_map, kappa_eff=0.15, d_max=1.0, exclude_base=True)
    mid_w = wv.gaussian_cluster_weights("Base", dist_map, kappa_eff=0.55, d_max=1.0, exclude_base=True)
    high_w = wv.gaussian_cluster_weights("Base", dist_map, kappa_eff=0.90, d_max=1.0, exclude_base=True)

    assert max(low_w, key=low_w.get) == "Adj"
    assert max(mid_w, key=mid_w.get) == "Mid"
    assert max(high_w, key=high_w.get) == "Opp"


def test_dimensional_binding_follows_five_kappa_bands():
    keys = ["setting", "lighting", "mechanism", "costume", "tonal_register"]

    # 0.00 - 0.15: Harmonic (all base)
    b_harm = wv.dimensional_binding_for_kappa(0.10, keys)
    assert set(b_harm.values()) == {"base"}

    # 0.25 - 0.35: Soft Accent (exactly 1 accent dimension from adjacent)
    b_soft = wv.dimensional_binding_for_kappa(0.30, keys, seed_draw=0)
    assert list(b_soft.values()).count("adjacent") == 1
    assert b_soft["setting"] == "base" and b_soft["costume"] == "base"

    # 0.50 - 0.65: Motivated Tension (setting/lighting in base; mechanism/costume in tension)
    b_tens = wv.dimensional_binding_for_kappa(0.58, keys)
    assert b_tens["setting"] == "base" and b_tens["lighting"] == "base"
    assert b_tens["mechanism"] == "tension" and b_tens["costume"] == "tension"

    # 0.70 - 0.85: Surreal Juxtaposition (setting/lighting adjacent; mechanism/costume opposite)
    b_surr = wv.dimensional_binding_for_kappa(0.78, keys)
    assert b_surr["setting"] == "adjacent" and b_surr["lighting"] == "adjacent"
    assert b_surr["mechanism"] == "opposite" and b_surr["costume"] == "opposite"

    # >= 0.90: Hot Bars (all maximal)
    b_hot = wv.dimensional_binding_for_kappa(0.95, keys)
    assert set(b_hot.values()) == {"maximal"}


def test_plan_gaussian_world_dissonance_is_pure_and_respects_grammar():
    from tests.test_vocab_select import _segment

    shots = [
        {"setting": "s0", "lighting": "l0", "mechanism": "m0", "costume": "c0"},
        {"setting": "s1", "lighting": "l1", "mechanism": "m1", "costume": "c1"},
    ]
    calm_seg = _segment(0, 0.08, "chaotic", shots)
    tension_seg = _segment(1, 0.58, "chaotic", shots)
    hot_seg = _segment(2, 0.95, "chaotic", shots)
    anchored_shots = [
        {"setting": "s0", "lighting": "l0", "mechanism": "fixed_clockwork", "costume": "c0"},
        {"setting": "s1", "lighting": "l1", "mechanism": "fixed_clockwork", "costume": "c1"},
    ]
    anchored_seg = _segment(3, 0.80, "thematic", anchored_shots, anchor="fixed_clockwork")

    segments = [calm_seg, tension_seg, hot_seg, anchored_seg]
    before = copy.deepcopy(segments)

    updates = vs.plan_gaussian_world_dissonance(
        segments, base_world="Bureaucratic / Carceral", seed=19, slider_percent=50.0
    )
    assert segments == before  # Pure: does not mutate input

    # Calm segment (kappa = 0.08 < 0.20) stays in harmonic band (no dissonance overrides)
    assert (0, 0) not in updates and (0, 1) not in updates

    # Tension segment (kappa = 0.58) keeps setting/lighting in base, overrides mechanism/costume
    _, v_tens = updates[(1, 0)]
    assert v_tens["setting"] == "s0" and v_tens["lighting"] == "l0"
    assert v_tens["mechanism"] != "m0" and v_tens["costume"] != "c0"

    # Hot Bars segment (kappa = 0.95 >= 0.90) overrides all dimensions simultaneously
    _, v_hot = updates[(2, 0)]
    assert v_hot["setting"] != "s0" and v_hot["lighting"] != "l0"
    assert v_hot["mechanism"] != "m0" and v_hot["costume"] != "c0"

    # Thematic segment with thematic_anchor preserves its anchored mechanism
    _, v_anch = updates[(3, 0)]
    assert v_anch["mechanism"] == "fixed_clockwork"
