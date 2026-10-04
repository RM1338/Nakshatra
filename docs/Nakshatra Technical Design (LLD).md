# Nakshatra Technical Design (LLD)

Oct 4, 2026 · @Ronel Abraham Mathew

Low-level design for Nakshatra v1.0: module interfaces, data structures, schemas and reference code for every component in the System Architecture document. Code blocks are written to be pasted in and run, with tests named alongside.

## 1. Scope, layout, dependencies, conventions

This document covers every backend module down to function signatures and reference code, plus the frontend state model. It traces to the SRS by requirement ID.

### 1.1 Repository layout

```text
nakshatra/
  pyproject.toml
  Makefile
  config.yaml
  .env.example                # SERPAPI_API_KEY=
  nakshatra/
    __init__.py
    settings.py               # §2
    store/   db.py schema.sql repos.py            # §3
    serp/    client.py budget.py engines.py       # §4
    graph/   model.py ingest.py dates.py          # §5
    algo/    prior.py expander.py peel.py significance.py lockstep.py rating.py minhash.py  # §6
    orchestrator/ run.py events.py                # §7
    api/     main.py models.py routes.py sse.py   # §7
    report/  result.py templates.py dossier.py narrator.py  # §8
  eval/      inject.py run_injection.py controls.py null_shuffle.py plots/   # §9
  tests/     test_dates.py test_peel.py test_significance.py test_budget.py ...
  web/       (Vite + React + TS)                  # §8
  data/      demo.db
```

### 1.2 Dependencies

```toml
[project]
name = "nakshatra"
version = "1.0.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "httpx>=0.27",
  "pydantic>=2.7",
  "pydantic-settings>=2.3",
  "pyyaml>=6.0",
  "numpy>=1.26",
  "scipy>=1.13",
  "datasketch>=1.6",
  "markdown>=3.6",
  "weasyprint>=62",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23", "pytest-cov>=5", "networkx>=3.3", "matplotlib>=3.9", "ruff>=0.5"]
```

The client calls SerpApi's REST endpoint directly with `httpx`, not through the `serpapi` SDK. This gives full control over retries, timeouts and the ledger, and an async API.

### 1.3 Conventions

- **Types.** Code is fully type-hinted. `algo/` and `graph/` use only the standard library and numpy (CI lint: no `httpx`, `sqlite3` or `fastapi` imports there).
- **Identifiers.**
  - `PlaceId = str`, the Maps `data_id` (`0x..:0x..`).
  - `UserId = str`, the `contributor_id`.
  - Dense ints (`uix`, `pix`) are used only inside the in-memory graph.
- **Time.** Unix seconds as `float`, UTC. The run reference time `T` is `runs.started_at` and is never `time.time()` inside algorithms.
- **Randomness.** Only `numpy.random.default_rng(seed)`, with the seed passed explicitly.
- **Errors.** `NakshatraError(code: str, message: str)`. The codes come from SRS Appendix A.
- **Logging.** stdlib `logging` with a JSON formatter. Every record carries `run_id` via `contextvars`.

## 2. Configuration

Settings come from three layers, applied in order: environment variables (secrets and paths), `config.yaml` (algorithm parameters), and per-run overrides (budget only). The resolved config is frozen and stored in `runs.config_json`.

```python
# nakshatra/settings.py
from __future__ import annotations
from pathlib import Path
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml

class Env(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    serpapi_api_key: str = ""
    nakshatra_db: Path = Path("data/nakshatra.db")
    nakshatra_offline: bool = False
    nakshatra_host: str = "127.0.0.1"
    nakshatra_port: int = 8000

class BudgetCfg(BaseModel):
    default: int = 60
    min: int = 20
    max: int = 200
    split: tuple[float, float, float] = (0.20, 0.65, 0.15)  # sample, expand, refine

class PriorCfg(BaseModel):
    weights: tuple[float, float, float, float, float, float] = (-1.0, 2.0, 0.8, 0.5, 0.6, 0.7)

class ExpandCfg(BaseModel):
    hot_boost: float = 0.5
    refine_every: int = 5
    plateau_eps: float = 0.02
    plateau_window: int = 8
    backfill_cap: int = 5

class RingCfg(BaseModel):
    min_users: int = 4
    min_places: int = 3
    min_coverage: float = 0.5
    max_rings: int = 5

class StatsCfg(BaseModel):
    alpha: float = 0.01
    mass_scale: float = 1.0

class TimeCfg(BaseModel):
    delta_days: float = 14.0
    lockstep_share: float = 0.6
    max_median_width_days: float = 30.0

class RatingCfg(BaseModel):
    kappa: float = 5.0
    tau: float = 1.0
    bootstrap_n: int = 1000
    bootstrap_seed: int = 7

class Config(BaseModel):
    budget: BudgetCfg = Field(default_factory=BudgetCfg)
    prior: PriorCfg = Field(default_factory=PriorCfg)
    expand: ExpandCfg = Field(default_factory=ExpandCfg)
    ring: RingCfg = Field(default_factory=RingCfg)
    stats: StatsCfg = Field(default_factory=StatsCfg)
    time: TimeCfg = Field(default_factory=TimeCfg)
    rating: RatingCfg = Field(default_factory=RatingCfg)
    narrator_enabled: bool = False

    model_config = {"frozen": True}

def load_config(path: Path = Path("config.yaml")) -> Config:
    data = yaml.safe_load(path.read_text()) if path.exists() else {}
    return Config.model_validate(data or {})

ENV = Env()
```

```yaml
# config.yaml (defaults shown; edit after calibration, then freeze)
budget: {default: 60, min: 20, max: 200, split: [0.20, 0.65, 0.15]}
prior: {weights: [-1.0, 2.0, 0.8, 0.5, 0.6, 0.7]}
expand: {hot_boost: 0.5, refine_every: 5, plateau_eps: 0.02, plateau_window: 8, backfill_cap: 5}
ring: {min_users: 4, min_places: 3, min_coverage: 0.5, max_rings: 5}
stats: {alpha: 0.01, mass_scale: 1.0}
time: {delta_days: 14, lockstep_share: 0.6, max_median_width_days: 30}
rating: {kappa: 5, tau: 1.0, bootstrap_n: 1000, bootstrap_seed: 7}
narrator_enabled: false
```

## 3. Storage

One SQLite file in WAL mode. All writes go through a single `Store` object on the event loop thread. CPU-bound algorithm threads never write.

### 3.1 Schema

