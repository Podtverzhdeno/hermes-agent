"""Per-skill execution contracts for Hermes Skills.

A skill document is instructional data, NOT a tool permission. Its sibling
harness.json provides testable routing, an execution checklist, risk and
evidence requirements. This module never executes tools, authorizes actions,
calls models or validates the authenticity of evidence.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any
import hashlib
import json
import re

HARNESS_FILENAME = "harness.json"
SCHEMA_VERSION = 1
MAX_PROFILE_BYTES = 32768
_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_RISKS = ("read_only", "local_write", "external_write", "critical")
_APPROVAL = {
    "read_only": "none",
    "local_write": "scoped",
    "external_write": "owner_exact",
    "critical": "owner_exact_and_secondary",
}
_SOURCES = frozenset(("git", "ci", "local_test", "artifact", "remote_api",
                      "human", "citation", "file_hash", "model_eval"))
_KEYS = frozenset(("schema_version", "skill", "purpose", "risk", "routing",
                   "preflight", "workflow", "actions", "evidence", "failure_modes"))


class SkillHarnessError(ValueError):
    """Invalid or unsafe individual skill harness."""


def _unique_pairs(pairs):
    out = {}
    for key, val in pairs:
        if key in out:
            raise SkillHarnessError("duplicate JSON key: " + key)
        out[key] = val
    return out


def _line(value: Any, name: str, max_chars: int = 240) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise SkillHarnessError(name + ": expected nonempty trimmed string")
    if len(value) > max_chars or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise SkillHarnessError(name + ": control character or excessive length")
    return value


def _lines(items: Any, name: str, minimum: int = 1, maximum: int = 12):
    if not isinstance(items, list) or not minimum <= len(items) <= maximum:
        raise SkillHarnessError(name + ": invalid list size")
    values = [_line(v, name) for v in items]
    if len(set(v.casefold() for v in values)) != len(values):
        raise SkillHarnessError(name + ": duplicated values")
    return values


def validate_harness(profile: Any, expected_skill: str) -> dict:
    """Versioned strict schema; unknown keys and risk understatements fail."""
    optional = {"skill_git_blob"}  # Drift check, NOT a trust signature.
    if (not isinstance(profile, dict) or not _KEYS.issubset(profile)
            or set(profile) - _KEYS - optional):
        raise SkillHarnessError("harness must contain exactly the supported v1 keys")
    if "skill_git_blob" in profile:
        blob = profile["skill_git_blob"]
        if not isinstance(blob, str) or not re.fullmatch(r"[0-9a-f]{40}", blob):
            raise SkillHarnessError("invalid Git blob fingerprint")
    if type(profile["schema_version"]) is not int or profile["schema_version"] != 1:
        raise SkillHarnessError("unsupported harness version")
    if not isinstance(profile["skill"], str) or not _NAME.fullmatch(profile["skill"]):
        raise SkillHarnessError("invalid skill name")
    if profile["skill"] != expected_skill:
        raise SkillHarnessError("harness identity does not match skill")
    _line(profile["purpose"], "purpose")
    if profile["risk"] not in _RISKS:
        raise SkillHarnessError("invalid risk level")

    router = profile["routing"]
    if not isinstance(router, dict) or set(router) != {"trigger", "do_not_trigger"}:
        raise SkillHarnessError("router must contain positive and negative cases")
    positive = _lines(router["trigger"], "routing.trigger", 2)
    negative = _lines(router["do_not_trigger"], "routing.do_not_trigger", 2)
    if set(x.casefold() for x in positive) & set(x.casefold() for x in negative):
        raise SkillHarnessError("contradictory routing fixtures")

    _lines(profile["preflight"], "preflight", 2, 10)
    _lines(profile["workflow"], "workflow", 2, 12)
    _lines(profile["failure_modes"], "failure_modes", 2, 10)

    actions = profile["actions"]
    if not isinstance(actions, list) or not 1 <= len(actions) <= 16:
        raise SkillHarnessError("invalid action list")
    seen = set()
    requirements = []
    highest = "read_only"
    for action in actions:
        if not isinstance(action, dict) or set(action) != {"operation", "risk", "approval", "requires_evidence"}:
            raise SkillHarnessError("invalid action shape")
        op = _line(action["operation"], "operation", 96)
        if op in seen:
            raise SkillHarnessError("duplicate operation")
        seen.add(op)
        names = _lines(action["requires_evidence"], "requires_evidence", 1, 12)
        if not all(_NAME.fullmatch(name) for name in names):
            raise SkillHarnessError("invalid evidence ID in action")
        requirements.extend(names)
        risk = action["risk"]
        if risk not in _RISKS or action["approval"] != _APPROVAL.get(risk):
            raise SkillHarnessError("inconsistent approval for action risk")
        if _RISKS.index(risk) > _RISKS.index(highest):
            highest = risk
    if highest != profile["risk"]:
        raise SkillHarnessError("profile must declare its highest action risk")

    evidence = profile["evidence"]
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 12:
        raise SkillHarnessError("invalid evidence list")
    seen = set()
    for e in evidence:
        if not isinstance(e, dict) or set(e) != {"id", "source", "how_to_verify"}:
            raise SkillHarnessError("invalid evidence contract")
        key = e["id"]
        if not isinstance(key, str) or not _NAME.fullmatch(key) or key in seen:
            raise SkillHarnessError("invalid or repeated evidence identifier")
        seen.add(key)
        if e["source"] not in _SOURCES:
            raise SkillHarnessError("invalid evidence source")
        _line(e["how_to_verify"], "how_to_verify")
    if not set(requirements).issubset(seen):
        raise SkillHarnessError("action references unknown evidence")
    return profile


def load_skill_harness(skill_dir: Path | None, expected_skill: str) -> dict | None:
    """Read a bounded non-symlink sibling file; do not silently bypass invalid profiles."""
    if skill_dir is None:
        return None
    root = Path(skill_dir)
    path = root / HARNESS_FILENAME
    if path.is_symlink():
        raise SkillHarnessError("harness.json symlink forbidden")
    if not path.exists():
        return None
    if not path.is_file():
        raise SkillHarnessError("harness.json must be regular")
    try:
        if not path.resolve().is_relative_to(root.resolve()):
            raise SkillHarnessError("harness.json escapes skill directory")
        if path.stat().st_size > MAX_PROFILE_BYTES:
            raise SkillHarnessError("harness.json exceeds byte limit")
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SkillHarnessError("unable to load harness.json: " + type(exc).__name__) from exc
    profile = validate_harness(data, expected_skill)
    if "skill_git_blob" in profile:
        skill_md = root / "SKILL.md"
        if skill_md.is_symlink():
            raise SkillHarnessError("SKILL.md symlink forbidden for pinned harness")
        try:
            raw = skill_md.read_bytes()
        except OSError as exc:
            raise SkillHarnessError("unable to read pinned SKILL.md") from exc
        # The Git blob hash is a *version consistency check*, not an
        # authenticity guarantee. Never use it to authorize a tool.
        def git_blob_hash(payload: bytes) -> str:
            return hashlib.sha1(
                b"blob " + str(len(payload)).encode("ascii") + b"\x00" + payload
            ).hexdigest()
        # Some Windows checkouts convert LF to CRLF. Markdown has the same
        # semantics under either line ending; compare both byte variants.
        expected = profile["skill_git_blob"]
        actual = git_blob_hash(raw)
        normalized = git_blob_hash(raw.replace(b"\r\n", b"\n"))
        if expected not in (actual, normalized):
            raise SkillHarnessError(
                "SKILL.md changed since its harness was reviewed; "
                "revalidate the contract and renew its fingerprint"
            )
    return profile


def format_harness_guidance(profile: Mapping[str, Any]) -> str:
    """Bounded per-skill prompt note: guidance only, NEVER authorization."""
    validate_harness(dict(profile), profile["skill"])
    out = [
        "[Skill-specific harness: advisory quality checklist; not tool authorization]",
        "Skill: " + profile["skill"] + " | worst-case risk: " + profile["risk"],
        "Existing OS, sandbox, connector and human approval rules still apply.",
        "Preflight:",
    ]
    out.extend("- " + v for v in profile["preflight"])
    out.append("Procedure:")
    out.extend("- " + v for v in profile["workflow"])
    out.append("Operation-specific evidence gates:")
    out.extend("- " + a["operation"] + " (" + a["risk"] + ", " + a["approval"] + "): "
               + ", ".join(a["requires_evidence"]) for a in profile["actions"])
    out.append("Evidence verification methods:")
    out.extend("- " + e["id"] + " [" + e["source"] + "]: " + e["how_to_verify"]
               for e in profile["evidence"])
    out.append("On failure:")
    out.extend("- " + v for v in profile["failure_modes"])
    out.append("Never self-certify success or fabricate a receipt. If unavailable, report blocked.")
    return "\n".join(out)


def assess_evidence_shape(profile: Mapping[str, Any], revision: str,
                          records: list[dict], *, operation: str) -> dict:
    """Schema check ONLY. Candidate records might be model-forged.

    A trusted verifier MUST re-fetch evidence independently, check actor,
    content and revision, before marking a task done. This function never
    returns authenticated or task_complete = True.
    """
    validate_harness(dict(profile), profile["skill"])
    if not isinstance(revision, str) or not revision.strip() or len(revision) > 256:
        raise SkillHarnessError("exact revision required")
    if not isinstance(records, list) or len(records) > 100:
        raise SkillHarnessError("invalid evidence records")
    action = next((a for a in profile["actions"] if a["operation"] == operation), None)
    if action is None:
        raise SkillHarnessError("unknown operation; no evidence gate can be satisfied")
    evidence_sources = {e["id"]: e["source"] for e in profile["evidence"]}
    required = {name: evidence_sources[name] for name in action["requires_evidence"]}
    passed, stale, wrong, failed = set(), set(), set(), set()
    for record in records:
        if not isinstance(record, dict):
            raise SkillHarnessError("invalid evidence record")
        key = record.get("id")
        if key not in required:
            continue
        if record.get("revision") != revision:
            stale.add(key)
        elif record.get("source") != required[key]:
            wrong.add(key)
        elif record.get("conclusion") != "passed":
            failed.add(key)
        else:
            passed.add(key)
    accepted = passed - stale - wrong - failed
    missing = sorted(set(required) - accepted)
    return {
        "schema_version": 1,
        "skill": profile["skill"],
        "operation": operation,
        "satisfied_by_structure": sorted(accepted),
        "missing_or_conflicting": missing,
        "stale": sorted(stale),
        "wrong_source": sorted(wrong),
        "failed": sorted(failed),
        "shape_complete": not missing,
        "authenticated": False,
        "task_complete": False,
        "note": "Requires independent trusted verification; structure alone is not proof.",
    }
