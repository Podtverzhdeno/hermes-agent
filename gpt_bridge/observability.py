"""Durable, content-minimizing observations for Hermes/GPT integration.

This is an *observer*, not a task scheduler, tool executor, authorization
boundary, or proof of a model's completion. No ChatGPT UI automation is used.
Producer authentication and trusted verification belong to future adapters.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Mapping

ZERO_HASH = "0" * 64
OPAQUE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
REASON_CODES = frozenset({
    "AUTH_DENIED", "PERMISSION_DENIED", "RATE_LIMITED", "HTTP_RETRY",
    "MODEL_TIMEOUT", "TOOL_TIMEOUT", "TRANSPORT_LOST", "CDP_DETACHED",
    "APPROVAL_EXPIRED", "EFFECT_UNCERTAIN", "EFFECT_RECONCILED",
    "WORKER_CRASHED", "WORKER_REPLACED", "RUN_CANCELLED",
    "SCHEMA_INVALID", "RESULT_MISMATCH", "VERIFICATION_FAILED",
    "TASK_FAILED", "INTERRUPTED", "SERVICE_UNAVAILABLE", "UNKNOWN",
})
KINDS = frozenset({
    "task.started", "worker.heartbeat", "step.started", "step.finished",
    "model.request_started", "model.request_finished", "tool.started",
    "tool.finished", "transport.connected", "transport.disconnected",
    "cdp.attached", "cdp.detached", "auth.denied", "auth.restored",
    "rate_limited", "rate_limit.cleared", "approval.requested",
    "approval.resolved", "effect.uncertain", "effect.reconciled",
    "verification.passed", "verification.failed", "task.failed",
    "task.cancelled", "task.completed", "worker.replaced",
})
SOURCES = frozenset({"browser_extension", "worker", "tool_gateway", "verifier", "operator", "api_adapter"})
DETAIL_KEYS = frozenset({"step_id", "action_id", "target_id", "channel_id", "request_id",
                         "reason_code", "http_status", "detach_reason", "attempt"})
DETACH_REASONS = frozenset({"target_closed", "canceled_by_user", "unknown"})
MAX_DB_EVENTS_PER_QUERY = 5000


class EventValidationError(ValueError):
    """Unstructured, oversize, or potentially sensitive telemetry rejected."""


class EventConflict(RuntimeError):
    """An event identity or producer sequence was reused inconsistently."""


def _id(name: str, value: Any) -> str:
    if not isinstance(value, str) or not OPAQUE_ID.fullmatch(value):
        raise EventValidationError(f"{name} must be an opaque 1..128 character ID")
    return value


def _positive_int(name: str, value: Any, *, allow_zero: bool = False) -> int:
    if type(value) is not int or not (0 if allow_zero else 1) <= value <= 2**31 - 1:
        raise EventValidationError(f"{name} must be a bounded integer")
    return value


def _details(details: Mapping[str, Any] | None) -> dict[str, Any]:
    if details is None:
        return {}
    if not isinstance(details, dict) or details.keys() - DETAIL_KEYS:
        raise EventValidationError("details must contain only allowlisted structured metadata")
    sanitized: dict[str, Any] = {}
    for key, value in details.items():
        if key in {"step_id", "action_id", "target_id", "channel_id", "request_id"}:
            sanitized[key] = _id(key, value)
        elif key == "reason_code":
            if not isinstance(value, str) or value not in REASON_CODES:
                raise EventValidationError("reason_code must match the fixed v1 reason catalog")
            sanitized[key] = value
        elif key == "http_status":
            if type(value) is not int or not 100 <= value <= 599:
                raise EventValidationError("http_status must be an integer 100..599")
            sanitized[key] = value
        elif key == "attempt":
            sanitized[key] = _positive_int(key, value, allow_zero=True)
        elif key == "detach_reason":
            if value not in DETACH_REASONS:
                raise EventValidationError("detach_reason must match the Chrome API enum")
            sanitized[key] = value
    return sanitized


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


class ObservationStore:
    """Local SQLite append-only event log; safe for multiple Python workers.

    This class deliberately provides *no* mutate/retry/approve action. Event
    source labels are claims until an authenticated adapter binds identity.
    A hash chain detects accidental corruption, not malicious DB rewrites.
    """

    def __init__(self, path: str | Path, *, clock: Callable[[], float] = time.time,
                 readonly: bool = False):
        self.path = Path(path)
        self.clock = clock
        self.readonly = readonly
        if readonly:
            if not self.path.is_file():
                raise FileNotFoundError(self.path)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize()

    @contextmanager
    def _db(self, *, write: bool = False):
        if write and self.readonly:
            raise PermissionError("read-only observation store cannot append")
        target = self.path.resolve().as_uri() + "?mode=ro" if self.readonly else str(self.path)
        db = sqlite3.connect(target, uri=self.readonly, isolation_level=None, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA busy_timeout=10000")
            if not self.readonly:
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

    def _initialize(self) -> None:
        with self._db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS observations (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT UNIQUE NOT NULL,
                    run_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    producer_id TEXT NOT NULL,
                    fence INTEGER NOT NULL,
                    source_seq INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    source TEXT NOT NULL,
                    received_at REAL NOT NULL,
                    payload TEXT NOT NULL,
                    prev_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL,
                    UNIQUE(task_id, producer_id, fence, source_seq)
                );
                CREATE INDEX IF NOT EXISTS observations_by_task
                    ON observations(task_id, fence, sequence);
                CREATE INDEX IF NOT EXISTS observations_by_run
                    ON observations(run_id, sequence);
            """)

    def append(self, *, event_id: str, run_id: str, task_id: str,
               agent_id: str, fence: int, source_seq: int,
               kind: str, source: str, producer_id: str | None = None,
               details: Mapping[str, Any] | None = None) -> int:
        """Append one typed event atomically; replay with same ID is idempotent.

        No free-form prompts, results, URLs, cookies, errors, or tool arguments
        can be stored via this API. A unique producer sequence prevents accidental
        event overwrite from overlapping agents in one lease epoch.
        """
        event = {
            "schema_version": 1,
            "event_id": _id("event_id", event_id),
            "run_id": _id("run_id", run_id),
            "task_id": _id("task_id", task_id),
            "agent_id": _id("agent_id", agent_id),
            "producer_id": _id("producer_id", producer_id if producer_id is not None else agent_id),
            "fence": _positive_int("fence", fence, allow_zero=True),
            "source_seq": _positive_int("source_seq", source_seq),
            "kind": kind,
            "source": source,
            "details": _details(details),
        }
        if kind not in KINDS:
            raise EventValidationError("kind is not in the supported event vocabulary")
        if source not in SOURCES:
            raise EventValidationError("source is not in the supported source vocabulary")
        mandatory = {
            "effect.uncertain": "action_id", "effect.reconciled": "action_id",
            "approval.requested": "action_id", "approval.resolved": "action_id",
            "cdp.attached": "target_id", "cdp.detached": "target_id",
            "transport.connected": "channel_id", "transport.disconnected": "channel_id",
        }
        required_detail = mandatory.get(kind)
        if required_detail and required_detail not in event["details"]:
            raise EventValidationError(f"{kind} requires details.{required_detail}")
        payload = _canonical(event)
        with self._db(write=True) as db:
            existing = db.execute("SELECT sequence,payload FROM observations WHERE event_id=?", (event_id,)).fetchone()
            if existing:
                if existing["payload"] != payload:
                    raise EventConflict("event_id has a different payload")
                return int(existing["sequence"])
            collision = db.execute(
                "SELECT event_id FROM observations WHERE task_id=? AND producer_id=? AND fence=? AND source_seq=?",
                (task_id, event["producer_id"], fence, source_seq),
            ).fetchone()
            if collision:
                raise EventConflict("producer sequence already occupied")
            last = db.execute("SELECT event_hash FROM observations ORDER BY sequence DESC LIMIT 1").fetchone()
            prev_hash = last["event_hash"] if last else ZERO_HASH
            received_at = float(self.clock())
            if not 0 <= received_at <= 1e15 or received_at != received_at:
                raise EventValidationError("clock returned an invalid timestamp")
            digest = hashlib.sha256(f"{prev_hash}|{payload}|{received_at!r}".encode("utf-8")).hexdigest()
            result = db.execute("""
                INSERT INTO observations(event_id,run_id,task_id,agent_id,producer_id,fence,source_seq,kind,source,
                                         received_at,payload,prev_hash,event_hash)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (event_id, run_id, task_id, agent_id, event["producer_id"], fence, source_seq, kind, source,
                  received_at, payload, prev_hash, digest))
            return int(result.lastrowid)

    def timeline(self, *, task_id: str, limit: int = 500) -> list[dict[str, Any]]:
        _id("task_id", task_id)
        if type(limit) is not int or not 1 <= limit <= MAX_DB_EVENTS_PER_QUERY:
            raise EventValidationError("limit out of bounds")
        with self._db() as db:
            rows = db.execute("""
                SELECT sequence,received_at,payload,event_hash FROM observations
                WHERE task_id=? ORDER BY sequence DESC LIMIT ?
            """, (task_id, limit)).fetchall()
        return [{"sequence": row["sequence"], "received_at": row["received_at"],
                 **json.loads(row["payload"]), "event_hash": row["event_hash"]}
                for row in reversed(rows)]

    def verify_chain(self) -> bool:
        """Detect accidental corruption (not proof against an attacker with DB write)."""
        prev_hash = ZERO_HASH
        with self._db() as db:
            for row in db.execute("SELECT payload,received_at,prev_hash,event_hash FROM observations ORDER BY sequence"):
                if row["prev_hash"] != prev_hash:
                    return False
                expected = hashlib.sha256(
                    f"{prev_hash}|{row['payload']}|{row['received_at']!r}".encode("utf-8")
                ).hexdigest()
                if row["event_hash"] != expected:
                    return False
                prev_hash = row["event_hash"]
        return True

    def diagnose_task(self, *, task_id: str, stale_after_seconds: float = 120.0) -> dict[str, Any]:
        """Conservative, streaming incident triage; NEVER authorizes automatic retry.

        Concurrent effects, approval requests, and browser tabs are tracked by
        *separate stable IDs*: a reconnect of tab B cannot clear tab A's failure.
        Only the highest fencing epoch determines current worker liveness;
        unresolved external effects carry across *all* epochs. A read-only
        observer cannot independently confirm worker self-reports.
        """
        _id("task_id", task_id)
        if (type(stale_after_seconds) not in (int, float)
                or not 1 <= stale_after_seconds <= 86400):
            raise EventValidationError("stale_after_seconds must be 1..86400")
        uncertain_effects: dict[str, int] = {}
        pending_approvals: set[str] = set()
        disconnected_channels: set[str] = set()
        detached_targets: dict[str, str] = {}
        auth_blocked = False
        rate_limited = False
        terminal: tuple[str, str] | None = None
        # Receipt order and producer sequence may disagree after replay/restart.
        # Never classify a worker as healthy on an incomplete causal history.
        producer_stats: dict[str, tuple[int, int, int, int]] = {}
        out_of_order_events = 0
        last = None
        with self._db() as db:
            row = db.execute("SELECT MAX(fence) AS f FROM observations WHERE task_id=?", (task_id,)).fetchone()
            fence = row["f"]
            if fence is None:
                return {"task_id": task_id, "status": "unobserved", "reason": "NO_EVENTS",
                        "confidence": "none", "fence": None, "last_event_sequence": None}
            # Side effects are task-global: replacing an agent or advancing
            # its fence does NOT erase an unresolved external mutation. Other
            # diagnostics (tab/transport/approval/terminal) belong only to the
            # latest worker epoch. Receipt order is not external causality.
            cursor = db.execute("""
                SELECT sequence,fence,producer_id,source_seq,kind,received_at,payload FROM observations
                WHERE task_id=? ORDER BY sequence
            """, (task_id,))
            latest_epoch_seen = -1
            for e in cursor:
                epoch = int(e["fence"])
                latest_epoch_seen = max(latest_epoch_seen, epoch)
                k = e["kind"]
                data = json.loads(e["payload"])["details"]
                if k == "effect.uncertain":
                    uncertain_effects.setdefault(data["action_id"], epoch)
                elif k == "effect.reconciled" and epoch >= latest_epoch_seen:
                    # Do not let a late old-fence worker retroactively erase
                    # uncertainty after a replacement worker has started.
                    uncertain_effects.pop(data["action_id"], None)
                if epoch != fence:
                    continue
                producer = e["producer_id"]
                seq = int(e["source_seq"])
                if producer in producer_stats:
                    low, high, count, prev_seq = producer_stats[producer]
                    if seq < prev_seq:
                        out_of_order_events += 1
                    producer_stats[producer] = (min(low, seq), max(high, seq), count + 1, seq)
                else:
                    producer_stats[producer] = (seq, seq, 1, seq)
                last = e
                if k == "approval.requested":
                    pending_approvals.add(data["action_id"])
                elif k == "approval.resolved":
                    pending_approvals.discard(data["action_id"])
                elif k == "cdp.detached":
                    detached_targets[data["target_id"]] = data.get("detach_reason", "unknown")
                elif k == "cdp.attached":
                    detached_targets.pop(data["target_id"], None)
                elif k == "transport.disconnected":
                    disconnected_channels.add(data["channel_id"])
                elif k == "transport.connected":
                    disconnected_channels.discard(data["channel_id"])
                elif k == "auth.denied":
                    auth_blocked = True
                elif k == "auth.restored":
                    auth_blocked = False
                elif k == "rate_limited":
                    rate_limited = True
                elif k == "rate_limit.cleared":
                    rate_limited = False
                elif k == "verification.passed":
                    terminal = ("reported_verified", "VERIFICATION_REPORTED")
                elif k == "verification.failed":
                    terminal = ("reported_failed", "VERIFICATION_FAILED")
                elif k == "task.failed":
                    terminal = ("reported_failed", data.get("reason_code", "TASK_FAILED"))
                elif k == "task.cancelled":
                    terminal = ("reported_cancelled", "TASK_CANCELLED")
                elif k == "task.completed":
                    terminal = ("reported_completed", "COMPLETION_REPORTED")

        assert last is not None
        now = float(self.clock())
        if not 0 <= now <= 1e15 or now != now:
            raise EventValidationError("diagnostic clock returned an invalid timestamp")
        clock_rollback = now + 1 < float(last["received_at"])
        age = max(0.0, now - float(last["received_at"]))
        sequence_gaps = sum(high - low + 1 - count for low, high, count, _ in producer_stats.values())
        if uncertain_effects:
            status, reason = "needs_reconciliation", "EXTERNAL_EFFECT_UNKNOWN"
        elif out_of_order_events:
            status, reason = "observation_inconsistent", "PRODUCER_EVENTS_OUT_OF_ORDER"
        elif sequence_gaps:
            status, reason = "telemetry_incomplete", "PRODUCER_SEQUENCE_GAPS"
        elif clock_rollback:
            status, reason = "observation_inconsistent", "COLLECTOR_CLOCK_ROLLBACK"
        elif pending_approvals:
            status, reason = "waiting_approval", "APPROVAL_PENDING"
        elif auth_blocked:
            status, reason = "auth_blocked", "AUTH_DENIED"
        elif detached_targets:
            status = "integration_unavailable"
            reason = "CDP_DETACHED_" + sorted(detached_targets.values())[0].upper()
        elif disconnected_channels:
            status, reason = "integration_unavailable", "TRANSPORT_DISCONNECTED"
        elif rate_limited:
            status, reason = "rate_limited", "RATE_LIMITED"
        elif terminal:
            status, reason = terminal
        elif age >= stale_after_seconds:
            status, reason = "suspected_stall", "NO_RECENT_OBSERVATIONS"
        else:
            status, reason = "observed_active", "EVENTS_RECEIVED"
        return {"task_id": task_id, "status": status, "reason": reason,
                "confidence": "none" if (out_of_order_events or sequence_gaps or clock_rollback) else "reported_only",
                "fence": fence,
                "producer_out_of_order_events": out_of_order_events,
                "producer_sequence_gaps": sequence_gaps,
                "collector_clock_rollback": clock_rollback,
                "last_event_sequence": int(last["sequence"]),
                "last_event_age_seconds": round(age, 3),
                "open_effects": len(uncertain_effects),
                "open_effects_from_prior_fences": sum(1 for origin in uncertain_effects.values() if origin < fence),
                "pending_approvals": len(pending_approvals)}
