"""Thin wrappers for the three engines Nakshatra uses (API Contract §8). Field shapes: DECISIONS C1-C5."""
from __future__ import annotations

from nakshatra.serp.budget import Token
from nakshatra.serp.client import Response, SerpClient

MAPS_PLACE_FIELDS = "place_results{data_id,place_id,title,type,rating,reviews,gps_coordinates}"
MAPS_SEARCH_FIELDS = "local_results{data_id,place_id,title,type,rating,reviews,gps_coordinates}"
REVIEWS_FIELDS = ("place_info,reviews{review_id,rating,iso_date,iso_date_of_last_edit,date,snippet,"
                  "user{contributor_id,reviews,photos,local_guide}},serpapi_pagination")
CONTRIB_FIELDS = ("contributor{level,points,local_guide,contributions},"
                  "reviews{review_id,rating,date,snippet,place_info{data_id,title,type,gps_coordinates,reviews}}")


def _r(c: SerpClient, p: dict, fields: str) -> dict:
    return {**p, "json_restrictor": fields} if c.restrict else p


async def maps_place(c: SerpClient, tok: Token, data_id: str | None = None, place_id: str | None = None) -> Response:
    p = {"type": "place", "place_id": place_id} if place_id else \
        {"type": "place", "data": f"!4m5!3m4!1s{data_id}!8m2!3d0!4d0"}  # DECISIONS C1: verify on T02
    return await c.get("google_maps", _r(c, p, MAPS_PLACE_FIELDS), tok)


async def maps_category(c: SerpClient, tok: Token, query: str, lat: float, lng: float) -> Response:
    return await c.get("google_maps", _r(c, {"type": "search", "q": query, "ll": f"@{lat},{lng},14z"},
                                         MAPS_SEARCH_FIELDS), tok)


async def place_reviews(c: SerpClient, tok: Token, data_id: str, sort_by: str, page_token: str | None) -> Response:
    p: dict = {"data_id": data_id, "sort_by": sort_by}
    if page_token:
        p |= {"next_page_token": page_token, "num": 20}  # first page returns 8 and rejects `num`
    return await c.get("google_maps_reviews", _r(c, p, REVIEWS_FIELDS), tok)


async def contributor_reviews(c: SerpClient, tok: Token, contributor_id: str) -> Response:
    return await c.get("google_maps_contributor_reviews",
                       _r(c, {"contributor_id": contributor_id, "num": 200}, CONTRIB_FIELDS), tok)
