"""Agent-owned harness updates: validation, digest, rollback and path isolation."""

import hashlib
from unittest.mock import patch

import pytest
import yaml

from agent.skill_harness import load_skill_harness
from tools.skill_manager_tool import _write_harness, skill_manage

SKILL_MD = "---\nname: sample\n" \
           "description: Test\n---\n\n# Sample\nWorkflow.\n"


def _valid_spec():
    return {
        "schema_version": 1, "skill": "sample",
        "activation": {"when": ["Test scenario"], "not_when": ["Other scenario"]},
        "capabilities": {"tools": ["read_file"], "side_effects": "none",
                         "approval_required": []},
        "lifecycle": {key: [f"{key} step"] for key in
                      ("preflight", "execute", "verify", "recover")},
        "budget": {"max_tool_calls": 12, "max_reference_bytes": 2048},
        "evidence": {"required": ["File path"]},
        "output": {"format": "Report", "acceptance": ["No fabrications"]},
    }


@pytest.fixture
def managed(tmp_path):
    root = tmp_path / "skills"
    target = root / "sample"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
    with patch("tools.skill_manager_tool.SKILLS_DIR", root):
        yield target


def test_first_write_is_validated_and_emits_digest(managed):
    contents = yaml.safe_dump(_valid_spec())
    with patch("tools.skill_manager_tool._security_scan_skill", return_value=None):
        response = _write_harness("sample", contents)
    assert response["success"] is True
    assert response["enforcement"] == "advisory_only"
    assert response["manifest_sha256"] == hashlib.sha256(contents.encode()).hexdigest()
    assert load_skill_harness(managed, "sample")["manifest_sha256"] == response["manifest_sha256"]


def test_existing_manifest_needs_fresh_digest(managed):
    original = yaml.safe_dump(_valid_spec())
    (managed / "harness.yaml").write_text(original, encoding="utf-8")
    edited = original.replace("Report", "Updated report")

    without = _write_harness("sample", edited)
    stale = _write_harness("sample", edited, expected_sha256="a" * 64)
    assert without["success"] is False
    assert stale["success"] is False
    assert "changed since" in stale["error"]
    assert (managed / "harness.yaml").read_text(encoding="utf-8") == original


def test_existing_manifest_updates_with_matching_digest(managed):
    original = yaml.safe_dump(_valid_spec())
    (managed / "harness.yaml").write_text(original, encoding="utf-8")
    edited = original.replace("Report", "Updated report")
    digest = hashlib.sha256(original.encode()).hexdigest()
    with patch("tools.skill_manager_tool._security_scan_skill", return_value=None):
        outcome = _write_harness("sample", edited, expected_sha256=digest)
    assert outcome["success"] is True
    assert (managed / "harness.yaml").read_text(encoding="utf-8") == edited


def test_invalid_schema_does_not_change_existing_file(managed):
    original = yaml.safe_dump(_valid_spec())
    (managed / "harness.yaml").write_text(original, encoding="utf-8")
    bad = original.replace("skill: sample", "skill: another")
    outcome = _write_harness(
        "sample", bad,
        expected_sha256=hashlib.sha256(original.encode()).hexdigest()
    )
    assert outcome["success"] is False
    assert "Invalid harness" in outcome["error"]
    assert (managed / "harness.yaml").read_text(encoding="utf-8") == original


def test_scanner_rejection_restores_original(managed):
    original = yaml.safe_dump(_valid_spec())
    (managed / "harness.yaml").write_text(original, encoding="utf-8")
    edited = original.replace("Report", "Updated report")
    digest = hashlib.sha256(original.encode()).hexdigest()
    with patch("tools.skill_manager_tool._security_scan_skill",
               return_value="approval required"):
        outcome = _write_harness("sample", edited, expected_sha256=digest)
    assert outcome["success"] is False
    assert (managed / "harness.yaml").read_text(encoding="utf-8") == original


def test_harness_symlink_escape_is_rejected(managed, tmp_path):
    outside = tmp_path / "secret.yaml"
    outside.write_text("private", encoding="utf-8")
    try:
        (managed / "harness.yaml").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported")
    outcome = _write_harness("sample", yaml.safe_dump(_valid_spec()))
    assert outcome["success"] is False
    assert "Unsafe" in outcome["error"]
    assert outside.read_text(encoding="utf-8") == "private"


def test_public_dispatcher_routes_write_harness(managed):
    with patch("tools.skill_manager_tool._security_scan_skill", return_value=None):
        raw = skill_manage(
            action="write_harness", name="sample", file_content=yaml.safe_dump(_valid_spec())
        )
    import json
    assert json.loads(raw)["success"] is True
