"""Review-health checks on a place's newest reviews (DECISIONS D17). Pure.

The crew miner only sees sellers who reuse accounts across many businesses. The commonest pattern in practice is
different: brand-new accounts, mostly 5 stars, arriving in bursts. These checks surface that on every place,
from data the run already has (no extra SerpApi calls). Each one compares the place with itself, so no outside
baseline is needed. They are observations to look at, never verdicts, and they do not change the rating.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

DAY = 86400.0
NEW_MAX = 2              # an account with at most this many reviews ever is "brand new"
EXPERIENCED_MIN = 10     # an account with at least this many reviews is "experienced"
MIN_GROUP = 5            # smallest group whose average rating we report
GAP = 0.5                # stars: new accounts rate the place this much higher than experienced ones
NEW_SHARE = 0.5          # half or more of the newest reviews come from brand-new accounts
BURST_DAYS = 3
BURST_MIN = 5            # at least this many reviews in BURST_DAYS
BURST_FACTOR = 4.0       # and at least this many times the place's usual pace
BURST_FIVE_STAR = 0.8    # and mostly 5 stars: a holiday crowd is mixed, bought reviews are not (ALG §4.1)
RECENT_GAP = 0.4         # stars between the newest reviews' average and the Google rating


@dataclass(frozen=True)
class Review:
    rating: float
    t: float | None      # exact time, if known
    k: int | None        # reviews the author has written in total
    text: bool           # has written text


def _avg(xs: list[float]) -> float | None:
    return round(mean(xs), 2) if len(xs) >= MIN_GROUP else None


def review_health(reviews: list[Review], displayed: float | None) -> dict:
    n = len(reviews)
    known = [r for r in reviews if r.k is not None]
    new = [r for r in known if r.k <= NEW_MAX]
    exp = [r for r in known if r.k >= EXPERIENCED_MIN]
    out: dict = {
        "n": n,
        "avg_recent": round(mean(r.rating for r in reviews), 2) if reviews else None,
        "displayed": displayed,
        "n_known": len(known),
        "n_new": len(new),
        "new_share": round(len(new) / len(known), 3) if known else None,
        "rating_new": _avg([r.rating for r in new]),
        "n_experienced": len(exp),
        "rating_experienced": _avg([r.rating for r in exp]),
        "five_star_share_new": round(sum(r.rating == 5 for r in new) / len(new), 3) if new else None,
        "no_text_share_new": round(sum(not r.text for r in new) / len(new), 3) if new else None,
        "burst": _burst(reviews),
        "flags": [],
    }
    if out["rating_new"] is not None and out["rating_experienced"] is not None \
            and out["rating_new"] - out["rating_experienced"] >= GAP:
        out["flags"].append("experience_gap")
    if out["new_share"] is not None and len(known) >= 10 and out["new_share"] >= NEW_SHARE:
        out["flags"].append("new_accounts")
    b = out["burst"]
    if b is not None and b["five_star"] >= BURST_FIVE_STAR * b["count"]:
        out["flags"].append("burst")
    if out["avg_recent"] is not None and displayed is not None and n >= 10 \
            and abs(out["avg_recent"] - displayed) >= RECENT_GAP:
        out["flags"].append("recent_gap")
    return out


def _burst(reviews: list[Review]) -> dict | None:
    """Densest BURST_DAYS window among exactly dated reviews, against the sample's own average pace."""
    dated = sorted((r for r in reviews if r.t is not None), key=lambda r: r.t)
    if len(dated) < 10:
        return None
    span_days = (dated[-1].t - dated[0].t) / DAY
    if span_days < 14:
        return None
    best, best_i, j = 0, 0, 0
    for i in range(len(dated)):
        while dated[i].t - dated[j].t > BURST_DAYS * DAY:
            j += 1
        if i - j + 1 > best:
            best, best_i = i - j + 1, j
    expected = len(dated) / span_days * BURST_DAYS
    if best < BURST_MIN or best < BURST_FACTOR * expected:
        return None
    window = dated[best_i:best_i + best]
    return {"count": best, "start": window[0].t, "end": window[-1].t, "expected": round(expected, 2),
            "five_star": sum(r.rating == 5 for r in window),
            "new_accounts": sum(r.k is not None and r.k <= NEW_MAX for r in window)}
