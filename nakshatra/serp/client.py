"""The only SerpApi adapter: cache-first, ledgered, budget-gated, retrying, offline-capable (LLD §4.2)."""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

from nakshatra.errors import NakshatraError
from nakshatra.serp.budget import Budget, Token
from nakshatra.store.db import Store

SERP_URL = "https://serpapi.com/search"
PII_KEYS = frozenset({"name", "link", "thumbnail", "images", "profile_link", "user_link"})  # DM §8
BACKOFF = (1.0, 2.0, 4.0)


def canonical_params(engine: str, params: dict) -> dict:
    canon = {k: v for k, v in params.items() if k != "api_key"}
    canon["engine"] = engine
    return canon


def params_hash(engine: str, params: dict) -> str:
    blob = json.dumps(canonical_params(engine, params), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def scrub(obj: Any) -> Any:
    """Drop names, profile links and photos before anything is persisted."""
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items() if k not in PII_KEYS}
    if isinstance(obj, list):
        return [scrub(v) for v in obj]
    return obj


def redact(obj: Any, secret: str) -> Any:
    """Replace the key inside string values; belt and braces, SerpApi does not echo it."""
    if isinstance(obj, dict):
        return {k: redact(v, secret) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v, secret) for v in obj]
    if isinstance(obj, str) and len(secret) >= 16 and secret in obj:  # real keys are 64 chars
        return obj.replace(secret, "REDACTED")
    return obj


def _quota(data: Any) -> bool:
    return isinstance(data, dict) and "run out of searches" in str(data.get("error", "")).lower()


@dataclass
class Response:
    data: dict
    cached: bool
    params_hash: str
    fetched_at: float  # reference time for relative dates in this response (DECISIONS B2)


class SerpClient:
    def __init__(self, store: Store, api_key: str, offline: bool, run_id: str, budget: Budget,
                 restrict: bool = False, clock: Callable[[], float] = time.time,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                 http: httpx.AsyncClient | None = None):
        self.store, self.api_key, self.offline, self.run_id = store, api_key, offline, run_id
        self.budget, self.restrict, self._sleep, self._clock = budget, restrict, sleep, clock
        self.http = http or httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))
        self.on_call: Callable[[], None] | None = None  # orchestrator hook: emit a `credit` event

    async def get(self, engine: str, params: dict, tok: Token) -> Response:
        if not isinstance(tok, Token):
            raise NakshatraError("E_INTERNAL", "SerpApi call without a budget reservation")
        params = {"hl": "en", **params}
        h = params_hash(engine, params)
        try:
            return await self._get(engine, params, h, tok)
        finally:
            if self.on_call:
                self.on_call()

    async def _get(self, engine: str, params: dict, h: str, tok: Token) -> Response:
        hit = self.store.cache_get(h)
        if hit is not None:
            self.budget.settle(tok, billed=False, cached=True)
            self.store.ledger_add(self.run_id, engine, h, tok.pool, True, False, True, 0)
            return Response(hit[0], True, h, hit[1])
        if self.offline:
            raise NakshatraError("E_CACHE_MISS", f"{engine} {h[:8]} is not in the offline cache")
        if not self.api_key:
            raise NakshatraError("E_AUTH", "no SerpApi key configured")

        t0 = time.perf_counter()
        q = {**params, "engine": engine, "api_key": self.api_key}
        last = "no response"
        for attempt in range(len(BACKOFF) + 1):
            try:
                r = await self.http.get(SERP_URL, params=q)
            except httpx.TransportError as e:
                last = type(e).__name__  # never the message: it can carry the URL with the key
            else:
                ms = int((time.perf_counter() - t0) * 1000)
                data = _json(r)
                if r.status_code == 401:
                    self._ledger_fail(engine, h, tok, ms)
                    raise NakshatraError("E_AUTH", "SerpApi rejected the key")
                if _quota(data):
                    self._ledger_fail(engine, h, tok, ms)
                    raise NakshatraError("E_QUOTA", "SerpApi plan quota exhausted")
                if r.status_code == 429 or r.status_code >= 500:
                    last = f"HTTP {r.status_code}"
                elif isinstance(data, dict):
                    ok = (data.get("search_metadata") or {}).get("status") == "Success"
                    self.budget.settle(tok, billed=True, cached=False)  # conservative: answered = billed
                    self.store.ledger_add(self.run_id, engine, h, tok.pool, False, True, ok, ms)
                    if not ok:
                        raise NakshatraError("E_UPSTREAM", f"{engine}: {str(data.get('error', 'not Success'))[:200]}")
                    clean = redact(scrub(data), self.api_key)
                    fetched = self._clock()
                    self.store.cache_put(h, engine, canonical_params(engine, params), clean, fetched)
                    return Response(clean, False, h, fetched)
                else:
                    last = f"HTTP {r.status_code} non-JSON"
            if attempt < len(BACKOFF):
                await self._sleep(BACKOFF[attempt])
        self._ledger_fail(engine, h, tok, int((time.perf_counter() - t0) * 1000))
        raise NakshatraError("E_UPSTREAM", f"{engine}: {last} after {len(BACKOFF)} retries")

    def _ledger_fail(self, engine: str, h: str, tok: Token, ms: int) -> None:
        self.budget.settle(tok, billed=False, cached=False)
        self.store.ledger_add(self.run_id, engine, h, tok.pool, False, False, False, ms)

    async def aclose(self) -> None:
        await self.http.aclose()


def _json(r: httpx.Response) -> Any:
    try:
        return r.json()
    except ValueError:
        return None
