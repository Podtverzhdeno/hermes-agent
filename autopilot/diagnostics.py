"""Read-only, privacy-minimizing diagnostics over the Autopilot ledger.

No model calls, tool execution, network requests or privileged mutations.
A snapshot reflects persisted data, not the health of any live worker process.
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from .ledger import FAILURE_CODES


class LedgerObserver:
    """Bounded, read-only view suitable for an authenticated control plane.

    Do NOT expose without access control: task names/project ids may be private.
    Deliberately excludes goals, event details, approvals digests, and raw errors.
    """

    def __init__(self, path: str | Path, clock: Callable[[], float] = time.time):
        self.path = Path(path)
        self.clock = clock

    @contextmanager
    def _db(self):
        if not self.path.is_file():
            raise FileNotFoundError(f"ledger database does not exist: {self.path.name}")
        db = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro",
                             uri=True, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA busy_timeout=5000")
            db.execute("PRAGMA query_only=ON")
            yield db
        finally:
            db.close()

    @staticmethod
    def _reason(task, now: float, expired_approval: bool,
                unresolved_effects: int, missing: list[str], failed: list[str]) -> str:
        state = task["status"]
        if task["cancel_requested"] and state not in ("cancelled", "failed", "succeeded"):
            return "CANCELLATION_PENDING"
        if state == "needs_reconciliation" or unresolved_effects and state not in (
            "running", "verifying"
        ):
            return "EXTERNAL_EFFECT_UNCERTAIN"
        if state in ("running", "verifying") and (
            task["lease_until"] is None or task["lease_until"] <= now
        ):
            return "WORKER_LEASE_EXPIRED_NOT_REAPED"
        if state == "waiting_approval":
            return "APPROVAL_EXPIRED_NOT_REAPED" if expired_approval else "WAITING_OWNER_APPROVAL"
        if state == "retry_wait":
            return "RETRY_READY" if task["available_at"] <= now else "RETRY_BACKOFF"
        if state == "queued":
            return "READY_TO_DISPATCH" if task["available_at"] <= now else "SCHEDULED"
        if state == "verifying":
            if failed:
                return "TRUSTED_VERIFICATION_FAILURE"
            if missing:
                return "WAITING_VERIFICATION_EVIDENCE"
        if state == "running":
            return "WORKER_LEASE_ACTIVE"
        return {
            "succeeded": "VERIFIED_COMPLETE", "failed": "ATTEMPTS_OR_HARD_FAILURE",
            "blocked": "BLOCKED_NEEDS_OPERATOR", "cancelled": "CANCELLED",
        }.get(state, "UNKNOWN_STATE")

    def snapshot(self, *, limit: int = 100) -> dict:
        """Return status, likely blocker, and event cursor without raw payloads."""
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError("limit must be integer in 1..500")
        now = self.clock()
        with self._db() as db:
            counts = {row["status"]: row["n"] for row in db.execute(
                "SELECT status,COUNT(*) AS n FROM tasks GROUP BY status"
            )}
            total = sum(counts.values())
            tasks = []
            rows = db.execute("""
                SELECT * FROM tasks ORDER BY updated_at DESC,id LIMIT ?
            """, (limit,)).fetchall()
            for t in rows:
                last = db.execute("""
                    SELECT seq,kind FROM events WHERE task_id=?
                    ORDER BY seq DESC LIMIT 1
                """, (t["id"],)).fetchone()
                last_failure = db.execute("""
                    SELECT detail FROM events WHERE task_id=? AND kind='failed_attempt'
                    ORDER BY seq DESC LIMIT 1
                """, (t["id"],)).fetchone()
                failure_code = None
                if last_failure:
                    try:
                        candidate = json.loads(last_failure["detail"]).get("reason_code")
                        if candidate in FAILURE_CODES or candidate == "UNCLASSIFIED_FAILURE":
                            failure_code = candidate
                    except (TypeError, ValueError, AttributeError):
                        pass
                approval = db.execute("""
                    SELECT MIN(expires_at) AS expires_at
                    FROM approvals WHERE task_id=? AND state='pending'
                """, (t["id"],)).fetchone()
                expiry = approval["expires_at"] if approval else None
                effects = db.execute("""
                    SELECT COUNT(*) AS n FROM actions
                    WHERE task_id=? AND status='reserved'
                """, (t["id"],)).fetchone()["n"]
                required = set(json.loads(t["required_evidence"]))
                missing, failed = [], []
                if t["status"] == "verifying":
                    verified = db.execute("""
                        SELECT kind,conclusion FROM evidence
                        WHERE task_id=? AND revision=? AND trusted=1
                    """, (t["id"], t["revision"])).fetchall()
                    passes = {v["kind"] for v in verified if v["conclusion"] == "passed"}
                    failures = {v["kind"] for v in verified if v["conclusion"] == "failed"}
                    missing = sorted(required - passes)
                    failed = sorted(required & failures)
                tasks.append({
                    "task_id": t["id"],
                    "project": t["project"],
                    "status": t["status"],
                    "reason_code": self._reason(t, now, expiry is not None and expiry <= now,
                                                effects, missing, failed),
                    "attempts": t["attempts"],
                    "max_attempts": t["max_attempts"],
                    "lease_until": t["lease_until"],
                    "next_eligible_at": t["available_at"],
                    "approval_expires_at": expiry,
                    "unresolved_effects": effects,
                    "missing_evidence": missing,
                    "failed_evidence": failed,
                    "cancel_requested": bool(t["cancel_requested"]),
                    "last_event_seq": last["seq"] if last else None,
                    "last_event_kind": last["kind"] if last else None,
                    "last_failure_code": failure_code,
                })
            cursor = db.execute("SELECT COALESCE(MAX(seq),0) AS n FROM events").fetchone()["n"]
        return {"schema_version": 1, "observed_at_epoch": now,
                "total_tasks": total, "status_counts": counts,
                "event_cursor": cursor, "tasks": tasks,
                "monitor_semantics": "ledger_snapshot_only_not_live_worker_heartbeat"}

    def event_headers(self, *, after_seq: int = 0, limit: int = 100) -> list[dict]:
        """Cursor-based event metadata. Details intentionally never leave the DB."""
        if type(after_seq) is not int or after_seq < 0:
            raise ValueError("after_seq must be nonnegative integer")
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError("limit must be integer in 1..500")
        with self._db() as db:
            return [dict(row) for row in db.execute("""
                SELECT seq,task_id,kind,created_at FROM events
                WHERE seq>? ORDER BY seq ASC LIMIT ?
            """, (after_seq, limit))]
