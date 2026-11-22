#!/usr/bin/env python3
"""Inventory every bundled/optional skill and validate harness coverage.

No provider access, external network or code execution is required.
Invoke from repository root:
  python -m scripts.audit_skill_harness --json
  python -m scripts.audit_skill_harness --strict

Exit codes: 0 = valid (coverage may be incomplete), 1 = validation failures.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agent.skill_harness import (
    SkillHarnessError, load_skill_harness, path_within_root,
)
from agent.skill_utils import parse_frontmatter


def audit_repository(repo_root: Path) -> dict[str, Any]:
    """Check both catalogs without modifying them or importing tool handlers."""
    result: dict[str, Any] = {
        "catalogs": {}, "counts": {"skills": 0, "harnessed": 0, "legacy": 0},
        "issues": [], "warnings": [],
        "harnessed_skills": [], "legacy_skills": [],
    }
    seen_names: dict[str, str] = {}
    for catalog in ("skills", "optional-skills"):
        root = repo_root / catalog
        count = 0
        if not root.is_dir():
            result["warnings"].append(f"Catalog missing: {catalog}")
            result["catalogs"][catalog] = 0
            continue

        for path in sorted(root.rglob("SKILL.md")):
            if any(part in (".git", ".github", ".hub")
                   for part in path.relative_to(root).parts):
                continue
            rel = str(path.relative_to(repo_root))
            if not path_within_root(path, root):
                result["issues"].append(f"{rel}: symlink escapes catalog root")
                continue
            try:
                raw = path.read_text(encoding="utf-8")
                frontmatter, body = parse_frontmatter(raw)
            except (OSError, UnicodeError, ValueError) as exc:
                result["issues"].append(f"{rel}: failed to read: {exc}")
                continue

            count += 1
            result["counts"]["skills"] += 1
            name = frontmatter.get("name") if isinstance(frontmatter, dict) else None
            if not isinstance(name, str) or not name.strip():
                result["issues"].append(f"{rel}: missing/invalid frontmatter name")
                continue
            desc = frontmatter.get("description")
            if not isinstance(desc, str) or not desc.strip():
                result["issues"].append(f"{rel}: missing/invalid description")
            if len(raw) > 20000:
                result["warnings"].append(
                    f"{rel}: long SKILL.md ({len(raw)} chars); consider progressive disclosure"
                )
            if name in seen_names:
                result["warnings"].append(
                    f"{rel}: duplicated skill name '{name}' (also {seen_names[name]})"
                )
            else:
                seen_names[name] = rel

            try:
                harness = load_skill_harness(path.parent, name)
            except SkillHarnessError as exc:
                result["issues"].append(f"{rel}: invalid harness: {exc}")
                continue
            if harness is None:
                result["counts"]["legacy"] += 1
                result["legacy_skills"].append(rel)
            else:
                result["counts"]["harnessed"] += 1
                result["harnessed_skills"].append(rel)

        result["catalogs"][catalog] = count

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Full JSON report")
    parser.add_argument("--strict", action="store_true", help="Fail on invalid metadata/manifest")
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1],
        help="Repository root",
    )
    args = parser.parse_args()
    report = audit_repository(args.root.resolve())
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        counts = report["counts"]
        print(
            f"Audited {counts['skills']} skills: {counts['harnessed']} harnessed, "
            f"{counts['legacy']} legacy, {len(report['issues'])} issues, "
            f"{len(report['warnings'])} warnings"
        )
        for issue in report["issues"]:
            print(f"ERROR: {issue}")
        for warning in report["warnings"]:
            print(f"WARN: {warning}")
    return 1 if args.strict and report["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
