"""Offline regression tests for the read-only Autopilot monitor."""
import json

import pytest

from autopilot import AutopilotLedger
from autopilot.diagnostics import LedgerObserver


class FakeClock:
    def __init__(self):
        self.now = 1_800_000_000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def monitor(tmp_path):
    clock = FakeClock()
    path = tmp_path / "control.sqlite3"
    ledger = AutopilotLedger(path, clock)
    observer = LedgerObserver(path, clock)
    return ledger, observer, clock


def add(ledger, key="job"):
    return ledger.submit(
        request_key=key, project="project-test",
        goal="PRIVATE_GOAL_DO_NOT_EXPOSE",
        revision="git:abcdef", required_evidence=["ci", "tests"],
    )


def test_snapshot_is_read_only_and_excludes_sensitive_payload(monitor):
    ledger, observer, _ = monitor
    task = add(ledger)
    snap = observer.snapshot()
    assert snap["total_tasks"] == 1
    assert snap["status_counts"] == {"queued": 1}
    assert snap["tasks"][0]["reason_code"] == "READY_TO_DISPATCH"
    assert snap["tasks"][0]["task_id"] == task
    serialized = json.dumps(snap)
    assert "PRIVATE_GOAL_DO_NOT_EXPOSE" not in serialized
    assert "approval_digest" not in serialized
    assert snap["monitor_semantics"] == "ledger_snapshot_only_not_live_worker_heartbeat"


def test_stale_lease_is_visible_before_scheduler_reaps_it(monitor):
    ledger, observer, clock = monitor
    add(ledger)
    claimed = ledger.claim("worker", lease_seconds=15)
    assert claimed
    assert observer.snapshot()["tasks"][0]["reason_code"] == "WORKER_LEASE_ACTIVE"
    clock.advance(16)
    snap = observer.snapshot()
    assert snap["tasks"][0]["reason_code"] == "WORKER_LEASE_EXPIRED_NOT_REAPED"
    assert ledger.get(claimed["id"])["status"] == "running"


def test_expired_approval_is_visible_without_mutating_state(monitor):
    ledger, observer, clock = monitor
    task = add(ledger)
    claimed = ledger.claim("worker")
    ledger.request_approval(task, "worker", claimed["fence"],
                            "action1", "digest:private", clock() + 5)
    assert observer.snapshot()["tasks"][0]["reason_code"] == "WAITING_OWNER_APPROVAL"
    clock.advance(6)
    assert observer.snapshot()["tasks"][0]["reason_code"] == "APPROVAL_EXPIRED_NOT_REAPED"
    assert ledger.get(task)["status"] == "waiting_approval"
    assert "digest:private" not in json.dumps(observer.snapshot())


def test_uncertain_external_effect_surfaces_as_blocker(monitor):
    ledger, observer, clock = monitor
    task = add(ledger)
    claimed = ledger.claim("worker")
    ledger.request_approval(task, "worker", claimed["fence"],
                            "action1", "digest", clock() + 100)
    ledger.decide_approval(task, "action1", "digest", "owner", True)
    again = ledger.claim("worker2", lease_seconds=15)
    ledger.reserve_effect(task, "worker2", again["fence"], "action1", "digest")
    clock.advance(16)
    ledger.claim("worker3")  # only reaps; no automatic rerun
    row = observer.snapshot()["tasks"][0]
    assert row["reason_code"] == "EXTERNAL_EFFECT_UNCERTAIN"
    assert row["unresolved_effects"] == 1


def test_verifier_failures_are_explained(monitor):
    ledger, observer, _ = monitor
    task = add(ledger)
    claimed = ledger.claim("worker")
    ledger.begin_verification(task, "worker", claimed["fence"])
    row = observer.snapshot()["tasks"][0]
    assert row["reason_code"] == "WAITING_VERIFICATION_EVIDENCE"
    assert row["missing_evidence"] == ["ci", "tests"]
    ledger.record_evidence(task, "ci", "github", "git:abcdef",
                           "failed", "run:bad", trusted=True)
    row = observer.snapshot()["tasks"][0]
    assert row["reason_code"] == "TRUSTED_VERIFICATION_FAILURE"
    assert row["failed_evidence"] == ["ci"]


def test_event_headers_have_stable_cursor_and_no_raw_details(monitor):
    ledger, observer, _ = monitor
    add(ledger)
    cursor = observer.snapshot()["event_cursor"]
    assert cursor >= 1
    assert observer.event_headers(after_seq=cursor) == []
    rows = observer.event_headers(after_seq=0, limit=1)
    assert len(rows) == 1
    assert set(rows[0]) == {"seq", "task_id", "kind", "created_at"}


def test_reader_rejects_bad_limits_and_missing_file(tmp_path, monitor):
    _, observer, _ = monitor
    for bad in (0, -1, 501, True, "3"):
        with pytest.raises(ValueError):
            observer.snapshot(limit=bad)
    missing = LedgerObserver(tmp_path / "missing.sqlite3")
    with pytest.raises(FileNotFoundError):
        missing.snapshot()
