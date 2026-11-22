#!/usr/bin/env python3
"""Opt-in read-only Hermes Autopilot observer (no external actions).

Usage:
  python scripts/autopilot_watch.py --db /path/to/autopilot.sqlite3 --once
  python scripts/autopilot_watch.py --db /path/to/autopilot.sqlite3 \
      --log /path/to/observer.jsonl --interval 15

Run under a system service/supervisor if continuous observation is required.
The script is NOT installed or started automatically.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autopilot.diagnostics import LedgerObserver  # noqa: E402


def safe_append_jsonl(path: Path, record: dict) -> None:
    """Append a single restricted-permission event; avoid symlink targets."""
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(str(path), flags, 0o600)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        payload = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        with os.fdopen(fd, "ab", closefd=False) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)


def observation(observer: LedgerObserver) -> dict:
    """Return one health/status snapshot without mutating a task."""
    try:
        result = observer.snapshot(limit=500)
        return {
            "kind": "observer.snapshot",
            "observed_at_epoch": result["observed_at_epoch"],
            "event_cursor": result["event_cursor"],
            "total_tasks": result["total_tasks"],
            "status_counts": result["status_counts"],
            "blocked": [
                {"task_id": t["task_id"], "reason_code": t["reason_code"]}
                for t in result["tasks"]
                if t["reason_code"] in (
                    "EXTERNAL_EFFECT_UNCERTAIN",
                    "WORKER_LEASE_EXPIRED_NOT_REAPED",
                    "APPROVAL_EXPIRED_NOT_REAPED",
                    "TRUSTED_VERIFICATION_FAILURE",
                    "ATTEMPTS_OR_HARD_FAILURE",
                    "BLOCKED_NEEDS_OPERATOR",
                    "CANCELLATION_PENDING",
                )
            ],
            "truncated": len(result["tasks"]) < result["total_tasks"],
        }
    except (OSError, ValueError, RuntimeError) as exc:
        # Error type only: exception strings may expose local paths or credentials.
        return {"kind": "observer.error", "observed_at_epoch": time.time(),
                "error_type": type(exc).__name__, "reason_code": "LEDGER_UNAVAILABLE"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--log", type=Path, help="optional local 0600 JSONL log")
    parser.add_argument("--interval", type=float, default=15.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.interval <= 3600:
        parser.error("interval must be between 1 and 3600 seconds")

    observer = LedgerObserver(args.db)
    last_fingerprint = None
    try:
        while True:
            result = observation(observer)
            fingerprint = json.dumps(
                {key: result.get(key) for key in
                 ("kind", "event_cursor", "status_counts", "blocked", "reason_code")},
                sort_keys=True,
            )
            # Emit on status/event change; an unchanged observer still emits a
            # heartbeat once each ~60 sec to make silent monitor death detectable.
            now = time.monotonic()
            if fingerprint != last_fingerprint or now - last_heartbeat >= 60 if last_fingerprint is not None else True:
                if args.log:
                    safe_append_jsonl(args.log, result)
                else:
                    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
                last_fingerprint = fingerprint
                last_heartbeat = now
            if args.once:
                return 0 if result["kind"] == "observer.snapshot" else 2
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
