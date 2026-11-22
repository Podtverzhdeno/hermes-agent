"""Read-only, fail-closed diagnostics for a *proposed* GPT Bridge event contract.

No event in this module is trusted to change a task, tool, approval, or retry.
The authority is the Hermes/Autopilot ledger (outside this module). This is an
independent, pure-stdlib audit of redacted metadata exports, not live telemetry.

Contract source: docs/gpt_bridge/SDD.md (draft PR #7, 2026-11-22).

Usage::

    python -m gateway.gpt_bridge_event_audit metadata.ndjson
    python -m gateway.gpt_bridge_event_audit metadata.ndjson --output report.json

The CLI emits *only* allowlisted identifiers, reason codes and counts. Never
supply raw model messages, credentials or tool arguments as input.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, Iterable, Mapping
from uuid import UUID

SCHEMA_VERSION = 1
MAX_EVENTS = 50_000
MAX_EVENT_BYTES = 4_096
MAX_INPUT_LINE_BYTES = 4_096
MAX_EVIDENCE_REFS = 16
MAX_IDENTIFIER_LENGTH = 128

# Closed metadata allowlist; expanding it requires a versioned schema/security
# review. In particular raw ``payload``, ``prompt`` and ``arguments`` are denied.
ALLOWED_KEYS = frozenset({
    "schema_version", "event_id", "source", "producer_id", "source_event_seq",
    "run_id", "task_id", "attempt_id", "agent_id", "lease_fence",
    "trace_id", "span_id", "parent_span_id", "causation_event_id",
    "occurred_at_utc", "observed_at_utc", "kind", "state_from", "state_to",
    "reason_code", "target_revision", "effect_key", "evidence_refs",
    "trust_level",
})
REQUIRED_KEYS = frozenset({
    "schema_version", "event_id", "source", "producer_id", "source_event_seq",
    "run_id", "task_id", "attempt_id", "agent_id", "lease_fence",
    "trace_id", "span_id", "parent_span_id", "causation_event_id",
    "occurred_at_utc", "observed_at_utc", "kind", "state_from", "state_to",
    "reason_code", "target_revision", "effect_key", "evidence_refs",
    "trust_level",
})
EVENT_KINDS = frozenset({
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
SOURCE_KINDS = frozenset({"worker", "gateway", "ledger", "verifier", "bridge",
                          "adapter", "observer", "provider", "github", "mcp", "browser"})
TRUST_LEVELS = frozenset({
    "untrusted", "producer_claimed", "adapter_observed", "trusted_verifier",
    "ledger_committed",
})
_SOURCE_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./:-]{0,127}$")
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")
_TRACE_RE = re.compile(r"^[a-f0-9]{32}$")
_SPAN_RE = re.compile(r"^[a-f0-9]{16}$")
_SHA_RE = re.compile(r"^(?:[a-f0-9]{40}|sha256:[a-f0-9]{64})$")
_STATE_VALUES = frozenset({"queued", "running", "verifying", "succeeded", "retry_wait",
                           "waiting_approval", "needs_reconciliation", "blocked", "failed", "cancelled"})
_REASON_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


class InvalidEvent(ValueError):
    """A metadata record is malformed or could leak sensitive input."""


def _identifier(value: Any, field_name: str, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise InvalidEvent(f"invalid {field_name}")


def _uuid(value: Any, field_name: str, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    if not isinstance(value, str) or len(value) > 48:
        raise InvalidEvent(f"invalid {field_name}")
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise InvalidEvent(f"invalid {field_name}") from exc
    if str(parsed) != value:  # canonical lowercase, hyphenated; stable dedup
        raise InvalidEvent(f"noncanonical {field_name}")


def _optional_state(value: Any, field_name: str) -> None:
    if value is not None:
        _identifier(value, field_name)


def validate_event(raw: Any) -> dict[str, Any]:
    """Validate a metadata-only v1 event, without echoing rejected content.

    A producer identity and its sequence are **claims** until authenticated by
    ingestion; this parser cannot attest to them. ``trace_id`` is never auth.
    """
    if not isinstance(raw, Mapping):
        raise InvalidEvent("event must be an object")
    keys = set(raw)
    if keys - ALLOWED_KEYS:
        raise InvalidEvent("unexpected event metadata field(s)")
    if REQUIRED_KEYS - keys:
        raise InvalidEvent("missing required event metadata field(s)")
    try:
        length = len(json.dumps(raw, separators=(",", ":"), ensure_ascii=False,
                                allow_nan=False).encode("utf-8"))
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
        raise InvalidEvent("event cannot be serialized safely") from exc
    if length > MAX_EVENT_BYTES:
        raise InvalidEvent("event metadata is too large")
    if type(raw["schema_version"]) is not int or raw["schema_version"] != SCHEMA_VERSION:
        raise InvalidEvent("unsupported event schema version")
    for name in ("event_id", "run_id", "task_id", "attempt_id"):
        _uuid(raw[name], name)
    _uuid(raw["causation_event_id"], "causation_event_id", optional=True)
    for name in ("producer_id", "agent_id"):
        _identifier(raw[name], name)
    if not isinstance(raw["source"], str) or raw["source"] not in SOURCE_KINDS:
        raise InvalidEvent("invalid source")
    if (type(raw["source_event_seq"]) is not int or raw["source_event_seq"] < 1
            or raw["source_event_seq"] > 2**63 - 1):
        raise InvalidEvent("invalid source_event_seq")
    if (type(raw["lease_fence"]) is not int or raw["lease_fence"] < 0
            or raw["lease_fence"] > 2**63 - 1):
        raise InvalidEvent("invalid lease_fence")
    if not isinstance(raw["trace_id"], str) or not _TRACE_RE.fullmatch(raw["trace_id"]):
        raise InvalidEvent("invalid trace_id")
    for name in ("span_id", "parent_span_id"):
        if raw[name] is None and name == "parent_span_id":
            continue
        if not isinstance(raw[name], str) or not _SPAN_RE.fullmatch(raw[name]):
            raise InvalidEvent(f"invalid {name}")
    for name in ("occurred_at_utc", "observed_at_utc"):
        if not isinstance(raw[name], str) or not _UTC_RE.fullmatch(raw[name]):
            raise InvalidEvent(f"invalid {name}")
        try:
            timestamp = datetime.fromisoformat(raw[name].replace("Z", "+00:00"))
        except ValueError as exc:
            raise InvalidEvent(f"invalid {name}") from exc
        if timestamp.tzinfo != timezone.utc:
            raise InvalidEvent(f"invalid {name}")
    if not isinstance(raw["kind"], str) or raw["kind"] not in EVENT_KINDS:
        raise InvalidEvent("unsupported event kind")
    for name in ("state_from", "state_to"):
        if raw[name] is not None and (not isinstance(raw[name], str) or raw[name] not in _STATE_VALUES):
            raise InvalidEvent(f"invalid {name}")
    if raw["reason_code"] is not None and (
        not isinstance(raw["reason_code"], str) or not _REASON_RE.fullmatch(raw["reason_code"])
    ):
        raise InvalidEvent("invalid reason_code")
    _optional_state(raw["effect_key"], "effect_key")
    if raw["target_revision"] is not None and (
        not isinstance(raw["target_revision"], str)
        or not _SHA_RE.fullmatch(raw["target_revision"])
    ):
        raise InvalidEvent("invalid target_revision")
    refs = raw["evidence_refs"]
    if not isinstance(refs, list) or len(refs) > MAX_EVIDENCE_REFS:
        raise InvalidEvent("invalid evidence_refs")
    for ref in refs:
        _identifier(ref, "evidence_ref")
    if not isinstance(raw["trust_level"], str) or raw["trust_level"] not in TRUST_LEVELS:
        raise InvalidEvent("unsupported trust_level")
    if raw["kind"].startswith("tool.effect.") and raw["effect_key"] is None:
        raise InvalidEvent("effect lifecycle event requires effect_key")
    # Keep only metadata to avoid retaining untrusted mapping subclasses.
    return {k: raw[k] for k in ALLOWED_KEYS}


@dataclass
class AuditReport:
    """Metadata-only hints; **never** an authoritative task/effect state."""

    accepted: int = 0
    duplicate_replays: int = 0
    rejected: int = 0
    # Unique diagnostic codes: events and status are not considered trustworthy
    # merely because they passed schema validation.
    problems: list[dict[str, Any]] = field(default_factory=list)
    tasks: dict[str, dict[str, Any]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "authority": "read_only_diagnostics_not_task_truth",
            "accepted": self.accepted,
            "duplicate_replays": self.duplicate_replays,
            "rejected": self.rejected,
            "problems": self.problems,
            "tasks": self.tasks,
        }


class CausalAuditor:
    """Bounded reducer for metadata snapshots, including out-of-order arrival.

    ``summarize`` is a view over all ingested evidence; never turn it into a
    scheduler or an automatic retry engine. This object is not thread-safe;
    feed from one collector or synchronize externally.
    """

    def __init__(self, max_events: int = MAX_EVENTS):
        if type(max_events) is not int or not 1 <= max_events <= MAX_EVENTS:
            raise ValueError("invalid max_events")
        self.max_events = max_events
        self.events: dict[str, dict[str, Any]] = {}
        self.by_producer: dict[str, dict[int, str]] = defaultdict(dict)
        self.duplicate_replays = 0
        self.reject_counts: dict[str, int] = defaultdict(int)

    @staticmethod
    def _digest(event: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(event, sort_keys=True, separators=(",", ":"),
                                         ensure_ascii=False).encode("utf-8")).hexdigest()

    def ingest(self, raw: Any) -> None:
        try:
            event = validate_event(raw)
        except InvalidEvent as exc:
            self.reject_counts[str(exc)] += 1
            return
        eid = event["event_id"]
        if eid in self.events:
            if self._digest(self.events[eid]) == self._digest(event):
                self.duplicate_replays += 1
            else:
                self.reject_counts["EVENT_ID_COLLISION"] += 1
            return
        seq_map = self.by_producer[event["producer_id"]]
        prior_eid = seq_map.get(event["source_event_seq"])
        if prior_eid is not None:
            self.reject_counts["PRODUCER_SEQUENCE_COLLISION"] += 1
            return
        if len(self.events) >= self.max_events:
            self.reject_counts["EVENT_LIMIT_REACHED"] += 1
            return
        self.events[eid] = event
        seq_map[event["source_event_seq"]] = eid

    def _causal_issues(self) -> list[dict[str, Any]]:
        problems: list[dict[str, Any]] = []
        # Every event has at most one causal parent. A DFS over this graph is
        # linear; avoid recursion to handle 50k-deep chains from 30+ agents.
        visited: set[str] = set()
        for eid, event in self.events.items():
            parent = event["causation_event_id"]
            if parent is not None and parent not in self.events:
                problems.append({"code": "CAUSAL_PARENT_UNOBSERVED", "event_id": eid,
                                 "severity": "info", "confidence": "partial_snapshot"})
            if parent is not None and parent in self.events:
                ancestor = self.events[parent]
                if ancestor["task_id"] != event["task_id"]:
                    problems.append({"code": "CROSS_TASK_CAUSATION_REVIEW", "event_id": eid,
                                     "severity": "info", "confidence": "requires_parent_task_context"})
                if (ancestor["producer_id"] == event["producer_id"] and
                        ancestor["source_event_seq"] >= event["source_event_seq"]):
                    problems.append({"code": "CAUSAL_SEQUENCE_CONTRADICTION", "event_id": eid,
                                     "severity": "error", "confidence": "metadata_observed"})
            if eid in visited:
                continue
            order: list[str] = []
            local: set[str] = set()
            cursor: str | None = eid
            while cursor is not None and cursor in self.events and cursor not in visited:
                if cursor in local:
                    problems.append({"code": "CAUSAL_CYCLE", "event_id": cursor,
                                     "severity": "error", "confidence": "metadata_observed"})
                    break
                order.append(cursor)
                local.add(cursor)
                cursor = self.events[cursor]["causation_event_id"]
            visited.update(order)
        return problems

    def summarize(self) -> AuditReport:
        report = AuditReport(accepted=len(self.events),
                             duplicate_replays=self.duplicate_replays,
                             rejected=sum(self.reject_counts.values()))
        report.problems.extend({"code": key, "count": count, "severity": "error"}
                               for key, count in sorted(self.reject_counts.items()))
        # A sequence gap is only a suspicion until producer retransmission and
        # a durable watermark prove absence. Do NOT infer missing 1..first-1.
        for producer, seqmap in sorted(self.by_producer.items()):
            seqs = sorted(seqmap)
            missing = sum(b - a - 1 for a, b in zip(seqs, seqs[1:]))
            if missing:
                report.problems.append({"code": "POSSIBLE_SOURCE_GAP",
                                        "producer_id_digest": "sha256:" + hashlib.sha256(producer.encode("utf-8")).hexdigest()[:20],
                                        "missing_count": missing,
                                        "severity": "warning", "confidence": "unconfirmed"})
        report.problems.extend(self._causal_issues())
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for e in self.events.values():
            grouped[e["task_id"]].append(e)
        for task_id, events in sorted(grouped.items()):
            task_flags: set[str] = set()
            dispositions: set[str] = set()
            unresolved: list[str] = []
            effect_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
            observed_complete = False
            claimed_verifier = False
            for e in events:
                kind = e["kind"]
                if kind.startswith("tool.effect."):
                    effect_groups[e["effect_key"]].append(e)
                if kind == "task.completed":
                    observed_complete = True
                if kind == "verifier.completed":
                    # A self-reported trust_level is not an authenticated proof.
                    # This offline tool has no adapter signature or CI receipt.
                    claimed_verifier = True
                if kind == "task.blocked" and e["reason_code"]:
                    dispositions.add(e["reason_code"])
                if kind == "model.throttled":
                    task_flags.add("MODEL_THROTTLED_OBSERVED")
                if kind == "approval.denied":
                    task_flags.add("APPROVAL_DENIED_OBSERVED")
                if kind == "worker.lease_expired":
                    task_flags.add("LEASE_EXPIRY_OBSERVED")
                if kind == "bridge.disconnected":
                    task_flags.add("BRIDGE_DISCONNECTED_OBSERVED")
            for effect_key, effect_events in sorted(effect_groups.items()):
                reservations = [e for e in effect_events if e["kind"] == "tool.effect.reserved"]
                acks = [e for e in effect_events if e["kind"] == "tool.effect.acknowledged"]
                unknowns = [e for e in effect_events if e["kind"] == "tool.effect.unknown"]
                fences = {e["lease_fence"] for e in effect_events}
                if len(fences) > 1:
                    task_flags.add("EFFECT_FENCE_DIVERGENCE")
                if unknowns or (reservations and not acks):
                    task_flags.add("EFFECT_OUTCOME_UNKNOWN")
                    # A stable effect key might carry business content; publish
                    # only an irreversible short correlation digest.
                    unresolved.append("sha256:" + hashlib.sha256(effect_key.encode("utf-8")).hexdigest()[:20])
                if acks and not reservations:
                    task_flags.add("EFFECT_ACK_WITHOUT_RESERVATION")
                if acks:
                    # Even a self-labelled "trusted_verifier" is NOT proof.
                    task_flags.add("EFFECT_ACK_NEEDS_AUTHENTICATED_RECEIPT")
                    if not any(e["evidence_refs"] for e in acks):
                        task_flags.add("EFFECT_ACK_PROOF_UNAVAILABLE")
            if observed_complete:
                task_flags.add("COMPLETION_NOT_INDEPENDENTLY_VERIFIED")
            if claimed_verifier:
                task_flags.add("VERIFIER_CLAIM_UNAUTHENTICATED")
            if unresolved:
                dispositions.add("needs_reconciliation")
            # No inference that a task actually stopped: these are reported
            # symptoms/candidates that the authoritative ledger must confirm.
            candidates: set[str] = set(dispositions)
            if "MODEL_THROTTLED_OBSERVED" in task_flags:
                candidates.add("RATE_LIMITED")
            if "APPROVAL_DENIED_OBSERVED" in task_flags:
                candidates.add("POLICY_DENIED")
            if "LEASE_EXPIRY_OBSERVED" in task_flags:
                candidates.add("WORKER_LEASE_LOST")
            if "BRIDGE_DISCONNECTED_OBSERVED" in task_flags:
                candidates.add("BRIDGE_DISCONNECTED")
            next_action = "consult_authoritative_ledger_and_revision_bound_evidence"
            if unresolved:
                next_action = "reconcile_external_receipt_before_retry"
            elif "POLICY_DENIED" in candidates:
                next_action = "verify_approval_binding_and_stop_retries"
            elif "WORKER_LEASE_LOST" in candidates:
                next_action = "read_current_ledger_fence_before_any_work"
            elif "RATE_LIMITED" in candidates:
                next_action = "confirm_retry_after_and_shared_provider_budget"
            elif "BRIDGE_DISCONNECTED" in candidates:
                next_action = "reconnect_observer_only_do_not_replay_task"
            report.tasks[task_id] = {
                "diagnostic_flags": sorted(task_flags),
                "candidate_stop_reasons": sorted(candidates) or ["INSUFFICIENT_EVIDENCE"],
                "reason_confidence": "unverified_metadata_only",
                "blocked_reasons_observed": sorted(dispositions),
                "unknown_effect_keys": unresolved,
                "ledger_state": "not_read_in_this_tool",
                "automatic_retry_allowed": False,
                "next_safe_action": next_action,
                "observed_event_count": len(events),
            }
        return report


def audit_ndjson(lines: Iterable[bytes], *, max_events: int = MAX_EVENTS) -> AuditReport:
    """Read bounded NDJSON metadata and classify syntactic and causal failures."""
    auditor = CausalAuditor(max_events=max_events)
    for line in lines:
        if len(line) > MAX_INPUT_LINE_BYTES:
            auditor.reject_counts["INPUT_LINE_TOO_LARGE"] += 1
            continue
        if not line.strip():
            continue
        try:
            # Explicitly reject duplicate JSON keys, which can otherwise hide
            # an earlier auth/metadata key from different parsers.
            def no_duplicates(pairs):
                obj = {}
                for k, v in pairs:
                    if k in obj:
                        raise InvalidEvent("DUPLICATE_JSON_KEY")
                    obj[k] = v
                return obj
            obj = json.loads(line.decode("utf-8"), object_pairs_hook=no_duplicates,
                             parse_constant=lambda x: (_ for _ in ()).throw(InvalidEvent("INVALID_NUMBER")))
        except (UnicodeDecodeError, ValueError, InvalidEvent, RecursionError):
            auditor.reject_counts["MALFORMED_JSON_OR_ENCODING"] += 1
            continue
        auditor.ingest(obj)
    return auditor.summarize()


def _atomic_write_text(path: Path, text: str) -> None:
    """Replace a local report only after flushing it; never append raw input."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=path.parent, prefix=".gpt-audit-",
                                         suffix=".tmp", delete=False) as f:
            tmp_path = f.name
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        if tmp_path is not None and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline read-only GPT Bridge event audit")
    parser.add_argument("metadata_ndjson", type=Path, help="Export of metadata-only v1 event envelopes")
    parser.add_argument("--output", type=Path, help="Atomically replace a metadata-only JSON report")
    args = parser.parse_args(argv)
    with args.metadata_ndjson.open("rb") as f:
        report = audit_ndjson(f)
    output = json.dumps(report.as_dict(), indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output:
        _atomic_write_text(args.output, output)
    else:
        sys.stdout.write(output)
    # Do not call every partial source/cause observation a task failure.
    return 2 if report.rejected else 0


if __name__ == "__main__":
    raise SystemExit(main())
