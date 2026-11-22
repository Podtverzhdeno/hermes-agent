"""Exercise the actual skill_view + slash invocation path with sibling harnesses."""
import json
import shutil
from pathlib import Path

import pytest

import agent.skill_utils as skill_utils
import tools.skills_tool as skills_tool
from agent.skill_commands import _build_skill_message, _load_skill_payload


REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def scratch_skills(tmp_path, monkeypatch):
    root = tmp_path / "skills"
    root.mkdir()
    source = REPO / "skills/research/arxiv"
    skill = root / "arxiv"
    skill.mkdir()
    shutil.copyfile(source / "SKILL.md", skill / "SKILL.md")
    shutil.copyfile(source / "harness.json", skill / "harness.json")
    monkeypatch.setattr(skills_tool, "SKILLS_DIR", root)
    monkeypatch.setattr(skill_utils, "get_external_skills_dirs", lambda: [])
    return skill


def test_skill_view_exposes_the_correct_profile(scratch_skills):
    result = json.loads(skills_tool.skill_view("arxiv"))
    assert result["success"], result
    assert result["name"] == "arxiv"
    harness = result["harness"]
    assert harness["skill"] == "arxiv"
    assert harness["risk"] == "read_only"
    assert harness["enforcement"].startswith("advisory_only")
    assert "Required independently checked evidence" in harness["guidance"]


def test_slash_invocation_keeps_individual_checklist(scratch_skills):
    payload = _load_skill_payload("arxiv")
    assert payload is not None
    data, skill_dir, name = payload
    message = _build_skill_message(
        data, skill_dir, "[Skill activation]", "Find credible papers."
    )
    assert "Skill-specific harness" in message
    assert "papers.search" in message
    assert "paper-metadata" in message
    assert "Find credible papers." in message
    assert message.count("[Skill-specific harness") == 1


def test_malformed_harness_blocks_skill_activation(scratch_skills):
    file = scratch_skills / "harness.json"
    value = json.loads(file.read_text(encoding="utf-8"))
    value["skill"] = "wrong-skill"
    file.write_text(json.dumps(value), encoding="utf-8")
    response = json.loads(skills_tool.skill_view("arxiv"))
    assert response["success"] is False
    assert "Invalid skill harness" in response["error"]
    assert _load_skill_payload("arxiv") is None


def test_unprofiled_legacy_skill_remains_available(scratch_skills):
    scratch_skills.joinpath("harness.json").unlink()
    response = json.loads(skills_tool.skill_view("arxiv"))
    assert response["success"] is True
    assert "harness" not in response


def test_reference_file_read_does_not_mutate_profile(scratch_skills):
    refs = scratch_skills / "references"
    refs.mkdir()
    (refs / "guide.md").write_text("Read-only helper.", encoding="utf-8")
    response = json.loads(skills_tool.skill_view("arxiv", "references/guide.md"))
    assert response["success"] is True
    assert response["content"] == "Read-only helper."
    assert "harness" not in response


@pytest.mark.parametrize("identifier", [
    "../secrets", "research/../../secrets", "./arxiv",
    "/tmp/arxiv", "C:\\Users\\test\\arxiv", "research\\arxiv",
    "research//arxiv", "arxiv\nbad",
])
def test_unsafe_identifier_is_refused_before_load(scratch_skills, identifier):
    response = json.loads(skills_tool.skill_view(identifier))
    assert response["success"] is False
    assert "Invalid skill identifier" in response["error"]


def test_malformed_profile_cannot_trigger_setup_capture(scratch_skills, monkeypatch):
    data = json.loads((scratch_skills / "harness.json").read_text())
    data["risk"] = "critical"  # under-/over-stated relative to action list
    (scratch_skills / "harness.json").write_text(json.dumps(data))
    def forbidden_capture(*args, **kwargs):
        raise AssertionError("Secret capture ran before harness validation")
    monkeypatch.setattr(skills_tool, "_capture_required_environment_variables",
                        forbidden_capture)
    result = json.loads(skills_tool.skill_view("arxiv"))
    assert result["success"] is False
    assert "Invalid skill harness" in result["error"]
