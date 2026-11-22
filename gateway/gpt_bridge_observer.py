"""Advisory, metadata-only GPT bridge event validation and sequence observation.

This module is intentionally NOT a task ledger, lock, watchdog, or execution
adapter. It never changes task status and never issues tool calls. State is
process-local and disposable; restore/resubscription must use the authoritative
ledger and its durable cursor before this can be a production observer.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
import json
import re
from typing import Any, Mapping


class InvalidBridgeEvent(ValueError):
    """Invalid or unsafe event. No untrusted input is included in its message."""


_ALLOWED_FIELDS = frozenset({
    "schema_version", "event_id", "source", "producer_id", "source_event_seq",
    "run_id", "task_id", "attempt_id", "agent_id", "lease_fence",
    "trace_id", "span_id", "parent_span_id", "causation_event_id",
    "occurred_at_utc", "observed_at_utc", "kind", "state_from", "state_to",
    "reason_code", "target_revision", "effect_key", "evidence_refs", "trust_level",
})
_REQUIRED = frozenset({
    "schema_version", "event_id", "producer_id", "source_event_seq",
    "run_id", "task_id", "attempt_id", "kind", "trace_id", "span_id",
    "occurred_at_utc", "observed_at_utc", "trust_level",
})
_EVENT_KINDS = frozenset({
    "task.received", "task.planned", "task.claimed", "task.blocked",
    "task.retry_scheduled", "task.cancel_requested", "task.completed",
    "worker.started", "worker.heartbeat", "worker.lease_expired",
    "model.requested", "model.responded", "model.throttled",
    "tool.intent", "tool.effect.reserved", "tool.effect.acknowledged",
    "tool.effect.unknown", "approval.requested", "approval.granted",
    "approval.denied", "verifier.started", "verifier.completed",
    "bridge.connected", "bridge.disconnected", "observer.gap_detected",
    "diagnostic.classified",
})
_TRUST_LEVELS = frozenset({"adapter_observed", "source_asserted", "verifier_attested"})
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_TRACE = re.compile(r"^[0-9a-f]{32}$")
_SPAN = re.compile(r"^[0-9a-f]{16}$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_REV = re.compile(r"^(?:[0-9a-f]{40}|sha256:[0-9a-f]{64})$")
_REASON = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


def _token(value: Any, limit: int = 128) -> bool:
    return type(value) is str and len(value) <= limit and bool(_TOKEN.fullmatch(value))


def _utc(value: Any) -> bool:
    if type(value) is not str or len(value) > 40:
        return False
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.tzinfo is not None and dt.utcoffset() is not None and dt.utcoffset().total_seconds() == 0
    except (ValueError, TypeError, OverflowError):
        return False


def validate_event(raw: Mapping[str, Any], *, max_bytes: int = 4096) -> dict[str, Any]:
    """Validate closed v1 metadata envelope; never log or echo rejected values.

    The caller MUST authenticate the producer independently. A JSON envelope is
    not proof of authorization, a verifier signature, or an external effect.
    """
    if not isinstance(raw, Mapping) or max_bytes < 256:
        raise InvalidBridgeEvent("invalid_envelope")
    if _REQUIRED - raw.keys() or raw.keys() - _ALLOWED_FIELDS:
        raise InvalidBridgeEvent("unsupported_event_shape")
    try:
        encoded = json.dumps(raw, ensure_ascii=False, allow_nan=False,
                             separators=(",", ":"))
    except (TypeError, ValueError, OverflowError):
        raise InvalidBridgeEvent("invalid_event_encoding") from None
    if len(encoded.encode("utf-8")) > max_bytes:
        raise InvalidBridgeEvent("event_too_large")
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise InvalidBridgeEvent("unsupported_schema_version")
    if not (type(raw["event_id"]) is str and _UUID.fullmatch(raw["event_id"])):
        raise InvalidBridgeEvent("invalid_event_id")
    for name in ("producer_id", "run_id", "task_id", "attempt_id"):
        if not _token(raw[name]):
            raise InvalidBridgeEvent("invalid_identity")
    seq = raw["source_event_seq"]
    if type(seq) is not int or seq < 1 or seq > 2**63 - 1:
        raise InvalidBridgeEvent("invalid_sequence")
    if type(raw["kind"]) is not str or raw["kind"] not in _EVENT_KINDS:
        raise InvalidBridgeEvent("unsupported_event_kind")
    if type(raw["trust_level"]) is not str or raw["trust_level"] not in _TRUST_LEVELS:
        raise InvalidBridgeEvent("unsupported_trust_level")
    for key, pattern, length in (("trace_id", _TRACE, 32), ("span_id", _SPAN, 16)):
        value = raw[key]
        if type(value) is not str or len(value) != length or set(value) == {"0"} or not pattern.fullmatch(value):
            raise InvalidBridgeEvent("invalid_trace_context")
    for time_key in ("occurred_at_utc", "observed_at_utc"):
        if not _utc(raw[time_key]):
            raise InvalidBridgeEvent("invalid_timestamp")
    for key in ("parent_span_id",):
        if key in raw and raw[key] is not None and (type(raw[key]) is not str or not _SPAN.fullmatch(raw[key]) or set(raw[key]) == {"0"}):
            raise InvalidBridgeEvent("invalid_parent_span")
    cause = raw.get("causation_event_id")
    if cause is not None and (type(cause) is not str or not _UUID.fullmatch(cause) or cause == raw["event_id"]):
        raise InvalidBridgeEvent("invalid_causation")
    for key in ("agent_id", "source", "effect_key"):
        if key in raw and raw[key] is not None and not _token(raw[key]):
            raise InvalidBridgeEvent("invalid_metadata_token")
    for key in ("state_from", "state_to"):
        if key in raw and raw[key] is not None and not _token(raw[key], 64):
            raise InvalidBridgeEvent("invalid_state")
    if "lease_fence" in raw and (type(raw["lease_fence"]) is not int or not 0 <= raw["lease_fence"] < 2**63):
        raise InvalidBridgeEvent("invalid_fence")
    if raw.get("reason_code") is not None and (type(raw["reason_code"]) is not str or not _REASON.fullmatch(raw["reason_code"])):
        raise InvalidBridgeEvent("invalid_reason_code")
    if raw.get("target_revision") is not None and (type(raw["target_revision"]) is not str or not _REV.fullmatch(raw["target_revision"])):
        raise InvalidBridgeEvent("invalid_target_revision")
    evidence = raw.get("evidence_refs", [])
    if type(evidence) is not list or len(evidence) > 16 or any(type(e) is not str or not _SHA256.fullmatch(e) for e in evidence):
        raise InvalidBridgeEvent("invalid_evidence_reference")
    return dict(raw)


@dataclass(frozen=True)
class Observation:
    accepted: bool
    code: str
    producer_id: str | None = None
    contiguous_through: int | None = None
    pending_gap: tuple[int, int] | None = None
    missing_causal_parent: bool = False


@dataclass
class _ProducerCursor:
    contiguous: int = 0
    ahead: dict[int, str] = field(default_factory=dict)


class ReadOnlyEventObserver:
    """Bounded process-local advisory sequence observer.

    No durable task state, no retries and no inferred worker-death decisions.
    Duplicate replay outside bounded cache is 'stale_unverifiable', not success.
    Producer epochs must use distinct producer IDs; sequence starts at 1.
    """

    def __init__(self, *, max_producers: int = 128, max_reorder: int = 128,
                 max_recent: int = 8192, max_event_bytes: int = 4096):
        if min(max_producers, max_reorder, max_recent, max_event_bytes) <= 0:
            raise ValueError("limits must be positive")
        self.max_producers = max_producers
        self.max_reorder = max_reorder
        self.max_recent = max_recent
        self.max_event_bytes = max_event_bytes
        self._producers: dict[str, _ProducerCursor] = {}
        self._recent: OrderedDict[str, tuple[str, int]] = OrderedDict()
        self._recent_seq: dict[tuple[str, int], str] = {}
        self._unresolved: dict[str, set[str]] = {}

    def ingest(self, raw: Mapping[str, Any]) -> Observation:
        try:
            event = validate_event(raw, max_bytes=self.max_event_bytes)
        except InvalidBridgeEvent as exc:
            return Observation(False, str(exc))
        producer, seq, event_id = (event["producer_id"], event["source_event_seq"], event["event_id"])
        cursor = self._producers.get(producer)
        if cursor is None:
            if len(self._producers) >= self.max_producers:
                return Observation(False, "producer_capacity")
            cursor = _ProducerCursor()
        prior = self._recent.get(event_id)
        if prior is not None:
            if prior == (producer, seq):
                return Observation(False, "duplicate_event", producer, cursor.contiguous)
            return Observation(False, "event_id_collision", producer, cursor.contiguous)
        old_at_seq = self._recent_seq.get((producer, seq))
        if old_at_seq is not None:
            return Observation(False, "sequence_collision", producer, cursor.contiguous)
        if seq <= cursor.contiguous:
            return Observation(False, "stale_unverifiable", producer, cursor.contiguous)
        if seq - cursor.contiguous > self.max_reorder:
            return Observation(False, "reorder_window_exceeded", producer, cursor.contiguous)
        if len(self._recent) >= self.max_recent and event.get("causation_event_id") is not None and event["causation_event_id"] not in self._recent and sum(map(len, self._unresolved.values())) >= self.max_recent:
            return Observation(False, "causal_capacity", producer, cursor.contiguous)
        # All structural/sequence checks complete: update advisory state now.
        self._producers.setdefault(producer, cursor)
        cursor.ahead[seq] = event_id
        while cursor.contiguous + 1 in cursor.ahead:
            cursor.contiguous += 1
            del cursor.ahead[cursor.contiguous]
        self._recent[event_id] = (producer, seq)
        self._recent_seq[(producer, seq)] = event_id
        while len(self._recent) > self.max_recent:
            old_event_id, old_identity = self._recent.popitem(last=False)
            self._recent_seq.pop(old_identity, None)
            # An evicted parent is not proof it never happened; retain only
            # bounded, explicitly incomplete causal observation state.
            self._unresolved.pop(old_event_id, None)
        self._unresolved.pop(event_id, None)
        cause = event.get("causation_event_id")
        missing_parent = cause is not None and cause not in self._recent
        if missing_parent:
            self._unresolved.setdefault(cause, set()).add(event_id)
        gap = (cursor.contiguous + 1, min(cursor.ahead) - 1) if cursor.ahead else None
        return Observation(True, "gap_suspected" if gap else "observed", producer,
                           cursor.contiguous, gap, missing_parent)

    def snapshot(self) -> dict[str, Any]:
        """Safe metadata-only view; not authoritative or durable."""
        return {
            "schema_version": 1,
            "kind": "advisory_event_observer",
            "producers": len(self._producers),
            "recent_events": len(self._recent),
            "out_of_order_events": sum(len(p.ahead) for p in self._producers.values()),
            "unresolved_causal_links": sum(len(v) for v in self._unresolved.values()),
            "status": "partial_observation",
        }
