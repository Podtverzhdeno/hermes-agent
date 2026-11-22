"""Offline, deterministic contract/fault-injection tests. No provider/OS writes."""
import io
import json
import unittest
import uuid
from unittest.mock import patch

from hermes_observer.audit import audit_stream, parse_event, InvalidEvent, MAX_LINE_BYTES

TASK = "11111111-1111-4111-8111-111111111111"
RUN = "22222222-2222-4222-8222-222222222222"


def ev(*, producer="worker-a", seq=1, kind="worker.started", task=TASK,
       event_id=None, **kw):
    base = {
        "schema_version": 1, "event_id": event_id or str(uuid.uuid4()),
        "producer_id": producer, "source_event_seq": seq, "kind": kind,
        "task_id": task, "run_id": RUN, "occurred_at_utc": "2026-11-22T10:00:00Z",
        "observed_at_utc": "2026-11-22T10:00:02Z",
        "trace_id": "a" * 32, "span_id": "b" * 16,
    }
    base.update(kw)
    return base


def audit(*items):
    data = b"".join((json.dumps(x, ensure_ascii=False).encode() if isinstance(x, dict) else x) + b"\n" for x in items)
    return audit_stream(io.BytesIO(data))


class MetadataContractTests(unittest.TestCase):
    def test_empty_snapshot_is_incomplete_not_success(self):
        result = audit_stream(io.BytesIO(b""))
        self.assertEqual(result["status"], "incomplete_observation")
        self.assertEqual(result["exit_code"], 3)
        self.assertIn("EMPTY_SNAPSHOT", result["finding_counts"])

    def test_conflicting_terminal_states_in_one_attempt(self):
        attempt = "33333333-3333-4333-8333-333333333333"
        a = ev(seq=1, kind="task.completed", attempt_id=attempt, state_to="failed", reason_code="UNKNOWN")
        b = ev(seq=2, kind="task.completed", attempt_id=attempt, state_to="succeeded")
        result = audit(a, b)
        self.assertEqual(result["status"], "integrity_anomaly")
        self.assertIn("CONFLICTING_ATTEMPT_TERMINAL_STATES", result["finding_counts"])

    def test_different_attempts_can_have_distinct_terminal_outcomes(self):
        a = ev(seq=1, kind="task.completed", state_to="failed", reason_code="UNKNOWN",
               attempt_id="33333333-3333-4333-8333-333333333333")
        b = ev(seq=2, kind="task.completed", state_to="succeeded",
               attempt_id="44444444-4444-4444-8444-444444444444")
        result = audit(a, b)
        self.assertNotIn("CONFLICTING_ATTEMPT_TERMINAL_STATES", result["finding_counts"])

    def test_missing_attempt_identity_marks_conflicting_terminals_uncertain(self):
        a = ev(seq=1, kind="task.completed", state_to="failed", reason_code="UNKNOWN")
        b = ev(seq=2, kind="task.completed", state_to="succeeded")
        result = audit(a, b)
        self.assertIn("TERMINAL_CONFLICT_WITHOUT_ATTEMPT_ID", result["finding_counts"])

    def test_clean_single_event_is_not_authoritative_health(self):
        result = audit(ev())
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["status"], "no_anomalies_in_supplied_slice")
        self.assertFalse(result["mutation_allowed"])
        self.assertFalse(result["external_effect_retry_allowed"])

    def test_duplicate_delivery_is_idempotent(self):
        event = ev()
        result = audit(event, event)
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["counts"]["duplicate_deliveries"], 1)
        self.assertEqual(result["counts"]["accepted_events"], 1)

    def test_event_id_collision_detected(self):
        eid = str(uuid.uuid4())
        result = audit(ev(event_id=eid), ev(event_id=eid, kind="model.responded"))
        self.assertEqual(result["status"], "integrity_anomaly")
        self.assertEqual(result["finding_counts"]["EVENT_ID_COLLISION"], 1)

    def test_producer_sequence_collision_detected(self):
        result = audit(ev(), ev(kind="worker.heartbeat"))
        self.assertEqual(result["finding_counts"]["SEQUENCE_COLLISION"], 1)

    def test_gap_but_not_truncated_head_or_tail(self):
        result = audit(ev(seq=10), ev(seq=12))
        self.assertEqual(result["finding_counts"]["PRODUCER_SEQUENCE_GAP"], 1)
        self.assertEqual(result["status"], "incomplete_observation")
        result = audit(ev(seq=11))
        self.assertEqual(result["exit_code"], 0)

    def test_reordered_clock_does_not_affect_causal_result(self):
        parent = ev(seq=1, event_id=str(uuid.uuid4()), occurred_at_utc="2026-11-22T11:00:00Z")
        child = ev(seq=2, event_id=str(uuid.uuid4()), causation_event_id=parent["event_id"],
                   occurred_at_utc="2026-11-22T09:00:00Z")
        self.assertEqual(audit(child, parent)["exit_code"], 0)

    def test_causal_inversion_is_detected(self):
        parent = ev(seq=4)
        child = ev(seq=3, causation_event_id=parent["event_id"])
        r = audit(parent, child)
        self.assertEqual(r["finding_counts"]["CAUSAL_SEQUENCE_INVERSION"], 1)

    def test_causal_cycle_is_detected(self):
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        result = audit(ev(event_id=a, seq=1, causation_event_id=b),
                       ev(event_id=b, seq=2, causation_event_id=a))
        self.assertIn("CAUSAL_CYCLE", result["finding_counts"])

    def test_missing_cause_is_incomplete_not_failure(self):
        result = audit(ev(causation_event_id=str(uuid.uuid4())))
        self.assertEqual(result["exit_code"], 3)
        self.assertIn("CAUSAL_PARENT_NOT_IN_SNAPSHOT", result["finding_counts"])

    def test_duplicate_json_property_is_rejected(self):
        event = json.dumps(ev())
        bad = event[:-1] + ',"kind":"task.completed"}'
        with self.assertRaises(InvalidEvent):
            parse_event(bad.encode())

    def test_unapproved_fields_and_prompt_data_rejected_without_echo(self):
        payload = ev(prompt="CONFIDENTIAL-EXAMPLE-DO-NOT-LOG")
        result = audit(payload)
        self.assertEqual(result["exit_code"], 4)
        self.assertNotIn("CONFIDENTIAL", json.dumps(result))
        self.assertEqual(result["finding_counts"]["INVALID_EVENT"], 1)

    def test_invalid_uuid_and_zero_trace_rejected(self):
        for candidate in (ev(event_id="bad"), ev(trace_id="0" * 32), ev(lease_fence=True),
                          ev(observed_at_utc="2026-99-66T00:00:00Z")):
            with self.subTest(candidate=candidate):
                self.assertEqual(audit(candidate)["exit_code"], 4)

    def test_oversized_line_safely_dropped_followed_by_valid(self):
        payload = b"{" + b"x" * (MAX_LINE_BYTES + 1) + b"}\n" + json.dumps(ev()).encode() + b"\n"
        result = audit_stream(io.BytesIO(payload))
        self.assertEqual(result["counts"]["accepted_events"], 1)
        self.assertEqual(result["counts"]["invalid_events"], 1)
        self.assertEqual(result["counts"]["lines_read"], 2)

    def test_json_type_confusion_cannot_crash_parser(self):
        for obj in (ev(reason_code=["POLICY_DENIED"]), ev(state_to=[]),
                    ev(kind=["worker.started"]), ev(reason_code={"x": 1}),
                    ev(state_from={"queued": True})):
            with self.subTest(obj=obj):
                self.assertEqual(audit(obj)["exit_code"], 4)

    def test_deeply_nested_json_is_invalid_not_a_process_crash(self):
        # Python's json decoder can raise RecursionError before it returns an
        # ordinary JSON value; hostile metadata must never crash diagnosis.
        malicious = (b"[" * 2200) + b"0" + (b"]" * 2200)
        result = audit_stream(io.BytesIO(malicious + b"\n" + json.dumps(ev()).encode() + b"\n"))
        self.assertEqual(result["status"], "invalid_snapshot")
        self.assertEqual(result["counts"]["accepted_events"], 1)
        self.assertEqual(result["counts"]["invalid_events"], 1)

    def test_required_occurrence_timestamp_cannot_be_null(self):
        self.assertEqual(audit(ev(occurred_at_utc=None))["status"], "invalid_snapshot")

    def test_task_completion_cannot_transition_to_running(self):
        result = audit(ev(kind="task.completed", state_to="running"))
        self.assertEqual(result["status"], "incomplete_observation")
        self.assertIn("COMPLETION_WITHOUT_TERMINAL_STATE", result["finding_counts"])

    def test_total_file_byte_budget_prevents_unbounded_scan(self):
        data = json.dumps(ev()).encode() + b"\n" + b"x" * 2000
        with patch("hermes_observer.audit.MAX_TOTAL_BYTES", 500):
            result = audit_stream(io.BytesIO(data))
        self.assertEqual(result["exit_code"], 3)
        self.assertIn("INPUT_BYTE_LIMIT_REACHED", result["finding_counts"])

    def test_invalid_completion_missing_state_and_task(self):
        self.assertEqual(audit(ev(kind="task.completed", task=None))["exit_code"], 4)
        result = audit(ev(kind="task.completed"))
        self.assertIn("COMPLETION_WITHOUT_TERMINAL_STATE", result["finding_counts"])

    def test_terminal_failure_requires_reason(self):
        result = audit(ev(kind="task.completed", state_to="failed"))
        self.assertIn("TERMINAL_FAILURE_WITHOUT_REASON", result["finding_counts"])

    def test_no_json_nonfinite_or_boolean_sequence(self):
        with self.assertRaises(InvalidEvent):
            parse_event(json.dumps(ev()).replace('"source_event_seq": 1', '"source_event_seq": NaN').encode())
        self.assertEqual(audit(ev(seq=True))["exit_code"], 4)

    def test_50_agent_reordered_5000_event_soak(self):
        import random
        events = [ev(producer=f"worker-{p}", seq=i) for p in range(50) for i in range(1, 101)]
        random.Random(42).shuffle(events)
        result = audit(*events)
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["counts"]["accepted_events"], 5000)
        self.assertEqual(result["counts"]["producer_count"], 50)
        self.assertEqual(result["counts"]["finding_total"], 0)

    def test_findings_are_bounded_but_total_is_not_hidden(self):
        events = [ev(producer=f"worker-{i}", seq=seq) for i in range(300) for seq in (1, 3)]
        result = audit(*events)
        self.assertEqual(result["finding_counts"]["PRODUCER_SEQUENCE_GAP"], 300)
        self.assertEqual(result["counts"]["finding_suppressed"], 50)
        self.assertEqual(len(result["findings"]), 250)

    def test_priority_keeps_late_critical_when_gap_storm_truncates_output(self):
        gaps = [ev(producer=f"worker-{i}", seq=seq) for i in range(300) for seq in (1, 3)]
        eid = "55555555-5555-4555-8555-555555555555"
        collision = [ev(producer="source-alpha", seq=1, event_id=eid),
                     ev(producer="source-beta", seq=1, event_id=eid)]
        result = audit(*(gaps + collision))
        self.assertEqual(result["status"], "integrity_anomaly")
        self.assertGreater(result["counts"]["finding_suppressed"], 0)
        self.assertIn("EVENT_ID_COLLISION", [x["code"] for x in result["findings"]])

    def test_priority_selection_stable_for_reversed_event_delivery(self):
        rows = [ev(producer=f"worker-{i}", seq=seq) for i in range(260) for seq in (1, 3)]
        a = audit(*rows)
        b = audit(*reversed(rows))
        self.assertEqual(a["findings"], b["findings"])
        self.assertEqual(a["finding_counts"], b["finding_counts"])

    def test_bounded_snapshot_does_not_return_green(self):
        src = io.BytesIO(b"".join(json.dumps(ev(seq=i + 1)).encode() + b"\n" for i in range(5)))
        result = audit_stream(src, max_events=2)
        self.assertEqual(result["exit_code"], 3)
        self.assertIn("INPUT_LIMIT_REACHED", result["finding_counts"])


