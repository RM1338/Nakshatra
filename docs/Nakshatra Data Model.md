# Nakshatra Data Model

Oct 4, 2026 · @Ronel Abraham Mathew

The persistent data model for Nakshatra v1.0: a single SQLite database that is at once the SerpApi cache, the reviewer graph, the run log and the replay source. This document is authoritative for schema; the LLD's storage section implements it.

## 1. Overview and modelling principles

Ten tables in three groups:

- **Raw.** What SerpApi returned: `serp_cache`.
- **Graph.** What the world looks like: `users`, `places`, `edges`. This is shared across runs.
- **Run.** What one investigation did and concluded: `runs`, `ledger`, `events`, `rings`, `results`, `run_members`.

**Principles**

1. **Raw is immutable.** SerpApi JSON is stored verbatim and never updated. Every graph fact can be re-derived from it, so a parser fix needs no new credits.
2. **The graph is shared and monotone.** Users, places and edges accumulate across runs. Later observations only make an edge more precise (§5); they never delete it.
3. **Runs are append-only records.** A finished run's rings, result and events are frozen. A run never mutates another run's rows.
4. **Natural keys from Google.** Places are keyed by Maps `data_id`; users by `contributor_id`. No surrogate integer IDs are persisted. The dense integer indices exist only in memory.
5. **Lineage everywhere.** Every edge records the `params_hash` of the call that produced it. Every ledger row points at a cache row. Any number in a dossier can therefore be traced back to a SerpApi `search_id`.
6. **Minimal personal data.** No names, photos or profile URLs are stored. Snippets are kept only as MinHash signatures, plus excerpts of at most 280 characters for ring members (§8).

**Engine:** SQLite 3.40+ in WAL mode, with a single writer. Timestamps are REAL Unix seconds in UTC. JSON is stored as TEXT and queried with SQLite's JSON1 functions when needed.

## 2. Entity-relationship diagram

Runs own their ledger, events, rings and result. The graph tables belong to no run and are shared by all of them.

&#91;embedded content: entity-relationship diagram · 10 tables in two groups\]

`run_members` links a run to the users and places it touched. `ledger.params_hash` and `edges.source_hash` (the elbow on the right) both point at `serp_cache`. These are the lineage links that let any dossier number be traced to a SerpApi `search_id`.

## 3. Entity dictionary

### serp\_cache: raw SerpApi responses

| Column | Type | Null | Description |
| --- | --- | --- | --- |
| `params_hash` | TEXT PK | no | SHA-256 of the canonical JSON of `{engine, params}` without `api_key` |
| `engine` | TEXT | no | `google_maps`, `google_maps_reviews`, `google_maps_contributor_reviews` |
| `params_json` | TEXT | no | Canonical params (sorted keys), key removed |
| `response_json` | TEXT | no | Verbatim response body |
| `search_id` | TEXT | yes | `search_metadata.id`, used for Search Archive lookups |
| `fetched_at` | REAL | no | Unix seconds |

### users: Google Maps contributors

| Column | Type | Null | Description |
| --- | --- | --- | --- |
| `contributor_id` | TEXT PK | no | Digits from `/maps/contrib/<id>` |
| `k_u` | INTEGER | yes | Total reviews, from `user.reviews` or `contributor.contributions.reviews` |
| `photos` | INTEGER | yes | Photo count, from `user.photos` |
| `local_guide` | INTEGER | no | 0/1 |
| `level` | INTEGER | yes | Local Guide level, from the contributor engine |
| `points` | INTEGER | yes | Local Guide points |
| `truncated` | INTEGER | no | 1 if the contributor engine returned 200 reviews (the cap) |
| `expanded_at` | REAL | yes | Last time the full history was fetched |

### places: Google Maps places

