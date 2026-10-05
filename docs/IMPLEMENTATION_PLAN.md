# Nakshatra Implementation Plan

Living plan. Status is updated as tasks land. Conflicts and deviations live in [DECISIONS.md](DECISIONS.md).

## 1. Document inventory

| File | Role | Owns |
| --- | --- | --- |
| PRD | Problem, users, goals, success metrics, P0/P1/P2 features | G1–G5, US1–US10, FR1–FR22, CR1–CR5, NF1–NF7, E1–E6, evaluation suite (§10) |
| SRS | Testable requirements, ISO 29148 | SRS-IN-1..5, CR-1..10, DT-1..6, RP-1..5, OP-1..4, IF-1..31, DA-1..21, NF-1..19; invariants I1–I6; error codes (App. A); config keys (App. B); open issues OI-1..3 |
| System Architecture | Containers, packages, runtime, deployment, ADRs | C1–C5, quality ranking, package boundaries, `make dev/demo/replay/eval`, ADR-1..10, determinism rules (§8.2) |
| Technical Design (LLD) | Module-level reference code | Repo layout, deps, conventions, `Config`, Budget, SerpClient, engines, dates, Graph, ingest, prior, expander, peel, narrator guard, dossier sections, test plan (§9.2). **Partly superseded** (DECISIONS A1–A13) |
| API Contract | HTTP + SSE + outbound SerpApi contract | `/api/v1` endpoints, error envelope and catalogue, SSE protocol, `S`/`R` pseudonyms, OpenAPI 3.1, contract tests. **Supersedes LLD/SRS on HTTP** |
| Data Model | Schema v2, upsert rules, invariants D1–D8, integrity check, payload schemas, privacy, export | **Authoritative for schema** |
| Core Algorithm Design | The maths: prior, active search, weighted peeling, significance (revised), lockstep (exact), adjusted rating, calibration | **Supersedes SRS §5.5 and LLD §6.4–6.6** |
| User Flow | Screens S1–S3, overlays O1–O2, flows A–C, states, copy, demo timing | Final UI copy; demo mapping (§8) |
| MVP Scope | What is in and out of the submission | M1–M12, S1–S6, C1–C5, Won't list, cut order, gates G1–G3, locked decisions |
| Development Plan | 41 tasks, critical path, days | T01–T41, gates, git conventions |
| Novelty Analysis | Positioning, prior art, permitted claims | README wording (§8) |

No separate Evaluation Plan or Demo Plan file exists (DECISIONS A17).

## 2. System summary

**User and decision.** A consumer (Priya), an investigator (Arun), a business owner (Meena) or a hackathon judge points Nakshatra at one Google Maps place and asks whether its rating is propped up by coordinated accounts. The output is a set of rings (pseudonymous members plus the non-seed places they share), statistical evidence for each ring (expected vs observed overlap, a permutation p-value, a lockstep ratio), a ring-adjusted recent rating with a 95% interval, and an exportable dossier. "No coordination detected" is a first-class result.

**Core innovation** (checked against ALG and NOV §5):

1. *Budgeted, feedback-driven discovery.* The reviewer graph is not given. It is crawled through `google_maps_contributor_reviews` under a credit budget, in priority order s0 · (1 + β|H_v|). Hot-place refinement and a plateau stopping rule are driven by re-peeling after every query.
2. *Camouflage-resistant weighted densest subgraph* (FRAUDAR peeling) with column weights c_p = 1/log(d_p + 5) taken from each place's **global** review count. The seed place is excluded.
3. *Selection-aware gate.* A degree-preserving (curveball) permutation of the **crawled** graph, rerunning the same miner, gives p_perm. A city-wide Poisson pairwise statistic is shown alongside it.
4. *Interval lockstep.* Exact sweep-line maximum clique on δ/2-widened intervals, using a mix of exact and relative dates, reported as null when intervals are too wide.
5. *Shrunk ring-adjusted rating.* Built from `newestFirst` reviews, with membership weights q_u = min(1, g/τ), shrinkage κ toward the category mean μ_cat, and a bootstrap 95% interval (seed 7).