```sql
-- nakshatra/store/schema.sql
PRAGMA user_version = 1;
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS serp_cache (
  params_hash   TEXT PRIMARY KEY,
  engine        TEXT NOT NULL,
  params_json   TEXT NOT NULL,
  response_json TEXT NOT NULL,
  search_id     TEXT,
  fetched_at    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
  run_id        TEXT PRIMARY KEY,
  seed_input    TEXT NOT NULL,
  seed_data_id  TEXT,
  budget        INTEGER NOT NULL,
  used          INTEGER NOT NULL DEFAULT 0,
  state         TEXT NOT NULL,
  offline       INTEGER NOT NULL DEFAULT 0,
  config_json   TEXT NOT NULL,
  started_at    REAL NOT NULL,
  ended_at      REAL,
  error_code    TEXT
);

CREATE TABLE IF NOT EXISTS ledger (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id        TEXT NOT NULL REFERENCES runs(run_id),
  engine        TEXT NOT NULL,
  params_hash   TEXT NOT NULL,
  cached        INTEGER NOT NULL,      -- 1 = served from local cache, 0 = network
  billed        INTEGER NOT NULL,      -- 1 = counted against budget
  ok            INTEGER NOT NULL,
  latency_ms    INTEGER NOT NULL,
  ts            REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ledger_run ON ledger(run_id);

CREATE TABLE IF NOT EXISTS places (
  data_id       TEXT PRIMARY KEY,
  title         TEXT,
  type          TEXT,
  lat           REAL,
  lng           REAL,
  rating        REAL,
  d_p           INTEGER
);

CREATE TABLE IF NOT EXISTS users (
  contributor_id TEXT PRIMARY KEY,
  level          INTEGER,
  points         INTEGER,
  k_u            INTEGER,
  photos         INTEGER,
  local_guide    INTEGER,
  truncated      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS edges (
  contributor_id TEXT NOT NULL,
  data_id        TEXT NOT NULL,
  rating         REAL NOT NULL CHECK (rating BETWEEN 1 AND 5),
  t_lo           REAL NOT NULL,
  t_hi           REAL NOT NULL CHECK (t_lo <= t_hi),
  exact          INTEGER NOT NULL,
  review_id      TEXT,
  excerpt        TEXT,                  -- <= 280 chars, ring members only
  minhash        BLOB,
  source_hash    TEXT NOT NULL,         -- params_hash of the call that produced it
  PRIMARY KEY (contributor_id, data_id)
);

CREATE TABLE IF NOT EXISTS run_members (       -- which nodes a run touched
  run_id TEXT NOT NULL, kind TEXT NOT NULL, node_id TEXT NOT NULL,
  PRIMARY KEY (run_id, kind, node_id)
);

CREATE TABLE IF NOT EXISTS rings (
  run_id TEXT NOT NULL, idx INTEGER NOT NULL,
  members_json TEXT NOT NULL, places_json TEXT NOT NULL,
  density REAL, exp_overlap REAL, obs_overlap REAL, pval REAL,
  lockstep_ratio REAL, reported INTEGER NOT NULL,
  PRIMARY KEY (run_id, idx)
);

CREATE TABLE IF NOT EXISTS results (
  run_id TEXT PRIMARY KEY, result_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
  run_id TEXT NOT NULL, seq INTEGER NOT NULL, type TEXT NOT NULL,
  payload_json TEXT NOT NULL, ts REAL NOT NULL,
  PRIMARY KEY (run_id, seq)
);
```

**Edge merge rule.** An exact date beats a relative interval. A narrower interval beats a wider one.

```sql
INSERT INTO edges (...) VALUES (...)
ON CONFLICT(contributor_id, data_id) DO UPDATE SET
  t_lo = CASE WHEN excluded.exact = 1 OR (edges.exact = 0 AND excluded.t_hi - excluded.t_lo < edges.t_hi - edges.t_lo) THEN excluded.t_lo ELSE edges.t_lo END,
  t_hi = CASE WHEN excluded.exact = 1 OR (edges.exact = 0 AND excluded.t_hi - excluded.t_lo < edges.t_hi - edges.t_lo) THEN excluded.t_hi ELSE edges.t_hi END,
  exact = MAX(edges.exact, excluded.exact),
  review_id = COALESCE(edges.review_id, excluded.review_id);
```

### 3.2 Store API

```python
# nakshatra/store/db.py
from __future__ import annotations
import json, sqlite3, time
from pathlib import Path
from typing import Any, Iterator

class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript((Path(__file__).parent / "schema.sql").read_text())

    # cache
    def cache_get(self, h: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT response_json FROM serp_cache WHERE params_hash=?", (h,)).fetchone()
        return json.loads(row[0]) if row else None

    def cache_put(self, h: str, engine: str, params: dict, resp: dict) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO serp_cache VALUES (?,?,?,?,?,?)",
            (h, engine, json.dumps(params, sort_keys=True), json.dumps(resp),
             resp.get("search_metadata", {}).get("id"), time.time()))

    # ledger
    def ledger_add(self, run_id: str, engine: str, h: str, cached: bool, billed: bool, ok: bool, latency_ms: int) -> None:
        self.conn.execute(
            "INSERT INTO ledger (run_id, engine, params_hash, cached, billed, ok, latency_ms, ts) VALUES (?,?,?,?,?,?,?,?)",
            (run_id, engine, h, int(cached), int(billed), int(ok), latency_ms, time.time()))

    # events
    def event_append(self, run_id: str, seq: int, etype: str, payload: dict) -> None:
        self.conn.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                          (run_id, seq, etype, json.dumps(payload), time.time()))

    def events_since(self, run_id: str, after_seq: int) -> Iterator[sqlite3.Row]:
        yield from self.conn.execute(
            "SELECT seq, type, payload_json FROM events WHERE run_id=? AND seq>? ORDER BY seq",
            (run_id, after_seq))
```

Run, ring, result, place, user and edge repositories follow the same pattern in `repos.py`. Each is a thin function that takes `Store` and a dataclass.

## 4. serp/: SerpApi client

One choke point for cost (SRS-CR-9, OP-1 to OP-3, IF-10 to IF-14). A network call needs a budget token. A cache hit returns the token unspent.

### 4.1 Budget

```python
# nakshatra/serp/budget.py
from __future__ import annotations
from dataclasses import dataclass, field
import math

POOLS = ("sample", "expand", "refine")

@dataclass
class Token:
    pool: str
    spent: bool = False

@dataclass
class Budget:
    total: int
    split: tuple[float, float, float]
    used: int = 0
    remaining: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        s = math.ceil(self.total * self.split[0])
        e = math.floor(self.total * self.split[1])
        self.remaining = {"sample": s, "expand": e, "refine": self.total - s - e}

    def reserve(self, pool: str) -> Token | None:
        if self.remaining[pool] <= 0 or self.used >= self.total:
            return None
        self.remaining[pool] -= 1
        return Token(pool)

    def settle(self, tok: Token, billed: bool) -> None:
        if billed:
            tok.spent = True
            self.used += 1
        else:
            self.remaining[tok.pool] += 1   # cache hit: give it back

    def rollover(self, src: str, dst: str) -> None:
        self.remaining[dst] += self.remaining[src]
        self.remaining[src] = 0

    @property
    def left(self) -> int:
        return self.total - self.used
```

**Invariant (I3).** `used ≤ total`. It holds because `used` only increments in `settle`, each settle needs a reserved token, and reservations are bounded by the pools, which sum to `total`.

### 4.2 Client

