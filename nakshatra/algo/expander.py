"""Budgeted expansion policy (ALG §4.2, SRS §5.3). Decides who to fetch; the orchestrator fetches. Pure."""
from __future__ import annotations

import heapq
import math

from nakshatra.graph.model import Graph


class Expander:
    def __init__(self, g: Graph, s0: dict[int, float], hot_boost: float):
        self.g, self.beta = g, hot_boost
        self.s0 = dict(s0)
        self.heap: list[tuple[float, str, int]] = []  # (-priority, contributor_id, u): ties break by contributor_id
        self.done: set[int] = set()
        self.refined: set[int] = set()
        for u, s in s0.items():
            self.push(u, s, 0)

    def push(self, u: int, s0: float, n_hot: int) -> None:
        if u in self.done:
            return
        self.s0.setdefault(u, s0)
        heapq.heappush(self.heap, (-(s0 * (1 + self.beta * n_hot)), self.g.users[u].contributor_id, u))

    def pop(self) -> int | None:
        while self.heap:
            _, _, u = heapq.heappop(self.heap)
            if u not in self.done:
                self.done.add(u)
                return u
        return None

    def hot_places(self, seed: int) -> dict[int, int]:
        """Non-seed place -> number of expanded reviewers, for places with >= 2."""
        cnt: dict[int, int] = {}
        for u in self.done:
            for p in self.g.uadj[u]:
                if p != seed:
                    cnt[p] = cnt.get(p, 0) + 1
        return {p: n for p, n in cnt.items() if n >= 2}

    def next_refine(self, seed: int, prefer: list[int] | None = None) -> int | None:
        """Next place to refine. First the current best ring's places whose d_p is unknown (refinement is the d_p
        backfill, DECISIONS C3), most-shared first; otherwise the hot place maximising n / log(d_p + 5) (ALG §4.2)."""
        hot = {p: n for p, n in self.hot_places(seed).items() if p not in self.refined}
        ring = [p for p in (prefer or []) if p in hot and self.g.places[p].d_p is None]
        if ring:
            best = min(ring, key=lambda p: (-hot[p], p))
        elif hot:
            best = max(sorted(hot), key=lambda p: hot[p] / math.log((self.g.places[p].d_p or 50) + 5))
        else:
            return None
        self.refined.add(best)
        return best


class Plateau:
    """Stop when best density improved by < eps over the last `window` steps, including 0 -> 0 (DECISIONS A15)."""

    def __init__(self, eps: float, window: int):
        self.eps, self.window, self.hist = eps, window, []

    def update(self, best: float) -> bool:
        self.hist.append(best)
        if len(self.hist) <= self.window:
            return False
        old = self.hist[-self.window - 1]
        return best <= old * (1 + self.eps)