**SerpApi engines** (API §8):

| Engine | Step | Params | Fields consumed | Credits per 60-credit run | Limits |
| --- | --- | --- | --- | --- | --- |
| `google_maps` | Seed resolve; category baseline; (P1) d_p backfill | `type=place` + `data`/`place_id`; `type=search`, `q`, `ll=@lat,lng,14z` | `place_results.{data_id, place_id, title, type, rating, reviews, gps_coordinates}`, `local_results[]` | 1 + 1 (+0–5) | — |
| `google_maps_reviews` | Seed sample (`newestFirst` / `ratingHigh`); hot-place refinement | `data_id`, `sort_by`, `next_page_token`, `num=20` after page 1 | `reviews[].{review_id, rating, iso_date, snippet, user.{contributor_id, reviews, photos, local_guide}}`, `place_info.reviews`, `serpapi_pagination.next_page_token` | 8–12 + 5–10 | First page 8 results; non-Google reviews have no `contributor_id` |
| `google_maps_contributor_reviews` | Reviewer expansion | `contributor_id`, `num=200` | `contributor.{level, points, local_guide, contributions.reviews}`, `reviews[].{review_id, rating, date, snippet, place_info.{data_id, title, type, gps_coordinates, reviews?}}` | 30–40 | Cap of 200 per contributor; relative dates only |

**Component map.**

| Package | Responsibility | Depends on |
| --- | --- | --- |
| `settings` | Env + `config.yaml` → frozen `Config`, `config_hash` | pydantic |
| `store/` | SQLite v2 schema, repos, event log, integrity check, demo export | sqlite3 |
| `serp/` | Budget, cache-first `SerpClient`, ledger, retries, offline mode, engine wrappers, PII scrub | store, httpx |
| `graph/` | Date intervals, in-memory Graph, ingest (pure) | numpy |
| `algo/` | prior, expander + plateau, peel + trimming, significance (Poisson + permutation), lockstep, rating (pure) | graph, numpy, scipy |
| `orchestrator/` | `Run` state machine, budget phases, event bus, persistence of graph and run rows | all of the above |
| `report/` | Result builder, pseudonyms, templates and copy lint, dossier, narrator guard | algo outputs |
| `api/` | FastAPI `/api/v1`, SSE, error envelope | orchestrator, store |
| `cli` | `python -m nakshatra.cli <place> --budget N [--offline]` | orchestrator |
| `eval/` | Injection, controls, null shuffle, credit efficiency, plots | graph, algo, store (read only) |
| `web/` | React + Vite + Cytoscape: InvestigateForm, useRunStream, GraphCanvas, CreditBar, RingPanel, RatingCard, ExportMenu, drawers | API |

**Data flow.** Input → `parse_place` (data_id regex) → `resolving`: `google_maps` place (1 credit; d_p < 20 → E_TOO_FEW_REVIEWS) → baseline category search (μ_cat, baseline d_p) → `sampling`: alternating `newestFirst`/`ratingHigh` pages from the sample pool → ingest with date intervals → s0 for each reviewer → `expanding`: pop max π, contributor call, ingest places and edges; every 5th expansion `refining` one hot place; re-peel after each call; `ring_update`; stop on plateau or budget → `mining`: find up to 5 rings, Poisson display statistic, permutation gate, lockstep, adjusted rating → `reporting`: build result (pseudonyms, explanations), persist `rings` and `results` → `done`. Every SerpApi call writes a ledger row and a `credit` event; every new node or edge emits an event.

**Runtime model.** One asyncio task per run, at most one active run (409 otherwise). State machine (SRS §6.4): `created → resolving → sampling → expanding ⇄ refining → mining → reporting → done`; any state → `failed` or `cancelled`. Events are persisted before fan-out (`seq` gapless) and replayed to late or reconnecting SSE clients. Cache: SHA-256 of canonical params without `api_key`; failed calls are never cached. Offline mode serves only from the cache, and a miss gives E_CACHE_MISS. CPU-heavy algorithm work runs in `asyncio.to_thread`.

