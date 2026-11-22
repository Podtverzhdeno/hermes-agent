"""Offline, read-only merge-collision gate for concurrent Hermes GPT work.

Input is an explicit, reviewed JSON snapshot, not live GitHub access. The output
never instructs an automated merge. A clean file list alone is not integration
proof; CI evidence must match the exact candidate head SHA.

    python scripts/gpt_bridge_pr_collision_audit.py prs.json
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
    pass


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
    allowed_snapshot_keys = {"base_sha", "pull_requests", "required_checks"}
    if (not isinstance(snapshot, dict) or not {"base_sha", "pull_requests"} <= set(snapshot)
            or set(snapshot) - allowed_snapshot_keys):
        raise InvalidSnapshot("expected base_sha, pull_requests and optional required_checks")
    required_checks = snapshot.get("required_checks", [])
    if (not isinstance(required_checks, list) or len(required_checks) > 50
            or len(set(x for x in required_checks if isinstance(x, str))) != len(required_checks)):
        raise InvalidSnapshot("invalid required_checks policy")
    for name in required_checks:
        if not isinstance(name, str) or not (1 <= len(name) <= 80) or any(
                term in name.lower() for term in ("token", "secret", "authorization")):
            raise InvalidSnapshot("invalid required check name")
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
        check_status_by_name = defaultdict(list)
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
            state = "fresh_pass" if (
                c["head_sha"] == pr["head_sha"] and c["status"] == "completed"
                and c["conclusion"] == "success"
            ) else "not_a_fresh_pass"
            check_statuses.append(state)
            check_status_by_name[c["name"]].append(state)
        for filename in files:
            path_owners[filename].append(n)
        missing_required = sorted(name for name in required_checks if name not in check_status_by_name)
        required_ok = bool(required_checks) and not missing_required and all(
            all(status == "fresh_pass" for status in check_status_by_name[name])
            for name in required_checks
        )
        # A partial GitHub checks export must NEVER label the complete suite green.
        # required_checks is operator-supplied metadata, not a trusted branch policy.
        all_observed_green = bool(check_statuses) and all(
            status == "fresh_pass" for status in check_statuses
        )
        normalized[n] = {
            "head_sha": pr["head_sha"],
            "draft": pr["draft"],
            "stale_base": pr["base_sha"] != snapshot["base_sha"],
            "checks_ok": required_ok and all_observed_green,
            "observed_checks_all_success": all_observed_green,
            "required_checks_missing": missing_required,
            "required_checks_policy_provided": bool(required_checks),
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
    # Git paths are case-sensitive but Windows/NTFS worktrees usually are not.
    # Report potential aliases separately rather than pretending all Unicode
    # case folds reflect the exact target filesystem's normalization policy.
    by_casefold = defaultdict(set)
    for path, owners in path_owners.items():
        by_casefold[path.casefold()].add(path)
    for alias, variants in sorted(by_casefold.items()):
        if len(variants) < 2:
            continue
        all_owners = sorted({n for path in variants for n in path_owners[path]})
        if len(all_owners) < 2:
            continue
        collisions.append({"path": alias, "paths": sorted(variants),
                           "owners": all_owners, "severity": "high",
                           "reason": "POSSIBLE_WINDOWS_CASE_ALIAS"})
        for i, a in enumerate(all_owners):
            for b in all_owners[i + 1:]:
                edges.add((a, b))
    # File/directory prefix conflicts are distinct from exact-file conflicts.
    for path, owners in sorted(path_owners.items()):
        parts = path.split("/")
        for i in range(1, len(parts)):
            prefix = "/".join(parts[:i])
            if prefix not in path_owners:
                continue
            all_owners = sorted(set(owners + path_owners[prefix]))
            if len(all_owners) < 2:
                continue
            collisions.append({"path": prefix, "paths": [prefix, path],
                               "owners": all_owners, "severity": "high",
                               "reason": "FILE_DIRECTORY_PREFIX_CONFLICT"})
            for j, a in enumerate(all_owners):
                for b in all_owners[j + 1:]:
                    edges.add((a, b))
    collided = {n for c in collisions for n in c["owners"]}
    for n, entry in normalized.items():
        entry["collision_count"] = sum(n in c["owners"] for c in collisions)
        entry["requires_review"] = True  # even if every listed check passed
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
        "required_checks_policy": "operator_supplied_unverified",
        "required_checks_count": len(required_checks),
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
