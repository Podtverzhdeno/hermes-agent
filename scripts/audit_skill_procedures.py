"""Heuristic audit of all SKILL.md instruction bodies.

This is triage, not a security guarantee. It reports path/line/rule instead
of printing matched secrets or instructions. All findings require review.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


RULES = (
    ("remote_shell_pipeline", "critical",
     re.compile(r"\b(?:curl|wget)\b[^\n]{0,250}\|\s*(?:sh|bash)\b", re.I)),
    ("secret_file_read", "critical",
     re.compile(r"^\s*(?:cat|grep|rg|sed|awk)\b.{0,200}(?:\.env|\.git-credentials|credentials\.json|secrets\.json)", re.I)),
    ("token_printing", "critical",
     re.compile(r"\b(?:echo|print|printf)\b.{0,90}(?:\$[A-Z_]*(?:KEY|TOKEN|SECRET)|os\.environ\[(?:'|\")[A-Z_]*(?:KEY|TOKEN))", re.I)),
    ("recursive_deletion", "review",
     re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f\b|\brm\s+-[a-zA-Z]*f[a-zA-Z]*r\b", re.I)),
    ("unaudited_runtime_download", "review",
     re.compile(r"\bnpx\s+(?:-y|--yes)\b|\b(?:pip|npm)\s+install\b", re.I)),
    ("privilege_escalation", "review",
     re.compile(r"\bsudo\b|\bchmod\s+777\b", re.I)),
    ("shell_bearer_header", "review",
     re.compile(r"Authorization:\s*Bearer\s*\$", re.I)),
    ("remote_document_transfer", "review",
     re.compile(r"\b(?:web_extract|remote\s+OCR|upload\s+.*(?:document|pdf)|pastebin)\b", re.I)),
)


def scan_text(content: str, path: str) -> list[dict]:
    """Return line-number-only heuristic findings, never line contents."""
    findings: list[dict] = []
    for line_no, line in enumerate(content.splitlines(), 1):
        for name, severity, pattern in RULES:
            if pattern.search(line):
                findings.append({
                    "path": path,
                    "line": line_no,
                    "rule": name,
                    "severity": severity,
                })
    return findings


def scan_roots(roots: list[Path]) -> tuple[int, list[dict]]:
    count = 0
    findings: list[dict] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("SKILL.md")):
            if any(p in {".git", "node_modules", ".venv", "__pycache__"} for p in path.parts):
                continue
            count += 1
            try:
                body = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                findings.append({
                    "path": str(path),
                    "line": 0,
                    "rule": "unreadable_skill",
                    "severity": "critical",
                })
                continue
            findings.extend(scan_text(body, path.as_posix()))
    return count, findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roots", nargs="+", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--fail-on-critical", action="store_true")
    opts = parser.parse_args(argv)
    repo = Path(__file__).resolve().parents[1]
    roots = opts.roots or [repo / "skills", repo / "optional-skills"]
    count, findings = scan_roots(roots)
    if opts.as_json:
        print(json.dumps({"skills": count, "findings": findings}, indent=2))
    else:
        by_rule = Counter(x["rule"] for x in findings)
        critical = sum(x["severity"] == "critical" for x in findings)
        print(f"Audited {count} SKILL.md files; {len(findings)} heuristic observations; {critical} critical review candidates")
        for name, count in sorted(by_rule.items()):
            print(f"  {name}: {count}")
        print("These are heuristic triage candidates, not verified vulnerabilities.")
        for x in (f for f in findings if f["severity"] == "critical"):
            print(f"  REVIEW {x['path']}:{x['line']} [{x['rule']}]")
    if opts.fail_on_critical and any(f["severity"] == "critical" for f in findings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
