"""Offline audit for metadata-only Hermes GPT bridge event snapshots.

Trust boundary: inputs are untrusted observations, not instructions/permissions.
This module NEVER executes tools, retries effects, advances a ledger or certifies
that a reported external action actually happened. It does not ingest prompts.

Usage: python -m hermes_observer.audit path/to/events.ndjson
Return codes: 0=no issue in supplied slice, 2=anomaly, 3=incomplete,
4=invalid input. None of these codes establishes production health.
"""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
from datetime import datetime
import json
import re
import sys
from typing import BinaryIO, Iterator
import uuid

MAX_LINE_BYTES = 32_768
MAX_TOTAL_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_EVENTS = 100_000
MAX_FINDINGS = 250
MAX_EVIDENCE_REFS = 16

# Explicit metadata allowlist prevents a new producer from inadvertently
# uploading prompt text, cookies, tokens or tool arguments into a shared log.
FIELDS = frozenset({
    "schema_version", "event_id", "source", "producer_id", "source_event_seq",
    "run_id", "task_id", "attempt_id", "agent_id", "lease_fence",
    "trace_id", "span_id", "parent_span_id", "causation_event_id",
    "occurred_at_utc", "observed_at_utc", "kind", "state_from", "state_to",
    "reason_code", "target_revision", "effect_key", "evidence_refs", "trust_level",
})
REQUIRED = frozenset({
    "schema_version", "event_id", "producer_id", "source_event_seq",
    "task_id", "occurred_at_utc", "kind",
})
KINDS = frozenset("""
task.received task.planned task.claimed task.blocked task.retry_scheduled
 task.cancel_requested task.completed worker.started worker.heartbeat
 worker.lease_expired model.requested model.responded model.throttled
 tool.intent tool.effect.reserved tool.effect.acknowledged tool.effect.unknown
 tool.effect.reconciled approval.requested approval.granted approval.denied
 verifier.started verifier.completed bridge.connected bridge.disconnected
 observer.gap_detected diagnostic.classified
""".split())
STOP_KINDS = frozenset({"task.blocked", "worker.lease_expired", "approval.denied"})
REASON_CODES = frozenset("""
AUTH_EXPIRED POLICY_DENIED RATE_LIMITED PROVIDER_UNAVAILABLE NETWORK_PARTITION
MCP_DISCONNECTED BROWSER_WORKER_SUSPENDED WORKER_LEASE_LOST CONTEXT_EXHAUSTED
BUDGET_EXHAUSTED OUTPUT_SCHEMA_INVALID RESOURCE_CONFLICT CI_REVISION_MISMATCH
EFFECT_OUTCOME_UNKNOWN OBSERVABILITY_GAP UNKNOWN
""".split())
EFFECT_KINDS = frozenset({
    "tool.effect.reserved", "tool.effect.acknowledged", "tool.effect.unknown",
    "tool.effect.reconciled",
})
STATES = frozenset({
    "queued", "running", "verifying", "succeeded", "retry_wait",
    "waiting_approval", "needs_reconciliation", "blocked", "failed", "cancelled",
})
TOKEN = re.compile(r"^[A-Za-z0-9_.:/-]{1,160}$")
HEX32 = re.compile(r"^[0-9a-f]{32}$")
HEX16 = re.compile(r"^[0-9a-f]{16}$")
UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")


class InvalidEvent(ValueError):
    """Error string never contains user input or message contents."""


def _pairs_unique(pairs: list[tuple[str, object]]) -> dict:
    output = {}
    for key, value in pairs:
        if key in output:
            raise InvalidEvent("duplicate JSON field")
        output[key] = value
    return output


def _reject_constant(_value: str) -> object:
    raise InvalidEvent("non-finite JSON number")


