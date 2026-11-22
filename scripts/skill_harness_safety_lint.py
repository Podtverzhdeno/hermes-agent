"""Regression lint for shell examples in security-reviewed Hermes Skills.

This checks code fences only, NOT complete prompt semantics or execution
security. Targeted patterns must stay out of executable examples.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import re

AUDITED = (
    "skills/github/github-auth/SKILL.md",
    "skills/github/github-repo-management/SKILL.md",
    "skills/github/github-pr-workflow/SKILL.md",
    "skills/github/github-code-review/SKILL.md",
    "skills/github/github-issues/SKILL.md",
    "skills/github/codebase-inspection/SKILL.md",
    "skills/autonomous-ai-agents/codex/SKILL.md",
    "skills/autonomous-ai-agents/claude-code/SKILL.md",
    "skills/productivity/nano-pdf/SKILL.md",
    "optional-skills/creative/blender-mcp/SKILL.md",
)

_PATTERNS = (
    ("plaintext-credential-store", re.compile(r"\bgit\s+config\s+--global\s+credential\.helper\s+store\b", re.I)),
    ("secret-from-credential-file", re.compile(r"\b(?:grep|cat|sed|awk)\b.*(?:\.git-credentials|\.hermes/\.env)", re.I)),
    ("secret-embedded-remote", re.compile(r"git\s+remote\s+set-url.*https://\S+:\S+@github\.com", re.I)),
    ("skip-agent-permissions", re.compile(r"(?:--yolo|--dangerously-skip-permissions|--dangerously-bypass-approvals-and-sandbox)", re.I)),
    ("global-python-package-override", re.compile(r"\bpip\s+install\s+--break-system-packages\b", re.I)),
    ("global-agent-install", re.compile(r"\bnpm\s+install\s+-g\s+@(?:openai/codex|anthropic-ai/claude-code)\b", re.I)),
    ("remote-install-pipe", re.compile(r"\bcurl\b.*\|\s*(?:bash|sh)(?:\s|$)", re.I)),
    ("unpinned-blender-addon", re.compile(r"\bcurl\b.*raw\.githubusercontent\.com/.+/main/addon\.py", re.I)),
)
_FENCE = re.compile(r"^\s*([\x60~]{3,})([A-Za-z0-9_-]*)\s*$")
_SHELLS = frozenset(("bash", "sh", "shell", "zsh", "powershell", "ps1", "console"))


def lint_shell_snippets(content: str, path: str = "SKILL.md") -> list[dict]:
    findings = []
    opening = None
    active = False
    for line_num, line in enumerate(content.splitlines(), 1):
        fence = _FENCE.fullmatch(line)
        if fence:
            token, language = fence.group(1), fence.group(2).lower()
            if opening is None:
                opening, active = token, language in _SHELLS
            elif opening[0] == token[0] and len(token) >= len(opening):
                opening, active = None, False
            continue
        if opening is None or not active or line.lstrip().startswith("#"):
            continue
        for rule, pattern in _PATTERNS:
            if pattern.search(line):
                findings.append({"path": path, "line": line_num, "rule": rule})
    return findings


def audit_reviewed_skills(root: Path) -> list[dict]:
    root = Path(root)
    findings = []
    for relative in AUDITED:
        file = root / relative
        try:
            content = file.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            findings.append({"path": relative, "line": 0, "rule": "unreadable"})
            continue
        findings.extend(lint_shell_snippets(content, relative))
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args(argv)
    findings = audit_reviewed_skills(Path(args.root))
    for f in findings:
        print(f["path"] + ":" + str(f["line"]) + ": " + f["rule"])
    print(("FAIL" if findings else "PASS") + ": " + str(len(findings)) + " forbidden executable examples")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
