"""Unit tests for the read-only GPT bridge trace doctor, no browser or network."""
from datetime import datetime, timedelta, timezone
import json
import tempfile
from pathlib import Path
import unittest

from hermes_gpt_bridge.diagnostics import Event, TraceError, analyze, load_jsonl
from scripts.gpt_bridge_trace_doctor import main

NOW = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)
SHA = "a" * 40
OTHER_SHA = "b" * 40


def event(kind, number, *, run="run1", emitter="collector.local", attempt="attempt1", **kw):
    raw = dict(schema_version=1, event_id=f"e{number}", run_id=run,
               attempt_id=attempt, emitter_id=emitter, seq=number, kind=kind,
               observed_at=(NOW - timedelta(seconds=10)).isoformat(), **kw)
    return Event.parse(raw)


def codes(events, **kw):
    return {x.code for x in analyze(events, now=NOW, **kw)}


class SchemaTests(unittest.TestCase):
    def test_rejects_prompt_payload(self):
        raw = event("run.created", 1).__dict__.copy()
        raw.update(observed_at=NOW.isoformat(), prompt="secret input")
        with self.assertRaises(TraceError):
            Event.parse(raw)

    def test_rejects_cookies_tokens_or_response_fields(self):
        base = event("run.created", 1).__dict__.copy()
        base["observed_at"] = NOW.isoformat()
        for key in ("cookie", "raw_response", "api_key", "url", "authorization"):
            with self.subTest(key=key), self.assertRaises(TraceError):
                Event.parse({**base, key: "do not store"})

    def test_utc_required(self):
        base = dict(event("run.created", 1).__dict__)
        for s in ("2026-11-22T12:00:00", "2026-11-22T12:00:00+03:00", "oops"):
            with self.subTest(s=s), self.assertRaises(TraceError):
                Event.parse({**base, "observed_at": s})

    def test_nonstring_and_wrong_types_are_rejected(self):
        base = event("run.created", 1).__dict__.copy()
        base["observed_at"] = NOW.isoformat()
        for field, value in (("seq", True), ("fence", 0), ("http_status", 999),
                             ("retry_after_seconds", -1), ("kind", []), ("revision", "main")):
            with self.subTest(field=field), self.assertRaises(TraceError):
                Event.parse({**base, field: value})

    def test_blank_missing_fields_and_invalid_schema(self):
        with self.assertRaises(TraceError):
            Event.parse({})
        with self.assertRaises(TraceError):
            Event.parse({"schema_version": 9})
        with self.assertRaises(TraceError):
            Event.parse([])

    def test_receipt_digest_never_raw_receipt(self):
        self.assertEqual(event("effect.acknowledged", 1, operation_id="o1", receipt_digest="c" * 64).receipt_digest, "c" * 64)
        with self.assertRaises(TraceError):
            event("effect.acknowledged", 1, operation_id="o1", receipt_digest="my-cookie")

    def test_jsonl_loader_size_and_event_limits(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "trace.jsonl"
            raw = event("run.created", 1).__dict__.copy()
            raw["observed_at"] = NOW.isoformat()
            p.write_text(json.dumps(raw) + "\n\n", encoding="utf-8")
            self.assertEqual(len(load_jsonl(p)), 1)
            with self.assertRaises(TraceError):
                load_jsonl(p, max_events=0)
            p.write_bytes(b"x" * 20_000)
            with self.assertRaises(TraceError):
                load_jsonl(p)


class DiagnosisTests(unittest.TestCase):
    def test_clean_completion(self):
        self.assertEqual(codes([event("run.created", 1), event("artifact.committed", 2, revision=SHA),
                                event("verification.passed", 3, revision=SHA), event("run.completed", 4, revision=SHA)]), set())

    def test_completion_no_evidence(self):
        self.assertIn("COMPLETED_WITHOUT_MATCHED_EVIDENCE", codes([event("run.completed", 1, revision=SHA)]))

    def test_completion_mismatched_revision(self):
        evs = [event("artifact.committed", 1, revision=SHA), event("verification.passed", 2, revision=SHA),
               event("run.completed", 3, revision=OTHER_SHA)]
        self.assertIn("COMPLETED_WITHOUT_MATCHED_EVIDENCE", codes(evs))

    def test_effect_reserved_outcome_unknown(self):
        self.assertIn("UNKNOWN_EXTERNAL_OUTCOME", codes([event("effect.reserved", 1, operation_id="op1")]))

    def test_effect_reservation_acknowledged(self):
        self.assertNotIn("UNKNOWN_EXTERNAL_OUTCOME", codes([
            event("effect.reserved", 1, operation_id="op1"),
            event("effect.acknowledged", 2, operation_id="op1", receipt_digest="d" * 64)]))

    def test_effect_reconciled(self):
        self.assertNotIn("UNKNOWN_EXTERNAL_OUTCOME", codes([
            event("effect.reserved", 1, operation_id="op1"),
            event("effect.reconciled", 2, operation_id="op1", receipt_digest="a" * 64)]))

    def test_dispatched_no_response_is_uncertain(self):
        results = analyze([event("bridge.request_dispatched", 1, operation_id="op1")], now=NOW)
        x = next(d for d in results if d.code == "UNCONFIRMED_BRIDGE_REQUEST")
        self.assertEqual(x.certainty, "hypothesis")
        self.assertNotIn("COMPLETED_WITHOUT_MATCHED_EVIDENCE", {d.code for d in results})

    def test_dispatched_with_response(self):
        self.assertNotIn("UNCONFIRMED_BRIDGE_REQUEST", codes([
            event("bridge.request_dispatched", 1, operation_id="op1"),
            event("bridge.response_received", 2, operation_id="op1")]))

    def test_silence_flag_only_if_active(self):
        self.assertIn("PROGRESS_SILENCE", codes([event("run.started", 1)], stale_after_seconds=5))
        self.assertNotIn("PROGRESS_SILENCE", codes([event("run.failed", 1)], stale_after_seconds=5))
        self.assertNotIn("PROGRESS_SILENCE", codes([event("run.started", 1)], stale_after_seconds=120))

    def test_disconnect_unresolved_and_recovered(self):
        evs = [event("bridge.transport_disconnected", 1)]
        self.assertIn("SESSION_CHANNEL_UNAVAILABLE", codes(evs))
        reconnect = event("bridge.transport_reconnected", 2)
        # Give the collector a later arrival time, not the same timestamp.
        reconnect = Event(**{**reconnect.__dict__, "observed_at": NOW - timedelta(seconds=5)})
        self.assertNotIn("SESSION_CHANNEL_UNAVAILABLE", codes(evs + [reconnect]))

    def test_service_worker_suspended(self):
        self.assertIn("SESSION_CHANNEL_UNAVAILABLE", codes([event("browser.service_worker_suspended", 1)]))

    def test_auth_failure_is_blocking(self):
        self.assertIn("AUTH_BLOCKED", codes([event("provider.auth_failed", 1)]))

    def test_rate_limit_missing_backoff_hint(self):
        self.assertIn("RATE_LIMIT_WITHOUT_BACKOFF_HINT", codes([event("provider.rate_limited", 1)]))
        self.assertNotIn("RATE_LIMIT_WITHOUT_BACKOFF_HINT", codes([
            event("provider.rate_limited", 1, retry_after_seconds=10)]))

    def test_duplicate_delivery_same_event(self):
        e = event("run.created", 1)
        self.assertNotIn("EVENT_ID_COLLISION", codes([e, e]))

    def test_event_id_collision(self):
        one = event("run.created", 1)
        two = event("run.started", 1)
        self.assertIn("EVENT_ID_COLLISION", codes([one, two]))

    def test_sequence_conflict(self):
        one = event("run.created", 1)
        two = event("run.started", 1)
        two = Event(**{**two.__dict__, "event_id": "different"})
        self.assertIn("SEQUENCE_CONFLICT", codes([one, two]))

    def test_sequence_gap_is_hypothesis(self):
        ds = analyze([event("run.created", 1), event("run.started", 3)], now=NOW)
        x = next(d for d in ds if d.code == "SEQUENCE_GAP")
        self.assertEqual(x.certainty, "hypothesis")

    def test_multi_emitter_sequence_independent(self):
        self.assertNotIn("SEQUENCE_CONFLICT", codes([
            event("run.created", 1, emitter="hermes"),
            event("run.started", 1, emitter="extension")]))

    def test_stale_fence_rejected(self):
        grants = event("worker.lease_granted", 1, fence=10)
        newgrant = event("worker.lease_granted", 2, fence=11)
        newgrant = Event(**{**newgrant.__dict__, "observed_at": NOW - timedelta(seconds=8)})
        stale = event("run.completed", 3, revision=SHA, fence=10)
        stale = Event(**{**stale.__dict__, "observed_at": NOW - timedelta(seconds=6)})
        self.assertIn("STALE_FENCE_WRITE", codes([grants, newgrant, stale]))

    def test_terminal_conflict(self):
        self.assertIn("TERMINAL_STATE_CONFLICT", codes([
            event("run.failed", 1), event("run.completed", 2, revision=SHA)]))

    def test_multi_run_isolation(self):
        d = analyze([event("effect.reserved", 1, run="runA", operation_id="o1"),
                     event("run.completed", 1, run="runB", revision=SHA)], now=NOW)
        self.assertEqual({x.run_id for x in d}, {"runA", "runB"})

    def test_no_automatic_side_effect(self):
        # A monitor should merely return deterministic diagnostics, never dispatch.
        events = [event("effect.reserved", 1, operation_id="danger")]
        self.assertEqual([d.as_dict() for d in analyze(events, now=NOW)],
                         [d.as_dict() for d in analyze(events, now=NOW)])


class CliTests(unittest.TestCase):
    def test_critical_exit(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "trace.jsonl"
            raw = dict(event("effect.reserved", 1, operation_id="op").__dict__)
            raw["observed_at"] = NOW.isoformat()
            p.write_text(json.dumps(raw), encoding="utf-8")
            self.assertEqual(main([str(p)]), 1)


if __name__ == "__main__":
    unittest.main()

class SnapshotTests(unittest.TestCase):
    def test_orthogonal_status_never_says_unauthenticated_success(self):
        from hermes_gpt_bridge import summarize
        s = summarize([event("run.started", 1), event("artifact.committed", 2, revision=SHA),
                       event("verification.passed", 3, revision=SHA),
                       event("run.completed", 4, revision=SHA)], now=NOW)[0]
        self.assertEqual(s.execution, "reported_completed")
        self.assertEqual(s.evidence, "reported_revision_matched")
        self.assertEqual(s.transport, "unobserved")
        self.assertEqual(s.provider, "unobserved")

    def test_cancellation_does_not_clear_effects(self):
        from hermes_gpt_bridge import summarize
        s = summarize([event("effect.reserved", 1, operation_id="op1"),
                       event("run.cancelled", 2)], now=NOW)[0]
        self.assertEqual(s.execution, "cancelled")
        self.assertEqual(s.effects, "needs_reconciliation")

    def test_browser_disconnected_does_not_equal_failed(self):
        from hermes_gpt_bridge import summarize
        s = summarize([event("run.started", 1), event("bridge.transport_disconnected", 2)], now=NOW)[0]
        self.assertEqual(s.execution, "reported_running")
        self.assertEqual(s.transport, "reported_unavailable")

    def test_duplicate_effect_reservation_alert(self):
        e = [event("effect.reserved", 1, operation_id="op1"),
             event("effect.reserved", 2, operation_id="op1"),
             event("effect.acknowledged", 3, operation_id="op1", receipt_digest="a" * 64)]
        self.assertIn("DUPLICATE_EFFECT_RESERVATION", codes(e))

class EffectReceiptTests(unittest.TestCase):
    def test_closure_without_receipt_remains_unknown(self):
        evs = [event("effect.reserved", 1, operation_id="op1"),
               event("effect.acknowledged", 2, operation_id="op1")]
        self.assertIn("UNKNOWN_EXTERNAL_OUTCOME", codes(evs))
        self.assertIn("EFFECT_CLOSURE_NO_RECEIPT", codes(evs))

    def test_orphan_ack_never_certifies_effect(self):
        evs = [event("effect.acknowledged", 1, operation_id="op1", receipt_digest="f" * 64)]
        self.assertIn("ORPHAN_EFFECT_CLOSURE", codes(evs))

    def test_missing_operation_id_rejected(self):
        for kind in ("effect.reserved", "effect.acknowledged", "bridge.request_dispatched",
                     "bridge.response_received", "provider.request_accepted"):
            with self.subTest(kind=kind), self.assertRaises(TraceError):
                event(kind, 1)

    def test_synthetic_hundred_workers_isolated(self):
        e = [event("run.started", 1, run=f"r{i}", emitter=f"worker.{i}") for i in range(100)]
        d = analyze(e, now=NOW)
        self.assertEqual(d, [])
        from hermes_gpt_bridge import summarize
        self.assertEqual(len(summarize(e, now=NOW)), 100)


class DistinctChannelRecoveryTests(unittest.TestCase):
    def test_websocket_reconnect_does_not_reattach_tab(self):
        from hermes_gpt_bridge import summarize
        e = [event("browser.tab_detached", 1), event("bridge.transport_reconnected", 2)]
        self.assertIn("SESSION_CHANNEL_UNAVAILABLE", codes(e))
        self.assertEqual(summarize(e, now=NOW)[0].transport, "reported_unavailable")

    def test_service_worker_resume_does_not_restore_websocket(self):
        e = [event("bridge.transport_disconnected", 1), event("browser.service_worker_started", 2)]
        self.assertIn("SESSION_CHANNEL_UNAVAILABLE", codes(e))

    def test_tab_reconnect_requires_explicit_event(self):
        from hermes_gpt_bridge import summarize
        attached = event("browser.tab_attached", 2)
        attached = Event(**{**attached.__dict__, "observed_at": NOW - timedelta(seconds=5)})
        e = [event("browser.tab_detached", 1), attached]
        self.assertNotIn("SESSION_CHANNEL_UNAVAILABLE", codes(e))
        self.assertEqual(summarize(e, now=NOW)[0].transport, "partially_observed_connected")

    def test_all_three_components_required_for_full_connection(self):
        from hermes_gpt_bridge import summarize
        e = [event("browser.tab_attached", 1), event("browser.service_worker_started", 2),
             event("bridge.transport_reconnected", 3)]
        self.assertEqual(summarize(e, now=NOW)[0].transport, "reported_connected")

    def test_event_ids_are_globally_unique_in_run(self):
        first = event("run.created", 1, emitter="worker")
        second = event("run.started", 1, emitter="bridge")
        second = Event(**{**second.__dict__, "event_id": first.event_id})
        self.assertIn("EVENT_ID_COLLISION", codes([first, second]))


class BoundedIngestionTests(unittest.TestCase):
    def test_no_unbounded_readline(self):
        from unittest.mock import patch
        class FakeStream:
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def readline(self, size):
                self.requested_size = size
                return b"x" * (size + 1)
        fake = FakeStream()
        with patch("pathlib.Path.open", return_value=fake), self.assertRaises(TraceError):
            load_jsonl("unused")
        from hermes_gpt_bridge.diagnostics import MAX_LINE_BYTES
        self.assertEqual(fake.requested_size, MAX_LINE_BYTES + 1)

    def test_bounded_event_capacity(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "event.jsonl"
            one = dict(event("run.created", 1).__dict__)
            one["observed_at"] = NOW.isoformat()
            p.write_text(json.dumps(one) + "\n" + json.dumps(one), encoding="utf-8")
            with self.assertRaises(TraceError):
                load_jsonl(p, max_events=1)
            for bad in (-1, True, 0, 100000000):
                with self.subTest(bad=bad), self.assertRaises(TraceError):
                    load_jsonl(p, max_events=bad)

    def test_total_input_size_guard_does_not_expose_payload(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "events.jsonl"
            raw = dict(event("run.created", 1).__dict__)
            raw["observed_at"] = NOW.isoformat()
            p.write_text(json.dumps(raw) + "\n", encoding="utf-8")
            with patch("hermes_gpt_bridge.diagnostics.MAX_TOTAL_BYTES", 8):
                with self.assertRaisesRegex(TraceError, "total input size limit"):
                    load_jsonl(p)


class ReasonCodePrivacyTests(unittest.TestCase):
    def test_reason_codes_must_be_allowlisted(self):
        self.assertEqual(event("run.failed", 1, reason_code="NETWORK_TIMEOUT").reason_code,
                         "NETWORK_TIMEOUT")
        for bad in ("FREEFORM_ACCOUNT_NUMBER_92823", "private_token_123", "a" * 64):
            with self.subTest(value=bad), self.assertRaises(TraceError):
                event("run.failed", 1, reason_code=bad)
