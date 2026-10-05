"""Build the shipped offline-replay database (Data Model §8 retention).

    python -m nakshatra.store.export_demo --out data/demo.db --runs r_x r_y ...

Copies only the listed runs: their runs/ledger/events/rings/results/run_members rows, the cache rows their
ledger references, and the users, places and edges they touched. Cached responses are minimised (review text,
reviews embedded in place lookups, contact details removed; names and photos were never cached). VACUUM, then
refuse to ship if the file exceeds 50 MB or contains the API key.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

from nakshatra.settings import Env
from nakshatra.store.db import Store

MAX_BYTES = 50 * 1024 * 1024
DROP_KEYS = frozenset({"extracted_snippet", "translated_snippet", "user_reviews", "details", "response",
                       "phone", "website", "booking_link", "address"})
TEXT_KEYS = frozenset({"snippet"})  # review text: the words go, the fact that there was text stays (health checks)
TEXT_PLACEHOLDER = "[text removed]"
KEY_PATTERN = re.compile(rb"api_key=[0-9a-f]{32,}", re.I)


def minimise(obj):
    if isinstance(obj, dict):
        return {k: (TEXT_PLACEHOLDER if v else v) if k in TEXT_KEYS else minimise(v)
                for k, v in obj.items() if k not in DROP_KEYS}
    if isinstance(obj, list):
        return [minimise(v) for v in obj]
    return obj


def export(src: Path, out: Path, run_ids: list[str], append: bool = False) -> dict:
    if out.exists() and not append:
        out.unlink()
    Store(out).close()  # schema v2 (no-op when appending)
    dst = sqlite3.connect(out)
    dst.execute("ATTACH DATABASE ? AS src", (str(src),))  # only read from
    marks = ",".join("?" * len(run_ids))
    missing = set(run_ids) - {r[0] for r in dst.execute(f"SELECT run_id FROM src.runs WHERE run_id IN ({marks})", run_ids)}
    if missing:
        raise SystemExit(f"unknown runs: {sorted(missing)}")
    with dst:
        for t in ("runs", "events", "rings", "results", "run_members"):
            dst.execute(f"INSERT INTO main.{t} SELECT * FROM src.{t} WHERE run_id IN ({marks})", run_ids)
        cols = "run_id, engine, params_hash, pool, cached, billed, ok, latency_ms, ts"  # fresh ids: sources collide
        dst.execute(f"INSERT INTO main.ledger ({cols}) SELECT {cols} FROM src.ledger WHERE run_id IN ({marks})"
                    " ORDER BY id", run_ids)
        rows = dst.execute(
            f"SELECT * FROM src.serp_cache WHERE params_hash IN (SELECT params_hash FROM src.ledger WHERE run_id IN ({marks}))",
            run_ids).fetchall()
        for h, eng, params, resp, sid, fetched in rows:
            dst.execute("INSERT OR IGNORE INTO main.serp_cache VALUES (?,?,?,?,?,?)",
                        (h, eng, params, json.dumps(minimise(json.loads(resp)), separators=(",", ":")), sid, fetched))
        dst.execute(f"""INSERT OR IGNORE INTO main.places SELECT * FROM src.places WHERE data_id IN
                        (SELECT node_id FROM src.run_members WHERE kind='place' AND run_id IN ({marks}))""", run_ids)
        dst.execute(f"""INSERT OR IGNORE INTO main.users SELECT * FROM src.users WHERE contributor_id IN
                        (SELECT node_id FROM src.run_members WHERE kind='user' AND run_id IN ({marks}))""", run_ids)
        dst.execute("""INSERT OR IGNORE INTO main.edges SELECT * FROM src.edges e
                       WHERE e.contributor_id IN (SELECT contributor_id FROM main.users)
                         AND e.data_id IN (SELECT data_id FROM main.places)""")
        # Excerpts only for reported-ring members' ring-place edges (DM §8).
        dst.execute("""UPDATE main.edges SET excerpt = NULL WHERE NOT EXISTS (
                         SELECT 1 FROM main.v_ring_evidence v JOIN main.rings r USING (run_id, idx)
                         WHERE r.reported = 1 AND v.contributor_id = edges.contributor_id AND v.data_id = edges.data_id)""")
    dst.execute("DETACH DATABASE src")
    dst.execute("PRAGMA journal_mode = DELETE")  # single self-contained file
    dst.execute("VACUUM")
    dst.close()
    blob = out.read_bytes()
    key = Env().serpapi_api_key
    if (key and key.encode() in blob) or KEY_PATTERN.search(blob):
        out.unlink()
        raise SystemExit("refusing to export: the API key pattern appears in the database")
    if len(blob) > MAX_BYTES:
        out.unlink()
        raise SystemExit(f"refusing to export: {len(blob)} bytes exceeds the 50 MB limit")
    return {"runs": len(run_ids), "cache_rows": len(rows), "bytes": len(blob)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", default=None, help="source DB (default $NAKSHATRA_DB)")
    ap.add_argument("--out", default="data/demo.db")
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--append", action="store_true", help="add to an existing demo DB (e.g. runs from another source)")
    a = ap.parse_args(argv)
    print(export(Path(a.src or Env().nakshatra_db), Path(a.out), a.runs, a.append))
    return 0


if __name__ == "__main__":
    sys.exit(main())
