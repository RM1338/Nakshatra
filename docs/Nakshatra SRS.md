# Nakshatra SRS

Oct 4, 2026 · @Ronel Abraham Mathew

Software Requirements Specification for Nakshatra v1.0 (hackathon release), following the structure of ISO/IEC/IEEE 29148. Product intent and priorities come from the Nakshatra PRD; this document states what the software shall do, testably.

## 1. Introduction

### 1.1 Purpose

This document specifies the functional, interface, data and quality requirements of Nakshatra v1.0. It is written for the developers building the system, the evaluator writing tests, and the SerpApi India Hackathon 2026 judges reviewing the repository.

### 1.2 Scope

Nakshatra is a locally run web application. It takes one Google Maps place and a SerpApi credit budget as input. It returns:

- coordinated reviewer groups (rings), each with a statistical significance score
- a ring-adjusted rating
- an exportable evidence dossier

It covers Google Maps only. Hosting, user accounts and other review platforms are out of scope.

### 1.3 Requirement conventions

- **Shall** marks a mandatory requirement. **Should** marks a recommended one. **May** marks an optional one.
- Requirement IDs take the form `SRS-<area>-<n>`. The areas are `IN` (input), `CR` (crawl), `DT` (detection), `RP` (report), `OP` (operations), `IF` (interface), `DA` (data) and `NF` (non-functional).
- Every requirement carries a priority: P0 is required for v1.0, P1 should ship, P2 is optional.

### 1.4 Definitions

| Term | Definition |
| --- | --- |
| Seed place (p0) | The Google Maps place under investigation |
| Contributor / reviewer (u) | A Google Maps account, identified by `contributor_id` |
| Edge | One review by u of place p, carrying a rating and a time interval |
| Credit | One billable SerpApi search. Responses served from SerpApi's cache are not billed |
| Expansion | Fetching a contributor's review history |
| Hot place | A non-seed place reviewed by at least 2 expanded suspects |
| Ring (R) | A user set together with a place set, returned by the ring miner and passing the significance test |
| Density g(S) | The popularity-weighted edge mass of a subgraph divided by its node count (§5.4) |
| Lockstep ratio | The share of a ring's places where at least 60% of members' reviews co-occur in time |
| Offline replay | A run served only from the local cache, making zero SerpApi calls |
| d\_p | The global review count of place p, as reported by Google Maps |

### 1.5 References