| Column | Type | Null | Description |
| --- | --- | --- | --- |
| `data_id` | TEXT PK | no | `0x…:0x…` |
| `place_id` | TEXT | yes | `ChIJ…` when known |
| `title` | TEXT | yes | Business name |
| `type` | TEXT | yes | Google category |
| `lat`, `lng` | REAL | yes | Coordinates |
| `rating` | REAL | yes | Displayed rating at last observation |
| `d_p` | INTEGER | yes | Global review count; drives the popularity weight c\_p |
| `observed_at` | REAL | no | Last update |

### edges: one review by a user of a place

| Column | Type | Null | Description |
| --- | --- | --- | --- |
| `contributor_id` | TEXT PK₁ FK→users | no | Author |
| `data_id` | TEXT PK₂ FK→places | no | Place reviewed |
| `rating` | REAL | no | 1–5 |
| `t_lo`, `t_hi` | REAL | no | Time interval; equal when exact. Unknown dates are stored as ±1e18 (SQLite has no infinity) |
| `exact` | INTEGER | no | 1 if from `iso_date` |
| `review_id` | TEXT | yes | Google review id |
| `excerpt` | TEXT | yes | ≤ 280 chars; retained only once the author is a ring member |
| `minhash` | BLOB | yes | 128 × uint32 signature |
| `source_hash` | TEXT FK→serp\_cache | no | The call that produced the most precise version of this edge |
| `first_seen` | REAL | no | First observation |

### runs: one investigation

| Column | Type | Null | Description |
| --- | --- | --- | --- |
| `run_id` | TEXT PK | no | `r_` + 10 hex |
| `seed_input` | TEXT | no | What the user typed |
| `seed_data_id` | TEXT FK→places | yes | Resolved seed |
| `budget` | INTEGER | no | 20–200 |
| `used` | INTEGER | no | Billed credits |
| `state` | TEXT | no | `created`, `resolving`, `sampling`, `expanding`, `refining`, `mining`, `reporting`, `done`, `failed`, `cancelled` |
| `offline` | INTEGER | no | 0/1 |
| `config_json` | TEXT | no | Frozen config |
| `config_hash` | TEXT | no | SHA-256 of `config_json` |
| `started_at` | REAL | no | Also the reference time T for date parsing |
| `ended_at` | REAL | yes |  |
| `error_code` | TEXT | yes | SRS Appendix A |

### ledger: every SerpApi request made by a run

| Column | Type | Null | Description |
| --- | --- | --- | --- |
| `id` | INTEGER PK | no | Autoincrement |
| `run_id` | TEXT FK→runs | no |  |
| `engine` | TEXT | no |  |
| `params_hash` | TEXT | no | Joins to `serp_cache` when `ok = 1` |
| `pool` | TEXT | yes | `sample`, `expand` or `refine` |
| `cached` | INTEGER | no | 1 = served locally |
| `billed` | INTEGER | no | 1 = counted against the budget |
| `ok` | INTEGER | no | 1 = `status == Success` |
| `latency_ms` | INTEGER | no |  |
| `ts` | REAL | no |  |

### events: the SSE stream, persisted

| Column | Type | Null | Description |
| --- | --- | --- | --- |
| `run_id` | TEXT PK₁ FK→runs | no |  |
| `seq` | INTEGER PK₂ | no | 1-based, gapless per run |
| `type` | TEXT | no | `phase`, `credit`, `node`, `edge`, `ring_update`, `warning`, `done`, `cancelled`, `error` (DECISIONS A6) |
| `payload_json` | TEXT | no | §6 |
| `ts` | REAL | no |  |

### rings, results, run\_members

| Table | Column | Type | Description |
| --- | --- | --- | --- |
| `rings` | `run_id`, `idx` | PK | Ring order by density |
|  | `members_json` | TEXT | Contributor IDs, sorted |
|  | `places_json` | TEXT | Place data\_ids, sorted |
|  | `density`, `exp_overlap`, `obs_overlap`, `pval`, `lockstep_ratio` | REAL | §5 of SRS; `lockstep_ratio` is nullable |
|  | `reported` | INTEGER | 1 if pval < α |
| `results` | `run_id` | PK |  |
|  | `result_json` | TEXT | Final result (§6.3); immutable |
| `run_members` | `run_id`, `kind`, `node_id` | PK | Which users (`kind='user'`) and places (`kind='place'`) a run touched, so the shared graph can be sliced per run |

