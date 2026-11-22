"""Read-only, offline diagnostics for a Hermes/GPT observation SQLite file.

Usage: python -m gpt_bridge.cli --db /path/to/events.sqlite status TASK_ID
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .observability import EventValidationError, ObservationStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hermes/GPT observation diagnostics (read-only operations)")
    parser.add_argument("--db", type=Path, required=True, help="Local SQLite observation file")
    commands = parser.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status", help="Conservative task diagnosis")
    status.add_argument("task_id")
    status.add_argument("--stale-after", type=float, default=120.0)
    events = commands.add_parser("timeline", help="View recent sanitized events")
    events.add_argument("task_id")
    events.add_argument("--limit", type=int, default=50)
    commands.add_parser("integrity", help="Validate the local hash chain")
    args = parser.parse_args(argv)
    if not args.db.is_file():
        parser.error("database not found (nothing is created by diagnostic CLI)")
    store = ObservationStore(args.db, readonly=True)
    try:
        if args.command == "status":
            payload = store.diagnose_task(task_id=args.task_id, stale_after_seconds=args.stale_after)
        elif args.command == "timeline":
            payload = store.timeline(task_id=args.task_id, limit=args.limit)
        else:
            ok = store.verify_chain()
            payload = {"chain_intact": ok,
                       "warning": "Hash chaining does not prevent attacker-controlled database rewrites"}
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0 if ok else 2
    except EventValidationError as exc:
        parser.error(str(exc))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
