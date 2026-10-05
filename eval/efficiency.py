"""Credit efficiency (ALG §4.2, §10.1; SRS-NF-10): recall of a planted crew vs budget, for the shipped priority
crawl against BFS and random expansion, on synthetic cities served by the mock SerpApi.

    python -m eval.efficiency --worlds 3

A synthetic city is used because it is fully known; real runs cannot be repeated cheaply (LLD §9.1). The
plateau stop is disabled so every strategy spends exactly budget B.
"""
from __future__ import annotations

import argparse
import asyncio
import heapq
import itertools
import json

import httpx
import numpy as np

from eval.common import eval_config, out_path, write_json
from nakshatra.algo import expander as X
from nakshatra.orchestrator import run as RUN
from nakshatra.store.db import Store

BUDGETS = (20, 40, 60, 80, 100, 120)


class BFS(X.Expander):
    """Discovery order: every reviewer gets the same share of the budget."""

    def push(self, u, s0, n_hot):
        if u in self.done:
            return
        self.s0.setdefault(u, s0)
        heapq.heappush(self.heap, (len(self.heap) + len(self.done), 0.0, self.g.users[u].contributor_id, u))


class Random(X.Expander):
    def push(self, u, s0, n_hot):
        if u in self.done:
            return
        self.s0.setdefault(u, s0)
        r = np.random.default_rng(int(self.g.users[u].contributor_id[-9:])).random()
        heapq.heappush(self.heap, (r, 0.0, self.g.users[u].contributor_id, u))


STRATEGIES = {"priority": X.Expander, "bfs": BFS, "random": Random}


def one(world_seed: int, budget: int, strategy: str) -> bool:
    from tests.synth_world import NOW, World
    w = World(seed=world_seed)
    base = eval_config()
    cfg = base.model_copy(update={"expand": base.expand.model_copy(update={"plateau_window": 10_000})})
    store = Store(":memory:")
    RUN.Expander = STRATEGIES[strategy]
    try:
        asyncio.run(RUN.run_once(w.seed_data_id, budget, api_key="synthetic-eval-key", now=NOW, cfg=cfg,
                                 store=store, http=httpx.AsyncClient(transport=w.transport())))
    finally:
        RUN.Expander = X.Expander
    for (members,) in store.conn.execute("SELECT members_json FROM rings WHERE reported=1"):
        m = set(json.loads(members))
        if len(m & w.ring_cids) / len(m | w.ring_cids) >= 0.5:
            return True
    return False


def run(n_worlds: int) -> dict:
    curves = {s: {b: 0 for b in BUDGETS} for s in STRATEGIES}
    worlds = [300 + i for i in range(n_worlds)]
    for ws, b, s in itertools.product(worlds, BUDGETS, STRATEGIES):
        curves[s][b] += one(ws, b, s)
    rec = {s: {b: curves[s][b] / n_worlds for b in BUDGETS} for s in STRATEGIES}

    def first(s):
        return next((b for b in BUDGETS if rec[s][b] >= 0.8), None)
    return {"config_hash": eval_config().hash(), "worlds": worlds, "budgets": list(BUDGETS), "recall": rec,
            "credits_for_0.8_recall": {s: first(s) for s in STRATEGIES},
            "target": "priority reaches 0.8 recall with <= 50% of BFS credits"}


def plot(res: dict, cfg) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(5, 3.6), constrained_layout=True)
    for s, r in res["recall"].items():
        ax.plot(res["budgets"], [r[b] for b in res["budgets"]], marker="o", label=s)
    ax.axhline(0.8, color="k", lw=0.6, ls="--")
    ax.set_xlabel("SerpApi credits (budget B)")
    ax.set_ylabel("planted-crew recall")
    ax.set_ylim(-0.05, 1.05)
    ax.set_title(f"Credit efficiency ({len(res['worlds'])} synthetic cities)")
    ax.legend()
    fig.savefig(out_path("credit_efficiency", cfg, "png"), dpi=130)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--worlds", type=int, default=3)
    res = run(ap.parse_args(argv).worlds)
    cfg = eval_config()
    res["recall"] = {s: {str(b): v for b, v in r.items()} for s, r in res["recall"].items()}
    print("wrote", write_json("credit_efficiency", cfg, res))
    res["recall"] = {s: {int(b): v for b, v in r.items()} for s, r in res["recall"].items()}
    plot(res, cfg)
    print(res["recall"], res["credits_for_0.8_recall"])


if __name__ == "__main__":
    main()
