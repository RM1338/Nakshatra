"""Date strings -> time intervals. Pure.

Google floors relative ages to whole units, with calendar months and years: "N units ago" means an age in
[N, N+1) units (verified on real pairs, tests/fixtures/serpapi/date_pairs.json; DECISIONS C6). This replaces
the ±0.5 rule in SRS §5.1. Months and years get CAL_SLACK on each side for calendar-length variation.
"""
from __future__ import annotations

import math
import re
from datetime import datetime

DAY = 86400.0
UNIT_DAYS = {"day": 1.0, "week": 7.0, "month": 30.44, "year": 365.25}
CAL_SLACK = 1.5 * DAY
REL = re.compile(r"^(?:edited\s+)?(a|an|one|\d+)\s+(day|week|month|year)s?\s+ago$", re.I)
UNKNOWN = (-math.inf, math.inf, False)


def parse_interval(s: str | None, T: float) -> tuple[float, float, bool]:
    """Return (t_lo, t_hi, exact). Unparseable -> (-inf, +inf, False). Upper bound never exceeds T."""
    if not s or not isinstance(s, str):
        return UNKNOWN
    s = s.strip()
    if s[:4].isdigit() and "T" in s:
        try:
            t = datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return UNKNOWN
        return t, t, True
    low = s.lower().removeprefix("edited").strip()
    if low in ("today", "just now", "a moment ago") or re.search(r"\b(hour|minute|second)s?\b", low):
        return T - DAY, T, False
    if low == "yesterday":
        return T - 2 * DAY, T - DAY, False
    m = REL.match(low)
    if not m:
        return UNKNOWN
    n = 1 if m.group(1) in ("a", "an", "one") else int(m.group(1))
    unit = m.group(2)
    d = UNIT_DAYS[unit] * DAY
    slack = CAL_SLACK if unit in ("month", "year") else 0.0
    return T - (n + 1) * d - slack, min(T, T - n * d + slack), False
