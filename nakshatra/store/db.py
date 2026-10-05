"""SQLite store (Data Model v2). One connection, writes only from the event-loop thread."""
from __future__ import annotations

import json
import math
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2
INF_DISK = 1e18  # SQLite has no infinity (DM §3)

EDGE_UPSERT = """
INSERT INTO edges (contributor_id, data_id, rating, t_lo, t_hi, exact, review_id, excerpt, minhash, source_hash, first_seen)
VALUES (:cid, :did, :rating, :lo, :hi, :exact, :rid, NULL, NULL, :src, :now)
ON CONFLICT(contributor_id, data_id) DO UPDATE SET
  t_lo        = CASE WHEN (excluded.exact = 1 AND edges.exact = 0)
                       OR (excluded.exact = 0 AND edges.exact = 0 AND excluded.t_hi - excluded.t_lo < edges.t_hi - edges.t_lo)
                     THEN excluded.t_lo ELSE edges.t_lo END,
  t_hi        = CASE WHEN (excluded.exact = 1 AND edges.exact = 0)
                       OR (excluded.exact = 0 AND edges.exact = 0 AND excluded.t_hi - excluded.t_lo < edges.t_hi - edges.t_lo)
                     THEN excluded.t_hi ELSE edges.t_hi END,
  source_hash = CASE WHEN (excluded.exact = 1 AND edges.exact = 0)
                       OR (excluded.exact = 0 AND edges.exact = 0 AND excluded.t_hi - excluded.t_lo < edges.t_hi - edges.t_lo)
                     THEN excluded.source_hash ELSE edges.source_hash END,
  exact       = MAX(edges.exact, excluded.exact),
  review_id   = COALESCE(edges.review_id, excluded.review_id),
  minhash     = COALESCE(edges.minhash, excluded.minhash)
"""

USER_UPSERT = """
INSERT INTO users (contributor_id, k_u, photos, local_guide, level, points, truncated, expanded_at)
VALUES (:cid, :k_u, :photos, :lg, :level, :points, :trunc, :exp)
ON CONFLICT(contributor_id) DO UPDATE SET
  k_u         = COALESCE(excluded.k_u, users.k_u),
  photos      = COALESCE(excluded.photos, users.photos),
  local_guide = MAX(users.local_guide, excluded.local_guide),
  level       = COALESCE(excluded.level, users.level),
  points      = COALESCE(excluded.points, users.points),
  truncated   = MAX(users.truncated, excluded.truncated),
  expanded_at = COALESCE(excluded.expanded_at, users.expanded_at)
"""

# d_p keeps the larger value when both observations fall within 1 hour (DM §5.1).
PLACE_UPSERT = """
INSERT INTO places (data_id, place_id, title, type, lat, lng, rating, d_p, observed_at)
VALUES (:did, :pid, :title, :type, :lat, :lng, :rating, :d_p, :now)
ON CONFLICT(data_id) DO UPDATE SET
  place_id    = COALESCE(excluded.place_id, places.place_id),
  title       = COALESCE(excluded.title, places.title),
  type        = COALESCE(excluded.type, places.type),
  lat         = COALESCE(excluded.lat, places.lat),
  lng         = COALESCE(excluded.lng, places.lng),
  rating      = COALESCE(excluded.rating, places.rating),
  d_p         = CASE WHEN excluded.d_p IS NULL THEN places.d_p
                     WHEN places.d_p IS NOT NULL AND excluded.observed_at - places.observed_at < 3600
                     THEN MAX(places.d_p, excluded.d_p)
                     ELSE excluded.d_p END,
  observed_at = excluded.observed_at
"""


def _disk(t: float) -> float:
    return max(-INF_DISK, min(INF_DISK, t)) if math.isinf(t) else t


def _mem(t: float) -> float:
    return math.inf if t >= INF_DISK else -math.inf if t <= -INF_DISK else t


