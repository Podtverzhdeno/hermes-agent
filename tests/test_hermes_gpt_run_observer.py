"""Offline read-only GPT/Hermes run observer contract tests."""
from pathlib import Path
import json
import os

import pytest

from scripts.hermes_gpt_run_observer import (
    JsonlRunLog, RunObserver, UnsupportedContract, extract_features,
    make_event, monitor, safe_projection, validate_origin, validate_run_id,
)


@pytest.mark.parametrize("candidate", [
    "http://gateway.local:8642", "http://192.168.1.10:8642",
    "http://example.com", "https://user:password@example.com",
    "http://127.0.0.1:8642/secret", "file:///etc/passwd",
    "http://127.0.0.1:8642?token=secret",
])
def test_remote_plaintext_and_credential_urls_blocked(candidate):
    with pytest.raises(ValueError):
        validate_origin(candidate)


def test_loopback_and_opt_in_remote_https():
    assert validate_origin("http://127.0.0.1:8642") == "http://127.0.0.1:8642"
    assert validate_origin("http://localhost:8642/") == "http://localhost:8642"
    with pytest.raises(ValueError):
        validate_origin("https://gateway.example.com")
    assert validate_origin("https://gateway.example.com", True) == "https://gateway.example.com"


def test_run_id_rejects_path_injection():
    assert validate_run_id("run_ABC-123") == "run_ABC-123"
    for bad in ["", "../secrets", "id?q=1", "réponse", "a" * 129]:
        with pytest.raises(ValueError):
            validate_run_id(bad)


def test_projection_keeps_metadata_only():
    raw = {
        "run_id": "r1", "status": "running", "last_event": "tool.started",
        "error": "provider_secret=HIDDEN", "output": "PASSWORD",
        "session_id": "private", "prompt": "PRIVATE", "pending_controls": [{}],
    }
    data = safe_projection(raw)
    assert data == {
        "status": "running", "last_event": "tool.started",
        "has_error": True, "has_pending_controls": True,
    }
    assert "PASSWORD" not in json.dumps(data)
    assert "HIDDEN" not in json.dumps(data)


def test_projection_rejects_unsafe_event_and_unrecognized_status():
    data = safe_projection({"status": "other", "last_event": "Bearer secret"})
    assert data["status"] == "unrecognized"
    assert data["last_event"] is None


def test_capability_gate_requires_advertised_status_and_reports_durability():
    assert extract_features({"features": {"run_status": True, "runs_idempotency": {
        "supported": True, "durable": True,
    }}}) == (True, True)
    assert extract_features({"features": {"run_status": True, "runs_idempotency": {
        "supported": True, "durable": False,
    }}}) == (True, False)
    assert extract_features({"features": {"run_status": False}}) == (False, False)


def test_log_files_are_unique_and_content_is_valid_jsonl(tmp_path):
    with JsonlRunLog(tmp_path, "run1") as a:
        p1 = a.path
        a.append(make_event("state_observed", "run1", status="queued"))
    with JsonlRunLog(tmp_path, "run1") as b:
        p2 = b.path
        b.append(make_event("state_observed", "run1", status="running"))
    assert p1 != p2
    assert json.loads(p1.read_text(encoding="utf-8"))["status"] == "queued"
    assert json.loads(p2.read_text(encoding="utf-8"))["status"] == "running"
    if os.name == "posix":
        assert (p1.stat().st_mode & 0o777) == 0o600


def test_observer_distinguishes_stall_from_terminal_and_waiting():
    events = []
    observer = RunObserver("r1", events.append, stale_seconds=10)
    assert not observer.observe({"status": "running", "last_event": "tool.started"}, now=1)
    assert not observer.observe({"status": "running", "last_event": "tool.started"}, now=12)
    assert events[-1]["kind"] == "progress_stale_suspected"
    assert events[-1]["reason_code"] == "NO_OBSERVED_PROGRESS"
    assert not observer.observe({"status": "running", "last_event": "tool.started"}, now=100)
    assert len([e for e in events if e["kind"] == "progress_stale_suspected"]) == 1
    assert not observer.observe({"status": "waiting_for_approval"}, now=101)
    assert not observer.observe({"status": "waiting_for_approval"}, now=999)
    assert observer.observe({"status": "completed"}, now=1000)
    assert len([e for e in events if e["kind"] == "progress_stale_suspected"]) == 1


def test_monitor_records_redacted_state_and_exits_on_terminal(tmp_path):
    seen = []
    replies = iter([
        {"status": "queued", "prompt": "secret_input"},
        {"status": "running", "last_event": "tool.started", "output": "leaked_output"},
        {"status": "completed", "output": "secret_result", "error": ""},
    ])

    def fetch(_base, path, token):
        seen.append((path, token))
        if path == "/v1/capabilities":
            return {"features": {"run_status": True, "runs_idempotency": {"durable": True}}}
        return next(replies)

    code, path = monitor(
        "http://127.0.0.1:8642", "r1", api_key="token-private",
        poll_seconds=.2, stale_seconds=10, max_seconds=10,
        log_dir=tmp_path, fetch=fetch, sleep=lambda _: None,
    )
    assert code == 0
    assert path.is_file()
    contents = path.read_text(encoding="utf-8")
    for secret in ("token-private", "secret_input", "leaked_output", "secret_result"):
        assert secret not in contents
    events = [json.loads(line) for line in contents.splitlines()]
    assert events[-1]["kind"] == "terminal_observed"
    assert [e["status"] for e in events if e["kind"] == "state_observed"] == [
        "queued", "running", "completed",
    ]
    assert [p for p, t in seen[1:]] == ["/v1/runs/r1"] * 3


def test_monitor_explicitly_rejects_old_api_contract(tmp_path):
    code, path = monitor(
        "http://127.0.0.1:8642", "r1", log_dir=tmp_path,
        fetch=lambda *_: {"features": {"chat_completions": True}},
    )
    assert code == 2
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert events[-1]["kind"] == "unsupported_capabilities"


def test_monitor_warns_on_in_memory_idempotency_without_faking_failure(tmp_path):
    def fetch(_base, path, _token):
        if path == "/v1/capabilities":
            return {"features": {
                "run_status": True, "runs_idempotency": {"durable": False},
            }}
        return {"status": "failed", "error": "secret"}

    code, path = monitor("http://127.0.0.1:8642", "r1", log_dir=tmp_path,
                         fetch=fetch, sleep=lambda _: None)
    assert code == 0
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert "durability_warning" in {x["kind"] for x in events}
    assert all("secret" not in json.dumps(x) for x in events)


def test_long_event_is_refused(tmp_path):
    with JsonlRunLog(tmp_path, "run1") as log:
        with pytest.raises(ValueError):
            log.append(make_event("test", "run1", huge="x" * 4500))


def test_stale_warning_is_not_an_operation_failure():
    events = []
    observer = RunObserver("r1", events.append, stale_seconds=1)
    observer.observe({"status": "running"}, now=0)
    observer.observe({"status": "running"}, now=2)
    assert events[-1]["kind"] == "progress_stale_suspected"
    assert all(x["kind"] != "terminal_observed" for x in events)
