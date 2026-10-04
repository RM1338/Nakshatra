# Nakshatra System Architecture

Oct 4, 2026 · @Ronel Abraham Mathew

How Nakshatra v1.0 is structured to meet the PRD and SRS: a local, single-process FastAPI service that turns a SerpApi credit budget into a reviewer graph, mines it deterministically, and streams the result to a React client.

## 1. Architectural drivers

Three forces shape the architecture. SerpApi credits are the scarce resource, results must be deterministic and replayable, and the demo must stream progress live.

### Business goals (from the PRD)

- Detect review rings for one Google Maps place within a fixed credit budget.
- Back every flagged ring with statistical evidence, and show a ring-adjusted rating.
- Run locally for a 3-minute hackathon demo. Ship by Oct 10, 2026.

### Constraints

| ID | Constraint | Architectural consequence |
| --- | --- | --- |
| C1 | All Google data comes via SerpApi | A single outbound adapter (`serp/`). No scrapers |
| C2 | No LLM in the decision path | The `algo/` package is pure Python with no I/O. The narrator is isolated in `report/` |
| C3 | Must run locally | Single machine, SQLite, no queues or containers required |
| C4 | About 1,200 credits in total | A cache-first client and a credit ledger. Budget enforcement sits in one component |
| C5 | Small team, 6 days | Monolith with clear module boundaries. No microservices |

### Quality attributes, ranked

1. **Cost control.** A run never exceeds its credit budget. Repeated requests are free.
2. **Reproducibility.** The same cache and config always give byte-identical output.
3. **Correctness and auditability.** Every number can be traced to engine calls and a formula.
4. **Responsiveness.** The first graph nodes appear within 5 s, and a full run takes under 3 min.
5. **Modifiability.** New review sources (Play Store, App Store) plug in behind the same graph interface.

## 2. System context

Nakshatra has three kinds of user. It depends on one data provider, SerpApi, and on one optional text provider, an LLM.

&#91;embedded content: system context · 3 user classes, 3 external systems\]

Google Maps is never contacted directly. The LLM receives only computed results and cannot change them. The exported dossier leaves the system by hand, through the user, to Google or the CCPA.

## 3. Container view

There are four containers: the browser SPA, one FastAPI process, the SQLite file and SerpApi. Inside the process, `orchestrator/` owns each run and is the only package that calls the others.

&#91;embedded content: containers · browser, one API process with 7 packages, SerpApi, SQLite\]

| Container | Technology | Responsibility | Talks to |
| --- | --- | --- | --- |
| Browser SPA | React 18, Vite, Cytoscape.js | Input, live graph, results, export | API process over REST and SSE |
| API process | Python 3.11, FastAPI, uvicorn, numpy, scipy, datasketch | Orchestration, crawl, detection, reporting | SerpApi (HTTPS), SQLite (file) |
| SQLite | sqlite3, WAL mode | Cache, ledger, graph, runs, events | API process only |
| SerpApi | External SaaS | Google Maps data | API process only, via `serp/` |
| LLM provider (optional) | Any chat API | Narrative summary | `report/` only |

## 4. Component view

The backend is split into seven Python packages. Dependencies point inward to `algo/` and `graph/`, and only `serp/` touches the network.

| Package | Responsibility | Key interfaces | Depends on | Pure? |
| --- | --- | --- | --- | --- |
| `api/` | HTTP routes, SSE endpoint, request validation, error mapping | `POST /api/runs`, `GET /api/runs/{id}/events` | `orchestrator/`, `store/` | No |
| `orchestrator/` | Owns one run: the state machine, budget split, phase sequencing, event emission | `Run.start()`, `Run.events()`, `Budget.reserve(engine)` | `serp/`, `graph/`, `algo/`, `report/`, `store/` | No |
| `serp/` | The only SerpApi adapter: cache-first fetch, retries, `json_restrictor`, ledger writes, offline mode | `SerpClient.get(engine, params) -> (json, cached)` | `store/` | No |
| `graph/` | Normalise engine JSON into nodes and edges, parse dates into intervals, hold the in-memory graph | `ingest_reviews()`, `ingest_contributor()`, `Graph.neighbors()`, `parse_interval()` | none | Yes |
| `algo/` | Prior, expansion policy, weighted peeling, Poisson significance, lockstep, adjusted rating | `prior(u)`, `Expander.next()`, `peel(G, w)`, `significance(ring, D)`, `adjusted_rating()` | `graph/` | Yes |
| `report/` | Result assembly, explanation templates, dossier Markdown/PDF, optional LLM narrator | `build_result(run)`, `render_dossier(fmt)` | `algo/` outputs | Mostly |
| `store/` | SQLite access, schema migrations, WAL, event log for SSE replay | `Cache`, `Ledger`, `RunRepo`, `EventLog` | sqlite3 | No |
| `eval/` | Injection, controls, null shuffles, plots | CLI `python -m eval.run_injection` | `graph/`, `algo/`, `store/` (read only) | Yes on cached data |

