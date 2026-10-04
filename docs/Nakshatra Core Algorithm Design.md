# Nakshatra Core Algorithm Design

Oct 4, 2026 · @Ronel Abraham Mathew

The reasoning behind Nakshatra's detection engine: what is being inferred, from which observations, under which assumptions, and how each stage fails. Where this document refines a formula from the SRS or LLD, it says so and why.

## 1. Problem formulation

Nakshatra answers one question about one place: **do some of this place's reviewers behave as a coordinated group, and how much does that group move the rating?**

### Setting

There is a true, mostly unobserved bipartite graph G\* = (U\* ∪ P\*, E\*) of every Google Maps reviewer, place and review in a metro area. Each edge carries a rating r ∈ {1..5} and a timestamp t. Somewhere in G\* are coordinated groups: sets of accounts R ⊂ U\* that review a common set of places Q ⊂ P\* at similar times, typically with 5 stars, because someone paid them to.

Nakshatra sees none of G\* directly. It can only *query* it, and each query costs one SerpApi credit:

- **Place query** `reviews(p, sort, page)`: up to 8 or 20 edges incident to p, with exact timestamps and reviewer profile counts.
- **Reviewer query** `history(u)`: up to 200 edges incident to u, with relative timestamps and place metadata, including the global review count d\_p.

### Inputs and outputs

| Input | Output |
| --- | --- |
| Seed place p0, budget B (credits), config θ | Rings {(R\_i, Q\_i)}, each with a significance score, an expected-vs-observed overlap and a lockstep ratio |
|  | Ring-adjusted rating r̂ for p0, with an interval |
|  | The observed subgraph Ĝ ⊂ G\*, with lineage, for audit |

### What makes it hard

1. **Partial, costly observation.** The graph must be discovered under a budget of about 60 queries. Which queries to spend is itself a decision. This is an active-search problem, not a batch-mining one.
2. **Heterogeneous precision.** Place queries return exact times; reviewer queries return fuzzy ones ("3 months ago"). Evidence quality varies by edge.
3. **Camouflage.** Paid accounts also review popular, legitimate places to look normal.
4. **Base rates.** Genuine reviewers in one city overlap by chance, especially at popular places. A ring must be *unlikely by chance*, not merely dense.
5. **Selection effects.** The ring is found and then tested on the same data. A naive test would be overconfident (§6).

## 2. Pipeline at a glance

Six stages run in two phases. An exploration phase repeats after every SerpApi query. A judgement phase then runs once.

&#91;embedded content: detection pipeline · 6 stages, 1 feedback loop\]

The feedback loop is the core design choice. Mining is cheap enough (milliseconds) to run after every query, so the current best ring steers which reviewer or place to query next, and tells the crawler when to stop spending credits.

## 3. Observation model and its biases

Every stage is designed around what the two queries can and cannot show. Six biases matter.

| # | Bias | Source | Effect if ignored | Handling |
| --- | --- | --- | --- | --- |
| B1 | **Sort-order sampling.** `ratingHigh` pages over-represent 5-star reviews | Seed sampling uses `ratingHigh` to find suspects fast | The rating estimate is inflated; suspects look more common than they are | Use `ratingHigh` pages **only for discovery**. The rating estimate uses `newestFirst` pages only (§7.2) |
| B2 | **Recency sampling.** `newestFirst` covers only the latest \~100–200 reviews | Budget | Old rings are invisible from the seed | Rings are found mainly through reviewer histories, which go back up to 200 reviews. Report "window covered" in the coverage block |
| B3 | **Relative dates.** Contributor feeds say "a year ago" | Engine format | False precision in time analysis | Interval arithmetic (§7.1). Refine exact dates only where a ring depends on them |
| B4 | **200-review cap.** Heavy reviewers are truncated | Engine limit | Overlap is under-counted for power users | Mark `truncated`. Use k\_u from the profile count, not the observed degree, in the null model |
| B5 | **Non-Google reviews** (Trip.com etc.) have no contributor | Aggregated sources | Missing graph edges | Excluded from expansion. Counted separately in coverage |
| B6 | **Survivorship.** Google already removed some fake reviews | Platform enforcement | Rings look smaller than they were | No correction is possible. The finding is a lower bound, and the dossier states it |

