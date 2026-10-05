"""Significance (ALG §6, revised): city-wide Poisson display statistic + selection-aware permutation gate. Pure."""
from __future__ import annotations

from itertools import combinations
from statistics import median

import numpy as np
from scipy.stats import poisson

from nakshatra.algo.peel import Adj, Ring, mine


def city_concentration(d_ps: list[int], scale: float) -> float:
    """H = Σ π_p², π_p = d_p / D, D = s · Σ d_p over every observed and baseline place (ALG §6.1)."""
    D = max(1.0, scale * sum(d_ps))
    return float(sum((d / D) ** 2 for d in d_ps))


def display_stat(ring: Ring, adj_u: Adj, k: dict[int, int], H: float) -> dict[str, float]:
    """Pairwise expected (λ = k_u k_v H) vs observed shared non-seed places, over the whole crawl."""
    lams, obs, ps = [], [], []
    for u, v in combinations(ring.users, 2):
        lam = k[u] * k[v] * H
        m = len(adj_u[u] & adj_u[v])
        lams.append(lam)
        obs.append(m)
        ps.append(float(poisson.sf(m - 1, lam)) if m > 0 else 1.0)
    if not ps:
        return {"expected_overlap": 0.0, "observed_overlap": 0.0, "pair_pval": 1.0}
    return {"expected_overlap": sum(lams) / len(lams), "observed_overlap": sum(obs) / len(obs),
            "pair_pval": float(median(ps))}


def curveball(adj_u: Adj, rng: np.random.Generator, trades_per_user: int = 5) -> Adj:
    """Degree-preserving rewiring (Strona et al. 2014). Every user and place keeps its degree."""
    users = sorted(adj_u)
    rows = [sorted(adj_u[u]) for u in users]
    sets = [set(r) for r in rows]
    n = len(users)
    if n < 2:
        return {u: set(adj_u[u]) for u in users}
    for _ in range(trades_per_user * n):
        a, b = rng.choice(n, size=2, replace=False)
        A, B = sets[a], sets[b]
        a_only, b_only = sorted(A - B), sorted(B - A)
        if not a_only or not b_only:
            continue
        pool = np.array(a_only + b_only)
        rng.shuffle(pool)
        k = len(a_only)
        shared = A & B
        sets[a] = shared | set(pool[:k].tolist())
        sets[b] = shared | set(pool[k:].tolist())
    return {u: sets[i] for i, u in enumerate(users)}


def permutation_gate(adj_u: Adj, c: dict[int, float], rings: list[Ring], ring_cfg: dict, n_perm: int,
                     seed: int) -> tuple[list[float], list[float]]:
    """p_i = (1 + #{null's i-th best ring density >= g_i}) / (N + 1), with the same miner on each null.

    Also returns, per ring, the mean number of places two of its accounts share in the null graphs: the
    "expected by chance" figure shown to users, from the same null that decides reporting (DECISIONS A22).
    """
    if not rings:
        return [], []
    rng = np.random.default_rng(seed)
    exceed = [0] * len(rings)
    shared = [0.0] * len(rings)
    pairs = [list(combinations(r.users, 2)) for r in rings]
    for _ in range(n_perm):
        g0 = curveball(adj_u, rng)
        null = mine(g0, c, **ring_cfg)
        for i, r in enumerate(rings):
            if i < len(null) and null[i].density >= r.density:
                exceed[i] += 1
            if pairs[i]:
                shared[i] += sum(len(g0[u] & g0[v]) for u, v in pairs[i]) / len(pairs[i])
    return [(1 + e) / (n_perm + 1) for e in exceed], [x / n_perm for x in shared]
