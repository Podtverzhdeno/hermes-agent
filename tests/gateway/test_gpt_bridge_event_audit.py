"""Offline contract tests for read-only, metadata-only GPT run auditing."""

import json
import pytest

from gateway.gpt_bridge_event_audit import (
    CausalRunAuditor,
    InvalidTelemetry,
    explain_sse,
    normalize_run_event,
    parse_sse_frames,
)


RID = "run_" + "a" * 32


def event(kind, seq, **extra):
    return {"run_id": RID, "event": kind, "seq": seq,
            "timestamp": 1795344000.0, **extra}


def sse(*payloads):
    return "".join(
        f"id: {data['seq']}\ndata: {json.dumps(data)}\n\n" for data in payloads
    )


def test_native_run_success_requires_independent_status_snapshot():
    wire = sse(event("run.queued", 0), event("run.running", 1),
               event("run.completed", 2))
    tentative = explain_sse(wire, RID)
    assert tentative["reported_terminal"] == "completed"
    assert tentative["stop_reason"] == "TERMINAL_EVENT_NOT_STATUS_VERIFIED"
    assert tentative["next_action"] == "FETCH_RUN_STATUS"
    grounded = explain_sse(wire, RID, {"run_id": RID, "status": "completed"})
    assert grounded["stop_reason"] == "COMPLETED"
    assert grounded["missing_events"] is False
    assert grounded["observed_events"] == 3


def test_client_disconnect_does_not_mean_agent_failed():
    wire = sse(event("run.queued", 0), event("run.running", 1))
    output = explain_sse(wire, RID)
    assert output["stop_reason"] == "NONTERMINAL_OBSERVATION"
    assert output["next_action"] == "CHECK_AUTHORITATIVE_RUN_STATUS"


def test_duplicate_replayed_sequence_does_not_reexecute_projection():
    wire = sse(event("run.queued", 0), event("run.running", 1),
               event("run.running", 1), event("run.completed", 2))
    outcome = explain_sse(wire, RID)
    assert outcome["observed_events"] == 3
    assert outcome["missing_events"] is False


def test_missing_first_sequence_is_evidence_gap_not_failure():
    out = explain_sse(sse(event("tool.completed", 23, tool_call_id="call_1")), RID)
    assert out["missing_events"]
    assert out["stop_reason"] == "EVIDENCE_INCOMPLETE"
    assert "HISTORY_NOT_OBSERVED" in out["evidence"]


def test_sequence_gap_requires_snapshot_and_replay():
    out = explain_sse(sse(event("run.queued", 0),
                          event("run.completed", 9)), RID,
                      {"run_id": RID, "status": "completed"})
    assert out["missing_events"]
    assert "SEQUENCE_GAP" in out["evidence"]
    assert out["next_action"] == "FETCH_STATUS_AND_REPLAY_EVENTS"


def test_replay_truncated_explicitly_declares_evidence_loss():
    wire = (f"data: {json.dumps(event('replay.truncated', 0, oldest_retained_seq=900))}\n\n")
    out = explain_sse(wire, RID)
    assert out["missing_events"]
    assert "REPLAY_TRUNCATED" in out["evidence"]


def test_inflight_tool_requires_effect_reconciliation():
    out = explain_sse(sse(event("run.queued", 0),
                          event("tool.started", 1, tool_call_id="call_1")), RID)
    assert out["pending_tool_calls"] == 1
    assert out["stop_reason"] == "POSSIBLE_EXTERNAL_EFFECT_UNKNOWN"
    assert out["next_action"] == "RECONCILE_TOOL_EFFECT"


def test_completed_tool_clears_pending_effect():
    out = explain_sse(sse(event("run.queued", 0),
                          event("tool.started", 1, tool_call_id="call_1"),
                          event("tool.completed", 2, tool_call_id="call_1"),
                          event("run.completed", 3)), RID,
                      {"run_id": RID, "status": "completed"})
    assert out["pending_tool_calls"] == 0
    assert out["stop_reason"] == "COMPLETED"


