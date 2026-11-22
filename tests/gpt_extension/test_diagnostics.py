"""Regression tests for conservative, pure Hermes task diagnosis."""
import unittest
from dataclasses import replace

from gpt_extension.diagnostics import Diagnosis, Effect, Evidence, Snapshot, diagnose


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.base = Snapshot("task", "running", "abc123", 1, 3, now=1000.0,
                             lease_until=1120.0, last_event_at=995.0)

    def case(self, code, **kw):
        result = diagnose(replace(self.base, **kw))
        self.assertEqual(result.code, code)
        return result

    def test_active_is_not_finished(self):
        self.case("NO_BLOCKER_OBSERVED")

    def test_reserved_effect_blocks_all_retry_even_when_succeeded(self):
        d = self.case("EXTERNAL_EFFECT_UNCERTAIN", status="succeeded",
                      effects=(Effect("r2-call", "reserved"),))
        self.assertEqual(d.unresolved_evidence, ("r2-call",))

    def test_reconciliation_without_effect_is_still_ambiguous(self):
        self.case("EXTERNAL_EFFECT_UNCERTAIN", status="needs_reconciliation")

    def test_success_without_evidence_contract_is_not_verified(self):
        self.case("EVIDENCE_POLICY_MISSING", status="succeeded")

    def test_untrusted_ci_does_not_complete(self):
        self.case("UNVERIFIED_SUCCESS", status="succeeded", required_evidence=("ci",),
                  evidence=(Evidence("ci", "abc123", "success", False),))

    def test_stale_revision_does_not_complete(self):
        self.case("UNVERIFIED_SUCCESS", status="succeeded", required_evidence=("ci",),
                  evidence=(Evidence("ci", "old", "success", True),))

    def test_failed_ci_does_not_complete(self):
        self.case("UNVERIFIED_SUCCESS", status="succeeded", required_evidence=("ci",),
                  evidence=(Evidence("ci", "abc123", "failed", True),))

    def test_trusted_revision_bound_ci_succeeds(self):
        self.case("VERIFIED_SUCCESS", status="succeeded", required_evidence=("ci",),
                  evidence=(Evidence("ci", "abc123", "success", True),))

    def test_cancel_precedes_observed_timeout(self):
        self.case("CANCELLATION_PENDING", cancel_requested=True, lease_until=900.0)

    def test_waiting_approval(self):
        self.case("APPROVAL_PENDING", status="waiting_approval")

    def test_no_lease(self):
        self.case("LEASE_MISSING", lease_until=None)

    def test_expired_lease_is_not_root_cause(self):
        d = self.case("LEASE_EXPIRED", lease_until=999.0)
        self.assertEqual(d.cause_status, "unknown")

    def test_retry_wait(self):
        self.case("RETRY_BACKOFF", status="retry_wait")

    def test_exhausted_retry_inconsistency(self):
        self.case("RETRY_BUDGET_INCONSISTENT", status="retry_wait", attempts=3)

    def test_down_connector_is_not_model_failure(self):
        self.case("CONNECTOR_UNAVAILABLE", connector_status="down")

    def test_stale_activity_is_not_inferred_crash(self):
        d = self.case("NO_PROGRESS_OBSERVED", last_event_at=10.0)
        self.assertEqual(d.cause_status, "unknown")

    def test_queue_not_eligible(self):
        self.case("NOT_YET_ELIGIBLE", status="queued", available_at=2000.0)

    def test_verification_pending(self):
        self.case("VERIFICATION_PENDING", status="verifying", required_evidence=("qa",))

    def test_terminal_failed_does_not_guess_why(self):
        d = self.case("TASK_FAILED", status="failed")
        self.assertEqual(d.cause_status, "unknown")

    def test_invalid_state_rejected(self):
        with self.assertRaises(ValueError):
            diagnose(replace(self.base, status="silently_dead"))

    def test_invalid_budget_rejected(self):
        with self.assertRaises(ValueError):
            diagnose(replace(self.base, max_attempts=0))

    def test_no_payload_logging(self):
        d = self.case("EXTERNAL_EFFECT_UNCERTAIN", effects=(Effect("a", "reserved"),))
        self.assertNotIn("api_key", repr(d).lower())


if __name__ == "__main__":
    unittest.main()


# Extended source-contract cases: effect receipts and Autopilot evidence names.
class EvidenceAndEffectInvariantTests(unittest.TestCase):
    def setUp(self):
        self.base = Snapshot("task", "succeeded", "sha123", 1, 3, now=100.,
                             required_evidence=("ci",),
                             evidence=(Evidence("ci", "sha123", "success", True),))

    def test_unknown_effect_status_fails_closed(self):
        d = diagnose(replace(self.base, effects=(Effect("action", "pending_future"),)))
        self.assertEqual(d.code, "EFFECT_STATE_UNKNOWN")

    def test_acknowledged_effect_needs_independent_receipt(self):
        d = diagnose(replace(self.base, effects=(Effect("action", "acknowledged"),)))
        self.assertEqual(d.code, "EFFECT_RECEIPT_MISSING")

    def test_acknowledged_effect_with_receipt_can_pass(self):
        d = diagnose(replace(self.base, effects=(Effect("action", "acknowledged", "receipt-ref"),)))
        self.assertEqual(d.code, "VERIFIED_SUCCESS")

    def test_conflicting_trusted_pass_and_failure_blocks(self):
        e = (Evidence("ci", "sha123", "success", True),
             Evidence("ci", "sha123", "failed", True))
        self.assertEqual(diagnose(replace(self.base, evidence=e)).code, "CONFLICTING_VERIFICATION")

    def test_autopilot_passed_label_supported(self):
        e = (Evidence("ci", "sha123", "passed", True),)
        self.assertEqual(diagnose(replace(self.base, evidence=e)).code, "VERIFIED_SUCCESS")
