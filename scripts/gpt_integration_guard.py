"""Read-only, fail-closed GitHub PR integration audit for Hermes/GPT.

No tool execution, branch mutation, secret logging or success attestation.
Example: python scripts/gpt_integration_guard.py --repo Podtverzhdeno/hermes-agent
         python scripts/gpt_integration_guard.py --snapshot snapshot.json --journal audit.sqlite
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_CODE_EXT = (".py", ".js", ".ts", ".tsx", ".mjs", ".cjs", ".json", ".toml", ".yaml", ".yml")
# Based on this fork's .github/workflows/tests.yml and supply-chain-audit.yml.
# This is a repository-specific evidence policy, not a generic GitHub default.
_REQUIRED_CHECKS = frozenset({"test", "Scan PR for supply chain risks"})
_OPTIONAL_SKIPPED = frozenset({"build-and-push"})
_OBSERVERS = {
    "gpt_bridge/observability.py",
    "hermes_gpt_bridge/diagnostics.py",
    "gpt_companion/journal.py",
    "autopilot/diagnostics.py",
    "gateway/gpt_bridge_diagnostics.py",
}


class IncompleteScan(Exception):
    """Evidence is missing; never convert this into a clean result."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward an authentication header to an unexpected redirect target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_SAFE_OPENER = urllib.request.build_opener(_NoRedirect)


def _get_json(repo: str, path: str, token: str | None) -> Any:
    if not _REPO.fullmatch(repo):
        raise ValueError("Invalid owner/repository selector")
    # path is built exclusively by the collector, not accepted from input.
    url = f"https://api.github.com/repos/{repo}/{path}"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "hermes-gpt-integration-guard/1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with _SAFE_OPENER.open(req, timeout=15) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        # Do not print token, request headers, full response or provider payload.
        raise IncompleteScan(f"GitHub API HTTP {exc.code} during read-only collection") from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise IncompleteScan(f"GitHub API unavailable ({type(exc).__name__})") from None


def collect(repo: str, token: str | None = None, max_prs: int = 100) -> dict[str, Any]:
    """Bounded, read-only snapshot; abort if pagination cannot be proven complete."""
    if not _REPO.fullmatch(repo):
        raise ValueError("Invalid owner/repository selector")
    if not 1 <= max_prs <= 1000:
        raise ValueError("max_prs must be 1..1000")
    baseline = _get_json(repo, "branches/main", token)
    prs: list[dict[str, Any]] = []
    page = 1
    while True:
        batch = _get_json(repo, f"pulls?state=open&per_page=100&page={page}", token)
        if not isinstance(batch, list):
            raise IncompleteScan("Unexpected pull request listing schema")
        if len(prs) + len(batch) > max_prs:
            raise IncompleteScan("Open PR count exceeds configured scan limit")
        for item in batch:
            n = item["number"]
            # GitHub's LIST /pulls payload omits changed_files; fetch the detail.
            detail = _get_json(repo, f"pulls/{n}", token)
            if (detail["head"]["sha"] != item["head"]["sha"]
                    or detail["base"]["sha"] != item["base"]["sha"]):
                raise IncompleteScan(f"PR {n}: revision changed during initial scan")
            total_files = detail["changed_files"]
            if not isinstance(n, int) or not 0 <= total_files <= 3000:
                raise IncompleteScan("PR metadata or GitHub file-list boundary unsupported")
            files = []
            file_page = 1
            while True:
                part = _get_json(repo, f"pulls/{n}/files?per_page=100&page={file_page}", token)
                if not isinstance(part, list):
                    raise IncompleteScan("Unexpected PR file-list schema")
                files.extend(p["filename"] for p in part)
                if len(part) < 100:
                    break
                file_page += 1
                if file_page > 30:
                    raise IncompleteScan("GitHub truncates PR file list at 3000")
            if len(files) != total_files:
                raise IncompleteScan(f"PR {n}: file list incomplete; cannot certify no overlap")
            # The list of PRs and their file diffs are not one atomic GitHub API read.
            # Refuse a snapshot if the exact PR head/base changed mid-inspection.
            fresh = _get_json(repo, f"pulls/{n}", token)
            if (fresh["head"]["sha"] != item["head"]["sha"]
                    or fresh["base"]["sha"] != item["base"]["sha"]
                    or fresh["changed_files"] != total_files):
                raise IncompleteScan(f"PR {n}: revision changed during scan")
            head_sha = item["head"]["sha"]
            try:
                checks = _get_json(repo, f"commits/{head_sha}/check-runs?per_page=100", token)
                if not isinstance(checks, dict) or checks.get("total_count", 0) > 100:
                    raise IncompleteScan("Check-run list requires pagination")
                ci = [{"name": r.get("name"), "status": r.get("status"),
                       "conclusion": r.get("conclusion"), "head_sha": r.get("head_sha")}
                      for r in checks.get("check_runs", [])]
            except IncompleteScan:
                ci = None  # Evidence unavailable is different from green.
            prs.append({"number": n, "head": item["head"]["ref"], "head_sha": head_sha,
                        "base": item["base"]["ref"], "base_sha": item["base"]["sha"],
                        "draft": item.get("draft", False), "files": sorted(files),
                        "changed_files": total_files, "checks": ci})
        if len(batch) < 100:
            break
        page += 1
        if page > 10:
            raise IncompleteScan("PR listing exceeds supported pagination")
    # Re-read the whole open-PR collection; GitHub list pagination is not
    # atomic and an agent may open/move a PR while files are being collected.
    final_index: dict[int, tuple[str, str, str, str]] = {}
    final_page = 1
    while True:
        final_batch = _get_json(repo, f"pulls?state=open&per_page=100&page={final_page}", token)
        if not isinstance(final_batch, list):
            raise IncompleteScan("Final PR listing malformed")
        for item in final_batch:
            n = item["number"]
            if n in final_index:
                raise IncompleteScan("Duplicate PR in final listing")
            final_index[n] = (item["head"]["sha"], item["base"]["sha"],
                              item["head"]["ref"], item["base"]["ref"])
        if len(final_index) > max_prs:
            raise IncompleteScan("Final PR count exceeds configured scan limit")
        if len(final_batch) < 100:
            break
        final_page += 1
        if final_page > 10:
            raise IncompleteScan("Final PR listing exceeds supported pagination")
    first_index = {p["number"]: (p["head_sha"], p["base_sha"], p["head"], p["base"])
                   for p in prs}
    if len(first_index) != len(prs) or final_index != first_index:
        raise IncompleteScan("Open PR set or revisions changed during scan")
    latest_main = _get_json(repo, "branches/main", token)
    if latest_main["commit"]["sha"] != baseline["commit"]["sha"]:
        raise IncompleteScan("Main HEAD changed during the scan")
    return {"schema_version": 1, "repository": repo, "baseline_sha": baseline["commit"]["sha"],
            "main_protected": baseline.get("protected"), "prs": prs}