def test_completion_with_pending_tool_never_gives_false_success():
    out = explain_sse(sse(event("run.queued", 0),
                          event("tool.started", 1, tool_call_id="call_1"),
                          event("run.completed", 2)), RID,
                      {"run_id": RID, "status": "completed"})
    assert out["stop_reason"] == "POSSIBLE_EXTERNAL_EFFECT_UNKNOWN"
    assert "COMPLETED_WITH_UNCONFIRMED_TOOL" in out["evidence"]


def test_contradicting_terminal_status_flagged():
    out = explain_sse(sse(event("run.queued", 0), event("run.completed", 1)), RID,
                      {"run_id": RID, "status": "failed"})
    assert out["status_inconsistent"]
    assert out["stop_reason"] == "CONTRADICTORY_STATUS"
    assert "TERMINAL_STATUS_MISMATCH" in out["evidence"]


def test_pending_approval_must_not_be_automatically_resolved():
    out = explain_sse(sse(event("run.queued", 0),
                          event("approval.request", 1, request_id="approve_1")), RID)
    assert out["pending_approvals"] == 1
    assert out["stop_reason"] == "WAITING_APPROVAL"
    assert out["next_action"] == "WAIT_FOR_AUTHORIZED_APPROVAL"


def test_approval_responded_clears_waiting_state():
    out = explain_sse(sse(event("run.queued", 0),
                          event("approval.request", 1, request_id="approve_1"),
                          event("approval.responded", 2, request_id="approve_1")), RID)
    assert out["pending_approvals"] == 0


def test_status_snapshot_run_id_mismatch_is_refused():
    with pytest.raises(InvalidTelemetry):
        explain_sse(sse(event("run.queued", 0)), RID,
                    {"run_id": "run_other", "status": "completed"})


def test_cross_run_event_is_rejected_without_cross_agent_data_leak():
    auditor = CausalRunAuditor(RID)
    other = normalize_run_event({"run_id": "run_other",
                                 "event": "run.completed", "seq": 0})
    with pytest.raises(InvalidTelemetry):
        auditor.observe(other)


def test_sensitive_stream_fields_are_not_emitted_or_retained():
    secret = "A_VERY_PRIVATE_PROMPT_API_KEY_9999"
    message = event("run.started", 0, user_message={"content": secret},
                    preview=secret, command=secret, authorization=secret)
    out = explain_sse(sse(message), RID)
    assert secret not in json.dumps(out)
    normalized = normalize_run_event(message)
    assert secret not in repr(normalized)


def test_malformed_json_never_echoes_secret():
    secret = "password_super_sensitive"
    try:
        parse_sse_frames(f"data: {{BROKEN {secret}\n\n")
    except InvalidTelemetry as exc:
        assert secret not in str(exc)
    else:
        raise AssertionError("malformed frame must be rejected")


@pytest.mark.parametrize("field,value", [
    ("run_id", "../escape"), ("event", "tool.started\ninjected"),
    ("seq", -1), ("seq", True), ("timestamp", float("nan")),
])
def test_untrusted_metadata_rejected_without_echo(field, value):
    source = event("run.queued", 0)
    source[field] = value
    with pytest.raises(InvalidTelemetry):
        normalize_run_event(source)


def test_sse_keepalive_and_comments_are_not_actions():
    wire = (": open\n\n: keepalive\n\n" + sse(event("run.queued", 0))
            + ": stream closed\n\n")
    events = parse_sse_frames(wire)
    assert len(events) == 1
    assert events[0].kind == "run.queued"


def test_parallel_agents_diagnostics_remain_strictly_isolated():
    # The audit is pure and never joins event streams from different agents.
    seen = []
    for i in range(30):
        rid = f"run_{i:032x}"
        payload = {"run_id": rid, "event": "run.queued",
                   "seq": 0, "timestamp": 1795344000}
        projection = explain_sse(
            "id: 0\ndata: " + json.dumps(payload) + "\n\n", rid)
        seen.append(projection["run_id"])
        assert projection["observed_events"] == 1
    assert len(set(seen)) == 30


def test_reordering_late_frame_never_silently_claims_full_history():
    wire = sse(event("run.queued", 0), event("run.completed", 2),
               event("run.running", 1))
    out = explain_sse(wire, RID)
    assert out["missing_events"]
    assert "OUT_OF_ORDER_EVENT" in out["evidence"]