**Core consequence.** Ĝ is a biased sample of G\*, collected *because* the nodes looked suspicious. Every statistic computed on it must either condition on that selection or be calibrated against a null that undergoes the same selection. This drives the revised significance test in §6.

## 4. Stages 1 and 2: reviewer prior and budgeted exploration

### 4.1 Reviewer prior s0(u)

The prior answers one narrow question: *if we can afford to follow only some reviewers, which are most likely to lead to a ring?* It is a crawl heuristic, not a verdict. Nobody is flagged because of s0.

```latex
s_0(u) = \sigma\big(w_0 + w_1 / \log(2 + k_u) + w_2[r = 5] + w_3[\text{photos}_u = 0] + w_4 z(t) - w_5[\text{local guide}_u]\big)
```

| Feature | Why it carries signal | Why it is weak alone |
| --- | --- | --- |
| 1/log(2+k\_u) | Purpose-made accounts have short histories | Many genuine people review rarely |
| Rating = 5 | Paid reviews are almost always 5 stars | Most genuine reviews are also 4–5 stars |
| No photos | Low-effort accounts rarely upload | Many genuine users do not upload either |
| Burst z-score | Rings are often deployed in bursts | Real events (an opening, a festival) cause bursts too |
| Local Guide (negative) | Gamified long-term contributors are costlier to fake | Guide accounts can also be bought or hijacked |

**Calibration.** The initial weights are hand-set. Once injected data exists, fit them by logistic regression with a label of "belongs to a planted ring", using L2 regularisation and the five features. Keep the hand-set sign constraints, and fall back to the hand-set values if a fitted coefficient flips sign. Freeze the result before the demo.

### 4.2 Exploration as active search

**Objective.** Given the budget B, choose the queries that maximise the chance of recovering the densest anomalous subgraph incident to the seed. This is active search on graphs. The optimal policy is intractable, so Nakshatra uses a greedy policy with two signals:

1. **Prior relevance.** Follow high-s0 reviewers first. A reviewer query returns up to 200 edges for 1 credit, so it is by far the cheapest way to grow the graph.
2. **Structural feedback (snowball).** Once two followed reviewers share a non-seed place p, p is "hot". Reviewers who also reviewed p become more valuable, because a ring is exactly a set of users who share places.

```latex
\pi(v) = s_0(v)\,\big(1 + \beta\,|H_v|\big), \qquad H_v = \{p \in \text{hot} : (v, p) \in \hat E\}
```

**Refinement as value of information.** A place query on a hot place costs 1 credit and buys two things. It turns relative dates into exact ones for the ring's edges, and it surfaces new co-reviewers who were not among the seed's sampled reviewers. The second is what lets Nakshatra find ring members whose seed review fell outside the sampled window (bias B2). The hot place chosen is the one maximising (followed reviewers of p) / log(d\_p + 5): many suspects at a small place is the strongest lead.

**Why not BFS.** BFS from the seed spends its credits evenly across reviewers. Because ring members are a small minority of a popular place's reviewers, BFS dilutes the budget. The evaluation compares priority, BFS and random expansion on the same cached graphs (§10).

**Stopping rule.** After each query, re-peel and record the best density g\*. Stop when g\* improves by less than ε = 2% over the last 8 queries, or when the budget is spent. A plateau means the ring is fully revealed, or that there is no ring to find. In both cases further credits buy little.

## 5. Stage 3: ring mining

### 5.1 Objective

Find node sets S = R ∪ Q in Ĝ (seed removed) that maximise a weighted average degree:

```latex
g(S) = \frac{f(S)}{|S|}, \qquad f(S) = \sum_{(u,p) \in E(S)} c_p, \qquad c_p = \frac{1}{\log(d_p + 5)}
```

This is FRAUDAR's objective ([Hooi et al., KDD 2016](https://unpaywall.org/10.1145%2F2939672.2939747)), with one adaptation.

### 5.2 Why these choices

