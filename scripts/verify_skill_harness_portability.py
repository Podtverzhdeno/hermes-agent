#!/usr/bin/env python3
"""Platform-light harness contract check (stdlib + PyYAML only).

Intended for Windows/macOS/Linux smoke verification without installing Hermes
provider clients. Does NOT test actual model execution or OS sandboxing.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from agent.skill_harness import (
    SkillHarnessError,
    load_skill_harness,
    path_within_root,
    validate_skill_lookup_name,
)


def validate_all(root: Path) -> tuple[int, list[str]]:
    total = 0
    issues: list[str] = []
    for catalog_name in ("skills", "optional-skills"):
        catalog = root / catalog_name
        if not catalog.is_dir():
            issues.append(f"Missing skill catalog: {catalog}")
            continue
        for harness in catalog.rglob("harness.yaml"):
            total += 1
            if not path_within_root(harness, catalog):
                issues.append(f"{harness}: path escaped root")
                continue
            skill_md = harness.parent / "SKILL.md"
            try:
                if not skill_md.is_file() or not path_within_root(skill_md, catalog):
                    raise SkillHarnessError("Missing or unsafe SKILL.md")
                source = skill_md.read_text(encoding="utf-8")
                if not source.startswith("---\n"):
                    raise SkillHarnessError("Missing frontmatter")
                end = source.find("\n---\n", 4)
                if end == -1:
                    raise SkillHarnessError("Unterminated frontmatter")
                meta = yaml.safe_load(source[4:end])
                if not isinstance(meta, dict):
                    raise SkillHarnessError("Frontmatter is not a YAML object")
                name = meta.get("name")
                if not isinstance(name, str) or validate_skill_lookup_name(name):
                    raise SkillHarnessError(f"Invalid skill name: {name!r}")
                checked = load_skill_harness(harness.parent, name)
                if checked is None:
                    raise SkillHarnessError("Manifest unexpectedly absent")
                if not checked["manifest_sha256"]:
                    raise SkillHarnessError("Missing content digest")
            except (OSError, UnicodeError, yaml.YAMLError, SkillHarnessError) as exc:
                issues.append(f"{harness}: {type(exc).__name__}: {exc}")
    return total, issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    args = parser.parse_args()
    number, issues = validate_all(args.root)
    print(f"Platform harness check: {number} contracts; {len(issues)} issues")
    for issue in issues:
        print("ERROR:", issue)
    return 1 if issues or number == 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
