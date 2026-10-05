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
    display: dict[str, float]  # expected_overlap, observed_overlap, pair_pval
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
    pvals = significance.permutation_gate(adj, cw, rings, ring_cfg, cfg.stats.n_perm, cfg.stats.perm_seed)
    if pvals and min(pvals) <= 1 / (cfg.stats.n_perm + 1) and cfg.stats.n_perm_max > cfg.stats.n_perm:
        pvals = significance.permutation_gate(adj, cw, rings, ring_cfg, cfg.stats.n_perm_max, cfg.stats.perm_seed)
    out = []
    for r, p_perm in zip(rings, pvals, strict=True):
        st = significance.display_stat(r, adj, k, H)
        out.append(Judged(r, st, p_perm, p_perm < cfg.stats.alpha,
                          lockstep.lockstep_ratio(g, r, cfg.time.delta_days, cfg.time.lockstep_share,
                                                  cfg.time.max_median_width_days)))
    return out
