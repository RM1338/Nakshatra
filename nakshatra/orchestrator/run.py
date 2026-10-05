"""One investigation: state machine, budget phases, persistence and events (ARCH §5, LLD §7.2).

The only package that calls serp/, graph/, algo/, report/ and store/ together.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx

from nakshatra.algo import lockstep, peel, prior, rating
from nakshatra.algo.expander import Expander, Plateau
from nakshatra.algo.judge import judge
from nakshatra.errors import NakshatraError
from nakshatra.graph import ingest as I
from nakshatra.graph.model import Graph
from nakshatra.orchestrator.events import EventBus
from nakshatra.report import result as R
from nakshatra.serp import engines as E
from nakshatra.serp.budget import Budget
from nakshatra.serp.client import Response, SerpClient
from nakshatra.settings import Config, Env, load_config
from nakshatra.store.db import Store

log = logging.getLogger("nakshatra.run")

DATA_ID = re.compile(r"(0x[0-9a-f]+:0x[0-9a-f]+)", re.I)
PLACE_ID = re.compile(r"\b(ChIJ[0-9A-Za-z_-]{10,})")
FATAL = ("E_AUTH", "E_QUOTA")
MIN_SEED_REVIEWS = 20


def parse_place(s: str) -> tuple[str, str]:
    """('data_id', '0x..:0x..') or ('place_id', 'ChIJ..'); E_BAD_PLACE otherwise (SRS-IN-1)."""
    if m := DATA_ID.search(s or ""):
        return "data_id", m.group(1).lower()
    if m := PLACE_ID.search(s or ""):
        return "place_id", m.group(1)
    raise NakshatraError("E_BAD_PLACE", "No Google Maps place ID found in the input")


def _t(x: float) -> float | None:
    return x if math.isfinite(x) else None


class Run:
    def __init__(self, store: Store, cfg: Config, seed_input: str, budget: int, offline: bool, api_key: str,
                 http: httpx.AsyncClient | None = None, clock: Callable[[], float] = time.time,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep):
        if not cfg.budget.min <= budget <= cfg.budget.max:
            raise NakshatraError("E_BUDGET", f"budget must be between {cfg.budget.min} and {cfg.budget.max}")
        self.seed_kind, self.seed_ref = parse_place(seed_input)
        self.id = "r_" + uuid.uuid4().hex[:10]
        self.store, self.cfg, self.offline = store, cfg, offline
        self.started_at = time.time()
        store.run_create(self.id, seed_input, budget, offline, cfg.canonical_json(), cfg.hash(), self.started_at)
        self.budget = Budget(budget, cfg.budget.split)
        self.client = SerpClient(store, api_key, offline, self.id, self.budget, restrict=cfg.serp.json_restrictor,
                                 clock=clock, sleep=sleep, http=http)
        self.client.on_call = self._credit
        self.bus = EventBus(store, self.id)
        self.g = Graph()
        self.state = "created"
        self.seed: int | None = None
        self.baseline: list[dict] = []
        self.newest: dict[int, float] = {}  # user -> rating, from newestFirst pages only (ALG §7.2)
        self.ex: Expander | None = None
        self.low_coverage = False
        self.best_ring: peel.Ring | None = None
        self.cancel_requested = False
        self.skipped_non_google = 0
        self.result: dict | None = None

    # ---------- events ----------
    def _phase(self, s: str) -> None:
        self.state = s
        with self.store.tx():
            self.store.run_update(self.id, state=s)
            self.bus.emit("phase", {"phase": s, "ts": time.time()})

    def _credit(self) -> None:
        with self.store.tx():
            self.store.run_update(self.id, used=self.budget.billed)
            self.bus.emit("credit", {"used": self.budget.billed, "budget": self.budget.total,
                                     "cached": self.budget.cached})

    def _warn(self, code: str, message: str) -> None:
        self.bus.emit("warning", {"code": code, "message": message})

    def sid(self, u: int) -> str:
        """Stream pseudonym: S + first-seen order within this run (API §4.3)."""
        return f"S{u + 1}"

    def _persist(self, d: I.Delta, src: Response, user_role: str, place_role: str,
                 expanded: str | None = None) -> None:
        """Write what one response changed, then emit node/edge events, in one transaction."""
        g = self.g
        with self.store.tx():
            for p in d.places:
                P = g.places[p]
                self.store.upsert_place(P.data_id, place_id=P.place_id, title=P.title, type=P.type, lat=P.lat,
                                        lng=P.lng, rating=P.rating, d_p=P.d_p)
            for u in dict.fromkeys(d.users):
                U = g.users[u]
                self.store.upsert_user(U.contributor_id, k_u=U.k_u, photos=U.photos, local_guide=U.local_guide,
                                       level=U.level, points=U.points, truncated=U.truncated,
                                       expanded_at=src.fetched_at if U.contributor_id == expanded else None)
            for (u, p) in d.edges:
                e = g.edges[(u, p)]
                self.store.upsert_edge(g.users[u].contributor_id, g.places[p].data_id, e.rating, e.t_lo, e.t_hi,
                                       e.exact, e.review_id, e.source_hash)
            for p in d.new_places:
                P = g.places[p]
                role = "seed" if p == self.seed else place_role
                self.store.run_member(self.id, "place", P.data_id, role)
                self.bus.emit("node", {"id": P.data_id, "kind": "place", "label": P.title, "d_p": P.d_p,
                                       "role": role})
            for u in d.new_users:
                self.store.run_member(self.id, "user", g.users[u].contributor_id, user_role)
                self.bus.emit("node", {"id": self.sid(u), "kind": "user", "role": user_role})
            for (u, p) in d.edges:
                e = g.edges[(u, p)]
                self.bus.emit("edge", {"u": self.sid(u), "p": g.places[p].data_id, "rating": e.rating,
                                       "t_lo": _t(e.t_lo), "t_hi": _t(e.t_hi), "exact": e.exact})
            for f in d.drift:
                self.bus.emit("warning", {"code": "E_SCHEMA_DRIFT", "message": f"missing field {f}"})

    # ---------- lifecycle ----------
    async def execute(self) -> None:
        try:
            await self._resolve()
            await self._sample()
            await self._expand()
            await self._mine_and_report()
            with self.store.tx():
                self.store.run_update(self.id, state="done", ended_at=time.time())
                self.state = "done"
                self.bus.emit("phase", {"phase": "done", "ts": time.time()})
                self.bus.emit("done", {"run_id": self.id})
        except NakshatraError as e:
            self._fail(e.code, e.message)
        except Exception as e:  # noqa: BLE001 - surfaced as E_INTERNAL, logged with run_id
            log.exception("run %s crashed", self.id)
            self._fail("E_INTERNAL", type(e).__name__)
        finally:
            await self.client.aclose()

    def _fail(self, code: str, message: str) -> None:
        with self.store.tx():
            self.store.run_update(self.id, state="failed", ended_at=time.time(), error_code=code)
            self.state = "failed"
            self.bus.emit("phase", {"phase": "failed", "ts": time.time()})
            self.bus.emit("error", {"code": code, "message": message})

    async def _resolve(self) -> None:
        self._phase("resolving")
        tok = self.budget.reserve("sample")
        if self.seed_kind == "place_id":
            resp = await E.maps_place(self.client, tok, place_id=self.seed_ref)
        else:
            resp = await E.maps_place(self.client, tok, data_id=self.seed_ref)
        p, d = I.ingest_place(self.g, resp.data)
        if p is None:
            raise NakshatraError("E_BAD_PLACE", "SerpApi returned no place for this ID")
        self.seed = p
        self._persist(d, resp, "seed_reviewer", "seed")
        self.store.run_update(self.id, seed_data_id=self.g.places[p].data_id)
        S = self.g.places[p]
        if (S.d_p or 0) < MIN_SEED_REVIEWS:
            raise NakshatraError("E_TOO_FEW_REVIEWS", f"This place has only {S.d_p or 0} reviews")

        tok = self.budget.reserve("sample")
        if S.lat is None or S.lng is None or not (S.type or S.title):
            self._warn("E_SCHEMA_DRIFT", "seed has no coordinates or type; category baseline skipped")
            return
        try:
            resp = await E.maps_category(self.client, tok, S.type or S.title, S.lat, S.lng)
        except NakshatraError as e:
            if e.code in FATAL:
                raise
            self._warn(e.code, f"category baseline skipped: {e.message}")
            return
        self.baseline = [b for b in I.ingest_search(resp.data) if b["data_id"] != S.data_id]
        with self.store.tx():
            for b in self.baseline:
                gps = b.get("gps_coordinates") or {}
                self.store.upsert_place(b["data_id"], place_id=b.get("place_id"), title=b.get("title"),
                                        type=b.get("type"), lat=gps.get("latitude"), lng=gps.get("longitude"),
                                        rating=b.get("rating"), d_p=I._int(b.get("reviews")))
                self.store.run_member(self.id, "place", b["data_id"], "baseline")

    async def _sample(self) -> None:
        self._phase("sampling")
        S = self.g.places[self.seed]
        cursor: dict[str, str | None] = {"newestFirst": "", "ratingHigh": ""}  # "" = first page; None = exhausted
        while any(c is not None for c in cursor.values()) and not self.cancel_requested:
            for sort in ("newestFirst", "ratingHigh"):
                if cursor[sort] is None:
                    continue
                tok = self.budget.reserve("sample")
                if tok is None:
                    break
                try:
                    resp = await E.place_reviews(self.client, tok, S.data_id, sort, cursor[sort] or None)
                except NakshatraError as e:
                    if e.code in FATAL:
                        raise
                    self._warn(e.code, f"skipped a {sort} review page")
                    cursor[sort] = None
                    continue
                d = I.ingest_place_reviews(self.g, S.data_id, resp.data, resp.fetched_at, resp.params_hash)
                self.skipped_non_google += d.skipped
                if sort == "newestFirst":
                    for u in d.users:
                        self.newest.setdefault(u, self.g.edges[(u, self.seed)].rating)
                self._persist(d, resp, "seed_reviewer", "seed")
                cursor[sort] = (resp.data.get("serpapi_pagination") or {}).get("next_page_token")
            else:
                continue
            break
        self.budget.rollover("sample", "expand")

    async def _expand(self) -> None:
        self._phase("expanding")
        c, g = self.cfg, self.g
        s0 = prior.priors(g, self.seed, c.prior.weights)
        ex = self.ex = Expander(g, s0, c.expand.hot_boost, c.ring.min_places)
        plateau = Plateau(c.expand.plateau_eps, c.expand.plateau_window)
        n, stopped = 0, "queue"
        while not self.cancel_requested:
            if self.budget.left("expand", "refine") == 0:
                stopped = "budget"
                break
            u = ex.pop()
            if u is None:
                break
            tok = self.budget.reserve("expand" if self.budget.remaining["expand"] > 0 else "refine")
            cid = g.users[u].contributor_id
            try:
                resp = await E.contributor_reviews(self.client, tok, cid)
            except NakshatraError as e:
                if e.code in FATAL:
                    raise
                self._warn(e.code if e.code != "E_CACHE_MISS" else "E_UPSTREAM",
                           "Skipped one reviewer (SerpApi didn't respond). Continuing.")
                continue
            d = I.ingest_contributor(g, cid, resp.data, resp.fetched_at, resp.params_hash)
            self._persist(d, resp, "discovered", "discovered", expanded=cid)
            self.store.run_member(self.id, "user", cid, "expanded")
            if g.users[u].truncated:
                self._warn("E_TRUNCATED", f"{self.sid(u)} hit the 200-review cap")
            n += 1
            if n % c.expand.refine_every == 0 and self.budget.remaining["refine"] > 0:
                await self._refine(s0, "refine")
            best = await self._repeel()
            if plateau.update(best):
                stopped = "plateau"
                break
        self.low_coverage = self.cancel_requested or stopped == "budget"
        # Leftover credits buy d_p and exact dates for the best ring's places (DECISIONS C3).
        while self.best_ring and not self.cancel_requested and self.budget.left("expand", "refine") > 0:
            pool = "refine" if self.budget.remaining["refine"] > 0 else "expand"
            if not await self._refine(s0, pool, only_ring=True):
                break
            await self._repeel()

    async def _repeel(self) -> float:
        c, g = self.cfg, self.g
        rings = await asyncio.to_thread(peel.find_rings, g, self.seed, c.ring.min_users, c.ring.min_places,
                                        c.ring.min_coverage, 1)
        prev, self.best_ring = self.best_ring, rings[0] if rings else None
        if self.best_ring and (prev is None or (prev.users, prev.places, prev.density) !=
                               (self.best_ring.users, self.best_ring.places, self.best_ring.density)):
            self.bus.emit("ring_update", {"ring_idx": 0, "members": [self.sid(x) for x in self.best_ring.users],
                                          "places": [g.places[x].data_id for x in self.best_ring.places],
                                          "density": round(self.best_ring.density, 4)})
        return self.best_ring.density if self.best_ring else 0.0

    async def _refine(self, s0: dict[int, float], pool: str, only_ring: bool = False) -> bool:
        """Hot-place refinement: d_p, exact dates and new co-reviewers in one call (ALG §4.2, SRS-CR-6/7)."""
        ex, g = self.ex, self.g
        prefer = self.best_ring.places if self.best_ring else []
        if only_ring and not any(p not in ex.refined and g.places[p].d_p is None for p in prefer):
            return False
        p = ex.next_refine(self.seed, prefer)
        if p is None:
            return False
        self._phase("refining")
        tok = self.budget.reserve(pool)
        try:
            resp = await E.place_reviews(self.client, tok, g.places[p].data_id, "newestFirst", None)
        except NakshatraError as e:
            if e.code in FATAL:
                raise
            self._warn(e.code if e.code != "E_CACHE_MISS" else "E_UPSTREAM", "skipped a place refinement")
        else:
            d = I.ingest_place_reviews(g, g.places[p].data_id, resp.data, resp.fetched_at, resp.params_hash)
            self._persist(d, resp, "discovered", "refined")
            self.store.run_member(self.id, "place", g.places[p].data_id, "refined")
            hot = ex.hot_places(self.seed)
            for v in d.users:
                if g.edges[(v, p)].rating >= 4:
                    ex.push(v, s0.get(v, 0.5), len(g.uadj[v] & hot.keys()))
        self._phase("expanding")
        return True

    async def _mine_and_report(self) -> None:
        self._phase("mining")
        c, g = self.cfg, self.g
        base_dps = [I._int(b.get("reviews")) or 0 for b in self.baseline if b["data_id"] not in g.pix]
        judged = await asyncio.to_thread(judge, g, self.seed, base_dps, c)
        scored = [(j.ring, {**j.display, "null_overlap": j.null_overlap}, j.p_perm, j.reported, j.lockstep)
                  for j in judged]
        rings = [j.ring for j in judged]
        reported = [r for r, _, _, ok, _ in scored if ok]

        tot = sum(I._int(b.get("reviews")) or 0 for b in self.baseline)
        mu = (sum(float(b["rating"]) * (I._int(b.get("reviews")) or 0) for b in self.baseline) / tot) if tot else 4.0
        if not tot:
            self._warn("E_SCHEMA_DRIFT", "no category baseline; using 4.0 as the neighbourhood mean")
        newest = sorted(self.newest.items(), key=lambda x: g.users[x[0]].contributor_id)
        rat = await asyncio.to_thread(rating.adjusted_rating, newest, reported, mu, c.rating.kappa, c.rating.tau,
                                      c.rating.bootstrap_n, c.rating.bootstrap_seed)

        self._phase("reporting")
        S = g.places[self.seed]
        cids = [U.contributor_id for U in g.users]
        names = R.pseudonyms(self.ex.s0 if self.ex else {}, cids, [u for r in rings for u in r.users])
        out_rings = []
        for i, (r, st, p_perm, ok, lock) in enumerate(scored):
            out_rings.append({
                "idx": i, "members": [names[u] for u in sorted(r.users, key=lambda u: int(names[u][1:]))],
                "stream_members": [self.sid(u) for u in r.users],
                "places": [{"data_id": g.places[p].data_id, "title": g.places[p].title, "d_p": g.places[p].d_p}
                           for p in r.places],
                "density": round(r.density, 4), "expected_overlap": R.sig3(st["null_overlap"]),
                "poisson_expected": R.sig3(st["expected_overlap"]),
                "observed_overlap": R.sig3(st["observed_overlap"]), "pval": R.sig3(p_perm),
                "pair_pval": R.sig3(st["pair_pval"]), "lockstep_ratio": None if lock is None else round(lock, 3),
                "reported": ok, "evidence": self._evidence(r, names)})
        expanded = sum(1 for U in g.users if U.expanded)
        result = R.build(
            run_id=self.id,
            seed={"data_id": S.data_id, "title": S.title, "rating": S.rating, "d_p": S.d_p},
            credits={"budget": self.budget.total, "used": self.budget.billed, "cached": self.budget.cached},
            coverage={"reviewers_sampled": len(g.reviewers_of(self.seed)), "reviewers_expanded": expanded,
                      "places": len(g.places), "edges": len(g.edges), "low_coverage": self.low_coverage,
                      "non_google_skipped": self.skipped_non_google},
            rings=out_rings, rating={"displayed": S.rating, **rat}, config_hash=self.cfg.hash(),
            delta_days=c.time.delta_days)
        with self.store.tx():
            for (r, st, p_perm, ok, lock), o in zip(scored, out_rings, strict=True):
                self.store.ring_put(self.id, o["idx"], [cids[u] for u in r.users],
                                    [g.places[p].data_id for p in r.places], r.density, st["null_overlap"],
                                    st["observed_overlap"], p_perm, lock, ok)
                if ok:  # excerpts are kept only for ring members' ring-place reviews (DM §8)
                    for u in r.users:
                        for p in r.places:
                            if (u, p) in g.edges and g.edges[(u, p)].snippet:
                                self.store.set_excerpt(cids[u], g.places[p].data_id, g.edges[(u, p)].snippet)
            self.store.result_put(self.id, json.dumps(result, sort_keys=True, separators=(",", ":")))
        self.result = result

    def _evidence(self, r: peel.Ring, names: dict[int, str]) -> list[dict]:
        """Who reviewed which ring place, and when, with pseudonyms only (API §5.1; stored in the result)."""
        g, c = self.g, self.cfg
        locked = lockstep.place_lockstep(g, r, c.time.delta_days, c.time.lockstep_share)
        out = []
        for p in r.places:
            reviews = [{"member": names[u], "rating": g.edges[(u, p)].rating, "t_lo": _t(g.edges[(u, p)].t_lo),
                        "t_hi": _t(g.edges[(u, p)].t_hi), "exact": g.edges[(u, p)].exact}
                       for u in sorted(r.users, key=lambda u: int(names[u][1:])) if (u, p) in g.edges]
            out.append({"data_id": g.places[p].data_id, "title": g.places[p].title, "d_p": g.places[p].d_p,
                        "lockstep": locked[p], "reviews": reviews})
        return out

    def status(self) -> dict[str, Any]:
        row = self.store.run_get(self.id)
        return status_of(self.store, row)


def status_of(store: Store, row) -> dict[str, Any]:
    """RunStatus (API §3.2) from the persisted run row."""
    totals = store.ledger_totals(row["run_id"])
    err = None
    if row["error_code"]:
        last = store.conn.execute("SELECT payload_json FROM events WHERE run_id=? AND type='error' ORDER BY seq DESC"
                                  " LIMIT 1", (row["run_id"],)).fetchone()
        err = json.loads(last[0]) if last else {"code": row["error_code"], "message": ""}
    return {"run_id": row["run_id"], "state": row["state"], "started_at": row["started_at"],
            "ended_at": row["ended_at"], "credits": {"budget": row["budget"], "used": row["used"],
                                                     "cached": totals["cached"]},
            "error": err, "result": store.result_get(row["run_id"]), "partial": None}


async def run_once(place: str, budget: int, *, db: str | Path | None = None, offline: bool = False,
                   api_key: str | None = None, http: httpx.AsyncClient | None = None, now: float | None = None,
                   cfg: Config | None = None, store: Store | None = None) -> dict[str, Any]:
    """Run one investigation to completion (CLI, tests, fixtures). Returns RunStatus."""
    env = Env()
    store = store or Store(db or env.nakshatra_db)
    run = Run(store, cfg or load_config(), place, budget, offline or env.nakshatra_offline,
              env.serpapi_api_key if api_key is None else api_key, http=http,
              clock=(lambda: now) if now is not None else time.time)
    await run.execute()
    return run.status()
