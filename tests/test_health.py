from nakshatra.algo.health import DAY, Review, review_health

T0 = 1_780_000_000.0


def test_clean_place_raises_no_flags():
    reviews = [Review(float(4 + (i % 2)), T0 + i * 3 * DAY, 15 + i, True) for i in range(40)]
    h = review_health(reviews, 4.5)
    assert h["flags"] == [] and h["burst"] is None and h["rating_new"] is None


def test_bought_pattern_raises_flags():
    old = [Review(3.0 + (i % 3), T0 + i * 4 * DAY, 20 + i, True) for i in range(15)]   # experienced, mixed stars
    burst = [Review(5.0, T0 + 30 * DAY + i * 3600, 1, False) for i in range(15)]        # 15 new accounts in a day
    h = review_health(old + burst, 4.2)
    assert set(h["flags"]) >= {"experience_gap", "new_accounts", "burst"}
    assert h["rating_new"] == 5.0 and h["rating_experienced"] == 4.0
    assert h["burst"]["count"] >= 15 and h["burst"]["new_accounts"] >= 15 and h["burst"]["five_star"] >= 15
    assert h["no_text_share_new"] == 1.0


def test_recent_gap_and_small_samples():
    assert "recent_gap" in review_health([Review(5.0, None, 3, True) for _ in range(12)], 4.2)["flags"]
    small = review_health([Review(5.0, None, 1, False) for _ in range(4)], 3.0)
    assert small["flags"] == [] and small["rating_new"] is None  # too few to say anything
    assert review_health([], None)["avg_recent"] is None


def test_mixed_burst_is_shown_but_not_flagged():
    calm = [Review(4.0, T0 + i * 20 * DAY, 20, True) for i in range(10)]
    crowd = [Review(float(3 + (i % 3)), T0 + 100 * DAY + i * 3600, 15, True) for i in range(6)]  # holiday crowd
    h = review_health(calm + crowd, 4.1)
    assert h["burst"] is not None and "burst" not in h["flags"]
