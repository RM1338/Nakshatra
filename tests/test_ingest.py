from nakshatra.graph.ingest import ingest_contributor, ingest_place, ingest_place_reviews
from nakshatra.graph.model import Edge, Graph
from tests.synth_world import NOW, World

W = World()


def test_place_reviews_skip_non_google_and_exact_dates():
    g = Graph()
    resp = W.respond({"engine": "google_maps_reviews", "data_id": W.seed_data_id, "sort_by": "newestFirst"})
    d = ingest_place_reviews(g, W.seed_data_id, resp, NOW, "h" * 64)
    assert len(d.users) == 8 and d.skipped == 1
    assert all(g.edges[k].exact for k in d.edges)
    assert g.places[g.pix[W.seed_data_id]].d_p == W.seed_d_p


def test_place_and_contributor():
    g = Graph()
    p, d = ingest_place(g, W.respond({"engine": "google_maps", "type": "place",
                                      "data": f"!4m5!3m4!1s{W.seed_data_id}!8m2!3d0!4d0"}))
    assert g.places[p].d_p == W.seed_d_p and not d.drift
    heavy = max(range(len(W.users)), key=lambda u: len(W.by_user.get(u, [])))
    cid = W.users[heavy]["cid"]
    d = ingest_contributor(g, cid, W.respond({"engine": "google_maps_contributor_reviews", "contributor_id": cid}),
                           NOW, "h" * 64)
    U = g.users[g.uix[cid]]
    assert U.expanded and U.truncated == (len(W.by_user[heavy]) >= 200)
    assert len(d.edges) == min(200, len(W.by_user[heavy]))
    assert all(not g.edges[k].exact for k in d.edges)
    assert all(g.places[p].d_p is None for p in d.new_places if p != g.pix.get(W.seed_data_id))


def test_missing_fields_are_drift_not_errors():
    g = Graph()
    p, d = ingest_place(g, {})
    assert p is None and d.drift
    d = ingest_contributor(g, "5", {"reviews": [{"rating": 5, "place_info": {"data_id": "0x1:0x2"}}, {"rating": 4}]},
                           NOW, "")
    assert d.skipped == 1 and not d.drift


def test_merge_rule():
    g = Graph()
    u, p = g.user("1"), g.place("0x1:0x2")
    assert g.add_edge(Edge(u, p, 5, 0, 100, False)) == "new"
    assert g.add_edge(Edge(u, p, 5, 0, 200, False)) is None
    assert g.add_edge(Edge(u, p, 5, 10, 50, False)) == "upgraded"
    assert g.add_edge(Edge(u, p, 5, 30, 30, True)) == "upgraded"
    assert g.add_edge(Edge(u, p, 5, 40, 40, True)) is None
    assert g.edges[(u, p)].t_lo == 30


# ---------- real SerpApi shapes (tests/fixtures/serpapi, minimised; DECISIONS C) ----------
def _fx(name):
    import json
    from pathlib import Path
    return json.loads((Path(__file__).parent / "fixtures/serpapi" / f"{name}.json").read_text())


def test_real_place_type_list_and_counts():
    g = Graph()
    p, d = ingest_place(g, _fx("maps_place"))
    P = g.places[p]
    assert isinstance(P.type, str) and P.d_p and P.lat and not d.drift


def test_real_reviews_pages():
    g = Graph()
    for name in ("reviews_page1", "reviews_page2"):
        resp = _fx(name)
        did = "0x1:0x1"
        d = ingest_place_reviews(g, did, resp, 1_791_000_000.0, "h" * 64)
        assert d.users and all(g.edges[k].exact for k in d.edges)
        assert all(g.users[u].k_u is not None for u in d.users)
    assert len(_fx("reviews_page1")["reviews"]) == 8 and len(_fx("reviews_page2")["reviews"]) == 20  # C5


def test_real_contributor_has_no_d_p():
    g = Graph()
    d = ingest_contributor(g, "1", _fx("contributor"), 1_791_000_000.0, "h" * 64)
    assert d.edges and not d.drift
    assert all(g.places[p].d_p is None for p in d.places)  # DECISIONS C3
    assert all(not g.edges[k].exact and g.edges[k].t_lo > 0 for k in d.edges)


def test_real_search_results():
    from nakshatra.graph.ingest import ingest_search
    base = ingest_search(_fx("maps_search"))
    assert len(base) == 20 and all(b.get("reviews") is not None for b in base)
