"""Result assembly: pseudonyms, explanations, final JSON (DM §6.3 ∪ API Result; DECISIONS A2, A12)."""
from __future__ import annotations

from typing import Any

from nakshatra.report.templates import LOCK_TMPL, NONE_TMPL, RING_TMPL, VERDICT_TMPL, check_copy


def sig3(x: float) -> float:
    return float(f"{x:.3g}")


def pseudonyms(s0: dict[int, float], cids: list[str], extra: list[int]) -> dict[int, str]:
    """R1..Rn by s0 descending, ties by contributor_id (SRS-DA-10, DM §6.3). Recomputable, never persisted."""
    order = sorted(set(s0) | set(extra), key=lambda u: (-s0.get(u, 0.0), cids[u]))
    return {u: f"R{i + 1}" for i, u in enumerate(order)}


def ring_explanation(n_users: int, n_places: int, exp: float, obs: float, lock: float | None, delta: float) -> str:
    lk = LOCK_TMPL.format(lock_pct=100 * lock, delta=delta) if lock is not None else ""
    return check_copy(RING_TMPL.format(n_users=n_users, n_places=n_places, exp=exp, obs=obs, lock=lk))


def verdict(reported: list[dict], rating: dict, n_expanded: int, n_places: int) -> str:
    if not reported or rating.get("adjusted") is None:
        return check_copy(NONE_TMPL.format(n_exp=n_expanded, n_places=n_places))
    members = {m for r in reported for m in r["members"]}
    places = {p["data_id"] for r in reported for p in r["places"]}
    timed = [r["lockstep_ratio"] for r in reported if r.get("lockstep_ratio") is not None]
    timing = ", mostly within the same fortnight" if timed and max(timed) >= 0.5 else ""
    lo, hi = rating["ci"]
    return check_copy(VERDICT_TMPL.format(n_users=len(members), n_places=len(places), timing=timing,
                                          adj=rating["adjusted"], lo=lo, hi=hi))


def build(*, run_id: str, seed: dict, credits: dict, coverage: dict, rings: list[dict], rating: dict,
          config_hash: str, delta_days: float, state: str = "done") -> dict[str, Any]:
    for r in rings:
        r["explanation"] = ring_explanation(len(r["members"]), len(r["places"]), r["expected_overlap"],
                                            r["observed_overlap"], r["lockstep_ratio"], delta_days)
    reported = [r for r in rings if r["reported"]]
    v = verdict(reported, rating, coverage["reviewers_expanded"], coverage["places"])
    return {
        "run_id": run_id, "state": state, "seed": seed, "credits": credits, "coverage": coverage,
        "rings": rings, "rating": rating, "verdict": v,
        "explanations": [r["explanation"] for r in reported],
        "no_coordination_message": None if reported else v,
        "narrative": None, "config_hash": config_hash,
    }