class EffectSafetyTests(unittest.TestCase):
    def test_reserved_without_ack_is_unknown_not_retryable(self):
        reserve = ev(kind="tool.effect.reserved", effect_key="git:commit:abc", lease_fence=3)
        r = audit(reserve)
        self.assertEqual(r["status"], "requires_effect_reconciliation")
        self.assertFalse(r["external_effect_retry_allowed"])

    def test_reserved_with_ack_receipt_is_no_longer_unacknowledged(self):
        r = audit(ev(seq=1, kind="tool.effect.reserved", effect_key="op:abc", lease_fence=3),
                  ev(seq=2, kind="tool.effect.acknowledged", effect_key="op:abc",
                     lease_fence=3, evidence_refs=["receipt:opaque-id"]))
        self.assertEqual(r["exit_code"], 0)
        self.assertFalse(r["external_effect_retry_allowed"])

    def test_ack_without_receipt_does_not_clear_ambiguity(self):
        r = audit(ev(seq=1, kind="tool.effect.reserved", effect_key="op:abc", lease_fence=3),
                  ev(seq=2, kind="tool.effect.acknowledged", effect_key="op:abc", lease_fence=3))
        self.assertIn("EFFECT_OUTCOME_UNKNOWN", r["finding_counts"])
        self.assertIn("ACK_WITHOUT_EVIDENCE_REF", r["finding_counts"])

    def test_ack_without_reservation_is_incomplete(self):
        r = audit(ev(kind="tool.effect.acknowledged", effect_key="op:abc", lease_fence=3,
                     evidence_refs=["receipt:opaque-id"]))
        self.assertEqual(r["exit_code"], 3)
        self.assertIn("ACK_WITHOUT_RESERVATION_IN_SNAPSHOT", r["finding_counts"])

    def test_explicit_unknown_persists_even_after_claimed_ack(self):
        r = audit(ev(seq=1, kind="tool.effect.reserved", effect_key="op:abc", lease_fence=3),
                  ev(seq=2, kind="tool.effect.unknown", effect_key="op:abc", lease_fence=3),
                  ev(seq=3, kind="tool.effect.acknowledged", effect_key="op:abc", lease_fence=3,
                     evidence_refs=["receipt:unverified"]))
        self.assertEqual(r["status"], "requires_effect_reconciliation")

    def test_reconcile_claim_not_automatically_trusted(self):
        r = audit(ev(seq=1, kind="tool.effect.unknown", effect_key="op:abc", lease_fence=3),
                  ev(seq=2, kind="tool.effect.reconciled", effect_key="op:abc", lease_fence=3,
                     evidence_refs=["receipt:opaque-id"], trust_level="verifier_attested"))
        self.assertIn("RECONCILIATION_CLAIM_REQUIRES_LEDGER", r["finding_counts"])
        self.assertIn("EFFECT_OUTCOME_UNKNOWN", r["finding_counts"])

    def test_success_with_unknown_effect_flagged(self):
        r = audit(ev(seq=1, kind="tool.effect.reserved", effect_key="op:abc", lease_fence=1),
                  ev(seq=2, kind="task.completed", state_to="succeeded", target_revision="abc"))
        self.assertIn("SUCCESS_WHILE_EFFECT_UNRESOLVED", r["finding_counts"])
        self.assertEqual(r["exit_code"], 2)

    def test_success_with_matching_verifier_is_still_not_certified(self):
        r = audit(ev(seq=1, kind="verifier.completed", target_revision="sha:abc",
                     evidence_refs=["ci:run-7"]),
                  ev(seq=2, kind="task.completed", state_to="succeeded", target_revision="sha:abc"))
        self.assertEqual(r["exit_code"], 0)
        self.assertEqual(r["authority"], "UNTRUSTED_OFFLINE_DIAGNOSTIC_ONLY")

    def test_ci_revision_mismatch_flagged_as_incomplete(self):
        r = audit(ev(seq=1, kind="verifier.completed", target_revision="sha:old",
                     evidence_refs=["ci:old"]),
                  ev(seq=2, kind="task.completed", state_to="succeeded", target_revision="sha:new"))
        self.assertIn("SUCCESS_WITHOUT_REVISION_VERIFIER_IN_SNAPSHOT", r["finding_counts"])

    def test_two_workers_claiming_same_fence(self):
        r = audit(ev(producer="agent-a", agent_id="A", lease_fence=8, kind="task.claimed"),
                  ev(producer="agent-b", agent_id="B", lease_fence=8, kind="task.claimed"))
        self.assertIn("FENCE_OWNER_CONFLICT", r["finding_counts"])

    def test_30_producers_may_legally_have_the_same_sequence_number(self):
        r = audit(*[ev(producer=f"agent-{i}", seq=1) for i in range(30)])
        self.assertEqual(r["exit_code"], 0)
        self.assertEqual(r["counts"]["producer_count"], 30)

    def test_same_named_agent_in_two_processes_is_two_fence_claimants(self):
        first = ev(producer="process-boot-a", seq=1, kind="task.claimed",
                   agent_id="A1", lease_fence=4)
        second = ev(producer="process-boot-b", seq=1, kind="task.claimed",
                    agent_id="A1", lease_fence=4)
        result = audit(first, second)
        self.assertIn("FENCE_OWNER_CONFLICT", result["finding_counts"])
        self.assertEqual(result["status"], "integrity_anomaly")

    def test_cross_fence_effect_reuse_not_silent(self):
        r = audit(ev(seq=1, kind="tool.effect.reserved", effect_key="write:abc", lease_fence=2),
                  ev(seq=2, kind="tool.effect.reserved", effect_key="write:abc", lease_fence=3))
        self.assertIn("EFFECT_REUSED_ACROSS_FENCES", r["finding_counts"])

    def test_cross_producer_ack_requires_causation(self):
        reserve = ev(seq=1, producer="agent-a", kind="tool.effect.reserved",
                     effect_key="op:abc", lease_fence=2)
        ack = ev(seq=1, producer="agent-b", kind="tool.effect.acknowledged",
                 effect_key="op:abc", lease_fence=2, evidence_refs=["receipt:abc"])
        r = audit(reserve, ack)
        self.assertIn("ACK_CAUSAL_PROOF_MISSING", r["finding_counts"])
        self.assertIn("EFFECT_OUTCOME_UNKNOWN", r["finding_counts"])
        ack["causation_event_id"] = reserve["event_id"]
        r = audit(reserve, ack)
        self.assertEqual(r["exit_code"], 0)

    def test_ack_preceding_reservation_is_not_sufficient(self):
        r = audit(ev(seq=1, kind="tool.effect.acknowledged", effect_key="op:abc",
                     lease_fence=2, evidence_refs=["receipt:abc"]),
                  ev(seq=2, kind="tool.effect.reserved", effect_key="op:abc", lease_fence=2))
        self.assertIn("ACK_CAUSAL_PROOF_MISSING", r["finding_counts"])

    def test_distinct_reservations_same_effect_are_high_risk(self):
        r = audit(ev(seq=1, kind="tool.effect.reserved", effect_key="op:abc", lease_fence=2),
                  ev(seq=2, kind="tool.effect.reserved", effect_key="op:abc", lease_fence=2),
                  ev(seq=3, kind="tool.effect.acknowledged", effect_key="op:abc",
                     lease_fence=2, evidence_refs=["receipt:abc"]))
        self.assertIn("MULTIPLE_EFFECT_RESERVATIONS", r["finding_counts"])
        self.assertIn("EFFECT_OUTCOME_UNKNOWN", r["finding_counts"])

    def test_stop_reason_is_observation_not_verified_cause(self):
        r = audit(ev(kind="task.blocked", reason_code="POLICY_DENIED"))
        self.assertEqual(r["stop_observations"][0]["reason_code"], "POLICY_DENIED")
        self.assertEqual(r["stop_observations"][0]["basis"], "UNTRUSTED_REPORTED_METADATA")
        self.assertEqual(r["exit_code"], 0)

    def test_unexplained_stop_remains_incomplete(self):
        r = audit(ev(kind="task.blocked"))
        self.assertIn("STOP_WITHOUT_REASON_CODE", r["finding_counts"])

    def test_unknown_effect_followed_by_rejected_payload_never_green(self):
        r = audit(ev(kind="tool.effect.reserved", effect_key="write:abc", lease_fence=2),
                  ev(seq=2, kind="task.completed", state_to="succeeded", target_revision="sha:new"),
                  ev(seq=3, kind="tool.effect.acknowledged", effect_key="write:abc", lease_fence=4,
                     evidence_refs=["receipt:other-fence"]))
        self.assertEqual(r["status"], "requires_effect_reconciliation")


if __name__ == "__main__":
    unittest.main()
