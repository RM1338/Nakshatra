"""Shared evaluation plumbing: source graphs (cached real runs, synthetic city), injection, scoring, output paths.

All of it runs offline: real graphs are rebuilt from the SerpApi cache in a temporary copy of the DB.
"""
from __future__ import annotations

import asyncio
import copy
import json
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np

from nakshatra.graph.model import Edge, Graph
from nakshatra.orchestrator.run import Run
from nakshatra.settings import Config, Env, load_config
from nakshatra.store.db import Store

PLOTS = Path(__file__).parent / "plots"
DAY = 86400.0


@dataclass
class Source:
    name: str
    kind: str  # "real" | "synthetic"
    g: Graph
    seed: int
    baseline_dps: list[int]
    T: float


def eval_config() -> Config:
    """Exactly the shipped config: evaluation measures what runs report."""
    return load_config()


def _source_from_run(run: Run, name: str, kind: str) -> Source:
    base = [int(b.get("reviews") or 0) for b in run.baseline if b["data_id"] not in run.g.pix]
    T = max((e.t_hi for e in run.g.edges.values() if e.exact), default=0.0)
    return Source(name, kind, run.g, run.seed, base, T)


async def _replay(store: Store, place: str, budget: int, cfg: Config, http=None, api_key="") -> Run:
    run = Run(store, cfg, place, budget, offline=http is None, api_key=api_key, http=http)
    await run.execute()
    if run.state != "done":
        raise RuntimeError(f"replay of {place} ended in {run.state}")
    return run


def real_sources(db: Path | None = None, cfg: Config | None = None) -> list[Source]:
    """Every seed with a finished live run, rebuilt offline from the cache (0 credits)."""
    db = Path(db or Env().nakshatra_db)
    if not db.exists():
        return []
    rows = sqlite3.connect(db).execute(
        "SELECT seed_data_id, MAX(budget) FROM runs WHERE state='done' AND offline=0 AND seed_data_id IS NOT NULL"
        " GROUP BY seed_data_id ORDER BY seed_data_id").fetchall()
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copy(db, Path(tmp) / "eval.db")
        store = Store(Path(tmp) / "eval.db")
        for did, budget in rows:
            run = asyncio.run(_replay(store, did, budget, cfg or load_config()))
            out.append(_source_from_run(run, f"real:{did[-8:]}", "real"))
    return out


def synthetic_source(world_seed: int, ring_size: int = 0, budget: int = 60, cfg: Config | None = None) -> Source:
    from tests.synth_world import NOW, World
    w = World(seed=world_seed, ring_size=ring_size)
    http = httpx.AsyncClient(transport=w.transport())
    run = asyncio.run(_replay(Store(":memory:"), w.seed_data_id, budget, cfg or load_config(), http, "synthetic-eval"))
    src = _source_from_run(run, f"synth:{world_seed}", "synthetic")
    src.T = NOW
    return src


def inject_ring(g: Graph, seed: int, n_users: int, n_places: int, camo: float, rng: np.random.Generator,
                T: float, tag: str, coverage: float = 0.85,
                dp_range: tuple[int, int] = (5, 60)) -> tuple[set[int], set[int]]:
    """Plant a crew (LLD §9.1): new accounts that 5-star the seed and `coverage` of n_places new places
    (d_p in dp_range) within 10 days, plus camouflage edges to the 50 most popular places with probability camo/5."""
    places = []
    for j in range(n_places):
        p = g.place(f"inj:{tag}:p{j}")
        g.places[p].d_p = int(rng.integers(*dp_range))
        places.append(p)
    popular = sorted((p for p in range(len(g.places)) if p != seed), key=lambda p: -(g.places[p].d_p or 0))[:50]
    t0 = T - float(rng.integers(30, 400)) * DAY
    users = []
    for i in range(n_users):
        u = g.user(f"inj:{tag}:u{i}")
        U = g.users[u]
        U.k_u, U.photos, U.expanded = n_places + 3, 0, True
        users.append(u)
        t = t0 + float(rng.uniform(0, 10)) * DAY
        g.add_edge(Edge(u, seed, 5.0, t, t, True))
        for p in places:
            if rng.random() < coverage:
                tt = t0 + float(rng.uniform(0, 10)) * DAY
                g.add_edge(Edge(u, p, 5.0, tt - 15 * DAY, tt + 15 * DAY, False))
        for p in popular:
            if rng.random() < camo / 5:
                g.add_edge(Edge(u, p, float(rng.integers(3, 6)), t0, t0, True))
    return set(users), set(places)


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def clone(src: Source) -> Graph:
    return copy.deepcopy(src.g)


def out_path(name: str, cfg: Config, ext: str) -> Path:
    PLOTS.mkdir(parents=True, exist_ok=True)
    return PLOTS / f"{name}_{cfg.hash()[:8]}.{ext}"


def write_json(name: str, cfg: Config, data: dict) -> Path:
    p = out_path(name, cfg, "json")
    p.write_text(json.dumps(data, indent=1, sort_keys=True))
    return p
