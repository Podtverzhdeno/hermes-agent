#!/usr/bin/env python3
"""Read-only, fail-closed GPT/Hermes PR integration evidence gate.

This is a review aid, NEVER an authorizer for deployment, task execution or merge.
No GitHub write requests are made. No prompts, credentials or tool inputs are logged.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import PurePosixPath, Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
REF_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
HIGH_RISK = ("gateway/platforms/api_server.py", "pyproject.toml", "tools/approval.py",
             "tools/terminal_tool.py", "acp_adapter/permissions.py", "acp_adapter/server.py")
OBSERVER_FAMILIES = {"gpt_bridge/", "gpt_companion/", "hermes_gpt_bridge/"}
MAX_PAGES = 10


class EvidenceError(ValueError):
    """Malformed or incomplete review evidence; never interpreted as healthy."""


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise EvidenceError("Invalid repository-relative path")
    p = PurePosixPath(value)
    if p.is_absolute() or any(part in (".", "..") for part in value.split("/")):
        raise EvidenceError("Unsafe path in evidence")
    return value


def validate(snapshot: dict) -> None:
    if not isinstance(snapshot, dict) or snapshot.get("schema_version") != 1:
        raise EvidenceError("Expected schema_version=1 snapshot object")
    if not snapshot.get("complete"):
        raise EvidenceError("Partial PR/CI scan: cannot grant a clean result")
    if not isinstance(snapshot.get("repository"), str) or not REPO_RE.fullmatch(snapshot["repository"]):
        raise EvidenceError("Invalid repository identity")
    if not isinstance(snapshot.get("base_sha"), str) or not SHA_RE.fullmatch(snapshot["base_sha"]):
        raise EvidenceError("Missing exact base commit")
    if not isinstance(snapshot.get("prs"), list):
        raise EvidenceError("Missing PR inventory")
    seen = set()
    for pr in snapshot["prs"]:
        if not isinstance(pr, dict):
            raise EvidenceError("Invalid PR entry")
        number = pr.get("number")
        if type(number) is not int or number < 1 or number in seen:
            raise EvidenceError("Duplicate or invalid PR number")
        seen.add(number)
        if not isinstance(pr.get("head_sha"), str) or not SHA_RE.fullmatch(pr["head_sha"]):
            raise EvidenceError("Missing exact PR head SHA")
        if not isinstance(pr.get("head_ref"), str) or not REF_RE.fullmatch(pr["head_ref"]):
            raise EvidenceError("Invalid PR head ref")
        if not isinstance(pr.get("base_ref"), str) or not REF_RE.fullmatch(pr["base_ref"]):
            raise EvidenceError("Invalid PR base ref")
        if type(pr.get("draft")) is not bool:
            raise EvidenceError("PR draft status absent")
        if not isinstance(pr.get("files"), list) or not isinstance(pr.get("runs"), list):
            raise EvidenceError("Missing complete file or run inventory")
        paths = [_path(p) for p in pr["files"]]
        if len(set(paths)) != len(paths):
            raise EvidenceError("Duplicate changed-file entries")
        for run in pr["runs"]:
            if not isinstance(run, dict) or not isinstance(run.get("name"), str):
                raise EvidenceError("Malformed workflow-run record")
            if run.get("head_sha") != pr["head_sha"]:
                raise EvidenceError("Workflow run SHA does not match PR head")


def analyze(snapshot: dict, required_checks: tuple[str, ...] = ("Tests",)) -> dict:
    validate(snapshot)
    findings: list[dict] = []

    def add(code: str, subjects: list[int] | None, severity: str, detail: str, action: str):
        findings.append({"code": code, "prs": subjects or [], "severity": severity,
                         "detail": detail, "action": action})

    prs = sorted(snapshot["prs"], key=lambda x: x["number"])
    if snapshot.get("base_protected") is not True:
        add("BASE_UNPROTECTED_OR_UNKNOWN", None, "block",
            "Protected base branch was not verified; concurrent writes can bypass review.",
            "Require branch ruleset, independent review and exact-head CI before release.")

    refs = {p["head_ref"]: p["number"] for p in prs}
    file_owners: dict[str, list[int]] = {}
    observer_implementations: dict[str, list[int]] = {}

    for pr in prs:
        n = pr["number"]
        if pr["draft"]:
            add("PR_DRAFT", [n], "block", "Draft PR cannot be treated as release-ready.",
                "Wait for independent review and explicit ready-for-review transition.")
        if pr["base_ref"] != "main":
            parent = refs.get(pr["base_ref"])
            add("STACKED_BRANCH", [n] + ([parent] if parent else []), "block",
                f"PR base is {pr['base_ref']}, not main; downstream checks cannot authorize direct merge.",
                "Integrate parent first; refresh base and rerun checks on resulting commit.")
        latest_by_name: dict[str, dict] = {}
        for run in pr["runs"]:
            name = run["name"]
            rank = (int(run.get("run_number", 0)), int(run.get("run_attempt", 0)),
                    int(run.get("id", 0)))
            existing = latest_by_name.get(name)
            oldrank = (int(existing.get("run_number", 0)), int(existing.get("run_attempt", 0)),
                       int(existing.get("id", 0))) if existing else (-1, -1, -1)
            if rank >= oldrank:
                latest_by_name[name] = run
        for check in required_checks:
            run = latest_by_name.get(check)
            if run is None:
                add("CI_ABSENT", [n], "block", f"Missing required '{check}' workflow on head SHA.",
                    "Run required tests against exact PR head; do not count other workflows.")
            elif run.get("status") != "completed" or run.get("conclusion") != "success":
                add("CI_NOT_GREEN", [n], "block",
                    f"'{check}' status={run.get('status')}, conclusion={run.get('conclusion')}.",
                    "Inspect failing job and compare with baseline before promotion.")
        families = set()
        for path in pr["files"]:
            file_owners.setdefault(path, []).append(n)
            for prefix in OBSERVER_FAMILIES:
                if path.startswith(prefix):
                    families.add(prefix)
        for family in families:
            observer_implementations.setdefault(family, []).append(n)

    for path, owners in sorted(file_owners.items()):
        if len(owners) < 2:
            continue
        critical = path in HIGH_RISK or path.startswith("gateway/") or path.startswith("autopilot/")
        add("CRITICAL_FILE_COLLISION" if critical else "FILE_COLLISION", owners,
            "block" if critical else "review",
            f"Multiple open PRs modify {path}.",
            "Designate exactly one integration owner; reconcile by reviewed patch, not blind merging.")

    implementing = sorted({n for owners in observer_implementations.values() for n in owners})
    if len(observer_implementations) > 1:
        add("COMPETING_OBSERVER_PROTOCOLS", implementing, "block",
            "Several independent event/observer packages would produce incompatible diagnostics.",
            "Select one versioned event contract; others may be read-only adapters only.")

    order = {"block": 0, "review": 1, "info": 2}
    findings.sort(key=lambda x: (order.get(x["severity"], 9), x["code"], x["prs"]))
    return {"schema_version": 1, "repository": snapshot["repository"],
            "base_sha": snapshot["base_sha"], "captured_at_utc": snapshot.get("captured_at_utc"),
            "snapshot_sha256": hashlib.sha256(canonical_bytes(snapshot)).hexdigest(),
            "pr_count": len(prs), "scan_attempts": snapshot.get("scan_attempts", 1),
            "ready_for_merge": not any(f["severity"] == "block" for f in findings),
            "findings": findings,
            "disclaimer": "Read-only static evidence analysis, not proof of live browser/runtime health or authorization to merge."}


def _get_json(url: str, token: str | None) -> dict | list:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "hermes-gpt-pr-review-gate/1",
               "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=20) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        # No full URLs, token, response bodies or headers in logs.
        raise EvidenceError(f"GitHub evidence fetch failed ({type(exc).__name__})") from None


def _pages(url: str, token: str | None, key: str | None = None) -> list:
    result = []
    for page in range(1, MAX_PAGES + 1):
        join = "&" if "?" in url else "?"
        body = _get_json(f"{url}{join}per_page=100&page={page}", token)
        rows = body.get(key) if key else body
        if not isinstance(rows, list):
            raise EvidenceError("Malformed GitHub pagination result")
        result.extend(rows)
        if len(rows) < 100:
            return result
    raise EvidenceError("Pagination limit reached; refusing partial review")


def collect_live(repository: str, token: str | None) -> dict:
    if not REPO_RE.fullmatch(repository):
        raise EvidenceError("Bad owner/repo name")
    root = f"https://api.github.com/repos/{quote(repository, safe='/')}"
    branch = _get_json(root + "/branches/main", token)
    base = branch.get("commit", {}).get("sha")
    first_inventory = _pages(root + "/pulls?state=open", token)
    def inspect_pr(p):
        sha = p["head"]["sha"]
        paths = [f["filename"] for f in _pages(root + f"/pulls/{p['number']}/files", token)]
        raw_runs = _pages(root + "/actions/runs?head_sha=" + quote(sha), token, key="workflow_runs")
        runs = [{"name": r.get("name"), "status": r.get("status"),
                 "conclusion": r.get("conclusion"), "head_sha": r.get("head_sha"),
                 "run_number": r.get("run_number", 0), "run_attempt": r.get("run_attempt", 0),
                 "id": r.get("id", 0)} for r in raw_runs if r.get("head_sha") == sha]
        return {"number": p["number"], "head_sha": sha, "head_ref": p["head"]["ref"],
                "base_ref": p["base"]["ref"], "draft": bool(p["draft"]),
                "files": paths, "runs": runs}

    # Bound read-only concurrency reduces the duration of the non-atomic REST
    # scan when dozens of agents are pushing, without expanding privileges.
    if len(first_inventory) > 8:
        with ThreadPoolExecutor(max_workers=8) as pool:
            prs = list(pool.map(inspect_pr, first_inventory))
    else:
        prs = [inspect_pr(p) for p in first_inventory]
    # An agent may push while the scan is running. Mixed-time file lists are NOT
    # a reliable snapshot. The double-read cannot solve every GitHub race, but
    # it reliably detects ordinary PR additions, removals and head moves.
    second_inventory = _pages(root + "/pulls?state=open", token)
    final_branch = _get_json(root + "/branches/main", token)
    def inventory(items):
        return {p["number"]: (p["head"]["sha"], p["head"]["ref"],
                              p["base"]["ref"], bool(p["draft"])) for p in items}
    if inventory(first_inventory) != inventory(second_inventory):
        raise EvidenceError("PR inventory/head moved during scan: retry a fresh snapshot")
    if final_branch.get("commit", {}).get("sha") != base:
        raise EvidenceError("Base branch moved during scan: retry a fresh snapshot")
    return {"schema_version": 1, "repository": repository, "base_sha": base,
            "base_protected": branch.get("protected") is True,
            "complete": True, "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "prs": prs}


def collect_live_stable(repository: str, token: str | None, attempts: int = 3) -> dict:
    """Retry a torn READ snapshot, never a task or external side effect."""
    if not 1 <= attempts <= 5:
        raise EvidenceError("Snapshot attempt count must be between 1 and 5")
    for attempt in range(1, attempts + 1):
        try:
            snapshot = collect_live(repository, token)
            snapshot["scan_attempts"] = attempt
            return snapshot
        except EvidenceError as exc:
            if "moved during scan" not in str(exc) or attempt == attempts:
                raise
            print(f"EVIDENCE_RETRY attempt={attempt}/{attempts} reason=PR_OR_BASE_MOVED",
                  file=sys.stderr)
            time.sleep(0.25 * 2 ** (attempt - 1))
    raise EvidenceError("Unreachable snapshot retry path")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--snapshot", type=Path, help="Offline JSON evidence (no network)")
    source.add_argument("--live", metavar="OWNER/REPO", help="Read-only GitHub REST snapshot")
    parser.add_argument("--output", type=Path, help="Write JSON review report")
    parser.add_argument("--snapshot-output", type=Path, help="Write captured raw evidence")
    parser.add_argument("--required-check", action="append", default=[], help="Required workflow name")
    parser.add_argument("--strict", action="store_true", help="Exit 2 when blockers exist")
    parser.add_argument("--snapshot-attempts", type=int, default=3,
                        help="Bounded read-only rescan attempts after moving PR heads (1..5)")
    args = parser.parse_args(argv)
    try:
        snapshot = (collect_live_stable(args.live, os.getenv("GITHUB_TOKEN"),
                                        args.snapshot_attempts) if args.live else
                    json.loads(args.snapshot.read_text(encoding="utf-8")))
        report = analyze(snapshot, tuple(args.required_check or ["Tests"]))
        if args.snapshot_output:
            args.snapshot_output.write_bytes(canonical_bytes(snapshot) + b"\n")
        if args.output:
            args.output.write_bytes(canonical_bytes(report) + b"\n")
        print(f"PRs={report['pr_count']} blockers={sum(f['severity'] == 'block' for f in report['findings'])} "
              f"ready_for_merge={report['ready_for_merge']} snapshot_sha256={report['snapshot_sha256']}")
        for f in report["findings"]:
            print(f"{f['severity'].upper()} {f['code']} PRs={f['prs']} {f['detail']}")
        return 2 if args.strict and not report["ready_for_merge"] else 0
    except (EvidenceError, OSError, json.JSONDecodeError) as exc:
        print(f"EVIDENCE_UNKNOWN: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
