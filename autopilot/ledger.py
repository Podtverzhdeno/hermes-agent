"""Durable, fail-closed coordination primitives for Hermes Autopilot.

This module deliberately does NOT execute external tools. Tool adapters must
check authorization, reserve an effect, invoke the tool once and acknowledge
its outcome. After a crash, an unacknowledged effect needs reconciliation.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterable, Optional


ACTIVE = ("running", "verifying")
TERMINAL = ("succeeded", "failed", "cancelled", "blocked")


class LedgerConflict(RuntimeError):
    """A stale worker, invalid transition, or conflicting idempotency key."""


class ApprovalRequired(LedgerConflict):
    """An exact action has not been explicitly approved."""


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class AutopilotLedger:
    """One-host SQLite coordination ledger; not a distributed consensus system.

    Use on a *local* filesystem, not a network share. Each call opens its own
    connection so that SQLite serializes concurrent writers across processes.
    Never expose this object directly as an LLM tool: trusted service methods
    (approve/evidence/reconciliation) require a separate authorization layer.
    """

    def __init__(self, path: str | Path, clock: Callable[[], float] = time.time):
        self.path = Path(path)
        self.clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _db(self, write: bool = False):
        db = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA busy_timeout=10000")
            db.execute("PRAGMA foreign_keys=ON")
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

    def _initialize(self):
        with self._db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    request_key TEXT UNIQUE NOT NULL,
                    project TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    required_evidence TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 0,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL,
                    available_at REAL NOT NULL,
                    owner TEXT,
                    fence INTEGER NOT NULL DEFAULT 0,
                    lease_until REAL,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS task_queue
                    ON tasks(status, available_at, priority);
                CREATE TABLE IF NOT EXISTS actions (
                    task_id TEXT NOT NULL REFERENCES tasks(id),
                    action_key TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_ref TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY(task_id, action_key)
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    task_id TEXT NOT NULL REFERENCES tasks(id),
                    action_key TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    state TEXT NOT NULL,
                    reviewer TEXT,
                    expires_at REAL NOT NULL,
                    PRIMARY KEY(task_id, action_key)
                );
                CREATE TABLE IF NOT EXISTS evidence (
                    task_id TEXT NOT NULL REFERENCES tasks(id),
                    kind TEXT NOT NULL,
                    source TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    conclusion TEXT NOT NULL,
                    artifact_ref TEXT NOT NULL,
                    trusted INTEGER NOT NULL DEFAULT 0,
                    observed_at REAL NOT NULL,
                    PRIMARY KEY(task_id, kind, source, revision)
                );
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL REFERENCES tasks(id),
                    kind TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
            """)

    def _event(self, db, task_id: str, kind: str, detail: dict):
        db.execute(
            "INSERT INTO events(task_id,kind,detail,created_at) VALUES(?,?,?,?)",
            (task_id, kind, _json(detail), self.clock()),
        )

    @staticmethod
    def _task(db, task_id: str):
        row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(task_id)
        return row

    def get(self, task_id: str) -> dict:
        with self._db() as db:
            row = dict(self._task(db, task_id))
            row["required_evidence"] = json.loads(row["required_evidence"])
            return row

    def history(self, task_id: str) -> list[dict]:
        with self._db() as db:
            self._task(db, task_id)
            return [dict(x) for x in db.execute(
                "SELECT * FROM events WHERE task_id=? ORDER BY seq", (task_id,)
            )]

    def submit(
        self,
        *,
        request_key: str,
        project: str,
        goal: str,
        revision: str,
        required_evidence: Iterable[str],
        priority: int = 0,
        max_attempts: int = 3,
    ) -> str:
        """Submission is idempotent only for an *identical* request payload."""
        required = sorted(set(required_evidence))
        if not all((request_key, project, goal, revision)) or not required:
            raise ValueError("request key, project, goal, revision and evidence are required")
        if any(not isinstance(x, str) or not x.strip() for x in required):
            raise ValueError("evidence identifiers must be non-empty strings")
        if not 1 <= max_attempts <= 20:
            raise ValueError("max_attempts must be between 1 and 20")
        now = self.clock()
        with self._db(write=True) as db:
            existing = db.execute(
                "SELECT * FROM tasks WHERE request_key=?", (request_key,)
            ).fetchone()
            if existing:
                fingerprint = (project, goal, revision, _json(required), priority, max_attempts)
                old = (existing["project"], existing["goal"], existing["revision"],
                       existing["required_evidence"], existing["priority"], existing["max_attempts"])
                if fingerprint != old:
                    raise LedgerConflict("request_key reused with different task content")
                return existing["id"]
            task_id = uuid.uuid4().hex
            db.execute("""
                INSERT INTO tasks
                    (id,request_key,project,goal,revision,required_evidence,status,
                     priority,max_attempts,available_at,created_at,updated_at)
                VALUES(?,?,?,?,?,?, 'queued', ?,?,?,?,?)
            """, (task_id, request_key, project, goal, revision, _json(required),
                  priority, max_attempts, now, now, now))
            self._event(db, task_id, "submitted", {"revision": revision})
            return task_id

    def _recover_expired(self, db, now: float):
        expired = db.execute(
            "SELECT * FROM tasks WHERE status IN ('running','verifying') AND lease_until < ?",
            (now,),
        ).fetchall()
        for task in expired:
            unresolved = db.execute(
                "SELECT 1 FROM actions WHERE task_id=? AND status='reserved' LIMIT 1",
                (task["id"],),
            ).fetchone()
            if unresolved:
                target = "needs_reconciliation"
            elif task["cancel_requested"]:
                target = "cancelled"
            elif task["attempts"] >= task["max_attempts"]:
                target = "failed"
            else:
                target = "retry_wait"
            delay = min(3600, 2 ** min(task["attempts"], 10)) if target == "retry_wait" else 0
            db.execute("""
                UPDATE tasks SET status=?, owner=NULL, lease_until=NULL, available_at=?,
                    updated_at=? WHERE id=?
            """, (target, now + delay, now, task["id"]))
            self._event(db, task["id"], "lease_expired", {"next": target})

    def claim(self, worker: str, lease_seconds: int = 120) -> Optional[dict]:
        """Atomic claim with monotone fencing token; expired effects fail closed."""
        if not worker.strip() or not 5 <= lease_seconds <= 3600:
            raise ValueError("invalid worker or lease_seconds")
        now = self.clock()
        with self._db(write=True) as db:
            self._recover_expired(db, now)
            row = db.execute("""
                SELECT id FROM tasks
                WHERE status IN ('queued','retry_wait') AND available_at <= ?
                  AND cancel_requested=0
                ORDER BY priority DESC, created_at, id LIMIT 1
            """, (now,)).fetchone()
            if row is None:
                return None
            task_id = row["id"]
            db.execute("""
                UPDATE tasks SET status='running', owner=?, fence=fence+1,
                    attempts=attempts+1, lease_until=?, updated_at=? WHERE id=?
            """, (worker, now + lease_seconds, now, task_id))
            task = dict(self._task(db, task_id))
            self._event(db, task_id, "claimed", {"worker": worker, "fence": task["fence"]})
            task["required_evidence"] = json.loads(task["required_evidence"])
            return task

    def _assert_worker(self, db, task_id: str, worker: str, fence: int):
        row = self._task(db, task_id)
        if (row["status"] not in ACTIVE or row["owner"] != worker
                or row["fence"] != fence or row["lease_until"] <= self.clock()
                or row["cancel_requested"]):
            raise LedgerConflict("stale/expired lease, cancelled task, or invalid state")
        return row

    def heartbeat(self, task_id: str, worker: str, fence: int, lease_seconds: int = 120):
        if not 5 <= lease_seconds <= 3600:
            raise ValueError("invalid lease_seconds")
        with self._db(write=True) as db:
            self._assert_worker(db, task_id, worker, fence)
            db.execute("UPDATE tasks SET lease_until=?,updated_at=? WHERE id=?",
                       (self.clock() + lease_seconds, self.clock(), task_id))

    def request_approval(
        self, task_id: str, worker: str, fence: int,
        action_key: str, digest: str, expires_at: float,
    ):
        """Pause task; agent does not get to decide its own approval."""
        now = self.clock()
        if not action_key or not digest or expires_at <= now:
            raise ValueError("exact action digest and future expiry are required")
        with self._db(write=True) as db:
            task = self._assert_worker(db, task_id, worker, fence)
            if task["status"] != "running":
                raise LedgerConflict("approval request allowed only while running")
            old = db.execute(
                "SELECT digest FROM approvals WHERE task_id=? AND action_key=?",
                (task_id, action_key),
            ).fetchone()
            if old and old["digest"] != digest:
                raise LedgerConflict("action_key reused with different payload")
            db.execute("""
                INSERT INTO approvals(task_id,action_key,digest,state,expires_at)
                VALUES(?,?,?,'pending',?)
                ON CONFLICT(task_id,action_key)
                    DO UPDATE SET state='pending',reviewer=NULL,expires_at=excluded.expires_at
            """, (task_id, action_key, digest, expires_at))
            db.execute("""
                UPDATE tasks SET status='waiting_approval',owner=NULL,lease_until=NULL,
                    updated_at=? WHERE id=?
            """, (now, task_id))
            self._event(db, task_id, "approval_requested", {"action_key": action_key, "digest": digest})

    def decide_approval(
        self, task_id: str, action_key: str, digest: str, reviewer: str, approve: bool,
    ):
        """TRUSTED CONTROL PLANE ONLY: enforce reviewer identity outside this DB API."""
        if not reviewer.strip():
            raise ValueError("reviewer is required")
        now = self.clock()
        with self._db(write=True) as db:
            task = self._task(db, task_id)
            approval = db.execute(
                "SELECT * FROM approvals WHERE task_id=? AND action_key=?",
                (task_id, action_key),
            ).fetchone()
            if not approval or task["status"] != "waiting_approval":
                raise LedgerConflict("no pending task approval")
            if approval["state"] != "pending" or approval["digest"] != digest:
                raise LedgerConflict("approval mismatch or already decided")
            allowed = bool(approve and approval["expires_at"] > now)
            db.execute("""
                UPDATE approvals SET state=?, reviewer=? WHERE task_id=? AND action_key=?
            """, ("approved" if allowed else "denied", reviewer, task_id, action_key))
            db.execute("""
                UPDATE tasks SET status=?,available_at=?,updated_at=? WHERE id=?
            """, ("queued" if allowed else "blocked", now, now, task_id))
            self._event(db, task_id, "approval_decided",
                        {"action_key": action_key, "approved": allowed, "reviewer": reviewer})

    def reserve_effect(
        self, task_id: str, worker: str, fence: int, action_key: str, digest: str,
    ):
        """Persist a one-shot reservation BEFORE any external side effect.

        An existing reservation MUST NOT be re-issued. Its outcome may be
        unknown after a crash. Call reconcile_effect only with independent proof.
        """
        now = self.clock()
        with self._db(write=True) as db:
            task = self._assert_worker(db, task_id, worker, fence)
            if task["status"] != "running":
                raise LedgerConflict("effects allowed only while running")
            a = db.execute(
                "SELECT * FROM approvals WHERE task_id=? AND action_key=?",
                (task_id, action_key),
            ).fetchone()
            if not a or a["state"] != "approved" or a["digest"] != digest or a["expires_at"] <= now:
                raise ApprovalRequired("explicit matching unexpired approval required")
            old = db.execute(
                "SELECT digest FROM actions WHERE task_id=? AND action_key=?",
                (task_id, action_key),
            ).fetchone()
            if old:
                raise LedgerConflict("action already reserved; reconcile, never blindly retry")
            db.execute("""
                INSERT INTO actions(task_id,action_key,digest,status,created_at,updated_at)
                VALUES(?,?,?,'reserved',?,?)
            """, (task_id, action_key, digest, now, now))
            self._event(db, task_id, "effect_reserved", {"action_key": action_key})

    def acknowledge_effect(
        self, task_id: str, worker: str, fence: int,
        action_key: str, digest: str, result_ref: str,
    ):
        with self._db(write=True) as db:
            self._assert_worker(db, task_id, worker, fence)
            old = db.execute(
                "SELECT * FROM actions WHERE task_id=? AND action_key=?",
                (task_id, action_key),
            ).fetchone()
            if not old or old["status"] != "reserved" or old["digest"] != digest or not result_ref:
                raise LedgerConflict("effect reservation mismatch")
            db.execute("""
                UPDATE actions SET status='acknowledged',result_ref=?,updated_at=?
                WHERE task_id=? AND action_key=?
            """, (result_ref, self.clock(), task_id, action_key))
            self._event(db, task_id, "effect_acknowledged", {"action_key": action_key, "result_ref": result_ref})

    def reconcile_effect(self, task_id: str, action_key: str, outcome: str, proof_ref: str):
        """TRUSTED CONTROL PLANE ONLY; no automatic retrigger on uncertain outcomes."""
        if outcome not in ("acknowledged", "not_executed") or not proof_ref:
            raise ValueError("outcome and independent proof_ref required")
        with self._db(write=True) as db:
            task = self._task(db, task_id)
            if task["status"] != "needs_reconciliation":
                raise LedgerConflict("task not awaiting reconciliation")
            action = db.execute(
                "SELECT * FROM actions WHERE task_id=? AND action_key=?",
                (task_id, action_key),
            ).fetchone()
            if not action or action["status"] != "reserved":
                raise LedgerConflict("no unresolved reservation")
            db.execute("""
                UPDATE actions SET status=?, result_ref=?, updated_at=?
                WHERE task_id=? AND action_key=?
            """, (outcome, proof_ref, self.clock(), task_id, action_key))
            remaining = db.execute(
                "SELECT 1 FROM actions WHERE task_id=? AND status='reserved' LIMIT 1",
                (task_id,),
            ).fetchone()
            if remaining is None:
                target = "cancelled" if task["cancel_requested"] else (
                    "retry_wait" if task["attempts"] < task["max_attempts"] else "failed"
                )
                db.execute("""
                    UPDATE tasks SET status=?, available_at=?, updated_at=? WHERE id=?
                """, (target, self.clock(), self.clock(), task_id))
            self._event(db, task_id, "effect_reconciled",
                        {"action_key": action_key, "outcome": outcome, "proof_ref": proof_ref})

    def record_evidence(
        self, task_id: str, kind: str, source: str, revision: str,
        conclusion: str, artifact_ref: str, *, trusted: bool = False,
    ):
        """Only trusted verifier adapters should ever pass trusted=True."""
        if conclusion not in ("passed", "failed") or not all(
            (kind, source, revision, artifact_ref)
        ):
            raise ValueError("invalid evidence")
        with self._db(write=True) as db:
            self._task(db, task_id)
            db.execute("""
                INSERT INTO evidence
                (task_id,kind,source,revision,conclusion,artifact_ref,trusted,observed_at)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(task_id,kind,source,revision)
                DO UPDATE SET conclusion=excluded.conclusion, artifact_ref=excluded.artifact_ref,
                    trusted=excluded.trusted, observed_at=excluded.observed_at
            """, (task_id, kind, source, revision, conclusion, artifact_ref, int(trusted), self.clock()))
            self._event(db, task_id, "evidence_recorded",
                        {"kind": kind, "source": source, "trusted": trusted, "revision": revision})

    def begin_verification(self, task_id: str, worker: str, fence: int):
        with self._db(write=True) as db:
            task = self._assert_worker(db, task_id, worker, fence)
            if task["status"] != "running":
                raise LedgerConflict("not running")
            pending = db.execute(
                "SELECT 1 FROM actions WHERE task_id=? AND status='reserved' LIMIT 1",
                (task_id,),
            ).fetchone()
            if pending:
                raise LedgerConflict("unknown external effect outcome")
            db.execute("UPDATE tasks SET status='verifying',updated_at=? WHERE id=?",
                       (self.clock(), task_id))
            self._event(db, task_id, "verifying", {})

    def finalize(self, task_id: str, worker: str, fence: int) -> bool:
        """Success only if ALL required evidence is verified at this exact revision."""
        with self._db(write=True) as db:
            task = self._assert_worker(db, task_id, worker, fence)
            if task["status"] != "verifying":
                raise LedgerConflict("verification has not begun")
            required = json.loads(task["required_evidence"])
            passed = {
                x["kind"] for x in db.execute("""
                    SELECT kind FROM evidence WHERE task_id=? AND revision=?
                        AND conclusion='passed' AND trusted=1
                """, (task_id, task["revision"]))
            }
            if not set(required).issubset(passed):
                self._event(db, task_id, "verification_incomplete",
                            {"missing": sorted(set(required) - passed)})
                return False
            db.execute("""
                UPDATE tasks SET status='succeeded', owner=NULL,lease_until=NULL,
                    updated_at=? WHERE id=?
            """, (self.clock(), task_id))
            self._event(db, task_id, "succeeded", {"revision": task["revision"]})
            return True

    def fail(self, task_id: str, worker: str, fence: int, reason: str, retryable: bool):
        with self._db(write=True) as db:
            task = self._assert_worker(db, task_id, worker, fence)
            unresolved = db.execute(
                "SELECT 1 FROM actions WHERE task_id=? AND status='reserved' LIMIT 1",
                (task_id,),
            ).fetchone()
            status = ("needs_reconciliation" if unresolved else
                      "retry_wait" if retryable and task["attempts"] < task["max_attempts"]
                      else "failed")
            available_at = self.clock() + min(3600, 2 ** min(task["attempts"], 10))
            db.execute("""
                UPDATE tasks SET status=?,owner=NULL,lease_until=NULL,available_at=?,
                    updated_at=? WHERE id=?
            """, (status, available_at, self.clock(), task_id))
            self._event(db, task_id, "failed_attempt", {"reason": reason[:500], "next": status})

    def cancel(self, task_id: str):
        """Cancellation is cooperative for leased workers; no silent rollback."""
        with self._db(write=True) as db:
            task = self._task(db, task_id)
            if task["status"] in TERMINAL:
                return
            immediate = task["status"] in ("queued", "retry_wait", "waiting_approval")
            db.execute("""
                UPDATE tasks SET cancel_requested=1,status=?, updated_at=? WHERE id=?
            """, ("cancelled" if immediate else task["status"], self.clock(), task_id))
            self._event(db, task_id, "cancel_requested", {"immediate": immediate})
