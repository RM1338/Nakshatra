# Nakshatra User Flow

Oct 4, 2026 · @Ronel Abraham Mathew

How people move through Nakshatra: three screens, one live moment, and every state a user can land in. Copy shown in quotes is final UI text unless marked draft.

## 1. UX goals and principles

Nakshatra has one job in the UI: turn a star rating into something a non-expert can question, without accusing anyone.

### Goals

| Goal | Measure |
| --- | --- |
| Start an investigation in 2 interactions | Paste a link, press Enter |
| Show something real within 5 s | The first graph nodes render |
| The answer is readable without understanding the graph | Rating card plus a one-sentence verdict line |
| Evidence is one click away | Ring → shared place → who reviewed it and when |
| No accusation language anywhere | Copy lint passes (SRS-NF-14) |

### Principles

1. **Answer first, evidence second.** The rating card and the one-line summary come first. The graph is proof, not the product.
2. **Show the work live.** The credit counter and the growing graph make the search visible. They are also the demo.
3. **Numbers with context.** Every statistic sits next to its plain-language twin ("expected by chance: 0.3, observed: 7").
4. **Uncertainty is visible.** Intervals on ratings; "timing not resolvable" instead of a fake precise number; a "low coverage" badge when the budget ran out.
5. **Clean results are first-class.** "No coordination detected" gets the same care as a found ring. Most places should land here.
6. **People stay anonymous.** Reviewers appear as R1, R2 and so on. Businesses are named, because the user chose to investigate them.

## 2. Primary flow

A run either ends on the result screen, or, for a fatal seed-level error, returns home with a banner. Cancelling, or running out of budget, still produces a result marked low coverage.

&#91;embedded content: primary flow · 3 screens, 2 overlays, 2 decisions\]

The ledger drawer (O2) opens from the result screen or the credits bar and is left out of the picture for clarity.

## 3. Screen inventory

There are three screens and two overlays. The URL reflects state, so a run can be bookmarked or reopened: `/`, `/runs/:id`.

| Screen | Purpose | Key elements | Enters from | Exits to |
| --- | --- | --- | --- | --- |
| **S1 Home** | Start a run | Place input (URL or ID); "or search a place" link; budget slider (20–200, default 60); offline toggle (shown only when a key is missing or the cache has the place); two example chips ("Try a known case", "Try a control"); recent runs list | App open, "New investigation" | S2 |
| **S2 Investigation (live)** | Watch the search and the ring form | Top bar: seed name, phase pill, credits used/budget bar, elapsed time, Cancel. Left 65%: live graph. Right 35%: "Best ring so far" card (size, shared places, density sparkline). Bottom: event ticker (last 3 events, quiet text) | S1 | S3 on `done`/`cancelled`; S1 on `error` (with banner) |
| **S3 Result** | Answer and evidence | **Rating card** (displayed vs adjusted, interval, one-line verdict). **Rings list** (cards: members, shared places, expected vs observed, p-value, lockstep, explanation). Graph (static, rings coloured). Toolbar: Export ▾ (Markdown, PDF), Replay offline, Rerun with bigger budget, Ledger | S2, recent runs, deep link | O1, O2, S1 |
| **O1 Place drawer** (overlay) | Evidence for one shared place | Place name, type, total reviews (d\_p), "Why this matters: a place with 31 reviews shared by 9 accounts". Table: R-id, stars, date or date range, exact/approx badge | Click a place in a ring card or graph | S3 |
| **O2 Ledger drawer** (overlay) | Credit audit | Totals by pool; table of calls (engine, cached/billed, latency, search\_id) | Toolbar "Ledger", or the credits bar | S3 |
| **S1b Place search** (P1, inline on S1) | Find a place without a URL | Query + area input → up to 10 candidates with rating and review count; ineligible ones (< 20 reviews) are greyed out with a reason | S1 link | S1 with the place filled in |

## 4. Flow A: a consumer checks a clinic

**Persona:** Priya, comparing IVF clinics in Coimbatore. **Goal:** decide whether a 4.8 rating can be trusted. **Time on task:** about 3 minutes, mostly watching.

