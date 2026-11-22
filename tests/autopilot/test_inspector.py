"""Operator diagnostics are read-only and never assert remote success."""

import pytest

from autopilot.inspector import inspect_project
from autopilot.ledger import AutopilotLedger


class Clock:
    def __init__(self):
        self.t = 1900000000.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


@pytest.fixture()
def subject(tmp_path):
    c = Clock()
    return AutopilotLedger(tmp_path / "db.sqlite3", c), c


def create(l, key="one", project="Hermes", revision="sha:head"):
    return l.submit(
        request_key=key,
        project=project,
        goal="Verify local build",
        revision=revision,
        required_evidence=["tests", "ci"],
    )


def test_empty_project_is_idle_and_unverified(subject):
    ledger, clock = subject
    s = inspect_project(ledger, "Hermes", clock=clock)
    assert s["urgency"] == "idle"
    assert not s["remote_work_verified"]
    assert s["verification_scope"] == "local_ledger_only"
    assert s["tasks_total"] == 0
    assert s["revocation_generation"] == 0


def test_queued_and_running_are_not_presented_as_done(subject):
    ledger, clock = subject
    task = create(ledger)
    queued = inspect_project(ledger, "Hermes", clock=clock)
    assert queued["urgency"] == "queued"
    first = ledger.claim("A1", lease_seconds=15)
    assert first["id"] == task
    running = inspect_project(ledger, "Hermes", clock=clock)
    assert running["urgency"] == "active"
    assert running["next_step"] == "monitor_worker_lease"
    assert running["task_status_counts"] == {"running": 1}
    assert not running["tasks"][0]["stale_worker"]
    clock.advance(15)
    stale = inspect_project(ledger, "Hermes", clock=clock)
    assert stale["next_step"] == "reclaim_stale_workers"
    assert stale["expired_worker_leases"] == 1


def test_missing_evidence_is_revision_scoped(subject):
    ledger, clock = subject
    task = create(ledger)
    w = ledger.claim("A1")
    ledger.begin_verification(task, "A1", w["fence"])
    ledger.record_evidence(task, "tests", "pytest", "sha:old",
                           "passed", "report:old", trusted=True)
    ledger.record_evidence(task, "ci", "github", "sha:head",
                           "passed", "run:1", trusted=True)
    s = inspect_project(ledger, "Hermes", clock=clock)
    assert s["urgency"] == "active"
    assert s["next_step"] == "await_independent_evidence"
    assert s["tasks"][0]["missing_evidence"] == ["tests"]


def test_owner_approval_is_operator_actionable(subject):
    ledger, clock = subject
    task = create(ledger)
    w = ledger.claim("A1")
    ledger.request_approval(task, "A1", w["fence"],
                            "post", "sha256:opaque", clock() + 7)
    s = inspect_project(ledger, "Hermes", clock=clock)
    assert s["urgency"] == "attention"
    assert s["next_step"] == "owner_approval_required"
    assert s["waiting_owner_approvals"] == 1
    assert "sha256:opaque" not in str(s)
    clock.advance(8)
    expired = inspect_project(ledger, "Hermes", clock=clock)
    assert expired["next_step"] == "expire_or_review_approvals"
    assert expired["expired_owner_approvals"] == 1


def test_unknown_effect_outweighs_stopped_project(subject):
    ledger, clock = subject
    task = create(ledger)
    w = ledger.claim("A1")
    ledger.request_approval(task, "A1", w["fence"],
                            "publish", "sha256:receipt", clock() + 90)
    ledger.decide_approval(task, "publish", "sha256:receipt", "owner", True)
    w = ledger.claim("A1")
    ledger.reserve_effect(task, "A1", w["fence"], "publish", "sha256:receipt")
    ledger.stop_project("Hermes")
    s = inspect_project(ledger, "Hermes", clock=clock)
    assert s["urgency"] == "critical"
    assert s["next_step"] == "reconcile_reserved_external_effects"
    assert s["project_stopped"]
    assert s["revocation_generation"] == 1
    assert s["unknown_external_effects"] == 1


def test_inspector_does_not_mutate_status_or_generate_events(subject):
    ledger, clock = subject
    task = create(ledger)
    before = ledger.history(task)
    for _ in range(3):
        inspect_project(ledger, "Hermes", clock=clock)
    assert ledger.history(task) == before
    assert ledger.get(task)["status"] == "queued"


def test_sibling_project_isolation_and_truncation(subject):
    ledger, clock = subject
    create(ledger, "one", "Hermes")
    create(ledger, "other", "My_shelter")
    create(ledger, "three", "Hermes")
    result = inspect_project(ledger, "Hermes", clock=clock, limit=1)
    assert result["tasks_total"] == 2
    assert result["tasks_shown"] == 1
    assert result["tasks_truncated"]
    assert all("goal" not in x and "revision" not in x for x in result["tasks"])
    assert all(x["revision_fingerprint"].startswith("sha256:") for x in result["tasks"])


@pytest.mark.parametrize("limit", [-1, 0, 201])
def test_invalid_limits_fail_closed(subject, limit):
    ledger, clock = subject
    with pytest.raises(ValueError):
        inspect_project(ledger, "Hermes", clock=clock, limit=limit)


def test_contradictory_evidence_is_attention_not_success(subject):
    ledger, clock = subject
    task = create(ledger)
    w = ledger.claim("A1")
    ledger.begin_verification(task, "A1", w["fence"])
    ledger.record_evidence(task, "tests", "pytest", "sha:head",
                           "passed", "report:good", trusted=True)
    ledger.record_evidence(task, "tests", "secondary", "sha:head",
                           "failed", "report:bad", trusted=True)
    ledger.record_evidence(task, "ci", "github", "sha:head",
                           "passed", "run:1", trusted=True)
    snapshot = inspect_project(ledger, "Hermes", clock=clock)
    assert snapshot["urgency"] == "attention"
    assert snapshot["next_step"] == "repair_failed_required_evidence"
    assert snapshot["failed_required_evidence_cards_shown"] == 1
    assert snapshot["tasks"][0]["failed_required_evidence"] == ["tests"]
    assert not ledger.finalize(task, "A1", w["fence"])
