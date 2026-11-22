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
    # The retry must use a 15-second lease too. claim() otherwise defaults
    # to 120 seconds and would correctly remain running after +16.
    assert ledger.claim("recover", lease_seconds=15)["id"] == task
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
    # Invalid enum is an input-validation error (ValueError), not an
    # inconsistent ledger transition (LedgerConflict). State stays unchanged.
    with pytest.raises(ValueError):
        ledger.reconcile_effect(task, "deploy", "unknown", "none")
    assert ledger.get(task)["status"] == "needs_reconciliation"
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


def test_expired_approval_is_closed_on_scheduler_tick(ctx):
    ledger, clock = ctx
    task = submit(ledger)
    _, token = lease(ledger)
    ledger.request_approval(task, "A1", token, "publish", "digest:1", clock() + 5)
    clock.advance(6)
    assert ledger.claim("A2") is None
    assert ledger.get(task)["status"] == "blocked"
    assert any(e["kind"] == "approval_expired" for e in ledger.history(task))


def test_proven_not_executed_can_be_rereserved_but_acknowledged_cannot(ctx):
    ledger, clock = ctx
    task = submit(ledger)
    _, token = lease(ledger)
    ledger.request_approval(task, "A1", token, "write", "digest:A", clock() + 100)
    ledger.decide_approval(task, "write", "digest:A", "owner", True)
    new = ledger.claim("A2", lease_seconds=15)
    ledger.reserve_effect(task, "A2", new["fence"], "write", "digest:A")
    clock.advance(16)
    assert ledger.claim("A3") is None
    ledger.reconcile_effect(task, "write", "not_executed", "readback:absent")
    retry = ledger.claim("A3")
    assert retry
    ledger.reserve_effect(task, "A3", retry["fence"], "write", "digest:A")
    ledger.acknowledge_effect(task, "A3", retry["fence"], "write", "digest:A", "receipt:8")
    with pytest.raises(LedgerConflict):
        ledger.reserve_effect(task, "A3", retry["fence"], "write", "digest:A")
    assert any(e["kind"] == "effect_rereserved" for e in ledger.history(task))


def test_nonretryable_failure_with_uncertain_effect_never_resumes(ctx):
    ledger, clock = ctx
    task = submit(ledger)
    _, token = lease(ledger)
    ledger.request_approval(task, "A1", token, "write", "digest:A", clock() + 100)
    ledger.decide_approval(task, "write", "digest:A", "owner", True)
    new = ledger.claim("A2")
    ledger.reserve_effect(task, "A2", new["fence"], "write", "digest:A")
    ledger.fail(task, "A2", new["fence"], "POLICY_DENIED", retryable=False)
    assert ledger.get(task)["status"] == "needs_reconciliation"
    ledger.reconcile_effect(task, "write", "acknowledged", "readback:present")
    assert ledger.get(task)["status"] == "failed"
    assert ledger.claim("A3") is None


def test_other_trusted_source_failure_vetoes_success(ctx):
    ledger, _ = ctx
    task = submit(ledger)
    _, token = lease(ledger)
    ledger.begin_verification(task, "A1", token)
    ledger.record_evidence(task, "tests", "pytest", "git:abc123",
                           "passed", "run:test1", trusted=True)
    ledger.record_evidence(task, "ci", "github-linux", "git:abc123",
                           "passed", "run:green", trusted=True)
    ledger.record_evidence(task, "ci", "github-windows", "git:abc123",
                           "failed", "run:red", trusted=True)
    assert ledger.finalize(task, "A1", token) is False
    assert ledger.get(task)["status"] == "verifying"


def test_untrusted_observation_cannot_downgrade_trusted_evidence(ctx):
    ledger, _ = ctx
    task = submit(ledger)
    _, token = lease(ledger)
    ledger.begin_verification(task, "A1", token)
    ledger.record_evidence(task, "ci", "github", "git:abc123",
                           "passed", "run:trusted", trusted=True)
    ledger.record_evidence(task, "ci", "github", "git:abc123",
                           "failed", "untrusted:fake", trusted=False)
    ledger.record_evidence(task, "tests", "pytest", "git:abc123",
                           "passed", "run:pytest", trusted=True)
    assert ledger.finalize(task, "A1", token)
    assert any(e["kind"] == "evidence_ignored_untrusted" for e in ledger.history(task))
    with pytest.raises(LedgerConflict):
        ledger.record_evidence(task, "ci", "github", "git:abc123",
                               "failed", "late:invalid", trusted=True)


