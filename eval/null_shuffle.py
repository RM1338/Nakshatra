"""Null calibration of the permutation gate (SRS-NF-9, ALG §10.1): shuffle each source graph with degree-
preserving curveball swaps (no coordination by construction), run the shipped judge, and record the best
ring's p-value (1.0 when no ring passes the size test). The share below α should be about α or less.

    python -m eval.null_shuffle --n 200
"""
from __future__ import annotations

import argparse
import math

import numpy as np

from eval.common import eval_config, out_path, real_sources, synthetic_source, write_json
from nakshatra.algo import peel, significance
from nakshatra.algo.judge import judge
from nakshatra.graph.model import Edge, Graph


def shuffled(src, rng) -> Graph:
    adj, _ = peel.build(src.g, src.seed)
    null = significance.curveball(adj, rng)
    g = Graph()
    for U in src.g.users:
        g.users.append(U)
        g.uadj.append(set())
    for P in src.g.places:
        g.places.append(P)
        g.padj.append(set())
    g.uix, g.pix = src.g.uix, src.g.pix
    for u in src.g.padj[src.seed]:
        g.add_edge(src.g.edges[(u, src.seed)])
    for u in sorted(null):
        for p in sorted(null[u]):
            g.add_edge(Edge(u, p, 4.0, -math.inf, math.inf, False))
    return g


def run(n: int, n_synth: int, seed: int) -> dict:
    cfg = eval_config()
    rng = np.random.default_rng(seed)
    srcs = real_sources(cfg=cfg) + [synthetic_source(100 + i, ring_size=0, cfg=cfg) for i in range(n_synth)]
    ps = []
    for src in srcs:
        for _ in range(max(1, n // len(srcs))):
            judged = judge(shuffled(src, rng), src.seed, src.baseline_dps, cfg)
            ps.append(min([j.p_perm for j in judged], default=1.0))
    a = cfg.stats.alpha
    share = float(np.mean(np.array(ps) < a))
    return {"config_hash": cfg.hash(), "alpha": a, "n_null_graphs": len(ps), "sources": [s.name for s in srcs],
            "share_below_alpha": share, "target_band": [0.5 * a, 2 * a],
            "share_with_any_ring": float(np.mean(np.array(ps) < 1.0)), "pvalues": ps}


def plot(res: dict, cfg) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    p = np.sort(np.array(res["pvalues"]))
    q = (np.arange(1, len(p) + 1) - 0.5) / len(p)
    fig, ax = plt.subplots(figsize=(4.2, 4), constrained_layout=True)
    ax.plot(q, p, ".", ms=3, label="best ring per null graph (1.0 = no ring)")
    ax.plot([0, 1], [0, 1], "k--", lw=0.8, label="uniform")
    ax.axhline(res["alpha"], color="r", lw=0.8, label=f"α = {res['alpha']}")
    ax.set_xlabel("uniform quantile")
    ax.set_ylabel("permutation p")
    ax.set_title(f"Null calibration ({res['n_null_graphs']} shuffled graphs)")
    ax.legend(fontsize=7)
    fig.savefig(out_path("null_calibration", cfg, "png"), dpi=130)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--synth", type=int, default=3)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args(argv)
    res = run(a.n, a.synth, a.seed)
    cfg = eval_config()
    print("wrote", write_json("null_calibration", cfg, res))
    plot(res, cfg)
    print({k: res[k] for k in ("n_null_graphs", "share_below_alpha", "target_band", "share_with_any_ring")})


if __name__ == "__main__":
    main()
