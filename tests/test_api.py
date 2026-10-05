"""Contract tests (API Contract §9.3) against the synthetic SerpApi; nothing leaves the process."""
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from nakshatra.api.main import create_app
from nakshatra.settings import Env, load_config
from nakshatra.store.db import Store
from tests.synth_world import NOW, World

W = World()
CODES = {"E_VALIDATION", "E_BAD_PLACE", "E_BUDGET", "E_RUN_ACTIVE", "E_RUN_TERMINAL", "E_RUN_NOT_DONE", "E_NOT_FOUND",
         "E_FORMAT", "E_PDF_UNAVAILABLE", "E_AUTH", "E_TOO_FEW_REVIEWS", "E_QUOTA", "E_UPSTREAM", "E_CACHE_MISS",
         "E_SCHEMA_DRIFT", "E_TRUNCATED", "E_INTERNAL"}


def client(tmp_path, key="synthetic-api-test-key", world=W):
    env = Env(_env_file=None, serpapi_api_key=key, nakshatra_db=tmp_path / "api.db")
    app = create_app(Store(tmp_path / "api.db"), load_config(), env,
                     lambda: {"http": httpx.AsyncClient(transport=world.transport()), "clock": lambda: NOW})
    return TestClient(app)


def wait_done(c, run_id, timeout=120):
    t = time.time()
    while time.time() - t < timeout:
        st = c.get(f"/api/v1/runs/{run_id}").json()
        if st["state"] in ("done", "failed", "cancelled"):
            return st
        time.sleep(0.2)
    raise AssertionError("run did not finish")


def assert_envelope(r, status, code):
    assert r.status_code == status, r.text
    body = r.json()
    assert set(body) == {"error"} and body["error"]["code"] == code and body["error"]["code"] in CODES
    assert isinstance(body["error"]["message"], str)


def sse(text):
    out = []
    for block in text.strip().split("\n\n"):
        f = dict(line.split(": ", 1) for line in block.splitlines() if not line.startswith(":"))
        if f:
            out.append((int(f["id"]), f["event"], json.loads(f["data"])))
    return out


