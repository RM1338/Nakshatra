# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

All Musts are built: SerpApi client, graph, algorithms, orchestrator + CLI, HTTP API/SSE (`nakshatra/api/main.py`), web UI (`web/`), eval harness (`eval/`), `data/demo.db` + `make replay`, README. Config frozen (hash `8dfd7dcb`; changing `config.yaml` invalidates `eval/plots/`). See `docs/IMPLEMENTATION_PLAN.md`. All Should items are done too (dossier MD/PDF, cancel + partial results, ring guards). Could C1 (place search) is done. Remaining: demo recording and submission (user); other Could items only on request. Work follows `docs/Nakshatra Development Plan.md` (tasks T01–T41, submission Oct 10, 2026). Commit messages start with the task ID (`T13: weighted peeling with trimming`) and carry **no `Co-Authored-By` or other AI attribution trailers** (user instruction); `main` must always run. Record every deviation from the docs in `docs/DECISIONS.md`, in the same commit.

Nakshatra: a local app that takes one Google Maps place, spends a fixed SerpApi credit budget (default 60) crawling reviewers via the Contributor Reviews engine, finds coordinated reviewer rings with weighted dense-subgraph peeling, tests them with a permutation gate plus a Poisson display statistic, and shows a ring-adjusted rating.

## Doc precedence (docs conflict in places)

- Significance = city-wide Poisson display stat + degree-preserving permutation gate (Core Algorithm §6) — **supersedes SRS §5.5**.
- Data Model schema v2 is authoritative over the LLD schema. Full conflict list and resolutions: `docs/DECISIONS.md`.
- API paths are `/api/v1/...` with error envelope and `S`/`R` pseudonyms (API Contract §9.1) — LLD route samples are older.
- LLD code samples for `significance.py`, `lockstep.py`, `api/routes.py`, `report/`, `useRunStream.ts` are stale; LLD also uses the old package name `lockstep/` in places — the package is `nakshatra/`.

## Commands

```
./run.sh [--replay]                       # install deps, start API :8000 + Vite :5173, open browser; Ctrl-C stops both
uv sync                                   # install (Python 3.13 via uv; requires >= 3.11)
make test                                 # ruff + pytest (tests never call SerpApi)
uv run pytest tests/test_algo.py -k planted         # single test
uv run python -m nakshatra.cli <maps-url|data_id> --budget 60 [--offline] [--db PATH]
uv run python -m nakshatra.store.check [db]         # integrity check (Data Model §5.3), must print zeros
NAKSHATRA_DB=data/dev.db make synth       # crawl the synthetic SerpApi city into a dev DB (no key needed)
make dev                                  # API on 127.0.0.1:8000 (docs at /api/v1/docs)
make eval                                 # injection, controls, null calibration, credit efficiency -> eval/plots/ (~20 min)
make replay                               # judge mode: data/demo.db, no key, offline forced, :8000
make demo / make dev                      # built SPA on :8000 / API :8000 + Vite :5173
cd web && npx tsc -b                      # typecheck the UI
```

`SERPAPI_API_KEY` is in `.env` (git-ignored). It is a **Free Plan: 250 searches/month, scarce.** Never spend live credits without the user's go-ahead; follow the allocation in DECISIONS A19. The SerpApi `/account` endpoint is free for checking the balance. `tests/synth_world.py` is a deterministic fake SerpApi (a city with a planted ring), served through an httpx `MockTransport`. Use it for tests and dev data. For UI checks, start the server with `SERPAPI_API_KEY=` (blank) so scripted clicks can never spend credits. Screenshots: system `/usr/bin/chromium` driven by playwright-core (the Playwright MCP's bundled Chrome is not installed).

## Architecture

Modular monolith: one FastAPI process + SQLite (WAL) + React/Vite/Cytoscape SPA. Packages under `nakshatra/`:

- `orchestrator/` owns a run (state machine, budget split, phases resolve → baseline → sample → expand/refine loop → mine → report) and is the **only** package that calls the others.
- `serp/` is the **only** network code: cache-first `SerpClient.get(engine, params)`, retries, `json_restrictor`, ledger writes, offline mode. Raw JSON cached forever, keyed by SHA-256 of params without `api_key`.
- `graph/` and `algo/` are **pure** (stdlib + numpy only; CI lints against `httpx`/`sqlite3`/`fastapi` imports). In-memory graph uses dense int indices and parallel numpy edge arrays with lazy CSR. Peeling is hand-written (not networkx/rgmining-fraudar); networkx only in `eval/`.
- `store/` SQLite access; `events` table enables SSE late-join replay.
- `report/` result assembly, pseudonymisation boundary (raw `contributor_id` never leaves it), dossier, optional LLM narrator.
- `api/` routes + SSE; `eval/` injection, controls, null shuffles, plots.

## Invariants that must hold

- **Credits:** every SerpApi call, cached or live, needs a `Budget.reserve(pool)` token; `serp/` refuses without one. Reservations are never returned, so replay matches live (DECISIONS B1/B7). Cache hits bill 0. billed ≤ calls ≤ budget.
- **Determinism:** same cache + config ⇒ byte-identical result JSON (`tests/test_e2e_slice.py`; `run_id` and `credits` excluded, DECISIONS B3). Ties broken by `contributor_id` / node index; sort keys at ingest; relative dates are parsed against the cache row's `fetched_at` (DECISIONS B2), never `time.time()` in algorithms; randomness only via `numpy.random.default_rng(seed)` with explicit seed.
- **No LLM in any decision.** Narrator gets result JSON only; output rejected if it contains any number not in the JSON.
- **Tests never call SerpApi** — fixtures in `tests/fixtures/serpapi/` and `respx` only.
- Run CPU-heavy `algo/` work via `asyncio.to_thread`.
- Output describes statistical anomalies, never intent ("fake", "fraud") — `test_copy.py` lints banned words.
- Errors: `NakshatraError(code, message)` with codes from SRS Appendix A.
