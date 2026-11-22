"""Regression tests for terminal report precedence and actionable causal diagnostics.

This module is additive to the parent PR's offline tests. No provider calls,
browser automation or privileged Hermes actions are involved.
"""

import pytest

from gpt_companion import EventJournal


@pytest.fixture
def journal(tmp_path):
    return EventJournal(tmp_path / "causal-events.sqlite3", clock=lambda: 1000.0)


def emit(journal, seq, kind, *, source="worker", attempt=1, **fields):
    payload = {
        "schema_version": 1,
        "event_id": f"evt-{attempt}-{source}-{seq}",
        "source": source,
        "run_id": "run-causal",
        "attempt": attempt,
        "sequence": seq,
        "kind": kind,
        **fields,
    }
    assert journal.ingest(payload) is True


def test_failure_is_not_hidden_by_later_worker_stop(journal):
    emit(journal, 1, "worker.started")
    emit(journal, 2, "run.reported_failed", reason_code="AUTH_DENIED")
    emit(journal, 3, "worker.stopped")
    result = journal.assess("run-causal")
    assert result["state"] == "REPORTED_FAILED"
    assert result["reported_reason_code"] == "AUTH_DENIED"
    assert result["next_action"] == "CHECK_CREDENTIAL_SCOPE"
    assert result["diagnostic_flags"] == []


def test_reported_completion_still_needs_verification_after_stop(journal):
    emit(journal, 1, "worker.started")
    emit(journal, 2, "run.reported_completed")
    emit(journal, 3, "worker.stopped")
    result = journal.assess("run-causal")
    assert result["state"] == "AWAITING_VERIFICATION"
    assert result["next_action"] == "VERIFY_ARTIFACTS_AT_EXACT_REVISION"
    assert "SUCCEEDED" not in result["state"]


def test_stop_without_outcome_remains_uncertain(journal):
    emit(journal, 1, "worker.started")
    emit(journal, 2, "worker.stopped")
    assert journal.assess("run-causal")["state"] == "STOPPED_UNCONFIRMED"


@pytest.mark.parametrize("first, second", [
    ("run.reported_completed", "run.reported_failed"),
    ("run.reported_failed", "run.reported_completed"),
])
def test_conflicting_outcomes_from_one_source_never_pass_as_final(journal, first, second):
    emit(journal, 1, "worker.started")
    emit(journal, 2, first)
    emit(journal, 3, second)
    result = journal.assess("run-causal")
    assert result["state"] == "TRACE_INCOMPLETE"
    assert result["next_action"] == "RECONCILE_CONFLICTING_EVENTS"
    assert result["reported_reason_code"] is None
    assert "CONFLICTING_OUTCOME_REPORTS" in result["diagnostic_flags"]
    assert "EVENT_CAUSALITY_CONFLICT" in result["diagnostic_flags"]


def test_late_delivery_does_not_make_stop_mask_earlier_success_report(journal):
    emit(journal, 3, "worker.stopped")
    emit(journal, 1, "worker.started")
    emit(journal, 2, "run.reported_completed")
    result = journal.assess("run-causal")
    assert result["state"] == "AWAITING_VERIFICATION"
    assert result["missing_sequences"] == 0
    assert journal.verify_chain() is True


def test_gap_has_distinct_recovery_step_from_conflict(journal):
    emit(journal, 1, "worker.started")
    emit(journal, 3, "worker.heartbeat")
    result = journal.assess("run-causal")
    assert result["state"] == "TRACE_INCOMPLETE"
    assert result["next_action"] == "FETCH_MISSING_EVENTS"
    assert result["diagnostic_flags"] == ["MISSING_SEQUENCES"]


def test_causally_impossible_effect_resolution_is_not_a_simple_gap(journal):
    emit(journal, 1, "tool.effect_acknowledged", action_id="write-1")
    emit(journal, 2, "tool.effect_reserved", action_id="write-1")
    result = journal.assess("run-causal")
    assert result["state"] == "TRACE_INCOMPLETE"
    assert result["next_action"] == "RECONCILE_CONFLICTING_EVENTS"
    assert result["missing_sequences"] == 0
    assert "EVENT_CAUSALITY_CONFLICT" in result["diagnostic_flags"]


def test_unconfirmed_effect_still_overrides_reported_completion(journal):
    emit(journal, 1, "tool.effect_reserved", action_id="write-1")
    emit(journal, 2, "run.reported_completed")
    emit(journal, 3, "worker.stopped")
    result = journal.assess("run-causal")
    assert result["state"] == "EFFECT_IN_FLIGHT"
    assert result["unresolved_effects"] == ["write-1"]


def test_cross_source_terminal_conflict_cannot_claim_success(journal):
    emit(journal, 1, "run.reported_completed", source="worker")
    emit(journal, 1, "run.reported_failed", source="gateway", reason_code="CI_FAILED")
    result = journal.assess("run-causal")
    assert result["state"] == "TRACE_INCOMPLETE"
    assert result["next_action"] == "RECONCILE_CONFLICTING_EVENTS"
    assert "CROSS_SOURCE_TERMINALS" in result["diagnostic_flags"]


