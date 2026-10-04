import json

import httpx
import pytest
import respx

from nakshatra.errors import NakshatraError
from nakshatra.serp.budget import Budget
from nakshatra.serp.client import SERP_URL, SerpClient, params_hash
from nakshatra.store.db import Store

KEY = "sk_test_9f8e7d6c5b4a"
OK = {"search_metadata": {"id": "s1", "status": "Success"},
      "reviews": [{"user": {"name": "Asha K", "contributor_id": "1", "thumbnail": "http://x/p.png"}}]}


async def nosleep(_):
    return None


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "c.db")
    s.run_create("r_0000000001", "x", 60, False, "{}", "h", 0.0)
    return s


def client(store, offline=False, key=KEY):
    b = Budget(60)
    return SerpClient(store, key, offline, "r_0000000001", b, sleep=nosleep), b


@respx.mock
async def test_cache_first_and_ledger(store):
    route = respx.get(SERP_URL).respond(200, json=OK)
    c, b = client(store)
    r1 = await c.get("google_maps_reviews", {"data_id": "0x1:0x2"}, b.reserve("sample"))
    r2 = await c.get("google_maps_reviews", {"data_id": "0x1:0x2"}, b.reserve("sample"))
    assert route.call_count == 1 and not r1.cached and r2.cached
    assert route.calls[0].request.url.params["hl"] == "en"
    assert (b.billed, b.cached) == (1, 1)
    assert store.ledger_totals("r_0000000001")["billed"] == 1


@respx.mock
async def test_pii_and_key_never_persisted(store):
    respx.get(SERP_URL).respond(200, json={**OK, "echo": f"https://serpapi.com/search?api_key={KEY}"})
    c, b = client(store)
    await c.get("google_maps_reviews", {"data_id": "0x1:0x2"}, b.reserve("sample"))
    dump = "\n".join(store.conn.iterdump())
    assert KEY not in dump and "Asha" not in dump and "p.png" not in dump
    assert '"contributor_id":"1"' in dump


@respx.mock
async def test_retry_then_success(store):
    route = respx.get(SERP_URL).mock(side_effect=[httpx.Response(429), httpx.Response(503), httpx.Response(200, json=OK)])
    c, b = client(store)
    r = await c.get("google_maps", {"q": "a"}, b.reserve("sample"))
    assert route.call_count == 3 and r.data["search_metadata"]["status"] == "Success"


@respx.mock
async def test_retries_exhausted(store):
    route = respx.get(SERP_URL).respond(500)
    c, b = client(store)
    with pytest.raises(NakshatraError) as e:
        await c.get("google_maps", {"q": "a"}, b.reserve("sample"))
    assert e.value.code == "E_UPSTREAM" and route.call_count == 4 and b.billed == 0


@respx.mock
async def test_401_is_auth(store):
    respx.get(SERP_URL).respond(401, json={"error": "Invalid API key."})
    c, b = client(store)
    with pytest.raises(NakshatraError) as e:
        await c.get("google_maps", {"q": "a"}, b.reserve("sample"))
    assert e.value.code == "E_AUTH"


@respx.mock
async def test_quota(store):
    respx.get(SERP_URL).respond(429, json={"error": "Your account has run out of searches."})
    c, b = client(store)
    with pytest.raises(NakshatraError) as e:
        await c.get("google_maps", {"q": "a"}, b.reserve("sample"))
    assert e.value.code == "E_QUOTA"


@respx.mock
async def test_non_success_not_cached(store):
    respx.get(SERP_URL).respond(200, json={"search_metadata": {"status": "Error"}, "error": "boom"})
    c, b = client(store)
    with pytest.raises(NakshatraError) as e:
        await c.get("google_maps", {"q": "a"}, b.reserve("sample"))
    assert e.value.code == "E_UPSTREAM"
    assert store.cache_get(params_hash("google_maps", {"hl": "en", "q": "a"})) is None
    assert store.ledger_totals("r_0000000001") == {"billed": 1, "cached": 0, "failed": 1, "by_pool": {"sample": 1}}


@respx.mock(assert_all_called=False)
async def test_offline_miss_makes_no_call(store):
    route = respx.get(SERP_URL).respond(200, json=OK)
    c, b = client(store, offline=True)
    with pytest.raises(NakshatraError) as e:
        await c.get("google_maps", {"q": "a"}, b.reserve("sample"))
    assert e.value.code == "E_CACHE_MISS" and route.call_count == 0


async def test_no_key_is_auth(store):
    c, b = client(store, key="")
    with pytest.raises(NakshatraError) as e:
        await c.get("google_maps", {"q": "a"}, b.reserve("sample"))
    assert e.value.code == "E_AUTH"


async def test_call_without_token_refused(store):
    c, _ = client(store)
    with pytest.raises(NakshatraError) as e:
        await c.get("google_maps", {"q": "a"}, None)
    assert e.value.code == "E_INTERNAL"


def test_hash_ignores_key_and_order():
    assert params_hash("e", {"a": 1, "b": 2, "api_key": "k"}) == params_hash("e", {"b": 2, "a": 1})
    assert len(params_hash("e", {})) == 64 and json.dumps({}) == "{}"
