"""Date strings -> time intervals (SRS §5.1). Pure."""
from __future__ import annotations

import math
import re
from datetime import datetime

DAY = 86400.0
UNIT_DAYS = {"day": 1.0, "week": 7.0, "month": 30.0, "year": 365.0}
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
    if unit == "day":
        lo, hi = T - (n + 1) * d, T - n * d
    elif unit == "year":
        lo, hi = T - (n + 0.5) * d, T - n * d
    else:
        lo, hi = T - (n + 0.5) * d, T - (n - 0.5) * d
    return lo, min(hi, T), False
