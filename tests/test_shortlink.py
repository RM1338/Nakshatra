"""Maps short share links (maps.app.goo.gl) expand to full URLs carrying the place ID; only redirects are read."""
import httpx
import pytest
import respx

from nakshatra.errors import NakshatraError
from nakshatra.orchestrator.run import parse_place
from nakshatra.serp.shortlink import expand, find_short_link

SHORT = "https://maps.app.goo.gl/ZZzxKG3Z3Mcsw3Me8"
FULL = ("https://www.google.com/maps/place/Karunya+Institute/@10.93,76.74,14.1z/data=!4m6!3m5!1s0x3ba866bd6aaaaaab:"
        "0xc650b8a75e7b51f0!8m2!3d10.936164!4d76.744061?entry=tts")  # shape observed Oct 5, 2026


def test_find_short_link():
    assert find_short_link(f"look at {SHORT} please") == SHORT
    assert find_short_link("https://goo.gl/maps/AbC123") == "https://goo.gl/maps/AbC123"
    assert find_short_link(FULL) is None and find_short_link("") is None


async def test_plain_input_untouched():
    assert await expand("0x1:0x2") == "0x1:0x2"


@respx.mock
async def test_expands_to_place_id():
    respx.get(SHORT).respond(302, headers={"location": FULL})
    url = await expand(SHORT)
    assert parse_place(url) == ("data_id", "0x3ba866bd6aaaaaab:0xc650b8a75e7b51f0")


@respx.mock
async def test_multi_hop_and_body_never_fetched():
    hop = "https://goo.gl/maps/next"
    respx.get(SHORT).respond(301, headers={"location": hop})
    respx.get(hop).respond(302, headers={"location": FULL})
    full = respx.get(FULL).respond(200, text="page body")
    assert await expand(SHORT) == FULL and full.call_count == 0


@respx.mock
async def test_refuses_foreign_redirects_and_dead_links():
    respx.get(SHORT).respond(302, headers={"location": "https://evil.example/maps/0x1:0x2"})
    with pytest.raises(NakshatraError) as e:
        await expand(SHORT)
    assert e.value.code == "E_BAD_PLACE"
    respx.get("https://maps.app.goo.gl/dead").respond(404)
    with pytest.raises(NakshatraError):
        await expand("https://maps.app.goo.gl/dead")
    respx.get("https://maps.app.goo.gl/down").mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(NakshatraError):
        await expand("https://maps.app.goo.gl/down")


async def test_offline_refuses_without_network():
    with pytest.raises(NakshatraError) as e:
        await expand(SHORT, offline=True)
    assert e.value.code == "E_BAD_PLACE" and "full Maps link" in e.value.message


def test_api_accepts_short_link(tmp_path):
    from tests.synth_world import World
    from tests.test_api import client, wait_done
    w = World()
    with respx.mock(assert_all_called=False) as m, client(tmp_path, world=w) as c:
        m.get("https://maps.app.goo.gl/synthetic1").respond(
            302, headers={"location": f"https://www.google.com/maps/place/x/data=!4m2!3m1!1s{w.seed_data_id}"})
        r = c.post("/api/v1/runs", json={"place": "https://maps.app.goo.gl/synthetic1"})
        assert r.status_code == 201, r.text
        assert r.json()["seed_data_id"] in (None, w.seed_data_id)
        st = wait_done(c, r.json()["run_id"])
        assert st["state"] == "done" and st["result"]["seed"]["data_id"] == w.seed_data_id