## 4. Full DDL

This supersedes the schema sketch in the LLD §3.1. It adds `place_id`, `observed_at`, `expanded_at`, `first_seen`, `pool`, `config_hash`, the indexes and the views.

```sql
-- nakshatra/store/schema.sql  (schema version 2)
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA synchronous = NORMAL;

-- ---------- Raw ----------
CREATE TABLE IF NOT EXISTS serp_cache (
  params_hash   TEXT PRIMARY KEY CHECK (length(params_hash) = 64),
  engine        TEXT NOT NULL CHECK (engine IN ('google_maps','google_maps_reviews','google_maps_contributor_reviews')),
  params_json   TEXT NOT NULL CHECK (json_valid(params_json) AND instr(params_json, 'api_key') = 0),
  response_json TEXT NOT NULL CHECK (json_valid(response_json)),
  search_id     TEXT,
  fetched_at    REAL NOT NULL
) WITHOUT ROWID;

-- ---------- Graph ----------
CREATE TABLE IF NOT EXISTS users (
  contributor_id TEXT PRIMARY KEY CHECK (contributor_id GLOB '[0-9]*' OR contributor_id GLOB 'inj:*'),
  k_u            INTEGER CHECK (k_u IS NULL OR k_u >= 0),
  photos         INTEGER CHECK (photos IS NULL OR photos >= 0),
  local_guide    INTEGER NOT NULL DEFAULT 0 CHECK (local_guide IN (0,1)),
  level          INTEGER,
  points         INTEGER,
  truncated      INTEGER NOT NULL DEFAULT 0 CHECK (truncated IN (0,1)),
  expanded_at    REAL
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS places (
  data_id     TEXT PRIMARY KEY CHECK (data_id GLOB '0x*:0x*' OR data_id GLOB 'inj:*'),
  place_id    TEXT,
  title       TEXT,
  type        TEXT,
  lat         REAL CHECK (lat IS NULL OR lat BETWEEN -90 AND 90),
  lng         REAL CHECK (lng IS NULL OR lng BETWEEN -180 AND 180),
  rating      REAL CHECK (rating IS NULL OR rating BETWEEN 1 AND 5),
  d_p         INTEGER CHECK (d_p IS NULL OR d_p >= 0),
  observed_at REAL NOT NULL
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS edges (
  contributor_id TEXT NOT NULL REFERENCES users(contributor_id),
  data_id        TEXT NOT NULL REFERENCES places(data_id),
  rating         REAL NOT NULL CHECK (rating BETWEEN 1 AND 5),
  t_lo           REAL NOT NULL,
  t_hi           REAL NOT NULL,
  exact          INTEGER NOT NULL CHECK (exact IN (0,1)),
  review_id      TEXT,
  excerpt        TEXT CHECK (excerpt IS NULL OR length(excerpt) <= 280),
  minhash        BLOB CHECK (minhash IS NULL OR length(minhash) = 512),
  source_hash    TEXT NOT NULL,
  first_seen     REAL NOT NULL,
  PRIMARY KEY (contributor_id, data_id),
  CHECK (t_lo <= t_hi),
  CHECK (exact = 0 OR t_lo = t_hi)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_edges_place ON edges(data_id, contributor_id);

-- ---------- Run ----------
CREATE TABLE IF NOT EXISTS runs (
  run_id       TEXT PRIMARY KEY,
  seed_input   TEXT NOT NULL,
  seed_data_id TEXT REFERENCES places(data_id),
  budget       INTEGER NOT NULL CHECK (budget BETWEEN 20 AND 200),
  used         INTEGER NOT NULL DEFAULT 0,
  state        TEXT NOT NULL CHECK (state IN ('created','resolving','sampling','expanding','refining',
                                                'mining','reporting','done','failed','cancelled')),
  offline      INTEGER NOT NULL DEFAULT 0 CHECK (offline IN (0,1)),
  config_json  TEXT NOT NULL CHECK (json_valid(config_json)),
  config_hash  TEXT NOT NULL,
  started_at   REAL NOT NULL,
  ended_at     REAL,
  error_code   TEXT,
  CHECK (used <= budget)
);
CREATE INDEX IF NOT EXISTS ix_runs_seed ON runs(seed_data_id, started_at);

CREATE TABLE IF NOT EXISTS ledger (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id      TEXT NOT NULL REFERENCES runs(run_id),
  engine      TEXT NOT NULL,
  params_hash TEXT NOT NULL,
  pool        TEXT CHECK (pool IS NULL OR pool IN ('sample','expand','refine')),
  cached      INTEGER NOT NULL CHECK (cached IN (0,1)),
  billed      INTEGER NOT NULL CHECK (billed IN (0,1)),
  ok          INTEGER NOT NULL CHECK (ok IN (0,1)),
  latency_ms  INTEGER NOT NULL,
  ts          REAL NOT NULL,
  CHECK (NOT (cached = 1 AND billed = 1))
);
CREATE INDEX IF NOT EXISTS ix_ledger_run ON ledger(run_id, id);

CREATE TABLE IF NOT EXISTS events (
  run_id       TEXT NOT NULL REFERENCES runs(run_id),
  seq          INTEGER NOT NULL CHECK (seq >= 1),
  type         TEXT NOT NULL CHECK (type IN ('phase','credit','node','edge','ring_update','warning','done','cancelled','error')),
  payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
  ts           REAL NOT NULL,
  PRIMARY KEY (run_id, seq)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS rings (
  run_id         TEXT NOT NULL REFERENCES runs(run_id),
  idx            INTEGER NOT NULL CHECK (idx >= 0),
  members_json   TEXT NOT NULL CHECK (json_valid(members_json)),
  places_json    TEXT NOT NULL CHECK (json_valid(places_json)),
  density        REAL NOT NULL,
  exp_overlap    REAL NOT NULL,
  obs_overlap    REAL NOT NULL,
  pval           REAL NOT NULL CHECK (pval BETWEEN 0 AND 1),
  lockstep_ratio REAL CHECK (lockstep_ratio IS NULL OR lockstep_ratio BETWEEN 0 AND 1),
  reported       INTEGER NOT NULL CHECK (reported IN (0,1)),
  PRIMARY KEY (run_id, idx)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS results (
  run_id      TEXT PRIMARY KEY REFERENCES runs(run_id),
  result_json TEXT NOT NULL CHECK (json_valid(result_json))
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS run_members (
  run_id  TEXT NOT NULL REFERENCES runs(run_id),
  kind    TEXT NOT NULL CHECK (kind IN ('user','place')),
  node_id TEXT NOT NULL,
  role    TEXT NOT NULL CHECK (role IN ('seed','seed_reviewer','expanded','discovered','refined','baseline')),
  PRIMARY KEY (run_id, kind, node_id)
) WITHOUT ROWID;

-- ---------- Views ----------
CREATE VIEW IF NOT EXISTS v_run_credits AS
SELECT run_id,
       SUM(billed)                         AS billed,
       SUM(cached)                         AS cache_hits,
       SUM(1 - ok)                         AS failures,
       SUM(CASE WHEN pool='expand' THEN billed ELSE 0 END) AS expand_billed
FROM ledger GROUP BY run_id;

CREATE VIEW IF NOT EXISTS v_ring_members AS
SELECT r.run_id, r.idx, j.value AS contributor_id
FROM rings r, json_each(r.members_json) j;

CREATE VIEW IF NOT EXISTS v_ring_places AS
SELECT r.run_id, r.idx, j.value AS data_id
FROM rings r, json_each(r.places_json) j;

CREATE VIEW IF NOT EXISTS v_ring_evidence AS          -- who reviewed which ring place, and when
SELECT m.run_id, m.idx, e.contributor_id, e.data_id, p.title, p.d_p, e.rating, e.t_lo, e.t_hi, e.exact
FROM v_ring_members m
JOIN v_ring_places rp ON rp.run_id = m.run_id AND rp.idx = m.idx
JOIN edges e ON e.contributor_id = m.contributor_id AND e.data_id = rp.data_id
JOIN places p ON p.data_id = e.data_id;

PRAGMA user_version = 2;
```

