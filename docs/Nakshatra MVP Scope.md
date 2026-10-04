# Nakshatra MVP Scope

Oct 4, 2026 · @Ronel Abraham Mathew

The smallest Nakshatra that proves the idea to SerpApi judges, locked for the submission on Oct 10, 2026 23:59 IST. Anything not listed as Must is negotiable; anything under Won't is out until after submission.

## 1. MVP definition

**The MVP is a local web app that takes one Google Maps place and, within 60 SerpApi credits, finds coordinated reviewer rings, proves they are unlikely by chance, and shows a ring-adjusted rating.**

### What the MVP must prove

The four hypotheses map to the judging criteria. Each must be demonstrated, not claimed.

| # | Hypothesis | Judging criterion | Proof in the submission |
| --- | --- | --- | --- |
| H1 | The reviewer axis, reachable only through SerpApi's Contributor Reviews engine, reveals coordination that a place's own reviews hide | Idea strength, Meaningful SerpApi usage | Demo: a ring whose shared places are not the seed |
| H2 | A budgeted crawl finds rings with far fewer credits than naive expansion | Technical complexity | Credit-efficiency plot: priority vs BFS vs random |
| H3 | The detector separates planted rings from chance overlap, and stays quiet on controls | Technical complexity, Usefulness | Injection recall/precision table; control false-positive count |
| H4 | A non-expert can read the result correctly | Usefulness | Rating card + verdict line; the usability check passes |

### Not trying to prove

- Accuracy at scale
- That any specific real business bought reviews
- Multi-platform coverage
- Production readiness

These are deliberate non-claims, and the README says so.

## 2. In scope: Must

These 12 capabilities define the MVP. If any one of them is missing, the submission does not prove its hypotheses.

| # | Capability | Acceptance criterion | Proves |
| --- | --- | --- | --- |
| M1 | Place input by Maps URL or `data_id` | A URL containing `0x…:0x…` resolves to a seed in 1 credit; bad input gives an inline error with 0 credits | H4 |
| M2 | Cache-first SerpApi client with budget tokens and a ledger | The ledger sum never exceeds the budget; a repeat run of the same place costs 0 credits | H2 |
| M3 | Seed sampling (`newestFirst` + `ratingHigh`) | Reviewers ingested with `contributor_id`, k\_u and exact dates | H1 |
| M4 | Reviewer prior + priority expansion via Contributor Reviews | Expansion follows the s0 order; no contributor is expanded twice; the run stops on the plateau or the budget | H1, H2 |
| M5 | Popularity-weighted ring mining | The planted 8×6 ring is recovered first (unit test) | H3 |
| M6 | Significance: Poisson display statistic + permutation gate | Shuffled null graphs: the share of p < α is about α; rings are reported only if both pass | H3 |
| M7 | Adjusted rating from the `newestFirst` sample with an interval | With no rings, the adjusted rating sits within κ/(n+κ) of the sample mean | H4 |
| M8 | Live progress stream (SSE) with replay | The first node renders within 5 s; reconnect resumes without loss | H1 (demo) |
| M9 | Result screen: rating card, verdict line, ring cards, graph, place drawer | Flow A steps A1–A9 work end to end | H4 |
| M10 | Offline replay from a shipped `demo.db` | A judge with no key sees the demo run byte for byte, with 0 network calls | All |
| M11 | Evaluation harness: injection, controls, credit efficiency | `make eval` reproduces the committed plots | H2, H3 |
| M12 | README: insight, prior art, integration map, method, results, limitations | A reviewer understands the project without the video | All |

## 3. Should, Could, Won't

