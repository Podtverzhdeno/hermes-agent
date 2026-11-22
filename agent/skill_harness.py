"""Validated, advisory execution contracts for Hermes skills.

A harness manifest describes *expected* workflow and evidence. It never grants
permissions, installs dependencies or silently authorizes tool execution.
Actual capabilities remain subject to the Hermes tool/security policies.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

MAX_MANIFEST_BYTES = 32 * 1024
MAX_LOOKUP_NAME_LENGTH = 256
_ALLOWED_EFFECTS = frozenset(("none", "local_write", "external_write"))
_ALLOWED_KEYS = frozenset(
    ("schema_version", "skill", "activation", "capabilities", "lifecycle",
     "budget", "evidence", "output")
)
_PHASES = ("preflight", "execute", "verify", "recover")


class SkillHarnessError(ValueError):
    """A harness contract cannot be safely loaded or validated."""


def validate_skill_lookup_name(name: str) -> Optional[str]:
    """Reject absolute paths, traversal and glob injection in skill lookup names.

    Supports legacy category/subcategory/skill and flat .md names.
    """
    if not isinstance(name, str) or not name or len(name) > MAX_LOOKUP_NAME_LENGTH:
        return "Skill name must be a nonempty string of at most 256 characters."
    if name.startswith("/") or "\\" in name or "\x00" in name:
        return "Skill name must be a relative POSIX path without backslashes."
    segments = name.split("/")
    if any(
        segment in ("", ".", "..")
        or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9._-]*", segment)
        for segment in segments
    ):
        return "Skill name contains an unsafe path component."
    return None


def path_within_root(candidate: Path, root: Path) -> bool:
    """Canonical containment check; also refuses symlinks escaping the root."""
    try:
        return candidate.resolve().is_relative_to(root.resolve())
    except (OSError, ValueError, RuntimeError):
        return False


def _strings(container: Dict[str, Any], field: str, *, required: bool = True,
             minimum: int = 1, maximum: int = 16) -> list[str]:
    value = container.get(field)
    if value is None and not required:
        return []
    if not isinstance(value, list) or not (minimum <= len(value) <= maximum):
        raise SkillHarnessError(
            f"'{field}' must be a list containing {minimum}..{maximum} entries"
        )
    if any(not isinstance(item, str) or not item.strip()
           or len(item) > 300 for item in value):
        raise SkillHarnessError(
            f"'{field}' entries must be nonempty strings of at most 300 characters"
        )
    stripped = [item.strip() for item in value]
    if len({item.casefold() for item in stripped}) != len(stripped):
        raise SkillHarnessError(f"'{field}' has duplicate entries")
    return stripped


def _section(raw: Dict[str, Any], name: str, allowed: set[str]) -> Dict[str, Any]:
    section = raw.get(name)
    if not isinstance(section, dict):
        raise SkillHarnessError(f"'{name}' must be a mapping")
    if set(section) - allowed:
        raise SkillHarnessError(f"Unknown '{name}' fields: {sorted(set(section) - allowed)}")
    return section


def validate_skill_harness(raw: Any, expected_name: str) -> Dict[str, Any]:
    """Validate shape, type and internal consistency; never execute directives."""
    if not isinstance(raw, dict):
        raise SkillHarnessError("Harness manifest must be a YAML mapping")
    if set(raw) - _ALLOWED_KEYS:
        raise SkillHarnessError(f"Unknown harness fields: {sorted(set(raw) - _ALLOWED_KEYS)}")
    if type(raw.get("schema_version")) is not int or raw["schema_version"] != 1:
        raise SkillHarnessError("Unsupported harness schema_version (expected 1)")
    if raw.get("skill") != expected_name:
        raise SkillHarnessError("Harness 'skill' must exactly match SKILL.md name")

    activation = _section(raw, "activation", {"when", "not_when"})
    when = _strings(activation, "when", maximum=12)
    not_when = _strings(activation, "not_when", maximum=12)
    if set(map(str.casefold, when)) & set(map(str.casefold, not_when)):
        raise SkillHarnessError("Activation and exclusion conditions overlap")

    capabilities = _section(raw, "capabilities",
                            {"tools", "side_effects", "approval_required"})
    tools = _strings(capabilities, "tools", required=False, minimum=0)
    side_effects = capabilities.get("side_effects")
    if side_effects not in _ALLOWED_EFFECTS:
        raise SkillHarnessError("Invalid capabilities.side_effects")
    approvals = _strings(
        capabilities, "approval_required", required=False, minimum=0
    )
    if side_effects == "external_write" and not approvals:
        raise SkillHarnessError("External writes require explicit approval conditions")

    lifecycle = _section(raw, "lifecycle", set(_PHASES))
    phases = {phase: _strings(lifecycle, phase, maximum=12) for phase in _PHASES}

    budget = _section(raw, "budget", {"max_tool_calls", "max_reference_bytes"})
    max_calls = budget.get("max_tool_calls")
    max_reference = budget.get("max_reference_bytes")
    if type(max_calls) is not int or not 1 <= max_calls <= 200:
        raise SkillHarnessError("budget.max_tool_calls must be an integer in 1..200")
    if type(max_reference) is not int or not 1024 <= max_reference <= 1048576:
        raise SkillHarnessError(
            "budget.max_reference_bytes must be an integer in 1024..1048576"
        )

    evidence = _section(raw, "evidence", {"required"})
    required_evidence = _strings(evidence, "required", maximum=12)
    output = _section(raw, "output", {"format", "acceptance"})
    fmt = output.get("format")
    if not isinstance(fmt, str) or not fmt.strip() or len(fmt) > 120:
        raise SkillHarnessError("output.format must be a short nonempty string")
    acceptance = _strings(output, "acceptance", maximum=12)

    return {
        "schema_version": 1,
        "skill": expected_name,
        "activation": {"when": when, "not_when": not_when},
        "capabilities": {
            "tools": tools, "side_effects": side_effects,
            "approval_required": approvals,
        },
        "lifecycle": phases,
        "budget": {
            "max_tool_calls": max_calls,
            "max_reference_bytes": max_reference,
        },
        "evidence": {"required": required_evidence},
        "output": {"format": fmt.strip(), "acceptance": acceptance},
        "enforcement": "advisory_only",
        "security_notice": (
            "The manifest is procedural guidance, NOT a tool permission grant "
            "or security sandbox; host tool permissions and approvals take precedence."
        ),
    }


def load_skill_harness(skill_dir: Path, expected_name: str) -> Optional[Dict[str, Any]]:
    """Return validated per-skill metadata or None for legacy skills.

    Fail closed when a manifest exists but is malformed, oversized or redirected.
    """
    path = skill_dir / "harness.yaml"
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink() or not path_within_root(path, skill_dir):
        raise SkillHarnessError("Harness manifest symlink/path escape is prohibited")
    if not path.is_file():
        raise SkillHarnessError("Harness manifest must be a regular file")
    try:
        if path.stat().st_size > MAX_MANIFEST_BYTES:
            raise SkillHarnessError("Harness manifest exceeds 32 KiB")
        content = path.read_text(encoding="utf-8")
        if len(content.encode("utf-8")) > MAX_MANIFEST_BYTES:
            raise SkillHarnessError("Harness manifest exceeds 32 KiB")
        parsed = yaml.safe_load(content)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise SkillHarnessError(f"Cannot parse harness manifest: {exc}") from exc
    return validate_skill_harness(parsed, expected_name)
