#!/usr/bin/env python3
"""Read-only exact-SHA evidence and PR collision gate for Hermes.
Never authorizes merge, tool execution, task retries or side effects.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SHA = re.compile(r"^[0-9a-f]{40}$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
MAX_PRS, MAX_FILES = 150, 1000
MAX_COLLISION_PAIRS = 5000

class EvidenceError(ValueError):
    pass

def get_json(path, token=None):
    if not path.startswith("/repos/"):
        raise EvidenceError("out-of-scope endpoint")
    req = urllib.request.Request(
        "https://api.github.com" + path, method="GET",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "hermes-pr-gate/1",
                 **({"Authorization": "Bearer " + token} if token else {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read(3000001)
    except urllib.error.HTTPError as exc:
        raise EvidenceError("GitHub API failed HTTP " + str(exc.code)) from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise EvidenceError("GitHub API unavailable: " + type(exc).__name__) from None
    if len(raw) > 3000000:
        raise EvidenceError("response exceeds safety limit")
    try:
        return json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise EvidenceError("invalid API JSON") from None

def pages(path, token, limit):
    rows = []
    for page in range(1, (limit // 100) + 2):
        separator = "&" if "?" in path else "?"
        current = get_json(path + separator + "per_page=100&page=" + str(page), token)
        if not isinstance(current, list):
            raise EvidenceError("invalid paginated result")
        rows.extend(current)
        if len(rows) > limit:
            raise EvidenceError("pagination incomplete: exceeds bound")
        if len(current) < 100:
            return rows
    raise EvidenceError("pagination incomplete")

def _unstable_prs(before, after):
    """Detect exact head/base/draft drift; return numeric PR IDs for incident evidence."""
    def index(rows):
        return {p["number"]: (p["head"]["sha"], p["base"]["sha"],
                              p.get("draft"), p["head"].get("ref"),
                              p["base"].get("ref")) for p in rows}
    first, second = index(before), index(after)
    return sorted(n for n in first.keys() | second.keys()
                  if first.get(n) != second.get(n))


def _incident_code(reason):
    if "PRs changed during snapshot" in reason:
        return "SNAPSHOT_RACE"
    if "HTTP 429" in reason:
        return "UPSTREAM_RATE_LIMIT"
    if "HTTP 403" in reason:
        return "UPSTREAM_PERMISSION_OR_RATE_LIMIT"
    if "GitHub API unavailable" in reason:
        return "TRANSPORT_UNAVAILABLE"
    return "EVIDENCE_INCOMPLETE"


def _changed_paths(changes):
    """A rename conflicts with edits to either its old or its new path."""
    paths = set()
    for f in changes:
        name = f.get("filename")
        if not isinstance(name, str) or not name:
            raise EvidenceError("malformed changed-file name")
        paths.add(name)
        if f.get("status") == "renamed":
            previous = f.get("previous_filename")
            if not isinstance(previous, str) or not previous:
                raise EvidenceError("rename missing previous_filename")
            paths.add(previous)
    return sorted(paths)


def live_snapshot(repository, token=None):
    if not REPO.fullmatch(repository) or ".." in repository:
        raise EvidenceError("invalid repository")
    root = "/repos/" + repository
    first = pages(root + "/pulls?state=open", token, MAX_PRS)
    result = []
    for pr in first:
        number, head = pr.get("number"), (pr.get("head") or {}).get("sha")
        if type(number) is not int or not SHA.fullmatch(str(head)):
            raise EvidenceError("malformed PR identity/head SHA")
        files = pages(root + "/pulls/" + str(number) + "/files", token, MAX_FILES)
        checks = get_json(root + "/commits/" + head + "/check-runs?per_page=100", token)
        statuses = get_json(root + "/commits/" + head + "/status", token)
        if not isinstance(checks, dict) or not isinstance(checks.get("check_runs"), list):
            raise EvidenceError("missing checks evidence")
        if checks.get("total_count", 0) > len(checks["check_runs"]):
            raise EvidenceError("partial checks evidence")
        if not isinstance(statuses, dict) or not isinstance(statuses.get("statuses"), list):
            raise EvidenceError("missing legacy status evidence")
        result.append({
            "number": number, "title": pr.get("title", ""),
            "head_sha": head, "head_branch": pr["head"].get("ref"),
            "head_repo": (pr["head"].get("repo") or {}).get("full_name"),
            "base_branch": (pr.get("base") or {}).get("ref"),
            "base_sha": (pr.get("base") or {}).get("sha"),
            "base_repo": ((pr.get("base") or {}).get("repo") or {}).get("full_name"),
            "draft": pr.get("draft", True),
            "files": _changed_paths(files),
            "checks": [{"name": c.get("name"), "head_sha": c.get("head_sha"),
                        "status": c.get("status"), "conclusion": c.get("conclusion")}
                       for c in checks["check_runs"]],
            "statuses": [{"context": s.get("context"), "description": s.get("description"),
                          "state": s.get("state")} for s in statuses["statuses"]],
        })
    second = pages(root + "/pulls?state=open", token, MAX_PRS)
    moved = _unstable_prs(first, second)
    if moved:
        raise EvidenceError("PRs changed during snapshot: #" +
                            ",#".join(str(n) for n in moved[:30]) +
                            (" and others" if len(moved) > 30 else "") +
                            "; retry, do not greenlight")
    return {"schema_version": 1, "repository": repository,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "consistent": True, "prs": result}

def assess(snapshot):
    if not isinstance(snapshot, dict) or snapshot.get("schema_version") != 1 or snapshot.get("consistent") is not True:
        raise EvidenceError("untrusted/partial snapshot")
    prs = snapshot.get("prs")
    if not isinstance(prs, list) or len(prs) > MAX_PRS:
        raise EvidenceError("missing/oversized PR list")
    ids = set()
    for p in prs:
        n = p.get("number")
        if type(n) is not int or n <= 0 or n in ids or not SHA.fullmatch(str(p.get("head_sha", ""))):
            raise EvidenceError("duplicate/malformed PR identity")
        ids.add(n)
        if not isinstance(p.get("files"), list) or len(p["files"]) > MAX_FILES or not all(isinstance(f, str) for f in p["files"]):
            raise EvidenceError("missing changed-file evidence")
        if not isinstance(p.get("checks"), list):
            raise EvidenceError("missing check-run list")
        for c in p["checks"]:
            if not isinstance(c, dict) or c.get("head_sha") != p["head_sha"]:
                raise EvidenceError("check-run not tied to exact PR SHA")
        if not isinstance(p.get("head_branch"), str) or not isinstance(p.get("base_branch"), str):
            raise EvidenceError("missing PR branch")
    # Branch names collide across forks. Parent is valid only for the SAME origin repo.
    repo = snapshot.get("repository")
    branch_owner = {}
    for p in prs:
        origin = p.get("head_repo", repo)
        if origin is None:
            continue  # Unknown/deleted fork; cannot prove a dependency.
        key = (origin, p["head_branch"])
        if key in branch_owner:
            raise EvidenceError("ambiguous PR head branch identity")
        branch_owner[key] = p["number"]
    parents = {
        p["number"]: branch_owner.get((p.get("base_repo", repo), p["base_branch"]))
        for p in prs
    }
    def ancestry(n):
        visited = set()
        while parents.get(n) is not None:
            n = parents[n]
            if n in visited:
                raise EvidenceError("PR dependency cycle")
            visited.add(n)
        return visited
    dependencies = []
    collisions = []
    by_file = defaultdict(list)
    for p in prs:
        for file in set(p["files"]):
            by_file[file].append(p["number"])
        if parents[p["number"]] is not None:
            dependencies.append({"pr": p["number"], "depends_on": parents[p["number"]]})
        ancestry(p["number"])
    collision_truncated = False
    for file, owners in sorted(by_file.items()):
        for a, b in itertools.combinations(sorted(owners), 2):
            if a not in ancestry(b) and b not in ancestry(a):
                if len(collisions) >= MAX_COLLISION_PAIRS:
                    collision_truncated = True
                    break
                collisions.append({"file": file, "prs": [a, b]})
        if collision_truncated:
            break
    semantic = []
    families = {
        "api-singleflight": {"gateway/platforms/api_server.py", "gateway/idempotency.py"},
        "event-observer": {"gpt_bridge/observability.py", "gpt_companion/journal.py",
                           "hermes_gpt_bridge/diagnostics.py", "gateway/gpt_bridge_diagnostics.py"},
        "task-control": {"autopilot/ledger.py", "autopilot/policy.py"},
    }
    for family, paths in families.items():
        hits = sorted({p["number"] for p in prs if set(p["files"]) & paths})
        if len(hits) > 1:
            semantic.append({"family": family, "candidate_prs": hits,
                             "note": "review needed; not a proven semantic conflict"})
    checks = []
    for p in prs:
        relevant = [c for c in p["checks"] if c.get("name") == "test"]
        if not relevant:
            status = "MISSING"
        elif all(c.get("status") == "completed" and c.get("conclusion") == "success" for c in relevant):
            status = "PASS"
        else:
            status = "BLOCKED:" + ",".join(sorted({str(c.get("conclusion") or c.get("status") or "unknown") for c in relevant}))
        skipped_review = [s.get("context") for s in p.get("statuses", [])
                          if isinstance(s, dict) and "skipp" in str(s.get("description", "")).lower()]
        checks.append({"pr": p["number"], "head_sha": p["head_sha"], "test": status,
                       "review_skipped": skipped_review, "draft": p.get("draft") is True})
    return {
        "schema_version": 1, "repository": snapshot.get("repository"),
        "observed_at": snapshot.get("observed_at"),
        "pull_requests": len(prs), "checks": sorted(checks, key=lambda c: c["pr"]),
        "collisions": collisions,
        "collisions_truncated": collision_truncated,
        "collision_pairs_at_least": len(collisions) + int(collision_truncated),
        "stacked_dependencies": dependencies,
        "semantic_reviews": semantic, "merge_ready": False,
        "reason": "ADVISORY_ONLY: independent combined-SHA tests, extension runtime and security review required",
    }

def _safe_markdown(value):
    """User-controlled GitHub paths are data, never Markdown directives."""
    return (str(value).replace(chr(92), chr(92) * 2)
            .replace("|", chr(92) + "|")
            .replace(chr(10), chr(92) + "n")
            .replace(chr(13), chr(92) + "r")
            .replace("<", "&lt;").replace(">", "&gt;"))


def markdown(report):
    out = ["# Hermes GPT integration evidence", "",
           "Snapshot: " + _safe_markdown(report["observed_at"]),
           "Merge authorization: **NO** (read-only evidence)", "",
           "| PR | Exact head SHA | Required test | Review skipped |",
           "|---|---|---|---|"]
    for c in report["checks"]:
        out.append("| #{pr} | {sha} | {test} | {review} |".format(
            pr=c["pr"], sha=c["head_sha"][:12], test=_safe_markdown(c["test"]),
            review=", ".join(_safe_markdown(x) for x in c["review_skipped"]) or "—"))
    out += ["", "## Independent file overlap"]
    out += ["- PR {} × PR {}: {}".format(*c["prs"], _safe_markdown(c["file"])) for c in report["collisions"]] or ["None observed"]
    if report.get("collisions_truncated"):
        out += ["", "WARNING: collision list truncated (at least " +
                str(report["collision_pairs_at_least"]) +
                " independent pairs). Report is INCOMPLETE; manual review mandatory."]
    out += ["", "## Stacked dependencies"]
    out += ["- PR {} depends on PR {}".format(d["pr"], d["depends_on"]) for d in report["stacked_dependencies"]] or ["None observed"]
    out += ["", "## Semantic review candidates"]
    out += ["- {}: {}".format(s["family"], s["candidate_prs"]) for s in report["semantic_reviews"]] or ["None observed"]
    out += ["", "Caution: no file overlap does not prove contract compatibility; successful legacy status is not a passing required test.", ""]
    return "\n".join(out)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--snapshot", type=Path)
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--repo", default="Podtverzhdeno/hermes-agent")
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-md", type=Path)
    parser.add_argument("--fail-on-collision", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.live:
            # With dozens of active agents, PR heads can move mid-snapshot.
            # Retry only a recognized transient race. Never manufacture a green result.
            for attempt in range(3):
                try:
                    snapshot = live_snapshot(args.repo, os.getenv("GITHUB_TOKEN"))
                    break
                except EvidenceError as exc:
                    if "PRs changed during snapshot" not in str(exc) or attempt == 2:
                        raise
                    time.sleep(2)
        else:
            snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        report = assess(snapshot)
        human = markdown(report)
        if args.output_json:
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            args.output_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        if args.output_md:
            args.output_md.parent.mkdir(parents=True, exist_ok=True)
            args.output_md.write_text(human, encoding="utf-8")
        if not args.output_md:
            print(human)
        return 2 if args.fail_on_collision and report["collisions"] else 0
    except (EvidenceError, OSError, ValueError) as exc:
        # Emit a durable incident artifact even when no trustworthy snapshot exists.
        # Explicitly NOT authorized for a merge; this is a diagnosis, not success.
        reason = "INPUT_IO_ERROR" if isinstance(exc, OSError) else str(exc)
        failure = {
            "schema_version": 1, "repository": args.repo,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "status": "EVIDENCE_UNAVAILABLE", "merge_ready": False,
            "reason_code": _incident_code(reason),
            "reason": reason,
        }
        if args.output_json:
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            args.output_json.write_text(json.dumps(failure, indent=2, ensure_ascii=False), encoding="utf-8")
        if args.output_md:
            args.output_md.parent.mkdir(parents=True, exist_ok=True)
            args.output_md.write_text("# Hermes PR evidence unavailable\n\n"
                                     "Status: FAIL CLOSED. No merge authorization.\n\n"
                                     "Reason: " + failure["reason_code"] + " / " + reason + "\n",
                                     encoding="utf-8")
        print("EVIDENCE_UNAVAILABLE: " + reason, file=sys.stderr)
        return 3

if __name__ == "__main__":
    raise SystemExit(main())
