"""Append-only, untrusted telemetry journal for Hermes/GPT connector events.

Never feed this module secrets or message bodies. It deliberately cannot dispatch
work, approve actions, or declare independently verified task completion.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Mapping

EVENT_KINDS = frozenset({
    "run.accepted", "worker.started", "worker.heartbeat", "worker.progress",
    "llm.request_started", "llm.response_received", "tool.effect_reserved",
    "tool.effect_acknowledged", "tool.effect_not_executed", "approval.required",
    "approval.resolved", "run.reported_completed", "run.reported_failed",
    "worker.stopped",
})
_FIELDS = frozenset({"schema_version", "event_id", "source", "run_id", "attempt",
                     "sequence", "kind", "action_id", "reason_code", "trace_id",
                     "subject_revision"})
_REQUIRED = frozenset({"schema_version", "event_id", "source", "run_id", "attempt",
                       "sequence", "kind"})
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")
_REASON = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
# Telemetry may suggest a cause, but never authorizes an automated retry.
CAUSE_ACTIONS = {
    "AUTH_DENIED": "CHECK_CREDENTIAL_SCOPE",
    "RATE_LIMITED": "HONOR_RETRY_AFTER_AND_BUDGET",
    "QUOTA_EXCEEDED": "STOP_DISPATCH_AND_REVIEW_BUDGET",
    "CONTEXT_EXHAUSTED": "RESTORE_CHECKPOINT_OR_REPLAN",
    "UPSTREAM_TIMEOUT": "RECONCILE_PROVIDER_RESPONSE_FIRST",
    "STREAM_LOST": "RECONCILE_RESPONSE_ID_FIRST",
    "TOOL_SCHEMA_INVALID": "REPAIR_VERSIONED_TOOL_CONTRACT",
    "PERMISSION_DENIED": "REQUEST_SCOPED_ACCESS",
    "BUDGET_EXCEEDED": "STOP_DISPATCH_AND_REVIEW_BUDGET",
    "BROWSER_TAB_CLOSED": "CHECK_ADAPTER_SESSION_NOT_TASK_RESULT",
    "CI_FAILED": "INSPECT_CHECKS_AT_EXACT_SHA",
    "LEASE_EXPIRED": "CHECK_FENCING_AND_WORKER_OWNER",
    "INCOMPATIBLE_HERMES_VERSION": "STOP_INTEGRATION_AND_NEGOTIATE_VERSION",
    "HOOK_UNAVAILABLE": "CHECK_RUNTIME_CAPABILITIES_AND_VERSION",
    "PLUGIN_DISABLED": "CHECK_SCOPED_PLUGIN_CONFIG_AND_CONSENT",
    "MCP_SESSION_TERMINATED": "RECONNECT_TRANSPORT_AND_REPLAY_OUTBOX",
    "TRANSPORT_DISCONNECTED": "RECONNECT_TRANSPORT_AND_REPLAY_OUTBOX",
    "CORS_REJECTED": "CHECK_ALLOWED_EXTENSION_ORIGIN",
    "BROWSER_DETACHED": "CHECK_OPT_IN_TAB_ATTACHMENT",
    "OUTBOX_BACKPRESSURE": "PAUSE_PRODUCER_AND_CHECK_STORAGE_LIMIT",
    "SOURCE_UNAUTHENTICATED": "REJECT_EVENT_AND_CHECK_INGRESS_AUTH",
    "UNKNOWN": "CLASSIFY_FAILURE_MANUALLY",
}


class JournalConflict(ValueError):
    """Conflicting replay/sequence or invalid observability contract."""


def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def validate_event(data: Mapping[str, Any]) -> dict[str, Any]:
    """Strict allowlist prevents accidental capture of prompts, tokens and content."""
    if not isinstance(data, Mapping) or set(data) - _FIELDS or _REQUIRED - set(data):
        raise JournalConflict("unexpected or missing event fields")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise JournalConflict("unsupported schema_version")
    for key in ("event_id", "source", "run_id"):
        if type(data[key]) is not str or not _ID.fullmatch(data[key]):
            raise JournalConflict(f"invalid {key}")
    for key in ("action_id", "trace_id", "subject_revision"):
        if key in data and (type(data[key]) is not str or not _ID.fullmatch(data[key])):
            raise JournalConflict(f"invalid {key}")
    if "reason_code" in data and (type(data["reason_code"]) is not str or
                                  not _REASON.fullmatch(data["reason_code"])):
        raise JournalConflict("invalid reason_code")
    for key in ("attempt", "sequence"):
        if type(data[key]) is not int or not 1 <= data[key] <= 1_000_000_000:
            raise JournalConflict(f"invalid {key}")
    if type(data["kind"]) is not str or data["kind"] not in EVENT_KINDS:
        raise JournalConflict("unknown kind")
    if data["kind"].startswith("tool.effect_") and "action_id" not in data:
        raise JournalConflict("effect events need action_id")
    if data["kind"].startswith("approval.") and "action_id" not in data:
        raise JournalConflict("approval events need action_id")
    value = dict(data)
    if len(_canonical(value).encode("utf-8")) > 4096:
        raise JournalConflict("oversized event")
    return value


class EventJournal:
    """Local SQLite WAL event inbox: not a trusted verifier or task scheduler.

    Any external emitter authentication, per-agent scope checking and audit-anchor
    export MUST occur in the host adapter, not via caller-supplied event fields.
    """

    def __init__(self, path: str | Path, clock=time.time):
        self.path = Path(path)
        self.clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("""CREATE TABLE IF NOT EXISTS events (
                position INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT UNIQUE NOT NULL,
                source TEXT NOT NULL,
                run_id TEXT NOT NULL,
                attempt INTEGER NOT NULL,
                sequence INTEGER NOT NULL,
                kind TEXT NOT NULL,
                event_json TEXT NOT NULL,
                event_sha256 TEXT NOT NULL,
                received_at REAL NOT NULL,
                prev_sha256 TEXT NOT NULL,
                chain_sha256 TEXT NOT NULL,
                UNIQUE(source, run_id, attempt, sequence)
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS events_run_idx ON events(run_id,attempt,position)")

    @contextmanager
    def _db(self, write=False):
        db = sqlite3.connect(str(self.path), isolation_level=None, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA busy_timeout=10000")
            db.execute("PRAGMA synchronous=FULL")
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            if write:
                db.execute("COMMIT")
        except BaseException:
            if write and db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def ingest(self, raw: Mapping[str, Any]) -> bool:
        """Store one untrusted event. True means new; False means identical replay."""
        event = validate_event(raw)
        body = _canonical(event)
        digest = hashlib.sha256(body.encode()).hexdigest()
        with self._db(write=True) as db:
            old = db.execute("SELECT event_sha256 FROM events WHERE event_id=?",
                             (event["event_id"],)).fetchone()
            if old:
                if old["event_sha256"] != digest:
                    raise JournalConflict("event_id reused with conflicting payload")
                return False
            sequence = db.execute("""SELECT event_id FROM events
                WHERE source=? AND run_id=? AND attempt=? AND sequence=?""",
                (event["source"], event["run_id"], event["attempt"], event["sequence"])).fetchone()
            if sequence:
                raise JournalConflict("source sequence reused with different event_id")
            prev = db.execute("SELECT chain_sha256 FROM events ORDER BY position DESC LIMIT 1").fetchone()
            prev_digest = prev["chain_sha256"] if prev else "0" * 64
            received = float(self.clock())
            if not (0 <= received < 1e14):
                raise JournalConflict("invalid server clock")
            chain = hashlib.sha256(f"{prev_digest}|{digest}|{received:.6f}".encode()).hexdigest()
            db.execute("""INSERT INTO events
                (event_id,source,run_id,attempt,sequence,kind,event_json,event_sha256,
                 received_at,prev_sha256,chain_sha256)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (event["event_id"], event["source"], event["run_id"], event["attempt"],
                 event["sequence"], event["kind"], body, digest, received, prev_digest, chain))
        return True

    def verify_chain(self) -> bool:
        """Detect accidental edits/corruption; NOT cryptographic non-repudiation."""
        prior = "0" * 64
        with self._db() as db:
            for row in db.execute("SELECT * FROM events ORDER BY position"):
                digest = hashlib.sha256(row["event_json"].encode()).hexdigest()
                chain = hashlib.sha256(
                    f"{prior}|{digest}|{row['received_at']:.6f}".encode()
                ).hexdigest()
                try:
                    obj = json.loads(row["event_json"])
                    valid = validate_event(obj)
                except (ValueError, TypeError, json.JSONDecodeError):
                    return False
                if (digest != row["event_sha256"] or prior != row["prev_sha256"]
                        or chain != row["chain_sha256"] or valid["event_id"] != row["event_id"]
                        or valid["run_id"] != row["run_id"] or valid["kind"] != row["kind"]
                        or valid["source"] != row["source"] or valid["attempt"] != row["attempt"]
                        or valid["sequence"] != row["sequence"]):
                    return False
                prior = chain
        return True

    def list_runs(self, limit: int = 500) -> list[str]:
        """List recent opaque run ids for a read-only observer; bounded by design."""
        if type(limit) is not int or not 1 <= limit <= 10000:
            raise ValueError("invalid run listing limit")
        with self._db() as db:
            rows = db.execute("""SELECT run_id FROM events
                GROUP BY run_id ORDER BY MAX(position) DESC LIMIT ?""", (limit,)).fetchall()
        return [row["run_id"] for row in rows]

    def assess(self, run_id: str, *, now: float | None = None,
               liveness_timeout: float = 120, progress_timeout: float = 300) -> dict[str, Any]:
        """Conservative diagnosis only. No autonomous retry or success claims."""
        if type(run_id) is not str or not _ID.fullmatch(run_id):
            raise JournalConflict("invalid run_id")
        if not (5 <= liveness_timeout <= progress_timeout <= 86400):
            raise ValueError("invalid timeouts")
        moment = float(self.clock() if now is None else now)
        if not (0 <= moment < 1e14):
            raise ValueError("invalid observation clock")
        with self._db() as db:
            a = db.execute("SELECT MAX(attempt) AS n FROM events WHERE run_id=?", (run_id,)).fetchone()["n"]
            if a is None:
                return {"run_id": run_id, "state": "NOT_OBSERVED", "next_action": "CHECK_INTAKE"}
            rows = db.execute("""SELECT event_json,received_at,sequence,source
                FROM events WHERE run_id=? AND attempt=? ORDER BY position""",
                (run_id, a)).fetchall()
            # Keep outstanding writes from every earlier attempt visible when a
            # replacement worker starts; never infer success from attempt age.
            prior_effect_rows = db.execute("""SELECT attempt,source,sequence,kind,event_json
                FROM events WHERE run_id=? AND attempt<? AND kind IN
                ('tool.effect_reserved','tool.effect_acknowledged','tool.effect_not_executed')
                ORDER BY position""", (run_id, a)).fetchall()
            # A missing event in an older attempt can conceal a reservation
            # or failed stop. Advancing to a new attempt does not repair it.
            prior_seq_counts = db.execute("""SELECT attempt,source,MAX(sequence) AS high,
                COUNT(*) AS seen FROM events WHERE run_id=? AND attempt<?
                GROUP BY attempt,source""", (run_id, a)).fetchall()
        events = [(json.loads(r["event_json"]), r["received_at"]) for r in rows]
        # Server receipt timestamps can jump backward after NTP/time changes.
        # In that case time-based liveness diagnosis is unreliable.
        clock_reversed = any(
            rows[i]["received_at"] + 1.0 < rows[i - 1]["received_at"]
            for i in range(1, len(rows))
        ) or moment + 1.0 < max(t for _, t in events)
        # Delivery can be reordered. A backfilled event with an older sequence
        # must NOT refresh liveness/progress and conceal an abandoned worker.
        # Track the source-local highest sequence at receipt time, without
        # assuming any causal order across different sources.
        source_frontier: dict[str, int] = {}
        frontier_receipts: list[tuple[str, float, str]] = []
        progress_receipts: list[float] = []
        worker_sources = {e["source"] for e, _ in events if e["kind"].startswith("worker.")}
        for row, (event, received_at) in zip(rows, events):
            src, sequence = row["source"], row["sequence"]
            if sequence <= source_frontier.get(src, 0):
                continue
            source_frontier[src] = sequence
            frontier_receipts.append((src, received_at, event["kind"]))
            if (event["kind"] not in ("worker.heartbeat", "run.accepted")
                    and (not worker_sources or src in worker_sources)):
                progress_receipts.append(received_at)
        # Gateway/observer traffic does not keep a known worker alive. If this
        # attempt has worker.* signals, measure worker-only source frontiers.
        # For runs without any worker signal, retain the conservative generic
        # event freshness as a hint, never a lease/health verification.
        worker_last_seen: dict[str, float] = {}
        for src, stamp, _ in frontier_receipts:
            if src in worker_sources:
                worker_last_seen[src] = stamp
        live_receipts = (list(worker_last_seen.values()) if worker_last_seen else
                         [stamp for _, stamp, _ in frontier_receipts])
        last_seen = max(live_receipts)
        stale_worker_sources = sorted(
            src for src, stamp in worker_last_seen.items()
            if moment - stamp >= liveness_timeout
        )
        # With no progress events, the FIRST observed arrival is the baseline,
        # not the last heartbeat: endless heartbeat-only workers still stall.
        last_progress = (max(progress_receipts) if progress_receipts else
                         min(stamp for _, stamp, _ in frontier_receipts))
        live_age = max(0.0, moment - last_seen)
        progress_age = max(0.0, moment - last_progress)
        keys = {(r["source"], r["sequence"]) for r in rows}
        by_source: dict[str, set[int]] = {}
        for source, seq in keys:
            by_source.setdefault(source, set()).add(seq)
        missing = sum(max(sequences) - len(sequences) for sequences in by_source.values())
        reserved_events, effect_resolutions = {}, {}
        approval_requests, approval_resolutions = {}, {}
        contradictory = False
        for e, _ in events:
            kind, action = e["kind"], e.get("action_id")
            origin = (e["source"], e["sequence"])
            if kind == "tool.effect_reserved":
                if action in reserved_events:
                    contradictory = True
                reserved_events[action] = origin
            elif kind in ("tool.effect_acknowledged", "tool.effect_not_executed"):
                if action in effect_resolutions:
                    contradictory = True
                effect_resolutions[action] = origin
            elif kind == "approval.required":
                approval_requests[action] = origin
            elif kind == "approval.resolved":
                approval_resolutions[action] = origin
        # Different emitters have no shared sequence clock. A cross-source
        # ack is a hint requiring reconciliation, not a causal write receipt.
        cross_source_effects = {
            action for action, resolution in effect_resolutions.items()
            if action in reserved_events and reserved_events[action][0] != resolution[0]
        }
        reserved = (set(reserved_events) - set(effect_resolutions)) | cross_source_effects
        pending_approval = set(approval_requests) - set(approval_resolutions)
        for action, resolution in approval_resolutions.items():
            if action in approval_requests and approval_requests[action][0] != resolution[0]:
                pending_approval.add(action)
                contradictory = True
        # The telemetry is untrusted. Only source-local causal ordering can
        # discharge an observed reservation even provisionally; real effect
        # completion still needs independently authenticated ledger evidence.
        prior_reserved: dict[tuple[int, str], list[tuple[str, int]]] = {}
        prior_resolved: dict[tuple[int, str], list[tuple[str, int]]] = {}
        for row in prior_effect_rows:
            event = json.loads(row["event_json"])
            key = (row["attempt"], event["action_id"])
            target = prior_reserved if event["kind"] == "tool.effect_reserved" else prior_resolved
            target.setdefault(key, []).append((row["source"], row["sequence"]))
        missing_prior = sum(int(r["high"]) - int(r["seen"]) for r in prior_seq_counts)
        prior_unresolved = []
        for (past_attempt, action_id), reservations in sorted(prior_reserved.items()):
            resolutions = prior_resolved.get((past_attempt, action_id), [])
            if (len(reservations) != 1 or len(resolutions) != 1
                    or resolutions[0][0] != reservations[0][0]
                    or resolutions[0][1] <= reservations[0][1]):
                prior_unresolved.append({"attempt": past_attempt, "action_id": action_id})
        for resolution, request in ((effect_resolutions, reserved_events),
                                    (approval_resolutions, approval_requests)):
            for action, resolved_by in resolution.items():
                was_started = request.get(action)
                # Source-local sequence establishes causality. Cross-source
                # order is unknown, and these events remain untrusted hints.
                if was_started is None or (was_started[0] == resolved_by[0]
                                           and was_started[1] >= resolved_by[1]):
                    contradictory = True
        terminal_events = [e for e, _ in events if e["kind"] in
                           ("run.reported_completed", "run.reported_failed", "worker.stopped")]
        # Only a source-local sequence is ordered. Contradictory terminal
        # reports from multiple emitters require operator reconciliation.
        terminal_sources = {e["source"] for e in terminal_events}
        if len(terminal_sources) > 1:
            contradictory = True
        terminal_kinds = {e["kind"] for e in terminal_events}
        if {"run.reported_completed", "run.reported_failed"}.issubset(terminal_kinds):
            contradictory = True
        # A source that resumes normal execution after a final report in the
        # SAME attempt has a broken lifecycle contract; demand trace review.
        terminal_seq_by_source = {}
        for e in terminal_events:
            if e["kind"] in ("run.reported_completed", "run.reported_failed"):
                src = e["source"]
                terminal_seq_by_source[src] = min(
                    e["sequence"], terminal_seq_by_source.get(src, e["sequence"])
                )
        for e, _ in events:
            final_seq = terminal_seq_by_source.get(e["source"])
            if (final_seq is not None and e["sequence"] > final_seq
                    and e["kind"] not in ("worker.stopped", "run.reported_completed",
                                           "run.reported_failed")):
                contradictory = True
        # Terminal cause and terminal state must refer to the SAME event,
        # not to different events ordered by network delivery time.
        terminal = max(terminal_events, key=lambda e: e["sequence"]) if terminal_events else None
        last_terminal = terminal["kind"] if terminal else None
        reason = terminal.get("reason_code", "UNKNOWN") if terminal else "UNKNOWN"
        if prior_unresolved or cross_source_effects or (reserved and live_age >= liveness_timeout):
            state, next_action = "NEEDS_RECONCILIATION", "RECONCILE_EFFECT_RECEIPT"
        elif reserved:
            state, next_action = "EFFECT_IN_FLIGHT", "MONITOR_NO_BLIND_RETRY"
        elif clock_reversed:
            state, next_action = "CLOCK_SKEW_DETECTED", "CHECK_MONOTONIC_CLOCK_AND_TIME_SYNC"
        elif contradictory or missing or missing_prior:
            state, next_action = "TRACE_INCOMPLETE", "FETCH_MISSING_EVENTS"
        elif pending_approval:
            state, next_action = "WAITING_APPROVAL", "ASK_AUTHORIZED_REVIEWER"
        elif last_terminal == "run.reported_failed":
            state, next_action = "REPORTED_FAILED", CAUSE_ACTIONS.get(reason, CAUSE_ACTIONS["UNKNOWN"])
        elif last_terminal == "run.reported_completed":
            state, next_action = "AWAITING_VERIFICATION", "VERIFY_ARTIFACTS_AT_EXACT_REVISION"
        elif last_terminal == "worker.stopped":
            state, next_action = "STOPPED_UNCONFIRMED", "RECONCILE_WORKER_STOP"
        elif stale_worker_sources and len(stale_worker_sources) < len(worker_sources):
            state, next_action = "PARTIAL_WORKER_OUTAGE", "CHECK_EACH_WORKER_AND_LEASE"
        elif stale_worker_sources:
            state, next_action = "WORKER_UNRESPONSIVE", "CHECK_WORKER_AND_LEASE"
        elif live_age >= liveness_timeout:
            state, next_action = "WORKER_UNRESPONSIVE", "CHECK_WORKER_AND_LEASE"
        elif progress_age >= progress_timeout:
            state, next_action = "ALIVE_NO_PROGRESS", "INSPECT_STAGE_AND_BUDGET"
        else:
            state, next_action = "RECENT_TELEMETRY", "CONTINUE_OBSERVING"
        return {"run_id": run_id, "attempt": a, "state": state,
                "next_action": next_action, "unresolved_effects": sorted(reserved),
                "pending_approvals": sorted(pending_approval), "missing_sequences": missing,
                "missing_sequences_prior_attempts": missing_prior,
                "unresolved_effects_prior_attempts": prior_unresolved,
                "reported_reason_code": reason if last_terminal == "run.reported_failed" else None,
                "live_age_seconds": round(live_age, 3),
                "progress_age_seconds": round(progress_age, 3),
                "worker_sources_count": len(worker_sources),
                "stale_worker_sources": stale_worker_sources,
                "note": "Untrusted telemetry; only an independent verifier may certify success."}
