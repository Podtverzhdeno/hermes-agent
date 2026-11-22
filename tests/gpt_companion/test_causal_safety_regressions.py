"""Causal safety regressions for independently scheduled GPT/Hermes workers.

No network, API keys, browser sessions, or external side effects are required.
These are diagnostic gates; they do not prove a trusted provider receipt.
"""

import pytest

from gpt_companion import EventJournal


@pytest.fixture
def journal(tmp_path):
    return EventJournal(tmp_path / "causal-events.sqlite3", clock=lambda: 1000.0)


def event(attempt, seq, kind, *, source="worker-1", action=None, reason=None):
    result = {
        "schema_version": 1,
        "event_id": f"{source}-{attempt}-{seq}-{kind}",
        "source": source,
        "run_id": "run-causal",
        "attempt": attempt,
        "sequence": seq,
        "kind": kind,
    }
    if action is not None:
        result["action_id"] = action
    if reason is not None:
        result["reason_code"] = reason
    return result


def test_prior_unknown_write_survives_new_attempt(journal):
    journal.ingest(event(1, 1, "tool.effect_reserved", action="github-pr"))
    journal.ingest(event(2, 1, "worker.started", source="worker-2"))
    status = journal.assess("run-causal")
    assert status["attempt"] == 2
    assert status["state"] == "NEEDS_RECONCILIATION"
    assert status["next_action"] == "RECONCILE_EFFECT_RECEIPT"
    assert status["unresolved_effects_prior_attempts"] == [
        {"attempt": 1, "action_id": "github-pr"}
    ]


def test_new_attempt_same_action_ack_does_not_close_prior_effect(journal):
    journal.ingest(event(1, 1, "tool.effect_reserved", action="deploy"))
    journal.ingest(event(2, 1, "tool.effect_reserved", source="worker-2", action="deploy"))
    journal.ingest(event(2, 2, "tool.effect_acknowledged", source="worker-2", action="deploy"))
    status = journal.assess("run-causal")
    assert status["state"] == "NEEDS_RECONCILIATION"
    assert status["unresolved_effects_prior_attempts"] == [
        {"attempt": 1, "action_id": "deploy"}
    ]


def test_late_but_causally_ordered_prior_ack_clears_only_its_attempt(journal):
    journal.ingest(event(1, 1, "tool.effect_reserved", action="write-1"))
    journal.ingest(event(2, 1, "worker.started", source="worker-2"))
    assert journal.assess("run-causal")["state"] == "NEEDS_RECONCILIATION"
    journal.ingest(event(1, 2, "tool.effect_acknowledged", action="write-1"))
    result = journal.assess("run-causal")
    assert result["state"] == "RECENT_TELEMETRY"
    assert result["unresolved_effects_prior_attempts"] == []


def test_cross_emitter_ack_is_not_causal_receipt(journal):
    journal.ingest(event(1, 1, "tool.effect_reserved", source="worker", action="pr-create"))
    journal.ingest(event(1, 1, "tool.effect_acknowledged", source="gateway", action="pr-create"))
    result = journal.assess("run-causal")
    assert result["state"] == "NEEDS_RECONCILIATION"
    assert result["unresolved_effects"] == ["pr-create"]


def test_cross_emitter_prior_ack_does_not_clear_old_write(journal):
    journal.ingest(event(1, 1, "tool.effect_reserved", source="worker", action="write"))
    journal.ingest(event(1, 1, "tool.effect_acknowledged", source="gateway", action="write"))
    journal.ingest(event(2, 1, "worker.started", source="new-worker"))
    result = journal.assess("run-causal")
    assert result["state"] == "NEEDS_RECONCILIATION"
    assert result["unresolved_effects_prior_attempts"] == [
        {"attempt": 1, "action_id": "write"}
    ]


def test_cross_emitter_approval_cannot_silently_clear_wait(journal):
    journal.ingest(event(1, 1, "approval.required", source="worker", action="deploy"))
    journal.ingest(event(1, 1, "approval.resolved", source="third-party", action="deploy"))
    result = journal.assess("run-causal")
    assert result["state"] == "TRACE_INCOMPLETE"
    assert result["pending_approvals"] == ["deploy"]


def test_backfilled_failure_does_not_replace_terminal_reason(journal):
    journal.ingest(event(1, 2, "run.reported_failed", reason="RATE_LIMITED"))
    journal.ingest(event(1, 1, "run.reported_failed", reason="AUTH_DENIED"))
    status = journal.assess("run-causal")
    assert status["state"] == "REPORTED_FAILED"
    assert status["reported_reason_code"] == "RATE_LIMITED"
    assert status["next_action"] == "HONOR_RETRY_AFTER_AND_BUDGET"


def test_clock_rewind_is_visible_not_fake_liveness(journal):
    journal.ingest(event(1, 1, "worker.started"))
    status = journal.assess("run-causal", now=900.0)
    assert status["state"] == "CLOCK_SKEW_DETECTED"
    assert status["next_action"] == "CHECK_MONOTONIC_CLOCK_AND_TIME_SYNC"
    assert status["live_age_seconds"] == 0.0