| # | User does | System shows | Copy (final unless marked) |
| --- | --- | --- | --- |
| A1 | Opens Nakshatra | S1 with an empty input, focused | Heading: "Are these reviewers connected?" Placeholder: "Paste a Google Maps link" |
| A2 | Pastes the clinic's Maps link | Input validates inline. A green tick and the parsed place ID appear | Helper: "Found a place ID. Ready to investigate." |
| A3 | Leaves budget at 60, presses Enter | Navigates to S2 and the phase pill reads "Looking up the place". The seed node appears centred, labelled with the clinic name |  |
| A4 | Watches | Phase "Reading recent reviews". Reviewer dots attach to the seed; credits tick 1 → 12 | Ticker: "Read 8 reviews (newest)" |
| A5 | Watches | Phase "Following reviewers". Each followed reviewer sprouts places; shared places pull reviewers together | Ticker: "R4 has reviewed 37 other places" |
| A6 | Notices the right card change | A dense cluster gains a colour; the "Best ring so far" card shows 6 → 9 → 11 accounts | Card: "11 accounts share 9 places" |
| A7 | Waits | Phase "Checking whether this could be chance" (mining + permutation), about 2 s |  |
| A8 | Lands on S3 | The rating card animates from 4.8 to the adjusted value | Verdict line: "11 accounts reviewed the same 9 unrelated places, mostly within the same fortnight. Setting their reviews aside, the recent rating is 4.0 (3.7–4.3)." |
| A9 | Clicks "Example Tiles" in the ring card | O1 drawer opens | "31 people have ever reviewed this tile shop. 9 of them also reviewed your clinic, all within 10 days." (draft) |
| A10 | Goes back, opens the next clinic | S1 via "New investigation" |  |

**What Priya never has to read:** density, peeling, or p-values. Those sit one level down, in the ring card's "Details" toggle, for investigators and judges.

## 5. Flows B and C

### Flow B: an investigator exports evidence

**Persona:** Arun, a consumer journalist following a tip about a packers-and-movers firm.

| # | User does | System shows |
| --- | --- | --- |
| B1 | Uses "or search a place": "packers movers Gandhipuram" | S1b lists 10 candidates; two with fewer than 20 reviews are greyed out ("Too few reviews to test") |
| B2 | Picks the tipped firm and sets the budget to 120 | The credits bar shows 120 |
| B3 | Runs, then reaches S3 with 2 reported rings | Two ring cards, sorted by p-value |
| B4 | Opens "Details" on ring 1 | Density, permutation p, pairwise expected vs observed, lockstep ratio, rating variance, geographic spread |
| B5 | Clicks "Repeat clients" (P2) | Places shared with rings from earlier runs |
| B6 | Export ▾ → PDF | Dossier downloads: summary, method, rings with raw contributor IDs, shared-place tables, timeline, ledger with `search_id`s, limitations |
| B7 | Opens the Ledger drawer | 118 billed, 9 cached. He can cite each call |

**Guardrail.** The export dialog says, before download: "This file contains Google Maps contributor IDs. Use it for reporting to Google or a consumer authority, not for publication." The user must click "I understand" once per session.

### Flow C: a judge replays offline

**Persona:** a SerpApi judge cloning the repo with no API key.

| # | User does | System shows |
| --- | --- | --- |
| C1 | `make replay`, opens localhost | S1, with a banner: "Offline mode: replaying cached runs, 0 credits." Example chips are pre-filled with the demo places |
| C2 | Clicks "Try a known case" | S2 plays the run at real pace from the cache; the credits bar shows "57 (replayed)" |
| C3 | Lands on S3 | The same result as the video, byte for byte |
| C4 | Opens the Ledger | Every engine call with its `search_id`, proving where the data came from |
| C5 | Pastes a different place | Error banner: "This place isn't in the offline cache. Add a SerpApi key to run it live." |

## 6. States, errors and edge cases

| State or trigger | Where | What the user sees (copy) | Actions offered |
| --- | --- | --- | --- |
| Invalid input | S1 inline | "That doesn't look like a Google Maps place link. Copy the link from the place's Share button." | Edit |
| Another run active | S1 | "An investigation is already running." | "View it", "Cancel it" |
| Missing API key | S1 banner | "No SerpApi key found. You can replay cached runs offline, or add a key to `.env`." | Replay offline |
| Too few reviews (< 20) | S2 → S1 | "This place has only 14 reviews, which is too few to test for coordination." | New investigation |
| Seed lookup fails | S2 → S1 | "Couldn't load this place from SerpApi. Try again in a minute." | Retry |
| Contributor skipped | S2 ticker (quiet) | "Skipped one reviewer (SerpApi didn't respond). Continuing." | none |
| Quota exhausted | S2 → S3 partial | "Your SerpApi credits ran out. Showing what was found so far." + **Low coverage** badge | Ledger, Replay offline |
| User cancels | S2 → S3 partial | "Stopped early after 31 of 60 credits. Results are based on partial coverage." + **Low coverage** badge | Rerun with bigger budget |
| Budget spent before the plateau | S3 | Low-coverage badge with tooltip: "The search was still finding new connections when the budget ran out." | Rerun with +40 credits |
| No ring found | S3 | Rating card unchanged. Verdict: "No coordination detected. We followed 38 reviewers across 2,940 places and found no group that shares places more than chance would explain." | New investigation |
| Ring found, timing unresolvable | S3 ring card | Lockstep shown as "Timing not resolvable (dates too coarse)" | none |
| Possible genuine community (compact geography or high rating variance) | S3 ring card | Note: "These places are within 2 km of each other and ratings vary. This could be a real community, such as a college group." | none |
| Possible brand or employee activity | S3 ring card | Note: "Most shared places belong to the same brand." | none |
| SSE disconnects | S2 | Silent auto-reconnect resumes from the last event; after 10 s: "Reconnecting…" | none |
| Offline cache miss | S2 → S1 | "This place isn't in the offline cache. Add a SerpApi key to run it live." | none |

