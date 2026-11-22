#!/usr/bin/env python3
"""Read-only inventory of independently profiled Hermes Skills.

This is coverage and review prioritization, NOT a static security guarantee,
model routing evaluation, or permission scanner. Unprofiled skills remain
UNKNOWN, not safe. No network, model calls, writes or environment probing.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from agent.skill_harness import SkillHarnessError, load_skill_harness


_HINTS = {
    "external-endpoints": re.compile(r"https?://|curl |wget |web_extract", re.I),
    "external-mutation": re.compile(r"git push|gh pr merge|gh issue create|gh issue close|--method (POST|PATCH|PUT|DELETE)", re.I),
    "credential-guidance": re.compile(r"API_KEY|AUTH_TOKEN|GITHUB_TOKEN|credential|\.env", re.I),
    "shell-installation": re.compile(r"\bpip install\b|\bnpm install\b|\bnpx\b|\bcurl .*\|\s*(bash|sh)", re.I),
    "file-mutation": re.compile(r"write_file|remove_file|>>|git commit|\.write_text\(", re.I),
}


def inspect_skill(path: Path, root: Path) -> dict:
    relative = path.relative_to(root).as_posix()
    skill_dir = path.parent
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return {"path": relative, "status": "unreadable", "risk": "unknown",
                "review_hints": [], "name": skill_dir.name}
    match = re.search(r"(?m)^name:\s*['\"]?([a-z0-9-]+)['\"]?\s*$", content[:8000])
    name = match.group(1) if match else skill_dir.name
    result = {
        "path": relative,
        "name": name,
        "status": "unprofiled",
        "risk": "unknown",
        "review_hints": sorted(k for k, p in _HINTS.items() if p.search(content)),
    }
    try:
        profile = load_skill_harness(skill_dir, name)
    except SkillHarnessError as exc:
        result["status"] = "invalid-profile"
        result["detail"] = str(exc)
        return result
    if profile:
        result["status"] = "profiled"
        result["risk"] = profile["risk"]
        result["operations"] = len(profile["actions"])
        result["routing_fixtures"] = {
            "positive": len(profile["routing"]["trigger"]),
            "negative": len(profile["routing"]["do_not_trigger"]),
        }
        result["evidence_kinds"] = len(profile["evidence"])
    return result


def scan_repository(root: Path) -> dict:
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError("repository root must be a directory")
    files = []
    for tier in ("skills", "optional-skills"):
        base = root / tier
        if base.is_dir():
            files.extend(p for p in base.rglob("SKILL.md")
                         if p.is_file() and not p.is_symlink()
                         and not set(p.relative_to(base).parts) & {".git", ".hub", ".github"})
    entries = [inspect_skill(p, root) for p in sorted(files)]
    by_status = dict(sorted(Counter(x["status"] for x in entries).items()))
    return {
        "schema_version": 1,
        "scope": "bundled_and_optional_skill_sources_only",
        "total": len(entries),
        "counts": by_status,
        "profiled_fraction": (round(by_status.get("profiled", 0) / len(entries), 4)
                              if entries else 0),
        "model_behavior_tested": False,
        "host_authority_verified": False,
        "entries": entries,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    p.add_argument("--format", choices=("json", "markdown"), default="json")
    args = p.parse_args(argv)
    try:
        report = scan_repository(Path(args.root))
    except (OSError, ValueError) as exc:
        print("Skill inventory error: " + str(exc), file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("# Hermes Skill Harness coverage inventory")
        print()
        print("This is a file inventory, not proof of routing accuracy or execution safety.")
        print()
        print("| Metric | Count |")
        print("|---|---:|")
        for k, v in report["counts"].items():
            print("| " + k + " | " + str(v) + " |")
        print("| Total | " + str(report["total"]) + " |")
        print()
        print("| Skill path | Harness | Risk | Review hints |")
        print("|---|---|---|---|")
        for x in report["entries"]:
            print("| " + x["path"] + " | " + x["status"] + " | " + x["risk"]
                  + " | " + ", ".join(x["review_hints"]) + " |")
    return 1 if report["counts"].get("invalid-profile", 0) or report["counts"].get("unreadable", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
