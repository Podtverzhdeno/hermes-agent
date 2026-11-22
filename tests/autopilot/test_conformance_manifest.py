"""Validate proposed cross-component acceptance fixtures, without making tool calls.

This test validates only the manifest's structure, NOT runtime pass/fail
behavior of CDP, upstream Kanban, GitHub, Obsidian or remote providers.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "docs/autopilot/INTEGRATION_CONFORMANCE_V1.json"


def test_conformance_manifest_has_unique_negative_assertions():
    document = json.loads(SPEC.read_text(encoding="utf-8"))
    assert document["contract_id"] == "hermes-gpt-integration-conformance.v1"
    assert document["status"] == "proposal_not_live_runtime_validation"
    assert document["source_of_task_truth"] == "modern_upstream_hermes_kanban_only"
    cases = document["cases"]
    assert len(cases) == 32
    ids = [case["id"] for case in cases]
    assert ids == [f"C{i:02d}" for i in range(1, 33)]
    assert len(ids) == len(set(ids))
    required = {"id", "component", "scenario", "expected_decision",
                "reason_code", "forbidden", "evidence_requirement"}
    for c in cases:
        assert set(c) == required
        assert all(isinstance(v, str) and v.strip() for v in c.values())
        assert re.fullmatch(r"[A-Z][A-Z0-9_]{2,80}", c["reason_code"])
        assert c["expected_decision"] in {
            "REJECT", "WAIT", "BLOCK", "QUARANTINE", "RECONCILE",
            "DIAGNOSE", "IDEMPOTENT", "DETACH_ONLY", "REDACT",
            "REVIEW", "RETRY_SCAN", "REVERIFY", "UNKNOWN",
        }


def test_manifest_never_claims_unverified_live_coverage():
    document = json.loads(SPEC.read_text(encoding="utf-8"))
    assert document["authority"] == "offline_review_fixtures_only"
    for c in document["cases"]:
        assert c["forbidden"].startswith("do_not_") or c["forbidden"] in {
            "allow_only_same_digest_with_new_valid_approval",
            "stop_new_effects_and_reconcile_old",
        }
    assert any(x["reason_code"] == "EXTERNAL_EFFECT_UNCERTAIN"
               for x in document["cases"])
    assert any(x["reason_code"] == "CI_RUNNER_UNASSIGNED"
               for x in document["cases"])