```python
# nakshatra/serp/client.py
from __future__ import annotations
import asyncio, hashlib, json, time
import httpx
from nakshatra.serp.budget import Budget, Token
from nakshatra.store.db import Store

SERP_URL = "https://serpapi.com/search"

class NakshatraError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(f"{code}: {message}")
        self.code, self.message = code, message

def params_hash(engine: str, params: dict) -> str:
    canon = {k: v for k, v in params.items() if k != "api_key"}
    canon["engine"] = engine
    return hashlib.sha256(json.dumps(canon, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

class SerpClient:
    def __init__(self, store: Store, api_key: str, offline: bool, run_id: str):
        self.store, self.api_key, self.offline, self.run_id = store, api_key, offline, run_id
        self.http = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))

    async def get(self, engine: str, params: dict, budget: Budget | None, pool: str) -> tuple[dict, bool]:
        """Returns (json, from_cache). Raises NakshatraError on budget, auth, cache miss."""
        params = {"hl": "en", **params}
        h = params_hash(engine, params)
        t0 = time.perf_counter()

        cached = self.store.cache_get(h)
        if cached is not None:
            self.store.ledger_add(self.run_id, engine, h, True, False, True, 0)
            return cached, True
        if self.offline:
            raise NakshatraError("E_CACHE_MISS", f"{engine} {h[:8]}")

        tok: Token | None = budget.reserve(pool) if budget else None
        if budget and tok is None:
            raise NakshatraError("E_BUDGET_EXHAUSTED", pool)

        q = {**params, "engine": engine, "api_key": self.api_key}
        delay, last_exc = 1.0, None
        for attempt in range(4):                       # 1 try + 3 retries
            try:
                r = await self.http.get(SERP_URL, params=q)
            except httpx.TransportError as e:
                last_exc = e
            else:
                if r.status_code == 401:
                    if tok: budget.settle(tok, billed=False)
                    raise NakshatraError("E_AUTH", "SerpApi rejected the key")
                if r.status_code == 429 or r.status_code >= 500:
                    last_exc = NakshatraError("E_UPSTREAM", str(r.status_code))
                else:
                    data = r.json()
                    ok = data.get("search_metadata", {}).get("status") == "Success"
                    ms = int((time.perf_counter() - t0) * 1000)
                    if tok: budget.settle(tok, billed=True)   # conservative: any answered call is billed
                    self.store.ledger_add(self.run_id, engine, h, False, True, ok, ms)
                    if not ok:
                        if "run out of searches" in str(data.get("error", "")).lower():
                            raise NakshatraError("E_QUOTA", data["error"])
                        raise NakshatraError("E_UPSTREAM", str(data.get("error")))
                    self.store.cache_put(h, engine, {k: v for k, v in q.items() if k != "api_key"}, data)
                    return data, False
            if attempt < 3:
                await asyncio.sleep(delay); delay *= 2
        if tok: budget.settle(tok, billed=False)
        raise NakshatraError("E_UPSTREAM", repr(last_exc))

    async def aclose(self) -> None:
        await self.http.aclose()
```

### 4.3 Engine wrappers

```python
# nakshatra/serp/engines.py
from nakshatra.serp.client import SerpClient
from nakshatra.serp.budget import Budget

MAPS_PLACE_FIELDS = "place_results{data_id,place_id,title,type,rating,reviews,gps_coordinates}"
REVIEWS_FIELDS = ("place_info,reviews{review_id,rating,iso_date,iso_date_of_last_edit,snippet,"
                  "user{contributor_id,reviews,photos,local_guide}},serpapi_pagination")
CONTRIB_FIELDS = ("contributor{level,points,local_guide,contributions},"
                  "reviews{review_id,rating,date,snippet,place_info{data_id,title,type,gps_coordinates}}")

async def maps_place(c: SerpClient, b: Budget, data_id: str):
    return await c.get("google_maps", {"type": "place", "data": f"!4m5!3m4!1s{data_id}!8m2!3d0!4d0",
                                        "json_restrictor": MAPS_PLACE_FIELDS}, b, "sample")

async def maps_category(c: SerpClient, b: Budget, query: str, lat: float, lng: float):
    return await c.get("google_maps", {"type": "search", "q": query, "ll": f"@{lat},{lng},14z"}, b, "sample")

async def place_reviews(c: SerpClient, b: Budget, data_id: str, sort_by: str, token: str | None, pool: str):
    p = {"data_id": data_id, "sort_by": sort_by, "json_restrictor": REVIEWS_FIELDS}
    if token:
        p |= {"next_page_token": token, "num": 20}
    return await c.get("google_maps_reviews", p, b, pool)

async def contributor_reviews(c: SerpClient, b: Budget, contributor_id: str):
    return await c.get("google_maps_contributor_reviews",
                       {"contributor_id": contributor_id, "num": 200, "json_restrictor": CONTRIB_FIELDS}, b, "expand")
```

**Verify on day 1 in the playground:**

- The `google_maps` place lookup by `data_id` (the `data` parameter format above), versus passing `place_id`. Use whichever the docs confirm.
- The exact `json_restrictor` syntax. If it is wrong, drop the restrictor; correctness does not depend on it.
- Whether `place_info` in contributor reviews carries a review count (SRS OI-1).

## 5. graph/: model, ingest, dates

This package is pure. It turns engine JSON into an in-memory bipartite graph with integer indices and leaves persistence to the orchestrator.

### 5.1 Date intervals

```python
# nakshatra/graph/dates.py
from __future__ import annotations
import math, re
from datetime import datetime

DAY = 86400.0
UNIT_DAYS = {"day": 1.0, "week": 7.0, "month": 30.0, "year": 365.0}
REL = re.compile(r"^(?:edited\s+)?(a|an|\d+)\s+(day|week|month|year)s?\s+ago$", re.I)

def parse_iso(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()

def parse_interval(s: str | None, T: float) -> tuple[float, float, bool]:
    """Returns (t_lo, t_hi, exact). Unknown -> (-inf, +inf, False)."""
    if not s:
        return -math.inf, math.inf, False
    s = s.strip()
    if s[:4].isdigit() and "T" in s:
        t = parse_iso(s)
        return t, t, True
    m = REL.match(s)
    if not m:
        low = s.lower()
        if low in ("today", "just now") or "hour" in low or "minute" in low:
            return T - DAY, T, False
        return -math.inf, math.inf, False
    n = 1 if m.group(1).lower() in ("a", "an") else int(m.group(1))
    unit = m.group(2).lower()
    d = UNIT_DAYS[unit] * DAY
    if unit == "day":
        lo, hi = T - (n + 1) * d, T - n * d
    elif unit == "year":
        lo, hi = T - (n + 0.5) * d, T - n * d
    else:
        lo, hi = T - (n + 0.5) * d, T - max(n - 0.5, 0) * d
    return lo, hi, False

def gap(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distance between two intervals in seconds; 0 if they overlap."""
    return max(0.0, max(a[0], b[0]) - min(a[1], b[1]))
```

### 5.2 Graph model

```python
# nakshatra/graph/model.py
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np

@dataclass
class Place:
    data_id: str
    title: str = ""
    type: str = ""
    lat: float | None = None
    lng: float | None = None
    rating: float | None = None
    d_p: int | None = None            # global review count

@dataclass
class User:
    contributor_id: str
    k_u: int | None = None
    photos: int | None = None
    local_guide: bool = False
    level: int | None = None
    expanded: bool = False
    truncated: bool = False

@dataclass
class Edge:
    u: int
    p: int
    rating: float
    t_lo: float
    t_hi: float
    exact: bool
    review_id: str | None = None
    snippet: str = ""
    source_hash: str = ""

@dataclass
class Graph:
    users: list[User] = field(default_factory=list)
    places: list[Place] = field(default_factory=list)
    uix: dict[str, int] = field(default_factory=dict)
    pix: dict[str, int] = field(default_factory=dict)
    edges: dict[tuple[int, int], Edge] = field(default_factory=dict)

    def user(self, cid: str) -> int:
        if cid not in self.uix:
            self.uix[cid] = len(self.users); self.users.append(User(cid))
        return self.uix[cid]

    def place(self, data_id: str) -> int:
        if data_id not in self.pix:
            self.pix[data_id] = len(self.places); self.places.append(Place(data_id))
        return self.pix[data_id]

    def add_edge(self, e: Edge) -> bool:
        """Merge rule: exact beats relative; narrower beats wider. Returns True if new."""
        key = (e.u, e.p)
        old = self.edges.get(key)
        if old is None:
            self.edges[key] = e; return True
        if e.exact and not old.exact or (not old.exact and (e.t_hi - e.t_lo) < (old.t_hi - old.t_lo)):
            old.t_lo, old.t_hi, old.exact = e.t_lo, e.t_hi, e.exact
        old.review_id = old.review_id or e.review_id
        return False

    def reviewers_of(self, p: int) -> list[int]:
        return sorted(u for (u, q) in self.edges if q == p)

    def places_of(self, u: int) -> list[int]:
        return sorted(q for (v, q) in self.edges if v == u)

    def arrays(self, exclude_place: int | None = None) -> tuple[np.ndarray, np.ndarray]:
        keys = sorted(k for k in self.edges if k[1] != exclude_place)
        if not keys:
            return np.empty(0, np.int64), np.empty(0, np.int64)
        a = np.array(keys, dtype=np.int64)
        return a[:, 0], a[:, 1]
```