- Nakshatra PRD v1.0 (companion document)
- [SerpApi Google Maps Reviews API](https://serpapi.com/google-maps-reviews-api)
- [SerpApi Google Maps Contributor Reviews API](https://serpapi.com/google-maps-contributor-reviews-api)
- [SerpApi Google Maps API](https://serpapi.com/google-maps-api)
- [Hackathon rules](https://serpapi.github.io/serpapi-india-hackathon-2026/rules.html)
- Hooi et al., FRAUDAR, KDD 2016 ([ACM](https://unpaywall.org/10.1145%2F2939672.2939747))
- ISO/IEC/IEEE 29148:2018, Requirements engineering

## 2. Overall description

### 2.1 Product perspective

Nakshatra is a standalone system with four parts:

- a browser client
- a FastAPI server
- a local SQLite store
- one external dependency, the SerpApi HTTPS API

An optional LLM provider may be used to write a narrative summary. No requirement depends on it.

```text
Browser (React + Cytoscape)
   | REST + SSE (localhost:8000)
FastAPI server
   |-- serp/   SerpApi client, cache, ledger  --> https://serpapi.com/search
   |-- graph/  normaliser, interval parser
   |-- algo/   prior, expander, peel, significance, lockstep, rating
   |-- report/ dossier, narrator (optional LLM)
   |
SQLite (nakshatra.db)
```

### 2.2 Product functions

1. Resolve a seed place from a URL, an ID or a search query.
2. Sample the seed place's reviews and score each reviewer's prior suspicion.
3. Expand reviewers in priority order, within the credit budget.
4. Mine rings, then test their significance and temporal lockstep.
5. Compute a ring-adjusted rating with a confidence interval.
6. Stream progress to the UI, then render results and export a dossier.
7. Replay any past run offline, deterministically.
8. Run the evaluation harness.

### 2.3 User classes

| Class | Frequency | Technical skill | Primary features |
| --- | --- | --- | --- |
| Consumer (e.g. a patient choosing a clinic) | Occasional | Low | Investigate, rating card, plain-language explanation |
| Investigator (journalist, complainant) | Frequent | Medium | Ring drill-down, dossier export |
| Developer / evaluator / judge | Setup and review | High | Offline replay, evaluation harness, ledger |

### 2.4 Operating environment

- Python 3.11+, Node 20+, on macOS, Linux or Windows (WSL).
- A current version of Chrome, Firefox or Edge, on screens from 1280×720 up.
- Network access to `serpapi.com` for live runs. No network access is needed for offline replay.

### 2.5 Design and implementation constraints

- **C1.** All Google data shall be obtained through SerpApi. Direct scraping of Google is prohibited.
- **C2.** Detection, scoring and rating logic shall be deterministic code. An LLM shall not influence any number or ring membership.
- **C3.** The SerpApi key shall be supplied via the `SERPAPI_API_KEY` environment variable only.
- **C4.** The deliverable shall run locally, as the hackathon rules require for the demo.
- **C5.** The total development credit budget is limited to about 1,200 credits.

### 2.6 Assumptions and dependencies

- **A1.** The SerpApi response schemas match the current documentation. In particular:
  - `user.contributor_id` and `iso_date` are present in Maps Reviews.
  - `place_info.data_id` is present in Contributor Reviews.
- **A2.** The Contributor Reviews engine returns at most 200 reviews per contributor, with relative date strings.
- **A3.** The first page of Maps Reviews returns 8 results. Later pages accept `num` up to 20.
- **A4.** Identical requests made within 1 hour are served from SerpApi's cache and are not billed.
- **A5.** Review counts reported by Google (d\_p) are an adequate proxy for place popularity.

## 3. External interface requirements

### 3.1 User interface

| ID | Requirement | Pri |
| --- | --- | --- |
| SRS-IF-1 | The UI shall provide a single input that accepts a Google Maps URL, a `place_id` or a `data_id`, plus a budget control (integer 20 to 200, default 60) | P0 |
| SRS-IF-2 | During a run, the UI shall show credits used out of the budget, the current phase and elapsed time, updated at least once per second | P0 |
| SRS-IF-3 | The UI shall render the graph incrementally. Users are circles, places are squares and the seed is a highlighted hub; each ring gets a distinct colour | P0 |
| SRS-IF-4 | The UI shall show a rating card with the displayed rating, the adjusted rating and the 95% interval | P0 |
| SRS-IF-5 | Selecting a ring shall highlight its nodes. Selecting a shared place shall list each member's rating and date interval for that place | P0 |
| SRS-IF-6 | The UI shall never show the words "fake", "fraud" or "scam". Reviewers shall appear as pseudonyms R1…Rn | P0 |
| SRS-IF-7 | Every numeric output shall have a tooltip naming its formula or source | P1 |
| SRS-IF-8 | The UI shall offer "Export dossier (MD/PDF)", "Rerun with larger budget" and "Replay offline" | P1 |

### 3.2 Software interface: SerpApi

| ID | Requirement | Pri |
| --- | --- | --- |
| SRS-IF-10 | The system shall call `GET https://serpapi.com/search` with `engine` ∈ {`google_maps`, `google_maps_reviews`, `google_maps_contributor_reviews`} | P0 |
| SRS-IF-11 | Every call shall set `hl=en`. Contributor calls shall set `num=200`. Review calls after the first page shall set `num=20` | P0 |
| SRS-IF-12 | The system shall use `json_restrictor` to request only the fields listed in §6.1 | P1 |
| SRS-IF-13 | On HTTP 429 or 5xx, the system shall retry up to 3 times, with exponential backoff starting at 1 s. On 401, it shall abort the run with `E_AUTH` | P0 |
| SRS-IF-14 | The system shall treat `search_metadata.status != "Success"` as a failed call. Failed calls shall not be cached | P0 |

### 3.3 Software interface: REST and SSE

| Method | Path | Request | Response |
| --- | --- | --- | --- |
| POST | `/api/runs` | `{place: string, budget: int, offline: bool}` | `201 {run_id}`, or `400` with an error code |
| GET | `/api/runs/{id}/events` | none | `text/event-stream` (events below) |
| GET | `/api/runs/{id}` | none | `200` with the result JSON (§6.3), or `404` |
| GET | `/api/runs/{id}/dossier?fmt=md\|pdf` | none | A file |
| GET | `/api/runs/{id}/ledger` | none | An array of ledger rows |
| GET | `/api/places/search?q=&near=` | none | Up to 10 candidates (P1) |

| SSE event | Payload |
| --- | --- |
| `phase` | `{phase: seed\|sample\|expand\|refine\|mine\|report, ts}` |
| `credit` | `{used, budget, cached}` |
| `node` | `{id, kind: user\|place, label, attrs}` |
| `edge` | `{u, p, rating, t_lo, t_hi, exact}` |
| `ring_update` | `{ring_idx, members, places, density}` |
| `done` | `{run_id}` |
| `error` | `{code, message}` |

- **SRS-IF-20 (P0).** The SSE stream shall send a heartbeat comment every 10 s.
- **SRS-IF-21 (P0).** Events shall be replayable: a client that connects late shall first receive all prior events of the run.

### 3.4 Storage interface

- **SRS-IF-30 (P0).** The system shall persist all state in one SQLite file. The default path is `./data/nakshatra.db`, overridable with `NAKSHATRA_DB`.
- **SRS-IF-31 (P1).** Write-ahead logging (WAL) shall be enabled, so that the SSE readers and the crawl writer can work at the same time.

## 4. System features and functional requirements

### 4.1 Input and seed resolution

| ID | Requirement | Pri |
| --- | --- | --- |
| SRS-IN-1 | The system shall parse a `data_id` (pattern `0x[0-9a-f]+:0x[0-9a-f]+`) from Google Maps URLs, and accept a raw `place_id` or `data_id` | P0 |
| SRS-IN-2 | The system shall resolve the seed with one `google_maps` call and store its title, type, gps, rating and d\_p | P0 |
| SRS-IN-3 | The system shall reject seeds with d\_p < 20 with `E_TOO_FEW_REVIEWS`, consuming no further credits | P0 |
| SRS-IN-4 | The system shall reject budgets outside 20–200 with `E_BUDGET` | P0 |
| SRS-IN-5 | Given a query and area, the system shall return up to 10 candidate places using 1 credit | P1 |

### 4.2 Crawl

| ID | Requirement | Pri |
| --- | --- | --- |
| SRS-CR-1 | The system shall split the budget B up front: seed and sample get ⌈0.20B⌉, expansion gets ⌊0.65B⌋, and refinement gets the rest. Unspent allocation shall roll forward to the next phase | P0 |
| SRS-CR-2 | The system shall sample seed reviews with `sort_by=newestFirst` and `ratingHigh`, alternating pages, and deduplicate them by `review_id` | P0 |
| SRS-CR-3 | The system shall run one `google_maps` category query near the seed and store up to 20 baseline places | P0 |
| SRS-CR-4 | The system shall compute s0(u) for every sampled reviewer (§5.2) | P0 |
| SRS-CR-5 | The system shall expand reviewers in descending priority π (§5.3), one `google_maps_contributor_reviews` call per reviewer, and shall never expand a contributor twice in a run | P0 |
| SRS-CR-6 | Every new place found in a contributor response shall become a node with d\_p, when `place_info` provides it. Otherwise the place shall be queued for a popularity backfill, capped at 5 calls | P1 |
| SRS-CR-7 | After every 5 expansions, the system shall refine at most one new hot place with `google_maps_reviews` (`newestFirst`, 1 page) and push its 4- and 5-star reviewers into the queue | P1 |
| SRS-CR-8 | The system shall stop when the credits used reach B, or when the best-ring density improves by less than 2% over 8 consecutive expansions, whichever comes first | P0 |
| SRS-CR-9 | The system shall never issue a call that would exceed B. Cached responses shall not count against B | P0 |
| SRS-CR-10 | A contributor that returns exactly 200 reviews shall be marked `truncated=true` | P1 |

### 4.3 Detection

| ID | Requirement | Pri |
| --- | --- | --- |
| SRS-DT-1 | The system shall convert every date string to an interval \[t\_lo, t\_hi\] (§5.1). Unparseable strings shall produce \[−∞, +∞\] and be logged | P0 |
| SRS-DT-2 | The system shall extract up to 5 disjoint rings with weighted greedy peeling (§5.4), subject to the minimum ring constraints | P0 |
| SRS-DT-3 | The system shall compute the expected and observed overlap and a p-value for each ring (§5.5) | P0 |
| SRS-DT-4 | Only rings with corrected p < α (default 0.01) shall be reported. Others shall be retained as "candidates" in the stored result | P0 |
| SRS-DT-5 | The system shall compute a lockstep ratio per ring (§5.6) | P1 |
| SRS-DT-6 | The system shall compute MinHash signatures (128 permutations, 3-word shingles) and report review pairs within a ring with Jaccard ≥ 0.6 | P1 |

### 4.4 Reporting

| ID | Requirement | Pri |
| --- | --- | --- |
| SRS-RP-1 | The system shall compute the adjusted rating and its 95% bootstrap interval (1,000 resamples, fixed seed) (§5.7) | P0 |
| SRS-RP-2 | When no ring is reported, the system shall state the number of reviewers expanded and places examined | P0 |
| SRS-RP-3 | The system shall generate a ring explanation from a fixed template, filled only with computed values | P0 |
| SRS-RP-4 | The system shall export a dossier with: summary, method, parameters, rings, shared-place table, timeline, ledger and limitations | P1 |
| SRS-RP-5 | If an LLM narrator is enabled, its input shall be the result JSON only, and its output shall be rejected if it contains a number absent from that JSON | P1 |

### 4.5 Operations

| ID | Requirement | Pri |
| --- | --- | --- |
| SRS-OP-1 | Every SerpApi request shall go through a cache keyed by SHA-256 of the canonicalised parameters, excluding `api_key` | P0 |
| SRS-OP-2 | Every request shall append a ledger row: run\_id, engine, params\_hash, cached, latency\_ms, ts | P0 |
| SRS-OP-3 | With `offline=true` or `NAKSHATRA_OFFLINE=1`, the system shall make zero network calls and fail with `E_CACHE_MISS` on a miss | P0 |
| SRS-OP-4 | `python -m eval.run_injection --seed N` shall regenerate all evaluation tables and plots from the cache | P0 |

## 5. Algorithmic specifications

Each algorithm is specified by its inputs, outputs, method and invariants. Tests in §8 check the invariants directly.

### 5.1 Date interval parser

- **Input:** a string s and a run reference time T. All Maps calls set `hl=en`, so s is in English.
- **Output:** an interval (t\_lo, t\_hi) with t\_lo ≤ t\_hi ≤ T.
- **Rules:**
  - ISO 8601 → (t, t).
  - "a/N day(s) ago" → (T − (N+1)d, T − N·d).
  - "a/N week(s) ago" → (T − (N+0.5)w, T − (N−0.5)w).
  - "a/N month(s) ago" → (T − (N+0.5)·30d, T − (N−0.5)·30d).
  - "a/N year(s) ago" → (T − (N+0.5)·365d, T − N·365d).
  - "Edited …" prefixes are stripped before parsing.
- **Invariant I1:** for a review carrying both an ISO date and a relative date, the ISO date lies within the relative interval.
- **Revision (Oct 5, DECISIONS C6):** real SerpApi data shows that Google floors to whole units with calendar months and years. The implemented rule is "N units ago" → age ∈ [N, N+1) units (month = 30.44 d and year = 365.25 d, each ±1.5 d), which replaces the ±0.5 rules above.

### 5.2 Reviewer prior

- **Input:** the seed reviews for reviewer u: k\_u, photos\_u, local\_guide\_u, rating r, and t from `iso_date`.
- **Output:** s0(u) ∈ (0, 1).

```latex
s_0(u) = \sigma\big(w_0 + w_1 / \log(2 + k_u) + w_2[r = 5] + w_3[\text{photos}_u = 0] + w_4\, z(t) - w_5[\text{lg}_u]\big)
```

- z(t) is the z-score of the seed's daily review count on day(t), computed over the sampled window. It is clipped to \[−3, 3\].
- Default weights: w = (−1.0, 2.0, 0.8, 0.5, 0.6, 0.7), stored in `config.yaml`.
- **Invariant I2:** s0 is monotonically non-increasing in k\_u, with all other inputs held equal.

### 5.3 Budgeted expander

- **Input:** the seed reviewers with their s0 scores, the expansion budget B\_e, and the refinement budget B\_r.
- **Output:** the graph G, the set of expanded users and the set of hot places.

```text
PQ <- {(s0(u), u) for seed reviewers}
while used < B_e + B_r and PQ not empty:
    u <- PQ.pop_max()
    if u expanded: continue
    add_edges(contributor_reviews(u)); used += cost
    H <- {p != p0 : |expanded reviewers of p| >= 2}
    if expansions % 5 == 0 and refine_used < B_r and (H \ refined) not empty:
        p* <- argmax_{p in H \ refined} |expanded reviewers of p| / log(d_p + 5)
        for v in reviewers(place_reviews(p*)) with rating >= 4:
            PQ.push(s0(v) * (1 + 0.5 * |H_v|), v)
    best <- peel(G).density
    if improvement(best, last 8 expansions) < 2%: break
```

- **Invariant I3:** the credits used never exceed B.
- **Invariant I4:** no contributor is expanded twice.

### 5.4 Weighted peeling (ring miner)

- **Input:** the graph G with the seed place p0 removed, and the global review count d\_p for each place.
- **Output:** up to 5 disjoint rings (U\_i, P\_i).
- **Column weight:** c\_p = 1 / log(d\_p + 5).
- **Objective:** g(S) = Σ\_{(u,p) ∈ E(S)} c\_p / |S|.
- **Method:**
  1. Repeatedly remove the node with the minimum weighted degree, maintaining a min-heap so each removal takes O(log n).
  2. Track the best g(S) seen during peeling.
  3. Return the best S. Remove its users from G and repeat.
- **Ring constraints:** |U\_i| ≥ 4, |P\_i| ≥ 3, and each member reviewed at least 50% of P\_i. Members failing the coverage test are trimmed; a ring that no longer meets the size bounds after trimming is discarded.
- **Complexity:** O(|E| log |V|) per ring.
- **Invariant I5:** on a planted biclique of size ≥ 8 × 6 with low-popularity places, the planted biclique is the first ring returned (fixture test).

### 5.5 Significance

The null model estimates how many places two independent reviewers would share by chance.

```latex
\pi_p = d_p / D, \quad \lambda_{uv} = k_u k_v \sum_{p \in P_i} \pi_p^2, \quad \text{pval}_{uv} = 1 - F_{\text{Pois}}(m_{uv} - 1; \lambda_{uv})
```

- D is the city review mass: D = s · Σ d\_p over all observed and baseline places. The scale s is calibrated so that degree-preserving shuffles give a false-positive rate near α.
- The ring p-value is pval\_R = min(1, median\_{u\<v} pval\_uv × n\_rings\_tested).
- The ring also reports E\[overlap\] as the mean of λ\_uv, and the observed overlap as the mean of m\_uv.

### 5.6 Lockstep ratio

- Two edges on the same place co-occur when the gap between their intervals is at most δ = 14 days.
- A ring place is in lockstep if at least 60% of the members who reviewed it form one co-occurring cluster.
- The ring's lockstep ratio is the number of lockstep places divided by |P\_i|.
- The ratio is reported only when the median interval width is under 30 days. Otherwise it is null.

### 5.7 Adjusted rating

```latex
q_u = [u \in \cup_i U_i] \cdot \min(1, g(R_u)/\tau), \qquad \hat r = \frac{\sum_i (1 - q_{u_i}) r_i + \kappa \mu_{cat}}{\sum_i (1 - q_{u_i}) + \kappa}
```

- τ is the 95th percentile of g measured on the control set. Default τ = 1.0 until calibrated.
- κ = 5.
- μ\_cat is the review-count-weighted mean rating of the baseline places.
- The confidence interval is the 2.5th and 97.5th percentiles of r̂ over 1,000 bootstrap resamples of the sampled reviews, with seed 7.
- **Invariant I6:** with no reported rings, |r̂ − r\_sample| ≤ κ·|μ\_cat − r\_sample| / (n + κ).

## 6. Data requirements and run state machine

### 6.1 Fields consumed from SerpApi

| Engine | Fields (passed via `json_restrictor`) |
| --- | --- |
| `google_maps` | `place_results.{data_id, place_id, title, type, rating, reviews, gps_coordinates}`, `local_results[].{same fields}` |
| `google_maps_reviews` | `place_info`, `reviews[].{review_id, rating, iso_date, iso_date_of_last_edit, snippet, user.{contributor_id, reviews, photos, local_guide}, response.iso_date}`, `serpapi_pagination.next_page_token` |
| `google_maps_contributor_reviews` | `contributor.{level, points, local_guide, contributions}`, `reviews[].{review_id, rating, date, snippet, place_info.{data_id, title, type, gps_coordinates}}` |

### 6.2 Persistent entities

| ID | Entity | Key | Required attributes | Integrity rules |
| --- | --- | --- | --- | --- |
| SRS-DA-1 | `serp_cache` | params\_hash | engine, params\_json, response\_json, fetched\_at | Immutable once written |
| SRS-DA-2 | `ledger` | id | run\_id, engine, params\_hash, cached, latency\_ms, ts | Append-only |
| SRS-DA-3 | `places` | data\_id | title, type, lat, lng, rating, d\_p | d\_p ≥ 0; the latest value wins |
| SRS-DA-4 | `users` | contributor\_id | level, points, k\_u, photos, local\_guide, truncated |  |
| SRS-DA-5 | `edges` | (contributor\_id, data\_id) | rating ∈ \[1, 5\], t\_lo ≤ t\_hi, exact, review\_id, snippet\_minhash | Duplicate keys merge: exact beats relative |
| SRS-DA-6 | `runs` | run\_id | seed\_data\_id, budget, used, state, config\_json, started\_at, ended\_at | budget ≥ used |
| SRS-DA-7 | `rings` | (run\_id, idx) | members, places, density, exp\_overlap, obs\_overlap, pval, lockstep\_ratio, reported |  |
| SRS-DA-8 | `results` | run\_id | displayed, adjusted, ci\_lo, ci\_hi, n\_sampled, events\_json |  |

- **SRS-DA-10 (P0).** Contributor IDs shall be stored raw. They shall be exposed to the UI only as pseudonyms R1…Rn, ordered by s0 descending within a run.
- **SRS-DA-11 (P1).** Review snippets shall be stored only as MinHash signatures, plus excerpts of at most 280 characters for ring members.

### 6.3 Result schema (abridged)

```json
{
  "run_id": "string",
  "state": "done",
  "seed": {"data_id": "string", "title": "string", "rating": 0.0, "d_p": 0},
  "credits": {"budget": 60, "used": 0, "cached": 0},
  "coverage": {"reviewers_sampled": 0, "reviewers_expanded": 0, "places": 0, "edges": 0},
  "rings": [{"idx": 0, "members": ["R1"], "places": ["data_id"], "density": 0.0,
             "expected_overlap": 0.0, "observed_overlap": 0.0, "pval": 0.0,
             "lockstep_ratio": null, "reported": true}],
  "rating": {"displayed": 0.0, "adjusted": 0.0, "ci": [0.0, 0.0], "n_sampled": 0},
  "config": {"alpha": 0.01, "delta_days": 14, "kappa": 5, "weights": []}
}
```

### 6.4 Run state machine

```text
created -> resolving -> sampling -> expanding <-> refining -> mining -> reporting -> done
   |           |            |            |                       |           |
   +-----------+------------+------------+-----------------------+-----------+--> failed
expanding --(budget hit | plateau)--> mining
any state --(user cancel)--> cancelled (partial result kept, badge "low coverage")
```

- **SRS-DA-20 (P0).** Every state transition shall be persisted and emitted as a `phase` event.
- **SRS-DA-21 (P0).** A run in state `failed` shall keep its cache and ledger, and may be resumed offline.

## 7. Non-functional requirements

| ID | Category | Requirement | Measure | Pri |
| --- | --- | --- | --- | --- |
| SRS-NF-1 | Performance | A live 60-credit run shall complete in < 180 s at the 90th percentile | Run log, 10 runs | P0 |
| SRS-NF-2 | Performance | An offline replay shall complete in < 10 s | Timer | P0 |
| SRS-NF-3 | Performance | Peeling on a graph of 10,000 edges shall take < 2 s | Benchmark test | P1 |
| SRS-NF-4 | Performance | The UI shall render up to 3,000 nodes at ≥ 30 fps on a 2020-class laptop | Manual check | P1 |
| SRS-NF-5 | Reliability | One failed SerpApi call shall not abort a run. It is logged and skipped | Fault-injection test | P0 |
| SRS-NF-6 | Reliability | Offline replays shall be deterministic: same cache, config and seed give byte-identical result JSON | Diff test | P0 |
| SRS-NF-7 | Accuracy | Ring recall and precision ≥ 0.8 on injected rings of ≥ 8 members | `eval/run_injection.py` | P0 |
| SRS-NF-8 | Accuracy | ≤ 1 of 10 control places reported at α = 0.01 | `eval/controls.py` | P0 |
| SRS-NF-9 | Accuracy | False-positive rate on 200 degree-preserving shuffles within \[0.5α, 2α\] | `eval/null_shuffle.py` | P1 |
| SRS-NF-10 | Efficiency | The budgeted crawl reaches 0.8 recall with ≤ 50% of the BFS credits | Efficiency curve | P1 |
| SRS-NF-11 | Security | The API key shall never be written to the cache, logs, the repo, the dossier or SSE events | grep test in CI | P0 |
| SRS-NF-12 | Security | The server shall bind to 127.0.0.1 by default | Config check | P0 |
| SRS-NF-13 | Privacy | No profile images shall be fetched or stored. Pseudonyms shall be used in all UI | Code review | P0 |
| SRS-NF-14 | Ethics | UI and dossier text shall contain none of: fake, fraud, scam, fraudulent | Lint test on templates | P0 |
| SRS-NF-15 | Usability | A new user shall start a run in ≤ 2 interactions from the home screen | Walkthrough | P1 |
| SRS-NF-16 | Maintainability | Each `algo/` module shall have unit tests. Line coverage of `algo/` ≥ 80% | pytest-cov | P1 |
| SRS-NF-17 | Portability | `make dev` shall set up and start the system on a clean macOS or Ubuntu machine in < 10 min | README walkthrough | P0 |
| SRS-NF-18 | Compliance | The system shall use public data only, via SerpApi, consistent with the hackathon rules | Review | P0 |
| SRS-NF-19 | Observability | Every run shall write structured JSON logs with run\_id, phase and credits | Log check | P1 |

## 8. Verification and traceability

Verification methods: **T** = automated test, **D** = demonstration on video, **A** = analysis or evaluation script, **I** = inspection.

| SRS ID | PRD ref | Method | Verification |
| --- | --- | --- | --- |
| SRS-IN-1, IN-2 | FR1 | T | URL fixtures resolve to the expected data\_id |
| SRS-IN-3, IN-4 | FR3 | T | Invalid inputs return the error code with 0 credits used |
| SRS-IN-5 | FR2 | D | Search lists candidates |
| SRS-CR-1, CR-9 | FR3, CR1 | T | Mocked SerpApi; ledger sum ≤ B for budgets 20, 60 and 200 (I3) |
| SRS-CR-2 | FR4 | T | No duplicate review\_id in the sample |
| SRS-CR-4 | FR5 | T | Monotonicity in k\_u (I2) |
| SRS-CR-5 | FR6 | T | No contributor expanded twice (I4) |
| SRS-CR-7 | FR7 | T | Refinement occurs only after every 5 expansions and within B\_r |
| SRS-CR-8 | FR8 | T | Plateau fixture stops early |
| SRS-DT-1 | §5.1 | T | 40 date strings; ISO lies within the relative interval (I1) |
| SRS-DT-2 | FR10 | T | Planted biclique returned first (I5) |
| SRS-DT-3, DT-4 | FR11 | A | Null-shuffle calibration plot |
| SRS-DT-5 | FR12 | T | Synthetic co-timed ring gives a ratio ≥ 0.8 |
| SRS-DT-6 | FR13 | T | Paraphrase pairs flagged; unrelated pairs not |
| SRS-RP-1 | FR14 | T | No-ring invariant (I6); interval contains the point estimate |
| SRS-RP-2, RP-3 | FR15, FR16 | D | Control place shows the no-coordination message |
| SRS-RP-4 | FR17 | I | Dossier contains all sections |
| SRS-RP-5 | FR18 | T | Narrator output containing a foreign number is rejected |
| SRS-OP-1 to OP-3 | FR20, FR21 | T | Offline replay makes 0 network calls; a miss raises E\_CACHE\_MISS |
| SRS-OP-4 | FR22 | A | The committed plot is reproduced |
| SRS-IF-1 to IF-8 | §7 PRD | D | Demo video |
| SRS-IF-13, IF-14 | NF6 PRD | T | 429/500 retries; failed results are not cached |
| SRS-IF-21 | FR9 | T | A late subscriber receives the full event history |
| SRS-NF-1, NF-2 | NF1, NF2 | A | Run log percentiles |
| SRS-NF-6 | NF3 | T | Byte-identical JSON |
| SRS-NF-7 to NF-10 | §10 PRD | A | Evaluation report |
| SRS-NF-11, NF-14 | NF7, E1 | T | CI grep for the key and banned words |
| SRS-NF-17 | NF4 | D | Clean-machine walkthrough |

**Release criterion:** every P0 requirement verified, and every evaluation artifact committed under `eval/plots/` before Oct 10, 18:00 IST.

## Appendix A. Error codes

| Code | HTTP | Meaning | Credits consumed |
| --- | --- | --- | --- |
| `E_BAD_PLACE` | 400 | Input not parseable as a URL, place\_id or data\_id | 0 |
| `E_BUDGET` | 400 | Budget outside 20–200 | 0 |
| `E_TOO_FEW_REVIEWS` | 422 | Seed has d\_p < 20 | 1 |
| `E_AUTH` | 502 | SerpApi returned 401; the key is missing or invalid | 0–1 |
| `E_QUOTA` | 502 | SerpApi plan quota exhausted | as used |
| `E_UPSTREAM` | 502 | Upstream failure persisted after 3 retries on a required step | as used |
| `E_CACHE_MISS` | 409 | Offline mode, with a request absent from the cache | 0 |
| `E_NOT_FOUND` | 404 | Unknown run\_id | 0 |

## Appendix B. Configuration (`config.yaml` and environment)

| Key | Default | Range | Notes |
| --- | --- | --- | --- |
| `SERPAPI_API_KEY` | none | env only | Required for live runs |
| `NAKSHATRA_DB` | `./data/nakshatra.db` | path |  |
| `NAKSHATRA_OFFLINE` | `0` | 0/1 | Forces replay |
| `budget.default` | 60 | 20–200 |  |
| `budget.split` | \[0.20, 0.65, 0.15\] | sums to 1 | seed+sample / expand / refine |
| `prior.weights` | \[−1.0, 2.0, 0.8, 0.5, 0.6, 0.7\] | floats | Frozen after calibration |
| `expand.hot_boost` | 0.5 | ≥ 0 | β |
| `expand.refine_every` | 5 | ≥ 1 | expansions per refinement |
| `expand.plateau` | {eps: 0.02, window: 8} |  | Stopping rule |
| `ring.min_users` | 4 | ≥ 3 |  |
| `ring.min_places` | 3 | ≥ 2 |  |
| `ring.min_coverage` | 0.5 | 0–1 |  |
| `ring.max_rings` | 5 | ≥ 1 |  |
| `stats.alpha` | 0.01 | 0–0.1 |  |
| `stats.mass_scale` | 1.0 | > 0 | s, set by null calibration |
| `time.delta_days` | 14 | ≥ 1 |  |
| `rating.kappa` | 5 | ≥ 0 |  |
| `rating.tau` | 1.0 | > 0 | Set from controls |
| `rating.bootstrap` | {n: 1000, seed: 7} |  |  |
| `narrator.enabled` | false | bool | Optional LLM |

## Appendix C. Open issues

- **OI-1.** *Resolved Oct 5:* it does not. d_p for contributor-discovered places comes from hot-place refinement, with the best ring's places first (DECISIONS C3).
- **OI-2.** Measure how often `user.contributor_id` is missing for non-Google sources in Maps Reviews (for example Trip.com). Those reviews are excluded from expansion.
- **OI-3.** Decide whether MinHash similarity should feed the ring score (currently report-only).
