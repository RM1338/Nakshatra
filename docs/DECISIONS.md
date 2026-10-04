# Nakshatra Decisions Log

Conflicts between the design docs, gaps the docs leave open, and deviations made during implementation. Each entry: what, which docs, resolution, why. Precedence used: explicit "supersedes" > specialised doc in its domain (ALG for algorithms/statistics, API for HTTP/SSE, DM for schema, UF for copy) > MVP Scope for scope > whatever best preserves the core idea, determinism and credit safety.

Abbreviations: PRD, SRS, ARCH (System Architecture), LLD (Technical Design), API (API Contract), DM (Data Model), ALG (Core Algorithm Design), UF (User Flow), MVP (MVP Scope), PLAN (Development Plan), NOV (Novelty).

## A. Conflicts between documents

| # | Conflict | Docs | Resolution | Why |
| --- | --- | --- | --- | --- |
| A1 | Significance: λ summed over the ring's own places Q, ring p = median pair p × n_rings (Bonferroni) **vs** city-wide H = Σ_all π_p², m counted over all non-seed places, plus a degree-preserving permutation gate that reruns the miner | SRS §5.5, PRD §5.5, LLD §6.4 vs ALG §6 | **ALG §6.** A ring is reported iff `p_perm < α` **and** median pairwise Poisson p < α. Ring *i* is compared with the *i*-th best density of each null graph. No Bonferroni factor | ALG says it supersedes SRS §5.5; MVP §4 locks it |
| A2 | What the result's single `pval` field means | DM §3 (`reported` = "pval < α"), API `Ring.pval` | `pval` = the permutation p-value (the number that gates reporting). The median pairwise Poisson p goes in an extra field, `pair_pval`. `reported` = the gate in A1 | API §9.1 allows extra fields. UF B4 shows both "permutation p" and the pairwise numbers |
| A3 | Lockstep: pairwise check around one anchor review **vs** exact sweep-line (maximum clique of the interval graph) | LLD §6.5 vs ALG §7.1 | **ALG §7.1** sweep-line | ALG explicitly replaces the LLD version |
| A4 | Adjusted rating computed from every sampled seed review **vs** from `newestFirst` pages only | LLD §6.6 vs ALG §7.2 | **`newestFirst` only.** `ratingHigh` pages are used only to discover reviewers | ALG §7.2 (bias B1); MVP §4 locks it |
| A5 | Schema v1 (LLD) **vs** schema v2 (DM) | LLD §3.1 vs DM §4 | **DM v2** | DM states it is authoritative |
| A6 | DM's `events.type` CHECK omits `warning` and `cancelled`, which the API emits | DM §4 vs API §4.3 | Add both values to the CHECK; DM updated | The API owns SSE event types. Additive change |
| A7 | Migration mechanism: plain SQL migration files (0001 v1, 0002 v2) **vs** a single `schema.sql` with a version pragma | DM §9.3 vs ARCH §10.3 | One `schema.sql` at version 2, applied when `user_version < 2`. Add a `migrations/` folder only when version 3 is needed | No v1 database exists, so a v1→v2 migration would be dead code |
| A8 | REST paths `/api/...` and `?fmt=` **vs** `/api/v1/...` and `?format=` | SRS §3.3, PRD §8, LLD §7.4 vs API §1, §9.1 | **API.** `/api/v1` everywhere, `/api` kept as an alias, `?format=` | API supersedes these explicitly |
| A9 | HTTP status per error code differs (for example E_BUDGET 400 vs 422, E_AUTH 502 vs 503, E_TOO_FEW_REVIEWS 422 vs SSE-only) | SRS App. A vs API §6 | **API §6** catalogue | API owns HTTP |
| A10 | Raw contributor IDs on the SSE stream, with pseudonyms assigned on the client **vs** server-side `S`-pseudonyms | LLD §8.4 vs API §4.3 | **API.** `S` + n on the stream (first-seen order); `R` + n in results (s0 order); raw IDs only in the dossier | API supersedes |
| A11 | SSE phase names (`seed`, `sample`, `expand`, …) **vs** the State enum (`resolving`, `sampling`, …) | SRS §3.3 vs API §1, §7 | **API State enum** | API owns SSE |
| A12 | Result JSON shape: DM §6.3 (top-level `run_id`, `state`, `credits`, `explanations[]`) **vs** API `Result` (per-ring `explanation`, `stream_members`, `no_coordination_message`) **vs** SRS/PRD (ring places as strings) | DM, API, SRS, PRD | Store the **union** of DM and API fields in `results.result_json`; ring places are objects `{data_id, title, d_p}` | Both sets are additive; DM and API outrank SRS/PRD |
| A13 | Package name `lockstep/` in LLD §6.4 onwards **vs** `nakshatra/` | LLD | `nakshatra/` | Leftover from an old name |
| A14 | Relative-date intervals: LLD writes weeks/months as `max(n − 0.5, 0)`; SRS writes (N − 0.5) | LLD §5.1 vs SRS §5.1 | SRS formulas, with the upper bound clamped to T (so t_hi ≤ T, as SRS also requires) | Clamping only matters for "0 weeks ago", which never appears |
| A15 | Plateau rule when no ring has been found yet (best density 0): LLD's `old > 0` check never stops, so a clean place spends the whole budget | LLD §6.2 vs SRS-CR-8 ("improves by less than 2%") | Stop when `best ≤ old · (1 + ε)` over the window, **including 0 → 0** | Precedence rule 4 (credit safety). ALG §4.2: "a plateau means … there is no ring to find" |
| A16 | Error codes used in code but missing from the catalogue (`E_BUDGET_EXHAUSTED`) | LLD §4.2 vs API §6 | Internal only. The orchestrator catches it and ends the phase. It never reaches the API | Keeps the catalogue closed |
| A17 | No separate Evaluation Plan or Demo Plan document | — | Evaluation = ALG §10 + PRD §10 + SRS-NF-7..10. Demo = UF §8 + MVP §6–7 | — |

