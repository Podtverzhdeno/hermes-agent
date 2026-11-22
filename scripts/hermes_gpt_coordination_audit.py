#!/usr/bin/env python3
"""Read-only Hermes GPT integration collision audit.

This is a *pre-merge coordination gate*, not a task scheduler, runtime monitor,
proof of code correctness, or a replacement for upstream Hermes Kanban.
It deliberately fails closed when GitHub cannot provide a complete inventory.
Uses only Python's standard library. No prompts, tokens or diff bodies are logged.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import itertools
import json
import os
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

SHA40 = re.compile(r"^[0-9a-fA-F]{40}$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
CORE = {"gateway/platforms/api_server.py", "gateway/config.py",
        "acp_adapter/server.py", "acp_adapter/permissions.py"}
PACKAGING = {"pyproject.toml", "setup.py", "setup.cfg"}
CAPABILITY_PATHS = {
    "gpt-api": ("gateway/platforms/api_server.py", "gateway/idempotency.py"),
    "gpt-observer": ("gpt_bridge/", "gpt_extension/", "gpt_companion/",
                     "gateway/gpt_bridge_diagnostics.py", "gateway/gpt_bridge"),
    "task-ledger": ("autopilot/ledger.py", "kanban/"),
}

class AuditError(Exception):
    """Input or discovery incomplete; a green verdict is forbidden."""


def _get(url: str, token: str | None, tries: int = 3):
    headers = {"Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "hermes-gpt-coordination-audit/1"}
    if token:
        headers["Authorization"] = "Bearer " + token
    for attempt in range(tries):
        try:
            with urlopen(Request(url, headers=headers), timeout=15) as response:
                return json.load(response)
        except HTTPError as exc:
            # Never print response bodies: API errors can contain sensitive data.
            transient = exc.code in (429, 502, 503, 504) or (
                exc.code == 403 and exc.headers.get("Retry-After"))
            if transient and attempt + 1 < tries:
                delay = exc.headers.get("Retry-After", "1")
                try:
                    pause = min(4.0, max(1.0, float(delay)))
                except ValueError:
                    pause = 1.0
                time.sleep(pause)
                continue
            raise AuditError("GitHub API HTTP %d; inventory incomplete" % exc.code) from None
        except (URLError, TimeoutError, ValueError) as exc:
            if attempt + 1 < tries:
                time.sleep(1.0 + attempt)
                continue
            raise AuditError("GitHub API unreachable or invalid JSON: %s" %
                             type(exc).__name__) from None
    raise AuditError("GitHub API retries exhausted")


def _pages(url: str, token: str | None, limit: int) -> list:
    result = []
    for page in range(1, limit + 1):
        sep = "&" if "?" in url else "?"
        chunk = _get("%s%sper_page=100&page=%d" % (url, sep, page), token)
        if not isinstance(chunk, list):
            raise AuditError("Unexpected GitHub list response")
        result.extend(chunk)
        if len(chunk) < 100:
            return result
    raise AuditError("GitHub listing exceeds audited page limit")


def collect(repo: str, base: str = "main", prs_only: bool = False,
            token: str | None = None) -> dict:
    if not REPO.fullmatch(repo) or not re.fullmatch(r"[A-Za-z0-9_.\-/]+", base):
        raise AuditError("Invalid repository or branch")
    api = "https://api.github.com/repos/" + repo
    base_info = _get(api + "/branches/" + quote(base, safe=""), token)
    base_sha = base_info.get("commit", {}).get("sha")
    if not isinstance(base_sha, str) or not SHA40.fullmatch(base_sha):
        raise AuditError("Base commit SHA not verified")
    entries, represented = [], set()
    pulls = _pages(api + "/pulls?state=open", token, limit=10)
    for pr in pulls:
        if pr.get("base", {}).get("ref") != base:
            continue  # Different target base: explicitly outside this merge queue.
        number = pr.get("number")
        head = pr.get("head") or {}
        sha = head.get("sha")
        name = head.get("ref")
        origin = (head.get("repo") or {}).get("full_name")
        if not isinstance(number, int) or not name or not origin:
            raise AuditError("Malformed PR head")
        if not isinstance(sha, str) or not SHA40.fullmatch(sha):
            raise AuditError("Invalid PR head SHA")
        files = _pages(api + "/pulls/%d/files" % number, token, limit=30)
        if len(files) >= 3000:
            raise AuditError("PR file listing at GitHub's 3000-file limit")
        # The PR files endpoint addresses a moving PR number, not an immutable
        # commit. Re-read the PR after pagination; if HEAD or base moved,
        # discard this inventory instead of attributing mixed files to a SHA.
        latest = _get(api + "/pulls/%d" % number, token)
        initial_base_sha = (pr.get("base") or {}).get("sha")
        latest_base_sha = (latest.get("base") or {}).get("sha")
        if (latest.get("head", {}).get("sha") != sha or
                latest.get("base", {}).get("ref") != base or
                (initial_base_sha is not None and
                 latest_base_sha != initial_base_sha)):
            raise AuditError("PR moved during inventory: %d" % number)
        paths = [f.get("filename") for f in files]
        entries.append({"id": "PR-%d" % number, "head": sha, "files": paths,
                        "title": "", "origin": origin, "draft": bool(pr.get("draft"))})
        if origin.casefold() == repo.casefold():
            represented.add(name)
    if not prs_only:
        branches = _pages(api + "/branches", token, limit=10)
        for branch in branches:
            name = branch.get("name")
            if not isinstance(name, str) or name == base or name in represented:
                continue
            sha = (branch.get("commit") or {}).get("sha")
            if not isinstance(sha, str) or not SHA40.fullmatch(sha):
                raise AuditError("Invalid branch HEAD: " + name)
            # Compare recorded immutable SHAs; do not silently compare a
            # branch name that may have advanced since the branch listing.
            comparison = _get(api + "/compare/" + base_sha +
                              "..." + sha, token)
            paths = [f.get("filename") for f in comparison.get("files", [])]
            cmp_base = (comparison.get("base_commit") or {}).get("sha")
            cmp_head = (comparison.get("commits") or [{}])[-1].get("sha")
            if cmp_base and cmp_base != base_sha:
                raise AuditError("Comparison base changed unexpectedly: " + name)
            if cmp_head and cmp_head != sha:
                raise AuditError("Comparison head does not match branch SHA: " + name)
            if len(paths) >= 300 or comparison.get("status") not in (
                    "ahead", "diverged", "identical", "behind"):
                raise AuditError("Branch comparison missing or truncated: " + name)
            # If this branch advanced during the scan, a historical compare
            # must never be passed off as its *current* patch series.
            latest_branch = _get(api + "/branches/" + quote(name, safe=""), token)
            if (latest_branch.get("commit") or {}).get("sha") != sha:
                raise AuditError("Branch moved during inventory: " + name)
            if comparison.get("ahead_by", 0) == 0:
                continue
            entries.append({"id": "BRANCH:" + name, "head": sha, "files": paths,
                            "title": "", "origin": repo, "draft": True})
    # A changing base can invalidate all earlier PR file comparisons even
    # if individual heads did not move. No global REST snapshot transaction
    # exists, but we can detect common drift and fail closed.
    latest_base = _get(api + "/branches/" + quote(base, safe=""), token)
    if (latest_base.get("commit") or {}).get("sha") != base_sha:
        raise AuditError("Base branch moved during inventory")
    return {"schema_version": 1, "source": "GITHUB_REST",
            "repo": repo, "base": base, "base_sha": base_sha,
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "entries": entries}


def _capabilities(paths: set[str]) -> set[str]:
    return {name for name, prefixes in CAPABILITY_PATHS.items()
            if any(p == prefix or p.startswith(prefix)
                   for p in paths for prefix in prefixes)}


def validate(snapshot: dict) -> list[dict]:
    if not isinstance(snapshot, dict) or snapshot.get("schema_version") != 1:
        raise AuditError("Unsupported or absent snapshot schema")
    if not SHA40.fullmatch(str(snapshot.get("base_sha", ""))):
        raise AuditError("Missing immutable base SHA")
    entries = snapshot.get("entries")
    if not isinstance(entries, list) or len(entries) > 1000:
        raise AuditError("Invalid or oversized inventory")
    seen = set()
    clean = []
    for item in entries:
        if not isinstance(item, dict):
            raise AuditError("Malformed inventory entry")
        name, sha, paths = item.get("id"), item.get("head"), item.get("files")
        if not isinstance(name, str) or not name or name in seen:
            raise AuditError("Duplicate or absent branch identity")
        seen.add(name)
        if not isinstance(sha, str) or not SHA40.fullmatch(sha):
            raise AuditError("Missing verified branch HEAD: " + name)
        if not isinstance(paths, list) or not paths:
            raise AuditError("Missing changed file evidence: " + name)
        if len(paths) > 3000:
            raise AuditError("Oversized changed file inventory: " + name)
        for p in paths:
            if (not isinstance(p, str) or not p or p.startswith("/") or
                    "\\" in p or any(s in (".", "..") for s in p.split("/"))):
                raise AuditError("Untrusted changed path: " + name)
        clean.append({"id": name, "head": sha, "files": sorted(set(paths)),
                      "capabilities": sorted(_capabilities(set(paths)))})
    return sorted(clean, key=lambda item: item["id"])


def audit(snapshot: dict) -> dict:
    entries = validate(snapshot)
    findings = []
    for left, right in itertools.combinations(entries, 2):
        overlap = sorted(set(left["files"]) & set(right["files"]))
        shared_capabilities = sorted(set(left["capabilities"]) &
                                     set(right["capabilities"]))
        if not overlap and not shared_capabilities:
            continue
        if overlap:
            severity = ("P0" if any(p in CORE for p in overlap)
                        else "P1" if any(p in PACKAGING or not p.startswith(
                            ("docs/", "tests/")) for p in overlap) else "P2")
            reason = "EXACT_PATH_COLLISION"
            disposition = "HOLD_FOR_INTEGRATION"
        else:
            severity, reason = "P1", "CAPABILITY_OVERLAP_REVIEW"
            disposition = "REVIEW_REQUIRED"
        findings.append({"left": left["id"], "right": right["id"],
                         "severity": severity, "reason": reason,
                         "paths": overlap, "capabilities": shared_capabilities,
                         "disposition": disposition})
    blockers = sum(f["reason"] == "EXACT_PATH_COLLISION" for f in findings)
    reviews = len(findings) - blockers
    return {"schema_version": 1, "repo": snapshot.get("repo"),
            "base": snapshot.get("base"), "base_sha": snapshot["base_sha"],
            "source": snapshot.get("source", "UNVERIFIED_FIXTURE"),
            "entries_checked": len(entries), "exact_collisions": blockers,
            "capability_reviews": reviews,
            # 'NO_COLLISION_FOUND' never means CI/security/merge permission.
            "verdict": ("HOLD" if blockers else "REVIEW" if reviews
                        else "NO_COLLISION_FOUND_NOT_MERGE_APPROVAL"),
            "findings": findings}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--snapshot", help="Offline inventory JSON file")
    group.add_argument("--repo", help="owner/repo; read-only GitHub REST collection")
    p.add_argument("--base", default="main")
    p.add_argument("--prs-only", action="store_true")
    p.add_argument("--output", help="Optional JSON report path")
    args = p.parse_args(argv)
    try:
        if args.snapshot:
            with open(args.snapshot, encoding="utf-8") as f:
                snapshot = json.load(f)
            if not isinstance(snapshot, dict):
                raise AuditError("Snapshot must be an object")
            # A locally supplied JSON file is NOT source-authenticated even
            # if the file itself falsely claims source=GITHUB_REST.
            snapshot["source"] = "OFFLINE_INPUT_UNVERIFIED"
        else:
            snapshot = collect(args.repo, args.base, args.prs_only,
                               os.environ.get("GITHUB_TOKEN"))
        report = audit(snapshot)
        data = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            import tempfile
            directory = os.path.dirname(os.path.abspath(args.output))
            fd, path = tempfile.mkstemp(dir=directory, prefix=".hermes-gpt-audit-")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(path, args.output)
            finally:
                if os.path.exists(path):
                    os.unlink(path)
        else:
            sys.stdout.write(data)
        return 3 if report["verdict"] in ("HOLD", "REVIEW") else 0
    except (AuditError, OSError, ValueError, TypeError) as exc:
        print("INCOMPLETE_AUDIT: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
