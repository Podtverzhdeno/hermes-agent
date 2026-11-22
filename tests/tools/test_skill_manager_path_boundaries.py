"""Symlink boundary regressions for agent-created skill mutations."""

from pathlib import Path
from unittest.mock import patch

import pytest

from tools.skill_manager_tool import (
    _create_skill, _patch_skill, _remove_file, _write_file,
)


SKILL = "---\nname: demo\ndescription: Demo\n---\n\n# Demo\nInstructions.\n"


@pytest.fixture
def isolated(tmp_path):
    skills = tmp_path / "skills"
    skills.mkdir()
    with patch("tools.skill_manager_tool.SKILLS_DIR", skills):
        yield skills, tmp_path


def _symlink(link, target, directory=False):
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError):
        pytest.skip("Host does not allow symlinks")


def test_create_rejects_category_symlink_to_outside(isolated):
    root, tmp = isolated
    outside = tmp / "external"
    outside.mkdir()
    _symlink(root / "outside", outside, directory=True)

    response = _create_skill("demo", SKILL, category="outside")
    assert response["success"] is False
    assert "escapes" in response["error"]
    assert not (outside / "demo" / "SKILL.md").exists()


def test_write_file_rejects_symlinked_reference_directory(isolated):
    root, tmp = isolated
    assert _create_skill("demo", SKILL)["success"] is True
    outside = tmp / "external"
    outside.mkdir()
    _symlink(root / "demo" / "references", outside, directory=True)

    response = _write_file("demo", "references/target.md", "PRIVATE")
    assert response["success"] is False
    assert not (outside / "target.md").exists()


def test_patch_rejects_symlink_to_external_secret(isolated):
    root, tmp = isolated
    assert _create_skill("demo", SKILL)["success"] is True
    outside = tmp / "private.txt"
    outside.write_text("PRIVATE CONTENT", encoding="utf-8")
    refs = root / "demo" / "references"
    refs.mkdir()
    _symlink(refs / "target.md", outside)

    response = _patch_skill("demo", "PRIVATE", "LEAKED",
                            file_path="references/target.md")
    assert response["success"] is False
    assert outside.read_text(encoding="utf-8") == "PRIVATE CONTENT"


def test_remove_rejects_symlink_to_external_secret(isolated):
    root, tmp = isolated
    assert _create_skill("demo", SKILL)["success"] is True
    outside = tmp / "private.txt"
    outside.write_text("KEEP", encoding="utf-8")
    refs = root / "demo" / "references"
    refs.mkdir()
    _symlink(refs / "target.md", outside)

    response = _remove_file("demo", "references/target.md")
    assert response["success"] is False
    assert outside.read_text(encoding="utf-8") == "KEEP"
