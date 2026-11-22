import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "gpt_pr_guard.py"
spec = importlib.util.spec_from_file_location("gpt_pr_guard", SCRIPT)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)
SHA = "a" * 40
OTHER = "b" * 40


def pr(n, files=(), name=None, base="main", runs=None, draft=False):
    return {"number": n, "head_sha": SHA if n == 1 else OTHER,
            "head_ref": name or f"feat/p{n}", "base_ref": base, "draft": draft,
            "files": list(files), "runs": runs if runs is not None else
            [{"name": "Tests", "status": "completed", "conclusion": "success",
              "head_sha": SHA if n == 1 else OTHER, "id": n}]}


def snap(*prs, protected=True, complete=True):
    return {"schema_version": 1, "repository": "Owner/Repo", "base_sha": SHA,
            "base_protected": protected, "complete": complete,
            "captured_at_utc": "2026-11-22T10:00:00+00:00", "prs": list(prs)}


class GateTests(unittest.TestCase):
    def codes(self, data):
        return {f["code"] for f in g.analyze(data)["findings"]}

    def test_green_single_pr(self):
        result = g.analyze(snap(pr(1, ["docs/a.md"])))
        self.assertTrue(result["ready_for_merge"])

    def test_draft_never_green(self):
        self.assertIn("PR_DRAFT", self.codes(snap(pr(1, draft=True))))

    def test_unprotected_base_blocks(self):
        self.assertIn("BASE_UNPROTECTED_OR_UNKNOWN", self.codes(snap(pr(1), protected=False)))

    def test_critical_collision(self):
        self.assertIn("CRITICAL_FILE_COLLISION", self.codes(snap(
            pr(1, ["gateway/platforms/api_server.py"]),
            pr(2, ["gateway/platforms/api_server.py"]))))

    def test_noncritical_collision_review_only(self):
        findings = g.analyze(snap(pr(1, ["docs/a.md"]), pr(2, ["docs/a.md"])))
        self.assertTrue(findings["ready_for_merge"])
        self.assertTrue(any(f["severity"] == "review" for f in findings["findings"]))

    def test_stacked_branch_blocked(self):
        self.assertIn("STACKED_BRANCH", self.codes(snap(pr(1), pr(2, base="feat/p1"))))

    def test_duplicate_observer_packages(self):
        self.assertIn("COMPETING_OBSERVER_PROTOCOLS", self.codes(snap(
            pr(1, ["gpt_bridge/journal.py"]), pr(2, ["gpt_companion/journal.py"]))))

    def test_ci_missing(self):
        self.assertIn("CI_ABSENT", self.codes(snap(pr(1, runs=[]))))

    def test_ci_failed(self):
        failed = [{"name":"Tests", "status":"completed", "conclusion":"failure", "head_sha":SHA}]
        self.assertIn("CI_NOT_GREEN", self.codes(snap(pr(1, runs=failed))))

    def test_ci_skipped_not_success(self):
        skipped = [{"name":"Tests", "status":"completed", "conclusion":"skipped", "head_sha":SHA}]
        self.assertIn("CI_NOT_GREEN", self.codes(snap(pr(1, runs=skipped))))

    def test_latest_success_can_override_prior_failed(self):
        runs = [{"name":"Tests","status":"completed","conclusion":"failure", "head_sha":SHA,"run_number":1},
                {"name":"Tests","status":"completed","conclusion":"success", "head_sha":SHA,"run_number":2}]
        self.assertTrue(g.analyze(snap(pr(1,runs=runs)))["ready_for_merge"])

    def test_sha_mismatch_fail_closed(self):
        mismatch = [{"name":"Tests", "status":"completed", "conclusion":"success", "head_sha":OTHER}]
        with self.assertRaises(g.EvidenceError): g.analyze(snap(pr(1,runs=mismatch)))

    def test_partial_scan_fail_closed(self):
        with self.assertRaises(g.EvidenceError): g.analyze(snap(pr(1),complete=False))

    def test_unsafe_changed_file_fail_closed(self):
        with self.assertRaises(g.EvidenceError): g.analyze(snap(pr(1,["../secrets.txt"])))

    def test_duplicate_pr_fail_closed(self):
        with self.assertRaises(g.EvidenceError): g.analyze(snap(pr(1),pr(1)))

    def test_hash_is_deterministic(self):
        s = snap(pr(1))
        self.assertEqual(g.analyze(s)["snapshot_sha256"],g.analyze(s)["snapshot_sha256"])

    def test_required_check_overrides(self):
        r=g.analyze(snap(pr(1)),required_checks=("Unit Gate",))
        self.assertIn("CI_ABSENT", {f["code"] for f in r["findings"]})


    def test_live_detects_head_move_during_scan(self):
        from unittest.mock import patch
        original = {"number":1, "head":{"sha": SHA, "ref":"feat/p1"},
                    "base":{"ref":"main"},"draft":False}
        moved = {**original,"head":{"sha": OTHER,"ref":"feat/p1"}}
        with patch.object(g, "_get_json", return_value={"commit":{"sha":SHA},"protected":True}), \
             patch.object(g, "_pages", side_effect=[[original], [{"filename":"docs/a.md"}], [], [moved]]):
            with self.assertRaisesRegex(g.EvidenceError, "moved"):
                g.collect_live("Owner/Repo", None)

    def test_live_detects_base_move_during_scan(self):
        from unittest.mock import patch
        baseline = {"number":1,"head":{"sha":SHA,"ref":"feat/p1"},
                    "base":{"ref":"main"},"draft":False}
        with patch.object(g,"_get_json",side_effect=[
                {"commit":{"sha":SHA},"protected":True},
                {"commit":{"sha":OTHER},"protected":True}]), \
             patch.object(g,"_pages",side_effect=[[baseline],[{"filename":"docs/a.md"}],[],[baseline]]):
            with self.assertRaisesRegex(g.EvidenceError,"Base branch moved"):
                g.collect_live("Owner/Repo",None)

    def test_read_only_scan_recovers_from_moving_head(self):
        from unittest.mock import patch
        with patch.object(g, "collect_live", side_effect=[
                g.EvidenceError("PR inventory/head moved during scan"), snap(pr(1))]) as live, \
             patch.object(g.time, "sleep") as sleeper:
            snapshot = g.collect_live_stable("Owner/Repo", None, attempts=2)
        self.assertEqual(snapshot["scan_attempts"], 2)
        self.assertEqual(live.call_count, 2)
        sleeper.assert_called_once()

    def test_read_only_scan_gives_up_when_never_stable(self):
        from unittest.mock import patch
        with patch.object(g, "collect_live", side_effect=g.EvidenceError(
                "Base branch moved during scan")) as live, \
             patch.object(g.time, "sleep") as sleeper:
            with self.assertRaisesRegex(g.EvidenceError, "moved during scan"):
                g.collect_live_stable("Owner/Repo", None, attempts=3)
        self.assertEqual(live.call_count, 3)
        self.assertEqual(sleeper.call_count, 2)

    def test_read_only_scan_does_not_retry_auth_or_transport_error(self):
        from unittest.mock import patch
        with patch.object(g, "collect_live", side_effect=g.EvidenceError(
                "GitHub evidence fetch failed (HTTPError)")) as live:
            with self.assertRaises(g.EvidenceError):
                g.collect_live_stable("Owner/Repo", None)
        live.assert_called_once()

    def test_invalid_snapshot_retry_limit(self):
        with self.assertRaises(g.EvidenceError):
            g.collect_live_stable("Owner/Repo", None, attempts=0)

    def test_parallel_pr_scan_preserves_exact_revision_identity(self):
        from unittest.mock import patch
        source = [{"number":i,"head":{"sha":SHA,"ref":f"feat/p{i}"},
                   "base":{"ref":"main"},"draft":False} for i in range(1,10)]
        def pages(url,token,key=None):
            if "/pulls?state=open" in url: return source
            if "/files" in url: return [{"filename":"docs/stable.md"}]
            if "/actions/runs" in url: return [{"name":"Tests","status":"completed",
                "conclusion":"success","head_sha":SHA}]
            raise AssertionError(url)
        with patch.object(g,"_get_json",return_value={"commit":{"sha":SHA},"protected":True}), \
             patch.object(g,"_pages",side_effect=pages):
            result=g.collect_live("Owner/Repo",None)
        self.assertEqual(len(result["prs"]),9)
        self.assertEqual([x["number"] for x in result["prs"]],list(range(1,10)))

    def test_http_failure_is_redacted_and_classified(self):
        from unittest.mock import patch
        fake = g.HTTPError("https://secret.example/token=abc", 403,
                           "Forbidden bearer-secret", None, None)
        with patch.object(g, "urlopen", side_effect=fake):
            with self.assertRaises(g.EvidenceError) as caught:
                g._get_json("https://secret.example/token=abc", "sensitive-key")
        self.assertEqual(str(caught.exception), "GitHub HTTP 403")
        self.assertEqual(g.evidence_reason(caught.exception), "GITHUB_HTTP_403")

    def test_failed_scan_writes_redacted_incident_report(self):
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "out.json"
            code = g.main(["--snapshot", str(Path(temporary)/"absent-secret.json"),
                           "--output", str(target)])
            report = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(code, 3)
        self.assertEqual(report["status"], "evidence_unknown")
        self.assertEqual(report["reason_code"], "LOCAL_EVIDENCE_READ_FAILED")
        self.assertNotIn("absent-secret", json.dumps(report))

    def test_error_category_preserves_snapshot_race_vs_http_error(self):
        self.assertEqual(g.evidence_reason(g.EvidenceError("Base branch moved during scan")),
                         "SNAPSHOT_RACE")
        self.assertEqual(g.evidence_reason(g.EvidenceError("GitHub HTTP 429")),
                         "GITHUB_HTTP_429")
        self.assertEqual(g.evidence_reason(g.EvidenceError("Pagination limit reached")),
                         "EVIDENCE_TRUNCATED")

    def test_collect_pages_bounds(self):
        with self.assertRaises(g.EvidenceError):
            g.validate(snap(pr(1),complete=False))


if __name__ == "__main__": unittest.main()
