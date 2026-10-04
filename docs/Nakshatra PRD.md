# Nakshatra PRD

Oct 4, 2026 · @Ronel Abraham Mathew

Nakshatra finds coordinated review rings behind a Google Maps listing and shows a ring-adjusted rating with statistical evidence. Hackathon submission due Oct 10, 2026 23:59 IST.

## 1. Overview

**Problem.** Star ratings drive high-stakes local choices in India: fertility and hair-transplant clinics, packers and movers, coaching centres. Paid five-star reviews come from groups of accounts that review the same businesses together. In a LocalCircles survey of 56,000 respondents, 45% said Google ratings are inaccurate and 37% said they are positively biased ([Deccan Herald](https://www.deccanherald.com/business/45-survey-respondents-find-google-ratings-inaccurate-37-find-biases-localcircles-1171081.html)).

**Insight.** The fraud is visible on the reviewer axis, not on the place axis. One business's reviews look normal. The pattern appears only when you follow its reviewers to their *other* reviews and find that they all reviewed the same unrelated places in the same weeks. Google's official Places API has no endpoint for a reviewer's history. SerpApi's Google Maps Contributor Reviews API returns up to 200 of a reviewer's reviews in one call ([SerpApi docs](https://serpapi.com/google-maps-contributor-reviews-api)).

**Product.** The user pastes a Google Maps place. Nakshatra spends a visible SerpApi credit budget to crawl outward from the place's reviewers, mines the resulting graph for dense rings, and tests each ring against a null model. It returns:

- named rings, with their members (hashed), shared places and a timeline
- a p-value and an "expected vs observed" overlap for each ring
- the displayed rating next to a ring-adjusted rating with an interval
- an evidence dossier that can be exported for a report to Google or a complaint to the CCPA

**Positioning.** Existing browser extensions score reviewers one at a time, for example by flagging accounts with few reviews ([Maps Review Checker](https://chromewebstore.google.com/detail/flkjbaakoopafkcdhhijmjigbcnalmpn)). Nakshatra looks for coordination between accounts, which single-reviewer scoring cannot detect.

**Track:** Travel & Local Discovery, SerpApi India Hackathon 2026.

## 2. Goals, non-goals and success metrics

### Goals

1. **G1.** Detect coordinated review rings for any single Google Maps place within a fixed credit budget (default 60).
2. **G2.** Back every flagged ring with statistical evidence that a non-expert can read, such as "expected 0.04 shared places, observed 9".
3. **G3.** Show a ring-adjusted rating with an uncertainty interval next to the rating Google displays.
4. **G4.** Run locally and reproducibly: the same cached inputs always produce the same outputs.
5. **G5.** Make SerpApi's role legible: every step names the engine and the fields it uses.

### Non-goals

- Declaring any individual review or business "fake". Nakshatra reports anomalies, not verdicts.
- Covering review platforms other than Google Maps in the MVP.
- Training a supervised ML classifier.
- User accounts, hosting, monetisation, browser extension.
- Real-time monitoring of a place over weeks.

### Success metrics

| Metric | Target | Measured by |
| --- | --- | --- |
| Ring recall on injected rings (8+ members) | ≥ 0.8 | `eval/run_injection.py` |
| Ring precision on injected rings | ≥ 0.8 | same |
| Control places flagged at α = 0.01 | ≤ 1 of 10 | control set |
| Credits for 0.8 recall, budgeted vs BFS | ≤ 50% of BFS | credit-efficiency curve |
| p-value calibration on shuffled null graphs | QQ plot near diagonal | null-shuffle test |
| Wall time per 60-credit run | < 3 min | run log |
| Real rings found among scouted places | ≥ 1 demonstrable | manual review of dossier |

## 3. Users, personas and user stories

| Persona | Context | Decision | What they need from Nakshatra |
| --- | --- | --- | --- |
| **Priya, primary** | 34, Coimbatore. Comparing three IVF clinics, each rated 4.7 to 4.9 | Which clinic to visit first | Whether any clinic's rating is propped up, plus an adjusted rating she can compare |
| **Arun, secondary** | Consumer journalist in Bengaluru | Whether a tip about bought reviews is worth a story | Evidence: ring members, shared places, timeline, exportable dossier |
| **Meena, secondary** | Owner of a small packers-and-movers firm losing customers to a rival she suspects | Whether to file a CCPA complaint or a Google report | A neutral report she can attach |
| **Judge** | SerpApi developer advocate | Whether the project is original and uses SerpApi meaningfully | A visible ring, the engines behind it, a reproducible evaluation |

### User stories

| ID | Story | Priority |
| --- | --- | --- |
| US1 | As Priya, I paste a Maps link and get a result in under 3 minutes | P0 |
| US2 | As Priya, I see the displayed rating next to an adjusted rating with an interval | P0 |
| US3 | As Priya, I see in plain language why a ring was flagged | P0 |
| US4 | As Arun, I click a shared place and see which ring members reviewed it, and when | P0 |
| US5 | As Arun, I export a dossier with methods, evidence and raw IDs | P1 |
| US6 | As any user, I set the credit budget and watch it being spent | P0 |
| US7 | As any user, I see a clear "no coordination detected" result for clean places | P0 |
| US8 | As Meena, I search by category and area, then pick a place | P1 |
| US9 | As the judge, I rerun the evaluation with one command and get the same plot | P0 |
| US10 | As Priya, I compare two or three places side by side | P2 |

## 4. Functional requirements

P0 = required for submission, P1 = should ship, P2 = only if time remains.

| ID | Requirement | Priority | Story |
| --- | --- | --- | --- |
| **Input** |  |  |  |
| FR1 | Accept a Google Maps URL, `place_id` or `data_id` and resolve it to a seed place | P0 | US1 |
| FR2 | Accept a free-text query plus area, list the top 10 places, let the user pick one | P1 | US8 |
| FR3 | Credit budget input, 20 to 200, default 60; the run never exceeds it | P0 | US6 |
| **Crawl** |  |  |  |
| FR4 | Fetch seed reviews in two orders, `newestFirst` and `ratingHigh`, deduplicated by `review_id` | P0 | US1 |
| FR5 | Compute a reviewer prior s0(u) for every seed reviewer | P0 |  |
| FR6 | Expand reviewers in priority order using Contributor Reviews with `num=200` | P0 |  |
| FR7 | Promote places reviewed by ≥ 2 expanded suspects to "hot" and refine them with place reviews | P1 | US4 |
| FR8 | Stop early when ring density improves by < ε over the last 8 calls | P0 |  |
| FR9 | Stream progress events: credits spent, nodes, edges, current best ring | P0 | US6 |
| **Detect** |  |  |  |
| FR10 | Mine up to 5 disjoint rings with popularity-weighted greedy peeling | P0 |  |
| FR11 | Compute pairwise and ring-level Poisson p-values, Bonferroni-corrected | P0 | US3 |
| FR12 | Compute a temporal lockstep ratio from date intervals | P1 | US4 |
| FR13 | Flag near-duplicate review texts with MinHash, Jaccard ≥ 0.6 | P1 |  |
| **Report** |  |  |  |
| FR14 | Show displayed vs ring-adjusted rating with a 95% bootstrap interval | P0 | US2 |
| FR15 | Explain each ring in a template, for example: "9 accounts share 7 places that are unrelated to this business. Expected by chance: 0.04." | P0 | US3 |
| FR16 | Show "No coordination detected at α = 0.01" with the number of places checked | P0 | US7 |
| FR17 | Export the dossier as Markdown and PDF: method, rings, shared places, timeline, run log, engine calls | P1 | US5 |
| FR18 | Optional LLM narrator that turns the findings JSON into a short paragraph and cannot add facts | P1 |  |
| FR19 | Compare two or three places side by side | P2 | US10 |
| **Ops** |  |  |  |
| FR20 | Cache every SerpApi response in SQLite, keyed by a hash of its parameters; replay mode makes zero calls | P0 | US9 |
| FR21 | Keep a credit ledger per run: engine, parameters hash, cached or live | P0 |  |
| FR22 | One-command evaluation that reproduces plots from a fixed seed | P0 | US9 |

## 5. Detection engine requirements

All detection logic is deterministic Python. The LLM never decides membership, scores or ratings.

### 5.1 Graph model

The graph is bipartite: users U on one side, places P on the other. Each edge carries the rating r and a time interval.

```latex
G = (U \cup P, E), \quad e = (u, p, r, [t^-, t^+])
```

| Date string | Interval |
| --- | --- |
| ISO date from `google_maps_reviews` | the point \[t, t\] |
| "a day ago" / "N days ago" | \[now − N − 1 d, now − N d\] |
| "a week ago" / "N weeks ago" | \[now − (N + 0.5) w, now − (N − 0.5) w\] |
| "a month ago" / "N months ago" | \[now − (N + 0.5) mo, now − (N − 0.5) mo\] |
| "a year ago" / "N years ago" | \[now − (N + 0.5) y, now − N y\] |

These mappings must hold for both English and localized `hl` strings. In the MVP, every call is forced to `hl=en`.

### 5.2 Reviewer prior

Each seed reviewer gets a prior suspicion score between 0 and 1:

```latex
s_0(u) = \sigma\big(w_0 + w_1 / \log(2 + k_u) + w_2[r = 5] + w_3[\text{photos}_u = 0] + w_4 z_{burst} - w_5[\text{local guide}]\big)
```

- k\_u is the reviewer's total review count, taken from `user.reviews`.
- z\_burst is the z-score of the seed's daily review count on that reviewer's day.
- Initial weights are w = (−1, 2, 0.8, 0.5, 0.6, 0.7). They are tuned on injected data and frozen before the demo.

### 5.3 Budgeted expansion

- The crawl is a priority queue keyed by π(v) = s0(v) · (1 + β·|H\_v|), with β = 0.5.
- H\_v is the set of hot places that reviewer v has reviewed.
- At most 1 hot-place refinement is allowed per 5 contributor expansions.
- Reserve 15% of the budget for refinement.
- Stopping rule: the run halts when the budget is spent, or when the best-ring density has improved by less than 2% over the last 8 calls.

### 5.4 Ring mining

Rings are found by greedy peeling, a FRAUDAR-style densest-subgraph search ([Hooi et al. KDD 2016](https://unpaywall.org/10.1145%2F2939672.2939747)), with one change: column weights use each place's **global** review count d\_p from Maps.

```latex
c_p = \frac{1}{\log(d_p + 5)}, \qquad g(S) = \frac{\sum_{(u,p) \in E(S),\, p \neq p_0} c_p}{|S|}
```

- The seed place p0 is excluded from the density.
- Ring constraints: at least 4 users, at least 3 shared non-seed places, and every member reviews at least 50% of the ring's places.
- After a ring is found, remove its users and repeat, up to 5 rings.

### 5.5 Significance

Each ring is tested against a Poisson null model of chance overlap:

```latex
\pi_p = d_p / D, \quad \lambda_{uv} = k_u k_v \sum_{p \in Q} \pi_p^2, \quad \text{pval}_{uv} = P(X \ge m_{uv}),\ X \sim \text{Poisson}(\lambda_{uv})
```

- D is the city review mass. It is estimated as the sum of d\_p over all observed places plus the category-search places, multiplied by a scale constant calibrated on null shuffles.
- The ring p-value is the median pairwise p-value, multiplied by the number of rings tested.
- A ring is reported if its p-value is below α = 0.01.

### 5.6 Temporal lockstep

- Two edges on the same place co-occur if their intervals come within δ = 14 days of each other.
- The lockstep ratio is the share of shared places where at least 60% of members co-occur.
- The timeline is shown only when the median interval width is under 30 days.

### 5.7 Adjusted rating

Reviews from ring members are down-weighted, and the result is shrunk toward the category mean:

```latex
q_u = [u \in R] \cdot \min(1, g(R)/\tau), \qquad \hat r = \frac{\sum_i (1 - q_{u_i}) r_i + \kappa \mu_{cat}}{\sum_i (1 - q_{u_i}) + \kappa}
```

- τ is the 95th percentile of g on control places.
- κ = 5.
- μ\_cat is the mean rating of up to 20 same-category places nearby.
- The interval comes from 1,000 bootstrap resamples of the sampled reviews.
- The result is labelled "estimate from N sampled reviews".

### 5.8 Parameters

| Parameter | Default | Tuned on |
| --- | --- | --- |
| Budget B | 60 credits | n/a |
| β (hot boost) | 0.5 | injection |
| ε, window | 2%, 8 calls | injection |
| α | 0.01 | null shuffles |
| δ | 14 days | fixed |
| Min ring size | 4 users × 3 places | fixed |
| κ | 5 | fixed |

## 6. SerpApi integration and credit budget

Removing the Contributor Reviews engine breaks the product, which is the core of the claim that SerpApi usage is meaningful. All calls go through one client that applies the cache, the ledger and `json_restrictor`.

| Step | Engine | Key parameters | Fields consumed | Credits (default run) |
| --- | --- | --- | --- | --- |
| Seed resolve | `google_maps` | `q` or `data_id`/`place_id`, `type=place` | `data_id`, title, rating, reviews, type, gps | 1 |
| Category baseline | `google_maps` | `q=<type>`, `ll=@lat,lng,14z` | rating, reviews, `data_id` for \~20 places | 1 |
| Seed reviews | `google_maps_reviews` | `data_id`, `sort_by` = `newestFirst` and `ratingHigh`, `num=20` after page 1, `hl=en` | `review_id`, rating, `iso_date`, `iso_date_of_last_edit`, `user.contributor_id`, `user.reviews`, `user.photos`, `user.local_guide`, snippet, response | 8–12 |
| Expansion | `google_maps_contributor_reviews` | `contributor_id`, `num=200`, `hl=en` | `contributor.level/points/contributions`, `reviews[].place_info.{data_id, title, type, gps_coordinates}`, rating, `date`, snippet | 30–40 |
| Hot refinement | `google_maps_reviews` | `data_id` of hot place, `sort_by=newestFirst` | `iso_date` and `contributor_id` of ring members | 5–10 |
| Popularity backfill | `google_maps` | `data_id` | reviews count when missing | 0–5 |

Field behaviour has been checked against the SerpApi docs:

- The first page of Maps Reviews returns 8 results. Later pages accept `num` up to 20 via `next_page_token` ([docs](https://serpapi.com/google-maps-reviews-api)).
- Contributor Reviews returns at most 200 results per contributor, and its dates are relative strings only ([docs](https://serpapi.com/google-maps-contributor-reviews-api)).
- Identical repeat calls within 1 hour hit SerpApi's cache and cost no credits.

### Credit requirements

- **CR1.** The run planner allocates the budget up front as 20% seed, 65% expansion and 15% refinement, then reallocates leftovers.
- **CR2.** The ledger records every call: engine, parameter hash, cached, live, latency.
- **CR3.** Replay mode (`NAKSHATRA_OFFLINE=1`) serves only from SQLite and raises an error on a cache miss.
- **CR4.** The project needs about 800 to 1,200 credits in total for development, evaluation and demo, so the free tier of 250 per month is not enough. Secure credits before Oct 5.
- **CR5.** The API key comes only from the environment and never appears in the repo or in logs.

## 7. UX: screens and flows

There are three screens, and the investigation screen carries the demo.

### Primary flow

1. **Home.** The user enters a Maps URL in a single input, or a query plus an area (P1). A budget slider defaults to 60. Two example places are offered: one control and one known case.
2. **Investigation (live).**
   - **Left:** a Cytoscape graph that grows as events stream in. The seed place is the central node, reviewers are circles and other places are squares. Rings are coloured when they are found.
   - **Top bar:** credits used out of the budget, phase (seed, expand, refine, mine) and elapsed time.
   - **Right panel:** the current best ring, which updates live.
3. **Result.**
   - A rating card shows the displayed rating, the adjusted rating and its interval.
   - Below it, a ring list. Each ring shows its size, shared places, p-value and lockstep ratio.
   - Clicking a ring highlights it on the graph. Clicking a shared place opens a drawer listing which members reviewed it, with dates.
   - Buttons: Export dossier, Rerun with a bigger budget, Replay offline.

### Empty and edge states

| State | Message |
| --- | --- |
| No ring at α = 0.01 | "No coordination detected among N reviewers across M places." The adjusted rating equals the displayed rating within the interval |
| Place has fewer than 20 reviews | "Too few reviews to test." The run is not started |
| Budget exhausted before mining is stable | The partial result is shown with a "low coverage" badge |
| Contributor profile is private or empty | That node is greyed out, with no penalty |
| SerpApi error or quota exceeded | The run pauses and offers offline replay of whatever is cached |

### Copy rules

- Never use the words "fake", "fraud" or "scam" in the UI. Use "coordinated", "anomalous" and "unlikely by chance".
- Every number shown has a tooltip that explains how it was computed.
- Reviewer names are hidden. Members appear as R1, R2 and so on, and the raw ID is available only in the export.

## 8. Data model and backend API

The stack is FastAPI, SQLite, networkx, numpy and scipy, with a Vite + React + Cytoscape.js frontend.

### Tables (SQLite)

| Table | Key | Columns |
| --- | --- | --- |
| `serp_cache` | `params_hash` | engine, params\_json, response\_json, fetched\_at, search\_id |
| `ledger` | `id` | run\_id, engine, params\_hash, cached (bool), latency\_ms, ts |
| `places` | `data_id` | title, type, lat, lng, rating, review\_count, source\_engine |
| `users` | `contributor_id` | level, points, review\_total, photos, local\_guide, truncated (bool) |
| `edges` | `(contributor_id, data_id)` | rating, t\_lo, t\_hi, exact (bool), snippet\_hash, review\_id |
| `runs` | `run_id` | seed\_data\_id, budget, credits\_used, status, params\_json, started\_at |
| `rings` | `(run_id, ring_idx)` | members\_json, places\_json, density, pval, lockstep\_ratio |
| `results` | `run_id` | displayed\_rating, adjusted\_rating, ci\_lo, ci\_hi, n\_sampled |

### Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/runs` | Body `{place, budget, offline}`; returns `{run_id}` |
| GET | `/api/runs/{id}/events` | SSE stream: `credit`, `node`, `edge`, `ring_update`, `phase`, `done`, `error` |
| GET | `/api/runs/{id}` | Final result JSON |
| GET | `/api/runs/{id}/dossier?fmt=md\|pdf` | Evidence export |
| GET | `/api/places/search?q=&near=` | Candidate list (P1) |
| GET | `/api/runs/{id}/ledger` | Credit ledger |

### Result JSON (abridged)

```json
{
  "run_id": "r_01",
  "seed": {"data_id": "0x...", "title": "...", "rating": 4.8, "reviews": 412},
  "credits": {"budget": 60, "used": 57, "cached": 12},
  "rings": [{
    "id": 1, "members": ["R1", "R2"], "places": [{"data_id": "0x...", "title": "...", "d_p": 38}],
    "density": 2.41, "expected_overlap": 0.04, "observed_overlap": 9,
    "pval": 3.1e-7, "lockstep_ratio": 0.78
  }],
  "rating": {"displayed": 4.8, "adjusted": 3.9, "ci": [3.6, 4.2], "n_sampled": 176}
}
```

The values are illustrative.

### Repo layout

```text
nakshatra/
  api/           FastAPI app, SSE
  serp/          client, cache, ledger, engines
  graph/         normaliser, date intervals, graph store
  algo/          prior.py, expander.py, peel.py, significance.py, lockstep.py, rating.py
  report/        dossier templates, narrator
  web/           React + Cytoscape
  eval/          run_injection.py, controls.py, null_shuffle.py, plots/
  tests/         unit tests per algo module
```

## 9. Non-functional, ethics and privacy requirements

| ID | Requirement | Target |
| --- | --- | --- |
| NF1 | Latency of a 60-credit live run | < 3 min wall time |
| NF2 | Latency of an offline replay | < 10 s |
| NF3 | Determinism | Same cache + same seed gives byte-identical result JSON |
| NF4 | Setup | `make dev` brings up the API and web app; README works on a clean machine in < 10 min |
| NF5 | Test coverage | Every module in `algo/` has unit tests, including a planted-ring fixture |
| NF6 | Resilience | Retry with backoff on 429/5xx; a run survives a single engine failure with partial output |
| NF7 | Security | No secrets in the repo; `.env.example` only; the key is redacted from logs and cached JSON |

### Ethics and privacy

- **E1.** Output is framed as statistical anomaly with evidence. There is no verdict language anywhere in the UI or the dossier.
- **E2.** Reviewer identities are pseudonymised in the UI and the demo. Raw contributor IDs appear only in the exported dossier, which is intended for platform or regulator reporting.
- **E3.** No profile photos are stored or displayed. Review snippets are stored only as MinHash signatures, plus the text excerpts needed to show a ring's evidence.
- **E4.** The demo video blurs business names unless the business is a control or the case is already public.
- **E5.** The README carries a limitations section covering sampling, relative-date uncertainty, the null-model assumptions, and the fact that real coordinated communities (for example a local club) can look like rings.
- **E6.** The tool uses only public data retrieved through SerpApi and does not scrape Google directly.

## 10. Evaluation and acceptance criteria

The submission is accepted when every P0 requirement passes the checks below and the evaluation plots are committed.

### Evaluation suite

| Test | Setup | Pass condition |
| --- | --- | --- |
| Injection recall/precision | 10 real crawled graphs × 3 planted rings (size 5–15, 5–12 shared low-popularity places, 30% camouflage edges to popular places), fixed seed | Recall ≥ 0.8 and precision ≥ 0.8 for rings ≥ 8 |
| Credit efficiency | Same graphs, budgets 20–120; strategies: priority crawl, BFS, random | Priority crawl reaches 0.8 recall at ≤ 50% of BFS credits |
| Controls | 10 popular landmark or chain places | ≤ 1 flagged at α = 0.01 |
| Null calibration | Degree-preserving edge shuffles, 200 runs | Share of p < α within \[0.5α, 2α\] |
| Interval parser | 40 date strings | 100% correct intervals |
| Determinism | Two offline replays | Identical JSON |
| Real-world sanity | 8 scouted places in high-incentive categories | At least 1 ring a human reviewer agrees is unusual; findings written up as a case study |

### Acceptance checklist

- [ ] US1, US2, US3, US4, US6, US7 and US9 demonstrably work on video
- [ ] The README contains the insight, prior art table, integration map, method, evaluation plots and limitations
- [ ] `python eval/run_injection.py --seed 7` reproduces the committed plot
- [ ] The demo is under 3 minutes and shows the first ring before 0:45
- [ ] The repo is public, no secrets are present, and the links open in an incognito window

## 11. Milestones, risks and open questions

### Milestones

| Date (IST) | Milestone | Exit criterion |
| --- | --- | --- |
| Oct 4 night | M0 Credits + scouting | Credits secured; 3 playground calls confirm the field shapes; 8 candidate places listed |
| Oct 5 | M1 Data layer | FR1, FR3, FR4, FR6, FR20, FR21 pass; 2 real places ingested |
| Oct 6 | M2 Detection core | FR5, FR8, FR10, FR11 with unit tests; runs on 5 places |
| Oct 7 | M3 Evaluation + gate | Injection, controls and null calibration run. **Gate:** if no real ring is found, the demo uses a control, an injected ring and the best real anomaly, labelled honestly |
| Oct 8 | M4 UI + report | FR9, FR14 to FR17 working end to end |
| Oct 9, 12:00 | M5 Feature freeze | README, plots and screenshots done; first demo recorded |
| Oct 10, 18:00 | M6 Submitted | Final video and form submitted, leaving 6 hours of buffer |

### Risks

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| No demonstrable real ring | Medium | High | Scout high-incentive categories early; M3 gate; honest fallback |
| Credits run out | High on the free plan | High | Paid Developer plan or hackathon credits; aggressive caching |
| Relative dates too coarse | High | Medium | Interval maths; exact-date refinement on hot places only |
| False positives from genuine power reviewers | Medium | High | Global-popularity weights, local-guide prior, controls, Poisson null |
| Judges see it as "an extension already does this" | Medium | Medium | Prior-art table; the demo shows multi-hop rings with p-values |
| Harm to a named business | Low–Medium | High | Copy rules, pseudonymisation, blurred demo |

### Open questions

- Are the hackathon credits (1,000 per valid submission) granted only after the deadline? If so, the build needs a paid plan now.
- How should the city review mass D be calibrated? The current plan uses null shuffles; a better proxy from category searches is an alternative.
- Should a ring require temporal lockstep, or only report it? The current plan reports it, to keep recall up.
- Should the MVP add an App Store and Play adapter (APPLOCK) to show the algorithm generalises? Currently P2.
- Is a team member available to own the UI so the algorithm owner can focus on M2 and M3?