def test_unstructured_failure_message_is_not_logged(ctx):
    ledger, _ = ctx
    task = submit(ledger)
    _, token = lease(ledger)
    secret = "SENSITIVE_CANARY_NO_LOG"
    ledger.fail(task, "A1", token, "unexpected: " + secret, retryable=False)
    events = ledger.history(task)
    import json
    serialized = json.dumps(events)
    assert secret not in serialized
    assert "UNCLASSIFIED_FAILURE" in serialized


def test_legacy_tasks_table_is_migrated_without_losing_records(tmp_path):
    import sqlite3
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute("""
            CREATE TABLE tasks (
                id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL,
                project TEXT NOT NULL, goal TEXT NOT NULL, revision TEXT NOT NULL,
                required_evidence TEXT NOT NULL, status TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL, available_at REAL NOT NULL,
                owner TEXT, fence INTEGER NOT NULL DEFAULT 0,
                lease_until REAL, cancel_requested INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL, updated_at REAL NOT NULL
            )
        """)
        conn.execute("""
            INSERT INTO tasks (id,request_key,project,goal,revision,required_evidence,
                status,max_attempts,available_at,created_at,updated_at)
            VALUES('old','old-key','proj','goal','sha','["ci"]','queued',3,0,0,0)
        """)
    ledger = AutopilotLedger(path)
    assert ledger.get("old")["retry_allowed"] == 1
    assert ledger.submit(request_key="old-key", project="proj", goal="goal",
                         revision="sha", required_evidence=["ci"]) == "old"


def test_multiple_approvals_do_not_consume_retry_budget(ctx):
    ledger, clock = ctx
    task = submit(ledger, max_attempts=1)
    first = ledger.claim("A1", lease_seconds=15)
    assert first["attempts"] == 1
    for i in range(3):
        action_key = "safe-action-" + str(i)
        digest = "digest:" + str(i)
        ledger.request_approval(task, "A1", first["fence"], action_key,
                                digest, clock() + 100)
        ledger.decide_approval(task, action_key, digest, "owner", True)
        first = ledger.claim("A1", lease_seconds=15)
        assert first["attempts"] == 1
        assert first["fence"] == i + 2
        ledger.reserve_effect(task, "A1", first["fence"], action_key, digest)
        ledger.acknowledge_effect(task, "A1", first["fence"], action_key,
                                  digest, "receipt:" + str(i))
    ledger.begin_verification(task, "A1", first["fence"])
    ledger.record_evidence(task, "tests", "pytest", "git:abc123",
                           "passed", "pytest:1", trusted=True)
    ledger.record_evidence(task, "ci", "github", "git:abc123",
                           "passed", "ci:1", trusted=True)
    assert ledger.finalize(task, "A1", first["fence"])


def test_approval_pause_rejected_while_effect_outcome_unknown(ctx):
    ledger, clock = ctx
    task = submit(ledger)
    _, token = lease(ledger)
    ledger.request_approval(task, "A1", token, "mutate", "digest:first",
                            clock() + 60)
    ledger.decide_approval(task, "mutate", "digest:first", "owner", True)
    resumed = ledger.claim("A1", lease_seconds=15)
    ledger.reserve_effect(task, "A1", resumed["fence"], "mutate", "digest:first")
    with pytest.raises(LedgerConflict, match="unresolved external effect"):
        ledger.request_approval(task, "A1", resumed["fence"], "next", "digest:next",
                                clock() + 60)
    assert ledger.get(task)["status"] == "running"


def test_exact_expiry_boundary_invalidates_lease(ctx):
    ledger, clock = ctx
    task = submit(ledger)
    _, token = lease(ledger)
    clock.advance(15)
    with pytest.raises(LedgerConflict):
        ledger.heartbeat(task, "A1", token)
    assert ledger.claim("A2") is None
    assert ledger.get(task)["status"] == "retry_wait"


