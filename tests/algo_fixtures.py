"""Small synthetic graphs for algorithm tests."""
from __future__ import annotations

import numpy as np

from nakshatra.graph.model import Edge, Graph


def random_graph(n_users=120, n_places=400, seed=0, mean_k=6) -> tuple[Graph, int]:
    """Seed place 0 reviewed by everyone; other edges drawn by heavy-tailed popularity."""
    rng = np.random.default_rng(seed)
    g = Graph()
    s = g.place("0x0:0x0")
    g.places[s].d_p = 300
    pop = rng.pareto(1.2, n_places) + 1
    for i in range(n_places):
        p = g.place(f"0x{i + 1:x}:0x1")
        g.places[p].d_p = int(min(5000, 10 * pop[i]))
    w = np.array([g.places[p].d_p for p in range(1, n_places + 1)], float)
    w /= w.sum()
    for j in range(n_users):
        u = g.user(str(1000 + j))
        k = int(max(1, rng.poisson(mean_k)))
        g.users[u].k_u = k
        g.add_edge(Edge(u, s, float(rng.choice([3, 4, 5])), 0, 0, True))
        for p in rng.choice(n_places, size=k, replace=False, p=w) + 1:
            g.add_edge(Edge(u, int(p), 4.0, 0, 0, True))
    return g, s


def plant(g: Graph, seed: int, n_users=8, n_places=6, camo=0.0, rng_seed=1, t0=1.7e9, spread_days=5.0):
    rng = np.random.default_rng(rng_seed)
    places = []
    for j in range(n_places):
        p = g.place(f"0x{0xabc00 + j:x}:0x2")
        g.places[p].d_p = int(rng.integers(10, 40))
        places.append(p)
    popular = sorted(range(len(g.places)), key=lambda p: -(g.places[p].d_p or 0))[:10]
    users = []
    for i in range(n_users):
        u = g.user(str(900000 + i))
        g.users[u].k_u = n_places + 2
        users.append(u)
        g.add_edge(Edge(u, seed, 5.0, t0, t0, True))
        for p in places:
            t = t0 + float(rng.uniform(0, spread_days)) * 86400
            g.add_edge(Edge(u, p, 5.0, t, t, True))
        for p in popular:
            if p != seed and rng.random() < camo:
                g.add_edge(Edge(u, p, 4.0, t0, t0, True))
    return users, places
