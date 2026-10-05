"""T34 / M10 / SRS-NF-6: an exported demo DB replays offline to the same results, with no network and no key."""
import json
import shutil

import httpx
import pytest

from nakshatra.orchestrator.run import run_once
from nakshatra.settings import load_config
from nakshatra.store.check import violations
from nakshatra.store.db import Store
from nakshatra.store.export_demo import export
from tests.synth_world import NOW, World

KEY = "synthetic-replay-key-0123456789abcdef"


def stable(result):
    r = dict(result)
    r.pop("run_id"), r.pop("credits")
    return json.dumps(r, sort_keys=True, separators=(",", ":"))


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("demo")
    src = Store(tmp / "src.db")
    worlds = [World(), World(seed=8, ring_size=0)]
    runs = []
    for w in worlds:
        st = pytest.importorskip("asyncio").run(
            run_once(w.seed_data_id, 60, api_key=KEY, now=NOW, cfg=load_config(), store=src,
                     http=httpx.AsyncClient(transport=w.transport())))
        assert st["state"] == "done"
        runs.append((w, st))
    src.close()
    info = export(tmp / "src.db", tmp / "demo.db", [st["run_id"] for _, st in runs])
    return tmp, runs, info


def test_export_is_minimal_and_clean(demo):
    tmp, runs, info = demo
    blob = (tmp / "demo.db").read_bytes()
    assert info["bytes"] < 50 * 1024 * 1024 and KEY.encode() not in blob
    s = Store(tmp / "demo.db")
    assert all(not v for v in violations(s).values())
    assert {r[0] for r in s.conn.execute("SELECT run_id FROM runs")} == {st["run_id"] for _, st in runs}
    for (resp,) in s.conn.execute("SELECT response_json FROM serp_cache"):
        assert '"name"' not in resp and '"thumbnail"' not in resp
        assert all(v in ("", "[text removed]") for v in __import__("re").findall(r'"snippet":"([^"]*)"', resp))
    excerpts = s.conn.execute("SELECT COUNT(*) FROM edges WHERE excerpt IS NOT NULL").fetchone()[0]
    ring_edges = s.conn.execute("""SELECT COUNT(*) FROM v_ring_evidence v JOIN rings r USING (run_id, idx)
                                   WHERE r.reported = 1""").fetchone()[0]
    assert excerpts <= ring_edges


def test_offline_replay_matches(demo):
    tmp, runs, _ = demo
    shutil.copy(tmp / "demo.db", tmp / "replay.db")
    store = Store(tmp / "replay.db")
    for w, original in runs:
        before = w.calls
        st = pytest.importorskip("asyncio").run(
            run_once(w.seed_data_id, 60, offline=True, api_key="", now=NOW, cfg=load_config(), store=store,
                     http=httpx.AsyncClient(transport=w.transport())))
        assert st["state"] == "done" and st["credits"]["used"] == 0 and w.calls == before
        assert stable(st["result"]) == stable(original["result"])
    assert all(not v for v in violations(store).values())