| Tier | Item | Why it is in this tier | Est. |
| --- | --- | --- | --- |
| **Should** | S1 Hot-place refinement (exact dates + new co-reviewers) | Improves recall and timing evidence; the MVP still works without it | 2 h |
|  | S2 Temporal lockstep ratio (sweep-line) | Strong demo evidence; corroborating only | 1 h |
|  | S3 Dossier export (Markdown; PDF if WeasyPrint installs cleanly) | Usefulness story for investigators | 1.5 h |
|  | S4 Ledger drawer in the UI | Makes SerpApi usage visible to judges | 1 h |
|  | S5 Cancel with partial result | Graceful demo recovery | 1 h |
|  | S6 Ring guards: rating variance, geographic spread, brand overlap | Reduces misreading of genuine communities | 1.5 h |
| **Could** | C1 Place search by query + area | Convenience; a URL works fine | 1 h |
|  | C2 MinHash near-duplicate texts | Extra evidence; not gating | 1 h |
|  | C3 LLM narrator with number guard | Polish only | 1 h |
|  | C4 Cross-run "repeat clients" view | Compelling, but needs several real runs | 1.5 h |
|  | C5 PR adding a contributor tool to serpapi-search-tools | Open-source goodwill | 2 h |
| **Won't (v1)** | Play Store / App Store / Tripadvisor adapters | Scope; designed for later |  |
|  | Accounts, hosting, multi-user, mobile layout | Not needed for a local demo |  |
|  | Supervised ML classifier | No labels; it would undercut the statistics story |  |
|  | Continuous monitoring and alerts | Out of the decision the MVP supports |  |
|  | Hindi/Tamil text normalisation | Text is not a primary signal |  |
|  | Docker image | `make demo` is enough |  |

### Cut order if the schedule slips

Cut from the top of this list first:

1. C3
2. C5
3. C4
4. C2
5. C1
6. S3 PDF (keep Markdown)
7. S6
8. S5
9. S1

**Never cut:** M5, M6 and M11. They are the technical claim. A rough UI with working statistics beats a polished UI without them.

## 4. Boundaries and fixed decisions

### Boundaries

| Dimension | In | Out |
| --- | --- | --- |
| Platform | Google Maps reviews via 3 SerpApi engines | Every other review source |
| Geography | Any, tuned and demoed on Coimbatore and Bengaluru | Country-specific legal outputs beyond the dossier note |
| Users | One local user; consumer, investigator and judge flows | Teams, sharing, auth |
| Scale | One run at a time, ≤ 200 credits, ≤ \~10k edges | Batch scanning of a category or city |
| Output | Statistical anomaly with evidence | Verdicts about intent ("fake", "fraud") |
| Language | English UI; `hl=en` on every call | Localised UI |

### Decisions already locked

These are not up for debate during the build week.

| Decision | Source |
| --- | --- |
| Monolith: FastAPI + SQLite (WAL) + React/Cytoscape, localhost only | Architecture ADR-1 to ADR-3, ADR-10 |
| Raw SerpApi JSON cached forever; graph rebuildable from the cache | Data Model §1 |
| No LLM in any decision; the optional narrator only | Algorithm §10.3 |
| Significance = city-wide Poisson display + degree-preserving permutation gate | Algorithm §6 (supersedes SRS §5.5) |
| Adjusted rating from `newestFirst` only | Algorithm §7.2 |
| `/api/v1` paths, error envelope, `S`/`R` pseudonyms | API Contract §9.1 |
| Data-model schema v2 is authoritative | Data Model §4 |

**Update before coding:** the LLD code samples (`significance.py`, `lockstep.py`, `api/routes.py`, `report/`, `useRunStream.ts`) must be updated to the revisions above. Budget 1 hour on Oct 5 for this.

## 5. Prerequisites and dependencies

| # | Prerequisite | Needed by | Owner | Status |
| --- | --- | --- | --- | --- |
| P1 | **SerpApi credits ≥ 1,200.** The free tier is 250/month; options are a paid plan, or asking the organisers (adarsh@serpapi.com) | Oct 5 morning | You | Open |
| P2 | Playground checks: the `google_maps` place-lookup parameter for a `data_id`; the `json_restrictor` syntax; whether `place_info` in contributor reviews carries a review count | Oct 5 | You | Open |
| P3 | 8 scouting places in high-incentive categories (fertility, hair transplant, packers and movers, coaching) + 10 control places | Oct 6 | You | Open |
| P4 | Python 3.11, Node 20, WeasyPrint system libraries (only for PDF) | Oct 5 | You | Open |
| P5 | Public GitHub repo created; `.env` git-ignored; secret scanning on | Oct 5 | You | Open |

