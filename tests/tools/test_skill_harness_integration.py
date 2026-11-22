"""End-to-end skill_view safety and harness attachment regressions."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from tools.skills_tool import skill_view


BASE_SKILL = "---\nname: demo-skill\ndescription: Contract test\n---\n\n# Demo Skill\nTest.\n"


@pytest.fixture
def skill_layout(tmp_path):
    root = tmp_path / "skills"
    target = root / "demo-skill"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text(BASE_SKILL, encoding="utf-8")
    with patch("tools.skills_tool.SKILLS_DIR", root):
        yield root, target


def test_legacy_skill_works_without_harness(skill_layout):
    out = json.loads(skill_view("demo-skill"))
    assert out["success"] is True
    assert out["harness_status"] == "legacy"
    assert out["harness"] is None


def test_valid_manifest_reaches_skill_view(skill_layout):
    _, target = skill_layout
    spec = {
        "schema_version": 1, "skill": "demo-skill",
        "activation": {"when": ["Inspect test"], "not_when": ["No inspection"]},
        "capabilities": {"tools": ["read_file"], "side_effects": "none",
                         "approval_required": []},
        "lifecycle": {
            "preflight": ["Inspect baseline"], "execute": ["Read code"],
            "verify": ["Check result"], "recover": ["Report limitations"],
        },
        "budget": {"max_tool_calls": 12, "max_reference_bytes": 16384},
        "evidence": {"required": ["File and line"]},
        "output": {"format": "Review", "acceptance": ["No invented tests"]},
    }
    (target / "harness.yaml").write_text(yaml.safe_dump(spec), encoding="utf-8")
    out = json.loads(skill_view("demo-skill"))
    assert out["success"] is True
    assert out["harness_status"] == "declared"
    assert out["harness"]["enforcement"] == "advisory_only"


def test_invalid_manifest_fails_before_skill_read(skill_layout):
    _, target = skill_layout
    (target / "harness.yaml").write_text("schema_version: [invalid", encoding="utf-8")
    out = json.loads(skill_view("demo-skill"))
    assert out["success"] is False
    assert out["harness_status"] == "invalid"


def test_invalid_manifest_blocks_linked_file_read(skill_layout):
    _, target = skill_layout
    refs = target / "references"
    refs.mkdir()
    (refs / "secret.md").write_text("local reference", encoding="utf-8")
    (target / "harness.yaml").write_text("invalid: true\n", encoding="utf-8")
    out = json.loads(skill_view("demo-skill", file_path="references/secret.md"))
    assert out["success"] is False
    assert out["harness_status"] == "invalid"


def test_absolute_skill_name_cannot_read_outside_root(skill_layout, tmp_path):
    _, _target = skill_layout
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "SKILL.md").write_text(
        "---\nname: outside\ndescription: secret\n---\n\nPRIVATE MARKER",
        encoding="utf-8",
    )
    out = json.loads(skill_view(str(outside)))
    assert out["success"] is False
    assert "PRIVATE MARKER" not in json.dumps(out)


def test_traversal_skill_name_rejected_before_disk_access(skill_layout, tmp_path):
    (tmp_path / "hidden.md").write_text("PRIVATE MARKER", encoding="utf-8")
    out = json.loads(skill_view("../hidden"))
    assert out["success"] is False
    assert "PRIVATE MARKER" not in json.dumps(out)


def test_external_symlink_is_not_followed(skill_layout, tmp_path):
    root, _target = skill_layout
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "SKILL.md").write_text(
        "---\nname: link-skill\ndescription: secret\n---\n\nPRIVATE MARKER",
        encoding="utf-8",
    )
    link = root / "link-skill"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Host does not allow symlinks")
    out = json.loads(skill_view("link-skill"))
    assert out["success"] is False
    assert "PRIVATE MARKER" not in json.dumps(out)
