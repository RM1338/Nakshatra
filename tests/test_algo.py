import math

import numpy as np
import pytest

from nakshatra.algo import lockstep, peel, prior, rating, significance
from nakshatra.algo.expander import Expander, Plateau
from nakshatra.graph.model import Edge, Graph
from tests.algo_fixtures import plant, random_graph

W = (-1.0, 2.0, 0.8, 0.5, 0.6, 0.7)
RING = {"min_users": 4, "min_places": 3, "min_coverage": 0.5, "max_rings": 5}


# ---------- prior (I2) ----------
def test_prior_monotone_in_k_and_local_guide_lowers():
    s = [prior.score(k, 5, 0, 0.0, False, W) for k in (1, 3, 10, 50, 300)]
    assert all(a >= b for a, b in zip(s, s[1:], strict=False))
    assert prior.score(10, 5, 0, 0, True, W) < prior.score(10, 5, 0, 0, False, W)
    assert 0 < prior.score(None, 1, 5, -3, True, W) < 1


def test_burst_z_flags_a_burst_day():
    g = Graph()
    s = g.place("0x1:0x1")
    for i in range(30):
        u = g.user(str(i))
        day = 100 if i < 10 else 100 + i
        g.add_edge(Edge(u, s, 5, day * 86400.0, day * 86400.0, True))
    z = prior.burst_z(g, s)
    assert z[g.uix["0"]] > 2 > z[g.uix["20"]]


# ---------- expander (I4) and plateau ----------
def test_expander_never_twice_and_ties_by_contributor_id():
    g = Graph()
    us = [g.user(c) for c in ("30", "10", "20")]
    ex = Expander(g, dict.fromkeys(us, 0.5), 0.5)
    ex.push(us[0], 0.5, 0)
    order = []
    while (u := ex.pop()) is not None:
        order.append(g.users[u].contributor_id)
        ex.push(u, 0.9, 3)  # re-push after expansion is ignored
    assert order == ["10", "20", "30"]


def test_hot_boost_reorders():
    g = Graph()
    a, b = g.user("1"), g.user("2")
    ex = Expander(g, {a: 0.6}, 0.5)
    ex.push(b, 0.5, 1)  # 0.5 * 1.5 = 0.75 > 0.6
    assert ex.pop() == b


def test_plateau():
    p = Plateau(0.02, 8)
    assert not any(p.update(1.0 + 0.1 * i) for i in range(12))
    p = Plateau(0.02, 8)
    assert [p.update(1.0) for _ in range(9)][-1]
    p = Plateau(0.02, 8)
    assert [p.update(0.0) for _ in range(9)][-1]  # 0 -> 0 stops (DECISIONS A15)


# ---------- peel (I5) ----------
def test_planted_ring_recovered_first():
    g, s = random_graph()
    users, places = plant(g, s)
    rings = peel.find_rings(g, s, **RING)
    assert rings and set(rings[0].users) == set(users) and set(rings[0].places) == set(places)


def test_sparse_random_graph_gives_no_ring():
    g, s = random_graph(seed=3)
    assert peel.find_rings(g, s, **RING) == []


def test_camouflaged_ring_still_recovered():
    g, s = random_graph(seed=4)
    users, _ = plant(g, s, camo=0.6)
    rings = peel.find_rings(g, s, **RING)
    assert rings and set(users) <= set(rings[0].users)


def test_seed_excluded_and_deterministic():
    g, s = random_graph(seed=5)
    plant(g, s)
    a = peel.find_rings(g, s, **RING)
    b = peel.find_rings(g, s, **RING)
    assert a == b and all(s not in r.places for r in a)


def test_two_rings():
    g, s = random_graph(seed=6)
    u1, _ = plant(g, s, rng_seed=1)
    g2_users = []
    for i in range(6):  # second crew on other obscure places
        u = g.user(str(800000 + i))
        g2_users.append(u)
        for j in range(5):
            p = g.place(f"0x{0xdd00 + j:x}:0x3")
            g.places[p].d_p = 20
            g.add_edge(Edge(u, p, 5.0, 0, 0, True))
    rings = peel.find_rings(g, s, **RING)
    found = [set(r.users) for r in rings]
    assert set(u1) in found and set(g2_users) in found


# ---------- significance ----------
def test_display_stat():
    adj = {0: {1, 2, 3}, 1: {1, 2, 3}, 2: {9}}
    ring = peel.Ring([0, 1], [1, 2, 3], 1.0)
    st = significance.display_stat(ring, adj, {0: 14, 1: 11}, 2e-3)
    assert st["observed_overlap"] == 3 and st["pair_pval"] < 0.01
    st = significance.display_stat(peel.Ring([0, 2], [], 0), adj, {0: 14, 2: 11}, 2e-3)
    assert st["observed_overlap"] == 0 and st["pair_pval"] == 1.0  # m = 0 -> p = 1


