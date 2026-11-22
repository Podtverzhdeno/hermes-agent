"""Read-only collision and CI freshness audit for concurrent Hermes agents.

This tool does NOT authorize a merge. Input JSON comes from a separate,
authenticated GitHub evidence adapter; untrusted snapshots are for planning only.

Run: python scripts/gpt_bridge_pr_collision_audit.py snapshot.json
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import sys
from typing import Any

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PATH_RE = re.compile(r"^[\w./+@() -]{1,256}$")
MAX_PRS = 250
MAX_FILES_PER_PR = 2000


class InvalidSnapshot(ValueError):
    """Snapshot is incomplete, malformed or not suitable as CI evidence."""


def _check_sha(value: Any) -> None:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise InvalidSnapshot("invalid SHA")


def _check_path(path: Any) -> None:
    if (not isinstance(path, str) or not PATH_RE.fullmatch(path)
        or path.startswith("/") or any(part in {".", ".."} for part in path.split("/"))):
        raise InvalidSnapshot("invalid file path")


def _severity(path: str) -> str:
    if path.startswith(("gateway/", "agent/", "acp_adapter/", "tools/", "autopilot/")):
        return "critical"
    if path.startswith("tests/"):
        return "high"
    if path.startswith("docs/") or path.endswith(".md"):
        return "medium"
    return "high"


def check_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Compute exact-file collisions and per-head CI evidence freshness."""
    if not isinstance(snapshot, dict) or set(snapshot) != {"base_sha", "pull_requests"}:
        raise InvalidSnapshot("expected base_sha and pull_requests")
    _check_sha(snapshot["base_sha"])
    prs = snapshot["pull_requests"]
    if not isinstance(prs, list) or len(prs) > MAX_PRS:
        raise InvalidSnapshot("invalid PR count")
    seen_numbers = set()
    normalized = {}
    path_owners = defaultdict(list)
    for pr in prs:
        if not isinstance(pr, dict) or set(pr) != {"number", "head_sha", "base_sha", "files", "draft", "checks"}:
            raise InvalidSnapshot("invalid PR record")
        n = pr["number"]
        if type(n) is not int or n < 1 or n in seen_numbers:
            raise InvalidSnapshot("invalid or duplicate PR number")
        seen_numbers.add(n)
        _check_sha(pr["head_sha"])
        _check_sha(pr["base_sha"])
        if type(pr["draft"]) is not bool:
            raise InvalidSnapshot("invalid draft")
        files = pr["files"]
        if not isinstance(files, list) or len(files) > MAX_FILES_PER_PR:
            raise InvalidSnapshot("invalid files list")
        for filename in files:
            _check_path(filename)
        if len(files) != len(set(files)):
            raise InvalidSnapshot("duplicate path within PR")
        checks = pr["checks"]
        if not isinstance(checks, list) or len(checks) > 100:
            raise InvalidSnapshot("invalid check list")
        check_statuses = []
        for c in checks:
            if not isinstance(c, dict) or set(c) != {"name", "head_sha", "status", "conclusion"}:
                raise InvalidSnapshot("invalid check")
            if (not isinstance(c["name"], str) or len(c["name"]) > 80 or not c["name"]
                    or any(term in c["name"].lower() for term in ("token", "secret", "authorization"))):
                raise InvalidSnapshot("invalid check name")
            _check_sha(c["head_sha"])
            if not isinstance(c["status"], str) or c["status"] not in {"queued", "in_progress", "completed"}:
                raise InvalidSnapshot("invalid check status")
            if c["conclusion"] is not None and (not isinstance(c["conclusion"], str) or c["conclusion"] not in {
                "success", "failure", "cancelled", "timed_out", "skipped", "neutral",
                "action_required", "startup_failure", "stale",
            }):
                raise InvalidSnapshot("invalid conclusion")
            check_statuses.append("fresh_pass" if (
                c["head_sha"] == pr["head_sha"] and c["status"] == "completed"
                and c["conclusion"] == "success"
            ) else "not_a_fresh_pass")
        for filename in files:
            path_owners[filename].append(n)
        normalized[n] = {
            "head_sha": pr["head_sha"],
            "draft": pr["draft"],
            "stale_base": pr["base_sha"] != snapshot["base_sha"],
            "checks_ok": bool(check_statuses) and all(x == "fresh_pass" for x in check_statuses),
            "checks_total": len(checks),
            "check_passes": check_statuses.count("fresh_pass"),
            "file_count": len(files),
        }
    collisions = []
    edges = set()
    for path, owners in sorted(path_owners.items()):
        if len(owners) > 1:
            owners = sorted(owners)
            collisions.append({"path": path, "owners": owners, "severity": _severity(path)})
            for i, a in enumerate(owners):
                for b in owners[i+1:]:
                    edges.add((a, b))
    collided = {n for c in collisions for n in c["owners"]}
    for n, entry in normalized.items():
        entry["collision_count"] = sum(n in c["owners"] for c in collisions)
        entry["requires_review"] = True
        entry["merge_gate"] = (
            "blocked_overlap" if n in collided else
            "blocked_stale_base" if entry["stale_base"] else
            "blocked_checks_or_draft" if (entry["draft"] or not entry["checks_ok"]) else
            "manual_review_still_required"
        )
    return {
        "schema_version": 1,
        "authority": "read_only_merge_diagnostic",
        "base_sha": snapshot["base_sha"],
        "pr_count": len(prs),
        "overlap_edges": [list(edge) for edge in sorted(edges)],
        "collisions": collisions,
        "pull_requests": {str(n): normalized[n] for n in sorted(normalized)},
        "automerge_allowed": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Hermes concurrent PR overlap and CI SHA gate")
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args(argv)
    if args.snapshot.stat().st_size > 2_000_000:
        parser.error("snapshot too large")
    try:
        result = check_snapshot(json.loads(args.snapshot.read_text(encoding="utf-8")))
    except (InvalidSnapshot, UnicodeDecodeError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    sys.stdout.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 2 if result["collisions"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
