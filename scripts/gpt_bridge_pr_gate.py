#!/usr/bin/env python3
"""Offline fail-closed review of a *snapshot* of concurrent GPT/Hermes PRs.

No network access, no shell execution, no PR changes. A PASS means only that
this structural snapshot has no detected integration blockers; it is NEVER
proof of deployed safety or authorization to merge.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any

_SHA = re.compile(r"^[0-9a-f]{40}$")
_BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
_RESERVED = {"api", "observer", "control_plane", "extension"}
_MAX_BYTES = 1_000_000
_MAX_PRS = 500
_MAX_FILES = 5000


class InvalidSnapshot(ValueError):
    """Schema invalid; no untrusted snapshot content is included in errors."""


def _sha(v: Any) -> bool:
    return isinstance(v, str) and bool(_SHA.fullmatch(v))


def _branch(v: Any) -> bool:
    return (isinstance(v, str) and bool(_BRANCH.fullmatch(v))
            and ".." not in v and "//" not in v and not v.endswith("/"))


def _path(v: Any) -> bool:
    return (isinstance(v, str) and 0 < len(v) <= 240
            and "\\" not in v and not v.startswith("/")
            and not any(x in {"", ".", ".."} for x in v.split("/"))
            and all(ord(c) >= 32 for c in v))


def _date(v: Any) -> datetime:
    if not isinstance(v, str) or len(v) > 40:
        raise InvalidSnapshot("invalid captured_at")
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidSnapshot("invalid captured_at") from exc
    if dt.tzinfo is None or dt.utcoffset() != timedelta(0):
        raise InvalidSnapshot("captured_at must be UTC")
    return dt.astimezone(timezone.utc)


def validate(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or set(data) != {
            "schema_version", "captured_at", "main_sha", "source_verification", "proposals", "decisions"}:
        raise InvalidSnapshot("invalid top-level snapshot fields")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise InvalidSnapshot("unsupported snapshot schema")
    _date(data["captured_at"])
    if not _sha(data["main_sha"]):
        raise InvalidSnapshot("invalid main_sha")
    ver = data["source_verification"]
    if not isinstance(ver, dict) or set(ver) != {"local_extension_verified", "live_monitor_connected"}:
        raise InvalidSnapshot("invalid source_verification")
    if any(type(v) is not bool for v in ver.values()):
        raise InvalidSnapshot("verification flags must be booleans")
    dec = data["decisions"]
    if not isinstance(dec, dict) or set(dec) != {"api_pr", "observer_pr", "control_plane"}:
        raise InvalidSnapshot("invalid decisions")
    if any(type(dec[k]) is not int and dec[k] is not None for k in ("api_pr", "observer_pr")):
        raise InvalidSnapshot("invalid canonical PR decisions")
    if dec["control_plane"] not in ("upstream_kanban", "prototype_ledger", None):
        raise InvalidSnapshot("unknown control plane decision")
    proposals = data["proposals"]
    if not isinstance(proposals, list) or not (1 <= len(proposals) <= _MAX_PRS):
        raise InvalidSnapshot("invalid proposal count")
    seen_prs, seen_heads = set(), set()
    for item in proposals:
        if not isinstance(item, dict) or set(item) != {"pr", "head", "head_sha", "base", "base_sha", "files", "domains", "draft"}:
            raise InvalidSnapshot("invalid proposal fields")
        n = item["pr"]
        if type(n) is not int or not (1 <= n <= 10000000) or n in seen_prs:
            raise InvalidSnapshot("invalid or repeated PR number")
        seen_prs.add(n)
        if not _branch(item["head"]) or not _branch(item["base"]) or item["head"] == item["base"]:
            raise InvalidSnapshot("invalid branch")
        if item["head"] in seen_heads:
            raise InvalidSnapshot("repeated head branch")
        seen_heads.add(item["head"])
        if not _sha(item["head_sha"]) or not _sha(item["base_sha"]):
            raise InvalidSnapshot("invalid commit SHA")
        if type(item["draft"]) is not bool:
            raise InvalidSnapshot("draft flag must be boolean")
        files = item["files"]
        if not isinstance(files, list) or len(files) > _MAX_FILES or any(not _path(f) for f in files) or len(set(files)) != len(files):
            raise InvalidSnapshot("invalid changed-files collection")
        dom = item["domains"]
        if not isinstance(dom, list) or not dom or len(dom) > 8 or any(not isinstance(d, str) or d not in _RESERVED | {"security", "skills", "docs", "tests"} for d in dom) or len(set(dom)) != len(dom):
            raise InvalidSnapshot("invalid domain collection")
    for k in ("api_pr", "observer_pr"):
        if dec[k] is not None and dec[k] not in seen_prs:
            raise InvalidSnapshot("canonical PR not found in snapshot")
    return data


def evaluate(data: dict[str, Any], *, now: datetime | None = None,
             freshness: timedelta = timedelta(hours=1)) -> dict[str, Any]:
    """Deterministic report. Findings contain opaque PR IDs and validated paths only."""
    validate(data)
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    captured = _date(data["captured_at"])
    findings: list[dict[str, Any]] = []

    def add(code: str, *, prs: tuple[int, ...] = (), path: str | None = None):
        item: dict[str, Any] = {"code": code}
        if prs:
            item["prs"] = list(prs)
        if path is not None:
            item["path"] = path
        findings.append(item)

    if captured > now + timedelta(minutes=5) or now - captured > freshness:
        add("SNAPSHOT_STALE_OR_FUTURE")
    if not data["source_verification"]["local_extension_verified"]:
        add("LOCAL_EXTENSION_UNVERIFIED")
    if not data["source_verification"]["live_monitor_connected"]:
        add("LIVE_MONITOR_UNAVAILABLE")

    proposals = sorted(data["proposals"], key=lambda p: p["pr"])
    by_head = {p["head"]: p for p in proposals}
    by_num = {p["pr"]: p for p in proposals}
    for p in proposals:
        if p["base"] == "main":
            if p["base_sha"] != data["main_sha"]:
                add("STALE_MAIN_BASE", prs=(p["pr"],))
        elif p["base"] not in by_head:
            add("UNKNOWN_STACK_PARENT", prs=(p["pr"],))
        elif p["base_sha"] != by_head[p["base"]]["head_sha"]:
            add("STALE_STACK_BASE", prs=(by_head[p["base"]]["pr"], p["pr"]))

    def ancestor(parent: dict, child: dict) -> bool:
        # Any cycle is handled separately; never exempt unknown parents.
        visited = set()
        cur = child
        while cur["base"] in by_head and cur["base"] not in visited:
            visited.add(cur["base"])
            cur = by_head[cur["base"]]
            if cur["pr"] == parent["pr"]:
                return True
        return False

    for p in proposals:
        seen = set()
        cur = p
        while cur["base"] in by_head:
            if cur["base"] in seen or cur["base"] == p["head"]:
                add("STACK_CYCLE", prs=(p["pr"],))
                break
            seen.add(cur["base"])
            cur = by_head[cur["base"]]

    for i, a in enumerate(proposals):
        for b in proposals[i+1:]:
            overlap = sorted(set(a["files"]) & set(b["files"]))
            for path in overlap:
                if ancestor(a, b) or ancestor(b, a):
                    add("STACKED_SHARED_PATH_REVIEW", prs=(a["pr"], b["pr"]), path=path)
                else:
                    add("FILE_OWNERSHIP_CONFLICT", prs=(a["pr"], b["pr"]), path=path)

    for domain in sorted(_RESERVED):
        owners = [p["pr"] for p in proposals if domain in p["domains"]]
        if len(owners) > 1:
            # Multiple proposals need a human canonical decision, even without path overlap.
            add("DUPLICATE_" + domain.upper() + "_PROPOSALS", prs=tuple(owners))

    dec = data["decisions"]
    for field, domain in (("api_pr", "api"), ("observer_pr", "observer")):
        chosen = dec[field]
        if chosen is None:
            add("CANONICAL_" + domain.upper() + "_UNDECIDED")
        elif domain not in by_num[chosen]["domains"]:
            add("CANONICAL_" + domain.upper() + "_MISMATCH", prs=(chosen,))
    if dec["control_plane"] is None:
        add("CONTROL_PLANE_UNDECIDED")

    # Do not allow any report to be interpreted as an authorization to merge.
    # A clean snapshot would still require external signatures, exact CI SHA,
    # privileged gateway checks, and explicit owner approval.
    blockers = [f for f in findings if f["code"] != "STACKED_SHARED_PATH_REVIEW"]
    return {
        "schema_version": 1,
        "status": "BLOCKED" if blockers else "STRUCTURAL_ONLY_NOT_APPROVED",
        "release_authorized": False,
        "snapshot_captured_at": data["captured_at"],
        "proposals_scanned": len(proposals),
        "findings": sorted(findings, key=lambda f: (f["code"], f.get("prs", []), f.get("path", ""))),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline Hermes GPT bridge PR collision gate (never merges)")
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--max-age-hours", type=float, default=1.0)
    parser.add_argument("--structural-only-ok", action="store_true",
                        help="Exit 0 for a collision-free snapshot; never authorizes release")
    args = parser.parse_args(argv)
    if not 0 < args.max_age_hours <= 168:
        parser.error("--max-age-hours must be in (0, 168]")
    try:
        if args.snapshot.stat().st_size > _MAX_BYTES:
            raise InvalidSnapshot("snapshot exceeds byte limit")
        data = json.loads(args.snapshot.read_text(encoding="utf-8"))
        result = evaluate(data, freshness=timedelta(hours=args.max_age_hours))
    except (OSError, UnicodeError, json.JSONDecodeError, InvalidSnapshot, RecursionError):
        print(json.dumps({"status": "INVALID_SNAPSHOT", "release_authorized": False}), file=sys.stdout)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    if result["status"] == "BLOCKED":
        return 1
    return 0 if args.structural_only_ok else 3


if __name__ == "__main__":
    raise SystemExit(main())