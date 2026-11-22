"""Validate the advisory, NOT an authoritative/auto-assigning, multi-agent SDD registry."""
import json
import unittest
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / "docs" / "sdd" / "GPT_WORKSTREAM_REGISTRY_A0_2026-11-22.json"

class RegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = json.loads(PATH.read_text(encoding="utf-8"))
        cls.items = cls.root["workstreams"]

    def test_schema_has_no_execution_or_merge_authority(self):
        self.assertEqual(self.root["schema_version"], 1)
        self.assertEqual(self.root["scope"], "ADVISORY_COORDINATION_ONLY")
        self.assertFalse(self.root["approved_for_execution"])
        self.assertFalse(self.root["approved_for_merge"])

    def test_canonical_authority_not_second_scheduler(self):
        self.assertEqual(self.root["authoritative_run_state"],
                         "HERMES_NATIVE_RUNS_AND_KANBAN_AFTER_VERIFIED_MIGRATION")

    def test_workstream_ids_unique_and_nonempty(self):
        ids = [s["id"] for s in self.items]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(isinstance(s["id"], str) and s["id"] for s in self.items))

    def test_every_owner_starts_unapproved(self):
        for item in self.items:
            self.assertIsNone(item["owner"])
            self.assertFalse(item["owner_approved"])
            self.assertIsNone(item["chosen_candidate_pr"])
            self.assertEqual(item["verification_status"], "NOT_VERIFIED")

    def test_candidate_prs_are_positive_int_and_deduplicated(self):
        for item in self.items:
            candidates = item["candidate_prs"]
            self.assertEqual(len(candidates), len(set(candidates)))
            self.assertTrue(all(type(n) is int and 1 <= n <= self.root["snapshot_open_pr_count"]
                                for n in candidates))

    def test_dependencies_exist_and_acyclic(self):
        items = {x["id"]: x for x in self.items}
        def visit(name, visiting, visited):
            self.assertIn(name, items)
            self.assertNotIn(name, visiting)
            if name in visited:
                return
            visiting.add(name)
            for dep in items[name]["release_dependencies"]:
                visit(dep, visiting, visited)
            visiting.remove(name)
            visited.add(name)
        visited = set()
        for name in items:
            visit(name, set(), visited)

    def test_release_requires_every_other_gate(self):
        items = {x["id"]: x for x in self.items}
        release = items["W09_RELEASE_VERIFICATION"]
        self.assertEqual(set(release["release_dependencies"]),
                         set(items) - {"W09_RELEASE_VERIFICATION"})

    def test_browser_and_authority_are_separate_domains(self):
        items = {x["id"]: x for x in self.items}
        self.assertNotEqual(items["W03_BROWSER_CDP"]["domain"],
                            items["W01_NATIVE_RUNS_MIGRATION"]["domain"])
        self.assertIn("W01_NATIVE_RUNS_MIGRATION",
                      items["W08_ISOLATED_GPT_CONTROL_CENTER"]["release_dependencies"])

    def test_pinned_sources_are_exact_hashes(self):
        self.assertEqual(len(self.root["existing_fork_sha"]), 40)
        self.assertEqual(len(self.root["candidate_upstream_commit"]), 40)
        self.assertEqual(self.root["candidate_upstream_release"], "v0.23.3")

    def test_unassigned_gpt_frontend_blocks_release(self):
        items = {x["id"]: x for x in self.items}
        ui = items["W08_ISOLATED_GPT_CONTROL_CENTER"]
        self.assertEqual(ui["candidate_prs"], [])
        self.assertIsNone(ui["owner"])
        self.assertFalse(self.root["approved_for_execution"])

if __name__ == "__main__":
    unittest.main()
