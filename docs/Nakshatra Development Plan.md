# Nakshatra Development Plan

Oct 4, 2026 · @Ronel Abraham Mathew

41 tasks across 8 workstreams, from tonight to submission on Oct 10, 2026. Tick status in the tracker as you go; the critical path and gates decide what gets cut, not the clock.

## 1. Workstreams and effort

The 41 tasks add up to about 51 hours. Must tasks take about 42 of those. That fits 6 days at 7–9 focused hours each, with roughly 6 hours of buffer, if Could tasks are only picked up early.

| WS | Workstream | Tasks | Must h | Should h | Could h | Days |
| --- | --- | --- | --- | --- | --- | --- |
| WS0 | Setup and prerequisites | T01–T04 | 3.0 |  |  | Oct 4–5 |
| WS1 | Data layer (store, budget, SerpApi client) | T05–T08 | 5.0 |  |  | Oct 5 |
| WS2 | Graph (dates, model, ingest) | T09–T10 | 2.5 |  |  | Oct 5 |
| WS3 | Algorithms | T11–T18 | 8.0 | 1.5 |  | Oct 6–7 |
| WS4 | Orchestrator and API | T19–T25 | 6.0 | 3.0 |  | Oct 6–8 |
| WS5 | Frontend | T26–T29 | 6.0 |  |  | Oct 8 |
| WS6 | Evaluation and calibration | T30–T33 | 6.0 |  |  | Oct 7 |
| WS7 | Docs, demo, submission | T34–T38 | 5.5 | 1.0 |  | Oct 9–10 |
| WS8 | Could items | T39–T41 |  |  | 3.0 | Only if ahead |
|  | **Total** | **41** | **42.0** | **5.5** | **3.0** |  |

## 2. Task tracker

Each task names its exit test in "Done when". Doc references use: LLD = Technical Design, DM = Data Model, API = API Contract, ALG = Core Algorithm Design, UF = User Flow.

