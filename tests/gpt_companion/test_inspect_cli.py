"""CLI invocation contract and fail-closed input handling."""

import json
from scripts.gpt_event_inspect import main


def test_import_and_inspect(tmp_path, capsys):
    src = tmp_path / "events.jsonl"
    event = {"schema_version": 1, "event_id": "evt-1", "source": "connector",
             "run_id": "run-1", "attempt": 1, "sequence": 1,
             "kind": "run.reported_completed"}
    src.write_text(json.dumps(event) + "\n", encoding="utf-8")
    db = tmp_path / "events.db"
    assert main(["--db", str(db), "--run-id", "run-1", "--jsonl", str(src)]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["state"] == "AWAITING_VERIFICATION"
    assert first["ingested"] == 1
    assert main(["--db", str(db), "--run-id", "run-1", "--jsonl", str(src)]) == 0
    assert json.loads(capsys.readouterr().out)["replayed"] == 1


def test_refuses_raw_prompts_and_does_not_echo_them(tmp_path, capsys):
    secret = "PASSWORD_NEVER_LOG_ME"
    src = tmp_path / "bad.jsonl"
    src.write_text(json.dumps({"schema_version": 1, "event_id": "evt-1", "source": "connector",
                               "run_id": "run-1", "attempt": 1, "sequence": 1,
                               "kind": "worker.started", "prompt": secret}) + "\n")
    assert main(["--db", str(tmp_path / "events.db"), "--run-id", "run-1",
                 "--jsonl", str(src)]) == 2
    capture = capsys.readouterr()
    assert secret not in capture.out + capture.err
    assert "INSPECTION_REJECTED" in capture.err


def test_incomplete_or_invalid_jsonl_not_accepted(tmp_path, capsys):
    src = tmp_path / "bad.jsonl"
    src.write_text("not json\n", encoding="utf-8")
    assert main(["--db", str(tmp_path / "events.db"), "--run-id", "run-1",
                 "--jsonl", str(src)]) == 2
    assert "INSPECTION_REJECTED" in capsys.readouterr().err


def test_installed_module_entrypoint(tmp_path):
    import os
    import subprocess
    import sys
    source = tmp_path / "events.jsonl"
    source.write_text(json.dumps({"schema_version": 1, "event_id": "evt-installed",
                                  "source": "connector", "run_id": "run-new", "attempt": 1,
                                  "sequence": 1, "kind": "worker.started"}) + "\n")
    proc = subprocess.run([sys.executable, "-m", "gpt_companion", "--db",
                           str(tmp_path / "events.db"), "--run-id", "run-new",
                           "--jsonl", str(source)], capture_output=True, text=True,
                          timeout=10, cwd=os.fspath(__import__("pathlib").Path(__file__).resolve().parents[2]))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["state"] == "RECENT_TELEMETRY"


def test_corrupt_sqlite_is_reported_not_raw_traceback(tmp_path, capsys):
    db = tmp_path / "events.db"
    db.write_bytes(b"bad db header is not sqlite")
    assert main(["--db", str(db), "--run-id", "run-1"]) == 3
    err = capsys.readouterr().err
    assert "JOURNAL_INTEGRITY_FAILED" in err
    assert "Traceback" not in err
