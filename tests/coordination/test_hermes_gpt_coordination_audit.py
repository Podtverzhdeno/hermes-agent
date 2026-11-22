"""Offline contract tests for the read-only GPT integration collision gate."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[2] / "scripts" / "hermes_gpt_coordination_audit.py"
spec = importlib.util.spec_from_file_location("hermes_gpt_coordination_audit", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
S = "a" * 40
T = "b" * 40


def inventory(items):
    return {"schema_version": 1, "repo": "example/hermes",
            "base": "main", "base_sha": S, "source": "FIXTURE",
            "entries": [{"id": name, "head": T, "files": files}
                        for name, files in items]}


class CollisionAuditTests(unittest.TestCase):
    def test_exact_api_overlap_is_p0_blocker(self):
        result = module.audit(inventory([
            ("api", ["gateway/platforms/api_server.py"]),
            ("bridge", ["gateway/platforms/api_server.py"])]))
        self.assertEqual(result["verdict"], "HOLD")
        self.assertEqual(result["exact_collisions"], 1)
        self.assertEqual(result["findings"][0]["severity"], "P0")

    def test_package_overlap_is_p1_blocker(self):
        result = module.audit(inventory([
            ("alpha", ["pyproject.toml"]), ("beta", ["pyproject.toml"])]))
        self.assertEqual(result["findings"][0]["severity"], "P1")

    def test_docs_only_overlap_is_p2_blocker(self):
        result = module.audit(inventory([
            ("alpha", ["docs/sdd.md"]), ("beta", ["docs/sdd.md"])]))
        self.assertEqual(result["findings"][0]["severity"], "P2")

    def test_different_observer_implementations_require_review(self):
        result = module.audit(inventory([
            ("one", ["gpt_bridge/observability.py"]),
            ("two", ["gpt_extension/diagnostics.py"])]))
        self.assertEqual(result["exact_collisions"], 0)
        self.assertEqual(result["capability_reviews"], 1)
        self.assertEqual(result["verdict"], "REVIEW")

    def test_disjoint_feature_is_not_merge_approval(self):
        result = module.audit(inventory([
            ("one", ["docs/unrelated-one.md"]),
            ("two", ["tests/unrelated_two.py"])]))
        self.assertEqual(result["verdict"], "NO_COLLISION_FOUND_NOT_MERGE_APPROVAL")

    def test_missing_head_fails_closed(self):
        data = inventory([("a", ["README.md"])])
        data["entries"][0]["head"] = ""
        with self.assertRaises(module.AuditError):
            module.audit(data)

    def test_missing_base_fails_closed(self):
        data = inventory([("a", ["README.md"])])
        data["base_sha"] = "main"
        with self.assertRaises(module.AuditError):
            module.audit(data)

    def test_incomplete_changed_files_fails_closed(self):
        with self.assertRaises(module.AuditError):
            module.audit(inventory([("a", [])]))

    def test_duplicate_entry_fails_closed(self):
        with self.assertRaises(module.AuditError):
            module.audit(inventory([("same", ["a.py"]), ("same", ["b.py"])]))

    def test_untrusted_path_fails_closed(self):
        with self.assertRaises(module.AuditError):
            module.audit(inventory([("a", ["../secrets"]) ]))

    def test_order_is_independent_of_input_order(self):
        items = [("b", ["gateway/platforms/api_server.py"]),
                 ("a", ["gateway/platforms/api_server.py"])]
        self.assertEqual(module.audit(inventory(items))["findings"],
                         module.audit(inventory(list(reversed(items))))["findings"])

    def test_pr_collect_is_read_only_and_maps_exact_head(self):
        def fake_get(url, token):
            if "/branches/main" in url:
                return {"commit": {"sha": S}}
            if "/pulls/2" in url:
                return {"head": {"sha": T}, "base": {"ref": "main"}}
            raise AssertionError("unexpected HTTP URL " + url)
        def fake_pages(url, token, limit):
            if "/pulls?state=open" in url:
                return [{"number": 2, "base": {"ref": "main"},
                         "head": {"sha": T, "ref": "feature",
                                  "repo": {"full_name": "example/hermes"}},
                         "draft": True}]
            if "/pulls/2/files" in url:
                return [{"filename": "gateway/platforms/api_server.py"}]
            raise AssertionError("unexpected pagination " + url)
        with patch.object(module, "_get", fake_get), patch.object(
                module, "_pages", fake_pages):
            result = module.collect("example/hermes", prs_only=True)
        self.assertEqual(result["base_sha"], S)
        self.assertEqual(result["entries"][0]["head"], T)
        self.assertEqual(result["entries"][0]["files"],
                         ["gateway/platforms/api_server.py"])


    def test_pr_changed_during_inventory_is_rejected(self):
        def fake_get(url, token):
            if "/branches/main" in url:
                return {"commit": {"sha": S}}
            if "/pulls/2" in url:
                return {"head": {"sha": S}, "base": {"ref": "main"}}
            raise AssertionError(url)
        def fake_pages(url, token, limit):
            if "/pulls?state=open" in url:
                return [{"number": 2, "base": {"ref": "main"},
                         "head": {"sha": T, "ref": "feature",
                                  "repo": {"full_name": "example/hermes"}}}]
            if "/pulls/2/files" in url:
                return [{"filename": "gateway/platforms/api_server.py"}]
            raise AssertionError(url)
        with patch.object(module, "_get", fake_get), patch.object(
                module, "_pages", fake_pages):
            with self.assertRaisesRegex(module.AuditError, "PR moved"):
                module.collect("example/hermes", prs_only=True)

    def test_branch_compare_uses_exact_sha_not_moving_ref(self):
        seen = []
        def fake_get(url, token):
            seen.append(url)
            if "/branches/main" in url:
                return {"commit": {"sha": S}}
            if "/compare/" in url:
                return {"status": "ahead", "ahead_by": 1,
                        "files": [{"filename": "src/a.py"}],
                        "base_commit": {"sha": S}, "commits": [{"sha": T}]}
            if "/branches/feature" in url:
                return {"commit": {"sha": T}}
            raise AssertionError(url)
        def fake_pages(url, token, limit):
            if "/pulls?" in url:
                return []
            if url.endswith("/branches"):
                return [{"name": "main", "commit": {"sha": S}},
                        {"name": "feature", "commit": {"sha": T}}]
            raise AssertionError(url)
        with patch.object(module, "_get", fake_get), patch.object(
                module, "_pages", fake_pages):
            result = module.collect("example/hermes")
        self.assertIn("/compare/" + S + "..." + T, seen)
        self.assertEqual(result["entries"][0]["head"], T)

    def test_branch_head_changed_during_scan_is_rejected(self):
        def fake_get(url, token):
            if "/branches/main" in url:
                return {"commit": {"sha": S}}
            if "/compare/" in url:
                return {"status": "ahead", "ahead_by": 1,
                        "files": [{"filename": "src/a.py"}],
                        "base_commit": {"sha": S}, "commits": [{"sha": T}]}
            if "/branches/feature" in url:
                return {"commit": {"sha": S}}
            raise AssertionError(url)
        def fake_pages(url, token, limit):
            if "/pulls?" in url:
                return []
            if url.endswith("/branches"):
                return [{"name": "feature", "commit": {"sha": T}}]
            raise AssertionError(url)
        with patch.object(module, "_get", fake_get), patch.object(
                module, "_pages", fake_pages):
            with self.assertRaisesRegex(module.AuditError, "Branch moved"):
                module.collect("example/hermes")


    def test_thirty_agents_touching_one_api_file_are_all_flagged(self):
        items = [("agent-%02d" % i, ["gateway/platforms/api_server.py"])
                 for i in range(30)]
        result = module.audit(inventory(items))
        self.assertEqual(result["entries_checked"], 30)
        self.assertEqual(result["exact_collisions"], 435)
        self.assertEqual(result["verdict"], "HOLD")
        self.assertTrue(all(f["severity"] == "P0"
                            for f in result["findings"]))

    def test_hundred_disjoint_agent_paths_are_not_false_collisions(self):
        items = [("agent-%03d" % i, ["isolated/worktree-%03d/file.py" % i])
                 for i in range(100)]
        result = module.audit(inventory(items))
        self.assertEqual(result["entries_checked"], 100)
        self.assertEqual(result["exact_collisions"], 0)
        self.assertEqual(result["capability_reviews"], 0)
        self.assertEqual(result["verdict"],
                         "NO_COLLISION_FOUND_NOT_MERGE_APPROVAL")

    def test_pr_listing_at_limit_fails_closed(self):
        def fake_get(url, token):
            if "/branches/main" in url:
                return {"commit": {"sha": S}}
            raise AssertionError(url)
        def fake_pages(url, token, limit):
            if "/pulls?state=open" in url:
                return [{"number": 2, "base": {"ref": "main"},
                         "head": {"sha": T, "ref": "feature",
                                  "repo": {"full_name": "example/hermes"}}}]
            if "/pulls/2/files" in url:
                return [{"filename": "src/f%d.py" % i}
                        for i in range(3000)]
            raise AssertionError(url)
        with patch.object(module, "_get", fake_get), patch.object(
                module, "_pages", fake_pages):
            with self.assertRaisesRegex(module.AuditError, "3000-file"):
                module.collect("example/hermes", prs_only=True)

    def test_branch_comparison_truncation_fails_closed(self):
        def fake_get(url, token):
            if "/branches/main" in url:
                return {"commit": {"sha": S}}
            if "/compare/" in url:
                return {"status": "ahead", "ahead_by": 1,
                        "files": [{"filename": "src/%d.py" % i}
                                  for i in range(300)]}
            raise AssertionError(url)
        def fake_pages(url, token, limit):
            if "/pulls?" in url:
                return []
            if url.endswith("/branches"):
                return [{"name": "feature", "commit": {"sha": T}}]
            raise AssertionError(url)
        with patch.object(module, "_get", fake_get), patch.object(
                module, "_pages", fake_pages):
            with self.assertRaisesRegex(module.AuditError, "truncated"):
                module.collect("example/hermes")


    def test_base_ref_moving_mid_scan_never_returns_green(self):
        calls = [0]
        def fake_get(url, token):
            if "/branches/main" in url:
                calls[0] += 1
                return {"commit": {"sha": S if calls[0] == 1 else T}}
            raise AssertionError(url)
        def fake_pages(url, token, limit):
            if "/pulls?state=open" in url:
                return []
            raise AssertionError(url)
        with patch.object(module, "_get", fake_get), patch.object(
                module, "_pages", fake_pages):
            with self.assertRaisesRegex(module.AuditError, "Base branch moved"):
                module.collect("example/hermes", prs_only=True)

    def test_pr_base_sha_moving_mid_scan_never_returns_green(self):
        def fake_get(url, token):
            if "/branches/main" in url:
                return {"commit": {"sha": S}}
            if "/pulls/2" in url:
                return {"head": {"sha": T},
                        "base": {"ref": "main", "sha": T}}
            raise AssertionError(url)
        def fake_pages(url, token, limit):
            if "/pulls?state=open" in url:
                return [{"number": 2,
                         "base": {"ref": "main", "sha": S},
                         "head": {"sha": T, "ref": "feature",
                                  "repo": {"full_name": "example/hermes"}}}]
            if "/pulls/2/files" in url:
                return [{"filename": "src/changed.py"}]
            raise AssertionError(url)
        with patch.object(module, "_get", fake_get), patch.object(
                module, "_pages", fake_pages):
            with self.assertRaisesRegex(module.AuditError, "PR moved"):
                module.collect("example/hermes", prs_only=True)

    def test_offline_snapshot_cannot_claim_authenticated_github_source(self):
        import contextlib
        import io
        import json
        import tempfile
        import os
        data = inventory([("one", ["src/no-conflict.py"])])
        data["source"] = "GITHUB_REST"
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         suffix=".json", delete=False) as f:
            json.dump(data, f)
            filename = f.name
        try:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = module.main(["--snapshot", filename])
            self.assertEqual(code, 0)
            parsed = json.loads(output.getvalue())
            self.assertEqual(parsed["source"], "OFFLINE_INPUT_UNVERIFIED")
        finally:
            os.unlink(filename)

    def test_live_collection_failure_never_prints_green(self):
        def bad_get(url, token):
            raise module.AuditError("GitHub down")
        with patch.object(module, "_get", bad_get):
            with self.assertRaises(module.AuditError):
                module.collect("example/hermes")


if __name__ == "__main__":
    unittest.main()