def test_no_prior_effects_does_not_override_current_report(journal):
    journal.ingest(event(1, 1, "run.reported_completed"))
    journal.ingest(event(2, 1, "run.reported_failed", source="worker-2", reason="CI_FAILED"))
    assert journal.assess("run-causal")["state"] == "REPORTED_FAILED"
    assert journal.assess("run-causal")["unresolved_effects_prior_attempts"] == []


def test_missing_sequence_in_earlier_attempt_does_not_disappear(journal):
    journal.ingest(event(1, 1, "worker.started"))
    journal.ingest(event(1, 3, "worker.stopped"))
    journal.ingest(event(2, 1, "worker.started", source="replacement"))
    result = journal.assess("run-causal")
    assert result["state"] == "TRACE_INCOMPLETE"
    assert result["missing_sequences"] == 0
    assert result["missing_sequences_prior_attempts"] == 1
    journal.ingest(event(1, 2, "worker.heartbeat"))
    repaired = journal.assess("run-causal")
    assert repaired["state"] == "RECENT_TELEMETRY"
    assert repaired["missing_sequences_prior_attempts"] == 0


def test_prior_missing_event_has_lower_priority_than_unresolved_write(journal):
    journal.ingest(event(1, 1, "tool.effect_reserved", action="write-unknown"))
    journal.ingest(event(1, 3, "worker.stopped"))
    journal.ingest(event(2, 1, "worker.started", source="replacement"))
    result = journal.assess("run-causal")
    assert result["missing_sequences_prior_attempts"] == 1
    assert result["state"] == "NEEDS_RECONCILIATION"
    assert result["unresolved_effects_prior_attempts"] == [
        {"attempt": 1, "action_id": "write-unknown"}
    ]


def test_duplicate_ack_order_must_not_mask_uncertain_effect(journal):
    # Multiple separately emitted acks cannot be collapsed into a provider
    # receipt just because the final one came from the reserving worker.
    data = [
        event(1, 1, "tool.effect_reserved", source="worker", action="deploy"),
        event(1, 1, "tool.effect_acknowledged", source="gateway", action="deploy"),
        event(1, 2, "tool.effect_acknowledged", source="worker", action="deploy"),
    ]
    from itertools import permutations
    for order in permutations(data):
        # Every isolated DB sees the same events, only delivery order changes.
        from tempfile import TemporaryDirectory
        from pathlib import Path
        with TemporaryDirectory() as directory:
            sub = EventJournal(Path(directory) / "events.sqlite3", clock=lambda: 1000.0)
            for item in order:
                sub.ingest(item)
            state = sub.assess("run-causal")
            assert state["state"] == "NEEDS_RECONCILIATION"
            assert state["unresolved_effects"] == ["deploy"]


def test_duplicate_reservations_remain_unresolved_even_after_ack(journal):
    journal.ingest(event(1, 1, "tool.effect_reserved", source="worker", action="write"))
    journal.ingest(event(1, 1, "tool.effect_reserved", source="gateway", action="write"))
    journal.ingest(event(1, 2, "tool.effect_acknowledged", source="gateway", action="write"))
    state = journal.assess("run-causal")
    assert state["state"] == "NEEDS_RECONCILIATION"
    assert state["unresolved_effects"] == ["write"]


def test_single_same_source_resolution_is_not_false_duplicate(journal):
    journal.ingest(event(1, 1, "tool.effect_reserved", action="write"))
    journal.ingest(event(1, 2, "tool.effect_acknowledged", action="write"))
    state = journal.assess("run-causal")
    assert state["unresolved_effects"] == []
    assert state["state"] == "RECENT_TELEMETRY"


def test_worker_stopped_does_not_erase_reported_failure_reason(journal):
    journal.ingest(event(1, 1, "worker.started"))
    journal.ingest(event(1, 2, "run.reported_failed", reason="CI_FAILED"))
    journal.ingest(event(1, 3, "worker.stopped"))
    status = journal.assess("run-causal")
    assert status["state"] == "REPORTED_FAILED"
    assert status["reported_reason_code"] == "CI_FAILED"
    assert status["next_action"] == "INSPECT_CHECKS_AT_EXACT_SHA"


def test_worker_stopped_does_not_erase_completed_verification_gate(journal):
    journal.ingest(event(1, 1, "worker.started"))
    journal.ingest(event(1, 2, "run.reported_completed"))
    journal.ingest(event(1, 3, "worker.stopped"))
    status = journal.assess("run-causal")
    assert status["state"] == "AWAITING_VERIFICATION"
    assert status["next_action"] == "VERIFY_ARTIFACTS_AT_EXACT_REVISION"


def test_worker_stopped_without_run_report_stays_unconfirmed(journal):
    journal.ingest(event(1, 1, "worker.started"))
    journal.ingest(event(1, 2, "worker.stopped"))
    assert journal.assess("run-causal")["state"] == "STOPPED_UNCONFIRMED"
