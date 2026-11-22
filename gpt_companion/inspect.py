"""Offline Hermes/GPT event inbox inspection; no privileged/tool execution.

Usage: python -m gpt_companion --db ./events.sqlite3 --run-id run-1
To import a trusted local telemetry export first: add --jsonl path/to/events.jsonl.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from gpt_companion import EventJournal, JournalConflict


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect untrusted Hermes/GPT telemetry")
    parser.add_argument("--db", type=Path, required=True, help="Local SQLite event inbox")
    parser.add_argument("--run-id", required=True, help="Opaque run identifier")
    parser.add_argument("--jsonl", type=Path, help="Optional local event export to ingest")
    args = parser.parse_args(argv)
    try:
        journal = EventJournal(args.db)
        inserted = 0
        replayed = 0
        if args.jsonl is not None:
            with args.jsonl.open("r", encoding="utf-8") as f:
                for line_no, line in enumerate(f, 1):
                    if len(line) > 4096 or not line.strip():
                        raise JournalConflict(f"invalid or empty JSONL record at line {line_no}")
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        raise JournalConflict(f"invalid JSONL syntax at line {line_no}") from None
                    if journal.ingest(payload):
                        inserted += 1
                    else:
                        replayed += 1
        if not journal.verify_chain():
            print(json.dumps({"state": "JOURNAL_INTEGRITY_FAILED", "run_id": args.run_id}))
            return 3
        result = journal.assess(args.run_id)
        result["ingested"] = inserted
        result["replayed"] = replayed
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
        return 0
    except sqlite3.DatabaseError:
        # A corrupted/unreadable database is not an absent or failed worker.
        print(json.dumps({"state": "JOURNAL_INTEGRITY_FAILED"}), file=sys.stderr)
        return 3
    except (JournalConflict, OSError, ValueError) as exc:
        # Do not echo untrusted JSON payload or embedded secrets on failures.
        print(json.dumps({"state": "INSPECTION_REJECTED", "error_type": type(exc).__name__}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