**Deliberate omission.** There is no foreign key from `ledger.params_hash` or `edges.source_hash` to `serp_cache`. Failed calls are ledgered but never cached, and `inj:` evaluation edges have no source call. The integrity check in §5 enforces the link for real data instead.

## 5. Write rules, invariants and integrity checks

### 5.1 Upsert rules

| Table | On conflict | Rule |
| --- | --- | --- |
| `serp_cache` | `DO NOTHING` | Immutable; first successful response wins |
| `users` | update | Non-null new values overwrite; `truncated = MAX(old, new)`; `expanded_at` set only by contributor fetches |
| `places` | update | Non-null new values overwrite; `observed_at` = now. `d_p` keeps the larger of old and new when they come within 1 hour of each other (avoids flapping between engines) |
| `edges` | update | Precision only ever improves (below) |
| `runs` | update | `state`, `used`, `ended_at` and `error_code` are mutable until a terminal state; frozen after |
| `ledger`, `events` | none | Append-only |
| `rings`, `results` | none | Written once at the end of `mining` / `reporting` |

**Edge precision rule.** Let w = t\_hi − t\_lo. The incoming interval replaces the stored one if and only if one of these holds:

- the incoming edge is exact and the stored one is not; or
- neither is exact, and the incoming w is strictly smaller.

