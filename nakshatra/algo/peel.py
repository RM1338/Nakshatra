"""Popularity-weighted greedy peeling and ring trimming (ALG §5, FRAUDAR adapted). Pure."""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

from nakshatra.graph.model import Graph

Adj = dict[int, set[int]]


@dataclass
class Ring:
    users: list[int]
    places: list[int]
    density: float  # g(R ∪ Q) with popularity weights


def col_weight(d_p: int | None) -> float:
    return 1.0 / math.log((d_p if d_p is not None else 50) + 5)  # unknown d_p -> mid-popularity (DM §7)


def build(g: Graph, seed: int, drop_users: set[int] | None = None) -> tuple[Adj, dict[int, float]]:
    """User -> places adjacency with the seed removed, plus column weights from global d_p."""
    adj_u: Adj = {}
    for u in range(len(g.users)):
        if drop_users and u in drop_users:
            continue
        ps = g.uadj[u] - {seed}
        if ps:
            adj_u[u] = set(ps)
    c = {p: col_weight(g.places[p].d_p) for ps in adj_u.values() for p in ps}
    return adj_u, c


def _transpose(adj_u: Adj) -> Adj:
    adj_p: Adj = {}
    for u in sorted(adj_u):
        for p in adj_u[u]:
            adj_p.setdefault(p, set()).add(u)
    return adj_p


def peel_once(adj_u: Adj, adj_p: Adj, c: dict[int, float]) -> tuple[set[int], set[int], float]:
    """Remove the min weighted-degree node repeatedly; return the densest node set seen. Ties by (kind, index)."""
    wu = {u: sum(c[p] for p in ps) for u, ps in adj_u.items()}
    wp = {p: c[p] * len(us) for p, us in adj_p.items()}
    f, n = sum(wu.values()), len(wu) + len(wp)
    if n == 0:
        return set(), set(), 0.0
    heap = [(w, 0, u) for u, w in wu.items()] + [(w, 1, p) for p, w in wp.items()]
    heapq.heapify(heap)
    alive_u, alive_p = set(wu), set(wp)
    order: list[tuple[int, int]] = []
    best, best_k = f / n, 0
    while heap:
        w, kind, x = heapq.heappop(heap)
        if kind == 0:
            if x not in alive_u or wu[x] != w:
                continue
            alive_u.discard(x)
            for p in adj_u[x]:
                if p in alive_p:
                    wp[p] -= c[p]
                    heapq.heappush(heap, (wp[p], 1, p))
        else:
            if x not in alive_p or wp[x] != w:
                continue
            alive_p.discard(x)
            for u in adj_p[x]:
                if u in alive_u:
                    wu[u] -= c[x]
                    heapq.heappush(heap, (wu[u], 0, u))
        f -= w
        n -= 1
        order.append((kind, x))
        if n > 0 and f / n > best + 1e-12:
            best, best_k = f / n, len(order)
    removed = set(order[:best_k])
    return {u for u in adj_u if (0, u) not in removed}, {p for p in adj_p if (1, p) not in removed}, best


def trim(S_u: set[int], S_p: set[int], adj_u: Adj, adj_p: Adj, min_coverage: float) -> tuple[set[int], set[int]]:
    """Block -> ring: Q = places reviewed by >= 2 members; R = members covering >= min_coverage of Q; twice."""
    for _ in range(2):
        S_p = {p for p in S_p if len(adj_p[p] & S_u) >= 2}
        S_u = {u for u in S_u if S_p and len(adj_u[u] & S_p) / len(S_p) >= min_coverage}
    return S_u, S_p


def anchored(S_u: set[int], S_p: set[int], adj_u: Adj, adj_p: Adj, c: dict[int, float], min_users: int,
             min_places: int, min_coverage: float) -> tuple[set[int], set[int]] | None:
    """Fallback when a block fails trimming because bystanders dominate it (DECISIONS A20): for each block place
    with >= min_users block reviewers, trim starting from those reviewers; keep the densest valid ring."""
    best: tuple[float, list[int], set[int], set[int]] | None = None
    for p in sorted(S_p):
        start = adj_p[p] & S_u
        if len(start) < min_users:
            continue
        R, Q = trim(start, S_p, adj_u, adj_p, min_coverage)
        if len(R) >= min_users and len(Q) >= min_places:
            key = (ring_density(R, Q, adj_u, c), sorted(R))
            if best is None or key[0] > best[0] + 1e-12 or (abs(key[0] - best[0]) <= 1e-12 and key[1] < best[1]):
                best = (*key, R, Q)
    return (best[2], best[3]) if best else None


def ring_density(users: set[int], places: set[int], adj_u: Adj, c: dict[int, float]) -> float:
    n = len(users) + len(places)
    return sum(c[p] for u in users for p in adj_u[u] & places) / n if n else 0.0


def mine(adj_u: Adj, c: dict[int, float], min_users: int, min_places: int, min_coverage: float,
         max_rings: int) -> list[Ring]:
    """Up to max_rings disjoint rings, densest first.

    Each round peels the densest block and trims it (ALG §5.4). A block that trims to a ring loses only the ring's
    users (ALG: "remove R and peel again"). A block that fails trimming may still contain a crew merged with
    bystanders, so its densest anchored candidate is salvaged before the whole block is dropped (DECISIONS A20).
    """
    adj_u = {u: set(ps) for u, ps in adj_u.items()}
    adj_p = _transpose(adj_u)
    rings: list[Ring] = []
    for _ in range(max_rings * 3):  # bounded: also runs inside every permutation null
        if not adj_u:
            break
        S_u, S_p, _ = peel_once(adj_u, adj_p, c)
        if not S_u:
            break
        R, Q = trim(S_u, S_p, adj_u, adj_p, min_coverage)
        ok = len(R) >= min_users and len(Q) >= min_places
        if ok:
            rings.append(Ring(sorted(R), sorted(Q), ring_density(R, Q, adj_u, c)))
        elif found := anchored(S_u, S_p, adj_u, adj_p, c, min_users, min_places, min_coverage):
            rings.append(Ring(sorted(found[0]), sorted(found[1]), ring_density(*found, adj_u, c)))
        for u in (R if ok else S_u):
            for p in adj_u.pop(u):
                adj_p[p].discard(u)
                if not adj_p[p]:
                    del adj_p[p]
    rings.sort(key=lambda r: (-r.density, r.users))
    return rings[:max_rings]


def find_rings(g: Graph, seed: int, min_users: int, min_places: int, min_coverage: float,
               max_rings: int) -> list[Ring]:
    adj_u, c = build(g, seed)
    return mine(adj_u, c, min_users, min_places, min_coverage, max_rings)