- **Densest subgraph, not cliques.** Real rings are not perfect bicliques. Members skip some jobs and accounts get removed. Average degree tolerates missing edges, where clique-finding would fragment the ring.
- **Column weights for camouflage.** Fraudsters add edges to popular places to look normal. With c\_p decreasing in popularity, those camouflage edges add little to f(S). The edges that make a group dense are the ones to obscure places, which is exactly where coordination is visible. FRAUDAR proves that, with such weights, camouflage cannot hide the fraud block's contribution to the objective.
- **Global popularity, not local degree.** FRAUDAR uses each column's degree *in the observed graph*. In Nakshatra the observed graph is a tiny, suspicion-biased slice of the city, so a local degree would make a ring's own places look "popular" just because the ring was crawled. Maps reports each place's true review count d\_p, so the weight uses it. **This is the main adaptation, and it is only possible because the contributor engine returns place metadata.**
- **Seed excluded.** Every seed reviewer shares the seed by construction. Including it would make every sample look dense. Evidence must come from *other* shared places.

### 5.3 Greedy peeling

Repeatedly remove the node with the smallest weighted degree, and remember the best g along the way. The node set at that best point is returned.

- This is a 2-approximation of the optimal weighted densest subgraph.
- With a heap it runs in O(|E| log |V|).
- At ≤ 10k edges it takes milliseconds, which is what allows re-peeling after every query (the stopping rule needs it).

### 5.4 From dense block to ring

The densest block can contain bystanders: a genuine power user who happens to review many of the same small places. Two trimming passes turn the block into a ring:

1. Q = places in the block reviewed by ≥ 2 block users.
2. R = block users who reviewed ≥ 50% of Q.
3. Repeat steps 1 and 2 once more. Keep the ring if |R| ≥ 4 and |Q| ≥ 3.

To find several rings, remove R from the graph and peel again, up to 5 times. Peeling is deterministic, so removal order and ties break by index, and repeated runs return identical rings.

## 6. Stage 4: significance (revised)

**Revision.** The SRS/LLD formula sums π\_p² only over the ring's own places Q. That conditions on places the miner *picked because they were shared*. The result is overconfident, with p-values like 1e-40 that mean nothing.

This design replaces it with two tests:

- **A display statistic.** A pairwise overlap computed against the whole city. This is the number the user sees.
- **A selection-aware gate.** A permutation test that reruns the full miner on shuffled graphs. This is the number that decides whether a ring is reported.

Update `significance.py` and SRS §5.5 accordingly.

### 6.1 Display statistic: pairwise overlap against the whole city

Under independence, reviewer u picks each of their k\_u places with probability proportional to popularity π\_p = d\_p / D. The chance that two independent reviewers both reviewed p is about (k\_u π\_p)(k\_v π\_p). So the expected number of shared places is:

```latex
\lambda_{uv} = k_u\, k_v \sum_{p \in P} \pi_p^2 = k_u\, k_v\, H, \qquad H = \sum_p \pi_p^2
```

- **H** is the Herfindahl concentration of the city's review mass. It is large when a few malls and temples dominate, and small when reviews spread thinly. It is estimated from every place observed in the run plus the category-baseline places, with D = s · Σ d\_p.
- **m\_uv** is the observed number of shared places, counted over all non-seed places and not only Q.
- **The pair p-value** is the Poisson tail P(X ≥ m\_uv) with X \~ Poisson(λ\_uv).
- **The UI shows** the ring's mean λ as "expected by chance" and its mean m as "observed".

This statistic is honest about base rates. Two avid foodies sharing 3 popular restaurants yields λ ≈ 1 and an unremarkable p. It is still not selection-corrected, so it is shown but it does not gate.

### 6.2 Gate: degree-preserving permutation test

The question is whether a block this dense would emerge *from this crawl* if reviews were randomly rewired.

```text
input: observed subgraph Ĝ (seed removed), observed best ring density g_obs
repeat N = 200 times:
    Ĝ' <- Ĝ with edges rewired by curveball swaps   # preserves every user's and every place's degree
    g_null[i] <- best density of find_rings(Ĝ')     # same miner, same trimming, same weights
p_emp = (1 + #{i : g_null[i] >= g_obs}) / (N + 1)
report ring iff p_emp < alpha AND median pairwise p (6.1) < alpha
```

- **Why degree-preserving.** It keeps each account's activity level and each place's popularity, which are the things that make overlap likely by chance. It destroys only *who-with-whom*, which is the thing coordination creates.
- **Why the same miner.** The null then goes through the same "find the densest thing" search as the real data. That is what corrects the selection effect.
- **Rings beyond the first.** Compare ring i's density with the null's i-th best density. Equivalently, peel the null graph i times. This is mildly conservative.
- **Cost.** 200 × \~5 ms peel ≈ 1 s on a typical run graph. It runs once, in the mining phase. Curveball swapping does 5|E| swaps per sample for mixing.
- **Resolution.** With N = 200 the smallest attainable p\_emp is 1/201 ≈ 0.005. That is below α = 0.01 but not by much, so use N = 500 when a run's p\_emp sits at the floor.