## B. Determinism and budget semantics (gaps the docs leave open)

| # | Issue | Resolution | Why |
| --- | --- | --- | --- |
| B1 | "Cache hits return the token" (LLD §4.1, PLAN T06) makes a repeat run crawl *deeper* than the original, because cached calls are free. An offline replay of a budget-limited run would then keep expanding past the original stopping point and hit `E_CACHE_MISS`. That contradicts byte-identical replay (SRS-NF-6, MVP M10) | **The budget limits calls, not just credits.** Every call, cached or live, takes a reservation and spends it (`Budget.settle(tok, spent=True)`). `used` / billed counts only live billed calls. Invariant: billed ≤ calls ≤ budget. A cache hit is still free in credits ("a repeat run costs 0", M2). The only token ever returned is one for a call that failed before being answered | Determinism and credit safety both hold. The stated invariant `used ≤ budget` still holds and is tested |
| B2 | "T = runs.started_at" for parsing relative dates is wrong for cached responses fetched days earlier (the cache is shared across runs), and it changes when a run is replayed later | **The reference time for a response is its `serp_cache.fetched_at`.** The client returns `fetched_at` with every response | More correct ("a month ago" is relative to when it was fetched), and identical in every replay with no schema change |
| B3 | "Byte-identical result JSON" across runs, when `run_id` and the credits block legitimately differ (a live run bills 57; its replay bills 0) | The determinism test compares result JSON with `run_id` and `credits` removed, serialised with sorted keys. Everything else must match byte for byte | Those are the only fields that describe the run rather than the finding |
| B4 | The seed for the permutation shuffle | Config `stats.perm_seed` (default 11) and `stats.n_perm` (default 200, raised to 500 when p sits at the floor, ALG §6.2) | ALG §6.2 needs a fixed seed; PLAN rules say every random step takes one |
| B5 | Curveball mixing length: "5\|E\| swaps" | 5·\|U\| curveball *trades* per null sample. One trade fully reshuffles one pair of rows, which mixes far more than one edge swap | Same mixing goal; 5\|E\| trades would take about 40 s per run in Python |
| B6 | s0 for reviewers discovered during refinement (they are not seed reviewers) | Use 0.5, as in LLD §7.2 | LLD default; it only affects crawl order |

## C. SerpApi field shapes (PLAN T02, still to be checked live)

No API key is present yet. Following ground rule 3, the client is built against fixtures that follow the documented field shapes. These items stay **unverified** until T02 runs in the playground:

| # | Item | Current assumption | If wrong |
| --- | --- | --- | --- |
| C1 | `google_maps` place lookup by `data_id` | `type=place`, `data=!4m5!3m4!1s<data_id>!8m2!3d0!4d0` (LLD §4.3) | Switch to `place_id`. A one-line change in `engines.py` |
| C2 | `json_restrictor` syntax | **Off by default** (`serp.json_restrictor: false`). Instead, personal fields (user/contributor `name`, `link`, `thumbnail`, review `images`) are removed from the response before it is cached | DM §8 requires that names and photos are never stored. Removing them ourselves meets that whether or not the restrictor works. Turn the restrictor on once its syntax is confirmed |
| C3 | `place_info.reviews` present in contributor reviews (SRS OI-1) | Read if present. Otherwise d_p is unknown, and the column weight uses d_p = 50 (DM §7). Backfill (CR-6) is P1 | Popularity weights get weaker; the backfill is the planned fix |
| C4 | Contributor `num=200`, 200-review cap | As documented | Pagination needed |
| C5 | Reviews first page = 8 results, no `num`; later pages `num=20` | As documented | — |
