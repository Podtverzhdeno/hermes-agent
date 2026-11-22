"""Contract tests for the durable Hermes Autopilot control plane.

All tests run offline without LLM credentials, external providers or network.
"""

from concurrent.futures import ThreadPoolExecutor

import pytest

from autopilot import ApprovalRequired, AutopilotLedger, LedgerConflict


class Clock:
    def __init__(self):
        self.value = 1_800_000_000.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


@pytest.fixture
def ctx(tmp_path):
    clock = Clock()
    ledger = AutopilotLedger(tmp_path / "autopilot.sqlite3", clock)
    return ledger, clock


def submit(ledger, key="work-1", max_attempts=3):
    return ledger.submit(
        request_key=key, project="My_shelter",
        goal="Prepare an isolated PR and verify it",
        revision="git:abc123", required_evidence=["tests", "ci"],
        max_attempts=max_attempts,
    )


def lease(ledger, worker="A1"):
    entry = ledger.claim(worker=worker, lease_seconds=15)
    assert entry
    return entry["id"], entry["fence"]


def test_idempotent_submission_conflict_is_detected(ctx):
    ledger, _ = ctx
    task = submit(ledger)
    assert task == submit(ledger)
    with pytest.raises(LedgerConflict):
        ledger.submit(
            request_key="work-1", project="Other", goal="Different",
            revision="git:abc123", required_evidence=["ci"],
        )


def test_claim_is_atomic_even_across_independent_connections(ctx):
    ledger, _ = ctx
    submit(ledger)
    submit(ledger, key="work-2")
    path = ledger.path

    def do_claim(worker):
        own = AutopilotLedger(path, ledger.clock)
        return own.claim(worker=worker, lease_seconds=15)

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(do_claim, ["A" + str(i) for i in range(8)]))
    claimed = [x for x in outcomes if x]
    assert len(claimed) == 2
    assert len({x["id"] for x in claimed}) == 2
    assert all(x["fence"] == 1 for x in claimed)


def test_stale_worker_is_fenced_after_expiry(ctx):
    ledger, clock = ctx
    submit(ledger)
    task_id, old_token = lease(ledger)
    clock.advance(16)
    assert ledger.claim("A2") is None  # retry backoff applies
    with pytest.raises(LedgerConflict):
        ledger.heartbeat(task_id, "A1", old_token)
    clock.advance(2)
    claimed = ledger.claim("A2", lease_seconds=15)
    assert claimed["id"] == task_id
    assert claimed["fence"] > old_token
    with pytest.raises(LedgerConflict):
        ledger.begin_verification(task_id, "A1", old_token)


def test_attempts_are_bounded_and_eventually_fail(ctx):
    ledger, clock = ctx
    task = submit(ledger, max_attempts=2)
    lease(ledger)
    clock.advance(16)
    ledger.claim("recover")  # triggers expiration but next retry is delayed
    clock.advance(2)
    assert ledger.claim("recover")["id"] == task
    clock.advance(16)
    assert ledger.claim("recover") is None
    assert ledger.get(task)["status"] == "failed"
    assert ledger.get(task)["attempts"] == 2


def test_fail_closed_without_approval_and_no_double_effect(ctx):
    ledger, clock = ctx
    task = submit(ledger)
    task_id, token = lease(ledger)
    with pytest.raises(ApprovalRequired):
        ledger.reserve_effect(task_id, "A1", token, "publish-1", "sha256:payload")
    ledger.request_approval(task_id, "A1", token, "publish-1", "sha256:payload",
                            clock() + 100)
    assert ledger.get(task)["status"] == "waiting_approval"
    assert ledger.claim("A2") is None
    ledger.decide_approval(task, "publish-1", "sha256:payload", "owner", True)
    resumed = ledger.claim("A2", lease_seconds=15)
    assert resumed and resumed["id"] == task
    ledger.reserve_effect(task, "A2", resumed["fence"], "publish-1", "sha256:payload")
    with pytest.raises(LedgerConflict):
        ledger.reserve_effect(task, "A2", resumed["fence"], "publish-1", "sha256:payload")
    ledger.acknowledge_effect(task, "A2", resumed["fence"], "publish-1",
                              "sha256:payload", "pr:#145")
    ledger.begin_verification(task, "A2", resumed["fence"])
    assert ledger.get(task)["status"] == "verifying"


