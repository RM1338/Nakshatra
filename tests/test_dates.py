import math

import pytest

from nakshatra.graph.dates import DAY, parse_interval

T = 1_790_000_000.0
W, M, Y, S = 7 * DAY, 30.44 * DAY, 365.25 * DAY, 1.5 * DAY

CASES = [
    ("a day ago", T - 2 * DAY, T - DAY), ("1 day ago", T - 2 * DAY, T - DAY), ("3 days ago", T - 4 * DAY, T - 3 * DAY),
    ("6 days ago", T - 7 * DAY, T - 6 * DAY), ("a week ago", T - 2 * W, T - W),
    ("2 weeks ago", T - 3 * W, T - 2 * W), ("4 weeks ago", T - 5 * W, T - 4 * W),
    ("a month ago", T - 2 * M - S, T - M + S), ("an month ago", T - 2 * M - S, T - M + S),
    ("2 months ago", T - 3 * M - S, T - 2 * M + S), ("11 months ago", T - 12 * M - S, T - 11 * M + S),
    ("a year ago", T - 2 * Y - S, T - Y + S), ("2 years ago", T - 3 * Y - S, T - 2 * Y + S), ("10 years ago", T - 11 * Y - S, T - 10 * Y + S),
    ("Edited a week ago", T - 2 * W, T - W), ("edited 3 months ago", T - 4 * M - S, T - 3 * M + S),
    ("EDITED 2 years ago", T - 3 * Y - S, T - 2 * Y + S), ("  5 days ago ", T - 6 * DAY, T - 5 * DAY),
    ("A Week Ago", T - 2 * W, T - W), ("3 hours ago", T - DAY, T), ("an hour ago", T - DAY, T),
    ("12 minutes ago", T - DAY, T), ("just now", T - DAY, T), ("today", T - DAY, T),
    ("yesterday", T - 2 * DAY, T - DAY), ("one month ago", T - 2 * M - S, T - M + S),
]
ISO = [("2025-03-01T10:00:00Z", 1740823200.0), ("2025-03-01T10:00:00+00:00", 1740823200.0),
       ("2026-09-20T00:00:00Z", 1789862400.0), ("2019-12-31T23:59:59Z", 1577836799.0)]
GARBAGE = [None, "", "   ", "sometime", "hace 2 meses", "il y a 3 jours", "2 fortnights ago", "-3 days ago",
           "2025-13-45T00:00:00Z", "ago"]


@pytest.mark.parametrize("s,lo,hi", CASES)
def test_relative(s, lo, hi):
    assert parse_interval(s, T) == (lo, hi, False)


@pytest.mark.parametrize("s,t", ISO)
def test_iso_exact(s, t):
    assert parse_interval(s, T) == (t, t, True)


@pytest.mark.parametrize("s", GARBAGE)
def test_garbage_is_unknown(s):
    lo, hi, exact = parse_interval(s, T)
    assert lo == -math.inf and hi == math.inf and not exact


def test_count_and_upper_bound():
    assert len(CASES) + len(ISO) + len(GARBAGE) == 40
    assert all(hi <= T for _, _, hi in CASES)


def test_i1_on_real_pairs():
    """I1: the exact date lies inside the relative interval, on real SerpApi (label, age) pairs."""
    import json
    from pathlib import Path
    pairs = json.loads((Path(__file__).parent / "fixtures/serpapi/date_pairs.json").read_text())["pairs"]
    assert len(pairs) >= 30
    for label, age_days in pairs:
        lo, hi, _ = parse_interval(label, T)
        assert lo <= T - age_days * DAY <= hi, (label, age_days)
