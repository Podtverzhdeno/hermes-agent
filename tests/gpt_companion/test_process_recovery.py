"""Cross-process SQLite durability tests without network, browsers or model calls."""

import json
import subprocess
import sys
from pathlib import Path

from gpt_companion import EventJournal


ROOT = Path(__file__).resolve().parents[2]


def _event(name, source):
    return {"schema_version": 1, "event_id": name, "source": source,
            "run_id": "run-child", "attempt": 1, "sequence": 1, "kind": "worker.started"}


def test_uncommitted_sqlite_change_rolls_back_after_abrupt_process_exit(tmp_path):
    path = tmp_path / "events.db"
    journal = EventJournal(path)
    journal.ingest(_event("evt-main", "worker-main"))
    child_code = """import sqlite3,os,sys
conn=sqlite3.connect(sys.argv[1], isolation_level=None)
conn.execute('BEGIN IMMEDIATE')
conn.execute(\"UPDATE events SET kind='run.reported_completed' WHERE position=1\")
os._exit(73)
"""
    child = subprocess.run([sys.executable, "-c", child_code, str(path)],
                           capture_output=True, timeout=10, cwd=ROOT)
    assert child.returncode == 73
    reopened = EventJournal(path)
    assert reopened.verify_chain()
    assert reopened.assess("run-child")["state"] == "RECENT_TELEMETRY"


def test_independent_processes_can_ingest_distinct_sources(tmp_path):
    path = tmp_path / "events.db"
    journal = EventJournal(path)
    child_code = """import json,sys
from gpt_companion import EventJournal
EventJournal(sys.argv[1]).ingest(json.loads(sys.argv[2]))
"""
    children = [subprocess.Popen([sys.executable, "-c", child_code, str(path),
                                  json.dumps(_event(f"evt-{i}", f"worker-{i}"))],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=ROOT)
                for i in range(8)]
    try:
        for p in children:
            stdout, stderr = p.communicate(timeout=15)
            assert p.returncode == 0, (stdout.decode(), stderr.decode())
    finally:
        for p in children:
            if p.poll() is None:
                p.kill()
                p.wait()
    assert journal.verify_chain()
    result = journal.assess("run-child")
    assert result["worker_sources_count"] == 8
    assert result["missing_sequences"] == 0
