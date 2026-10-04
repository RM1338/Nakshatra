-- nakshatra/store/schema.sql  (schema version 2; Data Model §4, plus DECISIONS A6)
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