def _issue(code: str, severity: str, prs: list[int] | None = None,
           paths: list[str] | None = None) -> dict[str, Any]:
    return {"code": code, "severity": severity, "prs": prs or [], "paths": paths or []}


def evaluate(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Conservative static review. No missing data may yield a clean result."""
    issues: list[dict[str, Any]] = []
    if snapshot.get("schema_version") != 1 or not _REPO.fullmatch(str(snapshot.get("repository", ""))):
        raise IncompleteScan("Invalid snapshot schema or repository")
    if not _SHA.fullmatch(str(snapshot.get("baseline_sha", ""))):
        raise IncompleteScan("Missing exact baseline SHA")
    prs = snapshot.get("prs")
    if not isinstance(prs, list) or len(prs) > 1000:
        raise IncompleteScan("Missing or excessive PR list")
    seen_numbers: set[int] = set()
    by_head: dict[str, dict[str, Any]] = {}
    normalized = []
    for pr in prs:
        if not isinstance(pr, dict) or type(pr.get("number")) is not int or pr["number"] < 1:
            raise IncompleteScan("Invalid PR entry")
        n = pr["number"]
        if n in seen_numbers:
            raise IncompleteScan("Duplicate PR number")
        seen_numbers.add(n)
        if not _SHA.fullmatch(str(pr.get("head_sha", ""))) or not _SHA.fullmatch(str(pr.get("base_sha", ""))):
            raise IncompleteScan(f"PR {n}: missing exact head/base SHA")
        if not isinstance(pr.get("head"), str) or not isinstance(pr.get("base"), str):
            raise IncompleteScan(f"PR {n}: invalid ref")
        files = pr.get("files")
        if (not isinstance(files, list) or not all(isinstance(f, str) and f and len(f) < 4096 for f in files)
                or len(files) != len(set(files)) or pr.get("changed_files") != len(files)):
            raise IncompleteScan(f"PR {n}: incomplete or duplicated file list")
        if pr["head"] in by_head:
            raise IncompleteScan("Ambiguous head branch; cannot prove ownership")
        by_head[pr["head"]] = pr
        normalized.append(pr)
        checks = pr.get("checks", "absent")
        if checks is None or checks == "absent" or not isinstance(checks, list) or not checks:
            issues.append(_issue("CI_UNVERIFIED", "high", [n]))
        else:
            if not all(isinstance(c, dict) and c.get("head_sha") == pr["head_sha"]
                       and isinstance(c.get("name"), str) for c in checks):
                issues.append(_issue("CI_EVIDENCE_SHA_MISMATCH", "high", [n]))
                continue
            names = {c["name"] for c in checks}
            if not _REQUIRED_CHECKS.issubset(names):
                issues.append(_issue("REQUIRED_CI_MISSING", "high", [n]))
            bad = [c for c in checks if not (
                c.get("status") == "completed" and (
                    c.get("conclusion") == "success" or
                    (c.get("conclusion") == "skipped" and c["name"] in _OPTIONAL_SKIPPED)
                )
            )]
            if bad:
                issues.append(_issue("CI_NOT_GREEN_AT_EXACT_HEAD", "high", [n]))
    if snapshot.get("main_protected") is False:
        issues.append(_issue("MAIN_UNPROTECTED", "high"))
    if type(snapshot.get("main_protected")) is not bool:
        issues.append(_issue("MAIN_PROTECTION_UNVERIFIED", "medium"))
    observers: dict[int, list[str]] = {}
    for pr in normalized:
        matches = sorted(set(pr["files"]) & _OBSERVERS)
        if matches:
            observers[pr["number"]] = matches
        parent = by_head.get(pr["base"])
        if parent and pr["base_sha"] != parent["head_sha"]:
            issues.append(_issue("STACKED_BASE_STALE", "critical", [parent["number"], pr["number"]]))
    if len(observers) > 1:
        issues.append(_issue("DUPLICATE_OBSERVER_DESIGNS", "high", sorted(observers),
                             sorted(p for values in observers.values() for p in values)))
    for i, left in enumerate(normalized):
        for right in normalized[i + 1:]:
            common = sorted(set(left["files"]) & set(right["files"]))
            if not common:
                continue
            stacked = left["base"] == right["head"] or right["base"] == left["head"]
            code = "STACKED_PATH_OVERLAP" if stacked else "PARALLEL_PATH_OVERLAP"
            critical = any(p.endswith(_CODE_EXT) for p in common)
            severity = "critical" if critical else "medium"
            issues.append(_issue(code, severity, sorted([left["number"], right["number"]]), common))
    issues.sort(key=lambda i: ({"critical": 0, "high": 1, "medium": 2}[i["severity"]],
                               i["code"], i["prs"], i["paths"]))
    return {"schema_version": 1, "repository": snapshot["repository"],
            "baseline_sha": snapshot["baseline_sha"], "observed_prs": len(normalized),
            "status": "BLOCKED" if any(i["severity"] in ("critical", "high") for i in issues) else "REVIEW",
            "issues": issues, "statement": "Static review only; no deployment, runtime health or safe merge certified."}


def journal(path: str, report: dict[str, Any]) -> bool:
    """Metadata-only, concurrent-safe, append-only SQLite audit snapshot."""
    payload = json.dumps(report, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    db = sqlite3.connect(path, timeout=15, isolation_level=None)
    try:
        db.execute("PRAGMA busy_timeout=15000")
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE IF NOT EXISTS audit_snapshots ("
                   "seq INTEGER PRIMARY KEY AUTOINCREMENT, received_utc TEXT NOT NULL, "
                   "digest TEXT NOT NULL UNIQUE, payload TEXT NOT NULL)")
        db.execute("BEGIN IMMEDIATE")
        cur = db.execute("INSERT OR IGNORE INTO audit_snapshots "
                         "(received_utc, digest, payload) VALUES (?, ?, ?)",
                         (datetime.now(timezone.utc).isoformat(), digest, payload))
        db.execute("COMMIT")
        return bool(cur.rowcount)
    except Exception:
        if db.in_transaction:
            db.execute("ROLLBACK")
        raise
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--repo", help="Read-only GitHub API collection: owner/name")
    mode.add_argument("--snapshot", type=Path, help="Offline snapshot JSON")
    parser.add_argument("--journal", type=Path, help="Optional metadata-only SQLite journal")
    parser.add_argument("--max-prs", type=int, default=100)
    args = parser.parse_args(argv)
    try:
        snapshot = (json.loads(args.snapshot.read_text(encoding="utf-8")) if args.snapshot
                    else collect(args.repo, os.environ.get("GITHUB_TOKEN"), args.max_prs))
        report = evaluate(snapshot)
        if args.journal:
            report["journal_recorded"] = journal(str(args.journal), report)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 2 if report["status"] == "BLOCKED" else 0
    except (IncompleteScan, ValueError, OSError, json.JSONDecodeError, sqlite3.Error) as exc:
        # Never emit request headers, exception payloads or raw response bodies.
        print(json.dumps({"status": "UNKNOWN", "reason_code": "EVIDENCE_INCOMPLETE",
                          "detail": str(exc) if isinstance(exc, IncompleteScan) else type(exc).__name__}),
              file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
