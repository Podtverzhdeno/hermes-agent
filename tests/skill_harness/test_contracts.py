"""Pure-stdlib offline contracts for bundled, separately authored skill harnesses.

They test declarative validation, not an LLM's routing accuracy. Model
selection and real tool execution require an independent end-to-end eval.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from agent.skill_harness import (
    SkillHarnessError, assess_evidence_shape, format_harness_guidance,
    load_skill_harness, validate_harness,
)


ROOT = Path(__file__).resolve().parents[2]
PROFILES = (
    "skills/github/github-pr-workflow",
    "skills/github/github-code-review",
    "skills/github/github-issues",
    "skills/github/codebase-inspection",
    "skills/software-development/test-driven-development",
    "skills/software-development/systematic-debugging",
    "skills/software-development/subagent-driven-development",
    "skills/note-taking/obsidian",
    "skills/productivity/google-workspace",
    "skills/mlops/evaluation/lm-evaluation-harness",
    "skills/research/arxiv",
    "skills/mcp/native-mcp",
)


def example():
    return {
        "schema_version": 1,
        "skill": "my-skill",
        "purpose": "Create an artifact with independent verification.",
        "risk": "external_write",
        "routing": {
            "trigger": ["Publish the approved artifact", "Check its remote result"],
            "do_not_trigger": ["Make an offline diagram", "Delete all servers"],
        },
        "preflight": ["Pin exact target and revision.", "Check owner permissions."],
        "workflow": ["Prepare artifact without publishing.", "Verify outcome by read-back."],
        "actions": [
            {"operation": "inspect", "risk": "read_only", "approval": "none",
             "requires_evidence": ["remote-state"]},
            {"operation": "publish", "risk": "external_write", "approval": "owner_exact",
             "requires_evidence": ["remote-state", "owner-approval"]},
        ],
        "evidence": [
            {"id": "remote-state", "source": "remote_api",
             "how_to_verify": "Read exact target revision after the operation."},
            {"id": "owner-approval", "source": "human",
             "how_to_verify": "Record explicit approval bound to target and parameters."},
        ],
        "failure_modes": ["Do not retry ambiguous writes.", "Report blocked when API unavailable."],
    }


class TestBundledHarnesses(unittest.TestCase):
    def test_every_profile_is_individual_and_valid(self):
        names = set()
        trigger_cases, negative_cases = set(), set()
        for rel in PROFILES:
            with self.subTest(skill=rel):
                folder = ROOT / rel
                skill_doc = (folder / "SKILL.md").read_text(encoding="utf-8")
                self.assertTrue(skill_doc.startswith("---\n"))
                profile = json.loads((folder / "harness.json").read_text(encoding="utf-8"))
                self.assertIn("name: " + profile["skill"], skill_doc.split("---", 2)[1])
                self.assertEqual(load_skill_harness(folder, profile["skill"]), profile)
                self.assertNotIn(profile["skill"], names)
                names.add(profile["skill"])
                self.assertGreaterEqual(len(profile["routing"]["trigger"]), 2)
                self.assertGreaterEqual(len(profile["routing"]["do_not_trigger"]), 2)
                self.assertTrue(profile["failure_modes"])
                self.assertIn("not tool authorization", format_harness_guidance(profile))
                trigger_cases.update(profile["routing"]["trigger"])
                negative_cases.update(profile["routing"]["do_not_trigger"])
        self.assertEqual(len(names), len(PROFILES))
        self.assertFalse(trigger_cases & negative_cases)
        self.assertGreaterEqual(len(trigger_cases) + len(negative_cases), 48)

    def test_no_unprofiled_twin_for_same_skill(self):
        names = []
        for folder in PROFILES:
            profile = load_skill_harness(ROOT / folder,
                                         json.loads((ROOT / folder / "harness.json").read_text())["skill"])
            names.append(profile["skill"])
        self.assertEqual(len(names), len(set(names)))


class TestHarnessValidation(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate_harness(example(), "my-skill")["risk"], "external_write")

    def test_wrong_identity(self):
        with self.assertRaises(SkillHarnessError):
            validate_harness(example(), "different-skill")

    def test_unsupported_version(self):
        p = example()
        p["schema_version"] = 9
        with self.assertRaises(SkillHarnessError):
            validate_harness(p, "my-skill")

    def test_extra_key_rejected(self):
        p = example()
        p["autonomous_permissions"] = "allow_all"
        with self.assertRaises(SkillHarnessError):
            validate_harness(p, "my-skill")

    def test_contradictory_route(self):
        p = example()
        p["routing"]["do_not_trigger"][0] = p["routing"]["trigger"][0]
        with self.assertRaises(SkillHarnessError):
            validate_harness(p, "my-skill")

    def test_risk_cannot_be_underreported(self):
        p = example()
        p["risk"] = "read_only"
        with self.assertRaises(SkillHarnessError):
            validate_harness(p, "my-skill")

    def test_external_write_cannot_claim_no_approval(self):
        p = example()
        p["actions"][1]["approval"] = "none"
        with self.assertRaises(SkillHarnessError):
            validate_harness(p, "my-skill")

    def test_action_requirements_must_exist(self):
        p = example()
        p["actions"][1]["requires_evidence"] = ["fake-check"]
        with self.assertRaises(SkillHarnessError):
            validate_harness(p, "my-skill")

    def test_missing_file_is_backward_compatible(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(load_skill_harness(Path(tmp), "my-skill"))

    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "harness.json").write_text('{"skill":"one","skill":"two"}')
            with self.assertRaises(SkillHarnessError):
                load_skill_harness(folder, "one")

    def test_oversized_profile_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "harness.json").write_text("x" * 32769)
            with self.assertRaises(SkillHarnessError):
                load_skill_harness(folder, "my-skill")

    def test_symlink_profile_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            outside = folder / "external.json"
            outside.write_text(json.dumps(example()))
            linked = folder / "harness.json"
            try:
                linked.symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks not permitted on this host")
            with self.assertRaises(SkillHarnessError):
                load_skill_harness(folder, "my-skill")

    def test_unknown_action_is_not_accepted(self):
        with self.assertRaises(SkillHarnessError):
            assess_evidence_shape(example(), "git:one", [], operation="delete-everything")

    def test_evidence_is_bound_to_exact_operation(self):
        p = example()
        records = [{"id": "remote-state", "source": "remote_api",
                    "revision": "git:one", "conclusion": "passed"}]
        read = assess_evidence_shape(p, "git:one", records, operation="inspect")
        self.assertTrue(read["shape_complete"])
        publish = assess_evidence_shape(p, "git:one", records, operation="publish")
        self.assertFalse(publish["shape_complete"])
        self.assertEqual(publish["missing_or_conflicting"], ["owner-approval"])
        self.assertFalse(read["authenticated"])
        self.assertFalse(read["task_complete"])

    def test_stale_and_conflicting_evidence_fail(self):
        p = example()
        records = [
            {"id": "remote-state", "source": "remote_api",
             "revision": "git:one", "conclusion": "passed"},
            {"id": "remote-state", "source": "remote_api",
             "revision": "git:old", "conclusion": "passed"},
        ]
        result = assess_evidence_shape(p, "git:one", records, operation="inspect")
        self.assertFalse(result["shape_complete"])
        self.assertEqual(result["stale"], ["remote-state"])

    def test_wrong_source_and_failed_checks_fail(self):
        p = example()
        records = [{"id": "remote-state", "source": "model_eval",
                    "revision": "git:one", "conclusion": "passed"},
                   {"id": "remote-state", "source": "remote_api",
                    "revision": "git:one", "conclusion": "failed"}]
        result = assess_evidence_shape(p, "git:one", records, operation="inspect")
        self.assertFalse(result["shape_complete"])
        self.assertEqual(result["wrong_source"], ["remote-state"])
        self.assertEqual(result["failed"], ["remote-state"])

    def test_cannot_use_model_claim_to_certify_tool_result(self):
        p = example()
        forged = [
            {"id": "remote-state", "source": "remote_api",
             "revision": "git:one", "conclusion": "passed"},
            {"id": "owner-approval", "source": "human",
             "revision": "git:one", "conclusion": "passed"},
        ]
        result = assess_evidence_shape(p, "git:one", forged, operation="publish")
        # It may be structurally valid, but the function deliberately NEVER
        # certifies evidence. Production must independently retrieve receipts.
        self.assertTrue(result["shape_complete"])
        self.assertFalse(result["authenticated"])
        self.assertFalse(result["task_complete"])


if __name__ == "__main__":
    unittest.main()