`reviewers_of` and `places_of` are O(|E|). At v1 scale (≤ 10k edges) this is fine. Add adjacency dicts if profiling says otherwise.

### 5.3 Ingest

```python
# nakshatra/graph/ingest.py
from __future__ import annotations
from nakshatra.graph.model import Graph, Edge
from nakshatra.graph.dates import parse_interval

def ingest_place(g: Graph, place_results: dict) -> int:
    p = g.place(place_results["data_id"]); pl = g.places[p]
    pl.title = place_results.get("title", pl.title)
    pl.type = place_results.get("type", pl.type)
    gps = place_results.get("gps_coordinates") or {}
    pl.lat, pl.lng = gps.get("latitude", pl.lat), gps.get("longitude", pl.lng)
    pl.rating = place_results.get("rating", pl.rating)
    pl.d_p = place_results.get("reviews", pl.d_p)
    return p

def ingest_place_reviews(g: Graph, data_id: str, resp: dict, T: float, source_hash: str) -> list[int]:
    """Returns user indices seen. Skips non-Google reviews (no contributor_id)."""
    p = g.place(data_id)
    if (pi := resp.get("place_info")) and g.places[p].d_p is None:
        g.places[p].d_p = pi.get("reviews")
    seen: list[int] = []
    for r in resp.get("reviews", []):
        usr = r.get("user") or {}
        cid = usr.get("contributor_id")
        if not cid or r.get("rating") is None:
            continue
        u = g.user(cid); U = g.users[u]
        U.k_u = usr.get("reviews", U.k_u)
        U.photos = usr.get("photos", U.photos)
        U.local_guide = bool(usr.get("local_guide", U.local_guide))
        lo, hi, exact = parse_interval(r.get("iso_date") or r.get("date"), T)
        g.add_edge(Edge(u, p, float(r["rating"]), lo, hi, exact, r.get("review_id"),
                        (r.get("snippet") or "")[:280], source_hash))
        seen.append(u)
    return seen

def ingest_contributor(g: Graph, cid: str, resp: dict, T: float, source_hash: str) -> list[int]:
    """Returns place indices that are new to the graph."""
    u = g.user(cid); U = g.users[u]
    c = resp.get("contributor") or {}
    U.level = c.get("level", U.level)
    U.local_guide = bool(c.get("local_guide", U.local_guide))
    U.k_u = (c.get("contributions") or {}).get("reviews", U.k_u)
    reviews = resp.get("reviews", [])
    U.expanded, U.truncated = True, len(reviews) >= 200
    new_places: list[int] = []
    for r in reviews:
        pi = r.get("place_info") or {}
        did = pi.get("data_id")
        if not did or r.get("rating") is None:
            continue
        before = did in g.pix
        p = ingest_place(g, pi)
        if not before:
            new_places.append(p)
        lo, hi, exact = parse_interval(r.get("date"), T)
        g.add_edge(Edge(u, p, float(r["rating"]), lo, hi, exact, r.get("review_id"),
                        (r.get("snippet") or "")[:280], source_hash))
    return new_places
```

## 6. algo/: detection core

All functions are pure, deterministic and side-effect free. Ties always break on index order, so equal inputs produce byte-equal outputs.

### 6.1 Prior

```python
# nakshatra/algo/prior.py
from __future__ import annotations
import math
from collections import Counter
from nakshatra.graph.model import Graph

DAY = 86400.0

def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))

def burst_z(g: Graph, seed: int) -> dict[int, float]:
    """z-score of the seed's daily review count, per exact-dated reviewer. Clipped to [-3, 3]."""
    days = {u: int(e.t_lo // DAY) for (u, p), e in g.edges.items() if p == seed and e.exact}
    if len(days) < 5:
        return {u: 0.0 for u in days}
    counts = Counter(days.values())
    span = range(min(counts), max(counts) + 1)
    xs = [counts.get(d, 0) for d in span]
    mu = sum(xs) / len(xs)
    sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / len(xs)) or 1.0
    return {u: max(-3.0, min(3.0, (counts[d] - mu) / sd)) for u, d in days.items()}

def priors(g: Graph, seed: int, w: tuple[float, ...]) -> dict[int, float]:
    z = burst_z(g, seed)
    out: dict[int, float] = {}
    for u in g.reviewers_of(seed):
        U, e = g.users[u], g.edges[(u, seed)]
        k = U.k_u if U.k_u is not None else 1
        x = (w[0] + w[1] / math.log(2 + k) + w[2] * (e.rating == 5)
             + w[3] * (U.photos == 0) + w[4] * z.get(u, 0.0) - w[5] * U.local_guide)
        out[u] = _sigmoid(x)
    return out
```

### 6.2 Expander (priority policy)

The expander decides *who* to fetch next. The orchestrator does the fetching.

```python
# nakshatra/algo/expander.py
from __future__ import annotations
import heapq, math
from nakshatra.graph.model import Graph

class Expander:
    def __init__(self, s0: dict[int, float], hot_boost: float):
        self.s0, self.beta = dict(s0), hot_boost
        self.heap: list[tuple[float, int]] = []
        self.done: set[int] = set()
        self.refined: set[int] = set()
        for u, s in s0.items():
            heapq.heappush(self.heap, (-s, u))

    def push(self, u: int, s0: float, n_hot: int) -> None:
        if u in self.done:
            return
        self.s0.setdefault(u, s0)
        heapq.heappush(self.heap, (-(s0 * (1 + self.beta * n_hot)), u))

    def pop(self) -> int | None:
        while self.heap:
            _, u = heapq.heappop(self.heap)
            if u not in self.done:
                self.done.add(u)
                return u
        return None

    def hot_places(self, g: Graph, seed: int) -> dict[int, int]:
        """place -> number of expanded reviewers, for places with >= 2."""
        cnt: dict[int, int] = {}
        for (u, p) in g.edges:
            if p != seed and u in self.done:
                cnt[p] = cnt.get(p, 0) + 1
        return {p: n for p, n in cnt.items() if n >= 2}

    def next_refine(self, g: Graph, seed: int) -> int | None:
        hot = {p: n for p, n in self.hot_places(g, seed).items() if p not in self.refined}
        if not hot:
            return None
        best = max(sorted(hot), key=lambda p: hot[p] / math.log((g.places[p].d_p or 0) + 5))
        self.refined.add(best)
        return best

class Plateau:
    def __init__(self, eps: float, window: int):
        self.eps, self.window, self.hist = eps, window, []

    def update(self, best_density: float) -> bool:
        """Returns True when the run should stop."""
        self.hist.append(best_density)
        if len(self.hist) <= self.window:
            return False
        old = self.hist[-self.window - 1]
        return old > 0 and (best_density - old) / old < self.eps
```

### 6.3 Weighted peeling