`source_hash` follows whichever interval wins. `rating` is never changed after first insert: a review edit produces a new `review_id`, so the change is detectable but is not merged.

```sql
INSERT INTO edges (contributor_id, data_id, rating, t_lo, t_hi, exact, review_id, excerpt, minhash, source_hash, first_seen)
VALUES (:cid, :did, :rating, :lo, :hi, :exact, :rid, :excerpt, :mh, :src, :now)
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
  minhash     = COALESCE(edges.minhash, excluded.minhash);
```

### 5.2 Invariants

| ID | Invariant | Enforced by |
| --- | --- | --- |
| D1 | `runs.used ≤ runs.budget` | CHECK + Budget class |
| D2 | `runs.used = SUM(ledger.billed)` for that run | Integrity query below |
| D3 | No row anywhere contains the API key | CHECK on `serp_cache.params_json`; CI grep over the DB file |
| D4 | `edges.t_lo ≤ t_hi`, and exact edges are points | CHECK |
| D5 | Every non-`inj:` edge's `source_hash` exists in `serp_cache` | Integrity query |
| D6 | `events.seq` is gapless per run | Integrity query |
| D7 | A cached ledger row is never billed | CHECK |
| D8 | Terminal runs have exactly one `results` row (`done`) or none (`failed`, `cancelled`) | Integrity query |

### 5.3 Integrity check (run in CI and before recording the demo)

```sql
-- D2: credit totals agree
SELECT r.run_id FROM runs r LEFT JOIN v_run_credits c USING (run_id)
WHERE r.used <> COALESCE(c.billed, 0);

-- D5: edge lineage resolves
SELECT e.contributor_id, e.data_id FROM edges e
LEFT JOIN serp_cache s ON s.params_hash = e.source_hash
WHERE s.params_hash IS NULL AND e.data_id NOT GLOB 'inj:*';

-- D6: gapless event sequence
SELECT run_id FROM events GROUP BY run_id HAVING MAX(seq) <> COUNT(*);

-- D8: results present exactly for done runs
SELECT r.run_id FROM runs r LEFT JOIN results x USING (run_id)
WHERE (r.state = 'done') <> (x.run_id IS NOT NULL);
```

