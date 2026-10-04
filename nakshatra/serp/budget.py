"""Credit budget: the single choke point for SerpApi spend (LLD §4.1, DECISIONS B1).

Every call, cached or live, consumes one reservation, so a run's control flow is identical live and on
replay. `billed` counts only live calls SerpApi answered. Invariant: billed <= calls <= total.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

POOLS = ("sample", "expand", "refine")


@dataclass(frozen=True)
class Token:
    pool: str


@dataclass
class Budget:
    total: int
    split: tuple[float, float, float] = (0.20, 0.65, 0.15)
    calls: int = 0
    billed: int = 0
    cached: int = 0
    remaining: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        s = math.ceil(round(self.total * self.split[0], 9))  # round: 60 * 0.2 is 12.000000000000002
        e = math.floor(round(self.total * self.split[1], 9))
        self.remaining = {"sample": s, "expand": e, "refine": self.total - s - e}

    def reserve(self, pool: str) -> Token | None:
        if self.remaining[pool] <= 0 or self.calls >= self.total:
            return None
        self.remaining[pool] -= 1
        self.calls += 1
        return Token(pool)

    def settle(self, tok: Token, *, billed: bool, cached: bool) -> None:
        self.billed += int(billed)
        self.cached += int(cached)

    def rollover(self, src: str, dst: str) -> None:
        self.remaining[dst] += self.remaining[src]
        self.remaining[src] = 0

    def left(self, *pools: str) -> int:
        return sum(self.remaining[p] for p in (pools or POOLS))
