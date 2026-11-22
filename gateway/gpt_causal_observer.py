"""Read-only, evidence-first GPT/Hermes incident observer (stdlib only).

Not a scheduler, task state authority, authorization layer, or retry executor.
Caller MUST authenticate producers independently before setting trusted_origin.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import re
import sqlite3
import threading
import time
import uuid
from typing import Any, Mapping

MAX_EVENT_BYTES = 4096
MAX_EVIDENCE_REFS = 8
KINDS = frozenset({
    "worker.started", "worker.heartbeat", "tool.intent", "tool.effect.reserved",
    "tool.effect.acknowledged", "tool.effect.unknown", "verifier.completed",
    "task.completed", "task.blocked", "model.throttled", "bridge.disconnected",
    "approval.denied", "observer.gap_detected",
})
KEYS = frozenset({
    "schema_version", "event_id", "producer_id", "source_event_seq", "run_id",
    "task_id", "attempt_id", "lease_fence", "kind", "effect_key",
    "operation_fingerprint", "target_revision", "evidence_refs",
})
REQUIRED = {"schema_version", "event_id", "producer_id", "source_event_seq",
            "run_id", "task_id", "attempt_id", "lease_fence", "kind"}
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
REVISION = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
IDENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")


class InvalidEvent(ValueError):
    """Event rejected without persisting unsafe data."""


class EventConflict(ValueError):
    """A supposedly idempotent event or producer sequence changed meaning."""


def _validated(event: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    if not isinstance(event, dict) or event.keys() - KEYS or REQUIRED - event.keys():
        raise InvalidEvent("unexpected or missing event fields")
    if type(event["schema_version"]) is not int or event["schema_version"] != 1:
        raise InvalidEvent("unsupported schema version")
    if type(event["source_event_seq"]) is not int or not 1 <= event["source_event_seq"] < 2**63:
        raise InvalidEvent("bad producer sequence")
    if type(event["lease_fence"]) is not int or not 0 <= event["lease_fence"] < 2**63:
        raise InvalidEvent("bad fence")
    try:
        if str(uuid.UUID(event["event_id"])) != event["event_id"]:
            raise ValueError("noncanonical uuid")
    except (TypeError, ValueError, AttributeError) as ex:
        raise InvalidEvent("invalid event_id") from ex
    for key in ("producer_id", "run_id", "task_id", "attempt_id"):
        value = event[key]
        if not isinstance(value, str) or not IDENT.fullmatch(value):
            raise InvalidEvent("invalid identifier: " + key)
    if not isinstance(event["kind"], str) or event["kind"] not in KINDS:
        raise InvalidEvent("unsupported kind")
    # These fields may be attacker-supplied. Do not allow arbitrary short
    # phrases that could smuggle prompt fragments or credentials into a log.
    for key in ("effect_key", "operation_fingerprint"):
        if key in event and event[key] is not None:
            if not isinstance(event[key], str) or not DIGEST.fullmatch(event[key]):
                raise InvalidEvent("metadata fingerprint must be sha256")
    if "target_revision" in event and event["target_revision"] is not None:
        revision = event["target_revision"]
        if not isinstance(revision, str) or not REVISION.fullmatch(revision):
            raise InvalidEvent("target revision must be a full git digest")
    if event["kind"].startswith("tool.effect.") and not event.get("effect_key"):
        raise InvalidEvent("effect event needs stable effect key")
    refs = event.get("evidence_refs", [])
    if not isinstance(refs, list) or len(refs) > MAX_EVIDENCE_REFS or any(
            not isinstance(v, str) or not DIGEST.fullmatch(v) for v in refs):
        raise InvalidEvent("evidence refs must be bounded sha256 digests")
    normalized = dict(event)
    normalized["evidence_refs"] = refs
    encoded = json.dumps(normalized, ensure_ascii=True, sort_keys=True,
                         separators=(",", ":"), allow_nan=False)
    if len(encoded.encode("utf-8")) > MAX_EVENT_BYTES:
        raise InvalidEvent("oversized event")
    return encoded, normalized


class CausalObserver:
    """Non-authoritative atomic event journal with read-only incident projections.

    Store locally on one host. Keep outside the authoritative Kanban DB. An
    ingestion trust flag is supplied by an authenticated adapter, never a model.
    No execute, retry, approve or complete API is exposed.
    """

    def __init__(self, path: str = ":memory:"):
        self._lock = threading.RLock()
        self._epoch = uuid.uuid4().hex
        self._conn = sqlite3.connect(path, timeout=5, check_same_thread=False)
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS diagnostic_events (
            event_id TEXT PRIMARY KEY,
            producer_id TEXT NOT NULL,
            source_event_seq INTEGER NOT NULL,
            run_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            attempt_id TEXT NOT NULL,
            lease_fence INTEGER NOT NULL,
            kind TEXT NOT NULL,
            effect_key TEXT,
            operation_fingerprint TEXT,
            target_revision TEXT,
            evidence_refs TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            trusted_origin INTEGER NOT NULL,
            receive_epoch TEXT NOT NULL,
            received_mono REAL NOT NULL,
            UNIQUE(producer_id, source_event_seq)
        )""")
        self._conn.execute("CREATE INDEX IF NOT EXISTS diag_by_run ON diagnostic_events(run_id)")
        self._conn.commit()

    def ingest(self, event: Mapping[str, Any], *, trusted_origin: bool = False) -> str:
        if type(trusted_origin) is not bool:
            raise ValueError("trusted_origin must be a boolean supplied by adapter")
        canonical, v = _validated(event)
        digest = hashlib.sha256((canonical + ("|trusted" if trusted_origin else "|untrusted")).encode()).hexdigest()
        with self._lock:
            # BEGIN IMMEDIATE serializes concurrent SQLite processes BEFORE
            # lookup, not merely concurrent threads using this connection.
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                row = self._conn.execute(
                    "SELECT payload_hash FROM diagnostic_events WHERE event_id=? OR "
                    "(producer_id=? AND source_event_seq=?)",
                    (v["event_id"], v["producer_id"], v["source_event_seq"]),
                ).fetchone()
                if row:
                    exact = self._conn.execute(
                        "SELECT payload_hash FROM diagnostic_events WHERE event_id=? "
                        "AND producer_id=? AND source_event_seq=?",
                        (v["event_id"], v["producer_id"], v["source_event_seq"]),
                    ).fetchone()
                    if exact and exact[0] == digest:
                        self._conn.commit()
                        return "duplicate"
                    raise EventConflict("event identity or producer sequence reused")
                self._conn.execute("""INSERT INTO diagnostic_events (
                    event_id, producer_id, source_event_seq, run_id, task_id,
                    attempt_id, lease_fence, kind, effect_key,
                    operation_fingerprint, target_revision, evidence_refs,
                    payload_hash, trusted_origin, receive_epoch, received_mono
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (v["event_id"], v["producer_id"], v["source_event_seq"],
                     v["run_id"], v["task_id"], v["attempt_id"], v["lease_fence"],
                     v["kind"], v.get("effect_key"), v.get("operation_fingerprint"),
                     v.get("target_revision"), json.dumps(v["evidence_refs"]),
                     digest, int(trusted_origin), self._epoch, time.monotonic()))
                self._conn.commit()
            except BaseException:
                self._conn.rollback()
                raise
        return "inserted"

    def diagnose(self, run_id: str, *, heartbeat_max_age_s: float = 120,
                 repeat_min: int = 3) -> dict[str, Any]:
        if not isinstance(run_id, str) or not IDENT.fullmatch(run_id):
            raise ValueError("invalid run_id")
        if not 0 < heartbeat_max_age_s <= 86400 or not 2 <= repeat_min <= 100:
            raise ValueError("invalid diagnostic policy")
        with self._lock:
            # Causal order is only known per producer. Wall-clock timestamps
            # are not used to infer ordering across independent producers.
            self._conn.row_factory = sqlite3.Row
            rows = [dict(r) for r in self._conn.execute(
                "SELECT * FROM diagnostic_events WHERE run_id=? "
                "ORDER BY producer_id, source_event_seq", (run_id,))]
            if not rows:
                return {"run_id": run_id, "diagnostic": "UNKNOWN", "confidence": "insufficient_evidence",
                        "activity": "unobserved", "gap_count": 0, "event_count": 0,
                        "next_safe_action": "collect_authenticated_events"}
            producers = {r["producer_id"] for r in rows}
            gaps = 0
            for producer in producers:
                # A producer's sequence spans multiple runs.
                high, count = self._conn.execute(
                    "SELECT MAX(source_event_seq), COUNT(*) FROM diagnostic_events "
                    "WHERE producer_id=?", (producer,)).fetchone()
                gaps += (high - count) if high else 0
            latest_activity = max((r["received_mono"] for r in rows
                                   if r["receive_epoch"] == self._epoch and
                                   r["kind"] in ("worker.heartbeat", "worker.started")),
                                  default=None)
            if latest_activity is None:
                activity = "unobserved"
            elif time.monotonic() - latest_activity <= heartbeat_max_age_s:
                activity = "recent_heartbeat_not_proof_of_progress"
            else:
                activity = "heartbeat_stale_not_proof_of_crash"
            reservations = {
                (r["task_id"], r["attempt_id"], r["lease_fence"], r["effect_key"])
                for r in rows if r["kind"] in ("tool.effect.reserved", "tool.effect.unknown")
            }
            acknowledgments = {
                (r["task_id"], r["attempt_id"], r["lease_fence"], r["effect_key"])
                for r in rows if r["kind"] == "tool.effect.acknowledged" and r["trusted_origin"]
                and json.loads(r["evidence_refs"])
            }
            unresolved = sorted(reservations - acknowledgments)
            loops = []
            for producer in producers:
                p = [r for r in rows if r["producer_id"] == producer]
                grouped = defaultdict(list)
                for r in p:
                    if r["kind"] == "tool.intent" and r["operation_fingerprint"]:
                        # A verifier for task B cannot close a suspected loop
                        # in task A, even on a shared agent process.
                        group = (r["task_id"], r["attempt_id"], r["lease_fence"],
                                 r["operation_fingerprint"], r["target_revision"])
                        grouped[group].append(r)
                for key, intents in grouped.items():
                    verified_sequences = [x["source_event_seq"] for x in p
                        if x["task_id"] == key[0] and x["attempt_id"] == key[1]
                        and x["lease_fence"] == key[2] and x["trusted_origin"]
                        and x["kind"] == "verifier.completed" and x["target_revision"]
                        and (key[4] is None or x["target_revision"] == key[4])
                        and json.loads(x["evidence_refs"])]
                    last_verified_seq = max(verified_sequences, default=0)
                    pending = [x for x in intents
                               if x["source_event_seq"] > last_verified_seq]
                    if len(pending) >= repeat_min:
                        loops.append({"producer_id": producer,
                                      "operation_fingerprint": key[3],
                                      "repetition_count": len(pending)})
            if unresolved:
                diagnostic, confidence, next_action = (
                    "EFFECT_OUTCOME_UNKNOWN", "conservative_suspect", "reconcile_external_effect_no_retry")
            elif gaps:
                diagnostic, confidence, next_action = (
                    "OBSERVABILITY_GAP", "confirmed_missing_sequence", "replay_events_from_producer_cursor")
            elif loops:
                diagnostic, confidence, next_action = (
                    "NO_VERIFIED_PROGRESS", "suspect", "inspect_repeated_operation_and_independent_artifacts")
            elif any(r["kind"] == "approval.denied" and r["trusted_origin"] for r in rows):
                diagnostic, confidence, next_action = ("POLICY_DENIED", "observed_adapter_event", "stop_await_owner")
            elif any(r["kind"] == "model.throttled" and r["trusted_origin"] for r in rows):
                diagnostic, confidence, next_action = ("RATE_LIMITED", "observed_adapter_event", "respect_shared_retry_budget")
            else:
                diagnostic, confidence, next_action = ("UNKNOWN", "insufficient_evidence", "query_authoritative_kanban_state")
            last_by_producer = {
                p: {"seq": max(x["source_event_seq"] for x in rows if x["producer_id"] == p),
                    "last_kind": max((x for x in rows if x["producer_id"] == p),
                                     key=lambda x: x["source_event_seq"])["kind"]}
                for p in sorted(producers)
            }
            trusted_proof_count = sum(
                1 for r in rows if r["trusted_origin"] and
                r["kind"] == "verifier.completed" and r["target_revision"]
                and json.loads(r["evidence_refs"]))
            return {"run_id": run_id, "diagnostic": diagnostic,
                    "confidence": confidence, "activity": activity,
                    "gap_count": gaps, "event_count": len(rows),
                    "unresolved_effects": len(unresolved), "repeated_intents": loops,
                    "last_by_producer": last_by_producer,
                    "independent_evidence_markers": trusted_proof_count,
                    "next_safe_action": next_action,
                    "authoritative_task_state": None}

    def close(self) -> None:
        with self._lock:
            self._conn.close()