All four queries must return zero rows. Ship them as `python -m nakshatra.store.check`.

## 6. JSON payload schemas

### 6.1 Event payloads (`events.payload_json`)

| type | Payload | Example |
| --- | --- | --- |
| `phase` | `{phase: string, ts: number}` | `{"phase":"expanding","ts":1791110000.2}` |
| `credit` | `{used: int, budget: int, cached: int}` | `{"used":23,"budget":60,"cached":4}` |
| `node` | `{id: string, kind: "user"\|"place", label?: string, d_p?: int, role?: string}` | `{"id":"0x3ba8…:0x9f…","kind":"place","label":"Tile shop","d_p":31}` |
| `edge` | `{u: string, p: string, rating: number, t_lo: number, t_hi: number, exact: bool}` | `{"u":"1128…","p":"0x3ba8…","rating":5,"t_lo":1781000000,"t_hi":1783600000,"exact":false}` |
| `ring_update` | `{ring_idx: int, members: string[], places: string[], density: number}` |  |
| `done` | `{run_id: string}` |  |
| `error` | `{code: string, message: string}` | `{"code":"E_QUOTA","message":"…"}` |

Labels on `node` events are place titles only. User nodes never carry names.

### 6.2 `runs.config_json`

This is the full resolved `Config` (LLD §2) serialised with sorted keys. `config_hash` is the SHA-256 of that string. Evaluation plots embed the first 8 characters of the hash in their filenames.

