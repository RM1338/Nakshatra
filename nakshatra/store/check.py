"""Integrity check (Data Model §5.3). Prints violations; exit code = number of violating rows."""
from __future__ import annotations

import sys

from nakshatra.settings import Env
from nakshatra.store.db import Store

CHECKS = {
    "D2 credit totals agree": """
        SELECT r.run_id FROM runs r LEFT JOIN v_run_credits c USING (run_id)
        WHERE r.used <> COALESCE(c.billed, 0)""",
    "D5 edge lineage resolves": """
        SELECT e.contributor_id, e.data_id FROM edges e
        LEFT JOIN serp_cache s ON s.params_hash = e.source_hash
        WHERE s.params_hash IS NULL AND e.data_id NOT GLOB 'inj:*'""",
    "D6 gapless event sequence": """
        SELECT run_id FROM events GROUP BY run_id HAVING MAX(seq) <> COUNT(*)""",
    "D8 every done run has its result": """
        SELECT r.run_id FROM runs r LEFT JOIN results x USING (run_id)
        WHERE r.state = 'done' AND x.run_id IS NULL AND r.run_id <> 'r_0000000000'""",  # sentinel, API §5.4
    "D8b results only for finished runs": """
        SELECT r.run_id FROM runs r JOIN results x USING (run_id)
        WHERE r.state NOT IN ('done', 'cancelled', 'failed')""",
}


def violations(store: Store) -> dict[str, list[tuple]]:
    return {name: [tuple(r) for r in store.conn.execute(sql).fetchall()] for name, sql in CHECKS.items()}


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else Env().nakshatra_db
    bad = violations(Store(path))
    n = 0
    for name, rows in bad.items():
        print(f"{name}: {len(rows)}")
        for r in rows[:10]:
            print("   ", r)
        n += len(rows)
    return min(n, 255)


if __name__ == "__main__":
    sys.exit(main())
