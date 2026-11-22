#!/usr/bin/env python3
"""Offline metadata-only trace diagnosis. Example: python scripts/gpt_bridge_trace_doctor.py trace.jsonl"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

# Script execution from a checkout, without pip install.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hermes_gpt_bridge import TraceError, analyze, load_jsonl, summarize


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", help="JSONL of safe metadata-only events")
    parser.add_argument("--stale-after", type=int, default=120, help="seconds of collector silence")
    args = parser.parse_args(argv)
    try:
        events = load_jsonl(args.trace)
        findings = analyze(events, stale_after_seconds=args.stale_after)
        snapshots = summarize(events, stale_after_seconds=args.stale_after)
    except (TraceError, ValueError, OSError) as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps({"ok": not any(x.severity == "critical" for x in findings),
                      "runs": [x.as_dict() for x in snapshots],
                      "findings": [x.as_dict() for x in findings]}, ensure_ascii=False, indent=2))
    return 1 if any(x.severity == "critical" for x in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
