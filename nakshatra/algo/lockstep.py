"""Temporal lockstep via interval-graph maximum clique (ALG §7.1). Corroborating only; never gates. Pure."""
from __future__ import annotations

import math
from statistics import median

from nakshatra.algo.peel import Ring
from nakshatra.graph.model import Graph

DAY = 86400.0


def max_cooccurring(intervals: list[tuple[float, float]], delta: float) -> int:
    """Largest set of reviews pairwise within delta of each other (exact, interval-graph clique)."""
    ev = []
    for lo, hi in intervals:
        ev.append((lo - delta / 2, +1))
        ev.append((hi + delta / 2, -1))
    ev.sort(key=lambda x: (x[0], -x[1]))  # opens before closes at the same instant
    best = cur = 0
    for _, d in ev:
        cur += d
        best = max(best, cur)
    return best


def place_lockstep(g: Graph, ring: Ring, delta_days: float, share: float) -> dict[int, bool]:
    out = {}
    for p in ring.places:
        ivs = [(g.edges[(u, p)].t_lo, g.edges[(u, p)].t_hi) for u in ring.users
               if (u, p) in g.edges and math.isfinite(g.edges[(u, p)].t_lo)]
        out[p] = len(ivs) >= 2 and max_cooccurring(ivs, delta_days * DAY) / len(ivs) >= share
    return out


def lockstep_ratio(g: Graph, ring: Ring, delta_days: float, share: float, max_med_width_days: float) -> float | None:
    """Share of ring places in lockstep; None when the median interval is too wide to resolve timing."""
    widths = [g.edges[(u, p)].t_hi - g.edges[(u, p)].t_lo for u in ring.users for p in ring.places
              if (u, p) in g.edges]
    if not widths or not math.isfinite(median(widths)) or median(widths) > max_med_width_days * DAY:
        return None
    locked = place_lockstep(g, ring, delta_days, share)
    return sum(locked.values()) / len(ring.places)
