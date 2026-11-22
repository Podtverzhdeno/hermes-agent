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
        projection = explain_sse(
            f"id: 0\ndata: {json.dumps({'run_id': rid, 'event': 'run.queued',
                                     'seq': 0, 'timestamp': 1795344000})}\n\n",
            rid)
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