def test_distinct_connection_uses_full_synchronous_mode(ctx):
    ledger, _ = ctx
    with ledger._db() as db:
        assert db.execute("PRAGMA synchronous").fetchone()[0] == 2  # FULL


def test_operator_projections_are_durable_across_reopen(ctx):
    ledger, clock = ctx
    task = submit(ledger)
    _, token = lease(ledger)
    ledger.request_approval(task, "A1", token, "commit", "digest:1",
                            clock() + 10)
    reopened = AutopilotLedger(ledger.path, clock)
    listed = reopened.list_tasks(status="waiting_approval")
    assert len(listed) == 1 and listed[0]["id"] == task
    assert listed[0]["required_evidence"] == ["ci", "tests"]
    pending = reopened.approval_queue()
    assert len(pending) == 1
    assert pending[0]["action_key"] == "commit"
    assert pending[0]["digest"] == "digest:1"
    assert reopened.effects(task) == []
    with pytest.raises(ValueError):
        reopened.list_tasks(limit=1001)


def test_expired_approval_is_blocked_by_scheduler_sweep(ctx):
    ledger, clock = ctx
    task = submit(ledger)
    _, token = lease(ledger)
    ledger.request_approval(task, "A1", token, "commit", "digest:A",
                            clock() + 10)
    clock.advance(10)
    assert ledger.claim("A2") is None
    assert ledger.get(task)["status"] == "blocked"
    assert ledger.approval_queue() == []
    assert "approval_expired" in [x["kind"] for x in ledger.history(task)]
    with pytest.raises(LedgerConflict):
        ledger.decide_approval(task, "commit", "digest:A", "owner", True)


def test_effects_projection_preserves_unknown_state(ctx):
    ledger, clock = ctx
    task = submit(ledger)
    _, token = lease(ledger)
    ledger.request_approval(task, "A1", token, "send", "digest:send",
                            clock() + 100)
    ledger.decide_approval(task, "send", "digest:send", "owner", True)
    worker = ledger.claim("A2", lease_seconds=15)
    ledger.reserve_effect(task, "A2", worker["fence"], "send", "digest:send")
    clock.advance(15)
    assert ledger.claim("A3") is None
    assert ledger.get(task)["status"] == "needs_reconciliation"
    effects = ledger.effects(task)
    assert len(effects) == 1
    assert effects[0]["status"] == "reserved"
    assert effects[0]["digest"] == "digest:send"
    assert effects[0]["result_ref"] is None


def test_trusted_failure_cannot_be_overwritten_by_same_source_pass(ctx):
    ledger, _ = ctx
    task = submit(ledger)
    _, fence = lease(ledger)
    ledger.begin_verification(task, "A1", fence)
    ledger.record_evidence(task, "ci", "github-run-1", "git:abc123",
                           "failed", "run:1-failed", trusted=True)
    ledger.record_evidence(task, "tests", "pytest", "git:abc123",
                           "passed", "run:pytest", trusted=True)
    with pytest.raises(LedgerConflict):
        ledger.record_evidence(task, "ci", "github-run-1", "git:abc123",
                               "passed", "run:1-passed", trusted=True)
    # Even if an independent second run passes, the earlier trusted failure
    # must remain visible and veto release on the same revision.
    ledger.record_evidence(task, "ci", "github-run-2", "git:abc123",
                           "passed", "run:2-passed", trusted=True)
    assert ledger.finalize(task, "A1", fence) is False
    assert ledger.get(task)["status"] == "verifying"


def test_trusted_evidence_exact_replay_is_idempotent_and_run_identity_stable(ctx):
    ledger, _ = ctx
    task = submit(ledger)
    ledger.record_evidence(task, "ci", "github-run-1", "git:abc123",
                           "passed", "run:1", trusted=True)
    ledger.record_evidence(task, "ci", "github-run-1", "git:abc123",
                           "passed", "run:1", trusted=True)
    assert sum(e["kind"] == "evidence_replayed" for e in ledger.history(task)) == 1
    with pytest.raises(LedgerConflict):
        ledger.record_evidence(task, "ci", "github-run-1", "git:abc123",
                               "passed", "run:changed", trusted=True)