### 6.3 Calibration of s

Calibrate the scale s in D on the control places: choose s so that the share of control-place pairs with p < α in 6.1 is close to α. The gate in 6.2 needs no calibration. That robustness is why it, and not 6.1, decides reporting.

## 7. Stages 5 and 6: temporal lockstep and adjusted rating

### 7.1 Temporal lockstep (exact, via interval graphs)

Each edge carries an interval \[t\_lo, t\_hi\]. Exact dates are points; relative dates are ranges. Two reviews of the same place *co-occur* if their intervals come within δ (default 14 days) of each other.

**Reduction.** Widen every interval by δ/2 on both sides. Two widened intervals overlap if and only if the originals are within δ. The co-occurrence graph at a place is therefore an *interval graph*. Its maximum clique, the largest group of members who all posted within δ of each other, equals the maximum number of widened intervals covering a single point. A sweep line computes that exactly in O(n log n).

This replaces the LLD's O(n²) heuristic, which counted pairs relative to one anchor and could under-count.

```python
def max_cooccurring(intervals: list[tuple[float, float]], delta: float) -> int:
    """Largest set of reviews pairwise within delta of each other (exact, interval-graph clique)."""
    ev = []
    for lo, hi in intervals:
        ev.append((lo - delta / 2, +1))
        ev.append((hi + delta / 2, -1))
    ev.sort(key=lambda x: (x[0], -x[1]))      # opens before closes at the same instant
    best = cur = 0
    for _, d in ev:
        cur += d
        best = max(best, cur)
    return best
```

A place is **in lockstep** if `max_cooccurring / members_at_place ≥ 0.6`. The ring's lockstep ratio is the share of its places that are in lockstep.

**Honesty rule.** When the median interval width exceeds 30 days, the ratio is reported as `null` ("timing not resolvable"). Wide intervals overlap trivially, so a ratio computed from them would look like lockstep when it is not.

**Role.** Lockstep is corroborating evidence and is shown with the ring. It does not gate reporting, because rings can be deployed slowly on purpose. Requiring lockstep would cut recall for the cases a fraudster designs.

### 7.2 Ring-adjusted rating

**Sample.** Use reviews from `newestFirst` pages only, call them N. `ratingHigh` pages are excluded because they over-sample 5-star reviews (bias B1). The estimate therefore describes the place's *recent* rating, and the UI labels it that way.

**Down-weighting.** Each reviewer gets a membership weight q\_u ∈ \[0, 1\]. Members of reported rings get q\_u = min(1, g(R)/τ), where τ is the 95th-percentile density on the control places. Everyone else gets 0. A very dense ring removes its members' reviews completely; a borderline ring removes them partially.

**Shrinkage.** Removing reviews leaves fewer data points. To avoid a noisy estimate, the rating is shrunk toward μ\_cat, the review-weighted mean rating of the same-category places nearby. The pull is κ = 5 pseudo-reviews:

```latex
\hat r = \frac{\sum_{i \in N} (1 - q_{u_i})\, r_i + \kappa\, \mu_{\text{cat}}}{\sum_{i \in N} (1 - q_{u_i}) + \kappa}
```

This is the posterior mean under a conjugate normal prior centred on the neighbourhood. With no rings it stays within κ/(n + κ) of the sample mean, which is about 3% at n = 160.

**Uncertainty.** Resample the n reviews 1,000 times (seed 7). The interval is the 2.5th to 97.5th percentile of r̂. Ring membership is held fixed, so the interval reflects sampling noise, not membership uncertainty. The dossier says so.

**What the user sees.** "Recent rating 4.8 → 3.9 (3.6–4.2) after setting aside 11 coordinated accounts." The rating Google displays is shown alongside, unchanged.

## 8. Worked example

This is a synthetic example built to show the arithmetic. It does not describe a real business.

### City concentration H

The run observes about 3,000 places plus the baseline:

- 10 landmarks with 5,000 reviews each
- 100 mid-size places with 500 each
- 2,890 small places with about 100 each

That gives D ≈ 389,000.

| Group | π\_p | π\_p² | Count | Contribution to H |
| --- | --- | --- | --- | --- |
| Landmarks | 0.01285 | 1.65e-4 | 10 | 1.65e-3 |
| Mid-size | 0.00129 | 1.65e-6 | 100 | 1.65e-4 |
| Small | 0.000257 | 6.6e-8 | 2,890 | 1.91e-4 |
| **H** |  |  |  | **≈ 2.0e-3** |

Landmarks dominate H. That is why sharing a famous temple is weak evidence and sharing a tile shop is strong.

### Pair statistics (§6.1)

| Pair | k\_u, k\_v | λ = k\_u k\_v H | Observed shared m | P(X ≥ m) | Reading |
| --- | --- | --- | --- | --- | --- |
| Two ring accounts | 14, 11 | 154 × 2.0e-3 = 0.31 | 7 small places | ≈ 4e-8 | Very unlikely by chance |
| Two genuine power reviewers | 180, 150 | 27,000 × 2.0e-3 = 54 | 58 | ≈ 0.3 | Ordinary for heavy users |

The second row is why raw overlap counts mislead. Two heavy local reviewers share dozens of places legitimately.

### Density (§5)

The ring has 11 users and 9 places, with 85 of the 99 possible edges present. Every place has d\_p ≈ 30, so c\_p = 1/log(35) ≈ 0.28.

- f = 85 × 0.28 ≈ 23.9
- |S| = 20
- g ≈ 1.19

The densest block found in 200 degree-preserving shuffles of the same crawl peaks at about 0.4–0.6 (an assumed value, to be measured). That gives p\_emp = 1/201 ≈ 0.005, below α = 0.01, so the ring is reported.

### Lockstep (§7.1)

At 7 of the 9 places, at least 60% of the members' widened intervals overlap one point, so the lockstep ratio is 0.78. The median interval width is 30 days or less after refining 4 hot places, so the ratio is reported.

### Adjusted rating (§7.2)

The `newestFirst` sample has n = 80 reviews and a mean of 4.43. Ring members wrote 34 of them, all 5-star. g/τ ≥ 1, so each of those gets q = 1. The other 46 reviews average 4.0, and μ\_cat = 4.2.

```latex
\hat r = \frac{46 \times 4.0 + 5 \times 4.2}{46 + 5} = \frac{205}{51} \approx 4.02
```

**Displayed to the user:** "Recent rating 4.43 → 4.02 after setting aside 11 coordinated accounts (expected shared places by chance ≈ 0.3, observed ≈ 7)."

## 9. Adversarial robustness and false positives

### 9.1 How a ring operator would evade, and what still works

| Evasion | Effect on Nakshatra | Residual signal | Verdict |
| --- | --- | --- | --- |
| **Camouflage:** also review popular places | Adds edges with low c\_p | Weighted density still isolates the obscure shared places (§5.2) | Robust |
| **Slow deployment:** spread reviews over months | Lockstep ratio drops | Shared obscure places remain; lockstep does not gate | Robust (reported without lockstep) |
| **Aged or hijacked accounts** with long histories | Prior s0 drops; the account may not be expanded | Snowball: if 2 expanded members share a place, the hijacked co-reviewers are pulled in via refinement | Partially robust |
| **Rotate many small crews** (2–3 accounts per client) | Rings fall below the 4×3 minimum | Repeated crews across different seed runs (cross-run query in the Data Model §9.2) | **Weak in v1** |
| **One account per client, a huge pool** | No co-review structure | Only per-account signals, which are out of scope | **Not detectable** by design |
| **Mix in genuine reviews** at client places | Rating effect diluted | Ring still found; the adjusted rating reflects the smaller impact | Robust (correctly reports small impact) |
| **Delete reviews after payment** | Edges disappear before the crawl | None | Not detectable (B6) |

