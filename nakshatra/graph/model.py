"""In-memory bipartite graph with dense indices (LLD §5.2, DM §7). Pure."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Place:
    data_id: str
    title: str | None = None
    type: str | None = None
    lat: float | None = None
    lng: float | None = None
    rating: float | None = None
    d_p: int | None = None  # global review count
    place_id: str | None = None


@dataclass
class User:
    contributor_id: str
    k_u: int | None = None
    photos: int | None = None
    local_guide: bool = False
    level: int | None = None
    points: int | None = None
    expanded: bool = False
    truncated: bool = False


@dataclass
class Edge:
    u: int
    p: int
    rating: float
    t_lo: float
    t_hi: float
    exact: bool
    review_id: str | None = None
    snippet: str = ""
    source_hash: str = ""


@dataclass
class Graph:
    users: list[User] = field(default_factory=list)
    places: list[Place] = field(default_factory=list)
    uix: dict[str, int] = field(default_factory=dict)
    pix: dict[str, int] = field(default_factory=dict)
    edges: dict[tuple[int, int], Edge] = field(default_factory=dict)
    uadj: list[set[int]] = field(default_factory=list)  # user -> places
    padj: list[set[int]] = field(default_factory=list)  # place -> users

    def user(self, cid: str) -> int:
        if cid not in self.uix:
            self.uix[cid] = len(self.users)
            self.users.append(User(cid))
            self.uadj.append(set())
        return self.uix[cid]

    def place(self, data_id: str) -> int:
        if data_id not in self.pix:
            self.pix[data_id] = len(self.places)
            self.places.append(Place(data_id))
            self.padj.append(set())
        return self.pix[data_id]

    def add_edge(self, e: Edge) -> str | None:
        """Merge rule (DM §5.1): exact beats relative, narrower beats wider. Returns 'new', 'upgraded' or None."""
        key = (e.u, e.p)
        old = self.edges.get(key)
        if old is None:
            self.edges[key] = e
            self.uadj[e.u].add(e.p)
            self.padj[e.p].add(e.u)
            return "new"
        old.review_id = old.review_id or e.review_id
        old.snippet = old.snippet or e.snippet
        if (e.exact and not old.exact) or (not e.exact and not old.exact and e.t_hi - e.t_lo < old.t_hi - old.t_lo):
            old.t_lo, old.t_hi, old.exact, old.source_hash = e.t_lo, e.t_hi, e.exact, e.source_hash
            return "upgraded"
        return None

    def reviewers_of(self, p: int) -> list[int]:
        return sorted(self.padj[p])

    def places_of(self, u: int) -> list[int]:
        return sorted(self.uadj[u])