def test_power_users_unremarkable():
    ring = peel.Ring([0, 1], [], 0)
    adj = {0: set(range(58)), 1: set(range(58))}
    assert significance.display_stat(ring, adj, {0: 180, 1: 150}, 2e-3)["pair_pval"] > 0.2  # ALG §8 row 2


def test_city_concentration_worked_example():
    d = [5000] * 10 + [500] * 100 + [100] * 2890
    assert significance.city_concentration(d, 1.0) == pytest.approx(2.0e-3, rel=0.05)


def test_curveball_preserves_degrees():
    g, s = random_graph(seed=7)
    adj, _ = peel.build(g, s)
    null = significance.curveball(adj, np.random.default_rng(0))
    assert {u: len(p) for u, p in adj.items()} == {u: len(p) for u, p in null.items()}
    deg = lambda a: sorted((p, sum(p in ps for ps in a.values())) for p in {q for ps in a.values() for q in ps})
    assert deg(adj) == deg(null) and null != adj


def test_gate_passes_planted_ring():
    g, s = random_graph(seed=8)
    plant(g, s)
    adj, c = peel.build(g, s)
    rings = peel.mine(adj, c, **RING)
    p = significance.permutation_gate(adj, c, rings, RING, 60, seed=1)
    assert p[0] == pytest.approx(1 / 61)


def test_gate_calibrated_on_null_graphs():
    """On graphs with no planted structure, reported share stays near alpha (here alpha = 0.1)."""
    reported = 0
    for k in range(30):
        g, s = random_graph(n_users=60, n_places=80, seed=100 + k, mean_k=5)
        adj, c = peel.build(g, s)
        rings = peel.mine(adj, c, **RING)
        ps = significance.permutation_gate(adj, c, rings[:1], RING, 40, seed=k)
        reported += bool(ps and ps[0] < 0.1)
    assert reported <= 6  # 30 * 0.1 = 3 expected; generous binomial margin


# ---------- lockstep ----------
def test_max_cooccurring_exact():
    D = 14 * 86400.0
    assert lockstep.max_cooccurring([(0, 0), (D, D), (2 * D, 2 * D)], D) == 2
    assert lockstep.max_cooccurring([(0, 0), (D / 2, D / 2), (D, D)], D) == 3


def test_lockstep_ratio_cases():
    g, s = random_graph(seed=9)
    users, places = plant(g, s, spread_days=3)
    r = peel.Ring(users, places, 1.0)
    assert lockstep.lockstep_ratio(g, r, 14, 0.6, 30) >= 0.8
    g2, s2 = random_graph(seed=9)
    users, places = plant(g2, s2, spread_days=400)
    assert lockstep.lockstep_ratio(g2, peel.Ring(users, places, 1.0), 14, 0.6, 30) <= 0.2
    for (u, _p), e in g2.edges.items():
        if u in users:
            e.t_lo, e.t_hi, e.exact = e.t_lo - 60 * 86400, e.t_hi + 60 * 86400, False
    assert lockstep.lockstep_ratio(g2, peel.Ring(users, places, 1.0), 14, 0.6, 30) is None


# ---------- rating (I6) ----------
def test_rating_no_ring_invariant_and_ci():
    rng = np.random.default_rng(0)
    rs = [(i, float(rng.choice([3, 4, 5, 5]))) for i in range(80)]
    out = rating.adjusted_rating(rs, [], 4.2, 5, 1.0, 1000, 7)
    mean = sum(r for _, r in rs) / 80
    assert abs(out["adjusted"] - mean) <= 5 * abs(4.2 - mean) / 85 + 0.005
    assert out["ci"][0] <= out["adjusted"] <= out["ci"][1]
    assert out == rating.adjusted_rating(rs, [], 4.2, 5, 1.0, 1000, 7)


def test_rating_worked_example():
    rs = [(i, 5.0) for i in range(34)] + [(100 + i, 4.0) for i in range(46)]
    ring = peel.Ring(list(range(34)), [], 2.0)
    out = rating.adjusted_rating(rs, [ring], 4.2, 5, 1.0, 200, 7)
    assert out["adjusted"] == pytest.approx(205 / 51, abs=0.01) and out["set_aside"] == 34


def test_rating_empty():
    assert rating.adjusted_rating([], [], 4.0, 5, 1, 10, 7)["adjusted"] is None
    assert math.isclose(rating.membership_weights([peel.Ring([1], [], 0.5)], 1.0)[1], 0.5)