def test_frame_size_bounded_before_private_capture():
    with pytest.raises(InvalidTelemetry):
        parse_sse_frames("data: " + ("x" * (256 * 1024 + 1)) + "\n\n")


def test_late_event_does_not_rewind_last_confirmed_sequence():
    out = explain_sse(sse(event("run.queued", 0), event("run.completed", 2),
                          event("tool.started", 1, tool_call_id="late_call")), RID)
    assert out["missing_events"]
    assert out["last_event"] == "run.completed"
    # A late effect must not be added as if it started after completion.
    assert out["pending_tool_calls"] == 0
    assert "OUT_OF_ORDER_EVENT" in out["evidence"]


def test_stale_status_snapshot_cannot_confirm_newer_completion():
    wire = sse(event("run.queued", 0), event("run.completed", 1))
    out = explain_sse(wire, RID,
        {"run_id": RID, "status": "completed", "updated_at": 1795343999.0})
    assert out["stop_reason"] == "STALE_STATUS_SNAPSHOT"
    assert out["next_action"] == "REFETCH_AUTHORITATIVE_STATUS"
    assert "STATUS_SNAPSHOT_STALE" in out["evidence"]


def test_fresh_status_snapshot_can_confirm_terminal():
    wire = sse(event("run.queued", 0), event("run.completed", 1))
    out = explain_sse(wire, RID,
        {"run_id": RID, "status": "completed", "updated_at": 1795344002.0})
    assert out["stop_reason"] == "COMPLETED"


@pytest.mark.parametrize("bad_time", ["not-a-time", float("nan"), -10, True])
def test_invalid_status_timestamps_refused_safely(bad_time):
    with pytest.raises(InvalidTelemetry):
        explain_sse(sse(event("run.queued", 0)), RID,
            {"run_id": RID, "status": "running", "updated_at": bad_time})


def test_completed_run_with_failed_tool_keeps_failure_evidence():
    wire = sse(event("run.queued", 0),
               event("tool.started", 1, tool_call_id="tool_1"),
               event("tool.completed", 2, tool_call_id="tool_1", error=True,
                     preview="never_record_me"),
               event("run.completed", 3))
    out = explain_sse(wire, RID,
        {"run_id": RID, "status": "completed", "updated_at": 1795344001.0})
    assert out["tool_errors"] == 1
    assert out["stop_reason"] == "COMPLETED_WITH_TOOL_ERRORS"
    assert out["next_action"] == "INSPECT_TOOL_FAILURE_RECOVERY"
    assert "TOOL_ERROR_OBSERVED" in out["evidence"]
    assert "never_record_me" not in json.dumps(out)


def test_unscoped_single_approval_response_is_weakly_inferred():
    wire = sse(event("run.queued", 0),
               event("approval.request", 1, request_id="request_1"),
               event("approval.responded", 2))
    out = explain_sse(wire, RID)
    assert out["pending_approvals"] == 0
    assert "APPROVAL_INFERRED_SINGLE_PENDING" in out["evidence"]


def test_unscoped_multi_approval_response_remains_ambiguous():
    wire = sse(event("run.queued", 0),
               event("approval.request", 1, request_id="request_1"),
               event("approval.request", 2, request_id="request_2"),
               event("approval.responded", 3))
    out = explain_sse(wire, RID)
    assert out["missing_events"]
    assert out["pending_approvals"] == 2
    assert "APPROVAL_RESOLUTION_UNCORRELATED" in out["evidence"]
    assert out["next_action"] == "FETCH_STATUS_AND_REPLAY_EVENTS"


def test_token_shaped_reason_is_not_mistaken_for_safe_code():
    credential = "sk-proj-SUPERSECRETINCIDENTTOKEN"
    wire = sse(event("run.queued", 0),
               event("run.failed", 1, reason_code=credential))
    out = explain_sse(wire, RID,
        {"run_id": RID, "status": "failed", "turn_exit_reason": credential,
         "updated_at": 1795344001.0})
    assert credential not in json.dumps(out)
    assert out["stop_reason"] == "UNCLASSIFIED"