@pytest.fixture(scope="module")
def done_run(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("api")
    with client(tmp) as c:
        r = c.post("/api/v1/runs", json={"place": W.seed_data_id, "budget": 60}, headers={"Idempotency-Key": "k1"})
        assert r.status_code == 201, r.text
        rid = r.json()["run_id"]
        again = c.post("/api/v1/runs", json={"place": W.seed_data_id}, headers={"Idempotency-Key": "k1"})
        assert again.status_code == 200 and again.json()["run_id"] == rid
        assert_envelope(c.post("/api/v1/runs", json={"place": W.seed_data_id}), 409, "E_RUN_ACTIVE")
        status = wait_done(c, rid)
        yield c, rid, status


def test_health(tmp_path):
    with client(tmp_path) as c:
        h = c.get("/api/v1/health").json()
        assert h["status"] == "ok" and h["schema_version"] == 2 and h["api_key_present"] and h["active_run"] is None


def test_errors(tmp_path):
    with client(tmp_path) as c:
        assert_envelope(c.post("/api/v1/runs", json={"place": "hello world"}), 400, "E_BAD_PLACE")
        assert_envelope(c.post("/api/v1/runs", json={"place": W.seed_data_id, "budget": 500}), 422, "E_BUDGET")
        assert_envelope(c.post("/api/v1/runs", json={"place": W.seed_data_id, "x": 1}), 422, "E_VALIDATION")
        assert_envelope(c.post("/api/v1/runs", json={}), 422, "E_VALIDATION")
        assert_envelope(c.get("/api/v1/runs/r_ffffffffff"), 404, "E_NOT_FOUND")
        assert_envelope(c.get("/api/v1/runs/r_ffffffffff/events"), 404, "E_NOT_FOUND")
        assert_envelope(c.get("/api/v1/nope"), 404, "E_NOT_FOUND")
        assert c.get("/api/v1/runs").json() == []


def test_missing_key_is_503(tmp_path):
    with client(tmp_path, key="") as c:
        assert_envelope(c.post("/api/v1/runs", json={"place": W.seed_data_id}), 503, "E_AUTH")


def test_run_result_and_alias(done_run):
    c, rid, st = done_run
    assert st["state"] == "done" and st["result"]["rings"] and st["credits"]["used"] <= 60
    assert c.get(f"/api/runs/{rid}").json()["run_id"] == rid  # /api alias
    assert c.get("/api/v1/runs").json()[0]["run_id"] == rid


def test_sse_replay_resume_and_pseudonyms(done_run):
    c, rid, _ = done_run
    ev = sse(c.get(f"/api/v1/runs/{rid}/events").text)
    assert [e[0] for e in ev] == list(range(1, len(ev) + 1))  # gapless, ordered
    assert ev[-1][1] == "done" and sum(e[1] in ("done", "error", "cancelled") for e in ev) == 1
    blob = json.dumps([e[2] for e in ev])
    assert not any(cid in blob for cid in W.ring_cids)
    users = [e[2]["id"] for e in ev if e[1] == "node" and e[2]["kind"] == "user"]
    assert users and all(u.startswith("S") for u in users)
    n = len(ev)
    tail = sse(c.get(f"/api/v1/runs/{rid}/events", headers={"Last-Event-ID": str(n - 5)}).text)
    assert [e[0] for e in tail] == list(range(n - 4, n + 1))
    assert [e[0] for e in sse(c.get(f"/api/v1/runs/{rid}/events?after={n - 2}").text)] == [n - 1, n]


def test_evidence_and_ledger(done_run):
    c, rid, st = done_run
    ring = st["result"]["rings"][0]
    ev = c.get(f"/api/v1/runs/{rid}/rings/0/evidence").json()
    assert ev["idx"] == 0 and len(ev["places"]) == len(ring["places"])
    members = {r["member"] for p in ev["places"] for r in p["reviews"]}
    assert members <= set(ring["members"]) and all(m.startswith("R") for m in members)
    assert_envelope(c.get(f"/api/v1/runs/{rid}/rings/9/evidence"), 404, "E_NOT_FOUND")
    led = c.get(f"/api/v1/runs/{rid}/ledger?limit=5").json()
    assert len(led["items"]) == 5 and led["next"] == led["items"][-1]["id"]
    assert led["totals"]["billed"] == st["credits"]["used"]
    assert "params_hash" not in json.dumps(led)


def test_offline_run_makes_no_calls(done_run, tmp_path):
    c, rid, _ = done_run
    before = W.calls
    r = c.post("/api/v1/runs", json={"place": W.seed_data_id, "offline": True})
    st = wait_done(c, r.json()["run_id"])
    assert st["state"] == "done" and st["credits"]["used"] == 0 and W.calls == before


def test_seed_failure_is_an_sse_error(tmp_path):
    w = World(seed_d_p=12, ring_size=0)
    with client(tmp_path, world=w) as c:
        rid = c.post("/api/v1/runs", json={"place": w.seed_data_id}).json()["run_id"]
        st = wait_done(c, rid)
        assert st["state"] == "failed" and st["error"]["code"] == "E_TOO_FEW_REVIEWS"
        ev = sse(c.get(f"/api/v1/runs/{rid}/events").text)
        assert ev[-1][1] == "error" and ev[-1][2]["code"] == "E_TOO_FEW_REVIEWS"
        assert_envelope(c.get(f"/api/v1/runs/{rid}/rings/0/evidence"), 409, "E_RUN_NOT_DONE")


def test_live_stream_is_gapless(tmp_path):
    """Subscribe while the run is active: history then live events, no gaps or duplicates, terminal last."""
    with client(tmp_path) as c:
        rid = c.post("/api/v1/runs", json={"place": W.seed_data_id, "budget": 30}).json()["run_id"]
        ev = sse(c.get(f"/api/v1/runs/{rid}/events").text)  # opened immediately; ends at the terminal event
        assert [e[0] for e in ev] == list(range(1, len(ev) + 1)) and ev[-1][1] == "done"
        assert len(ev) == c.get(f"/api/v1/runs/{rid}/events").text.count("\nevent: ")


def test_cancel_gives_partial_result(tmp_path):
    with client(tmp_path) as c:
        rid = c.post("/api/v1/runs", json={"place": W.seed_data_id, "budget": 60}).json()["run_id"]
        r = c.post(f"/api/v1/runs/{rid}/cancel")
        assert r.status_code == 202 and r.json()["run_id"] == rid
        st = wait_done(c, rid)
        assert st["state"] == "cancelled" and st["result"] is None
        assert st["partial"]["coverage"]["low_coverage"] and st["partial"]["state"] == "cancelled"
        assert st["credits"]["used"] < 60
        ev = sse(c.get(f"/api/v1/runs/{rid}/events").text)
        assert ev[-1][1] == "cancelled" and [e[0] for e in ev] == list(range(1, len(ev) + 1))
        assert_envelope(c.post(f"/api/v1/runs/{rid}/cancel"), 409, "E_RUN_TERMINAL")
        assert_envelope(c.post("/api/v1/runs/r_ffffffffff/cancel"), 404, "E_NOT_FOUND")
        assert c.get(f"/api/v1/runs/{rid}/rings/9/evidence").status_code == 404  # partial is readable


def test_dossier(done_run):
    c, rid, st = done_run
    r = c.get(f"/api/v1/runs/{rid}/dossier?format=md")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/markdown")
    assert f'nakshatra-{rid}.md' in r.headers["content-disposition"]
    md = r.text
    for h in ("## 1. Summary", "## 2. Seed place", "## 3. Method and parameters", "## 4. Coordinated groups",
              "## 5. Statistical evidence", "## 6. Credit ledger", "## 7. Limitations"):
        assert h in md
    assert "contributor IDs" in md.splitlines()[2]  # the reporting-only warning comes first
    ring = next(x for x in st["result"]["rings"] if x["reported"])
    shown = {line.split("|")[2].strip() for line in md.splitlines() if line.startswith("| R")
             and line.split("|")[2].strip().isdigit() and len(line.split("|")[2].strip()) > 15}
    assert len(shown) == len(ring["members"]) and len(shown & W.ring_cids) >= 8  # raw IDs only here, mapped right
    assert_envelope(c.get(f"/api/v1/runs/{rid}/dossier?format=docx"), 415, "E_FORMAT")
    pdf = c.get(f"/api/v1/runs/{rid}/dossier?format=pdf")
    assert (pdf.status_code == 200 and pdf.content[:4] == b"%PDF") or pdf.json()["error"]["code"] == "E_PDF_UNAVAILABLE"
