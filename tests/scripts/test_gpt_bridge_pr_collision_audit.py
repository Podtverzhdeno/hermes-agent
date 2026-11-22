from __future__ import annotations

import unittest

from scripts.gpt_bridge_pr_collision_audit import check_snapshot, InvalidSnapshot

BASE = "a" * 40


def pr(n, files, *, checks=None, head=None, base=BASE, draft=True):
    head = head or f"{n % 10}" * 40
    return {"number": n, "head_sha": head, "base_sha": base, "files": files,
            "draft": draft, "checks": checks or []}


class TestPRCollision(unittest.TestCase):
    def test_conflict_api_server_three_workers(self):
        rows = [pr(n, ["gateway/platforms/api_server.py", f"docs/{n}.md"]) for n in [4, 5, 6]]
        report = check_snapshot({"base_sha": BASE, "pull_requests": rows})
        self.assertEqual(len(report["overlap_edges"]), 3)
        self.assertEqual(report["collisions"][0]["severity"], "critical")
        self.assertFalse(report["automerge_allowed"])
        self.assertEqual(report["pull_requests"]["4"]["merge_gate"], "blocked_overlap")

    def test_distinct_files_do_not_mean_automatic_merge(self):
        head = "f" * 40
        checks = [{"name": "test", "head_sha": head, "status": "completed", "conclusion": "success"}]
        report = check_snapshot({"base_sha": BASE, "pull_requests": [pr(1, ["a.py"], head=head, checks=checks, draft=False)], "required_checks": ["test"]})
        self.assertTrue(report["pull_requests"]["1"]["checks_ok"])
        self.assertEqual(report["pull_requests"]["1"]["merge_gate"], "manual_review_still_required")
        self.assertFalse(report["automerge_allowed"])

    def test_outdated_success_check_is_not_green(self):
        checks = [{"name": "test", "head_sha": "a" * 40, "status": "completed", "conclusion": "success"}]
        report = check_snapshot({"base_sha": BASE, "pull_requests": [pr(1, ["x.py"], checks=checks, draft=False)]})
        self.assertFalse(report["pull_requests"]["1"]["checks_ok"])

    def test_cancelled_and_skipped_are_not_proof(self):
        for conclusion in ["cancelled", "skipped", "neutral", "failure"]:
            checks = [{"name": "test", "head_sha": "1" * 40,
                       "status": "completed", "conclusion": conclusion}]
            report = check_snapshot({"base_sha": BASE,
                                     "pull_requests": [pr(1, ["x.py"], checks=checks, draft=False)]})
            self.assertFalse(report["pull_requests"]["1"]["checks_ok"])

    def test_stale_base_blocks(self):
        report = check_snapshot({"base_sha": BASE,
                                 "pull_requests": [pr(1, ["a.py"], base="b" * 40)]})
        self.assertTrue(report["pull_requests"]["1"]["stale_base"])

    def test_reject_path_traversal(self):
        with self.assertRaises(InvalidSnapshot):
            check_snapshot({"base_sha": BASE, "pull_requests": [pr(1, ["docs/../secrets"]) ]})

    def test_unhashable_status_and_conclusion_fail_closed(self):
        head = "f" * 40
        for key in ("status", "conclusion"):
            check = {"name": "test", "head_sha": head, "status": "completed", "conclusion": "success"}
            check[key] = ["completed"]
            with self.assertRaises(InvalidSnapshot):
                check_snapshot({"base_sha": BASE, "pull_requests": [pr(1, ["a.py"], head=head, checks=[check])]})

    def test_check_name_disallows_obvious_sensitive_content(self):
        check = {"name": "authorization secret", "head_sha": "f" * 40,
                 "status": "completed", "conclusion": "success"}
        with self.assertRaises(InvalidSnapshot):
            check_snapshot({"base_sha": BASE, "pull_requests": [pr(1, ["a.py"], head="f" * 40, checks=[check])]})

    def test_windows_case_insensitive_alias_between_agents(self):
        rows = [pr(1, ["docs/Case.md"]), pr(2, ["docs/case.md"])]
        report = check_snapshot({"base_sha": BASE, "pull_requests": rows})
        self.assertEqual(report["overlap_edges"], [[1, 2]])
        self.assertIn("POSSIBLE_WINDOWS_CASE_ALIAS", [x.get("reason") for x in report["collisions"]])
        self.assertFalse(report["automerge_allowed"])

    def test_directory_file_prefix_conflict(self):
        rows = [pr(1, ["docs/notes"]), pr(2, ["docs/notes/idea.md"])]
        report = check_snapshot({"base_sha": BASE, "pull_requests": rows})
        self.assertEqual(report["overlap_edges"], [[1, 2]])
        self.assertIn("FILE_DIRECTORY_PREFIX_CONFLICT", [x.get("reason") for x in report["collisions"]])

    def test_different_root_names_no_false_alias(self):
        rows = [pr(1, ["docs/alpha.md"]), pr(2, ["docs/beta.md"])]
        report = check_snapshot({"base_sha": BASE, "pull_requests": rows})
        self.assertEqual(report["collisions"], [])


    def test_supply_scan_alone_cannot_make_suite_green(self):
        head = "f" * 40
        checks = [{"name": "Scan PR for supply chain risks", "head_sha": head,
                   "status": "completed", "conclusion": "success"}]
        report = check_snapshot({"base_sha": BASE,
                                 "pull_requests": [pr(1, ["x.py"], head=head, checks=checks, draft=False)]})
        self.assertTrue(report["pull_requests"]["1"]["observed_checks_all_success"])
        self.assertFalse(report["pull_requests"]["1"]["checks_ok"])
        self.assertEqual(report["pull_requests"]["1"]["merge_gate"], "blocked_checks_or_draft")

    def test_required_job_missing_refuses_green_even_if_scan_passes(self):
        head = "1" * 40
        checks = [{"name": "Scan PR for supply chain risks", "head_sha": head,
                   "status": "completed", "conclusion": "success"}]
        report = check_snapshot({"base_sha": BASE,
                                 "pull_requests": [pr(1, ["x.py"], head=head, checks=checks, draft=False)],
                                 "required_checks": ["test"]})
        self.assertEqual(report["pull_requests"]["1"]["required_checks_missing"], ["test"])
        self.assertFalse(report["pull_requests"]["1"]["checks_ok"])

    def test_duplicate_same_name_job_failure_invalidates_green(self):
        head = "1" * 40
        checks = [{"name": "test", "head_sha": head, "status": "completed", "conclusion": "success"},
                  {"name": "test", "head_sha": head, "status": "completed", "conclusion": "failure"}]
        report = check_snapshot({"base_sha": BASE,
                                 "pull_requests": [pr(1, ["x.py"], head=head, checks=checks, draft=False)],
                                 "required_checks": ["test"]})
        self.assertFalse(report["pull_requests"]["1"]["checks_ok"])

    def test_bad_required_policy_fails_closed(self):
        for invalid in [["test", "test"], [7], "test", ["authorization secret"]]:
            with self.assertRaises(InvalidSnapshot):
                check_snapshot({"base_sha": BASE, "pull_requests": [], "required_checks": invalid})

    def test_100_agents_overlapping_10_files(self):
        rows = [pr(n, [f"gateway/file_{n%10}.py"]) for n in range(1, 101)]
        report = check_snapshot({"base_sha": BASE, "pull_requests": rows})
        self.assertEqual(report["pr_count"], 100)
        self.assertEqual(len(report["collisions"]), 10)
        self.assertFalse(report["automerge_allowed"])


if __name__ == "__main__":
    unittest.main()