### External dependencies and risks

| Dependency | Risk | Mitigation |
| --- | --- | --- |
| SerpApi availability and field shapes | Field drift, or an outage on demo day | Everything cached; the demo runs offline from `demo.db` |
| A real ring existing among the scouted places | None found by Oct 7 | Gate in §6: demo with an injected ring + a control + the best real anomaly, labelled honestly |
| Credit budget | Runs out mid-calibration | Calibrate on cached graphs; one live crawl per place, never repeated |

## 6. Schedule, gates and cut triggers

Six build days, with three gates. A gate that fails triggers the stated cut, not a slipped deadline.

| Day (IST) | Build | Musts done by end of day | Gate / cut trigger |
| --- | --- | --- | --- |
| Sun Oct 4, night | Prerequisites P1, P2, P5 |  | Credits not secured by Oct 5 noon → run the whole build on ≤ 250 credits: 3 real places + injected rings only |
| Mon Oct 5 | Data layer, client, ingest | M1, M2, M3 |  |
| Tue Oct 6 | Prior, expansion, mining, significance | M4, M5, M6 | **G1 (end of day):** a CLI run on one real place produces rings or a clean result. If not → cut S1 and S6 |
| Wed Oct 7 | Evaluation, calibration, scouting | M7, M11 | **G2 (18:00):** a real ring found? Yes → it is the demo case. No → demo with injected + control + best anomaly. Injection recall below 0.8 → raise the minimum ring size, re-measure, and report honestly |
| Thu Oct 8 | API, SSE, UI, export | M8, M9, M10 | **G3 (22:00):** Flow A end to end in the browser. If not → cut every Could, and S3 PDF |
| Fri Oct 9 | README, plots, demo DB, rehearsal | M12 | **Feature freeze 12:00.** Bug fixes only after that |
| Sat Oct 10 | Record, submit |  | **Submit by 18:00 IST**, leaving 6 hours of buffer before the 23:59 deadline |

**Daily rule.** No Should work starts on a day while a Must from that day is incomplete.

## 7. Definition of done and submission checklist

### The MVP is done when

- [ ] M1–M12 meet their acceptance criteria (§2)
- [ ] Unit tests pass for the budget, dates, peel, significance and rating modules; `make test` is green
- [ ] The integrity check returns zero rows (Data Model §5.3)
- [ ] `make replay` on a clean clone with no key reproduces the demo run
- [ ] Evaluation plots are committed: recall/precision grid, credit efficiency, control false positives, null calibration
- [ ] The copy lint finds no banned words in the UI, templates or dossier
- [ ] The usability check passes (User Flow §8)

### Submission checklist (hackathon rules)

- [ ] Public GitHub repo with setup instructions; opens in an incognito window
- [ ] Demo video under 3 minutes, showing the project running locally; the first ring appears before 0:45; the link opens in an incognito window
- [ ] Project description names the track (Travel & Local Discovery), the target user and the SerpApi usage (the 3 engines and why each is essential)
- [ ] "Existing project?" answered No; AI tools used are disclosed
- [ ] No API key or personal data in the repo; `demo.db` exported via the minimising script
- [ ] Rules and Terms accepted; **"Submit project" pressed**, not left as a draft

## 8. After the MVP

This is ordered by evidence value, not by effort. Nothing here is started before submission.

| Next | What | Why next |
| --- | --- | --- |
| 1 | Cross-run crew memory: persist detected rings and boost known members in future runs | Turns one-off detections into a growing map of crews; catches small rotating crews |
| 2 | Hand-labelled validation set (30 places, two annotators) | Moves beyond synthetic evaluation, which is the strongest judge objection |
| 3 | Time as a third mode: dense blocks in a user × place × week tensor | Better rings when deployment is bursty |
| 4 | APPLOCK: the same pipeline over Play Store and App Store reviews | Proves the method generalises; new users (app developers) |
| 5 | Category scan mode: rank all clinics in an area by ring exposure | The consumer product: "which of these 10 can I trust?" |
| 6 | Upstream contribution: a contributor-reviews tool for serpapi-search-tools | Lets any agent use the reviewer axis |