```python
# nakshatra/algo/peel.py
from __future__ import annotations
import heapq, math
from dataclasses import dataclass
from lockstep.graph.model import Graph

@dataclass
class Ring:
    users: list[int]
    places: list[int]
    density: float

def col_weight(d_p: int | None) -> float:
    return 1.0 / math.log((d_p if d_p is not None else 50) + 5)   # unknown d_p -> treat as mid-popularity

def _peel_once(adj_u: dict[int, set[int]], adj_p: dict[int, set[int]], c: dict[int, float]):
    wu = {u: sum(c[p] for p in ps) for u, ps in adj_u.items()}
    wp = {p: c[p] * len(us) for p, us in adj_p.items()}
    f = sum(wu.values())
    n = len(wu) + len(wp)
    if n == 0:
        return set(), set(), 0.0
    heap = [(w, 0, u) for u, w in wu.items()] + [(w, 1, p) for p, w in wp.items()]
    heapq.heapify(heap)
    alive_u, alive_p = set(wu), set(wp)
    order: list[tuple[int, int]] = []
    best, best_k = f / n, 0
    while heap:
        w, kind, x = heapq.heappop(heap)
        cur = wu.get(x) if kind == 0 else wp.get(x)
        if (kind == 0 and x not in alive_u) or (kind == 1 and x not in alive_p) or cur != w:
            continue                                  # stale entry
        if kind == 0:
            alive_u.discard(x)
            for p in adj_u[x]:
                if p in alive_p:
                    wp[p] -= c[p]; heapq.heappush(heap, (wp[p], 1, p))
            f -= w
        else:
            alive_p.discard(x)
            for u in adj_p[x]:
                if u in alive_u:
                    wu[u] -= c[x]; heapq.heappush(heap, (wu[u], 0, u))
            f -= w
        order.append((kind, x))
        n -= 1
        if n > 0 and f / n > best + 1e-12:
            best, best_k = f / n, len(order)
    removed = set(order[:best_k])
    S_u = {u for u in adj_u if (0, u) not in removed}
    S_p = {p for p in adj_p if (1, p) not in removed}
    return S_u, S_p, best

def find_rings(g: Graph, seed: int, min_users: int, min_places: int,
               min_coverage: float, max_rings: int) -> list[Ring]:
    adj_u: dict[int, set[int]] = {}
    adj_p: dict[int, set[int]] = {}
    for (u, p) in sorted(g.edges):
        if p == seed:
            continue
        adj_u.setdefault(u, set()).add(p); adj_p.setdefault(p, set()).add(u)
    c = {p: col_weight(g.places[p].d_p) for p in adj_p}
    rings: list[Ring] = []
    while len(rings) < max_rings and adj_u:
        S_u, S_p, dens = _peel_once(adj_u, adj_p, c)
        if not S_u:
            break
        # ring places: reviewed by >= 2 members; then trim low-coverage members (2 passes)
        for _ in range(2):
            S_p = {p for p in S_p if len(adj_p[p] & S_u) >= 2}
            S_u = {u for u in S_u if S_p and len(adj_u[u] & S_p) / len(S_p) >= min_coverage}
        if len(S_u) >= min_users and len(S_p) >= min_places:
            rings.append(Ring(sorted(S_u), sorted(S_p), dens))
        # remove peeled users (ring or not) to find the next dense block
        for u in S_u or set(list(adj_u)[:1]):
            for p in adj_u.pop(u, set()):
                adj_p[p].discard(u)
                if not adj_p[p]:
                    del adj_p[p]
        if not S_u:
            break
    return rings
```

Complexity is O(|E| log |V|) per ring. A planted 8×6 biclique on low-d\_p places is recovered first (test `test_peel_planted`).

### 6.4 Significance

```python
# lockstep/algo/significance.py
from __future__ import annotations
from itertools import combinations
from statistics import median
from scipy.stats import poisson
from lockstep.graph.model import Graph
from lockstep.algo.peel import Ring

def city_mass(g: Graph, baseline_dp: list[int], scale: float) -> float:
    total = sum(p.d_p for p in g.places if p.d_p) + sum(baseline_dp)
    return max(1.0, scale * total)

def ring_significance(g: Graph, ring: Ring, D: float, n_tests: int) -> dict:
    Q = set(ring.places)
    pi2 = sum(((g.places[p].d_p or 50) / D) ** 2 for p in Q)
    pvals, lams, obs = [], [], []
    for u, v in combinations(ring.users, 2):
        ku = max(g.users[u].k_u or 0, len(g.places_of(u)))
        kv = max(g.users[v].k_u or 0, len(g.places_of(v)))
        lam = ku * kv * pi2
        m = len(set(g.places_of(u)) & set(g.places_of(v)) & Q)
        pvals.append(float(poisson.sf(m - 1, lam)) if m > 0 else 1.0)
        lams.append(lam); obs.append(m)
    if not pvals:
        return {"pval": 1.0, "expected_overlap": 0.0, "observed_overlap": 0.0}
    return {
        "pval": min(1.0, median(pvals) * max(1, n_tests)),
        "expected_overlap": sum(lams) / len(lams),
        "observed_overlap": sum(obs) / len(obs),
    }
```

### 6.5 Lockstep ratio

```python
# lockstep/algo/lockstep.py
from __future__ import annotations
import math
from statistics import median
from lockstep.graph.model import Graph
from lockstep.graph.dates import gap
from lockstep.algo.peel import Ring

DAY = 86400.0

def lockstep_ratio(g: Graph, ring: Ring, delta_days: float, share: float, max_med_width_days: float) -> float | None:
    members = set(ring.users)
    widths = [e.t_hi - e.t_lo for (u, p), e in g.edges.items()
              if u in members and p in ring.places and math.isfinite(e.t_lo)]
    if not widths or median(widths) > max_med_width_days * DAY:
        return None
    locked = 0
    for p in ring.places:
        ivs = [(g.edges[(u, p)].t_lo, g.edges[(u, p)].t_hi) for u in ring.users
               if (u, p) in g.edges and math.isfinite(g.edges[(u, p)].t_lo)]
        if len(ivs) < 2:
            continue
        best = max(sum(1 for b in ivs if gap(a, b) <= delta_days * DAY) for a in ivs)
        if best / len(ivs) >= share:
            locked += 1
    return locked / len(ring.places)
```

### 6.6 Adjusted rating

```python
# lockstep/algo/rating.py
from __future__ import annotations
import numpy as np
from lockstep.graph.model import Graph
from lockstep.algo.peel import Ring

def membership_weights(rings: list[Ring], tau: float) -> dict[int, float]:
    q: dict[int, float] = {}
    for r in rings:
        for u in r.users:
            q[u] = max(q.get(u, 0.0), min(1.0, r.density / tau))
    return q

def adjusted_rating(g: Graph, seed: int, reported: list[Ring], mu_cat: float,
                    kappa: float, tau: float, n_boot: int, rng_seed: int) -> dict:
    us = g.reviewers_of(seed)
    r = np.array([g.edges[(u, seed)].rating for u in us], dtype=float)
    q = membership_weights(reported, tau)
    w = np.array([1.0 - q.get(u, 0.0) for u in us], dtype=float)
    def est(idx: np.ndarray) -> float:
        return float((np.dot(w[idx], r[idx]) + kappa * mu_cat) / (w[idx].sum() + kappa))
    n = len(us)
    if n == 0:
        return {"adjusted": None, "ci": [None, None], "sample_mean": None, "n_sampled": 0}
    all_idx = np.arange(n)
    rng = np.random.default_rng(rng_seed)
    boots = np.array([est(rng.integers(0, n, n)) for _ in range(n_boot)])
    return {
        "adjusted": round(est(all_idx), 2),
        "ci": [round(float(np.percentile(boots, 2.5)), 2), round(float(np.percentile(boots, 97.5)), 2)],
        "sample_mean": round(float(r.mean()), 2),
        "n_sampled": n,
    }
```

### 6.7 Near-duplicate text (P1)

Use `datasketch.MinHash(num_perm=128)` over lower-cased 3-word shingles. Report pairs inside a ring with estimated Jaccard ≥ 0.6. The result is report-only and does not feed any score (SRS OI-3).