**Rules that keep it testable**

- `algo/` and `graph/` import no I/O libraries. CI lints for `requests`, `sqlite3` and `httpx` imports there.
- Every budget decision goes through `orchestrator.Budget`. `serp/` refuses a live call when no reservation token is passed.
- Every stochastic step (bootstrap) takes an explicit `seed` argument.

### Frontend components

| Component | Responsibility |
| --- | --- |
| `InvestigateForm` | Place input and budget slider; posts the run |
| `useRunStream` | SSE hook; replays event history, then live events; reducer builds graph state |
| `GraphCanvas` | Cytoscape.js with an incremental `cose-bilkent` layout; ring colouring |
| `CreditBar` | Credits used/budget, phase, elapsed |
| `RingPanel` | Ring list, p-values, lockstep; place drawer |
| `RatingCard` | Displayed vs adjusted rating with interval |
| `ExportMenu` | Dossier MD/PDF, offline replay, rerun |

## 5. Runtime views

### 5.1 Investigation sequence

A run is one async task inside the API process. The SSE endpoint reads the persisted event log, so a browser that reconnects loses nothing.

1. **Browser → `POST /api/runs`.** `api/` validates the input and creates the run row. `orchestrator` spawns an asyncio task and the endpoint returns `run_id`.
2. **Browser → `GET /events`.** `api/` streams from `EventLog`, first the full history, then live events.
3. **Resolve** (1 credit). `serp.get(google_maps, data_id)` returns the seed. `graph/` adds the place node. Emit `phase`, `credit` and `node`.
4. **Baseline** (1 credit). A category search near the seed. Store μ\_cat and the baseline d\_p.
5. **Sample** (8–12 credits). Alternate `newestFirst` and `ratingHigh` pages. `graph/` ingests edges with exact dates, and `algo.prior` scores each reviewer.
6. **Expand / refine loop** (40–50 credits). See 5.2. Each contributor call emits nodes, edges and, after re-peeling, `ring_update`.
7. **Mine.** Run the final peel, then significance, lockstep and adjusted rating. Pure CPU, under 2 s.
8. **Report.** `report.build_result` writes the `results` row and emits `done`. The narrator runs afterwards if it is enabled.
9. **Browser → `GET /api/runs/{id}`.** Fetch the final JSON. The dossier is rendered on demand.

### 5.2 Crawl loop (inside step 6)

```text
          +-------------------------------+
          v                               |
   pop max-priority reviewer u            |
          |                               |
   Budget.reserve(contributor) --no--> exit loop
          | yes                           |
   serp.get(contributor_reviews, u)       |
          |                               |
   graph.ingest -> new places, edges      |
          |                               |
   update hot set H                       |
          |                               |
   every 5th expansion and refine budget left?
      yes -> serp.get(maps_reviews, hot p*)
             push reviewers with boosted priority
          |                               |
   algo.peel(G) -> best density           |
   emit ring_update                       |
          |                               |
   plateau (< 2% over 8)? --yes--> exit loop
          | no                            |
          +-------------------------------+
```

### 5.3 Offline replay

The same orchestrator runs with `SerpClient(offline=True)`. Every `get` is served from `serp_cache`. A miss raises `E_CACHE_MISS`, and the run moves to `failed` with a partial result. Because the queue order, tie-breaks (by `contributor_id`) and bootstrap seed are deterministic, the event sequence and the result JSON are identical to the original run's.

## 6. Data architecture

There are two tiers. SQLite is the system of record and the replay source. A `networkx`-free, array-backed graph is rebuilt in memory per run.

### 6.1 Persistent tier (SQLite, WAL mode)

| Store | Written by | Read by | Lifetime | Notes |
| --- | --- | --- | --- | --- |
| `serp_cache` | `serp/` | `serp/`, `eval/` | Forever (immutable) | Key = SHA-256 of canonical params without `api_key`. Raw JSON is kept so the parsers can change later |
| `ledger` | `serp/` | `api/`, `report/` | Forever (append-only) | Source of truth for credits and evaluation cost curves |
| `places`, `users`, `edges` | `graph/` via `orchestrator` | `report/`, `eval/` | Forever | Upserts. An exact date overrides a relative interval |
| `runs`, `rings`, `results` | `orchestrator`, `report/` | `api/` | Forever | One result JSON per run |
| `events` | `orchestrator` | `api/` SSE | Forever | (run\_id, seq, type, payload). Enables late-join replay |

### 6.2 In-memory graph (per run)

