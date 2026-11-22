"""Read-only causal audit of Hermes /v1/runs SSE event exports.

This module never accepts credentials, runs a task, clicks a browser UI,
or mutates Hermes state. It interprets observed events, NOT private GPT
reasoning or a source-of-truth execution ledger.

Native upstream run SSE payloads contain {event, run_id, timestamp, seq};
the SSE frame also has "id: <seq>". Upstream emits "replay.truncated"
when a caller's cursor falls outside its bounded buffer. Treat that as
evidence loss, not as an invitation to reconstruct a fictitious timeline.
"""

from dataclasses import dataclass, field, asdict
import argparse
import json
from pathlib import Path
import re
import sys
from typing import Iterable, Optional


_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SAFE_CODE = re.compile(r"^[A-Za-z0-9_.:-]{1,96}$")
# Treat externally supplied labels as untrusted content. Syntax validation
# alone is not redaction: a token such as sk-secret can look like a code.
_EVENT_ALLOWLIST = frozenset((
    "run.queued", "run.running", "run.completed", "run.failed",
    "run.cancelled", "run.interrupted", "run.steered",
    "tool.started", "tool.completed", "reasoning.available",
    "subagent.start", "subagent.complete", "message.delta",
    "approval.request", "approval.responded", "approval.resolved",
    "approval.denied", "approval.cancelled", "replay.truncated",
))
_STATUS_ALLOWLIST = frozenset((
    "queued", "running", "waiting_for_approval", "completed",
    "failed", "cancelled", "interrupted", "stopping", "unknown",
))
_REASON_ALLOWLIST = frozenset((
    "AGENT_ERROR", "STREAM_FAILED", "AGENT_CANCELLED",
    "AUTH_REQUIRED", "AUTH_EXPIRED", "PERMISSION_DENIED",
    "THROTTLED", "UPSTREAM_UNAVAILABLE", "MODEL_REJECTED",
    "BROWSER_TARGET_LOST", "EXTENSION_SUSPENDED", "DOM_CONTRACT_CHANGED",
    "SSE_CLIENT_GONE", "WAITING_HUMAN", "DEPENDENCY_UNAVAILABLE",
    "IDEMPOTENCY_CONFLICT", "IN_PROGRESS", "SIDE_EFFECT_UNCERTAIN",
    "WORKER_STALLED", "UNKNOWN", "OUTCOME_UNKNOWN",
    "max_iterations", "max_turns", "context_limit", "model_error",
    "tool_error", "interrupted", "completed", "failed", "partial",
))
_TERMINAL = frozenset(("completed", "failed", "cancelled", "interrupted"))
_TOOL_BEGIN = frozenset(("tool.started",))
_TOOL_END = frozenset(("tool.completed",))
_APPROVAL_BEGIN = frozenset(("approval.request",))
_APPROVAL_END = frozenset(("approval.responded", "approval.resolved", "approval.denied", "approval.cancelled"))
_FINISH_EVENT = {
    "run.completed": "completed", "run.failed": "failed",
    "run.cancelled": "cancelled", "run.interrupted": "interrupted",
}
_MAX_FRAMES = 30000
_MAX_FRAME_CHARS = 256 * 1024
_MAX_BYTES = 16 * 1024 * 1024


class InvalidTelemetry(ValueError):
    """Malformed or unsafe event export; no hidden or raw content in message."""


@dataclass(frozen=True)
class SafeEvent:
    run_id: str
    kind: str
    seq: Optional[int]
    timestamp: Optional[float]
    tool_call_id: Optional[str]
    request_id: Optional[str]
    reason: Optional[str]
    tool_error: Optional[bool] = None
    # Never retain the raw event, preview, prompt, transcript or credentials.
    truncated: bool = False


@dataclass(frozen=True)
class RunExplanation:
    run_id: str
    observed_events: int
    highest_seq: Optional[int]
    last_event: Optional[str]
    last_event_timestamp: Optional[float]
    reported_terminal: Optional[str]
    supplied_status: Optional[str]
    pending_tool_calls: int
    tool_errors: int
    pending_approvals: int
    missing_events: bool
    status_inconsistent: bool
    stop_reason: str
    next_action: str
    evidence: tuple[str, ...]

    def as_dict(self) -> dict:
        return asdict(self)


def _safe_id(value, *, optional=False) -> Optional[str]:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not _RUN_ID.fullmatch(value):
        raise InvalidTelemetry("Invalid run or correlation identifier")
    return value


def _safe_event_kind(value) -> str:
    if not isinstance(value, str) or not _SAFE_CODE.fullmatch(value):
        raise InvalidTelemetry("Event type is missing or invalid")
    return value if value in _EVENT_ALLOWLIST else "event.unrecognized"


