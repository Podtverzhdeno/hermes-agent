"""Deterministic, read-only Autopilot operator projection.

This is a diagnostic projection, not a task runner, policy authority or health
probe for remote tools. It intentionally returns no secrets, prompt transcripts,
raw action arguments or effect receipts.
"""

from __future__ import annotations

import json
import time
from typing import Callable

from .ledger import AutopilotLedger


def inspect_project(
    ledger: AutopilotLedger,
    project: str,
    *,
    clock: Callable[[], float] = time.time,
    limit: int = 100,
) -> dict:
    """Return one consistent snapshot of project coordination state.

    Operator must distinguish unavailable/unverified external service health
    from this local database's health. Display cannot assert that a GitHub
    PR, Obsidian sync or running agent actually succeeded.
    """
    if not isinstance(project, str) or not project.strip():
        raise ValueError("project is required")
    if not 1 <= limit <= 200:
        raise ValueError("limit must be between 1 and 200")
    now = clock()
    with ledger._db() as db:  # single pinned SQLite snapshot
        db.execute("BEGIN")
        try:
            control = db.execute(
                "SELECT stopped, generation FROM project_controls WHERE project=?",
                (project,),
            ).fetchone()
            statuses = db.execute("""
                SELECT status, COUNT(*) AS n FROM tasks WHERE project=?
                GROUP BY status
            """, (project,)).fetchall()
            counts = {x["status"]: x["n"] for x in statuses}
            total = sum(counts.values())
            pending_effects = db.execute("""
                SELECT COUNT(*) FROM actions JOIN tasks ON actions.task_id=tasks.id
                WHERE tasks.project=? AND actions.status='reserved'
            """, (project,)).fetchone()[0]
            waiting_approvals = db.execute("""
                SELECT COUNT(*) FROM approvals JOIN tasks ON approvals.task_id=tasks.id
                WHERE tasks.project=? AND tasks.status='waiting_approval'
                  AND approvals.state='pending' AND approvals.expires_at>?
            """, (project, now)).fetchone()[0]
            expired_approvals = db.execute("""
                SELECT COUNT(*) FROM approvals JOIN tasks ON approvals.task_id=tasks.id
                WHERE tasks.project=? AND tasks.status='waiting_approval'
                  AND approvals.state='pending' AND approvals.expires_at<=?
            """, (project, now)).fetchone()[0]
            expired_workers = db.execute("""
                SELECT COUNT(*) FROM tasks
                WHERE project=? AND status IN ('running','verifying')
                  AND lease_until<=?
            """, (project, now)).fetchone()[0]
            rows = db.execute("""
                SELECT id, goal, status, revision, attempts, max_attempts,
                       required_evidence, lease_until, updated_at, cancel_requested
                FROM tasks WHERE project=?
                ORDER BY
                    CASE status
                      WHEN 'needs_reconciliation' THEN 0
                      WHEN 'waiting_approval' THEN 1
                      WHEN 'blocked' THEN 2
                      WHEN 'verifying' THEN 3
                      WHEN 'running' THEN 4
                      WHEN 'failed' THEN 5
                      ELSE 6 END,
                    updated_at DESC, id LIMIT ?
            """, (project, limit)).fetchall()
            cards = []
            for task in rows:
                missing = []
                if task["status"] == "verifying":
                    passed = {
                        r["kind"] for r in db.execute("""
                            SELECT kind FROM evidence
                            WHERE task_id=? AND revision=?
                              AND conclusion='passed' AND trusted=1
                        """, (task["id"], task["revision"]))
                    }
                    missing = sorted(set(json.loads(task["required_evidence"])) - passed)
                cards.append({
                    "task_id": task["id"],
                    "goal": task["goal"],
                    "status": task["status"],
                    "revision": task["revision"],
                    "attempts": task["attempts"],
                    "max_attempts": task["max_attempts"],
                    "cancel_requested": bool(task["cancel_requested"]),
                    "stale_worker": task["status"] in ("running", "verifying")
                                    and task["lease_until"] is not None
                                    and task["lease_until"] <= now,
                    "missing_evidence": missing,
                    # Never emit approval digest, tool arguments, receipts or secrets.
                })
            db.execute("ROLLBACK")
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise

    stopped = bool(control and control["stopped"])
    generation = int(control["generation"]) if control else 0
    if pending_effects:
        urgency, next_step = ("critical", "reconcile_reserved_external_effects")
    elif stopped:
        urgency, next_step = ("paused", "owner_must_resume_or_close")
    elif expired_approvals:
        urgency, next_step = ("attention", "expire_or_review_approvals")
    elif waiting_approvals:
        urgency, next_step = ("attention", "owner_approval_required")
    elif expired_workers:
        urgency, next_step = ("attention", "reclaim_stale_workers")
    elif counts.get("blocked", 0):
        urgency, next_step = ("attention", "resolve_blockers")
    elif counts.get("failed", 0):
        urgency, next_step = ("attention", "inspect_failed_tasks")
    elif counts.get("verifying", 0):
        urgency, next_step = ("active", "await_independent_evidence")
    elif counts.get("running", 0):
        urgency, next_step = ("active", "monitor_worker_lease")
    elif counts.get("queued", 0) or counts.get("retry_wait", 0):
        urgency, next_step = ("queued", "await_bounded_dispatch")
    else:
        urgency, next_step = ("idle", "no_dispatchable_work")

    return {
        "schema_version": 1,
        "project": project,
        "generated_at_unix": now,
        "project_stopped": stopped,
        "revocation_generation": generation,
        "tasks_total": total,
        "task_status_counts": counts,
        "unknown_external_effects": pending_effects,
        "waiting_owner_approvals": waiting_approvals,
        "expired_owner_approvals": expired_approvals,
        "expired_worker_leases": expired_workers,
        "urgency": urgency,
        "next_step": next_step,
        "tasks_shown": len(cards),
        "tasks_truncated": total > len(cards),
        "tasks": cards,
        "verification_scope": "local_ledger_only",
        "remote_work_verified": False,
    }
