"""Regression tests for terminal report precedence and actionable causal diagnostics.

This module is additive to the parent PR's offline tests. No provider calls,
browser automation or privileged Hermes actions are involved.
"""

import pytest

from gpt_companion import EventJournal


@pytest.fixture
def journal(tmp_path):
    return EventJournal(tmp_path / "causal-events.sqlite3", clock=lambda: 1000.0)


def emit(journal, seq, kind, *, source="worker", **fields):
    payload = {
        "schema_version": 1,
        "event_id": f"evt-{source}-{seq}",
        "source": source,
        "run_id": "run-causal",
        "attempt": 1,
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


def test_nonzero_first_sequence_is_unknown_prefix_not_internal_gap(journal):
    emit(journal, 50, "worker.started")
    emit(journal, 51, "worker.progress")
    emit(journal, 52, "worker.heartbeat")
    result = journal.assess("run-causal")
    assert result["missing_sequences"] == 0
    assert result["unverified_prefix_sources"] == ["worker"]
    assert result["state"] == "TRACE_INCOMPLETE"
    assert result["next_action"] == "VERIFY_SOURCE_CURSOR_OR_CHECKPOINT"
    assert "UNVERIFIED_SOURCE_PREFIX" in result["diagnostic_flags"]
    assert "MISSING_SEQUENCES" not in result["diagnostic_flags"]


def test_known_internal_gap_and_unknown_prefix_are_both_reported(journal):
    emit(journal, 50, "worker.started")
    emit(journal, 52, "worker.heartbeat")
    result = journal.assess("run-causal")
    assert result["missing_sequences"] == 1
    assert result["unverified_prefix_sources"] == ["worker"]
    assert "MISSING_SEQUENCES" in result["diagnostic_flags"]
    assert "UNVERIFIED_SOURCE_PREFIX" in result["diagnostic_flags"]
    assert result["next_action"] == "FETCH_MISSING_EVENTS"


def test_source_prefix_baseline_is_scoped_independently_per_producer(journal):
    emit(journal, 1, "worker.started", source="worker")
    emit(journal, 90, "llm.request_started", source="gateway")
    emit(journal, 91, "llm.response_received", source="gateway")
    result = journal.assess("run-causal")
    assert result["missing_sequences"] == 0
    assert result["unverified_prefix_sources"] == ["gateway"]
    assert result["state"] == "TRACE_INCOMPLETE"


def test_source_seq_start_one_is_complete_not_prefix_unknown(journal):
    emit(journal, 1, "worker.started")
    emit(journal, 2, "worker.progress")
    result = journal.assess("run-causal")
    assert result["missing_sequences"] == 0
    assert result["unverified_prefix_sources"] == []
    assert result["state"] == "RECENT_TELEMETRY"


def test_unverified_prefix_does_not_hide_pending_external_write(journal):
    emit(journal, 50, "tool.effect_reserved", action_id="write-unknown")
    result = journal.assess("run-causal")
    assert result["state"] == "EFFECT_IN_FLIGHT"
    assert result["unresolved_effects"] == ["write-unknown"]
    assert "UNVERIFIED_SOURCE_PREFIX" in result["diagnostic_flags"]


def test_latest_attempt_snapshot_is_single_sql_statement(journal, monkeypatch):
    # Regression on the observable DB contract: independent autocommit reads
    # of MAX(attempt) and the row set may see different SQLite snapshots.
    import sqlite3
    import gpt_companion.journal as journal_module

    emit(journal, 1, "worker.started")
    observed_selects = []
    original_connect = sqlite3.connect

    class TrackingConnection(sqlite3.Connection):
        def execute(self, sql, *params):
            if "FROM events WHERE run_id=?" in sql:
                observed_selects.append(sql)
            return super().execute(sql, *params)

    def make_connection(*args, **kwargs):
        return original_connect(*args, factory=TrackingConnection, **kwargs)

    monkeypatch.setattr(journal_module.sqlite3, "connect", make_connection)
    result = journal.assess("run-causal")
    assert result["state"] == "RECENT_TELEMETRY"
    assert len(observed_selects) == 1
    assert "SELECT MAX(attempt)" in observed_selects[0]
    assert "SELECT event_json,received_at" in observed_selects[0]


def test_latest_attempt_snapshot_reads_only_its_attempt(journal):
    emit(journal, 1, "run.reported_failed", reason_code="CI_FAILED")
    new_attempt = {
        "schema_version": 1, "event_id": "new-worker",
        "source": "worker", "run_id": "run-causal", "attempt": 2,
        "sequence": 1, "kind": "worker.started",
    }
    assert journal.ingest(new_attempt)
    result = journal.assess("run-causal")
    assert result["attempt"] == 2
    assert result["state"] == "RECENT_TELEMETRY"
    assert result["reported_reason_code"] is None
