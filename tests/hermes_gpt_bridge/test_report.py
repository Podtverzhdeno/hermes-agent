"""Read-only operator reports with no network or background process required."""
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import hmac
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from hermes_gpt_bridge.inbox import EventInbox
from hermes_gpt_bridge.report import SnapshotError, load_snapshot, report
from scripts.gpt_bridge_inbox_report import main

KEY = b"fake-collector-test-key---32-bytes" * 2
NOW = datetime(2026, 11, 22, 14, 0, tzinfo=timezone.utc)


class OperatorReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "events.db"
        self.inbox = EventInbox(self.path, {"test.emitter": KEY}, clock=lambda: NOW)

    def tearDown(self):
        self.tmp.cleanup()

    def append(self, seq, kind, run="run1", **kw):
        p = json.dumps({"schema_version":1,"event_id":f"event{run}{seq}",
                        "run_id":run,"attempt_id":"attempt1","emitter_id":"test.emitter",
                        "seq":seq,"kind":kind,"observed_at":NOW.isoformat(),**kw}).encode()
        sig = hmac.new(KEY,p,hashlib.sha256).hexdigest()
        self.inbox.ingest(p,identity="test.emitter",signature_hex=sig)

    def test_empty_report_is_not_claim_of_provider_success(self):
        r = report(self.path,now=NOW)
        self.assertEqual(r["event_count"],0)
        self.assertFalse(r["provider_outcomes_trusted"])
        self.assertEqual(r["runs"],[])

    def test_unknown_effect_shows_in_report(self):
        self.append(1,"effect.reserved",operation_id="operation.1")
        r=report(self.path,now=NOW)
        self.assertEqual(r["event_count"],1)
        self.assertEqual(r["last_ingestion_offset"],1)
        self.assertIn("UNKNOWN_EXTERNAL_OUTCOME", [x["code"] for x in r["findings"]])

    def test_readonly_snapshot_does_not_create_db(self):
        nowhere=Path(self.tmp.name)/"missing.db"
        with self.assertRaises(SnapshotError):
            load_snapshot(nowhere)
        self.assertFalse(nowhere.exists())

    def test_readonly_snapshot_does_not_change_event_count(self):
        self.append(1,"run.created")
        self.assertEqual(len(load_snapshot(self.path).events),1)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM ingress_event").fetchone()[0],1)

    def test_multi_run_report_isolation(self):
        self.append(1,"run.started",run="a")
        self.append(1,"run.failed",run="b")
        r=report(self.path,now=NOW)
        self.assertEqual({x["run_id"] for x in r["runs"]},{"a","b"})

    def test_row_limit_and_invalid_arg(self):
        self.append(1,"run.created")
        self.append(2,"run.started")
        with self.assertRaises(SnapshotError):
            load_snapshot(self.path,limit=1)
        with self.assertRaises(SnapshotError):
            load_snapshot(self.path,limit=True)

    def test_corrupt_row_never_deserialized_as_success(self):
        self.append(1,"run.created")
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE ingress_event SET payload='not JSON'")
        with self.assertRaises(SnapshotError):
            load_snapshot(self.path)

    def test_cli_critical_status_exit_1(self):
        self.append(1,"effect.reserved",operation_id="op")
        output=io.StringIO()
        with redirect_stdout(output):
            code=main([str(self.path)])
        self.assertEqual(code,1)
        parsed=json.loads(output.getvalue())
        self.assertFalse(parsed["ok"])

    def test_cli_bad_path_exit_2_without_leaking_path(self):
        output=io.StringIO()
        path=str(Path(self.tmp.name)/"secret-name.db")
        with redirect_stderr(output):
            code=main([path])
        self.assertEqual(code,2)
        self.assertNotIn("secret-name",output.getvalue())


if __name__=="__main__":
    unittest.main()
