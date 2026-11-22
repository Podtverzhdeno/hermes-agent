"""No-network contract tests for read-only Hermes PR evidence gate."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

p = Path(__file__).resolve().parents[2] / "scripts" / "hermes_pr_gate.py"
spec = importlib.util.spec_from_file_location("hermes_pr_gate", p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def pr(number, *, head=None, base="main", name=None, files=(), outcome="success", review=None):
    sha = head or (format(number, "040x"))
    return {"number": number, "head_sha": sha,
            "base_branch": base, "head_branch": name or "b" + str(number),
            "files": list(files), "checks": [{"name": "test", "head_sha": sha,
                                             "status": "completed", "conclusion": outcome}],
            "statuses": [{"context": "Devin Review", "description": review}] if review else [],
            "draft": True}

def snapshot(*ps):
    return {"schema_version": 1, "consistent": True,
            "repository": "x/y", "observed_at": "2026-11-22", "prs": list(ps)}

class GateTests(unittest.TestCase):
    def test_exact_head_pass(self):
        self.assertEqual(m.assess(snapshot(pr(1)))["checks"][0]["test"], "PASS")

    def test_concurrent_file_collision(self):
        r = m.assess(snapshot(pr(1, files=["x.py"]), pr(2, files=["x.py"])))
        self.assertEqual(r["collisions"], [{"file": "x.py", "prs": [1, 2]}])

    def test_stacked_overlap_not_sibling_collision(self):
        r = m.assess(snapshot(pr(1, files=["x.py"]), pr(2, base="b1", files=["x.py"])))
        self.assertEqual(r["collisions"], [])
        self.assertEqual(r["stacked_dependencies"], [{"pr": 2, "depends_on": 1}])

    def test_nested_stack(self):
        r = m.assess(snapshot(pr(1, files=["x.py"]), pr(2, base="b1", files=["x.py"]),
                              pr(3, base="b2", files=["x.py"])))
        self.assertEqual(r["collisions"], [])

    def test_sibling_collision(self):
        r = m.assess(snapshot(pr(1, files=["x.py"]), pr(2, base="b1", files=["x.py"]),
                              pr(3, base="b1", files=["x.py"])))
        self.assertEqual(r["collisions"], [{"file": "x.py", "prs": [2, 3]}])

    def test_check_failure(self):
        self.assertIn("failure", m.assess(snapshot(pr(1, outcome="failure")))["checks"][0]["test"])

    def test_missing_check_is_not_green(self):
        p = pr(1); p["checks"] = []
        self.assertEqual(m.assess(snapshot(p))["checks"][0]["test"], "MISSING")

    def test_skipped_review_not_test(self):
        p = pr(1, review="Full review skipped: trial expired")
        r = m.assess(snapshot(p))
        self.assertEqual(r["checks"][0]["test"], "PASS")
        self.assertEqual(r["checks"][0]["review_skipped"], ["Devin Review"])
        self.assertFalse(r["merge_ready"])

    def test_wrong_sha_fails_closed(self):
        p = pr(1); p["checks"][0]["head_sha"] = "a" * 40
        with self.assertRaises(m.EvidenceError):
            m.assess(snapshot(p))

    def test_incomplete_snapshot_fails_closed(self):
        p = snapshot(pr(1)); p["consistent"] = False
        with self.assertRaises(m.EvidenceError):
            m.assess(p)

    def test_dependency_cycle_fails_closed(self):
        a=pr(1,base="b2"); b=pr(2,base="b1")
        with self.assertRaises(m.EvidenceError):
            m.assess(snapshot(a,b))

    def test_semantic_collision_without_same_file(self):
        r=m.assess(snapshot(pr(1,files=["gpt_bridge/observability.py"]),
                            pr(2,files=["gpt_companion/journal.py"])))
        self.assertEqual(r["collisions"], [])
        self.assertEqual(r["semantic_reviews"][0]["family"],"event-observer")

    def test_unavailable_evidence_emits_reasoned_artifact(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "bad.json"
            out_json = Path(folder) / "evidence.json"
            out_md = Path(folder) / "evidence.md"
            source.write_text(json.dumps({"schema_version": 1, "consistent": False, "prs": []}))
            rc = m.main(["--snapshot", str(source),
                         "--output-json", str(out_json), "--output-md", str(out_md)])
            self.assertEqual(rc, 3)
            failure = json.loads(out_json.read_text())
            self.assertEqual(failure["status"], "EVIDENCE_UNAVAILABLE")
            self.assertFalse(failure["merge_ready"])
            self.assertIn("FAIL CLOSED", out_md.read_text())

    def test_markdown_has_sha_and_warning(self):
        result=m.assess(snapshot(pr(1)))
        self.assertIn("Merge authorization: **NO**",m.markdown(result))
        self.assertIn("000000000000",m.markdown(result))

if __name__=="__main__":
    unittest.main()
