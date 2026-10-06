# Project status

Last updated: October 6, 2026. Submission deadline: October 10, 2026, 23:59 IST.

This page says what Nakshatra can do today, how that is checked, and what is left. The design documents are in [`docs/`](docs/), and every place where the build departs from them is explained in [`docs/DECISIONS.md`](docs/DECISIONS.md).

## What works today

### Investigating a place

- **Any Google Maps place as input:** a full Maps link, a short share link (`maps.app.goo.gl/…`), a raw place ID, or a search by category and area ("packers and movers", "Gandhipuram, Coimbatore").
- **A fixed credit budget** of 20 to 200 SerpApi searches, 60 by default. A run never spends more than its budget, and repeating a run costs nothing because every response is cached.
- **The investigation itself:**
  1. Read the place's newest and highest-rated reviews.
  2. Follow the most promising reviewers to their full review histories (SerpApi Contributor Reviews).
  3. Check the places they share for exact dates and popularity.
  4. Stop when no new connections are forming.
- **Live progress:** the credit counter, the current step and a growing map of reviewers and shared places, streamed as it happens.

### What the result tells you

- **A headline answer:** "Coordinated reviewing found", "N things worth a closer look", "Nothing unusual found" or "Not enough data for a clear answer".
- **Three ratings side by side:** Google's rating, the newest reviews (or the rating without a coordinated group, when one is found), and what experienced reviewers (10+ reviews) say.
- **Four checks, each marked "Worth a look", "Looks normal" or "Not enough data":**
  1. *Accounts that move together:* a group of accounts that keeps reviewing the same unrelated, little-known places. It is tested against randomly shuffled data and reported only when chance produces a group that tight less than 1% of the time.
  2. *Who wrote the recent reviews:* the share of brand-new accounts, and whether they rate the place much higher than experienced reviewers do.
  3. *Bursts of reviews:* many 5-star reviews in a few days, against the place's own usual pace.
  4. *Recent rating vs overall.*
- **Evidence:** the coordinated group's members (as R1, R2…), the places they share with dates, a table of every reviewer we followed, and the credit ledger with SerpApi search IDs.
- **Exports:** an evidence dossier in Markdown or PDF for reporting to Google or a consumer authority. It is the only output with contributor IDs, behind an "I understand" warning.
- **Controls:** cancel a running investigation and keep what was found; replay any past investigation offline for free.

### Running it

- `./run.sh` starts the backend and frontend and opens the browser. `./run.sh --replay` uses the shipped demo data with no key and no credits.
- `make test` runs 148 tests, and none of them calls SerpApi. They also run on GitHub for every push.
- `make eval` reproduces every evaluation number and plot in the README without spending credits.
- `data/demo.db` holds the shipped demo runs (real places plus a clearly labelled synthetic city). They replay offline byte for byte.

## How it is checked

| Check | Result |
| --- | --- |
| Planted coordinated groups of 8+ accounts found (real and synthetic graphs) | 100% found, no false groups |
| Control places wrongly flagged | 0 of 7 |
| Shuffled data wrongly flagged | 0.5% (target 0.5–2%) |
| Credits needed vs a naive crawl | 40 vs 60 credits; the target of half was **missed** |
| Offline replay | identical results in about 6 seconds |
| Real places checked live | 2 fertility clinics, 1 university, 2 landmark controls; Nakshatra itself has spent 98 SerpApi searches in total |

On real places, neither clinic showed a coordinated group of reused accounts. Both did show review-health patterns worth a look, such as 23 five-star reviews in 3 days at an 84-review clinic, while both landmark controls looked normal.

## Known limits

- Only groups that reuse the same accounts across several places count as "coordinated". Single-use accounts show up only in the review-health checks.
- The health checks are observations, not proof: a burst or a gap between newcomers and experienced reviewers can have ordinary causes.
- A run reads at most about 100 of a place's reviews, and SerpApi returns at most 200 reviews per reviewer.
- Calibration rests on 2 real and 5 synthetic control places, because the free plan allows only 250 searches a month.
- One investigation at a time; it runs on your own machine only.

## What is left

### Before submission (Oct 10)

- [ ] **Quick check mode:** about 6 credits per place, reading ~88 recent reviews and running only the four health checks. It works as a cheap first look, and as a way to scout many places before spending a full budget on one.
- [ ] **Scouting real places:** quick-check about 10 high-rated places in high-incentive categories (fertility, hair transplant, packers and movers), then run a full investigation on the one or two with the strongest flags, aiming for a real finding for the demo. **Blocked on credits:** as of Oct 6 the SerpApi key has only 18 of its 250 monthly searches left. SerpApi counts 232 used, of which Nakshatra's ledger accounts for 98, so the rest were used elsewhere with the same key. This needs the monthly reset, hackathon credits, or a different key.
- [ ] **Demo video** under 3 minutes, showing the first finding before 0:45.
- [ ] **Submission form,** including the AI-use disclosure.
- [ ] Optional: update the GitHub Actions versions (GitHub warns that Node 20 actions are being retired).

### Nice to have (planned, not started)

- **Near-duplicate review texts:** flag reviews in a group that are reworded copies of each other.
- **Optional plain-language summary** written by a language model, rejected automatically if it contains any number not in the result.
- **Repeat clients:** places that show up in coordinated groups across several investigations.
- **Open-source contribution:** a Contributor Reviews tool for SerpApi's search tools.

### After the hackathon

- **Memory across investigations:** remember detected groups so their accounts are recognised faster next time.
- **A hand-labelled validation set** of about 30 places, to measure accuracy on real data rather than planted groups.
- **Time as part of the search:** look for groups that review the same places in the same weeks, not just the same places.
- **Other review platforms:** the same method for Play Store and App Store reviews.
- **Area scans:** rank all clinics in an area by how trustworthy their reviews look.