def _uuid(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 36:
        return False
    try:
        return str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def _token(value: object, length: int = 160) -> bool:
    return isinstance(value, str) and len(value) <= length and bool(TOKEN.fullmatch(value))


def _utc(value: object) -> bool:
    if not isinstance(value, str) or not UTC.fullmatch(value):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def parse_event(raw: bytes) -> dict:
    """Return validated metadata; reject every non-allowlisted field."""
    if len(raw) > MAX_LINE_BYTES:
        raise InvalidEvent("oversized event line")
    try:
        obj = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs_unique,
                         parse_constant=_reject_constant)
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        if isinstance(exc, InvalidEvent):
            raise
        raise InvalidEvent("invalid UTF-8 or JSON") from None
    if not isinstance(obj, dict):
        raise InvalidEvent("event is not an object")
    if obj.keys() - FIELDS:
        raise InvalidEvent("unapproved metadata field present")
    if REQUIRED - obj.keys():
        raise InvalidEvent("missing required metadata field")
    if type(obj["schema_version"]) is not int or obj["schema_version"] != 1:
        raise InvalidEvent("unsupported schema version")
    for key in ("event_id", "run_id", "task_id", "attempt_id", "causation_event_id"):
        if key in obj and obj[key] is not None and not _uuid(obj[key]):
            raise InvalidEvent("invalid UUID field")
    if not _uuid(obj["event_id"]):
        raise InvalidEvent("missing event identity")
    if not _token(obj["producer_id"], 96):
        raise InvalidEvent("invalid producer identity")
    if type(obj["source_event_seq"]) is not int or obj["source_event_seq"] < 1:
        raise InvalidEvent("invalid producer sequence")
    if not isinstance(obj["kind"], str) or obj["kind"] not in KINDS:
        raise InvalidEvent("unknown event kind")
    # The occurrence timestamp is required AND non-null. A missing optional
    # observation timestamp is allowed, but a null occurrence timestamp is not.
    if not _utc(obj["occurred_at_utc"]):
        raise InvalidEvent("invalid required occurrence timestamp")
    if obj.get("observed_at_utc") is not None and not _utc(obj["observed_at_utc"]):
        raise InvalidEvent("invalid UTC observation timestamp")
    for key, maxlen in (("source", 64), ("agent_id", 96), ("reason_code", 64),
                        ("target_revision", 160), ("effect_key", 160),
                        ("trust_level", 48)):
        if key in obj and obj[key] is not None and not _token(obj[key], maxlen):
            raise InvalidEvent("invalid metadata token")
    if obj.get("reason_code") is not None and (not isinstance(obj["reason_code"], str) or obj["reason_code"] not in REASON_CODES):
        raise InvalidEvent("unknown reason code")
    for key in ("state_from", "state_to"):
        if key in obj and obj[key] is not None and (not isinstance(obj[key], str) or obj[key] not in STATES):
            raise InvalidEvent("invalid task state")
    if "lease_fence" in obj and obj["lease_fence"] is not None:
        if type(obj["lease_fence"]) is not int or obj["lease_fence"] < 0:
            raise InvalidEvent("invalid lease fence")
    for key, pattern in (("trace_id", HEX32), ("span_id", HEX16),
                         ("parent_span_id", HEX16)):
        if key in obj and obj[key] is not None:
            if not isinstance(obj[key], str) or not pattern.fullmatch(obj[key]) or int(obj[key], 16) == 0:
                raise InvalidEvent("invalid trace field")
    if "evidence_refs" in obj:
        refs = obj["evidence_refs"]
        if not isinstance(refs, list) or len(refs) > MAX_EVIDENCE_REFS or any(not _token(x) for x in refs):
            raise InvalidEvent("invalid evidence reference list")
    if obj["kind"].startswith("task.") or obj["kind"].startswith("verifier."):
        if not obj.get("task_id"):
            raise InvalidEvent("task event lacks task id")
    if obj["kind"] in EFFECT_KINDS:
        if not obj.get("task_id") or not obj.get("effect_key") or obj.get("lease_fence") is None:
            raise InvalidEvent("effect lacks task, key or fence")
    return obj


def bounded_lines(source: BinaryIO) -> Iterator[tuple[int, bytes | None]]:
    """Bounded streaming reader; (-1, None) means total byte budget used up.

    Drains an overlong line without keeping it in memory, but stops the file
    when the total bytes read exceed MAX_TOTAL_BYTES. A clean EOF at exactly
    MAX_LINE_BYTES without a newline remains legal.
    """
    row = 0
    remaining = MAX_TOTAL_BYTES

    def take_line() -> bytes | None:
        nonlocal remaining
        fragment = source.readline(min(MAX_LINE_BYTES + 1, remaining + 1))
        if len(fragment) > remaining:
            return None
        remaining -= len(fragment)
        return fragment

    while True:
        fragment = take_line()
        if fragment is None:
            yield -1, None
            return
        if not fragment:
            return
        row += 1
        oversized = len(fragment) > MAX_LINE_BYTES
        if len(fragment) == MAX_LINE_BYTES and not fragment.endswith(b"\n"):
            if remaining == 0:
                # Distinguish EOF exactly at the limit from another byte.
                ahead = source.read(1)
                if ahead:
                    yield -1, None
                    return
            else:
                ahead = source.read(1)
                if ahead:
                    remaining -= 1
                    fragment += ahead
                    oversized = True
        if oversized:
            while fragment and not fragment.endswith(b"\n"):
                fragment = take_line()
                if fragment is None:
                    yield -1, None
                    return
            yield row, None
        else:
            yield row, fragment
        if remaining == 0:
            if source.read(1):
                yield -1, None
            return


