#!/usr/bin/env python3
"""Read-only Hermes GPT local inbox status; optional operator-started polling."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hermes_gpt_bridge.report import SnapshotError, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db", help="existing local metadata-only SQLite inbox")
    parser.add_argument("--stale-after", type=int, default=120)
    parser.add_argument("--watch", action="store_true", help="poll while this local process stays running")
    parser.add_argument("--interval", type=float, default=15.0)
    args = parser.parse_args(argv)
    if not 1 <= args.interval <= 3600 or not 1 <= args.stale_after <= 86400:
        parser.error("invalid interval or stale-after value")
    prior = None
    try:
        while True:
            current = report(args.db, stale_after_seconds=args.stale_after)
            current["ok"] = not any(f["severity"] == "critical" for f in current["findings"])
            # Suppress unchanged snapshots. as_of is excluded from comparison
            # so an idle monitor does not produce an endless identical log.
            content = {k: v for k, v in current.items() if k != "as_of"}
            fingerprint = json.dumps(content, sort_keys=True)
            if not args.watch or fingerprint != prior:
                print(json.dumps(current, ensure_ascii=False), flush=True)
                prior = fingerprint
            if not args.watch:
                return 1 if not current["ok"] else 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0
    except (SnapshotError, OSError, ValueError) as exc:
        # Do not echo filesystem paths or raw payloads from a corrupt database.
        print(json.dumps({"ok": False, "error_code": type(exc).__name__}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