| ID | Task | Pri | Day | Est h | Depends on | Done when | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T01 | Secure ≥ 1,200 SerpApi credits (paid plan, or email adarsh@serpapi.com) | Must | Oct 4 | 0.5 | none | Credits visible in the SerpApi dashboard | To do |
| T02 | Playground checks: place lookup by `data_id`, `json_restrictor` syntax, `place_info.reviews` in contributor feed | Must | Oct 4 | 0.5 | T01 | Findings in `docs/dev-notes.md`; engine wrappers adjusted | To do |
| T03 | Repo scaffold: pyproject, Makefile, config.yaml, .env.example, CI (ruff + pytest), secret scanning | Must | Oct 5 | 1.0 | none | `make test` green on an empty suite; CI runs on push | To do |
| T04 | Apply design revisions to the LLD code (ALG §6, §7; API §9.1) | Must | Oct 5 | 1.0 | none | Checklist of 5 files closed | To do |
| T05 | Schema v2, migrations, Store, integrity check (DM §4–5) | Must | Oct 5 | 1.5 | T03 | `python -m nakshatra.store.check` returns 0 rows on a fresh DB | To do |
| T06 | Budget class + tests (LLD §4.1) | Must | Oct 5 | 0.5 | T03 | used ≤ total holds at budgets 20, 60, 200; cache hit returns the token | To do |
| T07 | SerpClient: cache, ledger, retries, offline mode + respx tests | Must | Oct 5 | 2.0 | T05, T06 | 429 retry, 401 E\_AUTH, offline miss E\_CACHE\_MISS, key never cached | To do |
| T08 | Engine wrappers; cache 3 real fixtures (place, reviews page, contributor) | Must | Oct 5 | 1.0 | T02, T07 | Fixtures in `tests/fixtures/serpapi/` | To do |
| T09 | Date interval parser + 40-case test (ALG §7.1 widening) | Must | Oct 5 | 1.0 | T03 | ISO lies within the relative interval; garbage → unknown | To do |
| T10 | Graph model + ingest (place, reviews, contributor) | Must | Oct 5 | 1.5 | T08, T09 | Real fixtures ingest; non-Google reviews skipped; truncated flag at 200 | To do |
| T11 | Reviewer prior s0 + burst z-score | Must | Oct 6 | 1.0 | T10 | Monotone in k\_u; local guide lowers the score | To do |
| T12 | Expander (priority queue, hot places) + plateau rule | Must | Oct 6 | 1.5 | T11 | Never expands twice; plateau fixture stops early | To do |
| T13 | Weighted peeling + ring trimming (ALG §5) | Must | Oct 6 | 2.0 | T10 | Planted 8×6 ring returned first; sparse random graph gives none | To do |
| T14 | City-wide Poisson display statistic (ALG §6.1) | Must | Oct 6 | 1.0 | T13 | m = 0 → p = 1; power-user pair unremarkable | To do |
| T15 | Permutation gate with curveball swaps (ALG §6.2) | Must | Oct 6 | 1.5 | T13 | Degrees preserved; on null graphs, share of p < α ≈ α | To do |
| T16 | Adjusted rating from `newestFirst` with shrinkage + bootstrap | Must | Oct 7 | 1.0 | T10 | No-ring invariant; CI contains the point; same seed gives the same CI | To do |
| T17 | Sweep-line lockstep ratio (ALG §7.1) | Should | Oct 7 | 0.5 | T13 | Co-timed ring ≥ 0.8; wide intervals → null | To do |
| T18 | Ring guards: rating variance, geo spread, brand overlap | Should | Oct 7 | 1.0 | T13 | Notes render on fixture rings | To do |
| T19 | Run orchestrator + CLI `python -m nakshatra.cli <url>` | Must | Oct 6 | 2.0 | T12–T16 | **G1:** one real place gives rings or a clean result end to end | To do |
| T20 | Hot-place refinement inside the loop | Should | Oct 7 | 1.0 | T19 | Refine budget respected; new co-reviewers pushed | To do |
| T21 | FastAPI: /runs, /runs/{id}, /health, error envelope, idempotency | Must | Oct 8 | 1.5 | T19 | Contract error tests pass (API §9.3) | To do |
| T22 | SSE events with replay, Last-Event-ID, S-pseudonyms | Must | Oct 8 | 1.5 | T21 | Gapless seq; late join gets full history; no raw IDs | To do |
| T23 | Evidence + ledger endpoints | Must | Oct 8 | 1.0 | T21 | Schemas match the OpenAPI spec | To do |
| T24 | Cancel with partial result | Should | Oct 8 | 0.5 | T21 | Cancelled run shows a low-coverage result | To do |
| T25 | Dossier export (MD; PDF if WeasyPrint installs) | Should | Oct 8 | 1.5 | T21 | File contains all 7 sections | To do |
| T26 | Vite + React scaffold, routing, S1 Home | Must | Oct 7 | 1.0 | T21 | Paste + Enter starts a run | To do |
| T27 | useRunStream + S2 live graph (Cytoscape, batching) | Must | Oct 8 | 2.5 | T22, T26 | First node < 5 s; smooth at 10k events | To do |
| T28 | S3 result: rating card, verdict line, ring cards | Must | Oct 8 | 1.5 | T27 | **G3:** Flow A steps A1–A8 work in the browser | To do |
| T29 | Place drawer + ledger drawer | Must | Oct 8 | 1.0 | T23, T28 | Flow A step A9 works | To do |
| T30 | Injection harness + scoring | Must | Oct 7 | 1.5 | T19 | Recall/precision computed on 1 cached graph | To do |
| T31 | Controls, null calibration; fit priors, s, τ; freeze config.yaml | Must | Oct 7 | 2.0 | T30, T33 | Control false positives ≤ 1/10; config hash committed | To do |
| T32 | Credit-efficiency simulation + plots | Must | Oct 7 | 1.0 | T30 | Priority vs BFS vs random curve committed | To do |
| T33 | Scout 8 real places + 10 controls live; G2 decision | Must | Oct 7 | 1.5 | T19, T01 | **G2:** demo case chosen and written down | To do |
| T34 | demo.db export + offline replay test | Must | Oct 9 | 0.5 | T33, T22 | Clean clone, no key: demo replays byte for byte | To do |
| T35 | README: insight, prior art, integration map, method, results, limitations, diagrams | Must | Oct 9 | 3.0 | T31, T32 | A first-time reader can explain the project | To do |
| T36 | Usability check with 2 people; fix copy | Should | Oct 9 | 1.0 | T29 | UF §8 checklist passes | To do |
| T37 | Record the demo; cut to under 3 min | Must | Oct 9–10 | 1.5 | T34, T36 | Ring visible before 0:45; link opens in incognito | To do |
| T38 | Submit the form; incognito link checks | Must | Oct 10 | 0.5 | T37 | "Submit project" pressed by 18:00 IST | To do |
| T39 | Place search endpoint + UI | Could | any | 1.0 | T21, T26 | Candidates list with eligibility | To do |
| T40 | MinHash near-duplicate texts | Could | any | 1.0 | T10 | Paraphrase pairs flagged | To do |
| T41 | LLM narrator with number guard | Could | any | 1.0 | T21 | A foreign number triggers the fallback | To do |