**Non-functional constraints.** Credits used ≤ budget (one choke point, tested). Determinism (sorted ingest, index tie-breaks, explicit seeds, reference time from the cache — DECISIONS B1–B3). First node within 5 s; full run within 180 s; replay within 10 s. Privacy: no names, photos or profile URLs stored; `S`/`R` pseudonyms; raw IDs only in the dossier, behind a warning. Copy: never "fake", "fraud", "scam" or "fraudulent", enforced by a lint test. Localhost binding; the key comes from the environment only.

## 3. Current repository state (Oct 4)

- **Exists:** `docs/` (11 design docs), `CLAUDE.md`. Git repository on `main` with no commits.
- **Missing:** everything else: no package, configs, tests, fixtures, frontend, CI or cached data.
- **Conflicts with docs:** none, because nothing has been built.
- **Toolchain:** system Python 3.14 and `uv` 0.12 (pin Python 3.12 via uv for wheel availability; `requires-python >=3.11` as documented). Node 26 present (docs say 20+). No `SERPAPI_API_KEY` in the environment, so T01/T02 are blocked on the user. Everything is built against fixtures (ground rule 3).

## 4. MVP checklist

Never-cut items (MVP §3): **M5, M6, M11**.

| ID | Requirement | Acceptance test | Module | Status |
| --- | --- | --- | --- | --- |
| M1 / FR1 / IN-1..4 | Place input by URL / data_id; budget 20–200 | URL fixtures → data_id; bad input 400 E_BAD_PLACE with 0 credits; d_p < 20 → E_TOO_FEW_REVIEWS after 1 credit | `api`, `orchestrator`, `cli` | done (`test_api`, `test_e2e_slice`) |
| M2 / FR20–21 / OP-1..3 / CR-9 | Cache-first client, budget tokens, ledger | ledger billed ≤ budget at 20/60/200; repeat run costs 0; key never cached; 429 retry; 401 E_AUTH; non-Success not cached; offline miss E_CACHE_MISS | `serp`, `store` | done (`test_client`, `test_budget`, `test_e2e_slice`) |
| M3 / FR4 / CR-2,3 | Seed sampling `newestFirst` + `ratingHigh`, baseline | No duplicate review_id; exact dates on seed edges | `orchestrator`, `graph` | done (`test_ingest`, `test_e2e_slice`) |
| M4 / FR5,6,8 / CR-1,4,5,8 | Prior + priority expansion + plateau | I2 monotone in k_u; local guide lowers s0; I4 never expanded twice; plateau fixture stops early | `algo.prior`, `algo.expander` | done (`test_algo`) |
| **M5** / FR10 / DT-2 | Weighted ring mining | I5: planted 8×6 ring returned first; sparse random → none; camouflaged ring still found | `algo.peel` | done (`test_algo`) |
| **M6** / FR11 / DT-3,4 | Poisson display + permutation gate | m = 0 → p = 1; power-user pair unremarkable; degrees preserved; on null graphs share of p < α ≈ α | `algo.significance` | done; `s` uncalibrated (DECISIONS B8) |
| M7 / FR14 / RP-1 | Adjusted rating, `newestFirst`, CI | I6 no-ring invariant; CI contains the point; same seed → same CI | `algo.rating` | done (`test_algo`) |
| M8 / FR9 / IF-20,21 | SSE with replay | First node < 5 s; gapless seq; Last-Event-ID resume; no raw IDs | `api`, `orchestrator.events` | done (`test_api`); first-node latency to measure in the UI |
| M9 / IF-1..6 / RP-2,3 | Result screen: rating card, verdict, ring cards, graph, place drawer | Flow A1–A9 in the browser | `web`, `report` | done (**G3** Oct 5; checked by scripted headless-Chromium screenshots, real + synthetic runs) |
| M10 / NF-6 | Offline replay from `demo.db` | Clean clone, no key: replay identical (B3), 0 network calls | `store.export_demo`, `orchestrator` | done (`test_replay`; `make replay`; 6.2 s replay) |
| **M11** / FR22 / OP-4 / NF-7..10 | Evaluation harness | `make eval` reproduces committed plots (injection grid, controls, null calibration, credit efficiency) | `eval/` | done; results under `eval/plots/*_<config hash>` |
| M12 | README | Insight, prior art, integration map, method, results, limitations, demo | `README.md` | done (Oct 5) |
| NF-11..14 | Security, privacy, copy | Key grep test; localhost bind; banned-word lint | cross-cutting | done (key, copy, `make dev` binds 127.0.0.1) |
| DM §5.3 | Integrity check | `python -m nakshatra.store.check` returns 0 rows | `store.check` | done (`test_store`, `test_e2e_slice`) |