The limits are honest and belong in the README. Nakshatra catches *crews*, groups that reuse the same accounts across several clients. That is the dominant model for cheap review sellers, and it is how human investigators find them ([Local Search Forum](https://localsearchforum.com/threads/business-paying-for-fake-5-star-reviews-on-google-maps.63271/)).

### 9.2 Genuine communities that look like rings

| Lookalike | Why it is dense | What separates it | Mitigation |
| --- | --- | --- | --- |
| A college friend group reviewing campus cafés | Shared obscure places, similar times | Mixed ratings; places cluster geographically near one point; long, varied texts | Show rating variance and the geographic spread of Q in the ring panel; the dossier notes "a geographically compact ring may be a real community" |
| A tour group reviewing the same itinerary | Strong lockstep in time | Places are mostly landmarks (low c\_p); one-off timing, not repeated across months | Low weighted density; the permutation test usually fails |
| A family reviewing relatives' businesses | Shared small places | Small size, often fewer than 4 members | Size threshold |
| Local Guide meetups | Shared events, many places | High k\_u gives a large λ; long, unrelated histories | Poisson display shows an unremarkable p; local-guide prior |
| Employees reviewing their employer's branches | Same chain, many branches | The places share a title or brand | **Add a check:** flag rings whose Q titles share a brand token; label "possible employee or brand activity" |

**Planned guard (P1).** Compute two extra numbers for each ring and show them:

- the rating variance of the ring's edges (paid crews ≈ 0, genuine groups > 0); and
- the spread of Q's coordinates (the median pairwise distance in km).

Neither gates reporting. Both help a human read the ring correctly.

## 10. Calibration, sensitivity, the LLM's role, future work

### 10.1 Calibration procedure (run once, on Oct 7, then freeze)

1. **Data.** Fully crawl 10 real places (≥ 60 credits each, all cached) plus 10 control places, meaning chains and landmarks where coordination is implausible.
2. **Inject.** Plant 3 rings per real graph using `eval/inject.py`, with the size, place-count and camouflage grid in step 4.
3. **Fit.**
   - Fit the prior weights by logistic regression (§4.1).
   - Choose s so the control false-positive rate of §6.1 ≈ α (§6.3).
   - Set τ to the 95th-percentile ring density on the controls.
4. **Measure.** Record recall and precision for each cell of the grid:
   - ring size {5, 8, 12} × places {5, 8, 12} × camouflage {0, 0.3, 0.6};
   - credit-efficiency curves for priority, BFS and random expansion;
   - permutation p-value calibration on pure-null shuffles. The share below α should be ≈ α.
5. **Freeze.** Write the fitted values to `config.yaml`. Commit the plots with the `config_hash` in their filenames.

### 10.2 Sensitivity (what to report, not guess)

| Parameter | Expected effect of increasing it | Report |
| --- | --- | --- |
| Budget B | Higher recall, with diminishing returns | Recall vs B curve |
| β (hot boost) | Faster ring completion; more risk of over-following one cluster | Recall at B = 60 for β ∈ {0, 0.5, 1} |
| Minimum ring size | Higher precision, lower recall on small crews | Grid in step 4 |
| δ | More lockstep, which is less meaningful | Lockstep ratio on controls vs δ |
| κ | Adjusted rating moves toward μ\_cat | Shown in the dossier |

### 10.3 Where the LLM is and is not used

| Step | LLM? | Why |
| --- | --- | --- |
| Query planning, prior, expansion, mining, significance, lockstep, rating | **No** | These decide outcomes, and must be deterministic, auditable and testable |
| Ring explanation text | No; a template | Numbers must be exact |
| Optional narrative paragraph | Yes | Language only. The guard rejects any number not present in the result (LLD §8.2) |

The intelligence is in the search policy and the statistics, not in a prompt. That is deliberate, and it is the answer to the "wrapper" critique.

### 10.4 Future work (post-hackathon)

- **Time as a third mode.** Mine dense blocks in a user × place × week tensor ([D-Cube family](https://www.frontiersin.org/journals/big-data/articles/10.3389/fdata.2020.594302/pdf)) instead of using time as a post-hoc check.
- **Cross-run memory.** Persist detected crews, and boost their members' priors in future runs. Small rotating crews become visible across clients.
- **Cross-platform.** Same algorithm over Play Store and App Store reviews (APPLOCK) and Tripadvisor reviews, all available through SerpApi engines.
- **Membership uncertainty.** Bootstrap over the crawl and the mining, not only over ratings, to give per-member confidence.
- **Active-search theory.** Replace the greedy priority with an expected-improvement criterion on density, and compare against the greedy policy on the same budgets.