## 3. Critical path

Two chains decide the finish date. Any slip on them moves submission, so protect them first each morning.

**Detection chain (the technical claim):**

T01 → T02 → T08 → T10 → T13 → T15 → T19 → T30 → T31 → T35 → T37 → T38

**Demo chain (the visible product):**

T19 → T21 → T22 → T27 → T28 → T34 → T37

| Slack-free task | Why it is critical | If it slips |
| --- | --- | --- |
| T01 credits | Every live call depends on it | Fall back to 250 credits: 3 real places + injected rings only (MVP Scope §6) |
| T13 peeling | Everything downstream needs rings | Do not start the UI until the planted-ring test passes |
| T19 orchestrator (G1) | First end-to-end proof | Cut T18, T20 |
| T31 calibration | Report thresholds must be frozen before recording | Keep the defaults; report them as uncalibrated in the README |
| T27 live graph | The demo moment | Fall back to a static graph rendered on `done`, with the credits bar still live |
| T34 demo.db | Judges must be able to replay | No fallback. Do it before the README |

Tasks off the critical path, which can move between days freely: T17, T18, T20, T24, T25, T36 and T39–T41.

## 4. Day-by-day plan

The two heaviest days are Oct 6 and Oct 8. Two tasks are shifted to keep each day near 9 hours:

- **T16** (adjusted rating) moves to the morning of Oct 7.
- **T26** (UI scaffold) moves to the evening of Oct 7. It can be built against a mocked event stream.

That shift is already reflected below.

| Day | Morning | Afternoon | Evening | Hours | Exit |
| --- | --- | --- | --- | --- | --- |
| Sun Oct 4 |  |  | T01, T02 | 1.0 | Credits secured; field shapes confirmed |
| Mon Oct 5 | T03, T04, T06 | T05, T07 | T08, T09, T10 | 9.5 | Real fixtures ingest into a graph |
| Tue Oct 6 | T11, T13 | T14, T15, T12 | T19 | 9.0 | **G1:** the CLI investigates a real place |
| Wed Oct 7 | T16, T30, T17 | T33 (scouting runs in the background), T31, T32 | T20, T18, T26 | 10.0 | **G2:** demo case chosen; config frozen |
| Thu Oct 8 | T21, T22 | T27 | T28, T23, T29 | 10.0 | **G3:** Flow A works in the browser |
| Fri Oct 9 | T34, T24, T25 | T35 | T36, first recording | 8.5 | **Feature freeze at 12:00.** README done |
| Sat Oct 10 | T37 final cut | T38 by 18:00 | Buffer | 2.0 | Submitted |

**If a day overruns by more than 2 hours:**

1. Drop that day's Should tasks.
2. Move Could tasks off the plan entirely.
3. Never push a gate task to the next day without cutting something else.

**Parallelism.** If a teammate joins, split along the two chains. One person takes WS3 + WS6 (detection), the other takes WS4 + WS5 (API and UI) against the API contract with mocked data. Merge on Oct 8 morning.

## 5. Working conventions and buffers

### Definition of done (every task)

- [ ] The "Done when" test in the tracker passes, and is automated wherever the tracker names a test
- [ ] `make test` and `ruff` are green; no new warnings
- [ ] No secrets in code, fixtures or logs (CI grep)
- [ ] Status set to Done in the tracker; any scope change noted in the MVP Scope doc

### Git

- Trunk-based: short branches named `t13-peel`, merged the same day. `main` must always run `make demo`.
- Commit messages start with the task ID: `T13: weighted peeling with trimming`. Judges can read the repository history, and task IDs make the progression legible.
- Tag `v1.0-submission` when submitting.

### Credit discipline

- Never call SerpApi from tests. Tests use fixtures and respx only.
- Each real place is crawled live once. Every later run uses the cache.
- Check the ledger total against the SerpApi dashboard at the end of each day.

### Buffers

| Buffer | Size | Where |
| --- | --- | --- |
| Daily slack | about 1 h on most days | Absorbed by dropping that day's Should tasks |
| Feature-freeze buffer | Oct 9, 12:00 to Oct 10 | Bug fixes, README, recording |
| Submission buffer | Oct 10, 18:00 to 23:59 | Only for re-uploading the video or fixing links |

### Daily stand-up with yourself (5 minutes)

Each morning, answer three questions:

1. Which critical-path task is today's?
2. What did yesterday's gate show?
3. What gets cut if today overruns?

Write the answers in `docs/dev-notes.md`. They become your build log for the README.
