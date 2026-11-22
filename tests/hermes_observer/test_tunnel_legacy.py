"""Negative tests for actual public Tunnel v0.6.6 60-row bridge diagnostics."""
import json
import unittest

from hermes_observer.tunnel_legacy import LegacyTraceError, summarize_legacy_trace

T = "2026-11-22T11:00:00+00:00"


def raw(*events):
    return json.dumps([{"at": T, "stage": stage, **({"reason": reason} if reason else {})}
                       for stage, reason in events], separators=(",", ":")).encode()


class TestLegacyBridgeTrace(unittest.TestCase):
    def test_empty_does_not_claim_healthy(self):
        d = summarize_legacy_trace(b"[]")
        self.assertEqual(d["result"], "incomplete_observation")
        self.assertFalse(d["coverage_complete"])
        self.assertFalse(d["mutation_allowed"])
        self.assertFalse(d["external_effect_retry_allowed"])

    def test_pre_send_claim_cannot_prove_unsent(self):
        d = summarize_legacy_trace(raw(("prompt_filled", "")))
        self.assertFalse(d["stage_signals"]["send_clicked"])
        self.assertFalse(d["independent_effect_receipt_verified"])
        self.assertFalse(d["external_effect_retry_allowed"])

    def test_click_signal_is_not_durable_effect_receipt(self):
        d = summarize_legacy_trace(raw(("send_clicked", "")))
        self.assertTrue(d["stage_signals"]["send_clicked"])
        self.assertFalse(d["independent_effect_receipt_verified"])
        self.assertFalse(d["external_effect_retry_allowed"])

    def test_message_saved_without_click_signal_does_not_infer_rollback(self):
        d = summarize_legacy_trace(raw(("message_saved", "")))
        self.assertTrue(d["stage_signals"]["message_saved"])
        self.assertFalse(d["stage_signals"]["send_clicked"])
        self.assertFalse(d["external_effect_retry_allowed"])

    def test_report_acked_and_receipt_still_not_independent_quality(self):
        d = summarize_legacy_trace(raw(("report_acked", ""), ("receipt_accepted", "")))
        self.assertTrue(d["stage_signals"]["report_acked"])
        self.assertTrue(d["stage_signals"]["receipt_accepted"])
        self.assertFalse(d["final_delivery_verified"])
        self.assertFalse(d["source_provenance_authenticated"])

    def test_exactly_sixty_is_not_proof_of_entire_trace(self):
        d = summarize_legacy_trace(raw(*[("message_saved", "")]*60))
        self.assertTrue(d["window_at_capacity"])
        self.assertFalse(d["coverage_complete"])
        self.assertEqual(d["event_count_in_supplied_window"], 60)

    def test_fifty_nine_also_unverified_prefix(self):
        d = summarize_legacy_trace(raw(*[("assigned", "")]*59))
        self.assertFalse(d["window_at_capacity"])
        self.assertFalse(d["coverage_complete"])

    def test_sixty_one_refused(self):
        with self.assertRaises(LegacyTraceError):
            summarize_legacy_trace(raw(*[("assigned", "")]*61))

    def test_unknown_stage_refused_without_echo(self):
        with self.assertRaisesRegex(LegacyTraceError, "unrecognized_event_stage") as c:
            summarize_legacy_trace(raw(("password_secret", "")))
        self.assertNotIn("password", str(c.exception))

    def test_secret_field_rejected(self):
        with self.assertRaisesRegex(LegacyTraceError, "invalid_event_shape"):
            summarize_legacy_trace(b'[{"at":"'+T.encode()+b'","stage":"assigned","prompt":"secret"}]')

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(LegacyTraceError, "duplicate_json_key"):
            summarize_legacy_trace(b'[{"at":"'+T.encode()+b'","stage":"assigned","stage":"done"}]')

    def test_non_utc_refused(self):
        with self.assertRaisesRegex(LegacyTraceError, "non_utc_observation_time"):
            summarize_legacy_trace(b'[{"at":"2026-11-22T11:00:00+03:00","stage":"assigned"}]')

    def test_backward_clock_is_a_hypothesis_not_causation(self):
        rows = [{"at":"2026-11-22T11:00:03+00:00","stage":"send_clicked"},
                {"at":"2026-11-22T11:00:02+00:00","stage":"message_saved"}]
        d = summarize_legacy_trace(json.dumps(rows).encode())
        self.assertIn("OBSERVATION_CLOCK_REGRESSION", d["diagnostic_candidates"])
        self.assertFalse(d["external_effect_retry_allowed"])

    def test_auth_context_dispute_reason_is_public_code_only(self):
        d = summarize_legacy_trace(raw(("auth_context_changed", "account_context_changed")))
        self.assertIn("AUTH_CONTEXT_DISPUTED", d["diagnostic_candidates"])
        self.assertNotIn("account_context_changed", json.dumps(d))

    def test_unknown_reason_does_not_echo(self):
        d = summarize_legacy_trace(raw(("runtime_error", "secret_test_code")))
        self.assertNotIn("secret_test_code", json.dumps(d))
        self.assertIn("RUNTIME_ERROR_CLAIMED", d["diagnostic_candidates"])

    def test_invalid_type_bool_or_float_stage(self):
        for stage in (False, 1, 1.3, None):
            with self.subTest(stage=stage), self.assertRaises(LegacyTraceError):
                summarize_legacy_trace(json.dumps([{"at":T,"stage":stage}]).encode())

    def test_too_large_buffer_refused(self):
        with self.assertRaisesRegex(LegacyTraceError,"invalid_trace_bounds"):
            summarize_legacy_trace(b"x"*32769)

    def test_null_json_nonfinite_refused(self):
        with self.assertRaisesRegex(LegacyTraceError, "nonfinite_json"):
            summarize_legacy_trace(b'[{"at":"'+T.encode()+b'","stage":"assigned","reason":NaN}]')

    def test_huge_numeric_literal_refused_as_invalid_json(self):
        raw = b'[{"at":"'+T.encode()+b'","stage":' + b'9'*6000 + b'}]'
        with self.assertRaisesRegex(LegacyTraceError, "invalid_json"):
            summarize_legacy_trace(raw)

    def test_nested_json_not_reported_as_parsing_success(self):
        s = b"[" * 1500 + b"0" + b"]" * 1500
        with self.assertRaises(LegacyTraceError):
            summarize_legacy_trace(s)

    def test_not_a_list_refused(self):
        with self.assertRaisesRegex(LegacyTraceError, "invalid_event_count"):
            summarize_legacy_trace(b'{}')

    def test_exact_stage_allowlist(self):
        d = summarize_legacy_trace(raw(("tab_opening",""),("tab_created",""),
                                      ("send_ui_diagnostic","button_ambiguous")))
        self.assertIn("SEND_CONTROL_AMBIGUOUS", d["diagnostic_candidates"])

    def test_all_output_fields_are_allowlisted(self):
        d = summarize_legacy_trace(raw(("unknown", "unexpected_close")))
        self.assertFalse(d["mutation_allowed"])
        self.assertIn("TAB_DISAPPEARED", d["diagnostic_candidates"])
        self.assertNotIn(T, json.dumps(d))

    def test_version_is_metadata_not_installed_worker_evidence(self):
        d = summarize_legacy_trace(raw(("assigned", "")))
        self.assertEqual(d["contract"], "tunnel-web-companion-legacy-60-v0.6.6")
        self.assertFalse(d["source_provenance_authenticated"])
        self.assertFalse(d["coverage_complete"])

if __name__ == "__main__":
    unittest.main()