- Users and places are mapped to dense integer indices.
- Edges are stored as parallel numpy arrays: `u_idx`, `p_idx`, `rating`, `t_lo`, `t_hi`, `exact`.
- The CSR adjacency is rebuilt lazily after every 5 ingests, and peeling works on it with a binary heap of weighted degrees.
- Column weights are `c = 1 / log(d + 5)`, a vector aligned to the place indices.
- At the expected scale of 40 contributors × ≤ 200 reviews, there are at most about 8,000 edges per run, so peeling takes milliseconds.

### 6.3 Data flow and lineage

```text
SerpApi JSON --(serp_cache)--> graph.ingest --(edges)--> algo.* --(rings, rating)--> report --(results, dossier)
      |                                                                                  |
      +-------------------------- ledger rows (credit lineage) --------------------------+
```

Every ring in the result carries the `params_hash` list of the calls that produced its edges. This lets the dossier cite the exact SerpApi searches, which can be reopened through SerpApi's Search Archive by `search_id`.

### 6.4 Privacy in the data tier

- `contributor_id` is stored raw for joins, and pseudonymised at the `report/` boundary.
- Snippets are stored as MinHash signatures. At most 280 characters of excerpt are kept per ring-member edge.
- No thumbnails or profile URLs are persisted, because `json_restrictor` excludes them at fetch time.

## 7. Deployment view

One laptop, two local processes in development, and one process in demo mode. The only outbound dependency is HTTPS to `serpapi.com`.

| Mode | Processes | Ports | Command |
| --- | --- | --- | --- |
| Development | `uvicorn api.main:app --reload` and Vite dev server (proxies `/api`) | 8000, 5173 | `make dev` |
| Demo / judge | `uvicorn` serving the built SPA from `web/dist` as static files | 8000 | `make demo` |
| Offline replay | Same as demo, with `NAKSHATRA_OFFLINE=1` and the shipped `data/demo.db` | 8000 | `make replay` |
| Evaluation | CLI, no server | none | `make eval` |

**Runtime requirements:** Python 3.11+ (uv or pip), Node 20+ only to build the UI, and about 200 MB of disk for the cache.

**Shipped data:** the repo includes `data/demo.db` with the cached SerpApi responses for the demo places. Judges can then replay the exact demo with no API key and no credits. Live runs need `SERPAPI_API_KEY` in `.env`.

**Optional Docker:** a single-stage `Dockerfile` running `make demo` is a P2 convenience, not a requirement.

**Binding:** the server binds to `127.0.0.1` by default. CORS is restricted to the Vite origin in development.

## 8. Cross-cutting concerns

### 8.1 Credit control

- **Single choke point.** `Budget` holds three sub-budgets (sample, expand, refine). Before every live call, `Budget.reserve(engine)` either returns a token or refuses. `serp/` requires the token.
- **Cache first.** A cache hit returns no token and costs nothing. SerpApi's own 1-hour cache is also free, but the ledger still marks those calls as live and unbilled using `search_metadata`.
- **Rollover.** At each phase boundary, the unused sample budget flows to expansion, and unused refinement budget flows back to expansion.
- **Guarantee.** Credits used never exceed the budget, because every live call needs a reservation token and reservations never exceed the remaining budget.

### 8.2 Determinism

- The priority queue breaks ties by `contributor_id`, and the peel heap breaks ties by node index.
- Dict iteration order is fixed by sorting keys at ingest.
- "Now" for date parsing is the run's `started_at`, persisted, never the wall clock at replay.
- The bootstrap uses `numpy.random.default_rng(seed)`.
- A CI test replays `data/demo.db` twice and diffs the JSON.

### 8.3 Error handling

| Failure | Handling |
| --- | --- |
| 429 / 5xx from SerpApi | 3 retries, backoff 1 s, 2 s, 4 s. Then skip that contributor and log it |
| 401 | Abort the run with `E_AUTH`. Partial events are kept |
| `status != Success` | Not cached. Counted in the ledger as failed |
| Schema drift (missing field) | The parser logs the field and treats the value as unknown. The run continues |
| Unparseable date | Interval (−∞, +∞), excluded from the lockstep calculation |
| Server crash mid-run | The run stays `expanding`. On restart it is marked `failed` and can be replayed offline up to its last cached call |

### 8.4 Security

- The key comes from the environment only. A redaction filter covers the logs, and `api_key` is stripped before hashing or caching. CI greps for key patterns.
- Localhost binding. No auth, because the system is a single user on a local machine.
- The PDF renderer is fed only with escaped template output, with no user HTML passed through.

### 8.5 Observability

- Structured JSON logs carry `run_id`, `phase`, `credits_used` and `latency_ms`.
- The `/api/runs/{id}/ledger` endpoint and the UI credit bar are the same data, so what the judge sees is the audit trail.
- Evaluation outputs are versioned under `eval/plots/` with the config hash in the filename.

