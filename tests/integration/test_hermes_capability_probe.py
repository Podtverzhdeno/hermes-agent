"""No-network deterministic contract tests for local Hermes Runs capability probe."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

path = Path(__file__).resolve().parents[2] / "scripts" / "hermes_capability_probe.py"
spec = importlib.util.spec_from_file_location("hermes_capability_probe", path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def canonical():
    return {
        "object": "hermes.api_server.capabilities", "platform": "hermes-agent",
        "auth": {"type": "bearer", "required": True},
        "features": {
            "run_submission": True, "run_status": True, "run_events_sse": True,
            "run_stop": True, "run_unknown_resolution": True,
            "runs_idempotency": {"supported": True, "durable": True, "retention_seconds": 86400},
        },
        "endpoints": {
            name: {"method": method, "path": path}
            for name, (method, path) in m.ROUTES.items()
        },
    }

class ProbeTests(unittest.TestCase):
    def test_canonical_features_are_only_eligible_for_testing(self):
        result = m.evaluate_capabilities(canonical())
        self.assertEqual(result["status"], "CAPABILITIES_PRESENT")
        self.assertEqual(result["missing"], [])
        self.assertTrue(result["eligible_for_isolated_integration_test"])
        self.assertFalse(result["production_ready"])

    def test_missing_auth_required_blocks(self):
        x = canonical()
        x["auth"]["required"] = False
        self.assertIn("auth_required", m.evaluate_capabilities(x)["missing"])

    def test_nondurable_run_store_blocks(self):
        x = canonical()
        x["features"]["runs_idempotency"]["durable"] = False
        self.assertIn("idempotency_durable", m.evaluate_capabilities(x)["missing"])

    def test_no_unknown_resolution_blocks(self):
        x = canonical()
        x["features"]["run_unknown_resolution"] = False
        x["endpoints"].pop("run_unknown_resolution")
        self.assertIn("run_unknown_resolution", m.evaluate_capabilities(x)["missing"])

    def test_wrong_endpoint_route_blocks(self):
        x = canonical()
        x["endpoints"]["run_events"]["path"] = "/not-the-event-stream"
        self.assertIn("route:run_events", m.evaluate_capabilities(x)["missing"])

    def test_wrong_api_schema_fails_closed(self):
        with self.assertRaises(m.ProbeError):
            m.evaluate_capabilities({"features": {}})

    def test_loopback_ipv4_and_ipv6_with_scoped_profile(self):
        self.assertEqual(m.normalize_base_url("http://127.0.0.1:8642/"), "http://127.0.0.1:8642")
        self.assertEqual(m.normalize_base_url("http://[::1]:8642/p/work_1"),
                         "http://[::1]:8642/p/work_1")

    def test_remote_and_dns_alias_blocked(self):
        for url in ["http://localhost:8642", "https://example.org:443",
                    "http://192.168.1.1:8642", "http://127.0.0.2:8642"]:
            with self.subTest(url=url), self.assertRaises(m.ProbeError):
                m.normalize_base_url(url)

    def test_credentials_query_path_traversal_and_redirect_target_blocked(self):
        for url in ["http://user:password@127.0.0.1:8642",
                    "http://127.0.0.1:8642?token=secret",
                    "http://127.0.0.1:8642/p/../root",
                    "http://127.0.0.1:8642/#x",
                    "http://127.0.0.1",
                    "http://127.0.0.1:99999"]:
            with self.subTest(url=url), self.assertRaises(m.ProbeError):
                m.normalize_base_url(url)

    def test_malformed_idempotency_is_not_accepted(self):
        x = canonical()
        x["features"]["runs_idempotency"]["retention_seconds"] = "86400"
        self.assertIn("idempotency_retention", m.evaluate_capabilities(x)["missing"])

    def test_snapshot_is_offline_and_writes_successful_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            f, out = Path(tmp) / "cap.json", Path(tmp) / "result.json"
            f.write_text(json.dumps(canonical()))
            self.assertEqual(m.main(["--snapshot", str(f), "--output-json", str(out)]), 0)
            saved = json.loads(out.read_text())
            self.assertTrue(saved["eligible_for_isolated_integration_test"])
            self.assertFalse(saved["production_ready"])

    def test_offline_error_preserves_typed_incident_not_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            f, out = Path(tmp) / "cap.json", Path(tmp) / "result.json"
            f.write_text("{secret-invalid-json")
            self.assertEqual(m.main(["--snapshot", str(f), "--output-json", str(out)]), 3)
            saved = json.loads(out.read_text())
            self.assertEqual(saved["status"], "EVIDENCE_UNAVAILABLE")
            self.assertNotIn("secret-invalid-json", json.dumps(saved))
            self.assertFalse(saved["production_ready"])

    def test_monitor_can_remain_available_without_unknown_resolution(self):
        x = canonical()
        x["features"]["run_unknown_resolution"] = False
        x["endpoints"].pop("run_unknown_resolution")
        report = m.evaluate_capabilities(x)
        self.assertEqual(report["status"], "MONITOR_ONLY")
        self.assertTrue(report["eligible_for_readonly_monitoring"])
        self.assertFalse(report["eligible_for_isolated_integration_test"])
        self.assertFalse(report["production_ready"])

    def test_auth_disabled_blocks_even_readonly_monitor(self):
        x = canonical()
        x["auth"]["required"] = False
        report = m.evaluate_capabilities(x)
        self.assertFalse(report["eligible_for_readonly_monitoring"])
        self.assertIn("auth_required", report["monitor_missing"])

    def test_boolean_retention_type_is_not_integer_86400(self):
        x = canonical()
        x["features"]["runs_idempotency"]["retention_seconds"] = True
        report = m.evaluate_capabilities(x)
        self.assertIn("idempotency_retention", report["missing"])
        self.assertFalse(report["eligible_for_isolated_integration_test"])

    def test_short_idempotency_retention_blocks_control(self):
        x = canonical()
        x["features"]["runs_idempotency"]["retention_seconds"] = 1
        report = m.evaluate_capabilities(x)
        self.assertIn("idempotency_retention_below_24h", report["missing"])
        self.assertEqual(report["status"], "MONITOR_ONLY")

    def test_oversized_snapshot_is_typed_incident(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "huge.json"
            out = Path(tmp) / "incident.json"
            source.write_text("x" * (m.MAX_BYTES + 1))
            rc = m.main(["--snapshot", str(source), "--output-json", str(out)])
            self.assertEqual(rc, 3)
            self.assertEqual(json.loads(out.read_text())["reason_code"], "SNAPSHOT_TOO_LARGE")

    def test_valid_but_legacy_returns_nonzero_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            x = canonical()
            x["features"]["run_submission"] = False
            f = Path(tmp) / "legacy.json"
            f.write_text(json.dumps(x))
            self.assertEqual(m.main(["--snapshot", str(f)]), 2)

if __name__ == "__main__":
    unittest.main()
