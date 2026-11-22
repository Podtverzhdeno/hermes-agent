#!/usr/bin/env python3
"""Offline read-only JSONL probe. Only counters, never input text, are printed.

Usage: python scripts/gpt_bridge_observe.py < trusted_metadata_events.jsonl
Not a native host, persistent monitor, daemon, or task-control API.
"""
from __future__ import annotations

from collections import Counter
import json
import sys
from pathlib import Path

# Permit invocation from a checked-out repository without an editable install.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gateway.gpt_bridge_observer import ReadOnlyEventObserver  # noqa: E402

MAX_LINE = 4096
MAX_RECORDS = 100_000


def _strict_json_object(pairs):
    """Reject duplicate JSON keys; JSON last-key-wins would mask an ingress attack."""
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate_json_key")
        out[key] = value
    return out


def main() -> int:
    observer = ReadOnlyEventObserver()
    counts: Counter[str] = Counter()
    total = 0
    while total < MAX_RECORDS:
        line = sys.stdin.buffer.readline(MAX_LINE + 2)
        if not line:
            break
        total += 1
        if len(line) > MAX_LINE + 1 or (len(line) == MAX_LINE + 1 and not line.endswith(b"\n")):
            counts["oversized_line"] += 1
            # Drain without accumulating untrusted bytes in memory.
            if not line.endswith(b"\n"):
                while True:
                    part = sys.stdin.buffer.readline(MAX_LINE + 2)
                    if not part or part.endswith(b"\n"):
                        break
            continue
        try:
            raw = json.loads(line, object_pairs_hook=_strict_json_object)
        except (ValueError, UnicodeDecodeError):
            counts["invalid_json"] += 1
            continue
        outcome = observer.ingest(raw)
        counts[outcome.code] += 1
    if total == MAX_RECORDS:
        counts["record_limit_reached"] += 1
    print(json.dumps({
        "records_seen": total,
        "outcomes": dict(sorted(counts.items())),
        "observer": observer.snapshot(),
        "limitations": [
            "advisory_only", "not_durable", "no_live_host_access",
            "no_worker_death_inference", "no_side_effect_replay",
        ],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
