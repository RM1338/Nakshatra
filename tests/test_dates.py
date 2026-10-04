import math

import pytest

from nakshatra.graph.dates import DAY, parse_interval

T = 1_790_000_000.0
W, M, Y = 7 * DAY, 30 * DAY, 365 * DAY

CASES = [
    ("a day ago", T - 2 * DAY, T - DAY), ("1 day ago", T - 2 * DAY, T - DAY), ("3 days ago", T - 4 * DAY, T - 3 * DAY),
    ("6 days ago", T - 7 * DAY, T - 6 * DAY), ("a week ago", T - 1.5 * W, T - 0.5 * W),
    ("2 weeks ago", T - 2.5 * W, T - 1.5 * W), ("4 weeks ago", T - 4.5 * W, T - 3.5 * W),
    ("a month ago", T - 1.5 * M, T - 0.5 * M), ("an month ago", T - 1.5 * M, T - 0.5 * M),
    ("2 months ago", T - 2.5 * M, T - 1.5 * M), ("11 months ago", T - 11.5 * M, T - 10.5 * M),
    ("a year ago", T - 1.5 * Y, T - Y), ("2 years ago", T - 2.5 * Y, T - 2 * Y), ("10 years ago", T - 10.5 * Y, T - 10 * Y),
    ("Edited a week ago", T - 1.5 * W, T - 0.5 * W), ("edited 3 months ago", T - 3.5 * M, T - 2.5 * M),
    ("EDITED 2 years ago", T - 2.5 * Y, T - 2 * Y), ("  5 days ago ", T - 6 * DAY, T - 5 * DAY),
    ("A Week Ago", T - 1.5 * W, T - 0.5 * W), ("3 hours ago", T - DAY, T), ("an hour ago", T - DAY, T),
    ("12 minutes ago", T - DAY, T), ("just now", T - DAY, T), ("today", T - DAY, T),
    ("yesterday", T - 2 * DAY, T - DAY), ("one month ago", T - 1.5 * M, T - 0.5 * M),
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


def test_i1_iso_within_relative_on_fixture():
    """I1 on review pairs that carry both strings (synthetic until real fixtures exist, DECISIONS C)."""
    from tests.synth_world import NOW, World
    w = World()
    seed = w.seed_idx
    for u in w.by_place[seed]:
        r = w._review(u, seed)
        age = (NOW - parse_interval(r["iso_date"], NOW)[0]) / DAY
        if age >= 365:  # year buckets: real Google rounding unverified (DECISIONS C, T02)
            continue
        lo, hi, _ = parse_interval(r["date"], NOW)
        t = parse_interval(r["iso_date"], NOW)[0]
        assert lo <= t <= hi, (r["date"], age)
