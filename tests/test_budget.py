import pytest

from nakshatra.serp.budget import Budget


@pytest.mark.parametrize("total", [20, 60, 200])
def test_split_sums_and_invariant(total):
    b = Budget(total)
    assert sum(b.remaining.values()) == total
    assert b.remaining["sample"] == -(-total * 20 // 100)
    toks = 0
    for pool in ("sample", "expand", "refine") * total:
        t = b.reserve(pool)
        if t:
            toks += 1
            b.settle(t, billed=True, cached=False)
    assert toks == total and b.billed == b.calls == total
    assert b.reserve("expand") is None


def test_cache_hit_costs_no_credit_but_takes_a_call():
    b = Budget(20)
    t = b.reserve("sample")
    b.settle(t, billed=False, cached=True)
    assert (b.billed, b.calls, b.cached) == (0, 1, 1)


def test_rollover():
    b = Budget(60)
    b.rollover("sample", "expand")
    assert b.remaining == {"sample": 0, "expand": 51, "refine": 9}
    assert b.reserve("sample") is None