## 7. Microcopy rules and interaction details

### Microcopy

| Rule | Use | Never |
| --- | --- | --- |
| Describe behaviour, not intent | "coordinated", "reviewed the same places", "unlikely by chance" | "fake", "fraud", "scam", "paid reviews" |
| Pair every statistic with words | "Expected by chance: 0.3 · Observed: 7" | A bare "p = 4e-8" on the main card (it lives under Details) |
| Name the window | "recent rating (newest 80 reviews)" | "true rating" |
| Hedge with numbers, not adjectives | "3.7–4.3" | "probably around 4" |
| Phase names in plain verbs | "Looking up the place" → "Reading recent reviews" → "Following reviewers" → "Checking places they share" → "Checking whether this could be chance" → "Done" | Internal names (sampling, peeling) |
| Reviewers | R1, R2 … | Names, photos, profile links |

### Interaction details

- **Graph.**
  - Users are small circles; places are rounded squares sized by log(d\_p); the seed is a large, labelled square.
  - New nodes fade in over 200 ms. The layout reflows at most every 1.5 s, and existing nodes keep their positions.
  - Ring members and places take the ring colour. Everything else dims to 30% when a ring is selected.
- **Hover.** A place shows its name and review count. A user shows R-id, total reviews and local-guide status.
- **Rating card animation.** One 600 ms count from displayed to adjusted. No animation when they are equal.
- **Keyboard.** Enter submits on S1. Esc closes drawers. Tab order runs rating card → rings → graph. Ring cards are buttons.
- **Accessibility.**
  - Graph colours meet 3:1 contrast against the background, and ring colour is never the only cue: a ring badge number is drawn on member nodes.
  - Every graph insight is also in a text list (the ring card), so screen-reader users lose nothing.
- **Responsive.** Built for ≥ 1280 px wide; the demo target. Below 900 px the graph stacks under the cards. Mobile is out of scope for v1.
- **Performance.** At 10,000 events, batch at animation-frame rate. If frame time exceeds 50 ms, hide edge rendering for non-ring nodes and show a note: "Showing ring edges only for speed."

## 8. Demo flow mapping and usability checks

### 3-minute demo, mapped to screens

| Time | Screen | Flow step | Must be visible |
| --- | --- | --- | --- |
| 0:00–0:12 | S1 | A1 | The 4.8 listing and the question "Are these reviewers connected?" |
| 0:12–0:20 | S1 → S2 | A2–A3 | Paste, Enter. The localhost URL in the address bar |
| 0:20–0:45 | S2 | A4–A6 | Graph growing; credits ticking; the ring card reaching 11 accounts |
| 0:45–1:15 | S3 | A8 + Details | Verdict line; expected vs observed; permutation p |
| 1:15–1:40 | O1 | A9 | The tile-shop drawer: 9 accounts, 10 days |
| 1:40–2:00 | S3 | Rating card | Displayed vs adjusted with interval |
| 2:00–2:20 | S2 → S3 | Control run (offline replay, sped up) | "No coordination detected" |
| 2:20–2:40 | O2 | Ledger | Engines used, `search_id`s |
| 2:40–3:00 | Slide + export | B6 | Eval plot; dossier PDF opens |

### Usability checks before recording (Oct 9)

- [ ] Someone who has not seen the project can start a run from S1 without help, within 30 s
- [ ] After reading only the rating card, they can say in their own words what was found
- [ ] They can find which places the ring shared within 2 clicks
- [ ] Nobody reads the result as "this clinic is fake" (ask: "what does this tell you?")
- [ ] The control-place result reads as reassuring, not empty or broken
- [ ] All copy passes the banned-word lint