## 7. orchestrator/ and api/

### 7.1 Event bus

Every event is persisted first, then fanned out to live subscribers. A late subscriber replays from `seq=0` (SRS-IF-21).

```python
# lockstep/orchestrator/events.py
from __future__ import annotations
import asyncio
from lockstep.store.db import Store

class EventBus:
    def __init__(self, store: Store, run_id: str):
        self.store, self.run_id, self.seq = store, run_id, 0
        self.subs: set[asyncio.Queue] = set()

    def emit(self, etype: str, payload: dict) -> None:
        self.seq += 1
        self.store.event_append(self.run_id, self.seq, etype, payload)
        for q in list(self.subs):
            q.put_nowait((self.seq, etype, payload))

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(); self.subs.add(q); return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subs.discard(q)
```

### 7.2 Run lifecycle

```python
# lockstep/orchestrator/run.py  (abridged to the control flow; helpers named in comments)
from __future__ import annotations
import asyncio, time, uuid
from lockstep.settings import Config, ENV
from lockstep.serp.budget import Budget
from lockstep.serp.client import SerpClient, LockstepError, params_hash
from lockstep.serp import engines as E
from lockstep.graph.model import Graph
from lockstep.graph import ingest as I
from lockstep.algo import prior, peel, significance, lockstep, rating
from lockstep.algo.expander import Expander, Plateau
from lockstep.orchestrator.events import EventBus

class Run:
    def __init__(self, store, cfg: Config, seed_data_id: str, budget: int, offline: bool):
        self.id = "r_" + uuid.uuid4().hex[:10]
        self.cfg, self.store = cfg, store
        self.seed_data_id = seed_data_id
        self.T = time.time()                                   # persisted; replay reuses it
        self.budget = Budget(budget, cfg.budget.split)
        self.client = SerpClient(store, ENV.serpapi_api_key, offline or ENV.lockstep_offline, self.id)
        self.bus = EventBus(store, self.id)
        self.g = Graph()
        self.state = "created"

    def _phase(self, s: str) -> None:
        self.state = s
        self.bus.emit("phase", {"phase": s, "ts": time.time()})   # also UPDATE runs.state

    def _credit(self) -> None:
        self.bus.emit("credit", {"used": self.budget.used, "budget": self.budget.total})

    async def execute(self) -> None:
        try:
            await self._resolve_and_sample()
            await self._expand_loop()
            await self._mine_and_report()
            self._phase("done"); self.bus.emit("done", {"run_id": self.id})
        except LockstepError as e:
            self.bus.emit("error", {"code": e.code, "message": e.message}); self._phase("failed")
        finally:
            await self.client.aclose()

    async def _resolve_and_sample(self) -> None:
        self._phase("resolving")
        resp, _ = await E.maps_place(self.client, self.budget, self.seed_data_id); self._credit()
        self.seed = I.ingest_place(self.g, resp["place_results"])
        sp = self.g.places[self.seed]
        if (sp.d_p or 0) < 20:
            raise LockstepError("E_TOO_FEW_REVIEWS", str(sp.d_p))
        base, _ = await E.maps_category(self.client, self.budget, sp.type or sp.title, sp.lat, sp.lng); self._credit()
        self.baseline = [r for r in base.get("local_results", [])[:20] if r.get("rating")]
        self._phase("sampling")
        tokens = {"newestFirst": None, "ratingHigh": None}
        while self.budget.remaining["sample"] > 0:
            for sort in ("newestFirst", "ratingHigh"):
                if self.budget.remaining["sample"] <= 0:
                    break
                resp, _ = await E.place_reviews(self.client, self.budget, sp.data_id, sort, tokens[sort], "sample")
                h = params_hash("google_maps_reviews", {"hl": "en", "data_id": sp.data_id, "sort_by": sort})
                for u in I.ingest_place_reviews(self.g, sp.data_id, resp, self.T, h):
                    self.bus.emit("node", {"id": self.g.users[u].contributor_id, "kind": "user"})
                tokens[sort] = (resp.get("serpapi_pagination") or {}).get("next_page_token")
                self._credit()
            if not any(tokens.values()):
                break
        self.budget.rollover("sample", "expand")

    async def _expand_loop(self) -> None:
        self._phase("expanding")
        c = self.cfg
        s0 = prior.priors(self.g, self.seed, c.prior.weights)
        ex, plateau, n = Expander(s0, c.expand.hot_boost), Plateau(c.expand.plateau_eps, c.expand.plateau_window), 0
        while (u := ex.pop()) is not None:
            if self.budget.remaining["expand"] <= 0 and self.budget.remaining["refine"] <= 0:
                break
            pool = "expand" if self.budget.remaining["expand"] > 0 else "refine"
            cid = self.g.users[u].contributor_id
            try:
                resp, _ = await self.client.get("google_maps_contributor_reviews",
                                                {"contributor_id": cid, "num": 200}, self.budget, pool)
            except LockstepError as e:
                if e.code in ("E_AUTH", "E_QUOTA"):
                    raise
                continue                                    # SRS-NF-5: skip and go on
            I.ingest_contributor(self.g, cid, resp, self.T, "")   # emit node/edge events here
            self._credit(); n += 1
            if n % c.expand.refine_every == 0 and self.budget.remaining["refine"] > 0:
                p = ex.next_refine(self.g, self.seed)
                if p is not None:
                    resp, _ = await E.place_reviews(self.client, self.budget, self.g.places[p].data_id,
                                                    "newestFirst", None, "refine")
                    hot = ex.hot_places(self.g, self.seed)
                    for v in I.ingest_place_reviews(self.g, self.g.places[p].data_id, resp, self.T, ""):
                        if self.g.edges[(v, p)].rating >= 4:
                            n_hot = sum(1 for q in self.g.places_of(v) if q in hot)
                            ex.push(v, s0.get(v, 0.5), n_hot)
                    self._credit()
            rings = await asyncio.to_thread(peel.find_rings, self.g, self.seed, c.ring.min_users,
                                            c.ring.min_places, c.ring.min_coverage, 1)
            best = rings[0].density if rings else 0.0
            if rings:
                self.bus.emit("ring_update", {"ring_idx": 0, "density": best,
                    "members": [self.g.users[x].contributor_id for x in rings[0].users],
                    "places": [self.g.places[x].data_id for x in rings[0].places]})
            if plateau.update(best):
                break

    async def _mine_and_report(self) -> None:
        self._phase("mining")
        c = self.cfg
        rings = await asyncio.to_thread(peel.find_rings, self.g, self.seed, c.ring.min_users,
                                        c.ring.min_places, c.ring.min_coverage, c.ring.max_rings)
        D = significance.city_mass(self.g, [r.get("reviews", 0) for r in self.baseline], c.stats.mass_scale)
        scored = []
        for r in rings:
            s = significance.ring_significance(self.g, r, D, len(rings))
            s["lockstep_ratio"] = lockstep.lockstep_ratio(self.g, r, c.time.delta_days,
                                                         c.time.lockstep_share, c.time.max_median_width_days)
            scored.append((r, s, s["pval"] < c.stats.alpha))
        reported = [r for r, s, ok in scored if ok]
        tot = sum(b.get("reviews", 0) for b in self.baseline) or 1
        mu = sum(b["rating"] * b.get("reviews", 0) for b in self.baseline) / tot if self.baseline else 4.0
        rat = await asyncio.to_thread(rating.adjusted_rating, self.g, self.seed, reported, mu,
                                      c.rating.kappa, c.rating.tau, c.rating.bootstrap_n, c.rating.bootstrap_seed)
        self._phase("reporting")
        # report.result.build(...) -> persist results row (§8.1)
```