def _safe_reason(value) -> Optional[str]:
    if value is None:
        return None
    # Unknown categories are deliberately dropped rather than echoed.
    # Raw provider exception text may be a single identifier-shaped secret.
    return value if isinstance(value, str) and value in _REASON_ALLOWLIST else "UNCLASSIFIED"


def _safe_status(value) -> str:
    if not isinstance(value, str) or not _SAFE_CODE.fullmatch(value):
        raise InvalidTelemetry("Run status is missing or invalid")
    return value if value in _STATUS_ALLOWLIST else "unknown_status"


def normalize_run_event(payload: dict, *, sse_id=None) -> SafeEvent:
    """Extract an explicit allowlist from a potentially sensitive SSE event."""
    if not isinstance(payload, dict):
        raise InvalidTelemetry("Event payload must be a JSON object")
    run_id = _safe_id(payload.get("run_id"))
    kind = _safe_event_kind(payload.get("event"))
    raw_seq = payload.get("seq", sse_id)
    if raw_seq is None:
        seq = None
    else:
        if isinstance(raw_seq, bool):
            raise InvalidTelemetry("Invalid sequence")
        try:
            seq = int(raw_seq)
        except (ValueError, TypeError, OverflowError):
            raise InvalidTelemetry("Invalid sequence") from None
        if str(raw_seq).strip() != str(seq) or seq < 0 or seq > 2**53:
            raise InvalidTelemetry("Invalid sequence")
    timestamp = payload.get("timestamp")
    if timestamp is not None:
        if isinstance(timestamp, bool):
            raise InvalidTelemetry("Invalid timestamp")
        try:
            timestamp = float(timestamp)
        except (ValueError, TypeError, OverflowError):
            raise InvalidTelemetry("Invalid timestamp") from None
        if not (0 <= timestamp < 4102444800):
            raise InvalidTelemetry("Invalid timestamp")
    tool_id = _safe_id(payload.get("tool_call_id"), optional=True)
    approval_id = _safe_id(payload.get("request_id"), optional=True)
    # Hermes uses turn_exit_reason in terminal run events and error reason in
    # some status surfaces; avoid raw "error" text.
    reason = _safe_reason(payload.get("turn_exit_reason") or payload.get("reason_code"))
    tool_error = payload.get("error") if (
        kind == "tool.completed" and isinstance(payload.get("error"), bool)
    ) else None
    return SafeEvent(run_id, kind, seq, timestamp, tool_id,
                     approval_id, reason, tool_error, kind == "replay.truncated")