class Store:
    def __init__(self, path: Path | str):
        path = Path(path)
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        if self.conn.execute("PRAGMA user_version").fetchone()[0] < SCHEMA_VERSION:
            self.conn.executescript((Path(__file__).parent / "schema.sql").read_text())
        else:
            self.conn.execute("PRAGMA foreign_keys = ON")
        self._depth = 0

    @contextmanager
    def tx(self) -> Iterator[None]:
        """Nestable transaction; only the outermost level commits."""
        if self._depth == 0:
            self.conn.execute("BEGIN")
        self._depth += 1
        try:
            yield
        except BaseException:
            self._depth -= 1
            if self._depth == 0:
                self.conn.execute("ROLLBACK")
            raise
        self._depth -= 1
        if self._depth == 0:
            self.conn.execute("COMMIT")

    def close(self) -> None:
        self.conn.close()

    # ---------- cache ----------
    def cache_get(self, h: str) -> tuple[dict[str, Any], float] | None:
        row = self.conn.execute("SELECT response_json, fetched_at FROM serp_cache WHERE params_hash=?", (h,)).fetchone()
        return (json.loads(row[0]), row[1]) if row else None

    def cache_put(self, h: str, engine: str, params: dict, resp: dict, fetched_at: float) -> None:
        self.conn.execute(
            "INSERT INTO serp_cache VALUES (?,?,?,?,?,?) ON CONFLICT DO NOTHING",
            (h, engine, json.dumps(params, sort_keys=True, separators=(",", ":")),
             json.dumps(resp, separators=(",", ":")), (resp.get("search_metadata") or {}).get("id"), fetched_at))

    def cache_search_id(self, h: str) -> str | None:
        row = self.conn.execute("SELECT search_id FROM serp_cache WHERE params_hash=?", (h,)).fetchone()
        return row[0] if row else None

    # ---------- ledger ----------
    def ledger_add(self, run_id: str, engine: str, h: str, pool: str | None, cached: bool, billed: bool,
                   ok: bool, latency_ms: int) -> None:
        self.conn.execute(
            "INSERT INTO ledger (run_id, engine, params_hash, pool, cached, billed, ok, latency_ms, ts)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (run_id, engine, h, pool, int(cached), int(billed), int(ok), latency_ms, time.time()))

    def ledger(self, run_id: str, after: int = 0, limit: int = 500) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT l.*, s.search_id FROM ledger l LEFT JOIN serp_cache s ON s.params_hash = l.params_hash"
            " WHERE l.run_id=? AND l.id>? ORDER BY l.id LIMIT ?", (run_id, after, limit)).fetchall()

    def ledger_totals(self, run_id: str) -> dict[str, Any]:
        r = self.conn.execute(
            "SELECT COALESCE(SUM(billed),0), COALESCE(SUM(cached),0), COALESCE(SUM(1-ok),0) FROM ledger WHERE run_id=?",
            (run_id,)).fetchone()
        pools = self.conn.execute(
            "SELECT pool, SUM(billed) FROM ledger WHERE run_id=? AND pool IS NOT NULL GROUP BY pool ORDER BY pool",
            (run_id,)).fetchall()
        return {"billed": r[0], "cached": r[1], "failed": r[2], "by_pool": {p: n for p, n in pools}}

    # ---------- runs ----------
    def run_create(self, run_id: str, seed_input: str, budget: int, offline: bool, config_json: str,
                   config_hash: str, started_at: float) -> None:
        self.conn.execute(
            "INSERT INTO runs (run_id, seed_input, budget, used, state, offline, config_json, config_hash, started_at)"
            " VALUES (?,?,?,0,'created',?,?,?,?)",
            (run_id, seed_input, budget, int(offline), config_json, config_hash, started_at))

    def run_update(self, run_id: str, **cols: Any) -> None:
        sets = ", ".join(f"{k}=?" for k in cols)
        self.conn.execute(f"UPDATE runs SET {sets} WHERE run_id=?", (*cols.values(), run_id))

    def run_get(self, run_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()

    def runs_list(self, limit: int = 20, before: float | None = None) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT r.*, p.title AS seed_title, (SELECT COUNT(*) FROM rings g WHERE g.run_id=r.run_id AND g.reported=1)"
            " AS rings_reported FROM runs r LEFT JOIN places p ON p.data_id = r.seed_data_id"
            " WHERE r.run_id <> 'r_0000000000' AND r.started_at < ? ORDER BY r.started_at DESC LIMIT ?",
            (before if before is not None else math.inf, limit)).fetchall()

    def run_member(self, run_id: str, kind: str, node_id: str, role: str) -> None:
        self.conn.execute("INSERT OR IGNORE INTO run_members VALUES (?,?,?,?)", (run_id, kind, node_id, role))

    # ---------- events ----------
    def event_append(self, run_id: str, seq: int, etype: str, payload: dict) -> None:
        self.conn.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                          (run_id, seq, etype, json.dumps(payload, separators=(",", ":")), time.time()))

    def events_since(self, run_id: str, after_seq: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT seq, type, payload_json FROM events WHERE run_id=? AND seq>? ORDER BY seq",
            (run_id, after_seq)).fetchall()

    # ---------- graph ----------
    def upsert_place(self, did: str, *, place_id: str | None = None, title: str | None = None,
                     type: str | None = None, lat: float | None = None, lng: float | None = None,
                     rating: float | None = None, d_p: int | None = None) -> None:
        self.conn.execute(PLACE_UPSERT, {"did": did, "pid": place_id, "title": title, "type": type, "lat": lat,
                                         "lng": lng, "rating": rating, "d_p": d_p, "now": time.time()})

    def upsert_user(self, cid: str, *, k_u: int | None = None, photos: int | None = None, local_guide: bool = False,
                    level: int | None = None, points: int | None = None, truncated: bool = False,
                    expanded_at: float | None = None) -> None:
        self.conn.execute(USER_UPSERT, {"cid": cid, "k_u": k_u, "photos": photos, "lg": int(local_guide),
                                        "level": level, "points": points, "trunc": int(truncated), "exp": expanded_at})

    def upsert_edge(self, cid: str, did: str, rating: float, t_lo: float, t_hi: float, exact: bool,
                    review_id: str | None, source_hash: str) -> None:
        self.conn.execute(EDGE_UPSERT, {"cid": cid, "did": did, "rating": rating, "lo": _disk(t_lo), "hi": _disk(t_hi),
                                        "exact": int(exact), "rid": review_id, "src": source_hash, "now": time.time()})

    def edge_get(self, cid: str, did: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM edges WHERE contributor_id=? AND data_id=?", (cid, did)).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["t_lo"], d["t_hi"] = _mem(d["t_lo"]), _mem(d["t_hi"])
        return d

    def set_excerpt(self, cid: str, did: str, excerpt: str) -> None:
        self.conn.execute("UPDATE edges SET excerpt=? WHERE contributor_id=? AND data_id=?", (excerpt[:280], cid, did))

    # ---------- rings / results ----------
    def ring_put(self, run_id: str, idx: int, members: list[str], places: list[str], density: float,
                 # members in pseudonym order (R1, R2, ...), aligned with the result's ring members (DECISIONS D12)
                 exp_overlap: float, obs_overlap: float, pval: float, lockstep_ratio: float | None,
                 reported: bool) -> None:
        self.conn.execute(
            "INSERT INTO rings VALUES (?,?,?,?,?,?,?,?,?,?)",
            (run_id, idx, json.dumps(members), json.dumps(sorted(places)), density, exp_overlap,
             obs_overlap, pval, lockstep_ratio, int(reported)))

    def result_put(self, run_id: str, result_json: str) -> None:
        self.conn.execute("INSERT INTO results VALUES (?,?)", (run_id, result_json))

    def result_get(self, run_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT result_json FROM results WHERE run_id=?", (run_id,)).fetchone()
        return json.loads(row[0]) if row else None
