"""Offline deterministic failure-mode checks for the read-only GPT observation inbox."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from gpt_companion import EventJournal, JournalConflict, validate_event


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def jump(self, n):
        self.t += n


@pytest.fixture
def context(tmp_path):
    clock = FakeClock()
    return EventJournal(tmp_path / "events.db", clock), clock


def event(seq, kind, *, event_id=None, attempt=1, source="gpt-connector", **kwargs):
    return {"schema_version": 1, "event_id": event_id or f"event-{attempt}-{source}-{seq}",
            "source": source, "run_id": "run-1", "attempt": attempt,
            "sequence": seq, "kind": kind, **kwargs}


def test_new_and_identical_replay_survive_restart(context):
    db, clock = context
    msg = event(1, "run.accepted")
    assert db.ingest(msg) is True
    db2 = EventJournal(db.path, clock)
    assert db2.ingest(msg) is False
    assert db2.verify_chain() is True


def test_conflicting_event_id_fails_closed(context):
    db, _ = context
    db.ingest(event(1, "run.accepted"))
    with pytest.raises(JournalConflict, match="event_id reused"):
        db.ingest(event(1, "worker.started"))


def test_duplicate_sequence_different_event_id_rejected(context):
    db, _ = context
    db.ingest(event(1, "run.accepted"))
    with pytest.raises(JournalConflict, match="sequence reused"):
        db.ingest(event(1, "worker.started", event_id="other"))


def test_sequence_gap_is_not_silent(context):
    db, _ = context
    db.ingest(event(1, "worker.started"))
    db.ingest(event(3, "worker.progress"))
    result = db.assess("run-1")
    assert result["state"] == "TRACE_INCOMPLETE"
    assert result["missing_sequences"] == 1
    db.ingest(event(2, "worker.heartbeat"))
    assert db.assess("run-1")["state"] == "RECENT_TELEMETRY"


def test_reordered_effect_ack_cannot_prove_success(context):
    db, _ = context
    db.ingest(event(2, "tool.effect_acknowledged", action_id="post-pr"))
    db.ingest(event(1, "tool.effect_reserved", action_id="post-pr"))
    assert db.assess("run-1")["state"] == "RECENT_TELEMETRY"


def test_unknown_external_effect_must_be_reconciled(context):
    db, clock = context
    db.ingest(event(1, "tool.effect_reserved", action_id="post-pr"))
    assert db.assess("run-1")["state"] == "EFFECT_IN_FLIGHT"
    clock.jump(150)
    result = db.assess("run-1")
    assert result["state"] == "NEEDS_RECONCILIATION"
    assert result["next_action"] == "RECONCILE_EFFECT_RECEIPT"
    assert result["unresolved_effects"] == ["post-pr"]
    db.ingest(event(2, "tool.effect_acknowledged", action_id="post-pr"))
    assert db.assess("run-1")["state"] == "RECENT_TELEMETRY"


def test_approval_never_auto_granted(context):
    db, _ = context
    db.ingest(event(1, "approval.required", action_id="deploy"))
    assert db.assess("run-1")["state"] == "WAITING_APPROVAL"
    db.ingest(event(2, "approval.resolved", action_id="deploy"))
    assert db.assess("run-1")["state"] == "RECENT_TELEMETRY"


def test_model_says_done_not_independent_pass(context):
    db, _ = context
    db.ingest(event(1, "run.reported_completed"))
    assert db.assess("run-1")["state"] == "AWAITING_VERIFICATION"


def test_unobserved_run(context):
    db, _ = context
    assert db.assess("run-missing")["state"] == "NOT_OBSERVED"


def test_heartbeat_does_not_mean_progress(context):
    db, clock = context
    db.ingest(event(1, "worker.progress"))
    clock.jump(350)
    db.ingest(event(2, "worker.heartbeat"))
    assert db.assess("run-1")["state"] == "ALIVE_NO_PROGRESS"
    clock.jump(150)
    assert db.assess("run-1")["state"] == "WORKER_UNRESPONSIVE"


def test_prior_attempt_events_do_not_hide_latest_failure(context):
    db, _ = context
    db.ingest(event(1, "worker.started", attempt=1))
    db.ingest(event(1, "run.reported_failed", attempt=2, reason_code="AUTH_DENIED"))
    db.ingest(event(2, "worker.heartbeat", attempt=1))
    assert db.assess("run-1")["state"] == "REPORTED_FAILED"
    assert db.assess("run-1")["attempt"] == 2
    assert db.assess("run-1")["next_action"] == "CHECK_CREDENTIAL_SCOPE"


@pytest.mark.parametrize("change", [
    {"prompt": "secret"}, {"api_key": "sk-example"}, {"raw_output": "hi"},
    {"reason_code": "error detail; password"}, {"sequence": True},
    {"event_id": "a b"}, {"attempt": 0}, {"schema_version": 2},
    {"kind": "provider.anything"}, {"kind": ["worker.started"]},
])
def test_rejects_unapproved_content_or_invalid_contract(change):
    with pytest.raises(JournalConflict):
        validate_event({**event(1, "run.accepted"), **change})


def test_effect_requires_action_identity(context):
    db, _ = context
    with pytest.raises(JournalConflict, match="action_id"):
        db.ingest(event(1, "tool.effect_reserved"))


def test_tampering_detected_without_claiming_nonrepudiation(context):
    db, _ = context
    db.ingest(event(1, "worker.started"))
    assert db.verify_chain()
    with sqlite3.connect(db.path) as conn:
        conn.execute("UPDATE events SET kind='run.reported_completed' WHERE position=1")
    assert not db.verify_chain()


def test_concurrent_writers_serialized(context):
    db, _ = context
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert all(pool.map(db.ingest, [event(i, "worker.heartbeat") for i in range(1, 33)]))
    assert db.verify_chain()
    assert db.assess("run-1")["missing_sequences"] == 0


def test_invalid_deadlines_rejected(context):
    db, _ = context
    with pytest.raises(ValueError):
        db.assess("run-1", liveness_timeout=500, progress_timeout=100)


def test_cross_source_conflicting_terminals_need_trace_reconciliation(context):
    db, _ = context
    db.ingest(event(1, "run.reported_completed", source="worker"))
    db.ingest(event(1, "run.reported_failed", source="gateway", reason_code="CI_FAILED"))
    assert db.assess("run-1")["state"] == "TRACE_INCOMPLETE"


def test_rate_limit_is_diagnosis_not_permission_to_retry(context):
    db, _ = context
    db.ingest(event(1, "run.reported_failed", reason_code="RATE_LIMITED"))
    result = db.assess("run-1")
    assert result["next_action"] == "HONOR_RETRY_AFTER_AND_BUDGET"
    assert result["state"] == "REPORTED_FAILED"


def test_delayed_backfill_does_not_fake_worker_liveness(context):
    db, clock = context
    db.ingest(event(1, "worker.started"))
    clock.jump(2)
    db.ingest(event(3, "worker.heartbeat"))
    clock.jump(125)
    # Older event is delivered late; its receipt time is NOT a new heartbeat.
    db.ingest(event(2, "worker.progress"))
    result = db.assess("run-1")
    assert result["missing_sequences"] == 0
    assert result["state"] == "WORKER_UNRESPONSIVE"
    assert result["live_age_seconds"] == 125
    assert result["progress_age_seconds"] == 127


def test_heartbeat_only_worker_eventually_has_no_progress(context):
    db, clock = context
    db.ingest(event(1, "run.accepted"))
    for seq in range(2, 7):
        clock.jump(65)
        db.ingest(event(seq, "worker.heartbeat"))
    result = db.assess("run-1")
    assert result["state"] == "ALIVE_NO_PROGRESS"
    assert result["progress_age_seconds"] == 325
    assert result["live_age_seconds"] == 0


def test_invalid_observation_clock_fails_closed(context):
    db, _ = context
    db.ingest(event(1, "worker.started"))
    for invalid in (float("nan"), float("inf"), float("-inf"), -1):
        with pytest.raises(ValueError, match="observation clock"):
            db.assess("run-1", now=invalid)


def test_gateway_traffic_cannot_mask_known_dead_worker(context):
    db, clock = context
    db.ingest(event(1, "worker.started", source="worker-A"))
    db.ingest(event(1, "run.accepted", source="gateway"))
    clock.jump(140)
    db.ingest(event(2, "llm.response_received", source="gateway"))
    result = db.assess("run-1")
    assert result["state"] == "WORKER_UNRESPONSIVE"
    assert result["stale_worker_sources"] == ["worker-A"]
    assert result["worker_sources_count"] == 1


def test_partial_outage_among_independent_workers_is_visible(context):
    db, clock = context
    db.ingest(event(1, "worker.started", source="worker-A"))
    db.ingest(event(1, "worker.started", source="worker-B"))
    clock.jump(140)
    db.ingest(event(2, "worker.heartbeat", source="worker-B"))
    result = db.assess("run-1")
    assert result["state"] == "PARTIAL_WORKER_OUTAGE"
    assert result["stale_worker_sources"] == ["worker-A"]
    assert result["worker_sources_count"] == 2


@pytest.mark.parametrize("reason,expected", [
    ("INCOMPATIBLE_HERMES_VERSION", "STOP_INTEGRATION_AND_NEGOTIATE_VERSION"),
    ("MCP_SESSION_TERMINATED", "RECONNECT_TRANSPORT_AND_REPLAY_OUTBOX"),
    ("OUTBOX_BACKPRESSURE", "PAUSE_PRODUCER_AND_CHECK_STORAGE_LIMIT"),
    ("CORS_REJECTED", "CHECK_ALLOWED_EXTENSION_ORIGIN"),
])
def test_gateway_failure_codes_yield_specific_diagnostic(context, reason, expected):
    db, _ = context
    db.ingest(event(1, "run.reported_failed", reason_code=reason))
    assert db.assess("run-1")["next_action"] == expected


def test_unrelated_gateway_events_cannot_mask_worker_stagnation(context):
    db, clock = context
    db.ingest(event(1, "worker.started", source="worker-A"))
    clock.jump(360)
    db.ingest(event(2, "worker.heartbeat", source="worker-A"))
    db.ingest(event(1, "llm.response_received", source="gateway"))
    result = db.assess("run-1")
    assert result["state"] == "ALIVE_NO_PROGRESS"
    assert result["progress_age_seconds"] == 360
    assert result["live_age_seconds"] == 0