### 6.3 `results.result_json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "NakshatraResult",
  "type": "object",
  "required": ["run_id", "state", "seed", "credits", "coverage", "rings", "rating", "config_hash", "explanations"],
  "properties": {
    "run_id": {"type": "string", "pattern": "^r_[0-9a-f]{10}$"},
    "state": {"enum": ["done"]},
    "seed": {
      "type": "object",
      "required": ["data_id", "title", "rating", "d_p"],
      "properties": {"data_id": {"type": "string"}, "title": {"type": "string"},
                     "rating": {"type": ["number", "null"]}, "d_p": {"type": ["integer", "null"]}}
    },
    "credits": {
      "type": "object",
      "required": ["budget", "used", "cached"],
      "properties": {"budget": {"type": "integer"}, "used": {"type": "integer"}, "cached": {"type": "integer"}}
    },
    "coverage": {
      "type": "object",
      "required": ["reviewers_sampled", "reviewers_expanded", "places", "edges"],
      "properties": {"reviewers_sampled": {"type": "integer"}, "reviewers_expanded": {"type": "integer"},
                     "places": {"type": "integer"}, "edges": {"type": "integer"}, "low_coverage": {"type": "boolean"}}
    },
    "rings": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["idx", "members", "places", "density", "expected_overlap", "observed_overlap", "pval", "reported"],
        "properties": {
          "idx": {"type": "integer"},
          "members": {"type": "array", "items": {"type": "string", "pattern": "^R[0-9]+$"}},
          "places": {"type": "array", "items": {"type": "object", "required": ["data_id", "title", "d_p"]}},
          "density": {"type": "number"},
          "expected_overlap": {"type": "number"},
          "observed_overlap": {"type": "number"},
          "pval": {"type": "number", "minimum": 0, "maximum": 1},
          "lockstep_ratio": {"type": ["number", "null"]},
          "reported": {"type": "boolean"}
        }
      }
    },
    "rating": {
      "type": "object",
      "required": ["displayed", "adjusted", "ci", "sample_mean", "n_sampled"],
      "properties": {"displayed": {"type": ["number", "null"]}, "adjusted": {"type": ["number", "null"]},
                     "ci": {"type": "array", "minItems": 2, "maxItems": 2},
                     "sample_mean": {"type": ["number", "null"]}, "n_sampled": {"type": "integer"}}
    },
    "explanations": {"type": "array", "items": {"type": "string"}},
    "narrative": {"type": ["string", "null"]},
    "config_hash": {"type": "string"}
  }
}
```

The result JSON holds pseudonyms only. To map `R1` back to a contributor ID, the dossier exporter replays the run offline: priors are deterministic from the cached graph and the frozen config, so recomputing the ordering (s0 descending, ties broken by contributor ID) reproduces the mapping exactly. The mapping is never persisted, which keeps raw IDs out of every table the UI reads.

## 7. In-memory graph mapping

The persisted graph uses natural string keys. The in-memory graph (LLD §5.2) uses dense integers so the peeling and statistics code stays fast and simple.

| Persisted | In memory | Notes |
| --- | --- | --- |
| `users.contributor_id` | `Graph.uix[cid] -> int`, `Graph.users[int]: User` | Indices are assigned in first-seen order. They are stable within a run and meaningless across runs |
| `places.data_id` | `Graph.pix[did] -> int`, `Graph.places[int]: Place` | Same |
| `edges` row | `Graph.edges[(u, p)]: Edge` | t\_lo/t\_hi = ±inf in memory, ±1e18 on disk |
| `places.d_p` | `c_p = 1 / log(d_p + 5)` | Computed at peel time; unknown d\_p → 50 |
| `run_members` | not loaded | Written as nodes are touched, for slicing |

### Load and save

- **Save** is incremental: after each SerpApi response, the orchestrator upserts the touched users, places and edges in one transaction.
- **Load** is used for offline replay and evaluation. It reads the subgraph a run touched:

```sql
-- load a run's subgraph
SELECT e.* FROM edges e
JOIN run_members mu ON mu.run_id = :run AND mu.kind = 'user'  AND mu.node_id = e.contributor_id
JOIN run_members mp ON mp.run_id = :run AND mp.kind = 'place' AND mp.node_id = e.data_id;
```

Subgraph loading is for analysis and evaluation. Exact reproduction of a run uses offline replay instead, which re-ingests the cached responses in the original call order (ledger `id` order). That reproduces the original index assignment, so tie-breaks match byte for byte.

## 8. Data classification, privacy and retention

All stored data is public Google Maps content retrieved through SerpApi. Some of it still identifies individuals, so it is classified and minimised.

| Data | Class | Stored | Shown in UI | In dossier | In shipped `demo.db` |
| --- | --- | --- | --- | --- | --- |
| Contributor ID | Personal (pseudonymous) | Raw | No, R1…Rn | Yes | Yes (needed for replay) |
| Contributor name, photo, profile URL | Personal | **Never** (stripped by `json_restrictor`; dropped on ingest) | No | No | No |
| Review text | Personal content | MinHash always; excerpt ≤ 280 chars for ring members only | Ring excerpts on click | Excerpts | Excerpts for demo rings only |
| Review rating, dates | Personal behaviour | Yes | Aggregated | Yes | Yes |
| Place name, type, coords, rating | Business, public | Yes | Yes | Yes | Yes |
| Raw SerpApi JSON | Mixed | Yes, but restricted fields reduce the personal content | No | `search_id` only | Yes, demo calls only |
| SerpApi API key | Secret | **Never** | No | No | No |

### Retention

- Development databases are kept locally with no expiry.
- `demo.db` is built by `python -m nakshatra.store.export_demo --runs r_x r_y`. The export:
  - copies only the listed runs' cache rows, members, edges, events, rings and results;
  - runs `VACUUM`;
  - fails if the file exceeds 50 MB or if the key pattern appears in it.
- Deletion: `python -m nakshatra.store.forget --contributor <id>` removes the user, their edges and the cache rows of their contributor call, and marks dependent runs `stale` in a log. This exists for takedown requests.

### Access

The database is a local file and is reachable only through the localhost API. There is no multi-tenant concern in v1.

## 9. Sizing, example queries and migrations

### 9.1 Sizing (estimates, to be confirmed on day 1)

| Item | Per 60-credit run | 20 runs (hackathon) |
| --- | --- | --- |
| `serp_cache` rows | \~60 | \~1,200 |
| `serp_cache` bytes, with `json_restrictor` | \~2–4 MB | \~40–80 MB |
| `serp_cache` bytes, without the restrictor | \~10–20 MB | \~200–400 MB |
| `edges` | \~3,000–8,000 | \~60k–160k (with overlap, fewer) |
| `places` | \~2,000–5,000 | \~50k |
| `events` | \~5,000–10,000 | \~150k |
| `ledger` | \~60–80 | \~1,500 |

All query paths are primary-key or covering-index lookups at this scale, so no tuning is needed beyond the indexes in §4.

### 9.2 Example queries

```sql
-- Credits per run and pool
SELECT run_id, pool, SUM(billed) AS billed, SUM(cached) AS hits
FROM ledger GROUP BY run_id, pool ORDER BY run_id;

