"""Vertical slice (IMPLEMENTATION_PLAN §6): live (mocked) run, free repeat, identical offline replays, integrity."""
import json

import httpx
import pytest

from nakshatra.orchestrator.run import run_once
from nakshatra.settings import load_config
from nakshatra.store.check import violations
from nakshatra.store.db import Store
from tests.synth_world import NOW, World

KEY = "synthetic-test-key-0123456789"


def cfg():
    base = load_config()  # mass_scale pinned for the synthetic city (DECISIONS B8)
    return base.model_copy(update={"stats": base.stats.model_copy(update={"mass_scale": 4.0})})


def stable(status):
    r = dict(status["result"])
    r.pop("run_id"), r.pop("credits")
    return json.dumps(r, sort_keys=True, separators=(",", ":"))


async def go(store, w, offline=False, budget=60):
    http = httpx.AsyncClient(transport=w.transport())
    return await run_once(w.seed_data_id, budget, offline=offline, api_key="" if offline else KEY, http=http,
                          now=NOW, cfg=cfg(), store=store)


@pytest.fixture(scope="module")
def world():
    return World()


async def test_slice(tmp_path, world):
    store = Store(tmp_path / "e2e.db")
    live = await go(store, world)
    assert live["state"] == "done", live["error"]
    assert 0 < live["credits"]["used"] <= 60
    res = live["result"]
    ring = next(r for r in res["rings"] if r["reported"])
    raw = json.loads(store.conn.execute("SELECT members_json FROM rings WHERE run_id=? AND idx=?",
                                        (live["run_id"], ring["idx"])).fetchone()[0])
    assert len(set(raw) & world.ring_cids) >= 8 and len(set(raw) - world.ring_cids) <= 1
    assert all(m.startswith("R") for m in ring["members"])
    assert res["rating"]["set_aside"] > 0 and res["rating"]["adjusted"] < res["rating"]["sample_mean"]

    calls = world.calls
    repeat = await go(store, world)
    assert repeat["credits"]["used"] == 0 and world.calls == calls  # repeat run is free
    assert stable(repeat) == stable(live)

    a = await go(store, world, offline=True)
    b = await go(store, world, offline=True)
    assert a["state"] == b["state"] == "done" and world.calls == calls  # zero network calls offline
    assert stable(a) == stable(b) == stable(live)

    assert all(not v for v in violations(store).values())
    for (payload,) in store.conn.execute("SELECT payload_json FROM events WHERE run_id=?", (live["run_id"],)):
        assert not any(cid in payload for cid in world.ring_cids)  # no raw IDs on the stream
    dump = "\n".join(store.conn.iterdump())
    assert KEY not in dump and "Person " not in dump


async def test_control_reports_nothing(tmp_path):
    st = await go(Store(tmp_path / "c.db"), World(seed=8, ring_size=0))
    assert st["state"] == "done" and not any(r["reported"] for r in st["result"]["rings"])
    assert st["result"]["no_coordination_message"].startswith("No coordination detected")


async def test_offline_unknown_place_is_cache_miss(tmp_path):
    st = await go(Store(tmp_path / "o.db"), World(), offline=True)
    assert st["state"] == "failed" and st["error"]["code"] == "E_CACHE_MISS" and st["credits"]["used"] == 0


@pytest.mark.parametrize("budget", [20, 60, 200])
async def test_budget_never_exceeded(tmp_path, budget, world):
    store = Store(tmp_path / "b.db")
    st = await go(store, world, budget=budget)
    assert st["credits"]["used"] <= budget
    assert store.conn.execute("SELECT COUNT(*) FROM ledger WHERE run_id=?", (st["run_id"],)).fetchone()[0] <= budget


async def test_too_few_reviews(tmp_path):
    w = World(seed_d_p=12, ring_size=0)
    st = await go(Store(tmp_path / "f.db"), w)
    assert st["state"] == "failed" and st["error"]["code"] == "E_TOO_FEW_REVIEWS" and st["credits"]["used"] == 1