**Should** (after all Musts; status Oct 5: **all done**: S1, S2, S3 MD + PDF, S4, S5, S6): S1 hot-place refinement (CR-7), S2 lockstep (DT-5), S3 dossier MD/PDF (RP-4), S4 ledger drawer, S5 cancel with partial result, S6 ring guards. Refinement and lockstep are cheap and sit in the core loop, so they are built right after the Must slice (PLAN T17 and T20 are scheduled Oct 7).
**Could:** C1 place search, C2 MinHash, C3 LLM narrator, C4 repeat clients, C5 upstream PR.
**Cut order** (first to go): C3, C5, C4, C2, C1, S3-PDF, S6, S5, S1.
**Won't:** other platforms, accounts/hosting/mobile, supervised ML, monitoring, Hindi/Tamil normalisation, Docker.

## 5. Implementation order

Critical path (PLAN §3, checked): credits/config → store → SerpApi client → graph ingest → mining → significance → orchestrator (**G1**) → evaluation (**G2**) → API/SSE → live UI (**G3**) → demo DB → README → recording.

| # | Step (PLAN task) | Depends on | Done when | Est. |
| --- | --- | --- | --- | --- |
| 1 | Scaffold: pyproject, Makefile, config.yaml, .env.example, ruff, pytest, CI, purity lint (T03) | — | `make test` green; purity test fails on an `httpx` import in `algo/` | 1 h |
| 2 | Settings + `Config` + config hash | 1 | Hash is stable across loads | 0.3 h |
| 3 | Store: schema v2, repos, integrity check (T05) | 1 | Fresh DB: check returns 0 rows; edge precision upsert test | 1.5 h |
| 4 | Budget (T06) | 1 | used ≤ total at 20/60/200; rollover; B1 semantics | 0.5 h |
| 5 | SerpClient + engines + PII scrub (T07, T08) | 3, 4 | respx: 429 retry, 401 E_AUTH, quota, non-Success not cached, offline miss, key absent from DB | 2.5 h |
| 6 | Synthetic SerpApi world fixture (stands in for T08's real fixtures until a key exists) | 5 | Responses follow API §8 shapes; deterministic per seed | 1 h |
| 7 | Dates (T09) + Graph + ingest (T10) | 1 | I1; garbage → unknown; non-Google skipped; truncated at 200 | 2 h |
| 8 | Prior + burst z (T11), Expander + Plateau (T12) | 7 | I2, I4, plateau stops | 1.5 h |
| 9 | Peel + trimming + multi-ring (T13) | 7 | I5 planted first; sparse → none | 2 h |
| 10 | Significance: Poisson display (T14) + permutation gate (T15) | 9 | m = 0 → p = 1; degrees preserved; null share ≈ α | 2.5 h |
| 11 | Adjusted rating (T16) | 7 | I6; CI contains the point; seeded | 1 h |
| 12 | Orchestrator `Run` + events + result builder + CLI (T19) — **vertical slice** | 3–11 | **G1** (on fixtures): live run against the mocked world finds the planted ring; offline replay ×2 identical; repeat costs 0 | 2.5 h |
| 13 | Refinement in the loop (T20), lockstep (T17) | 12 | Refine pool respected; co-timed ring ≥ 0.8; wide → null | 1.5 h |
| 14 | Eval: injection, controls, null calibration, efficiency, plots (T30–T32) | 12 | `make eval` writes plots with the config hash; recall/precision computed | 4 h |
| 15 | Real data: T01/T02 checks, scouting, calibration, freeze config (T31, T33) — **needs a key** | 14 | **G2** decision recorded | 3.5 h |
| 16 | API: runs, status, health, envelope, idempotency, 409 (T21) | 12 | Contract error tests | 1.5 h |
| 17 | SSE replay/resume/heartbeat (T22); evidence + ledger (T23); openapi.yaml | 16 | Contract SSE tests; OpenAPI diff test | 2.5 h |
| 18 | Web: scaffold + S1 (T26), live graph (T27), S3 result (T28), drawers (T29) | 17 | **G3**: Flow A1–A9 in the browser | 6 h |
| 19 | Cancel (T24), dossier MD (T25), ring guards (T18) | 17 | Partial result; 7 dossier sections | 2.5 h |
| 20 | demo.db export + replay test (T34); README (T35); usability check (T36) | 15, 18 | Clean clone replays; README per MVP M12 | 4 h |
| 21 | Record (T37), submit (T38) | 20 | Ring visible before 0:45; submitted by Oct 10 18:00 IST | 2 h |

**Gates** (PLAN §4, MVP §6):

- **G1**, end of Oct 6: a CLI end-to-end run produces rings or a clean result. Fail → cut S1 and S6.
- **G2**, Oct 7 18:00: a real ring found? If not → demo with an injected ring, a control and the best real anomaly. Recall < 0.8 → raise the minimum ring size and report honestly.
- **G3**, Oct 8 22:00: Flow A works in the browser. Fail → cut every Could and S3-PDF.
- **Feature freeze**: Oct 9 12:00.
- **Submit**: by Oct 10 18:00.

## 6. First vertical slice (Phase 7)

`python -m nakshatra.cli <url-or-data_id> --budget N [--offline] [--db PATH]`:

load config → open the store (schema v2) → resolve seed → baseline → sample pages → ingest with intervals → s0 → budgeted expansion with plateau → mine → Poisson display + permutation gate → adjusted rating → result JSON on stdout. The ledger records every call.

**Done when:**

- (a) a live run against the respx-mocked synthetic SerpApi recovers the planted ring;
- (b) a second run of the same input bills 0 credits;
- (c) two offline replays produce identical result JSON (DECISIONS B3);
- (d) the integrity check returns 0 rows.

All four are automated in `tests/test_e2e_slice.py`. **Status: done (Oct 5).** Steps 1–12 are complete, plus lockstep and refinement from step 13.

## 7. Real-data log

| Date | What | Credits | Outcome |
| --- | --- | --- | --- |
| Oct 5 | T02 field-shape probes (sentinel run) | 6 | DECISIONS C1–C7 |
| Oct 5 | **G1**: CLI live on a real 84-review Coimbatore fertility clinic (`0x3ba858e2ce004617:0xbf828b878d37ae96`) | 18 + 9 | Clean result. The first attempt exposed A18 (1-review accounts expanded first); the rerun followed 9 feasible reviewers across 65 places. Open question for T32: does the 0 → 0 plateau (A15) stop too early on places with ~30 feasible reviewers? |

| Oct 5 | Category search "tourist attraction" (sentinel), for controls | 1 | Control candidates |
| Oct 5 | Clinic #2: Vamsam Hospital & Fertility Centre (`0x3ba85983d088966d:0xeb6a844b48844f9b`) | 22 | Clean: 9 reviewers, 47 places |
| Oct 5 | Controls: Gass Forest Museum, Valankulam Boat House (budget 25 each) | 14 + 14 | Clean, 0 candidates. Used for τ (A21) |

Balance after scouting: **166 of 250** (SerpApi's own count matches the ledger).

## 8. Blocked on the user

- ~~T01: SerpApi key~~ added Oct 5: Free Plan, 250/month, 217 left after G1. Running on the MVP §6 fallback (DECISIONS A19).
