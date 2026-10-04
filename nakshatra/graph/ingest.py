"""Normalise SerpApi JSON into the graph (LLD §5.3). Pure; reads with .get() and defaults (API §8.5)."""
from __future__ import annotations

from dataclasses import dataclass, field

from nakshatra.graph.dates import parse_interval
from nakshatra.graph.model import Edge, Graph

CONTRIB_CAP = 200


@dataclass
class Delta:
    """What one response changed, so the orchestrator can persist and emit exactly that."""
    users: list[int] = field(default_factory=list)       # touched, in response order
    new_users: list[int] = field(default_factory=list)
    places: list[int] = field(default_factory=list)
    new_places: list[int] = field(default_factory=list)
    edges: list[tuple[int, int]] = field(default_factory=list)  # new or upgraded
    skipped: int = 0                                     # reviews without contributor_id / rating / place
    drift: list[str] = field(default_factory=list)       # missing expected fields


def _int(x) -> int | None:
    try:
        return int(x) if x is not None else None
    except (TypeError, ValueError):
        return None


def _touch_place(g: Graph, d: Delta, data_id: str) -> int:
    new = data_id not in g.pix
    p = g.place(data_id)
    if new:
        d.new_places.append(p)
    if p not in d.places:
        d.places.append(p)
    return p


def _touch_user(g: Graph, d: Delta, cid: str) -> int:
    new = cid not in g.uix
    u = g.user(cid)
    if new:
        d.new_users.append(u)
    d.users.append(u)
    return u


def apply_place(g: Graph, d: Delta, info: dict) -> int | None:
    did = info.get("data_id")
    if not did:
        return None
    p = _touch_place(g, d, did)
    pl = g.places[p]
    pl.title = info.get("title") or pl.title
    pl.type = info.get("type") or pl.type
    pl.place_id = info.get("place_id") or pl.place_id
    gps = info.get("gps_coordinates") or {}
    pl.lat = gps.get("latitude", pl.lat)
    pl.lng = gps.get("longitude", pl.lng)
    pl.rating = info.get("rating", pl.rating)
    pl.d_p = _int(info.get("reviews")) if info.get("reviews") is not None else pl.d_p
    return p


def ingest_place(g: Graph, resp: dict) -> tuple[int | None, Delta]:
    d = Delta()
    pr = resp.get("place_results") or {}
    p = apply_place(g, d, pr)
    if p is None:
        d.drift.append("place_results.data_id")
    elif pr.get("reviews") is None:
        d.drift.append("place_results.reviews")
    return p, d


def ingest_place_reviews(g: Graph, data_id: str, resp: dict, T: float, source_hash: str) -> Delta:
    """Reviews of one place. Skips non-Google reviews (no contributor_id). Seen users are in `d.users`."""
    d = Delta()
    p = _touch_place(g, d, data_id)
    pi = resp.get("place_info") or {}
    if g.places[p].d_p is None and pi.get("reviews") is not None:
        g.places[p].d_p = _int(pi.get("reviews"))
    for r in resp.get("reviews") or []:
        usr = r.get("user") or {}
        cid, rating = usr.get("contributor_id"), r.get("rating")
        if not cid or rating is None:
            d.skipped += 1
            continue
        u = _touch_user(g, d, str(cid))
        U = g.users[u]
        U.k_u = _int(usr.get("reviews")) if usr.get("reviews") is not None else U.k_u
        U.photos = _int(usr.get("photos")) if usr.get("photos") is not None else U.photos
        U.local_guide = U.local_guide or bool(usr.get("local_guide"))
        lo, hi, exact = parse_interval(r.get("iso_date") or r.get("date"), T)
        if g.add_edge(Edge(u, p, float(rating), lo, hi, exact, r.get("review_id"),
                           (r.get("snippet") or "")[:280], source_hash)):
            d.edges.append((u, p))
    return d


def ingest_contributor(g: Graph, cid: str, resp: dict, T: float, source_hash: str) -> Delta:
    d = Delta()
    u = _touch_user(g, d, cid)
    U = g.users[u]
    c = resp.get("contributor") or {}
    U.level = _int(c.get("level")) if c.get("level") is not None else U.level
    U.points = _int(c.get("points")) if c.get("points") is not None else U.points
    U.local_guide = U.local_guide or bool(c.get("local_guide"))
    k = (c.get("contributions") or {}).get("reviews")
    U.k_u = _int(k) if k is not None else U.k_u
    reviews = resp.get("reviews") or []
    U.expanded = True
    U.truncated = U.truncated or len(reviews) >= CONTRIB_CAP
    missing_dp = 0
    for r in reviews:
        pi = r.get("place_info") or {}
        if r.get("rating") is None or not pi.get("data_id"):
            d.skipped += 1
            continue
        p = apply_place(g, d, pi)
        missing_dp += pi.get("reviews") is None
        lo, hi, exact = parse_interval(r.get("date"), T)
        if g.add_edge(Edge(u, p, float(r["rating"]), lo, hi, exact, r.get("review_id"),
                           (r.get("snippet") or "")[:280], source_hash)):
            d.edges.append((u, p))
    if missing_dp:
        d.drift.append("place_info.reviews")
    return d


def ingest_search(resp: dict) -> list[dict]:
    """Baseline category search: places with a rating (not added to the graph)."""
    return [r for r in (resp.get("local_results") or []) if r.get("rating") is not None and r.get("data_id")][:20]
