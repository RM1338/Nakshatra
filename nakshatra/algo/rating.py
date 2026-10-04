"""Ring-adjusted recent rating (ALG §7.2): newestFirst sample, membership weights, shrinkage, bootstrap. Pure."""
from __future__ import annotations

import numpy as np

from nakshatra.algo.peel import Ring


def membership_weights(rings: list[Ring], tau: float) -> dict[int, float]:
    q: dict[int, float] = {}
    for r in rings:
        for u in r.users:
            q[u] = max(q.get(u, 0.0), min(1.0, r.density / tau))
    return q


def adjusted_rating(ratings: list[tuple[int, float]], reported: list[Ring], mu_cat: float, kappa: float,
                    tau: float, n_boot: int, seed: int) -> dict:
    """`ratings` = (user, stars) from newestFirst pages only, in a fixed order."""
    n = len(ratings)
    if n == 0:
        return {"adjusted": None, "ci": [None, None], "sample_mean": None, "n_sampled": 0, "set_aside": 0}
    q = membership_weights(reported, tau)
    r = np.array([s for _, s in ratings], dtype=float)
    w = np.array([1.0 - q.get(u, 0.0) for u, _ in ratings], dtype=float)

    def est(idx: np.ndarray) -> float:
        return float((np.dot(w[idx], r[idx]) + kappa * mu_cat) / (w[idx].sum() + kappa))

    rng = np.random.default_rng(seed)
    boots = np.array([est(rng.integers(0, n, n)) for _ in range(n_boot)])
    return {"adjusted": round(est(np.arange(n)), 2),
            "ci": [round(float(np.percentile(boots, 2.5)), 2), round(float(np.percentile(boots, 97.5)), 2)],
            "sample_mean": round(float(r.mean()), 2), "n_sampled": n,
            "set_aside": int(sum(1 for u, _ in ratings if q.get(u, 0.0) > 0))}