### 8.6 LLM containment

The narrator receives only the result JSON and returns text. A post-check extracts every number from that text and rejects the output if any number is absent from the JSON. A failed or disabled narrator falls back to the deterministic template, so no decision depends on it.

## 9. Architecture decision records

| ADR | Decision | Alternatives considered | Rationale | Consequence |
| --- | --- | --- | --- | --- |
| ADR-1 | Modular monolith (one FastAPI process) | Separate worker with Redis/Celery | Local demo, a single user, 6-day build | Long runs share the event loop; CPU work is pushed to a thread |
| ADR-2 | SQLite in WAL mode as both cache and record | Postgres; JSON files | Zero setup; one file to ship as `demo.db`; concurrent SSE reads | Single-writer, which is fine for one run at a time |
| ADR-3 | Server-Sent Events for progress | WebSockets; polling | One-way stream, auto-reconnect, trivial in FastAPI | No client-to-server channel; cancel goes through a REST call |
| ADR-4 | Cache raw SerpApi JSON, parse on read | Cache parsed rows only | Parsers can change without spending credits again | Larger DB, about 200 MB maximum |
| ADR-5 | Hand-written weighted peeling on numpy/CSR | `rgmining-fraudar` package; networkx | Needs global-popularity column weights, incremental re-peel, determinism; the existing wrapper is GPLv3 | About 150 lines to own and test. networkx is used only in `eval/` for shuffles |
| ADR-6 | Poisson null model with a calibrated mass scale | Permutation test per run | Closed form, instant, explainable on screen | Calibration needed (null shuffles); the assumption is documented |
| ADR-7 | Relative dates as intervals, refined selectively | Treat "a month ago" as a point | Honest uncertainty; refinement spends credits only where it changes conclusions | Lockstep is sometimes reported as null |
| ADR-8 | LLM only as an optional narrator with a number check | LLM-based ring judgement | Determinism, auditability, the judges' "not a wrapper" test | Explanations are template-like without the narrator |
| ADR-9 | Ship `demo.db` in the repo | Require a key to evaluate | Judges can verify without credits; reproducible demo | The repo contains cached public data. Snippets are minimised |
| ADR-10 | React + Cytoscape.js | Streamlit; D3 from scratch | Incremental graph rendering with layouts, at the needed polish | A Node toolchain is needed to build |

## 10. Quality scenarios, risks and technical debt

### 10.1 Quality attribute scenarios

| Attribute | Stimulus | Response | Measure |
| --- | --- | --- | --- |
| Cost control | User sets budget 60 on a place with 900 reviews | The crawl stops at or before 60 billable calls | Ledger sum ≤ 60 in 100% of test runs |
| Reproducibility | A judge runs `make replay` with no key | The demo run completes with identical output | JSON diff empty; 0 network calls |
| Responsiveness | User clicks Investigate | The first node renders | ≤ 5 s; full run ≤ 180 s at p90 |
| Availability | SerpApi returns 503 for 3 contributors | The run completes with those skipped and noted | `done` state; coverage shows the skips |
| Modifiability | Add a Play Store reviews source | New `serp/` engine + `graph.ingest_play()` only | No change in `algo/` |
| Auditability | A judge asks where the 9 shared places came from | The dossier lists the contributor calls by `search_id` | Every ring edge traceable to a cached call |
| Privacy | A demo is recorded | No real reviewer names or photos appear | Copy and pseudonym lint passes |

### 10.2 Architectural risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| SerpApi field drift (for example, `place_info` lacks a review count) | Popularity weights degrade | Backfill via `google_maps` within a 5-call cap. Parser tests run on the cached fixtures |
| Event loop blocked by CPU (peeling, bootstrap) | SSE stutters | Run `algo/` in `asyncio.to_thread`. The bootstrap runs only once, at the end |
| SQLite lock contention | Write errors under SSE load | WAL mode; a single writer task; reads go through a separate connection |
| Calibration constants overfit the injection data | False positives on real places | Hold-out controls; freeze the config before recording |
| `demo.db` size or content concerns | Repo bloat; privacy | `json_restrictor` minimisation; size check in CI (< 50 MB) |

### 10.3 Accepted technical debt (v1.0)

- There is one run at a time. Concurrent runs are not tested.
- No schema migrations framework. Changes are recorded in a single `schema.sql` with a version pragma.
- The PDF export uses a simple HTML-to-PDF path. Pixel fidelity is not a goal.
- The Hindi and Tamil text in snippets is not normalised before MinHash. This may under-detect duplicates written in those languages.
- The Play Store and App Store adapters (APPLOCK) are designed for but not built.
