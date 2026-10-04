"""Fixed explanation templates (SRS-RP-3) and the copy rule (SRS-NF-14, UF §7)."""
from __future__ import annotations

import re

BANNED = ("fake", "fraud", "scam", "fraudulent")
_BANNED_RE = re.compile(r"\b(" + "|".join(BANNED) + r")", re.I)

RING_TMPL = ("{n_users} accounts share {n_places} places that are unrelated to this business. "
             "By chance, two accounts here would share about {exp:.2f} of those places; "
             "these share {obs:.1f} on average.{lock}")
LOCK_TMPL = " At {lock_pct:.0f}% of those places, most of the accounts posted within {delta:.0f} days of each other."
VERDICT_TMPL = ("{n_users} accounts reviewed the same {n_places} unrelated places{timing}. Setting their reviews "
                "aside, the recent rating is {adj:.1f} ({lo:.1f}–{hi:.1f}).")
NONE_TMPL = ("No coordination detected. We followed {n_exp} reviewers across {n_places:,} places and found no group "
             "that shares places more than chance would explain.")
PHASE_LABELS = {
    "created": "Starting", "resolving": "Looking up the place", "sampling": "Reading recent reviews",
    "expanding": "Following reviewers", "refining": "Checking places they share",
    "mining": "Checking whether this could be chance", "reporting": "Checking whether this could be chance",
    "done": "Done", "failed": "Stopped", "cancelled": "Stopped early",
}


def check_copy(text: str) -> str:
    m = _BANNED_RE.search(text)
    if m:
        raise ValueError(f"banned word in copy: {m.group(0)!r}")
    return text