**Determinism.** Calling `asyncio.to_thread` does not change results, because the algorithms are pure.

**Place resolution.** `seed_data_id` is resolved from the user's input before `Run` is constructed (§7.4).

**Edge source hashes.** Track `source_hash` by having `client.get` return the hash as a third value. That change is left out of the abridged code above.

### 7.3 API models

```python
# lockstep/api/models.py
from pydantic import BaseModel, Field

class RunCreate(BaseModel):
    place: str = Field(min_length=3, max_length=2048)
    budget: int = Field(60, ge=20, le=200)
    offline: bool = False

class RunCreated(BaseModel):
    run_id: str

class RingOut(BaseModel):
    idx: int
    members: list[str]          # pseudonyms R1..Rn
    places: list[dict]          # {data_id, title, d_p}
    density: float
    expected_overlap: float
    observed_overlap: float
    pval: float
    lockstep_ratio: float | None
    reported: bool

class RatingOut(BaseModel):
    displayed: float | None
    adjusted: float | None
    ci: list[float | None]
    sample_mean: float | None
    n_sampled: int

class ResultOut(BaseModel):
    run_id: str
    state: str
    seed: dict
    credits: dict
    coverage: dict
    rings: list[RingOut]
    rating: RatingOut
    config: dict
```

### 7.4 Routes and SSE

```python
# lockstep/api/routes.py
from __future__ import annotations
import asyncio, json, re
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from lockstep.api.models import RunCreate, RunCreated

router = APIRouter(prefix="/api")
RUNS: dict = {}                         # run_id -> Run (one process, one user)
DATA_ID = re.compile(r"(0x[0-9a-f]+:0x[0-9a-f]+)", re.I)

def parse_place(s: str) -> str:
    m = DATA_ID.search(s)
    if not m:
        raise HTTPException(400, {"code": "E_BAD_PLACE"})
    return m.group(1).lower()

@router.post("/runs", status_code=201, response_model=RunCreated)
async def create_run(body: RunCreate):
    from lockstep.api.main import STORE, CFG
    from lockstep.orchestrator.run import Run
    run = Run(STORE, CFG, parse_place(body.place), body.budget, body.offline)
    RUNS[run.id] = run
    asyncio.create_task(run.execute())
    return RunCreated(run_id=run.id)

@router.get("/runs/{run_id}/events")
async def events(run_id: str):
    from lockstep.api.main import STORE
    run = RUNS.get(run_id)
    async def gen():
        last = 0
        for row in STORE.events_since(run_id, 0):                      # history first
            last = row["seq"]
            yield f"id: {row['seq']}\nevent: {row['type']}\ndata: {row['payload_json']}\n\n"
        if run is None or run.state in ("done", "failed"):
            return
        q = run.bus.subscribe()
        try:
            while True:
                try:
                    seq, etype, payload = await asyncio.wait_for(q.get(), timeout=10)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"; continue
                if seq <= last:
                    continue
                yield f"id: {seq}\nevent: {etype}\ndata: {json.dumps(payload)}\n\n"
                if etype in ("done", "error"):
                    return
        finally:
            run.bus.unsubscribe(q)
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
```

`parse_place` covers v1 inputs that contain a `data_id` (Maps URLs carry it as `!1s0x…:0x…`). For a bare `place_id` (`ChIJ…`), call `google_maps` with `place_id`, read `data_id` from the response, then construct the run.

**Subscription race.** Subscribe *before* replaying history and dedupe on `seq`. This avoids losing events emitted during the replay. The reference code above dedupes with `seq <= last`; move `subscribe()` to the top of `gen()` when implementing.

## 8. report/ and frontend

### 8.1 Result builder, pseudonyms, explanations

```python
# lockstep/report/templates.py
BANNED = ("fake", "fraud", "scam", "fraudulent")

RING_TMPL = ("{n_users} accounts share {n_places} places that are unrelated to this business. "
             "By chance, two accounts here would share about {exp:.2f} of those places; "
             "these share {obs:.1f} on average (p = {pval:.1e}).{lock}")
LOCK_TMPL = " At {lock_pct:.0f}% of those places, most of the accounts posted within {delta:.0f} days of each other."
NONE_TMPL = ("No coordination detected at α = {alpha}. {n_exp} reviewers were followed "
             "across {n_places} places.")

def check_copy(text: str) -> str:
    low = text.lower()
    for w in BANNED:
        assert w not in low, f"banned word in copy: {w}"
    return text
```

```python
# lockstep/report/result.py (core of build)
from lockstep.report.templates import RING_TMPL, LOCK_TMPL, NONE_TMPL, check_copy

def pseudonyms(s0: dict[int, float], ring_users: list[int]) -> dict[int, str]:
    order = sorted(set(s0) | set(ring_users), key=lambda u: (-s0.get(u, 0.0), u))
    return {u: f"R{i + 1}" for i, u in enumerate(order)}

def explain(ring, sig: dict, cfg) -> str:
    lock = ""
    if sig.get("lockstep_ratio") is not None:
        lock = LOCK_TMPL.format(lock_pct=100 * sig["lockstep_ratio"], delta=cfg.time.delta_days)
    return check_copy(RING_TMPL.format(n_users=len(ring.users), n_places=len(ring.places),
                                       exp=sig["expected_overlap"], obs=sig["observed_overlap"],
                                       pval=sig["pval"], lock=lock))
```

### 8.2 Narrator guard (optional LLM)

```python
# lockstep/report/narrator.py
import json, re
NUM = re.compile(r"-?\d+(?:\.\d+)?(?:e-?\d+)?")

def allowed_numbers(result: dict) -> set[str]:
    return set(NUM.findall(json.dumps(result)))

def guard(narrative: str, result: dict, fallback: str) -> str:
    """Reject narratives containing numbers absent from the result JSON, or banned words."""
    ok = allowed_numbers(result)
    if any(n not in ok for n in NUM.findall(narrative)):
        return fallback
    if any(w in narrative.lower() for w in ("fake", "fraud", "scam")):
        return fallback
    return narrative
```

The prompt sent to the LLM is the system instruction, followed by `json.dumps(result_minus_raw_ids)`. The instruction reads: "Summarise for a consumer in ≤ 80 words. Use only the numbers present. Never say fake, fraud or scam."

### 8.3 Dossier

The dossier is Markdown rendered from a Jinja-free f-string template, then converted to PDF with `markdown` + `weasyprint`. It has these sections, in order:

1. Summary
2. Seed place
3. Method and parameters (the config hash)
4. Rings: one table per ring of pseudonym, raw contributor ID, and shared places with dates
5. Statistical evidence
6. Credit ledger, with SerpApi `search_id`s
7. Limitations

Raw contributor IDs appear only here.

### 8.4 Frontend state

```ts
// web/src/types.ts
export type Phase = 'created'|'resolving'|'sampling'|'expanding'|'refining'|'mining'|'reporting'|'done'|'failed';
export interface NodeEv { id: string; kind: 'user'|'place'; label?: string }
export interface EdgeEv { u: string; p: string; rating: number; t_lo: number; t_hi: number; exact: boolean }
export interface RingEv { ring_idx: number; members: string[]; places: string[]; density: number }
export interface RunState {
  phase: Phase; used: number; budget: number;
  nodes: Record<string, NodeEv>; edges: Record<string, EdgeEv>;
  bestRing?: RingEv; error?: { code: string; message: string }; done: boolean;
}
export const initial: RunState = { phase: 'created', used: 0, budget: 60, nodes: {}, edges: {}, done: false };
```

