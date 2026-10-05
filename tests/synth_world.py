"""A deterministic synthetic SerpApi for tests and key-less development.

It models a small city: places with heavy-tailed global popularity, genuine reviewers who pick places by
popularity, and an optional planted ring that reviews the seed plus a set of obscure places within days of
each other, with camouflage edges to popular places. Responses follow the field shapes in API Contract §8
(DECISIONS C1-C5). This is fixture data, not a claim about real SerpApi output.

    python -m tests.synth_world --db data/nakshatra.db   # live-crawl the synthetic seeds into a DB
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import httpx
import numpy as np

DAY = 86400.0
NOW = 1_790_000_000.0  # fixed "now" of the synthetic world (2026-09-21)


def _rel(age_days: float) -> str:
    """Google's format: floor to whole units, calendar months and years (DECISIONS C6)."""
    if age_days < 1:
        return f"{max(1, int(age_days * 24))} hours ago"
    for unit, size, limit in (("day", 1, 7), ("week", 7, 30.44), ("month", 30.44, 365.25), ("year", 365.25, 1e9)):
        if age_days < limit:
            n = int(age_days // size)
            return f"a {unit} ago" if n == 1 else f"{n} {unit}s ago"
    raise AssertionError


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class World:
    seed: int = 7
    n_places: int = 2000
    n_users: int = 900
    n_seed_reviewers: int = 150
    ring_size: int = 10
    ring_places: int = 8
    camo: float = 0.3
    seed_d_p: int = 320
    places: list[dict] = field(default_factory=list)
    users: list[dict] = field(default_factory=list)
    reviews: dict[tuple[int, int], dict] = field(default_factory=dict)  # (user, place) -> {rating, t}
    ring_users: list[int] = field(default_factory=list)
    ring_place_idx: list[int] = field(default_factory=list)
    calls: int = 0

    def __post_init__(self) -> None:
        rng = np.random.default_rng(self.seed)
        types = ["Restaurant", "Hardware store", "Tile shop", "Pharmacy", "Temple", "Bakery", "Salon", "School"]
        for i in range(self.n_places):
            if i < 10:
                d_p, typ = int(rng.integers(3000, 6000)), "Temple"
            elif i < 160:
                d_p, typ = int(rng.integers(300, 800)), types[i % len(types)]
            else:
                d_p, typ = int(rng.integers(10, 150)), types[i % len(types)]
            self.places.append({
                "data_id": f"0x{self.seed:04x}{i:012x}:0x{(i * 7919 + 13):016x}", "title": f"Place {i}", "type": typ,
                "d_p": d_p, "rating": round(float(rng.uniform(3.6, 4.9)), 1),
                "lat": 11.0 + float(rng.uniform(-0.1, 0.1)), "lng": 76.95 + float(rng.uniform(-0.1, 0.1))})
        title = "Example Fertility Centre (synthetic city)" if self.ring_size else "Example Control Clinic (synthetic city)"
        seed = self._add_place(title, "Fertility clinic", self.seed_d_p, 4.8)
        for j in range(20):  # same-category neighbours for the baseline search
            self._add_place(f"Clinic {j}", "Fertility clinic", int(rng.integers(40, 900)),
                            round(float(rng.uniform(3.8, 4.7)), 1))
        self.seed_idx = seed

        pop = np.array([p["d_p"] for p in self.places[: self.n_places]], dtype=float)
        pop /= pop.sum()
        for _ in range(self.n_users):
            k = int(min(260, max(2, rng.lognormal(2.8, 1.0))))
            u = self._add_user(k, photos=int(rng.integers(0, 40)), local_guide=bool(rng.random() < 0.3))
            for p in rng.choice(self.n_places, size=min(k, self.n_places), replace=False, p=pop):
                self.reviews[(u, int(p))] = {"rating": float(rng.choice([3, 4, 4, 5, 5])),
                                             "t": NOW - float(rng.uniform(1, 900)) * DAY}
        for u in rng.choice(self.n_users, size=self.n_seed_reviewers, replace=False):
            self.reviews[(int(u), seed)] = {"rating": float(rng.choice([1, 3, 4, 4, 5, 5])),
                                            "t": NOW - float(rng.uniform(1, 400)) * DAY}

        if self.ring_size:
            obscure = [i for i in range(160, self.n_places) if self.places[i]["d_p"] < 45]
            self.ring_place_idx = [int(x) for x in rng.choice(obscure, size=self.ring_places, replace=False)]
            t0 = NOW - float(rng.uniform(40, 120)) * DAY
            for _ in range(self.ring_size):
                u = self._add_user(self.ring_places + 6, photos=0, local_guide=False)
                self.ring_users.append(u)
                self.reviews[(u, seed)] = {"rating": 5.0, "t": t0 + float(rng.uniform(0, 10)) * DAY}
                for p in self.ring_place_idx:
                    if rng.random() < 0.85:
                        self.reviews[(u, p)] = {"rating": 5.0, "t": t0 + float(rng.uniform(-30, 30)) * DAY}
                for p in range(10):  # camouflage: landmarks
                    if rng.random() < self.camo:
                        self.reviews[(u, p)] = {"rating": float(rng.choice([4, 5])), "t": NOW - 300 * DAY}

        self.by_place: dict[int, list[int]] = {}
        self.by_user: dict[int, list[int]] = {}
        for (u, p) in sorted(self.reviews):
            self.by_place.setdefault(p, []).append(u)
            self.by_user.setdefault(u, []).append(p)

    def _add_place(self, title: str, typ: str, d_p: int, rating: float) -> int:
        i = len(self.places)
        self.places.append({"data_id": f"0x{self.seed:04x}{i:012x}:0x{(i * 7919 + 13):016x}", "title": title, "type": typ,
                            "d_p": d_p, "rating": rating, "lat": 11.01, "lng": 76.96})
        return i

    def _add_user(self, k: int, photos: int, local_guide: bool) -> int:
        i = len(self.users)
        self.users.append({"cid": str(100000000000000000000 + self.seed * 10**12 + i * 7919), "k": k, "photos": photos, "lg": local_guide})
        return i

    @property
    def seed_data_id(self) -> str:
        return self.places[self.seed_idx]["data_id"]

    @property
    def ring_cids(self) -> set[str]:
        return {self.users[u]["cid"] for u in self.ring_users}

    # ---------- responses ----------
    def _place_json(self, p: int) -> dict:
        P = self.places[p]
        return {"data_id": P["data_id"], "title": P["title"], "type": P["type"], "rating": P["rating"],
                "reviews": P["d_p"], "gps_coordinates": {"latitude": P["lat"], "longitude": P["lng"]},
                "thumbnail": "https://example.invalid/photo.jpg"}

    def _place_info(self, p: int) -> dict:
        """Contributor feed place_info: no review count, as on real SerpApi (DECISIONS C3)."""
        P = self.places[p]
        return {"title": P["title"], "address": "Coimbatore", "type": P["type"], "data_id": P["data_id"],
                "gps_coordinates": {"latitude": P["lat"], "longitude": P["lng"]}}

    def _meta(self) -> dict:
        self.calls += 1
        return {"search_metadata": {"id": f"synth{self.calls:06d}", "status": "Success"}}

    def respond(self, q: dict[str, str]) -> dict:
        engine = q["engine"]
        if engine == "google_maps" and q.get("type") == "place":
            did = q["data"].split("!1s")[1].split("!")[0]
            idx = next((i for i, p in enumerate(self.places) if p["data_id"] == did), None)
            if idx is None:
                return {"search_metadata": {"status": "Error"}, "error": "Google hasn't returned any results"}
            return {**self._meta(), "place_results": self._place_json(idx)}
        if engine == "google_maps":
            hits = [i for i, p in enumerate(self.places) if p["type"] == q.get("q")][:20]
            return {**self._meta(), "local_results": [self._place_json(i) for i in hits]}
        if engine == "google_maps_reviews":
            p = next(i for i, x in enumerate(self.places) if x["data_id"] == q["data_id"])
            us = self.by_place.get(p, [])
            key = (lambda u: -self.reviews[(u, p)]["t"]) if q["sort_by"] == "newestFirst" else \
                (lambda u: (-self.reviews[(u, p)]["rating"], -self.reviews[(u, p)]["t"]))
            us = sorted(us, key=lambda u: (key(u), u))
            off = int(q["next_page_token"].split(":")[-1]) if q.get("next_page_token") else 0
            n = 8 if off == 0 else int(q.get("num", 10))
            page = us[off: off + n]
            out = {**self._meta(), "place_info": {"title": self.places[p]["title"], "reviews": self.places[p]["d_p"]},
                   "reviews": [self._review(u, p) for u in page]}
            if off == 0 and page:
                out["reviews"].append({"rating": 4, "snippet": "via another site", "source": "Trip.com"})  # B5
            if off + n < len(us):
                out["serpapi_pagination"] = {"next_page_token": f"{q['sort_by']}:{off + n}"}
            return out
        if engine == "google_maps_contributor_reviews":
            u = next(i for i, x in enumerate(self.users) if x["cid"] == q["contributor_id"])
            ps = sorted(self.by_user.get(u, []), key=lambda p: (-self.reviews[(u, p)]["t"], p))[:200]
            U = self.users[u]
            return {**self._meta(),
                    "contributor": {"name": f"Person {u}", "thumbnail": "https://example.invalid/me.jpg",
                                    "local_guide": U["lg"], "level": 5 if U["lg"] else None,
                                    "points": 1000 if U["lg"] else None, "contributions": {"reviews": U["k"]}},
                    "reviews": [{"rating": self.reviews[(u, p)]["rating"],
                                 "date": _rel((NOW - self.reviews[(u, p)]["t"]) / DAY),
                                 "snippet": f"review {u}-{p}", "review_id": f"rv{u}x{p}",
                                 "place_info": self._place_info(p)} for p in ps]}
        return {"search_metadata": {"status": "Error"}, "error": f"unknown engine {engine}"}

    def _review(self, u: int, p: int) -> dict:
        R, U = self.reviews[(u, p)], self.users[u]
        return {"rating": R["rating"], "date": _rel((NOW - R["t"]) / DAY), "iso_date": _iso(R["t"]),
                "snippet": f"review {u}-{p}", "review_id": f"rv{u}x{p}",
                "user": {"name": f"Person {u}", "link": "https://example.invalid/u", "thumbnail": "x",
                         "contributor_id": U["cid"], "reviews": U["k"], "photos": U["photos"],
                         "local_guide": U["lg"]}}

    def handler(self, request: httpx.Request) -> httpx.Response:
        q = {k: v[0] for k, v in parse_qs(urlparse(str(request.url)).query).items()}
        return httpx.Response(200, json=self.respond(q))

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


def _main() -> None:
    import argparse
    import asyncio
    import json

    from nakshatra.orchestrator.run import run_once

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/nakshatra.db")
    ap.add_argument("--budget", type=int, default=60)
    args = ap.parse_args()
    for name, w in (("ring", World()), ("control", World(seed=8, ring_size=0))):
        res = asyncio.run(run_once(w.seed_data_id, args.budget, db=args.db, api_key="synthetic-crawl-dummy-key-not-real",
                                   http=httpx.AsyncClient(transport=w.transport()), now=NOW))
        print(name, w.seed_data_id, json.dumps({k: res.get(k) for k in ("state", "error")}))


if __name__ == "__main__":
    _main()