def test_unknown_effect_must_be_reconciled_before_retry(ctx):
    ledger, clock = ctx
    task = submit(ledger)
    _, token = lease(ledger)
    ledger.request_approval(task, "A1", token, "deploy", "sha256:send", clock() + 100)
    ledger.decide_approval(task, "deploy", "sha256:send", "owner", True)
    new = ledger.claim("A2", lease_seconds=15)
    ledger.reserve_effect(task, "A2", new["fence"], "deploy", "sha256:send")
    clock.advance(16)
    assert ledger.claim("A3") is None
    assert ledger.get(task)["status"] == "needs_reconciliation"
    with pytest.raises(LedgerConflict):
        ledger.reconcile_effect(task, "deploy", "unknown", "none")
    ledger.reconcile_effect(task, "deploy", "acknowledged", "audit:external-789")
    assert ledger.get(task)["status"] == "retry_wait"
    with pytest.raises(LedgerConflict):
        ledger.reconcile_effect(task, "deploy", "acknowledged", "audit:repeat")


def test_approval_digest_and_expiry_are_bound(ctx):
    ledger, clock = ctx
    task = submit(ledger)
    _, token = lease(ledger)
    ledger.request_approval(task, "A1", token, "commit", "digest:A", clock() + 6)
    with pytest.raises(LedgerConflict):
        ledger.decide_approval(task, "commit", "digest:B", "owner", True)
    clock.advance(7)
    ledger.decide_approval(task, "commit", "digest:A", "owner", True)
    assert ledger.get(task)["status"] == "blocked"


def test_deny_is_terminal_and_cannot_be_claimed(ctx):
    ledger, clock = ctx
    task = submit(ledger)
    _, token = lease(ledger)
    ledger.request_approval(task, "A1", token, "delete", "digest:del", clock() + 50)
    ledger.decide_approval(task, "delete", "digest:del", "owner", False)
    assert ledger.get(task)["status"] == "blocked"
    assert ledger.claim("A3") is None


def test_verified_evidence_must_be_trusted_and_same_revision(ctx):
    ledger, _ = ctx
    task = submit(ledger)
    _, token = lease(ledger)
    ledger.begin_verification(task, "A1", token)
    ledger.record_evidence(task, "tests", "pytest", "git:abc123",
                           "passed", "artifact:/tests", trusted=False)
    ledger.record_evidence(task, "ci", "github", "git:wrong",
                           "passed", "run:33", trusted=True)
    assert ledger.finalize(task, "A1", token) is False
    ledger.record_evidence(task, "tests", "pytest", "git:abc123",
                           "passed", "artifact:/tests", trusted=True)
    ledger.record_evidence(task, "ci", "github", "git:abc123",
                           "passed", "run:34", trusted=True)
    assert ledger.finalize(task, "A1", token)
    assert ledger.get(task)["status"] == "succeeded"
    assert any(e["kind"] == "succeeded" for e in ledger.history(task))
    with pytest.raises(LedgerConflict):
        ledger.finalize(task, "A1", token)


def test_failed_evidence_prevents_completion(ctx):
    ledger, _ = ctx
    task = submit(ledger)
    _, token = lease(ledger)
    ledger.begin_verification(task, "A1", token)
    ledger.record_evidence(task, "tests", "pytest", "git:abc123",
                           "failed", "log:failing", trusted=True)
    ledger.record_evidence(task, "ci", "github", "git:abc123",
                           "passed", "run:35", trusted=True)
    assert not ledger.finalize(task, "A1", token)


def test_cancel_active_task_is_cooperative(ctx):
    ledger, clock = ctx
    task = submit(ledger)
    _, token = lease(ledger)
    ledger.cancel(task)
    assert ledger.get(task)["cancel_requested"]
    with pytest.raises(LedgerConflict):
        ledger.heartbeat(task, "A1", token)
    clock.advance(16)
    assert ledger.claim("other") is None
    assert ledger.get(task)["status"] == "cancelled"


def test_cancel_queued_task_is_immediate(ctx):
    ledger, _ = ctx
    task = submit(ledger)
    ledger.cancel(task)
    assert ledger.get(task)["status"] == "cancelled"
    assert ledger.claim("A1") is None


def test_nonretryable_fail_does_not_rerun(ctx):
    ledger, _ = ctx
    task = submit(ledger)
    _, token = lease(ledger)
    ledger.fail(task, "A1", token, reason="schema invalid", retryable=False)
    assert ledger.get(task)["status"] == "failed"
    assert ledger.claim("A2") is None


def test_heartbeat_extends_lease(ctx):
    ledger, clock = ctx
    task = submit(ledger)
    _, token = lease(ledger)
    clock.advance(10)
    ledger.heartbeat(task, "A1", token, lease_seconds=20)
    clock.advance(8)
    assert ledger.claim("A2") is None
    assert ledger.get(task)["status"] == "running"