def _finding(code: str, severity: str, *, task_id: str | None = None,
             event_id: str | None = None) -> dict:
    # Only validated UUID identifiers can leave the auditor.
    item = {"code": code, "severity": severity}
    if task_id is not None and _uuid(task_id):
        item["task_id"] = task_id
    if event_id is not None and _uuid(event_id):
        item["event_id"] = event_id
    return item


class _Findings:
    def __init__(self) -> None:
        self.items: list[dict] = []
        self.counts: dict[str, int] = defaultdict(int)

    @staticmethod
    def sort_key(item: dict) -> tuple[int, str, str, str]:
        # Deterministic, high-severity-first retention. Do not allow a storm of
        # missing low-risk sequence numbers to hide a late unsafe external effect.
        rank = {"critical": 0, "invalid": 1, "incomplete": 2}
        return (rank.get(item["severity"], 3), item["code"],
                item.get("task_id", ""), item.get("event_id", ""))

    def add(self, code: str, severity: str, **kwargs: object) -> None:
        self.counts[code] += 1
        item = _finding(code, severity, **kwargs)
        if len(self.items) < MAX_FINDINGS:
            self.items.append(item)
        else:
            # MAX_FINDINGS is deliberately small. Keep bounded memory while
            # making truncation-independent visible examples deterministic.
            worst = max(range(len(self.items)), key=lambda i: self.sort_key(self.items[i]))
            if self.sort_key(item) < self.sort_key(self.items[worst]):
                self.items[worst] = item


