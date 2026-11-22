"""Security scanner decisions must not silently bypass skill installation."""

from unittest.mock import patch

import pytest

from tools.skill_manager_tool import _create_skill, _edit_skill, _security_scan_skill


SKILL = "---\nname: demo\ndescription: Test\n---\n\n# Demo\nSafe steps.\n"
EDITED = "---\nname: demo\ndescription: Test\n---\n\n# Demo\nEdited steps.\n"


@pytest.fixture
def isolated(tmp_path):
    root = tmp_path / "skills"
    root.mkdir()
    with patch("tools.skill_manager_tool.SKILLS_DIR", root):
        yield root


def test_missing_scanner_blocks_create_and_rolls_back(isolated):
    with patch("tools.skill_manager_tool._GUARD_AVAILABLE", False):
        result = _create_skill("demo", SKILL)
    assert result["success"] is False
    assert "scanner unavailable" in result["error"]
    assert not (isolated / "demo").exists()


def test_needs_confirmation_blocks_create_and_rolls_back(isolated):
    with (
        patch("tools.skill_manager_tool._GUARD_AVAILABLE", True),
        patch("tools.skill_manager_tool.scan_skill", return_value=object()),
        patch("tools.skill_manager_tool.should_allow_install",
              return_value=(None, "dangerous source")),
        patch("tools.skill_manager_tool.format_scan_report",
              return_value="HIGH test finding"),
    ):
        result = _create_skill("demo", SKILL)
    assert result["success"] is False
    assert "requires explicit user review" in result["error"]
    assert "HIGH test finding" in result["error"]
    assert not (isolated / "demo").exists()


def test_scan_exception_blocks_create(isolated):
    with (
        patch("tools.skill_manager_tool._GUARD_AVAILABLE", True),
        patch("tools.skill_manager_tool.scan_skill",
              side_effect=RuntimeError("scan failed")),
    ):
        result = _create_skill("demo", SKILL)
    assert result["success"] is False
    assert "Security scan failed" in result["error"]
    assert not (isolated / "demo").exists()


def test_failed_security_scan_restores_existing_content(isolated):
    target = isolated / "demo"
    target.mkdir()
    path = target / "SKILL.md"
    path.write_text(SKILL, encoding="utf-8")
    with (
        patch("tools.skill_manager_tool._GUARD_AVAILABLE", True),
        patch("tools.skill_manager_tool.scan_skill", return_value=object()),
        patch("tools.skill_manager_tool.should_allow_install",
              return_value=(None, "dangerous source")),
        patch("tools.skill_manager_tool.format_scan_report", return_value="review"),
    ):
        result = _edit_skill("demo", EDITED)
    assert result["success"] is False
    assert path.read_text(encoding="utf-8") == SKILL
