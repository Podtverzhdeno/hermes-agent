"""Repository contract invariants for all selected Hermes skill harnesses.

Runs with no network or LLM credentials. Does not claim domain task accuracy.
"""
import re
from pathlib import Path

import pytest

from agent.skill_harness import load_skill_harness
from agent.skill_utils import parse_frontmatter

REPO = Path(__file__).resolve().parents[2]
CATALOGS = (REPO / "skills", REPO / "optional-skills")

PILOT_NAMES = frozenset((
    "code-review", "systematic-debugging", "test-driven-development",
    "subagent-driven-development", "github-auth", "github-pr-workflow",
    "github-code-review", "github-repo-management", "codebase-inspection",
    "arxiv", "ml-paper-writing", "obsidian", "google-workspace", "native-mcp",
    "pytorch-fsdp", "chroma", "faiss", "qdrant-vector-search", "dspy",
    "evaluating-llms-harness", "writing-plans", "hermes-agent",
    "github-issues", "mcporter", "ocr-and-documents", "fastmcp", "notion",
))


def _manifests():
    return [
        path for root in CATALOGS
        for path in sorted(root.rglob("harness.yaml"))
    ]


def _canonical_name(path):
    skill_file = path.parent / "SKILL.md"
    assert skill_file.is_file(), f"orphan harness: {path}"
    fm, _ = parse_frontmatter(skill_file.read_text(encoding="utf-8"))
    assert isinstance(fm.get("name"), str) and fm["name"].strip()
    return fm["name"]


def test_pilot_coverage_is_explicit_and_never_duplicated():
    all_manifests = _manifests()
    names = [_canonical_name(p) for p in all_manifests]
    assert len(names) == len(set(names)), "Ambiguous duplicate skill names"
    assert PILOT_NAMES <= set(names)
    assert len(all_manifests) >= len(PILOT_NAMES)


@pytest.mark.parametrize("path", _manifests(), ids=lambda p: str(p.relative_to(REPO)))
def test_each_harness_is_valid_and_matches_skill(path):
    name = _canonical_name(path)
    contract = load_skill_harness(path.parent, name)
    assert contract["skill"] == name
    assert contract["enforcement"] == "advisory_only"
    assert contract["manifest_sha256"]
    assert contract["activation"]["when"]
    assert contract["activation"]["not_when"]
    assert contract["lifecycle"]["verify"]
    assert contract["lifecycle"]["recover"]
    assert contract["evidence"]["required"]
    assert contract["output"]["acceptance"]
    if contract["capabilities"]["side_effects"] == "external_write":
        assert contract["capabilities"]["approval_required"]


@pytest.mark.parametrize("name", [
    "github-auth", "github-code-review", "github-pr-workflow",
    "github-repo-management", "github-issues",
])
def test_github_skills_have_no_credential_extraction_or_token_url_recipes(name):
    found = [
        path for root in CATALOGS
        for path in root.rglob("SKILL.md")
        if path.parent.name == name
    ]
    assert len(found) == 1
    body = found[0].read_text(encoding="utf-8")
    forbidden = [
        r"(?im)^\s*grep\s+.*(?:\.git-credentials|\.hermes/\.env)",
        r"(?im)^\s*git\s+config\s+--global\s+credential\.helper\s+store\b",
        r"(?im)^\s*git\s+remote\s+set-url\s+.*(?:token|password)",
        r"(?im)^\s*curl\s+[^\n]*Authorization:\s*token",
        r"(?im)^\s*-H\s+[\"']Authorization:\s*(?:token|Bearer)\s+\$",
    ]
    for pattern in forbidden:
        assert not re.search(pattern, body), (name, pattern)


def test_codebase_inspection_never_installs_into_system_python():
    content = (REPO / "skills/github/codebase-inspection/SKILL.md").read_text(encoding="utf-8")
    assert "pip install --break-system-packages" not in content
    assert "pygount" in content

def test_all_harnesses_have_concrete_negative_routing_examples():
    """Never regress to an undefined exclusion; nearby skills must be distinguished."""
    placeholders = {"undefined", "null", "none", "todo", "tbd", "n/a"}
    for path in _manifests():
        name = _canonical_name(path)
        contract = load_skill_harness(path.parent, name)
        exclusions = contract["activation"]["not_when"]
        assert len(exclusions) >= 2, f"{path} has no meaningful adjacent-skill contrast"
        assert not any(value.casefold().strip() in placeholders for value in exclusions), path
        assert len(exclusions) == len(set(x.casefold() for x in exclusions)), path


def test_github_issue_skill_uses_provider_auth_not_token_scraping():
    content = (REPO / "skills/github/github-issues/SKILL.md").read_text(encoding="utf-8")
    assert "gh auth status" in content
    assert "gh issue view" in content
    assert "gh issue create" in content
    assert not re.search(r"(?m)^\\s*(?:GITHUB_TOKEN=\\$\\(|grep\\s+.*(?:\\.git-credentials|\\.hermes/\\.env))", content)
    assert not re.search(r"(?m)^\\s*curl\\s+.*Authorization:", content)


def test_document_skill_requires_authorized_remote_processing():
    content = (REPO / "skills/productivity/ocr-and-documents/SKILL.md").read_text(encoding="utf-8")
    assert "private inputs stay local" in content
    assert "page.get_textpage_ocr()" in content
    assert "privacy" in content.lower()