```ts
// web/src/useRunStream.ts
import { useEffect, useReducer } from 'react';
import { RunState, initial } from './types';

type Action = { type: string; data: any };

function reducer(s: RunState, a: Action): RunState {
  switch (a.type) {
    case 'phase': return { ...s, phase: a.data.phase };
    case 'credit': return { ...s, used: a.data.used, budget: a.data.budget };
    case 'node': return s.nodes[a.data.id] ? s : { ...s, nodes: { ...s.nodes, [a.data.id]: a.data } };
    case 'edge': return { ...s, edges: { ...s.edges, [`${a.data.u}|${a.data.p}`]: a.data } };
    case 'ring_update': return { ...s, bestRing: a.data };
    case 'error': return { ...s, error: a.data, phase: 'failed' };
    case 'done': return { ...s, done: true };
    default: return s;
  }
}

export function useRunStream(runId?: string): RunState {
  const [state, dispatch] = useReducer(reducer, initial);
  useEffect(() => {
    if (!runId) return;
    const es = new EventSource(`/api/runs/${runId}/events`);
    const types = ['phase', 'credit', 'node', 'edge', 'ring_update', 'error', 'done'];
    types.forEach(t => es.addEventListener(t, (e: MessageEvent) => {
      dispatch({ type: t, data: JSON.parse(e.data) });
      if (t === 'done' || t === 'error') es.close();
    }));
    return () => es.close();
  }, [runId]);
  return state;
}
```

**Batching.** A run can emit thousands of `node` and `edge` events. Batch dispatches with `requestAnimationFrame`, and add elements to Cytoscape via `cy.batch()`. Re-run the `cose-bilkent` layout at most every 1.5 s, with `randomize: false` so node positions stay stable.

**Pseudonyms in the UI.** SSE events carry raw IDs, because the server is local. The UI maps them to `R1…Rn` client-side in first-seen order. The final result JSON carries the server's pseudonyms, which are authoritative.

## 9. Evaluation harness, tests, implementation order

### 9.1 Ring injection

```python
# eval/inject.py
from __future__ import annotations
import numpy as np
from lockstep.graph.model import Graph, Edge

def inject_ring(g: Graph, seed: int, n_users: int, n_places: int, camo: float, rng: np.random.Generator,
                T: float, tag: str) -> tuple[set[int], set[int]]:
    """Plant a ring: n_users new accounts, all 5-star the seed and >=70% of n_places new low-popularity places,
    within a 10-day window; plus camouflage edges to popular existing places with prob `camo`."""
    places = []
    for j in range(n_places):
        p = g.place(f"inj:{tag}:p{j}")
        g.places[p].d_p = int(rng.integers(5, 60))
        places.append(p)
    popular = sorted(range(len(g.places)), key=lambda p: -(g.places[p].d_p or 0))[:50]
    t0 = T - float(rng.integers(30, 400)) * 86400
    users = []
    for i in range(n_users):
        u = g.user(f"inj:{tag}:u{i}")
        g.users[u].k_u, g.users[u].photos, g.users[u].expanded = n_places + 3, 0, True
        users.append(u)
        t = t0 + float(rng.uniform(0, 10)) * 86400
        g.add_edge(Edge(u, seed, 5.0, t, t, True))
        for p in places:
            if rng.random() < 0.85:
                tt = t0 + float(rng.uniform(0, 10)) * 86400
                g.add_edge(Edge(u, p, 5.0, tt - 15 * 86400, tt + 15 * 86400, False))
        for p in popular:
            if rng.random() < camo / 5:
                g.add_edge(Edge(u, p, float(rng.integers(3, 6)), t0, t0, True))
    return set(users), set(places)
```

**Scoring.** A planted ring counts as recovered when a reported ring has Jaccard ≥ 0.5 with its user set. Precision is the share of reported rings that match a planted ring. Real places may hold genuine rings, so those are reported separately.

**Credit-efficiency simulation.** Real runs cannot be repeated cheaply, so the efficiency curve is simulated on a fully crawled cached graph. Each strategy (priority, BFS, random) "reveals" one contributor's edges per credit. Recall is then measured at budgets 20, 40, 60, 80, 100 and 120.

### 9.2 Test plan

| Test file | Covers | Key cases |
| --- | --- | --- |
| `test_dates.py` | SRS-DT-1, I1 | 40 strings: "a week ago", "3 months ago", "Edited 2 years ago", ISO, garbage; ISO lies within the relative interval |
| `test_budget.py` | CR-1, CR-9, I3 | Split rounding at budgets 20, 60, 200; cache hit returns the token; rollover; never `used > total` |
| `test_client.py` | OP-1 to OP-3, IF-13, IF-14 | `respx` mocks: 429 → retry → 200; 401 → E\_AUTH; status Error not cached; offline miss → E\_CACHE\_MISS; key absent from the cache row |
| `test_ingest.py` | Graph build | Fixture JSON from real cached calls; non-Google reviews skipped; truncated flag at 200 |
| `test_prior.py` | CR-4, I2 | Monotone in k\_u; local guide lowers the score |
| `test_peel.py` | DT-2, I5 | Planted 8×6 biclique recovered first; random sparse graph gives no ring; camouflaged ring still recovered |
| `test_significance.py` | DT-3, DT-4 | m = 0 → p = 1; large λ → large p; Bonferroni applied |
| `test_lockstep.py` | DT-5 | Co-timed ring ≥ 0.8; spread ring ≤ 0.2; wide intervals → None |
| `test_rating.py` | RP-1, I6 | No rings → adjusted ≈ shrunk sample mean; CI contains the estimate; same seed gives the same CI |
| `test_copy.py` | NF-14 | All templates and UI strings free of banned words |
| `test_replay.py` | NF-6 | Two offline runs on `demo.db` give byte-identical result JSON |

Add `respx` to the dev dependencies for mocking `httpx`.

### 9.3 Implementation order

Tasks are ordered so that something demonstrable exists at the end of every day.

| # | Task | Est. | Day |
| --- | --- | --- | --- |
| 1 | Repo scaffold, settings, schema, Store | 1.5 h | Oct 5 |
| 2 | Budget + SerpClient + engines + tests (mocked) | 2.5 h | Oct 5 |
| 3 | Playground checks (OI-1, the `json_restrictor` and place-lookup formats); 2 real places cached | 1 h | Oct 5 |
| 4 | dates.py, model.py, ingest.py + tests on real fixtures | 2 h | Oct 5 |
| 5 | prior, expander, peel + tests | 3 h | Oct 6 |
| 6 | significance, lockstep, rating + tests | 2.5 h | Oct 6 |
| 7 | Orchestrator Run end to end via CLI (`python -m lockstep.cli <url>`) | 2 h | Oct 6 |
| 8 | Injection + controls + null shuffle + plots | 3 h | Oct 7 |
| 9 | Calibrate mass\_scale and tau; freeze config.yaml | 1 h | Oct 7 |
| 10 | Scout runs on 8 places; Oct 7 gate decision | 2 h | Oct 7 |
| 11 | API routes + SSE + result builder | 2 h | Oct 8 |
| 12 | React UI: form, graph stream, ring panel, rating card | 4 h | Oct 8 |
| 13 | Dossier MD/PDF; narrator guard (optional) | 1.5 h | Oct 8 |
| 14 | README, prior-art table, integration map, plots, demo.db | 3 h | Oct 9 |
| 15 | Demo recording, incognito link checks, submit | 3 h | Oct 9–10 |

Total ≈ 34 hours of focused work. If the schedule slips, cut items in this order: the narrator, the PDF (keep MD), MinHash, then hot-place refinement. Keep the tests for peel, significance and budget no matter what.
