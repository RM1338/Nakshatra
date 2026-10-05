"""Ring guards (ALG §9.2): numbers that help a person read a ring correctly. They never gate reporting. Pure."""
from __future__ import annotations

import math
import re
from collections import Counter
from itertools import combinations
from statistics import median, pvariance

from nakshatra.algo.peel import Ring
from nakshatra.graph.model import Graph

COMPACT_KM = 2.0        # places this close together may be one neighbourhood's real community
VARIED_RATINGS = 0.5    # crews post near-uniform stars; genuine groups vary
BRAND_SHARE = 0.5       # share of ring places whose names contain the same distinctive word
STOPWORDS = frozenset("""the and for with best near shop store centre center hospital clinic restaurant cafe hotel
road street main place branch outlet showroom coimbatore bengaluru bangalore india private limited services service""".split())


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    (la1, lo1), (la2, lo2) = (tuple(map(math.radians, x)) for x in (a, b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def ring_guards(g: Graph, ring: Ring) -> dict:
    ratings = [g.edges[(u, p)].rating for u in ring.users for p in ring.places if (u, p) in g.edges]
    coords = [(g.places[p].lat, g.places[p].lng) for p in ring.places
              if g.places[p].lat is not None and g.places[p].lng is not None]
    spread = median(haversine_km(a, b) for a, b in combinations(coords, 2)) if len(coords) >= 2 else None
    words = Counter(w for p in ring.places
                    for w in {t for t in re.findall(r"[a-z]{4,}", (g.places[p].title or "").lower())} - STOPWORDS)
    brand = None
    if words:
        token, n = min(words.items(), key=lambda kv: (-kv[1], kv[0]))
        if n >= 2 and n / len(ring.places) >= BRAND_SHARE:
            brand = token
    return {"rating_variance": round(pvariance(ratings), 3) if len(ratings) >= 2 else None,
            "spread_km": None if spread is None else round(spread, 2), "brand_token": brand}


def guard_notes(guards: dict) -> list[str]:
    """User-facing notes (UF §6 copy)."""
    notes = []
    compact = guards["spread_km"] is not None and guards["spread_km"] <= COMPACT_KM
    varied = guards["rating_variance"] is not None and guards["rating_variance"] >= VARIED_RATINGS
    if compact and varied:
        notes.append(f"These places are within {max(guards['spread_km'], 0.1):.1f} km of each other and ratings vary. "
                     "This could be a real community, such as a college group.")
    elif compact:
        notes.append(f"These places are within {max(guards['spread_km'], 0.1):.1f} km of each other. "
                     "This could be a real community, such as a college group.")
    elif varied:
        notes.append("Ratings within this group vary. This could be a real community, such as a college group.")
    if guards["brand_token"]:
        notes.append("Most shared places belong to the same brand.")
    return notes