-- Reported rings with size and significance
SELECT run_id, idx, json_array_length(members_json) AS n_users,
       json_array_length(places_json) AS n_places, pval, lockstep_ratio
FROM rings WHERE reported = 1 ORDER BY pval;

-- Evidence table for one ring (powers the place drawer and dossier)
SELECT title, d_p, contributor_id, rating,
       datetime(t_lo, 'unixepoch') AS from_utc, datetime(t_hi, 'unixepoch') AS to_utc, exact
FROM v_ring_evidence WHERE run_id = :run AND idx = :idx ORDER BY title, t_lo;

-- Places most often shared by reported-ring members across all runs ("repeat clients")
SELECT p.title, p.data_id, COUNT(DISTINCT rp.run_id) AS runs
FROM v_ring_places rp JOIN rings r USING (run_id, idx) JOIN places p USING (data_id)
WHERE r.reported = 1 GROUP BY p.data_id HAVING runs >= 2 ORDER BY runs DESC;

-- Contributors seen in more than one reported ring
SELECT contributor_id, COUNT(*) AS rings
FROM v_ring_members m JOIN rings r USING (run_id, idx)
WHERE r.reported = 1 GROUP BY contributor_id HAVING rings >= 2;

-- Reconstruct the SerpApi call behind an edge
SELECT s.engine, s.search_id, s.params_json
FROM edges e JOIN serp_cache s ON s.params_hash = e.source_hash
WHERE e.contributor_id = :cid AND e.data_id = :did;
```

### 9.3 Migrations

The schema version lives in `PRAGMA user_version`, and migrations are plain SQL files applied in order at startup:

```text
nakshatra/store/migrations/
  0001_init.sql          -- LLD v1 schema
  0002_lineage.sql       -- adds place_id, observed_at, expanded_at, first_seen, pool, config_hash, views
```

```python
# nakshatra/store/migrate.py
from pathlib import Path
import sqlite3

def migrate(conn: sqlite3.Connection) -> int:
    cur = conn.execute("PRAGMA user_version").fetchone()[0]
    for f in sorted((Path(__file__).parent / "migrations").glob("*.sql")):
        n = int(f.name[:4])
        if n > cur:
            conn.executescript("BEGIN;" + f.read_text() + f"; PRAGMA user_version = {n}; COMMIT;")
            cur = n
    return cur
```

Because raw JSON is kept in `serp_cache`, any change to how graph tables are derived can be applied by rebuilding them from the cache, at zero credit cost:

```text
python -m nakshatra.store.rebuild_graph
```

That command truncates `users`, `places` and `edges`, then re-ingests every cache row in `fetched_at` order.