def test_token_shaped_unknown_event_is_redacted_but_schema_drift_flagged():
    credential = "sk-proj-EXPORTEDASUNKNOWNEVENT"
    out = explain_sse(sse(event("run.queued", 0), event(credential, 1)), RID)
    assert credential not in json.dumps(out)
    assert out["last_event"] == "event.unrecognized"
    assert out["missing_events"] is True
    assert "UNRECOGNIZED_EVENT" in out["evidence"]


def test_arbitrary_status_is_not_echoed_or_treated_as_terminal():
    credential = "ghp_SUPERSENSITIVEACCESSCODE"
    out = explain_sse(sse(event("run.queued", 0)), RID,
                      {"run_id": RID, "status": credential,
                       "updated_at": 1795344001.0})
    assert credential not in json.dumps(out)
    assert out["supplied_status"] == "unknown_status"
    assert "UNRECOGNIZED_STATUS" in out["evidence"]


def test_native_interim_and_stopping_events_are_not_schema_errors():
    wire = sse(event("run.queued", 0), event("message.interim", 1,
                          text="PRIVATE_ASSISTANT_COMMENTARY"),
               event("run.stopping", 2))
    out = explain_sse(wire, RID)
    assert out["missing_events"] is False
    assert "UNRECOGNIZED_EVENT" not in out["evidence"]
    assert "PRIVATE_ASSISTANT_COMMENTARY" not in json.dumps(out)
    assert out["last_event"] == "run.stopping"


@pytest.mark.parametrize("final_status", ["cancelled", "interrupted"])
def test_cancelled_run_status_not_proof_remote_effect_stopped(final_status):
    # A live Bot Chat owner can continue after gateway-level cancellation;
    # lack of a pending local tool event does not prove no external effects.
    out = explain_sse(
        sse(event("run.queued", 0),
            event("run." + final_status, 1)),
        RID, {"run_id": RID, "status": final_status,
              "updated_at": 1795344001.0})
    assert out["stop_reason"] == final_status.upper()
    assert out["next_action"] == "VERIFY_EXTERNAL_EFFECTS_BEFORE_RETRY"
    assert "CANCELLATION_NOT_EFFECT_PROOF" in out["evidence"]


@pytest.mark.parametrize("reason", [
    "empty_response_exhausted", "all_retries_exhausted_no_response",
    "partial_stream_recovery", "budget_exhausted", "pending_tool_result",
    "context_compression_timeout", "text_response(stop)",
])
def test_official_exact_exit_reasons_are_categorized_without_raw_error(reason):
    out = explain_sse(sse(event("run.queued", 0), event("run.failed", 1)), RID,
        {"run_id": RID, "status": "failed", "updated_at": 1795344001,
         "turn_exit_reason": reason})
    assert out["stop_reason"] == reason


@pytest.mark.parametrize("reason,expected", [
    ("max_iterations_reached(3/3)", "max_iterations_reached"),
    ("interrupted_during_api_call(watchdog)", "interrupted_during_api_call"),
    ("repeated_outer_errors(4)", "repeated_outer_errors"),
    ("max_iterations_reached(sk-proj-SECRET)", "UNCLASSIFIED"),
])
def test_parameterized_turn_exit_reason_does_not_leak_suffix(reason, expected):
    out = explain_sse(sse(event("run.queued", 0), event("run.failed", 1)), RID,
        {"run_id": RID, "status": "failed", "updated_at": 1795344001,
         "turn_exit_reason": reason})
    assert out["stop_reason"] == expected
    assert reason not in json.dumps(out) or reason == expected


def test_sse_frame_id_must_match_json_seq():
    bad = f"id: 7\ndata: {json.dumps(event('run.queued', 6))}\n\n"
    with pytest.raises(InvalidTelemetry, match="SSE cursor contradicts"):
        parse_sse_frames(bad)


def test_invalid_sse_frame_id_rejected_without_echo():
    secret = "sk-proj-SHOULD_NOT_BE_ECHOED"
    bad = f"id: {secret}\ndata: {json.dumps(event('run.queued', 0))}\n\n"
    with pytest.raises(InvalidTelemetry) as observed:
        parse_sse_frames(bad)
    assert secret not in str(observed.value)