def audit_stream(source: BinaryIO, *, max_events: int = DEFAULT_MAX_EVENTS) -> dict:
    if type(max_events) is not int or not (1 <= max_events <= DEFAULT_MAX_EVENTS):
        raise ValueError("max_events out of safe range")
    findings = _Findings()
    by_id: dict[str, dict] = {}
    canonical: dict[str, str] = {}
    by_sequence: dict[tuple[str, int], str] = {}
    invalid = 0
    lines_read = 0
    duplicates = 0
    for line_no, line in bounded_lines(source):
        if line_no == -1:
            findings.add("INPUT_BYTE_LIMIT_REACHED", "incomplete")
            break
        lines_read = line_no
        if line_no > max_events:
            findings.add("INPUT_LIMIT_REACHED", "incomplete")
            break
        if line is None:
            invalid += 1
            findings.add("INVALID_EVENT", "invalid")
            continue
        try:
            obj = parse_event(line)
        except InvalidEvent:
            invalid += 1
            findings.add("INVALID_EVENT", "invalid")
            continue
        eid = obj["event_id"]
        fingerprint = json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
        if eid in canonical:
            if canonical[eid] != fingerprint:
                findings.add("EVENT_ID_COLLISION", "critical", event_id=eid)
            else:
                duplicates += 1
            continue
        serial = (obj["producer_id"], obj["source_event_seq"])
        if serial in by_sequence and by_sequence[serial] != eid:
            findings.add("SEQUENCE_COLLISION", "critical", event_id=eid)
        else:
            by_sequence[serial] = eid
        by_id[eid] = obj
        canonical[eid] = fingerprint

    producers: dict[str, set[int]] = defaultdict(set)
    children: dict[str, list[str]] = defaultdict(list)
    in_degree = {eid: 0 for eid in by_id}
    effects: dict[tuple[str, str, int], dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    claims: dict[tuple[str, int], set[tuple[str, str | None]]] = defaultdict(set)
    verifications: set[tuple[str, str]] = set()
    successes: list[dict] = []
    terminals: dict[tuple[str, str | None], set[str]] = defaultdict(set)
    stopped: list[dict] = []
    reused_effects: dict[tuple[str, str], set[int]] = defaultdict(set)

    for eid, event in by_id.items():
        producers[event["producer_id"]].add(event["source_event_seq"])
        parent_id = event.get("causation_event_id")
        if parent_id:
            if parent_id not in by_id:
                findings.add("CAUSAL_PARENT_NOT_IN_SNAPSHOT", "incomplete", event_id=eid)
            else:
                parent = by_id[parent_id]
                children[parent_id].append(eid)
                in_degree[eid] += 1
                if (parent["producer_id"] == event["producer_id"]
                        and parent["source_event_seq"] >= event["source_event_seq"]):
                    findings.add("CAUSAL_SEQUENCE_INVERSION", "critical", event_id=eid)
        kind = event["kind"]
        task_id = event.get("task_id")
        fence = event.get("lease_fence")
        if kind == "task.claimed" and task_id and fence is not None:
            # agent_id may be a shared logical role (e.g. "A1") reused by many
            # process incarnations. Fence ownership must not collapse all
            # same-named agents into one identity.
            claims[(task_id, fence)].add((event["producer_id"], event.get("agent_id")))
        if kind == "verifier.completed" and task_id and event.get("target_revision") and event.get("evidence_refs"):
            verifications.add((task_id, event["target_revision"]))
        if kind == "task.completed" and task_id:
            if event.get("state_to") not in ("succeeded", "failed", "cancelled", "blocked"):
                findings.add("COMPLETION_WITHOUT_TERMINAL_STATE", "incomplete", task_id=task_id, event_id=eid)
            else:
                terminals[(task_id, event.get("attempt_id"))].add(event["state_to"])
            if event.get("state_to") in ("failed", "cancelled", "blocked") and not event.get("reason_code"):
                findings.add("TERMINAL_FAILURE_WITHOUT_REASON", "incomplete", task_id=task_id, event_id=eid)
            if event.get("state_to") == "succeeded":
                successes.append(event)
        if kind in STOP_KINDS and task_id:
            if kind in ("task.blocked", "worker.lease_expired") and not event.get("reason_code"):
                findings.add("STOP_WITHOUT_REASON_CODE", "incomplete", task_id=task_id, event_id=eid)
            stopped.append(event)
        if kind in EFFECT_KINDS:
            key = (task_id, event["effect_key"], fence)
            effects[key][kind].append(event)
            reused_effects[(task_id, event["effect_key"])].add(fence)

    for producer, sequences in producers.items():
        ordered = sorted(sequences)
        # Do not mark truncated head/tail as missing; a snapshot may be partial.
        for left, right in zip(ordered, ordered[1:]):
            if right > left + 1:
                findings.add("PRODUCER_SEQUENCE_GAP", "incomplete")

    queue = deque(eid for eid, degree in in_degree.items() if degree == 0)
    visited = 0
    while queue:
        eid = queue.popleft()
        visited += 1
        for child in children[eid]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)
    if visited != len(by_id):
        findings.add("CAUSAL_CYCLE", "critical")

    for (task_id, attempt_id), terminal_states in terminals.items():
        if len(terminal_states) > 1:
            if attempt_id is None:
                # Events from older attempts may share a task ID. Without an
                # attempt identifier the conflicting history is ambiguous.
                findings.add("TERMINAL_CONFLICT_WITHOUT_ATTEMPT_ID", "incomplete", task_id=task_id)
            else:
                findings.add("CONFLICTING_ATTEMPT_TERMINAL_STATES", "critical", task_id=task_id)

    for (task_id, fence), agents in claims.items():
        if len(agents) > 1:
            findings.add("FENCE_OWNER_CONFLICT", "critical", task_id=task_id)
    for (task_id, effect_key), fences in reused_effects.items():
        if len(fences) > 1:
            findings.add("EFFECT_REUSED_ACROSS_FENCES", "critical", task_id=task_id)

    def causally_after(ack: dict, reservations: list[dict]) -> bool:
        # Per-producer event sequence is an ordering guarantee; for different
        # producers require an explicit, possibly multi-hop causation chain.
        for reserve in reservations:
            if (reserve["producer_id"] == ack["producer_id"] and
                    reserve["source_event_seq"] < ack["source_event_seq"]):
                return True
        current_id = ack.get("causation_event_id")
        seen: set[str] = set()
        reserved_ids = {x["event_id"] for x in reservations}
        while current_id and current_id not in seen:
            if current_id in reserved_ids:
                return True
            seen.add(current_id)
            parent = by_id.get(current_id)
            current_id = parent.get("causation_event_id") if parent else None
        return False

    unresolved_tasks: set[str] = set()
    for (task_id, _effect_key, _fence), kinds in effects.items():
        reserved = kinds.get("tool.effect.reserved", [])
        acknowledged = kinds.get("tool.effect.acknowledged", [])
        explicit_unknown = kinds.get("tool.effect.unknown", [])
        reconciled = kinds.get("tool.effect.reconciled", [])
        if acknowledged and not reserved:
            findings.add("ACK_WITHOUT_RESERVATION_IN_SNAPSHOT", "incomplete", task_id=task_id)
        if reconciled:
            # Offline events are untrusted claims, not independently fetched
            # remote receipts or an authoritative state transition.
            findings.add("RECONCILIATION_CLAIM_REQUIRES_LEDGER", "incomplete", task_id=task_id)
        duplicate_reserve = len(reserved) > 1
        if duplicate_reserve:
            findings.add("MULTIPLE_EFFECT_RESERVATIONS", "critical", task_id=task_id)
        bad_ack = bool(acknowledged and any(not e.get("evidence_refs") for e in acknowledged))
        bad_order = bool(acknowledged and reserved and any(not causally_after(e, reserved) for e in acknowledged))
        if bad_order:
            findings.add("ACK_CAUSAL_PROOF_MISSING", "incomplete", task_id=task_id)
        if bad_ack:
            findings.add("ACK_WITHOUT_EVIDENCE_REF", "critical", task_id=task_id)
        if explicit_unknown or (reserved and not acknowledged) or bad_ack or bad_order or duplicate_reserve:
            unresolved_tasks.add(task_id)
            findings.add("EFFECT_OUTCOME_UNKNOWN", "critical", task_id=task_id)

    for success in successes:
        task_id = success["task_id"]
        if task_id in unresolved_tasks:
            findings.add("SUCCESS_WHILE_EFFECT_UNRESOLVED", "critical", task_id=task_id,
                         event_id=success["event_id"])
        revision = success.get("target_revision")
        if not revision or (task_id, revision) not in verifications:
            findings.add("SUCCESS_WITHOUT_REVISION_VERIFIER_IN_SNAPSHOT", "incomplete",
                         task_id=task_id, event_id=success["event_id"])

    if not by_id and not findings.counts:
        # A perfectly empty input is not a healthy run or a proof of uptime.
        findings.add("EMPTY_SNAPSHOT", "incomplete")

    codes = findings.counts
    if invalid:
        status, exit_code = "invalid_snapshot", 4
    elif "EFFECT_OUTCOME_UNKNOWN" in codes or "SUCCESS_WHILE_EFFECT_UNRESOLVED" in codes:
        status, exit_code = "requires_effect_reconciliation", 2
    elif any(x["severity"] == "critical" for x in findings.items) or any(k in codes for k in
             ("EVENT_ID_COLLISION", "SEQUENCE_COLLISION", "FENCE_OWNER_CONFLICT", "CONFLICTING_ATTEMPT_TERMINAL_STATES", "CAUSAL_CYCLE",
              "CAUSAL_SEQUENCE_INVERSION", "EFFECT_REUSED_ACROSS_FENCES", "ACK_WITHOUT_EVIDENCE_REF")):
        status, exit_code = "integrity_anomaly", 2
    elif codes:
        status, exit_code = "incomplete_observation", 3
    else:
        status, exit_code = "no_anomalies_in_supplied_slice", 0
    stop_observations = [
        {"task_id": x["task_id"], "kind": x["kind"],
         "reason_code": x.get("reason_code") or "UNKNOWN",
         "basis": "UNTRUSTED_REPORTED_METADATA"}
        for x in stopped[:MAX_FINDINGS]
    ]
    return {
        "schema_version": 1,
        "status": status,
        "exit_code": exit_code,
        "authority": "UNTRUSTED_OFFLINE_DIAGNOSTIC_ONLY",
        "mutation_allowed": False,
        "external_effect_retry_allowed": False,
        "counts": {"lines_read": lines_read, "accepted_events": len(by_id),
                   "duplicate_deliveries": duplicates, "invalid_events": invalid,
                   "producer_count": len(producers), "task_count": len({x.get("task_id") for x in by_id.values() if x.get("task_id")}),
                   "finding_total": sum(codes.values()),
                   "finding_suppressed": max(0, sum(codes.values()) - len(findings.items))},
        "finding_counts": dict(sorted(codes.items())),
        "stop_observations": stop_observations,
        "stop_observations_suppressed": max(0, len(stopped) - MAX_FINDINGS),
        "findings": sorted(findings.items, key=findings.sort_key),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Hermes metadata event auditor")
    parser.add_argument("path", help="local NDJSON export; never pass private chat transcripts")
    parser.add_argument("--max-events", type=int, default=DEFAULT_MAX_EVENTS)
    args = parser.parse_args(argv)
    try:
        with open(args.path, "rb") as source:
            result = audit_stream(source, max_events=args.max_events)
    except (OSError, ValueError) as exc:
        # Do not print attacker-provided file names or exception text.
        print(json.dumps({"status": "input_unavailable", "exit_code": 4,
                          "authority": "UNTRUSTED_OFFLINE_DIAGNOSTIC_ONLY"}))
        return 4
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
