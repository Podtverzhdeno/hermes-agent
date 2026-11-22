"""Tier-0 routing harness integration and on-disk snapshot invalidation."""

import yaml

from agent.prompt_builder import (
    _SKILLS_SNAPSHOT_VERSION,
    _build_skills_manifest,
    build_skills_system_prompt,
    clear_skills_system_prompt_cache,
)


def _make_skill(home, *, with_manifest=True):
    skill_dir = home / "skills" / "research" / "pilot-research"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: pilot-research\n"
        "description: Investigate specific research papers.\n---\n\n"
        "# Research\nVerify the primary sources.\n",
        encoding="utf-8",
    )
    if with_manifest:
        spec = {
            "schema_version": 1,
            "skill": "pilot-research",
            "activation": {
                "when": ["Verify a published paper's actual results"],
                "not_when": ["Write a fictional story without source checking"],
            },
            "capabilities": {
                "tools": ["web_search"], "side_effects": "none",
                "approval_required": [],
            },
            "lifecycle": {
                k: [k.title()] for k in ("preflight", "execute", "verify", "recover")
            },
            "budget": {"max_tool_calls": 8, "max_reference_bytes": 2048},
            "evidence": {"required": ["Verified paper URL"]},
            "output": {
                "format": "Primary-source review",
                "acceptance": ["No invented publications"],
            },
        }
        (skill_dir / "harness.yaml").write_text(
            yaml.safe_dump(spec), encoding="utf-8"
        )
    return skill_dir


def test_prompt_index_discloses_short_negative_trigger(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    clear_skills_system_prompt_cache(clear_snapshot=True)
    _make_skill(tmp_path)
    try:
        index = build_skills_system_prompt()
        assert "pilot-research" in index
        assert "Use: Verify a published paper" in index
        assert "Avoid: Write a fictional story" in index
        assert "max_tool_calls" not in index
    finally:
        clear_skills_system_prompt_cache(clear_snapshot=True)


def test_legacy_skill_still_indexed_without_extra_hints(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    clear_skills_system_prompt_cache(clear_snapshot=True)
    _make_skill(tmp_path, with_manifest=False)
    try:
        index = build_skills_system_prompt()
        assert "pilot-research" in index
        assert "Use:" not in index
        assert "Avoid:" not in index
    finally:
        clear_skills_system_prompt_cache(clear_snapshot=True)


def test_invalid_existing_harness_hidden_from_startup_index(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    clear_skills_system_prompt_cache(clear_snapshot=True)
    skill = _make_skill(tmp_path)
    (skill / "harness.yaml").write_text(
        "schema_version: 1\nschema_version: 2\n", encoding="utf-8"
    )
    try:
        index = build_skills_system_prompt()
        assert "pilot-research" not in index
    finally:
        clear_skills_system_prompt_cache(clear_snapshot=True)


def test_manifest_participates_in_snapshot_fingerprint(tmp_path):
    skill = _make_skill(tmp_path)
    first = _build_skills_manifest(tmp_path / "skills")
    assert "research/pilot-research/harness.yaml" in first
    assert _SKILLS_SNAPSHOT_VERSION >= 2
    harness = skill / "harness.yaml"
    harness.write_text(harness.read_text() + "# changed\n", encoding="utf-8")
    second = _build_skills_manifest(tmp_path / "skills")
    assert second != first


def test_cached_disk_snapshot_uses_updated_harness_route(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    clear_skills_system_prompt_cache(clear_snapshot=True)
    skill = _make_skill(tmp_path)
    try:
        initial = build_skills_system_prompt()
        assert "fictional story" in initial
        harness = skill / "harness.yaml"
        spec = yaml.safe_load(harness.read_text())
        spec["activation"]["not_when"] = ["A different unrelated request"]
        harness.write_text(yaml.safe_dump(spec), encoding="utf-8")
        # Model context is session-stable; fresh session drops in-process LRU
        # but should see changed manifest fingerprint, not stale disk snapshot.
        clear_skills_system_prompt_cache(clear_snapshot=False)
        refreshed = build_skills_system_prompt()
        assert "A different unrelated request" in refreshed
        assert "fictional story" not in refreshed
    finally:
        clear_skills_system_prompt_cache(clear_snapshot=True)
