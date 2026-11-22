"""Opt-in read-only status watcher with a durable, deduplicated incident timeline.

This is an observer of a *local* EventJournal, not an ingress adapter, LLM
runner, privileged monitor, scheduler, or trusted verification authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from .journal import EventJournal, JournalConflict


def _fingerprint(assessment: dict) -> str:
    # Never use continuously changing ages as a deduplication key.
    fields = ("attempt", "state", "next_action", "unresolved_effects",
              "pending_approvals", "missing_sequences", "reported_reason_code",
              "stale_worker_sources", "historical_unresolved_effects")
    value = {k: assessment.get(k) for k in fields}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class StatusWatch:
    """Append transitions at most once per changed diagnosis per run, per DB.

    Durable DB write occurs before yielding an alert. A crash after commit
    may suppress duplicate stdout notifications on restart; the transition
    remains queryable in SQLite. No exactly-once external delivery claim.
    """

    def __init__(self, event_db: str | Path, status_db: str | Path,
                 clock: Callable[[], float] = time.time):
        self.clock = clock
        self.events = EventJournal(event_db, clock=clock)
        self.path = Path(status_db)
        if self.events.path.resolve() == self.path.resolve():
            raise ValueError("status_db must be distinct from event_db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS latest (
                    run_id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    observed_at REAL NOT NULL,
                    source_position INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS transitions (
                    position INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    attempt INTEGER,
                    state TEXT NOT NULL,
                    next_action TEXT NOT NULL,
                    observed_at REAL NOT NULL,
                    assessment_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS transitions_run_idx
                    ON transitions(run_id, position);
            """)
        # Backward-compatible, serialized migration for any existing observer
        # status DB created before causal position fencing was introduced.
        with self._db(write=True) as db:
            cols = {r["name"] for r in db.execute("PRAGMA table_info(latest)")}
            if "source_position" not in cols:
                db.execute("ALTER TABLE latest ADD COLUMN source_position INTEGER NOT NULL DEFAULT 0")

    @contextmanager
    def _db(self, write: bool = False):
        db = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
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

    def sample(self, run_id: str, *, now: float | None = None) -> dict | None:
        assessment = self.events.assess(run_id, now=now)
        digest = _fingerprint(assessment)
        observed = float(self.clock() if now is None else now)
        if not 0 <= observed < 1e14:
            raise ValueError("invalid observation time")
        position = assessment.get("event_position", 0)
        with self._db(write=True) as db:
            old = db.execute("""SELECT fingerprint,source_position,observed_at
                FROM latest WHERE run_id=?""", (run_id,)).fetchone()
            if old and (position < old["source_position"] or
                        (position == old["source_position"] and observed < old["observed_at"])):
                # A concurrent observer delivered a newer state while this
                # process was diagnosing an earlier event snapshot.
                return None
            if old and old["fingerprint"] == digest:
                # Even unchanged status advances the causal watermark so
                # an older observer cannot later resurrect stale states.
                db.execute("""UPDATE latest SET source_position=?,observed_at=?
                    WHERE run_id=?""", (position, observed, run_id))
                return None
            db.execute("""INSERT INTO latest(run_id,fingerprint,observed_at,source_position)
                VALUES(?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET
                  fingerprint=excluded.fingerprint,observed_at=excluded.observed_at,
                  source_position=excluded.source_position""",
                (run_id, digest, observed, position))
            db.execute("""INSERT INTO transitions
                (run_id,attempt,state,next_action,observed_at,assessment_json)
                VALUES(?,?,?,?,?,?)""",
                (run_id, assessment.get("attempt"), assessment["state"],
                 assessment["next_action"], observed,
                 json.dumps(assessment, sort_keys=True, separators=(",", ":"))))
        return {"observed_at": observed, "diagnosis": assessment}

    def history(self, run_id: str, limit: int = 1000) -> list[dict]:
        # Bound reads to prevent large incidents from exhausting the process.
        if type(limit) is not int or not 1 <= limit <= 10000:
            raise ValueError("invalid history limit")
        self.events.assess(run_id)
        with self._db() as db:
            rows = db.execute("""SELECT assessment_json FROM transitions
                WHERE run_id=? ORDER BY position DESC LIMIT ?""", (run_id, limit)).fetchall()
        return [json.loads(row["assessment_json"]) for row in reversed(rows)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Opt-in local GPT diagnostic watcher")
    parser.add_argument("--db", required=True, type=Path, help="Local event journal")
    parser.add_argument("--status-db", required=True, type=Path, help="Separate durable alerts DB")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run-id", action="append", help="Run to observe (repeatable)")
    group.add_argument("--all", action="store_true", help="Observe up to 500 latest runs")
    parser.add_argument("--interval", type=float, default=10.0, help="Polling period seconds [1..3600]")
    parser.add_argument("--max-cycles", type=int, default=1,
                        help="1 = snapshot (default); 0 = explicit continuous loop")
    args = parser.parse_args(argv)
    if not 1 <= args.interval <= 3600 or not 0 <= args.max_cycles <= 1_000_000:
        print('{"state":"WATCH_CONFIGURATION_REJECTED"}', file=sys.stderr)
        return 2
    try:
        watch = StatusWatch(args.db, args.status_db)
        cycle = 0
        while args.max_cycles == 0 or cycle < args.max_cycles:
            cycle += 1
            run_ids = watch.events.list_runs() if args.all else args.run_id
            for run_id in run_ids:
                update = watch.sample(run_id)
                if update:
                    print(json.dumps(update, sort_keys=True, ensure_ascii=False), flush=True)
            if args.max_cycles == 0 or cycle < args.max_cycles:
                time.sleep(args.interval)
        return 0
    except KeyboardInterrupt:
        return 0
    except sqlite3.DatabaseError:
        print('{"state":"JOURNAL_INTEGRITY_FAILED"}', file=sys.stderr)
        return 3
    except (JournalConflict, OSError, ValueError):
        print('{"state":"WATCH_INSPECTION_REJECTED"}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
