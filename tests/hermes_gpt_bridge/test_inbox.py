"""No network, API calls, or browser dependencies: SQLite event ingestion contract."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hmac
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from hermes_gpt_bridge.inbox import EventInbox, InboxError

KEY = b"unit-test-only-not-a-real-secret__" * 2
NOW = datetime(2026, 11, 22, 13, 0, tzinfo=timezone.utc)


def frame(i=1, *, emitter="worker.1", run="run1", kind="run.started", **kwargs):
    obj = {"schema_version": 1, "event_id": f"event.{i}", "run_id": run,
           "attempt_id": "attempt.1", "emitter_id": emitter, "seq": i,
           "kind": kind, "observed_at": "2000-01-01T00:00:00Z", **kwargs}
    return json.dumps(obj, separators=(",", ":")).encode()


def signature(data):
    return hmac.new(KEY, data, hashlib.sha256).hexdigest()


class InboxTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "inbox.db"
        self.inbox = EventInbox(self.path, {"worker.1": KEY, "worker.2": KEY}, clock=lambda: NOW)

    def tearDown(self):
        self.dir.cleanup()

    def put(self, data, *, emitter="worker.1", sign=None):
        return self.inbox.ingest(data, identity=emitter,
                                 signature_hex=signature(data) if sign is None else sign)

    def test_insert_and_utc_collector_timestamp(self):
        p = frame()
        receipt = self.put(p)
        self.assertFalse(receipt.duplicate)
        rows = self.inbox.read_run("run1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].offset, receipt.offset)
        self.assertEqual(rows[0].event.observed_at, NOW)

    def test_same_canonical_json_deduplicates_despite_key_order(self):
        p = frame()
        a = self.put(p)
        semantically_identical = json.dumps(json.loads(p), sort_keys=True, indent=2).encode()
        b = self.put(semantically_identical)
        self.assertEqual((a.offset, b.duplicate), (b.offset, True))

    def test_secret_like_reason_code_rejected(self):
        p = frame(reason_code="client_private_token_123456789")
        with self.assertRaises(InboxError) as failure:
            self.put(p)
        self.assertNotIn("private_token", str(failure.exception))

    def test_allowed_reason_code(self):
        self.put(frame(reason_code="NETWORK_TIMEOUT"))
        self.assertEqual(self.inbox.read_run("run1")[0].event.reason_code, "NETWORK_TIMEOUT")

    def test_replay_returns_original_offset(self):
        p = frame()
        a, b = self.put(p), self.put(p)
        self.assertTrue(b.duplicate)
        self.assertEqual(a.offset, b.offset)
        self.assertEqual(len(self.inbox.read_run("run1")), 1)

    def test_corrupt_signature_denied(self):
        with self.assertRaises(InboxError):
            self.put(frame(), sign="0" * 64)
        self.assertEqual(self.inbox.read_run("run1"), [])

    def test_unknown_emitter_denied(self):
        p = frame(emitter="outsider")
        with self.assertRaises(InboxError):
            self.put(p, emitter="outsider")

    def test_signed_emitter_claim_mismatch_denied(self):
        with self.assertRaises(InboxError):
            self.put(frame(emitter="worker.2"))

    def test_same_event_id_with_different_body_denied(self):
        self.put(frame())
        with self.assertRaisesRegex(InboxError, "event ID collision"):
            self.put(frame(kind="run.failed"))

    def test_same_sequence_with_changed_event_id_denied(self):
        self.put(frame())
        p = frame().replace(b'"event.1"', b'"another.1"')
        with self.assertRaisesRegex(InboxError, "sequence collision"):
            self.put(p)

    def test_duplicate_json_properties_rejected_even_when_signed(self):
        p = frame()[:-1] + b',"seq":99}'
        with self.assertRaises(InboxError):
            self.put(p)

    def test_raw_prompt_rejected(self):
        p = frame()[:-1] + b',"prompt":"secret user message"}'
        with self.assertRaises(InboxError) as raised:
            self.put(p)
        self.assertNotIn("secret user message", str(raised.exception))

    def test_oversized_payload_rejected(self):
        p = frame() + (b" " * 20000)
        with self.assertRaises(InboxError):
            self.put(p)

    def test_restart_retains_records(self):
        r = self.put(frame())
        newer = EventInbox(self.path, {"worker.1": KEY}, clock=lambda: NOW)
        self.assertEqual(newer.read_run("run1")[0].offset, r.offset)

    def test_isolated_runs(self):
        self.put(frame(run="run1"))
        self.put(frame(run="run2"))
        self.assertEqual(len(self.inbox.read_run("run2")), 1)
        self.assertEqual(len(self.inbox.read_run("run1")), 1)

    def test_paging(self):
        for i in range(1, 4):
            self.put(frame(i))
        a = self.inbox.read_run("run1", limit=2)
        b = self.inbox.read_run("run1", after_offset=a[-1].offset)
        self.assertEqual([x.event.seq for x in a + b], [1, 2, 3])

    def test_invalid_page_denied(self):
        for wrong in (-1, True, 0, 999999):
            with self.subTest(limit=wrong), self.assertRaises(InboxError):
                self.inbox.read_run("run1", limit=wrong)

    def test_local_wal_mode(self):
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "wal")

    def test_concurrent_80_distinct_events(self):
        records = [(i, frame(i, emitter=f"worker.{1 + i % 2}"), f"worker.{1 + i % 2}")
                   for i in range(1, 81)]
        def do(r):
            i, data, emitter = r
            return self.put(data, emitter=emitter)
        with ThreadPoolExecutor(max_workers=12) as ex:
            receipts = list(ex.map(do, records))
        self.assertEqual(len({x.offset for x in receipts}), 80)
        self.assertEqual(len(self.inbox.read_run("run1", limit=100)), 80)

    def test_concurrent_same_event_is_idempotent(self):
        p = frame()
        with ThreadPoolExecutor(max_workers=10) as ex:
            receipts = list(ex.map(lambda _: self.put(p), range(30)))
        self.assertEqual({x.offset for x in receipts}, {receipts[0].offset})
        self.assertEqual(sum(not x.duplicate for x in receipts), 1)

    def test_invalid_configuration_rejected(self):
        for keymap in ({}, {"worker.1": b"short"}):
            with self.subTest(value=len(keymap)), self.assertRaises(InboxError):
                EventInbox(Path(self.dir.name) / "new.db", keymap)

    def test_clock_must_be_utc(self):
        other = EventInbox(self.path, {"worker.1": KEY},
                           clock=lambda: datetime(2026, 11, 22, 13, 0))
        with self.assertRaisesRegex(InboxError, "clock"):
            other.ingest(frame(), identity="worker.1", signature_hex=signature(frame()))
        self.assertEqual(self.inbox.read_run("run1"), [])


if __name__ == "__main__":
    unittest.main()
