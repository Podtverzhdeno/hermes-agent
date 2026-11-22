"""Process-level smoke tests for the opt-in observer command."""
import json
import os
import subprocess
import sys
from pathlib import Path

from autopilot import AutopilotLedger


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "autopilot_watch.py"


def test_observer_once_read_only_success(tmp_path):
    db = tmp_path / "ledger.sqlite3"
    ledger = AutopilotLedger(db)
    ledger.submit(request_key="x", project="project", goal="private goal",
                  revision="sha", required_evidence=["ci"])
    log = tmp_path / "private.jsonl"
    proc = subprocess.run([sys.executable, str(SCRIPT), "--db", str(db),
                           "--log", str(log), "--once"],
                          text=True, capture_output=True, timeout=15)
    assert proc.returncode == 0, proc.stderr
    records = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(records) == 1
    assert records[0]["kind"] == "observer.snapshot"
    assert records[0]["total_tasks"] == 1
    assert "private goal" not in log.read_text()
    if os.name == "posix":
        assert log.stat().st_mode & 0o077 == 0


def test_observer_once_missing_db_is_an_error_not_empty_success(tmp_path):
    proc = subprocess.run([sys.executable, str(SCRIPT),
                           "--db", str(tmp_path / "absent.sqlite3"), "--once"],
                          text=True, capture_output=True, timeout=15)
    assert proc.returncode == 2
    output = json.loads(proc.stdout.strip())
    assert output["kind"] == "observer.error"
    assert output["reason_code"] == "LEDGER_UNAVAILABLE"


def test_observer_rejects_log_file_symlink(tmp_path):
    if not hasattr(os, "symlink"):
        return
    db = tmp_path / "ledger.sqlite3"
    AutopilotLedger(db)
    target = tmp_path / "actual.jsonl"
    link = tmp_path / "linked.jsonl"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        return
    proc = subprocess.run([sys.executable, str(SCRIPT), "--db", str(db),
                           "--log", str(link), "--once"],
                          text=True, capture_output=True, timeout=15)
    assert proc.returncode != 0
    assert not target.exists()
