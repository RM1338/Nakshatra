"""Ring-injection recall/precision (ALG §10.1 step 4, SRS-NF-7, PRD §10).

    python -m eval.run_injection --seed 7

Plants one crew per trial into each source graph (real cached runs + synthetic control cities) over the grid
ring size {5, 8, 12} x places {5, 8, 12} x camouflage {0, 0.3, 0.6}, then runs the shipped judge().
Recovered: a reported ring with user-Jaccard >= 0.5. Precision: share of reported rings that touch the plant
and match it; reported rings with no injected member are counted separately as "native".
"""
from __future__ import annotations

import argparse
import itertools
import time

import numpy as np

from eval.common import (
    Source,
    clone,
    eval_config,
    inject_ring,
    jaccard,
    out_path,
    real_sources,
    synthetic_source,
    write_json,
)
from nakshatra.algo.judge import judge

SIZES, PLACES, CAMO = (5, 8, 12), (5, 8, 12), (0.0, 0.3, 0.6)
# Stress grid (beyond the spec): 8 accounts x 8 places, camouflage 0.3, weaker coverage and more popular places.
COVERAGE, DP = (0.85, 0.6, 0.4), ((5, 60), (100, 400), (500, 2000))


def sources(n_synth: int, cfg) -> list[Source]:
    return real_sources(cfg=cfg) + [synthetic_source(100 + i, ring_size=0, cfg=cfg) for i in range(n_synth)]


def _trial(cells: dict, key: str, meta: dict, src: Source, cfg, rng, **inj) -> None:
    g = clone(src)
    users, _ = inject_ring(g, src.seed, rng=rng, T=src.T, tag=key, **inj)
    judged = [j for j in judge(g, src.seed, src.baseline_dps, cfg) if j.reported]
    touching = [j for j in judged if set(j.ring.users) & users]
    c = cells.setdefault(key, {**meta, "trials": 0, "recovered": 0, "reported_touching": 0,
                               "reported_matching": 0, "native": 0})
    c["trials"] += 1
    c["recovered"] += any(jaccard(set(j.ring.users), users) >= 0.5 for j in touching)
    c["reported_touching"] += len(touching)
    c["reported_matching"] += sum(jaccard(set(j.ring.users), users) >= 0.5 for j in touching)
    c["native"] += len(judged) - len(touching)


def _rates(cells: dict) -> None:
    for c in cells.values():
        c["recall"] = c["recovered"] / c["trials"]
        c["precision"] = c["reported_matching"] / c["reported_touching"] if c["reported_touching"] else None


def run(seed: int, n_synth: int) -> dict:
    cfg = eval_config()
    rng = np.random.default_rng(seed)
    srcs = sources(n_synth, cfg)
    cells: dict[str, dict] = {}
    stress: dict[str, dict] = {}
    for src in srcs:
        for n_u, n_p, camo in itertools.product(SIZES, PLACES, CAMO):
            _trial(cells, f"{n_u}x{n_p}x{camo}", {"n_users": n_u, "n_places": n_p, "camo": camo}, src, cfg, rng,
                   n_users=n_u, n_places=n_p, camo=camo)
        for cov, dp in itertools.product(COVERAGE, DP):
            _trial(stress, f"cov{cov}_dp{dp[0]}-{dp[1]}", {"coverage": cov, "dp_range": list(dp)}, src, cfg, rng,
                   n_users=8, n_places=8, camo=0.3, coverage=cov, dp_range=dp)
    _rates(cells)
    _rates(stress)
    big = [c for c in cells.values() if c["n_users"] >= 8]
    tp = sum(c["reported_matching"] for c in big)
    rep = sum(c["reported_touching"] for c in big)
    return {"seed": seed, "config_hash": cfg.hash(), "sources": [s.name for s in srcs],
            "cells": cells, "stress_8x8_camo0.3": stress,
            "summary_rings_ge_8": {"recall": sum(c["recovered"] for c in big) / sum(c["trials"] for c in big),
                                   "precision": tp / rep if rep else None, "targets": {"recall": 0.8, "precision": 0.8}}}


def plot(res: dict, cfg) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6), constrained_layout=True)
    for ax, camo in zip(axes, CAMO, strict=True):
        m = np.array([[res["cells"][f"{u}x{p}x{camo}"]["recall"] for p in PLACES] for u in SIZES])
        im = ax.imshow(m, vmin=0, vmax=1, cmap="viridis", origin="lower")
        ax.set_xticks(range(3), PLACES)
        ax.set_yticks(range(3), SIZES)
        ax.set_xlabel("shared places")
        ax.set_ylabel("ring size")
        ax.set_title(f"camouflage {camo}")
        for (i, j), v in np.ndenumerate(m):
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", color="w" if v < 0.6 else "k")
    fig.colorbar(im, ax=axes, label="recall")
    fig.suptitle(f"Injected-ring recall ({len(res['sources'])} source graphs, seed {res['seed']})")
    fig.savefig(out_path("injection_recall", cfg, "png"), dpi=130)
    fig, ax = plt.subplots(figsize=(5, 3.8), constrained_layout=True)
    m = np.array([[res["stress_8x8_camo0.3"][f"cov{c}_dp{d[0]}-{d[1]}"]["recall"] for d in DP] for c in COVERAGE])
    ax.imshow(m, vmin=0, vmax=1, cmap="viridis", origin="lower")
    ax.set_xticks(range(3), [f"{a}-{b}" for a, b in DP])
    ax.set_yticks(range(3), COVERAGE)
    ax.set_xlabel("reviews per shared place (d_p)")
    ax.set_ylabel("member coverage")
    ax.set_title("Stress: 8 accounts x 8 places, camouflage 0.3")
    for (i, j), v in np.ndenumerate(m):
        ax.text(j, i, f"{v:.2f}", ha="center", va="center", color="w" if v < 0.6 else "k")
    fig.savefig(out_path("injection_stress", cfg, "png"), dpi=130)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--synth", type=int, default=3, help="synthetic control cities used as extra source graphs")
    a = ap.parse_args(argv)
    t = time.time()
    res = run(a.seed, a.synth)
    cfg = eval_config()
    print("wrote", write_json("injection", cfg, res))
    plot(res, cfg)
    print(res["summary_rings_ge_8"], f"{time.time() - t:.0f}s")


if __name__ == "__main__":
    main()
