"""Event bus: persist first, then fan out to live subscribers (LLD §7.1, API §4)."""
from __future__ import annotations

import asyncio

from nakshatra.store.db import Store

TERMINAL_EVENTS = ("done", "cancelled", "error")


class EventBus:
    def __init__(self, store: Store, run_id: str):
        self.store, self.run_id, self.seq = store, run_id, 0
        self.subs: set[asyncio.Queue] = set()
        self.closed = False

    def emit(self, etype: str, payload: dict) -> None:
        self.seq += 1
        self.store.event_append(self.run_id, self.seq, etype, payload)
        for q in list(self.subs):
            q.put_nowait((self.seq, etype, payload))
        if etype in TERMINAL_EVENTS:
            self.closed = True

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self.subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subs.discard(q)
