"""Contract validation tests for per-skill harness declarations."""

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from agent.skill_harness import (
    SkillHarnessError, load_skill_harness, path_within_root,
    validate_skill_harness, validate_skill_lookup_name,
)


@pytest.fixture
def manifest():
    return {
        "schema_version": 1,
        "skill": "demo-skill",
        "activation": {"when": ["Investigate a specific failure"],
                       "not_when": ["No failing behavior exists"]},
        "capabilities": {"tools": ["read_file", "terminal"],
                         "side_effects": "local_write",
                         "approval_required": ["Destructive operations"]},
        "lifecycle": {
            "preflight": ["Inspect the workspace"],
            "execute": ["Reproduce and patch"],
            "verify": ["Run focused tests"],
            "recover": ["Revert only owned edits"],
        },
        "budget": {"max_tool_calls": 20, "max_reference_bytes": 32768},
        "evidence": {"required": ["Reproducer and exact test result"]},
        "output": {"format": "Root cause and validated fix",
                   "acceptance": ["No unrelated changes"]},
    }


def test_valid_manifest_is_only_advisory(manifest):
    obj = validate_skill_harness(manifest, "demo-skill")
    assert obj["enforcement"] == "advisory_only"
    assert obj["capabilities"]["side_effects"] == "local_write"
    assert "NOT a tool permission" in obj["security_notice"]


@pytest.mark.parametrize("bad_name", [
    "", "../secret", "foo/../../etc", "/tmp/secret", r"C:\Users\secret",
    "foo\\bar", "foo//bar", "./demo", "foo/*.md", "foo/%", "foo/\x00bar",
    "x" * 257, None,
])
def test_lookup_rejects_malformed_names(bad_name):
    assert validate_skill_lookup_name(bad_name) is not None


@pytest.mark.parametrize("good_name", [
    "demo-skill", "research/arxiv", "mlops/research/dspy",
    "legacy.md", "_local", "my.skill_v2",
])
def test_lookup_allows_existing_category_conventions(good_name):
    assert validate_skill_lookup_name(good_name) is None


@pytest.mark.parametrize("section,key,value", [
    ("budget", "max_tool_calls", True),
    ("budget", "max_tool_calls", 201),
    ("budget", "max_reference_bytes", 100),
    ("capabilities", "side_effects", "root"),
    ("activation", "when", []),
    ("lifecycle", "verify", []),
    ("evidence", "required", [""]),
    ("output", "format", ""),
])
def test_rejects_invalid_types_and_limits(manifest, section, key, value):
    candidate = deepcopy(manifest)
    candidate[section][key] = value
    with pytest.raises(SkillHarnessError):
        validate_skill_harness(candidate, "demo-skill")


def test_unknown_root_and_section_fields_rejected(manifest):
    manifest["arbitrary_script"] = "run this"
    with pytest.raises(SkillHarnessError, match="Unknown harness"):
        validate_skill_harness(manifest, "demo-skill")
    del manifest["arbitrary_script"]
    manifest["capabilities"]["bypass_approval"] = True
    with pytest.raises(SkillHarnessError, match="Unknown 'capabilities'"):
        validate_skill_harness(manifest, "demo-skill")


def test_external_write_requires_approval(manifest):
    manifest["capabilities"]["side_effects"] = "external_write"
    manifest["capabilities"]["approval_required"] = []
    with pytest.raises(SkillHarnessError, match="require explicit approval"):
        validate_skill_harness(manifest, "demo-skill")


def test_activation_overlap_rejected(manifest):
    manifest["activation"]["not_when"] = ["INVESTIGATE A SPECIFIC FAILURE"]
    with pytest.raises(SkillHarnessError, match="overlap"):
        validate_skill_harness(manifest, "demo-skill")


def test_duplicate_stage_items_rejected(manifest):
    manifest["lifecycle"]["verify"] = ["Check tests", "check tests"]
    with pytest.raises(SkillHarnessError, match="duplicate"):
        validate_skill_harness(manifest, "demo-skill")


def test_manifest_name_must_match_skill(manifest):
    with pytest.raises(SkillHarnessError, match="exactly match"):
        validate_skill_harness(manifest, "another-skill")


def test_manifest_is_optional_for_legacy_skill(tmp_path):
    assert load_skill_harness(tmp_path, "demo-skill") is None


def test_valid_manifest_read(tmp_path, manifest):
    (tmp_path / "harness.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
    assert load_skill_harness(tmp_path, "demo-skill")["skill"] == "demo-skill"


def test_invalid_yaml_fails_closed(tmp_path):
    (tmp_path / "harness.yaml").write_text("hello: [broken", encoding="utf-8")
    with pytest.raises(SkillHarnessError, match="Cannot parse"):
        load_skill_harness(tmp_path, "demo-skill")


def test_oversized_manifest_fails_closed(tmp_path):
    (tmp_path / "harness.yaml").write_text("x" * 32769, encoding="utf-8")
    with pytest.raises(SkillHarnessError, match="32 KiB"):
        load_skill_harness(tmp_path, "demo-skill")


def test_manifest_symlink_escape_rejected(tmp_path, manifest):
    outside = tmp_path / "external.yaml"
    outside.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    link = skill_dir / "harness.yaml"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Host does not allow symlinks")
    with pytest.raises(SkillHarnessError, match="symlink"):
        load_skill_harness(skill_dir, "demo-skill")


def test_prefix_confusion_does_not_pass_containment(tmp_path):
    root = tmp_path / "skill"
    sibling = tmp_path / "skill-backup"
    root.mkdir()
    sibling.mkdir()
    assert not path_within_root(sibling / "SKILL.md", root)
    assert path_within_root(root / "SKILL.md", root)
