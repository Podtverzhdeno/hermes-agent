"""Deterministic scoring tests: no models, tools, network or real credentials."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.evaluate_specialized_skills import (
    SkillEvalError, create_casebook, read_jsonl, score_observations, wilson95,
)


ROOT = Path(__file__).resolve().parents[2]


def row(case, loaded, *, model="fake-lm", condition="with_skill",
        outcome="not_checked", cost_usd=0.0, tokens=0):
    return {
        "case_id": case["case_id"],
        "skill": case["skill"],
        "model": model,
        "condition": condition,
        "loaded": loaded,
        "outcome": outcome,
        "cost_usd": cost_usd,
        "tokens": tokens,
    }


class TestRoutingEvaluation(unittest.TestCase):
    def test_casebook_contains_both_directions_for_all_profiles(self):
        cases = create_casebook(ROOT)
        by_skill = {}
        for c in cases:
            by_skill.setdefault(c["skill"], {"trigger": 0, "do_not_trigger": 0})
            by_skill[c["skill"]][c["category"]] += 1
            self.assertEqual(c["expected_loaded"], c["category"] == "trigger")
        self.assertGreaterEqual(len(by_skill), 27)
        self.assertGreaterEqual(len(cases), 162)
        self.assertEqual(len({x["case_id"] for x in cases}), len(cases))
        self.assertTrue(all(x["trigger"] >= 2 and x["do_not_trigger"] >= 2
                            for x in by_skill.values()))

    def test_correct_and_incorrect_routing_is_counted(self):
        cases = [
            {"case_id": "one", "skill": "x", "category": "trigger", "expected_loaded": True},
            {"case_id": "two", "skill": "x", "category": "do_not_trigger", "expected_loaded": False},
            {"case_id": "three", "skill": "x", "category": "trigger", "expected_loaded": True},
            {"case_id": "four", "skill": "x", "category": "do_not_trigger", "expected_loaded": False},
        ]
        observations = [
            row(cases[0], True, cost_usd=.1, tokens=50),
            row(cases[1], True),
            row(cases[2], False),
            row(cases[3], False),
        ]
        report = score_observations(cases, observations)
        m = report["routing_metrics"][0]
        self.assertEqual(m["confusion"], {"tp": 1, "fp": 1, "tn": 1, "fn": 1})
        self.assertEqual(m["precision"], 0.5)
        self.assertEqual(m["recall"], 0.5)
        self.assertEqual(m["specificity"], 0.5)
        self.assertEqual(m["total_cost_usd"], 0.1)
        self.assertEqual(m["total_tokens"], 50)
        self.assertFalse(report["authenticates_external_evidence"])
        self.assertFalse(report["live_model_evaluation_performed"])

    def test_paired_comparison_is_claimed_not_authenticated(self):
        case = {"case_id": "p", "skill": "x", "category": "trigger", "expected_loaded": True}
        a = row(case, True, outcome="passed")
        b = row(case, False, condition="without_skill", outcome="failed")
        report = score_observations([case], [a, b])
        self.assertEqual(report["paired_reported_outcomes"][0]["with_only"], 1)
        self.assertEqual(report["paired_reported_outcomes"][0]["net_reported_win"], 1)
        self.assertFalse(report["authenticates_external_evidence"])

    def test_unverified_pair_excluded_from_comparison(self):
        case = {"case_id": "p", "skill": "x", "category": "trigger", "expected_loaded": True}
        report = score_observations(
            [case], [row(case, True, outcome="passed"),
                     row(case, False, condition="without_skill", outcome="not_checked")]
        )
        self.assertEqual(report["paired_reported_outcomes"], [])

    def test_duplicate_and_unknown_observations_rejected(self):
        case = {"case_id": "p", "skill": "x", "category": "trigger", "expected_loaded": True}
        entry = row(case, True)
        with self.assertRaises(SkillEvalError):
            score_observations([case], [entry, entry])
        with self.assertRaises(SkillEvalError):
            score_observations([case], [{**entry, "case_id": "unknown"}])
        with self.assertRaises(SkillEvalError):
            score_observations([case, case], [])

    def test_bad_metrics_cannot_poison_scores(self):
        case = {"case_id": "p", "skill": "x", "category": "trigger", "expected_loaded": True}
        good = row(case, True)
        for changes in ({"cost_usd": float("nan")}, {"cost_usd": -1},
                        {"duration_seconds": float("inf")},
                        {"tokens": -2}, {"tokens": True}, {"loaded": 1}):
            with self.subTest(changes=changes), self.assertRaises(SkillEvalError):
                score_observations([case], [{**good, **changes}])

    def test_wilson_small_sample_uncertainty(self):
        self.assertIsNone(wilson95(0, 0))
        lo, hi = wilson95(1, 1)
        self.assertLess(lo, 0.5)
        self.assertEqual(hi, 1.0)
        lo, hi = wilson95(0, 10)
        self.assertEqual(lo, 0.0)
        self.assertGreater(hi, 0.0)

    def test_malformed_jsonl_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "input.jsonl"
            path.write_text('{"ok":true}\nnot valid json\n', encoding="utf-8")
            with self.assertRaises(SkillEvalError):
                read_jsonl(path)


if __name__ == "__main__":
    unittest.main()
