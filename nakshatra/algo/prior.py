"""Reviewer prior s0(u) (ALG §4.1, SRS §5.2). A crawl heuristic, never a verdict. Pure."""
from __future__ import annotations

import math
from collections import Counter

from nakshatra.graph.model import Graph

DAY = 86400.0


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def burst_z(g: Graph, seed: int) -> dict[int, float]:
    """z-score of the seed's daily review count on each exact-dated reviewer's day, clipped to [-3, 3]."""
    days = {u: int(g.edges[(u, seed)].t_lo // DAY) for u in g.reviewers_of(seed) if g.edges[(u, seed)].exact}
    if len(days) < 5:
        return dict.fromkeys(days, 0.0)
    counts = Counter(days.values())
    xs = [counts.get(d, 0) for d in range(min(counts), max(counts) + 1)]
    mu = sum(xs) / len(xs)
    sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / len(xs)) or 1.0
    return {u: max(-3.0, min(3.0, (counts[d] - mu) / sd)) for u, d in days.items()}


def score(k_u: int | None, rating: float, photos: int | None, z: float, local_guide: bool,
          w: tuple[float, ...]) -> float:
    k = k_u if k_u is not None else 1
    x = (w[0] + w[1] / math.log(2 + k) + w[2] * (rating == 5) + w[3] * (photos == 0)
         + w[4] * z - w[5] * local_guide)
    return _sigmoid(x)


def priors(g: Graph, seed: int, w: tuple[float, ...]) -> dict[int, float]:
    z = burst_z(g, seed)
    return {u: score(g.users[u].k_u, g.edges[(u, seed)].rating, g.users[u].photos, z.get(u, 0.0),
                     g.users[u].local_guide, w)
            for u in g.reviewers_of(seed)}