class CausalRunAuditor:
    """Bounded-memory, read-only projection; one instance per run.

    All event transitions are tentative until checked against a separate
    authenticated run-status snapshot. Terminal SSE events are observations
    but never authorize a side effect or a remote retry.
    """

    def __init__(self, run_id: str):
        self.run_id = _safe_id(run_id)
        self._event_count = 0
        self._highest_seq: Optional[int] = None
        self._seen: set[int] = set()
        self._last_event: Optional[str] = None
        self._last_timestamp: Optional[float] = None
        self._reported_terminal: Optional[str] = None
        self._pending_tools: set[str] = set()
        self._tool_errors = 0
        self._pending_approvals: set[str] = set()
        self._missing_events = False
        self._anomalies: set[str] = set()
        self._reason: Optional[str] = None
        self._status: Optional[str] = None
        self._status_updated_at: Optional[float] = None

    def observe(self, event: SafeEvent) -> None:
        if event.run_id != self.run_id:
            raise InvalidTelemetry("Cross-run event cannot join a run")
        if self._event_count >= _MAX_FRAMES:
            raise InvalidTelemetry("Event count exceeds audit limit")
        late_event = False
        if event.seq is None:
            self._missing_events = True
        else:
            if event.seq in self._seen:
                # Replay after reconnect is expected; don't count or apply
                # the same sequence a second time.
                return
            if self._highest_seq is not None:
                if event.seq > self._highest_seq + 1:
                    self._missing_events = True
                    self._anomalies.add("SEQUENCE_GAP")
                if event.seq < self._highest_seq:
                    late_event = True
                    self._missing_events = True
                    self._anomalies.add("OUT_OF_ORDER_EVENT")
            elif event.seq > 0:
                # A stream that began with Last-Event-ID is a valid slice,
                # but it cannot establish a full causal timeline by itself.
                self._missing_events = True
                self._anomalies.add("HISTORY_NOT_OBSERVED")
            self._seen.add(event.seq)
            self._highest_seq = max(event.seq, self._highest_seq if self._highest_seq is not None else -1)

        self._event_count += 1
        if late_event:
            # Do not allow a delayed older event to roll back the current
            # projection or create false pending tool/approval states.
            # The ordered history remains incomplete until independently
            # reconciled, even if later events fill this sequence gap.
            return
        self._last_event = event.kind
        self._last_timestamp = event.timestamp
        if event.truncated:
            self._missing_events = True
            self._anomalies.add("REPLAY_TRUNCATED")
        if event.kind == "event.unrecognized":
            self._missing_events = True
            self._anomalies.add("UNRECOGNIZED_EVENT")
        if event.kind in _TOOL_BEGIN:
            if event.tool_call_id:
                self._pending_tools.add(event.tool_call_id)
            else:
                self._missing_events = True
                self._anomalies.add("TOOL_CORRELATION_MISSING")
        elif event.kind in _TOOL_END:
            if event.tool_error is True:
                self._tool_errors += 1
                self._anomalies.add("TOOL_ERROR_OBSERVED")
            if event.tool_call_id:
                if event.tool_call_id not in self._pending_tools:
                    self._missing_events = True
                    self._anomalies.add("TOOL_START_NOT_OBSERVED")
                self._pending_tools.discard(event.tool_call_id)
        elif event.kind in _APPROVAL_BEGIN:
            if event.request_id:
                self._pending_approvals.add(event.request_id)
            else:
                self._missing_events = True
                self._anomalies.add("APPROVAL_CORRELATION_MISSING")
        elif event.kind in _APPROVAL_END:
            if event.request_id:
                self._pending_approvals.discard(event.request_id)
            elif len(self._pending_approvals) == 1:
                # Some upstream approval.responded events omit request_id
                # when the unscoped operator decision resolves the only
                # pending approval. This is a weak inference, not proof.
                self._pending_approvals.clear()
                self._anomalies.add("APPROVAL_INFERRED_SINGLE_PENDING")
            elif self._pending_approvals:
                self._missing_events = True
                self._anomalies.add("APPROVAL_RESOLUTION_UNCORRELATED")
        if event.kind in _FINISH_EVENT:
            new_terminal = _FINISH_EVENT[event.kind]
            if self._reported_terminal and self._reported_terminal != new_terminal:
                self._anomalies.add("CONFLICTING_TERMINAL_EVENTS")
            self._reported_terminal = new_terminal
            self._reason = event.reason
        if event.kind == "run.completed" and self._pending_tools:
            self._anomalies.add("COMPLETED_WITH_UNCONFIRMED_TOOL")

    def observe_status(self, status: dict) -> None:
        """A caller-provided status snapshot; transport/auth must be checked by caller."""
        if not isinstance(status, dict) or status.get("run_id") != self.run_id:
            raise InvalidTelemetry("Run status snapshot does not match run")
        value = _safe_status(status.get("status"))
        self._status = value
        if value == "unknown_status":
            self._missing_events = True
            self._anomalies.add("UNRECOGNIZED_STATUS")
        raw_updated = status.get("updated_at")
        if raw_updated is not None:
            if isinstance(raw_updated, bool):
                raise InvalidTelemetry("Invalid run status timestamp")
            try:
                updated = float(raw_updated)
            except (TypeError, ValueError, OverflowError):
                raise InvalidTelemetry("Invalid run status timestamp") from None
            if not 0 <= updated < 4102444800:
                raise InvalidTelemetry("Invalid run status timestamp")
            self._status_updated_at = updated
            if self._last_timestamp is not None and updated + 0.001 < self._last_timestamp:
                self._anomalies.add("STATUS_SNAPSHOT_STALE")
        if status.get("turn_exit_reason"):
            self._reason = _safe_reason(status["turn_exit_reason"])

    def explain(self) -> RunExplanation:
        reasons = sorted(self._anomalies)
        inconsistent = bool(self._reported_terminal and self._status and
                            self._status != self._reported_terminal)
        if inconsistent:
            reasons.append("TERMINAL_STATUS_MISMATCH")

        if self._missing_events:
            stop_reason, action = "EVIDENCE_INCOMPLETE", "FETCH_STATUS_AND_REPLAY_EVENTS"
        elif self._pending_tools:
            stop_reason, action = "POSSIBLE_EXTERNAL_EFFECT_UNKNOWN", "RECONCILE_TOOL_EFFECT"
        elif "STATUS_SNAPSHOT_STALE" in self._anomalies:
            stop_reason, action = "STALE_STATUS_SNAPSHOT", "REFETCH_AUTHORITATIVE_STATUS"
        elif self._pending_approvals:
            stop_reason, action = "WAITING_APPROVAL", "WAIT_FOR_AUTHORIZED_APPROVAL"
        elif inconsistent:
            stop_reason, action = "CONTRADICTORY_STATUS", "FETCH_STATUS_AND_REPLAY_EVENTS"
        elif self._status in _TERMINAL:
            if self._status == "completed" and self._tool_errors:
                stop_reason, action = "COMPLETED_WITH_TOOL_ERRORS", "INSPECT_TOOL_FAILURE_RECOVERY"
            else:
                stop_reason, action = (
                    self._reason or self._status.upper(), "NO_RETRY_INSPECT_TERMINAL_RESULT")
        elif self._reported_terminal:
            stop_reason, action = "TERMINAL_EVENT_NOT_STATUS_VERIFIED", "FETCH_RUN_STATUS"
        elif self._status == "waiting_for_approval":
            stop_reason, action = "WAITING_APPROVAL", "WAIT_FOR_AUTHORIZED_APPROVAL"
        elif self._last_event is None:
            stop_reason, action = "NO_EVIDENCE", "CHECK_INGRESS_AND_RUN_ID"
        else:
            stop_reason, action = "NONTERMINAL_OBSERVATION", "CHECK_AUTHORITATIVE_RUN_STATUS"

        # All anomalies are metadata only. Nobody should infer that an
        # unknown external effect can be safely retried.
        return RunExplanation(
            run_id=self.run_id, observed_events=self._event_count,
            highest_seq=self._highest_seq, last_event=self._last_event,
            last_event_timestamp=self._last_timestamp,
            reported_terminal=self._reported_terminal, supplied_status=self._status,
            pending_tool_calls=len(self._pending_tools),
            tool_errors=self._tool_errors,
            pending_approvals=len(self._pending_approvals),
            missing_events=self._missing_events, status_inconsistent=inconsistent,
            stop_reason=stop_reason, next_action=action, evidence=tuple(reasons))


