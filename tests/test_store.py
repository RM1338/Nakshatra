import math

import pytest

from nakshatra.store.check import violations
from nakshatra.store.db import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "t.db")


def test_fresh_db_is_v2_and_clean(store):
    assert store.conn.execute("PRAGMA user_version").fetchone()[0] == 2
    assert store.conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert all(not v for v in violations(store).values())


def test_reopen_keeps_data(tmp_path):
    s = Store(tmp_path / "t.db")
    s.upsert_place("0x1:0x2", title="A", d_p=10)
    s.close()
    s2 = Store(tmp_path / "t.db")
    assert s2.conn.execute("SELECT title FROM places").fetchone()[0] == "A"


def test_edge_precision_only_improves(store):
    store.upsert_place("0x1:0x2")
    store.upsert_user("123")
    store.upsert_edge("123", "0x1:0x2", 5, 100.0, 200.0, False, None, "a" * 64)
    store.upsert_edge("123", "0x1:0x2", 5, 0.0, 1000.0, False, None, "b" * 64)   # wider: ignored
    assert store.edge_get("123", "0x1:0x2")["t_lo"] == 100.0
    store.upsert_edge("123", "0x1:0x2", 5, 120.0, 180.0, False, "rid", "c" * 64)  # narrower: wins
    e = store.edge_get("123", "0x1:0x2")
    assert (e["t_lo"], e["t_hi"], e["source_hash"], e["review_id"]) == (120.0, 180.0, "c" * 64, "rid")
    store.upsert_edge("123", "0x1:0x2", 4, 150.0, 150.0, True, None, "d" * 64)   # exact: wins, rating kept
    e = store.edge_get("123", "0x1:0x2")
    assert (e["t_lo"], e["exact"], e["rating"], e["source_hash"]) == (150.0, 1, 5, "d" * 64)
    store.upsert_edge("123", "0x1:0x2", 5, 160.0, 160.0, True, None, "e" * 64)   # exact vs exact: kept
    assert store.edge_get("123", "0x1:0x2")["t_lo"] == 150.0


def test_unknown_interval_roundtrips_as_inf(store):
    store.upsert_place("0x1:0x2")
    store.upsert_user("9")
    store.upsert_edge("9", "0x1:0x2", 3, -math.inf, math.inf, False, None, "a" * 64)
    e = store.edge_get("9", "0x1:0x2")
    assert e["t_lo"] == -math.inf and e["t_hi"] == math.inf


def test_constraints(store):
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        store.cache_put("x" * 64, "google_maps", {"api_key": "k"}, {}, 0.0)
    with pytest.raises(sqlite3.IntegrityError):
        store.upsert_place("not-a-data-id")
    store.run_create("r_0123456789", "x", 20, False, "{}", "h", 0.0)
    with pytest.raises(sqlite3.IntegrityError):
        store.run_update("r_0123456789", used=21)
    with pytest.raises(sqlite3.IntegrityError):
        store.ledger_add("r_0123456789", "google_maps", "h", None, cached=True, billed=True, ok=True, latency_ms=0)