def test_replay_after_restart_preserves_diagnostic_flags(journal):
    emit(journal, 1, "run.reported_failed", reason_code="RATE_LIMITED")
    emit(journal, 2, "worker.stopped")
    restored = EventJournal(journal.path, clock=lambda: 1000.0)
    assert restored.verify_chain() is True
    result = restored.assess("run-causal")
    assert result["state"] == "REPORTED_FAILED"
    assert result["next_action"] == "HONOR_RETRY_AFTER_AND_BUDGET"
    assert result["diagnostic_flags"] == []

def test_observer_wall_clock_regression_is_not_fresh_liveness(journal):
    emit(journal, 1, "worker.started")
    result = journal.assess("run-causal", now=900.0)
    assert result["state"] == "CLOCK_SKEW_DETECTED"
    assert result["next_action"] == "CHECK_MONOTONIC_CLOCK_AND_TIME_SYNC"
    assert "CLOCK_REGRESSION" in result["diagnostic_flags"]
    assert result["live_age_seconds"] == 0.0  # clamped age is not evidence of life


def test_clock_regression_does_not_authorize_effect_retry(journal):
    emit(journal, 1, "tool.effect_reserved", action_id="write-1")
    result = journal.assess("run-causal", now=900.0)
    assert result["state"] == "EFFECT_IN_FLIGHT"
    assert result["unresolved_effects"] == ["write-1"]
    assert "CLOCK_REGRESSION" in result["diagnostic_flags"]
    assert result["next_action"] == "MONITOR_NO_BLIND_RETRY"


def test_previous_attempt_uncertain_write_survives_new_attempt(journal):
    emit(journal, 1, "tool.effect_reserved", attempt=1, action_id="write-v1")
    emit(journal, 1, "worker.started", attempt=2)
    result = journal.assess("run-causal")
    assert result["attempt"] == 2
    assert result["state"] == "NEEDS_RECONCILIATION"
    assert result["next_action"] == "RECONCILE_PREVIOUS_ATTEMPT_EFFECTS"
    assert result["prior_attempt_unresolved_effect_count"] == 1
    assert result["prior_attempt_unresolved_effects"] == [
        {"attempt": 1, "action_id": "write-v1"}]
    assert "PRIOR_ATTEMPT_EFFECT_UNKNOWN" in result["diagnostic_flags"]


def test_prior_attempt_matching_claimed_resolution_no_longer_unmatched(journal):
    emit(journal, 1, "tool.effect_reserved", attempt=1, action_id="write-v1")
    emit(journal, 2, "tool.effect_acknowledged", attempt=1, action_id="write-v1")
    emit(journal, 1, "worker.started", attempt=2)
    result = journal.assess("run-causal")
    assert result["state"] == "RECENT_TELEMETRY"
    assert result["prior_attempt_unresolved_effect_count"] == 0
    # This is only telemetry: a claimed ACK never certifies an external effect.
    assert "SUCCEEDED" not in result["state"]


def test_invalid_prior_effect_causal_order_remains_unknown(journal):
    emit(journal, 1, "tool.effect_acknowledged", attempt=1, action_id="write-v1")
    emit(journal, 2, "tool.effect_reserved", attempt=1, action_id="write-v1")
    emit(journal, 1, "worker.started", attempt=2)
    assert journal.assess("run-causal")["state"] == "NEEDS_RECONCILIATION"


def test_latest_attempt_ack_cannot_clear_previous_attempt_write(journal):
    emit(journal, 1, "tool.effect_reserved", attempt=1, action_id="same-id")
    emit(journal, 1, "tool.effect_acknowledged", attempt=2, action_id="same-id")
    assert journal.assess("run-causal")["prior_attempt_unresolved_effect_count"] == 1


def test_prior_attempt_effect_display_is_bounded(journal):
    for attempt in range(1, 53):
        emit(journal, 1, "tool.effect_reserved", attempt=attempt,
             action_id=f"action-{attempt}")
    emit(journal, 1, "worker.started", attempt=53)
    result = journal.assess("run-causal")
    assert result["state"] == "NEEDS_RECONCILIATION"
    assert result["prior_attempt_unresolved_effect_count"] == 52
    assert len(result["prior_attempt_unresolved_effects"]) == 50
    assert "PRIOR_EFFECT_LIST_TRUNCATED" in result["diagnostic_flags"]


def test_prior_attempt_reservation_with_only_other_attempt_failure_is_unknown(journal):
    emit(journal, 1, "tool.effect_reserved", attempt=1, action_id="write-v1")
    emit(journal, 1, "run.reported_failed", attempt=2, reason_code="AUTH_DENIED")
    result = journal.assess("run-causal")
    assert result["state"] == "NEEDS_RECONCILIATION"
    assert result["reported_reason_code"] is None
    assert result["prior_attempt_unresolved_effect_count"] == 1
