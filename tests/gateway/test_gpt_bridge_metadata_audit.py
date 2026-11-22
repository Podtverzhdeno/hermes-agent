"""Deterministic offline contract tests, no provider account or live browser."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from uuid import NAMESPACE_URL, uuid5

from gateway.gpt_bridge_metadata_audit import (
    MAX_EVENT_BYTES,
    CausalAuditor,
    InvalidEvent,
    audit_ndjson,
    main,
    validate_event,
)


def uid(name: str) -> str:
    return str(uuid5(NAMESPACE_URL, name))


def ev(seq=1, kind="task.received", *, producer="producer-1", task="task-one",
       causal=None, effect_key=None, fence=1, trust="adapter_observed", **update):
    record = {
        "schema_version": 1,
        "event_id": uid(f"{producer}-{seq}-{task}-{kind}"),
        "source": "worker",
        "producer_id": producer,
        "source_event_seq": seq,
        "run_id": uid("run-one"),
        "task_id": uid(task),
        "attempt_id": uid("attempt-one"),
        "agent_id": "A3/worker-2",
        "lease_fence": fence,
        "trace_id": "f" * 32,
        "span_id": "a" * 16,
        "parent_span_id": None,
        "causation_event_id": causal,
        "occurred_at_utc": "2026-11-22T10:00:00Z",
        "observed_at_utc": "2026-11-22T10:00:01Z",
        "kind": kind,
        "state_from": "running",
        "state_to": "running",
        "reason_code": None,
        "target_revision": "1" * 40,
        "effect_key": effect_key,
        "evidence_refs": [],
        "trust_level": trust,
    }
    record.update(update)
    return record


class ValidationTests(unittest.TestCase):
    def test_valid_sdd_envelope(self):
        self.assertEqual(validate_event(ev())["schema_version"], 1)

    def test_reject_secret_field_without_echoing_secret(self):
        record = ev()
        record["token"] = "do-not-repeat"
        with self.assertRaises(InvalidEvent) as exc:
            validate_event(record)
        self.assertNotIn("do-not-repeat", str(exc.exception))

    def test_reject_prompt_and_tool_args(self):
        for key in ("prompt", "content", "tool_arguments", "authorization"):
            record = ev()
            record[key] = "secret"
            with self.assertRaises(InvalidEvent):
                validate_event(record)

    def test_reject_missing_fields(self):
        record = ev()
        del record["producer_id"]
        with self.assertRaises(InvalidEvent):
            validate_event(record)

    def test_boolean_sequence_is_not_an_int(self):
        for key in ("source_event_seq", "lease_fence", "schema_version"):
            record = ev()
            record[key] = True
            with self.assertRaises(InvalidEvent):
                validate_event(record)

    def test_recursive_python_metadata_is_rejected_as_invalid(self):
        record = ev()
        nested = []
        cursor = nested
        for _ in range(1200):
            next_level = []
            cursor.append(next_level)
            cursor = next_level
        record["evidence_refs"] = nested
        with self.assertRaises(InvalidEvent):
            validate_event(record)

    def test_deeply_nested_ndjson_does_not_crash(self):
        line = (b"[" * 1200) + b"0" + (b"]" * 1200) + b"\n"
        report = audit_ndjson([line])
        self.assertEqual(report.rejected, 1)

    def test_gap_report_redacts_sensitive_producer_name(self):
        auditor = CausalAuditor()
        producer = "a:private_marker"
        auditor.ingest(ev(1, producer=producer))
        auditor.ingest(ev(3, producer=producer))
        report_text = json.dumps(auditor.summarize().as_dict())
        self.assertNotIn(producer, report_text)
        self.assertIn("producer_id_digest", report_text)

    def test_reject_unknown_version(self):
        with self.assertRaises(InvalidEvent):
            validate_event(ev(schema_version=2))

    def test_unhashable_kind_rejected_not_exception(self):
        with self.assertRaises(InvalidEvent):
            validate_event(ev(kind=["task.received"]))

    def test_unhashable_trust_rejected_not_exception(self):
        with self.assertRaises(InvalidEvent):
            validate_event(ev(trust_level=["trusted_verifier"]))

    def test_uuid_trace_and_span_formats(self):
        for key, value in (("event_id", "x"), ("trace_id", "123"),
                           ("span_id", "zzzzzzzzzzzzzzzz"),
                           ("causation_event_id", "bad")):
            record = ev()
            record[key] = value
            with self.assertRaises(InvalidEvent):
                validate_event(record)

    def test_effect_requires_stable_id(self):
        for kind in ("tool.effect.reserved", "tool.effect.acknowledged", "tool.effect.unknown"):
            with self.assertRaises(InvalidEvent):
                validate_event(ev(kind=kind))

    def test_reject_unbounded_event(self):
        record = ev()
        record["producer_id"] = "x" * MAX_EVENT_BYTES
        with self.assertRaises(InvalidEvent):
            validate_event(record)

    def test_reject_url_shaped_evidence_ref(self):
        record = ev()
        record["evidence_refs"] = ["https://private.example/token?secret=abc"]
        with self.assertRaises(InvalidEvent):
            validate_event(record)

    def test_reject_bad_evidence_refs_types(self):
        for refs in (None, {}, ["a"] * 17, [5]):
            with self.assertRaises(InvalidEvent):
                validate_event(ev(evidence_refs=refs))

    def test_canonical_uuid_only(self):
        with self.assertRaises(InvalidEvent):
            validate_event(ev(event_id=uid("test").upper()))

    def test_bad_date_rejected(self):
        with self.assertRaises(InvalidEvent):
            validate_event(ev(occurred_at_utc="2026-13-40T25:61:61Z"))

    def test_unknown_source_rejected(self):
        with self.assertRaises(InvalidEvent):
            validate_event(ev(source="private-email-or-token"))

    def test_null_reason_is_valid(self):
        self.assertIsNone(validate_event(ev())["reason_code"])


class AuditTests(unittest.TestCase):
    def test_exact_duplicate_replay_is_idempotent(self):
        auditor = CausalAuditor()
        e = ev()
        auditor.ingest(e)
        auditor.ingest(dict(e))
        report = auditor.summarize()
        self.assertEqual(report.accepted, 1)
        self.assertEqual(report.duplicate_replays, 1)
        self.assertEqual(report.rejected, 0)

    def test_same_event_id_different_payload_is_collision(self):
        auditor = CausalAuditor()
        e = ev()
        auditor.ingest(e)
        auditor.ingest(dict(e, kind="task.blocked"))
        self.assertIn("EVENT_ID_COLLISION", [p["code"] for p in auditor.summarize().problems])

    def test_same_producer_sequence_different_event_is_collision(self):
        auditor = CausalAuditor()
        auditor.ingest(ev(1))
        auditor.ingest(ev(1, kind="worker.started"))
        self.assertIn("PRODUCER_SEQUENCE_COLLISION", [p["code"] for p in auditor.summarize().problems])

    def test_different_producers_can_start_at_one(self):
        auditor = CausalAuditor()
        auditor.ingest(ev(1, producer="a"))
        auditor.ingest(ev(1, producer="b"))
        self.assertEqual(auditor.summarize().accepted, 2)

    def test_reordered_delivery_does_not_create_false_gap(self):
        auditor = CausalAuditor()
        for n in (3, 1, 2):
            auditor.ingest(ev(n, producer="p"))
        report = auditor.summarize()
        self.assertNotIn("POSSIBLE_SOURCE_GAP", [p["code"] for p in report.problems])

    def test_gap_is_unconfirmed_not_task_failure(self):
        auditor = CausalAuditor()
        auditor.ingest(ev(10))
        auditor.ingest(ev(13))
        problems = [p for p in auditor.summarize().problems if p["code"] == "POSSIBLE_SOURCE_GAP"]
        self.assertEqual(problems[0]["missing_count"], 2)
        self.assertEqual(problems[0]["confidence"], "unconfirmed")

    def test_earliest_sequence_may_be_partial_export(self):
        auditor = CausalAuditor()
        auditor.ingest(ev(10))
        self.assertFalse(any(p["code"] == "POSSIBLE_SOURCE_GAP" for p in auditor.summarize().problems))

    def test_unseen_parent_does_not_invent_failure(self):
        auditor = CausalAuditor()
        auditor.ingest(ev(causal=uid("missing")))
        self.assertIn("CAUSAL_PARENT_UNOBSERVED", [p["code"] for p in auditor.summarize().problems])

    def test_causal_cycle_detected(self):
        a, b = ev(1), ev(2)
        a["causation_event_id"] = b["event_id"]
        b["causation_event_id"] = a["event_id"]
        auditor = CausalAuditor()
        auditor.ingest(a)
        auditor.ingest(b)
        self.assertIn("CAUSAL_CYCLE", [p["code"] for p in auditor.summarize().problems])

    def test_long_chain_does_not_recurse(self):
        auditor = CausalAuditor(max_events=3000)
        last = None
        for n in range(1, 2002):
            event = ev(n, causal=last)
            auditor.ingest(event)
            last = event["event_id"]
        self.assertEqual(auditor.summarize().accepted, 2001)

    def test_reservation_without_ack_never_autoretry(self):
        auditor = CausalAuditor()
        auditor.ingest(ev(kind="tool.effect.reserved", effect_key="effect-one"))
        task = auditor.summarize().tasks[uid("task-one")]
        self.assertIn("EFFECT_OUTCOME_UNKNOWN", task["diagnostic_flags"])
        self.assertEqual(task["next_safe_action"], "reconcile_external_receipt_before_retry")
        self.assertFalse(task["automatic_retry_allowed"])

    def test_unknown_effect_after_ack_stays_unknown(self):
        auditor = CausalAuditor()
        auditor.ingest(ev(1, kind="tool.effect.reserved", effect_key="effect-one"))
        auditor.ingest(ev(2, kind="tool.effect.acknowledged", effect_key="effect-one"))
        auditor.ingest(ev(3, kind="tool.effect.unknown", effect_key="effect-one"))
        self.assertIn("EFFECT_OUTCOME_UNKNOWN",
                      auditor.summarize().tasks[uid("task-one")]["diagnostic_flags"])

    def test_bare_ack_has_warning(self):
        auditor = CausalAuditor()
        auditor.ingest(ev(1, kind="tool.effect.acknowledged", effect_key="effect-one"))
        flags = auditor.summarize().tasks[uid("task-one")]["diagnostic_flags"]
        self.assertIn("EFFECT_ACK_WITHOUT_RESERVATION", flags)
        self.assertIn("EFFECT_ACK_PROOF_UNAVAILABLE", flags)

    def test_fence_conflict_is_visible(self):
        auditor = CausalAuditor()
        auditor.ingest(ev(1, kind="tool.effect.reserved", effect_key="effect-one", fence=1))
        auditor.ingest(ev(2, kind="tool.effect.acknowledged", effect_key="effect-one", fence=2))
        self.assertIn("EFFECT_FENCE_DIVERGENCE",
                      auditor.summarize().tasks[uid("task-one")]["diagnostic_flags"])

    def test_completion_without_verifier_is_unverified(self):
        auditor = CausalAuditor()
        auditor.ingest(ev(1, kind="task.completed"))
        flags = auditor.summarize().tasks[uid("task-one")]["diagnostic_flags"]
        self.assertIn("COMPLETION_NOT_INDEPENDENTLY_VERIFIED", flags)
        self.assertEqual(auditor.summarize().tasks[uid("task-one")]["ledger_state"], "not_read_in_this_tool")

    def test_claimed_verifier_not_treated_as_trusted(self):
        auditor = CausalAuditor()
        auditor.ingest(ev(1, kind="task.completed"))
        auditor.ingest(ev(2, kind="verifier.completed", trust="producer_claimed"))
        self.assertIn("COMPLETION_NOT_INDEPENDENTLY_VERIFIED",
                      auditor.summarize().tasks[uid("task-one")]["diagnostic_flags"])

    def test_ack_self_trust_is_not_authentication(self):
        auditor = CausalAuditor()
        auditor.ingest(ev(1, kind="tool.effect.reserved", effect_key="private-secret-123"))
        auditor.ingest(ev(2, kind="tool.effect.acknowledged", effect_key="private-secret-123",
                          trust="trusted_verifier", evidence_refs=["receipt-42"]))
        task = auditor.summarize().tasks[uid("task-one")]
        self.assertIn("EFFECT_ACK_NEEDS_AUTHENTICATED_RECEIPT", task["diagnostic_flags"])
        self.assertNotIn("private-secret-123", json.dumps(task))
        self.assertFalse(task["automatic_retry_allowed"])

    def test_contradictory_causal_sequence_detected(self):
        ancestor = ev(2, kind="worker.started")
        child = ev(1, kind="worker.heartbeat", causal=ancestor["event_id"])
        auditor = CausalAuditor()
        auditor.ingest(ancestor)
        auditor.ingest(child)
        self.assertIn("CAUSAL_SEQUENCE_CONTRADICTION",
                      [x["code"] for x in auditor.summarize().problems])

    def test_denied_permission_causes_stop_recommendation(self):
        auditor = CausalAuditor()
        auditor.ingest(ev(1, kind="approval.denied"))
        task = auditor.summarize().tasks[uid("task-one")]
        self.assertIn("POLICY_DENIED", task["candidate_stop_reasons"])
        self.assertEqual(task["next_safe_action"], "verify_approval_binding_and_stop_retries")

    def test_rate_limit_requires_shared_budget(self):
        auditor = CausalAuditor()
        auditor.ingest(ev(1, kind="model.throttled"))
        task = auditor.summarize().tasks[uid("task-one")]
        self.assertEqual(task["next_safe_action"], "confirm_retry_after_and_shared_provider_budget")
        self.assertEqual(task["reason_confidence"], "unverified_metadata_only")

    def test_metadata_only_report_no_prompt_or_cookies(self):
        auditor = CausalAuditor()
        auditor.ingest(dict(ev(), token="SUPER_SECRET"))
        payload = json.dumps(auditor.summarize().as_dict())
        self.assertNotIn("SUPER_SECRET", payload)

    def test_finite_capacity_does_not_drop_previous_events(self):
        auditor = CausalAuditor(max_events=1)
        auditor.ingest(ev(1))
        auditor.ingest(ev(2))
        report = auditor.summarize()
        self.assertEqual(report.accepted, 1)
        self.assertIn("EVENT_LIMIT_REACHED", [p["code"] for p in report.problems])

    def test_reason_codes_are_diagnostic_not_permissions(self):
        auditor = CausalAuditor()
        auditor.ingest(ev(1, kind="task.blocked", reason_code="POLICY_DENIED"))
        task = auditor.summarize().tasks[uid("task-one")]
        self.assertIn("POLICY_DENIED", task["blocked_reasons_observed"])
        self.assertFalse(task["automatic_retry_allowed"])

    def test_observer_disconnected_doesnt_mean_task_failed(self):
        auditor = CausalAuditor()
        auditor.ingest(ev(1, kind="bridge.disconnected"))
        task = auditor.summarize().tasks[uid("task-one")]
        self.assertIn("BRIDGE_DISCONNECTED_OBSERVED", task["diagnostic_flags"])
        self.assertEqual(task["ledger_state"], "not_read_in_this_tool")

    def test_cross_task_causality_is_review_only(self):
        a = ev(1, task="first")
        b = ev(2, task="second", causal=a["event_id"])
        auditor = CausalAuditor()
        auditor.ingest(a)
        auditor.ingest(b)
        self.assertIn("CROSS_TASK_CAUSATION_REVIEW", [p["code"] for p in auditor.summarize().problems])


class NDJSONTests(unittest.TestCase):
    def test_reject_duplicate_json_keys(self):
        raw = json.dumps(ev()).encode()
        dup = raw[:-1] + b',"event_id":"other"}'
        report = audit_ndjson([dup])
        self.assertEqual(report.rejected, 1)
        self.assertEqual(report.accepted, 0)

    def test_reject_oversized_line(self):
        report = audit_ndjson([b"x" * 4097])
        self.assertIn("INPUT_LINE_TOO_LARGE", [p["code"] for p in report.problems])

    def test_valid_ndjson_and_empty_lines(self):
        report = audit_ndjson([b"\n", json.dumps(ev()).encode() + b"\n"])
        self.assertEqual(report.accepted, 1)
        self.assertEqual(report.rejected, 0)

    def test_cli_atomic_report_is_metadata_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_file = Path(tmp) / "events.ndjson"
            output = Path(tmp) / "report.json"
            input_file.write_text(json.dumps(ev()) + "\n", encoding="utf-8")
            output.write_text("old", encoding="utf-8")
            self.assertEqual(main([str(input_file), "--output", str(output)]), 0)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["accepted"], 1)
            self.assertFalse(list(Path(tmp).glob(".gpt-audit-*")))


if __name__ == "__main__":
    unittest.main()
