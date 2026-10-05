"""Expand Maps short share links (maps.app.goo.gl/…) into full Maps URLs that carry the place ID.

Only redirect headers are read, never a page body, and redirects are followed only within Google hosts. This
costs no SerpApi credit. Offline mode makes no network calls, so short links are refused there.
"""
from __future__ import annotations

import re

import httpx

from nakshatra.errors import NakshatraError

SHORT = re.compile(r"https?://(?:maps\.app\.goo\.gl|goo\.gl/maps)/[A-Za-z0-9_-]+", re.I)
ALLOWED = re.compile(r"(^|\.)(goo\.gl|google\.[a-z.]+)$", re.I)
MAX_HOPS = 5
BAD = "Couldn't expand that short link. Open it in your browser and paste the full address instead."


def find_short_link(text: str) -> str | None:
    m = SHORT.search(text or "")
    return m.group(0) if m else None


async def expand(text: str, offline: bool = False, http: httpx.AsyncClient | None = None) -> str:
    """Return `text` unchanged unless it contains a short link; then return the expanded Maps URL."""
    url = find_short_link(text)
    if url is None:
        return text
    if offline:
        raise NakshatraError("E_BAD_PLACE", "Short links need the network. In offline mode, paste the full Maps link.")
    client = http or httpx.AsyncClient(timeout=httpx.Timeout(10.0))
    try:
        for _ in range(MAX_HOPS):
            r = await client.get(url, follow_redirects=False)
            loc = r.headers.get("location")
            if not r.is_redirect or not loc:
                break
            nxt = httpx.URL(url).join(loc)
            if not ALLOWED.search(nxt.host or ""):
                break
            url = str(nxt)
            if "goo.gl" not in nxt.host:
                return url
    except httpx.HTTPError as e:
        raise NakshatraError("E_BAD_PLACE", BAD) from e
    finally:
        if http is None:
            await client.aclose()
    raise NakshatraError("E_BAD_PLACE", BAD)
