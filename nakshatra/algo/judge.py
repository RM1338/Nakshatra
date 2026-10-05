"""The judgement phase as one pure function: mine -> Poisson display -> permutation gate -> lockstep (ALG §5-7).

Shared by the orchestrator and the evaluation harness, so the evaluation measures exactly what runs ship.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nakshatra.algo import lockstep, peel, significance
from nakshatra.graph.model import Graph


@dataclass
class Judged:
    ring: peel.Ring
    display: dict[str, float]  # expected_overlap (city Poisson), observed_overlap, pair_pval
    null_overlap: float        # mean shared places for these accounts in the permutation nulls (A22)
    p_perm: float
    reported: bool
    lockstep: float | None


def judge(g: Graph, seed: int, baseline_dps: list[int], cfg: Any) -> list[Judged]:
    """`cfg` is a settings.Config. Reported iff p_perm < α; the Poisson statistic is display-only (DECISIONS A1)."""
    ring_cfg = cfg.ring.model_dump()
    adj, cw = peel.build(g, seed)
    rings = peel.mine(adj, cw, **ring_cfg)
    d_ps = [p.d_p if p.d_p is not None else 50 for p in g.places] + list(baseline_dps)
    H = significance.city_concentration(d_ps, cfg.stats.mass_scale)
    k = {u: max(g.users[u].k_u or 0, len(g.uadj[u])) for u in adj}
    pvals, null_ov = significance.permutation_gate(adj, cw, rings, ring_cfg, cfg.stats.n_perm, cfg.stats.perm_seed)
    if pvals and min(pvals) <= 1 / (cfg.stats.n_perm + 1) and cfg.stats.n_perm_max > cfg.stats.n_perm:
        pvals, null_ov = significance.permutation_gate(adj, cw, rings, ring_cfg, cfg.stats.n_perm_max,
                                                       cfg.stats.perm_seed)
    out = []
    for r, p_perm, nov in zip(rings, pvals, null_ov, strict=True):
        st = significance.display_stat(r, adj, k, H)
        out.append(Judged(r, st, nov, p_perm, p_perm < cfg.stats.alpha,
                          lockstep.lockstep_ratio(g, r, cfg.time.delta_days, cfg.time.lockstep_share,
                                                  cfg.time.max_median_width_days)))
    return out


def overlap_summary(g: Graph, seed: int) -> dict:
    """What the crawl saw among followed reviewers, so a clean result still says something concrete:
    how many pairs were compared and the most other places any two had in common (seed excluded)."""
    users = sorted(u for u in range(len(g.users)) if g.users[u].expanded)
    places = {u: g.uadj[u] - {seed} for u in users}
    best = 0
    for i, u in enumerate(users):
        for v in users[i + 1:]:
            best = max(best, len(places[u] & places[v]))
    return {"pairs_compared": len(users) * (len(users) - 1) // 2, "max_shared_places": best}


def followed_reviewers(g: Graph, seed: int) -> list[dict]:
    """One row per followed reviewer: their activity and how much they overlap with the other followed reviewers."""
    users = sorted(u for u in range(len(g.users)) if g.users[u].expanded)
    places = {u: g.uadj[u] - {seed} for u in users}
    seen_by: dict[int, int] = {}
    for u in users:
        for p in places[u]:
            seen_by[p] = seen_by.get(p, 0) + 1
    rows = []
    for u in users:
        e = g.edges.get((u, seed))
        rows.append({"u": u, "reviews_total": max(g.users[u].k_u or 0, len(g.uadj[u])),
                     "local_guide": g.users[u].local_guide,
                     "rating_here": e.rating if e else None, "t_here": e.t_lo if e and e.exact else None,
                     "places_reviewed": len(places[u]),
                     "places_shared": sum(seen_by[p] >= 2 for p in places[u]),
                     "most_with_one": max((len(places[u] & places[v]) for v in users if v != u), default=0)})
    return rows