def parse_sse_frames(text: str) -> list[SafeEvent]:
    """Parse bounded native Hermes SSE frames. Comments/keepalives are ignored.

    Returns ONLY allowlisted metadata, never raw stream content.
    Authentication and source authenticity are outside the scope of an
    offline file reader.
    """
    if not isinstance(text, str) or len(text.encode("utf-8")) > _MAX_BYTES:
        raise InvalidTelemetry("SSE export exceeds size limit")
    events: list[SafeEvent] = []
    current_data: list[str] = []
    frame_id: Optional[str] = None
    frame_size = 0

    def flush():
        nonlocal current_data, frame_id, frame_size
        if current_data:
            try:
                payload = json.loads("\n".join(current_data))
            except (json.JSONDecodeError, ValueError):
                raise InvalidTelemetry("Malformed JSON SSE event") from None
            # Frame 'id' is only used if payload lacks an explicit seq.
            event = normalize_run_event(payload, sse_id=frame_id)
            events.append(event)
            if len(events) > _MAX_FRAMES:
                raise InvalidTelemetry("Too many SSE events")
        current_data, frame_id, frame_size = [], None, 0

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r")
        frame_size += len(line)
        if frame_size > _MAX_FRAME_CHARS:
            raise InvalidTelemetry("SSE frame too large")
        if not line:
            flush()
        elif line.startswith(":"):
            continue
        elif line.startswith("id:"):
            frame_id = line[3:].strip()
        elif line.startswith("data:"):
            data = line[5:].lstrip(" ")
            if data == "[DONE]":
                flush()
                continue
            current_data.append(data)
    flush()
    return events


def explain_sse(text: str, run_id: str, status: Optional[dict] = None) -> dict:
    auditor = CausalRunAuditor(run_id)
    for event in parse_sse_frames(text):
        auditor.observe(event)
    if status is not None:
        auditor.observe_status(status)
    return auditor.explain().as_dict()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Hermes run SSE diagnostic")
    parser.add_argument("--run-id", required=True, help="Run ID from /v1/runs")
    parser.add_argument("--events-file", required=True, type=Path,
                        help="Locally saved SSE stream export")
    parser.add_argument("--status-file", type=Path,
                        help="Optional separately fetched run-status JSON")
    opts = parser.parse_args(argv)
    try:
        if opts.events_file.stat().st_size > _MAX_BYTES:
            raise InvalidTelemetry("SSE export exceeds size limit")
        raw_sse = opts.events_file.read_text(encoding="utf-8")
        status = None
        if opts.status_file:
            if opts.status_file.stat().st_size > 64 * 1024:
                raise InvalidTelemetry("Status snapshot is too large")
            status = json.loads(opts.status_file.read_text(encoding="utf-8"))
        report = explain_sse(raw_sse, opts.run_id, status)
    except (InvalidTelemetry, OSError, ValueError, UnicodeError) as exc:
        # The detailed exception may contain sensitive file contents; use
        # class name only and a generic, non-echoing exit.
        print(json.dumps({"error": "INVALID_AUDIT_INPUT", "exception": type(exc).__name__}))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
