# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

Design-only so far: `docs/` holds the full spec set, no code exists yet. Build follows `docs/Nakshatra Development Plan.md` (tasks T01–T41, submission Oct 10, 2026). Commit messages start with the task ID (`T13: weighted peeling with trimming`); branches are short, named like `t13-peel`; `main` must always run `make demo`.

Nakshatra: local web app that takes one Google Maps place, spends a fixed SerpApi credit budget (default 60) crawling reviewers via the Contributor Reviews engine, finds coordinated reviewer rings with weighted dense-subgraph peeling, tests them statistically, and shows a ring-adjusted rating.

## Doc precedence (docs conflict in places)

- Significance = city-wide Poisson display stat + degree-preserving permutation gate (Core Algorithm §6) — **supersedes SRS §5.5**.
- Data Model schema v2 is authoritative over the LLD schema.
- API paths are `/api/v1/...` with error envelope and `S`/`R` pseudonyms (API Contract §9.1) — LLD route samples are older.
- LLD code samples for `significance.py`, `lockstep.py`, `api/routes.py`, `report/`, `useRunStream.ts` are stale; LLD also uses the old package name `lockstep/` in places — the package is `nakshatra/`.

## Commands (planned, per LLD/Architecture)

```
make dev      # uvicorn API on :8000 with --reload + Vite on :5173 (proxies /api)
make demo     # uvicorn serving built SPA from web/dist on :8000
make replay   # demo with NAKSHATRA_OFFLINE=1 against shipped data/demo.db (no key, 0 credits)
make eval     # evaluation harness, no server; reproduces committed plots
make test     # pytest; ruff for lint
pytest tests/test_peel.py -k planted     # single test
python -m nakshatra.cli <maps-url>       # end-to-end run without UI
python -m nakshatra.store.check          # integrity check, must return 0 rows
```

Python 3.11+, Node 20+ (UI build only). Live runs need `SERPAPI_API_KEY` in `.env`. Settings layers: env vars (`NAKSHATRA_DB`, `NAKSHATRA_OFFLINE`, …) → `config.yaml` (algorithm params, frozen after calibration) → per-run budget override; resolved config stored in `runs.config_json`.

## Architecture

Modular monolith: one FastAPI process + SQLite (WAL) + React/Vite/Cytoscape SPA. Packages under `nakshatra/`:

- `orchestrator/` owns a run (state machine, budget split, phases resolve → baseline → sample → expand/refine loop → mine → report) and is the **only** package that calls the others.
- `serp/` is the **only** network code: cache-first `SerpClient.get(engine, params)`, retries, `json_restrictor`, ledger writes, offline mode. Raw JSON cached forever, keyed by SHA-256 of params without `api_key`.
- `graph/` and `algo/` are **pure** (stdlib + numpy only; CI lints against `httpx`/`sqlite3`/`fastapi` imports). In-memory graph uses dense int indices and parallel numpy edge arrays with lazy CSR. Peeling is hand-written (not networkx/rgmining-fraudar); networkx only in `eval/`.
- `store/` SQLite access; `events` table enables SSE late-join replay.
- `report/` result assembly, pseudonymisation boundary (raw `contributor_id` never leaves it), dossier, optional LLM narrator.
- `api/` routes + SSE; `eval/` injection, controls, null shuffles, plots.

## Invariants that must hold

- **Credits:** every live call needs a token from `orchestrator.Budget.reserve(engine)`; `serp/` refuses without one. Cache hits are free. Ledger sum never exceeds budget.
- **Determinism:** same cache + config ⇒ byte-identical result JSON (`test_replay.py`). Ties broken by `contributor_id` / node index; sort keys at ingest; "now" is `runs.started_at`, never `time.time()` in algorithms; randomness only via `numpy.random.default_rng(seed)` with explicit seed.
- **No LLM in any decision.** Narrator gets result JSON only; output rejected if it contains any number not in the JSON.
- **Tests never call SerpApi** — fixtures in `tests/fixtures/serpapi/` and `respx` only.
- Run CPU-heavy `algo/` work via `asyncio.to_thread`.
- Output describes statistical anomalies, never intent ("fake", "fraud") — `test_copy.py` lints banned words.
- Errors: `NakshatraError(code, message)` with codes from SRS Appendix A.
