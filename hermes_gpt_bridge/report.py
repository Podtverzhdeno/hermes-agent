"""Read-only local SQLite inbox projections for diagnostics and operator reports.

Only metadata admitted by an authorized local inbox is read. The source may
still report fictitious provider states. This never performs repairs or retries.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from urllib.parse import quote

from .diagnostics import Event, TraceError, analyze, summarize

MAX_SNAPSHOT_EVENTS = 100_000


class SnapshotError(ValueError):
    """Sanitized error for missing, corrupt or too-large local snapshots."""


@dataclass(frozen=True)
class Snapshot:
    events: tuple[Event, ...]
    last_offset: int
    quick_check_ok: bool


def load_snapshot(db_path: str | Path, *, limit: int = MAX_SNAPSHOT_EVENTS) -> Snapshot:
    """Read one SQLite WAL snapshot without ever creating the database.

    Event order is durable offset order for the returned rows, but the current
    trace doctor uses UTC timestamps for cross-emitter presentation. Do not
    claim a total causal ordering until the collector offset is made part of
    the projection protocol.
    """
    if type(limit) is not int or not 1 <= limit <= MAX_SNAPSHOT_EVENTS:
        raise SnapshotError("snapshot row limit outside supported range")
    path = Path(db_path).absolute()
    if not path.is_file():
        raise SnapshotError("local inbox database is not available")
    uri = "file:" + quote(path.as_posix(), safe="/:") + "?mode=ro"
    items: list[Event] = []
    offset = 0
    try:
        with closing(sqlite3.connect(uri, uri=True, timeout=5)) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            check = db.execute("PRAGMA quick_check(1)").fetchone()
            if not check or check[0] != "ok":
                raise SnapshotError("inbox database quick check failed")
            cursor = db.execute("SELECT offset,payload FROM ingress_event ORDER BY offset")
            for off, raw in cursor:
                if len(items) >= limit:
                    raise SnapshotError("snapshot exceeds row limit; use a bounded retention/export policy")
                if type(off) is not int or off <= offset:
                    raise SnapshotError("invalid ingestion ordering")
                if not isinstance(raw, str) or len(raw.encode("utf-8")) > 16_384:
                    raise SnapshotError("stored event outside metadata size cap")
                try:
                    obj = json.loads(raw)
                    event = Event.parse(obj)
                except (ValueError, TypeError) as exc:
                    raise SnapshotError("stored event violates schema") from exc
                items.append(event)
                offset = off
            db.execute("COMMIT")
    except sqlite3.DatabaseError as exc:
        raise SnapshotError("inbox database cannot be read") from exc
    return Snapshot(tuple(items), offset, True)


def report(db_path: str | Path, *, stale_after_seconds: int = 120,
           now: datetime | None = None) -> dict:
    """Pure diagnostic JSON snapshot with explicit uncertainty labeling."""
    now = now or datetime.now(timezone.utc)
    snap = load_snapshot(db_path)
    findings = analyze(snap.events, now=now, stale_after_seconds=stale_after_seconds)
    runs = summarize(snap.events, now=now, stale_after_seconds=stale_after_seconds)
    return {
        "report_schema_version": 1,
        "as_of": now.isoformat(),
        "source": "local_sqlite_snapshot",
        "provider_outcomes_trusted": False,
        "database_quick_check_ok": snap.quick_check_ok,
        "last_ingestion_offset": snap.last_offset,
        "event_count": len(snap.events),
        "runs": [run.as_dict() for run in runs],
        "findings": [finding.as_dict() for finding in findings],
    }
