"""Offline, side-effect-free diagnosis of Hermes ↔ GPT bridge event traces.

This is an *observer*, not an executor, lease manager, or a source of trusted
verification. Events from an extension or LLM are untrusted until authenticated
by a collector. Never make an automated retry or approval decision from this
module's findings alone.

Each JSONL event follows the SDD's v1 envelope. No text prompts, cookies,
responses, URLs, or token-bearing headers are accepted into the schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import re
from typing import Iterable

SCHEMA_VERSION = 1
MAX_LINE_BYTES = 16_384
MAX_EVENTS = 100_000
MAX_TOTAL_BYTES = 64 * 1024 * 1024
_STABLE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$")
_HEX_SHA = re.compile(r"^[0-9a-fA-F]{40,64}$")
_FIELDS = frozenset({
    "schema_version", "event_id", "run_id", "attempt_id", "emitter_id", "seq",
    "kind", "observed_at", "operation_id", "revision", "fence", "reason_code",
    "http_status", "retry_after_seconds", "receipt_digest",
})
_KINDS = frozenset({
    "run.created", "run.started", "run.completed", "run.failed", "run.cancelled",
    "worker.heartbeat", "worker.lease_granted", "worker.lease_revoked",
    "bridge.request_dispatched", "bridge.response_received", "bridge.response_timed_out",
    "bridge.transport_disconnected", "bridge.transport_reconnected",
    "browser.tab_detached", "browser.tab_attached", "browser.service_worker_started", "browser.service_worker_suspended",
    "provider.request_accepted", "provider.response_completed", "provider.rate_limited", "provider.auth_failed",
    "effect.reserved", "effect.acknowledged", "effect.reconciled",
    "artifact.committed", "verification.passed", "verification.failed",
    "operator.approval_pending", "operator.approval_granted", "operator.approval_denied",
})
_TERMINAL = frozenset({"run.completed", "run.failed", "run.cancelled"})
_REASON_CODES = frozenset({
    "UNKNOWN", "NETWORK_TIMEOUT", "TRANSPORT_LOST", "PROVIDER_RATE_LIMIT",
    "PROVIDER_QUOTA", "AUTH_FAILURE", "USER_CANCELLED", "TOOL_FAILED",
    "WORKER_CRASH", "LEASE_EXPIRED", "SESSION_REVOKED", "TAB_DETACHED",
    "SERVICE_WORKER_SUSPENDED", "VERIFICATION_FAILED", "APPROVAL_DENIED",
    "OUTCOME_AMBIGUOUS", "STORAGE_UNAVAILABLE",
})



class TraceError(ValueError):
    """Invalid or unsafe input event; includes line number, never raw content."""


@dataclass(frozen=True)
class Event:
    schema_version: int
    event_id: str
    run_id: str
    attempt_id: str
    emitter_id: str
    seq: int
    kind: str
    observed_at: datetime
    operation_id: str | None = None
    revision: str | None = None
    fence: int | None = None
    reason_code: str | None = None
    http_status: int | None = None
    retry_after_seconds: int | None = None
    receipt_digest: str | None = None

    @classmethod
    def parse(cls, raw: object, *, line: int = 0) -> "Event":
        loc = f"line {line}: " if line else ""
        if not isinstance(raw, dict):
            raise TraceError(loc + "expected JSON object")
        unknown = set(raw) - _FIELDS
        if unknown:
            # Deliberately do not echo potentially sensitive key names or values.
            raise TraceError(loc + "unexpected field(s); strict metadata-only schema")
        required = ("schema_version", "event_id", "run_id", "attempt_id", "emitter_id", "seq", "kind", "observed_at")
        if any(k not in raw for k in required):
            raise TraceError(loc + "missing required event field")
        if type(raw["schema_version"]) is not int or raw["schema_version"] != SCHEMA_VERSION:
            raise TraceError(loc + "unsupported schema version")
        for k in ("event_id", "run_id", "attempt_id", "emitter_id"):
            if not isinstance(raw[k], str) or not _STABLE_ID.fullmatch(raw[k]):
                raise TraceError(loc + f"invalid {k}")
        if not isinstance(raw["kind"], str) or raw["kind"] not in _KINDS:
            raise TraceError(loc + "unknown event kind")
        if raw["kind"] in {"effect.reserved", "effect.acknowledged", "effect.reconciled",
                            "bridge.request_dispatched", "bridge.response_received",
                            "bridge.response_timed_out", "provider.request_accepted",
                            "provider.response_completed"} and not raw.get("operation_id"):
            raise TraceError(loc + "operation_id is required for causal operation events")
        for k in ("operation_id", "reason_code"):
            v = raw.get(k)
            if v is not None and (not isinstance(v, str) or not _STABLE_ID.fullmatch(v)):
                raise TraceError(loc + f"invalid {k}")
        if raw.get("reason_code") is not None and raw["reason_code"] not in _REASON_CODES:
            raise TraceError(loc + "unknown reason code (must be a normalized enum)")
        if type(raw["seq"]) is not int or raw["seq"] < 1:
            raise TraceError(loc + "seq must be a positive integer")
        stamp = raw["observed_at"]
        if not isinstance(stamp, str) or len(stamp) > 48:
            raise TraceError(loc + "invalid observed_at")
        try:
            dt = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError as e:
            raise TraceError(loc + "invalid observed_at") from e
        if dt.tzinfo is None or dt.utcoffset() != timezone.utc.utcoffset(dt):
            raise TraceError(loc + "observed_at must be UTC with explicit offset")
        revision = raw.get("revision")
        if revision is not None and (not isinstance(revision, str) or len(revision) not in (40, 64) or not _HEX_SHA.fullmatch(revision)):
            raise TraceError(loc + "revision must be an exact commit/blob SHA")
        receipt = raw.get("receipt_digest")
        if receipt is not None and (not isinstance(receipt, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", receipt)):
            raise TraceError(loc + "receipt_digest must be SHA-256 hex")
        for k in ("fence", "retry_after_seconds"):
            v = raw.get(k)
            if v is not None and (type(v) is not int or v < (1 if k == "fence" else 0)):
                raise TraceError(loc + f"invalid {k}")
        status = raw.get("http_status")
        if status is not None and (type(status) is not int or not 100 <= status <= 599):
            raise TraceError(loc + "invalid http_status")
        return cls(observed_at=dt, **{k: v for k, v in raw.items() if k != "observed_at"})


def load_jsonl(path: str | Path, *, max_events: int = MAX_EVENTS) -> list[Event]:
    """Read bounded metadata-only JSONL without allocating unbounded lines.

    An attacker-controlled newline-free file must not allocate its full length
    before the size check. The total input cap applies before parsing JSON.
    """
    if type(max_events) is not int or not 1 <= max_events <= MAX_EVENTS:
        raise TraceError("max_events outside supported range")
    events: list[Event] = []
    total_bytes = 0
    with Path(path).open("rb") as stream:
        line_num = 0
        while True:
            raw = stream.readline(MAX_LINE_BYTES + 1)
            if not raw:
                break
            line_num += 1
            total_bytes += len(raw)
            if total_bytes > MAX_TOTAL_BYTES:
                raise TraceError("trace exceeds total input size limit")
            if len(raw) > MAX_LINE_BYTES:
                raise TraceError(f"line {line_num}: input exceeds event size limit")
            if not raw.strip():
                continue
            if len(events) >= max_events:
                raise TraceError("trace exceeds maximum event count")
            try:
                event = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as e:
                raise TraceError(f"line {line_num}: invalid JSON or UTF-8") from e
            events.append(Event.parse(event, line=line_num))
    return events


@dataclass(frozen=True)
class Diagnostic:
    run_id: str
    code: str
    severity: str
    evidence: tuple[str, ...]
    recommendation: str
    certainty: str = "observed"  # observed or hypothesis

    def as_dict(self) -> dict:
        return {"run_id": self.run_id, "code": self.code, "severity": self.severity,
                "certainty": self.certainty, "event_ids": list(self.evidence),
                "recommendation": self.recommendation}


_CHANNELS_REQUIRED = frozenset({"websocket", "tab", "service_worker"})
_CHANNELS = {
    "bridge.transport_disconnected": ("websocket", False),
    "bridge.transport_reconnected": ("websocket", True),
    "browser.tab_detached": ("tab", False),
    "browser.tab_attached": ("tab", True),
    "browser.service_worker_suspended": ("service_worker", False),
    "browser.service_worker_started": ("service_worker", True),
}


def _channel_observations(events: Iterable[Event]) -> dict[str, Event]:
    """Most recent reported event *per transport component*.

    This is observational only. Reconnecting a WebSocket never re-authorizes a
    detached tab. A service worker awakening cannot resurrect a tab lease.
    Multiple independent emitters' timestamp ordering is only an approximation
    until a trusted collector assigns ordered ingestion offsets.
    """
    last_by_channel: dict[str, Event] = {}
    for e in events:
        if e.kind not in _CHANNELS:
            continue
        name, connected = _CHANNELS[e.kind]
        old = last_by_channel.get(name)
        if old is None or (e.observed_at, not connected, e.emitter_id, e.seq) > (
                old.observed_at, not _CHANNELS[old.kind][1], old.emitter_id, old.seq):
            last_by_channel[name] = e
    return last_by_channel


def analyze(events: Iterable[Event], *, now: datetime | None = None,
            stale_after_seconds: int = 120) -> list[Diagnostic]:
    """Diagnose trace invariants without taking actions or interpreting DOM content.

    now must be a trusted UTC collector clock. A silence finding is a *hypothesis*,
    never proof of timeout or permission to replay an external operation.
    """
    if type(stale_after_seconds) is not int or stale_after_seconds < 1:
        raise ValueError("stale_after_seconds must be positive")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() != timezone.utc.utcoffset(now):
        raise ValueError("now must be timezone-aware UTC")
    grouped: dict[str, list[Event]] = {}
    for ev in events:
        if not isinstance(ev, Event):
            raise TypeError("analyze expects validated Event objects")
        grouped.setdefault(ev.run_id, []).append(ev)
    result: list[Diagnostic] = []
    for run_id, group in sorted(grouped.items()):
        # Cross-emitter arrival order is not a causal order. Only local seq is.
        ordered = sorted(group, key=lambda e: (e.observed_at, e.emitter_id, e.seq, e.event_id))
        seen: dict[tuple[str, str], dict[int, Event]] = {}
        by_event_id: dict[str, Event] = {}
        unique: list[Event] = []
        for ev in ordered:
            eid_key = ev.event_id
            existing = by_event_id.get(eid_key)
            if existing is not None:
                if existing != ev:
                    result.append(Diagnostic(run_id, "EVENT_ID_COLLISION", "critical", (existing.event_id, ev.event_id),
                                             "Quarantine conflicting event; reconcile against authenticated source."))
                continue  # byte-identical duplicate delivery is not a second event
            by_event_id[eid_key] = ev
            source = (ev.attempt_id, ev.emitter_id)
            pos = seen.setdefault(source, {})
            other = pos.get(ev.seq)
            if other is not None:
                result.append(Diagnostic(run_id, "SEQUENCE_CONFLICT", "critical", (other.event_id, ev.event_id),
                                         "Reject conflicting emitter sequence; investigate competing writers."))
            else:
                pos[ev.seq] = ev
            unique.append(ev)
        for (_attempt, _emitter), seqmap in seen.items():
            seqs = sorted(seqmap)
            # Some stored artifacts may be partial; report gaps as uncertain, not data loss fact.
            if seqs and (seqs[0] != 1 or seqs[-1] - seqs[0] + 1 != len(seqs)):
                result.append(Diagnostic(run_id, "SEQUENCE_GAP", "warning", tuple(seqmap[x].event_id for x in seqs[:3]),
                                         "Fetch missing events from authoritative collector; do not infer order from timestamps.", "hypothesis"))
        # A stale fence is meaningful *within one run*, independent of emitter clock skew.
        grants = [e for e in unique if e.kind == "worker.lease_granted" and e.fence is not None]
        if grants:
            max_fence = max(e.fence for e in grants)
            latest_grant = max((e for e in grants if e.fence == max_fence), key=lambda e: e.observed_at)
            for ev in unique:
                if ev.fence is not None and ev.fence < max_fence and ev.kind in {
                    "effect.acknowledged", "effect.reconciled", "artifact.committed", "verification.passed", "run.completed"
                } and ev.observed_at >= latest_grant.observed_at:
                    result.append(Diagnostic(run_id, "STALE_FENCE_WRITE", "critical", (latest_grant.event_id, ev.event_id),
                                             "Reject stale worker's completion and verify fencing at every effect gateway."))
        reservations: dict[str, list[Event]] = {}
        for e in unique:
            if e.kind == "effect.reserved" and e.operation_id:
                reservations.setdefault(e.operation_id, []).append(e)
        for op_id, entries in sorted(reservations.items()):
            if len(entries) > 1:
                result.append(Diagnostic(run_id, "DUPLICATE_EFFECT_RESERVATION", "critical",
                                         tuple(e.event_id for e in entries),
                                         "Quarantine duplicate reservations; verify idempotency key and side effects."))
        reserved = {op: entries[-1] for op, entries in reservations.items()}
        closures = [e for e in unique if e.kind in {"effect.acknowledged", "effect.reconciled"} and e.operation_id]
        # A statement of success without a receipt digest is not confirmation.
        # The trusted collector must still authenticate any supplied digest.
        closed = {e.operation_id for e in closures if e.receipt_digest}
        for ev in closures:
            if not ev.receipt_digest:
                result.append(Diagnostic(run_id, "EFFECT_CLOSURE_NO_RECEIPT", "critical", (ev.event_id,),
                                         "Preserve needs_reconciliation until a trusted receipt/read-back digest exists."))
            if ev.operation_id not in reserved:
                result.append(Diagnostic(run_id, "ORPHAN_EFFECT_CLOSURE", "critical", (ev.event_id,),
                                         "Do not trust effect acknowledgement without matching reservation."))
        for op_id, ev in sorted(reserved.items()):
            if op_id not in closed:
                result.append(Diagnostic(run_id, "UNKNOWN_EXTERNAL_OUTCOME", "critical", (ev.event_id,),
                                         "Do NOT resend. Read provider receipt or state, then reconcile the reserved effect."))
        dispatched = {e.operation_id: e for e in unique if e.kind == "bridge.request_dispatched" and e.operation_id}
        answered = {e.operation_id for e in unique if e.kind in {"bridge.response_received", "provider.response_completed"} and e.operation_id}
        for op_id, ev in sorted(dispatched.items()):
            if op_id not in answered:
                result.append(Diagnostic(run_id, "UNCONFIRMED_BRIDGE_REQUEST", "warning", (ev.event_id,),
                                         "Check provider-side request status/receipt before retry; do not treat missing UI reply as failure.", "hypothesis"))
        terminal = [e for e in unique if e.kind in _TERMINAL]
        completions = [e for e in unique if e.kind == "run.completed"]
        verified_revs = {e.revision for e in unique if e.kind == "verification.passed" and e.revision}
        artifacts = {e.revision for e in unique if e.kind == "artifact.committed" and e.revision}
        for ev in completions:
            if ev.revision not in verified_revs or ev.revision not in artifacts:
                result.append(Diagnostic(run_id, "COMPLETED_WITHOUT_MATCHED_EVIDENCE", "critical", (ev.event_id,),
                                         "Require artifact and independent verifier success for the exact revision."))
        if any(e.kind == "provider.auth_failed" for e in unique):
            e = next(e for e in reversed(ordered) if e.kind == "provider.auth_failed")
            result.append(Diagnostic(run_id, "AUTH_BLOCKED", "error", (e.event_id,),
                                     "Stop automated dispatch; request authorized account recovery. Never log credentials."))
        if any(e.kind == "provider.rate_limited" and e.retry_after_seconds is None for e in unique):
            e = next(e for e in reversed(ordered) if e.kind == "provider.rate_limited" and e.retry_after_seconds is None)
            result.append(Diagnostic(run_id, "RATE_LIMIT_WITHOUT_BACKOFF_HINT", "warning", (e.event_id,),
                                     "Apply centrally budgeted bounded retry with jitter; inspect provider Retry-After when available."))
        if terminal:
            if len({e.kind for e in terminal}) > 1:
                result.append(Diagnostic(run_id, "TERMINAL_STATE_CONFLICT", "critical", tuple(e.event_id for e in terminal),
                                         "Reconcile authoritative terminal transition; reject narrative-only status changes."))
        elif unique:
            last = max(unique, key=lambda e: e.observed_at)
            elapsed = (now - last.observed_at).total_seconds()
            if elapsed >= stale_after_seconds:
                result.append(Diagnostic(run_id, "PROGRESS_SILENCE", "warning", (last.event_id,),
                                         "Probe bridge/worker/extension independently; silence alone is not proof of job failure.", "hypothesis"))
            # Record currently unresolved disconnect; no auto-retry implied.
            unavailable = [e for e in _channel_observations(unique).values() if not _CHANNELS[e.kind][1]]
            if unavailable:
                result.append(Diagnostic(run_id, "SESSION_CHANNEL_UNAVAILABLE", "warning",
                                         tuple(e.event_id for e in sorted(unavailable, key=lambda e: e.kind)),
                                         "Inspect each disconnected channel independently; reattach a tab only with user authorization and reconcile in-flight operations.", "hypothesis"))
        # Stable presentation for deterministic diff-based monitoring.
    return sorted(result, key=lambda d: (d.run_id, d.code, d.evidence))


@dataclass(frozen=True)
class RunSnapshot:
    """Orthogonal *observations*, not a claim that an agent really finished.

    In particular `execution=reported_completed` is deliberately weaker than
    verified success. Collector authentication and trusted evidence are external.
    """
    run_id: str
    execution: str
    transport: str
    provider: str
    evidence: str
    effects: str
    last_event_id: str
    last_observed_at: str
    blockers: tuple[str, ...]

    def as_dict(self) -> dict:
        return {"run_id": self.run_id, "execution": self.execution,
                "transport": self.transport, "provider": self.provider,
                "evidence": self.evidence, "effects": self.effects,
                "last_event_id": self.last_event_id, "last_observed_at": self.last_observed_at,
                "blockers": list(self.blockers)}


def summarize(events: Iterable[Event], *, now: datetime | None = None,
              stale_after_seconds: int = 120) -> list[RunSnapshot]:
    """Four-axis run projection; useful for showing 'what stopped' without guessing.

    This function never authorizes resume/retry. It returns only recorded signals.
    Events from a browser or LLM cannot become trusted solely by naming their
    emitter 'verifier'. A trusted collector and ledger still need to vet them.
    """
    seq = list(events)
    findings = analyze(seq, now=now, stale_after_seconds=stale_after_seconds)
    by_run: dict[str, list[Event]] = {}
    by_blocker: dict[str, set[str]] = {}
    for e in seq:
        by_run.setdefault(e.run_id, []).append(e)
    for f in findings:
        by_blocker.setdefault(f.run_id, set()).add(f.code)
    result: list[RunSnapshot] = []
    for run_id, group in sorted(by_run.items()):
        group = sorted(group, key=lambda e: (e.observed_at, e.emitter_id, e.seq, e.event_id))
        last = group[-1]
        kind_set = {e.kind for e in group}
        terminal = kind_set & _TERMINAL
        if len(terminal) > 1:
            execution = "conflicted"
        elif "run.completed" in terminal:
            execution = "reported_completed"
        elif "run.cancelled" in terminal:
            execution = "cancelled"
        elif "run.failed" in terminal:
            execution = "reported_failed"
        elif "run.started" in kind_set:
            execution = "reported_running"
        elif "run.created" in kind_set:
            execution = "queued"
        else:
            execution = "unknown"
        channel_events = _channel_observations(group)
        if not channel_events:
            transport = "unobserved"
        elif any(not _CHANNELS[e.kind][1] for e in channel_events.values()):
            transport = "reported_unavailable"
        elif all(name in channel_events for name in _CHANNELS_REQUIRED):
            transport = "reported_connected"
        else:
            transport = "partially_observed_connected"
        provider_events = [e for e in group if e.kind.startswith("provider.")]
        provider_status = {
            "provider.auth_failed": "reported_auth_failure",
            "provider.rate_limited": "reported_rate_limited",
            "provider.request_accepted": "reported_accepted",
            "provider.response_completed": "reported_response_completed",
        }
        provider = provider_status[provider_events[-1].kind] if provider_events else "unobserved"
        finished = [e for e in group if e.kind == "run.completed"]
        required_rev = finished[-1].revision if finished else None
        verified = {e.revision for e in group if e.kind == "verification.passed" and e.revision}
        committed = {e.revision for e in group if e.kind == "artifact.committed" and e.revision}
        if required_rev and required_rev in verified and required_rev in committed:
            evidence = "reported_revision_matched"
        elif finished:
            evidence = "missing_or_mismatched"
        elif verified:
            evidence = "reported_verification_unfinalized"
        else:
            evidence = "unobserved"
        blockers = tuple(sorted(by_blocker.get(run_id, set())))
        effects = "needs_reconciliation" if any(b in blockers for b in ("UNKNOWN_EXTERNAL_OUTCOME", "DUPLICATE_EFFECT_RESERVATION", "EFFECT_CLOSURE_NO_RECEIPT", "ORPHAN_EFFECT_CLOSURE")) else "no_unresolved_reservation_observed"
        result.append(RunSnapshot(run_id, execution, transport, provider, evidence, effects,
                                  last.event_id, last.observed_at.isoformat(), blockers))
    return result
