"""python -m nakshatra.cli <maps-url | data_id | place_id> [--budget N] [--offline] [--db PATH]

Runs one investigation end to end and prints the RunStatus JSON (result included when done).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from nakshatra.errors import NakshatraError
from nakshatra.orchestrator.run import run_once
from nakshatra.settings import load_config


def main(argv: list[str] | None = None) -> int:
    cfg = load_config()
    ap = argparse.ArgumentParser(prog="python -m nakshatra.cli", description=__doc__.splitlines()[0])
    ap.add_argument("place")
    ap.add_argument("--budget", type=int, default=cfg.budget.default)
    ap.add_argument("--offline", action="store_true", help="serve only from the local cache (0 network calls)")
    ap.add_argument("--db", default=None, help="SQLite path (default: $NAKSHATRA_DB or data/nakshatra.db)")
    args = ap.parse_args(argv)
    try:
        status = asyncio.run(run_once(args.place, args.budget, db=args.db, offline=args.offline, cfg=cfg))
    except NakshatraError as e:
        print(json.dumps({"error": {"code": e.code, "message": e.message}}), file=sys.stderr)
        return 2
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0 if status["state"] == "done" else 1


if __name__ == "__main__":
    sys.exit(main())
