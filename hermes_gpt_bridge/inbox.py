"""Authenticated, durable metadata-event inbox; NOT a task/effect ledger.

No HTTP listener, browser execution, approval, or retry is implemented here.
The future authorized adapter must verify the client and manage HMAC keys,
network bindings, backups, retention, and rate limits. HMAC authenticates a
configured emitter, not the truth of a self-reported provider outcome.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Callable, Mapping

from .diagnostics import Event, TraceError, MAX_LINE_BYTES, MAX_EVENTS, _STABLE_ID

_SIG = re.compile(r"^[0-9a-fA-F]{64}$")


class InboxError(ValueError):
    """Sanitized input, conflict, or authorization error."""


@dataclass(frozen=True)
class IngestReceipt:
    offset: int
    duplicate: bool


@dataclass(frozen=True)
class StoredEvent:
    offset: int
    event: Event


@dataclass(frozen=True)
class InboxHealth:
    quick_check_ok: bool
    journal_mode: str
    row_count: int
    last_offset: int
    last_observed_at: str | None
    db_bytes: int
    wal_bytes: int

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    obj: dict[str, object] = {}
    for key, value in pairs:
        if key in obj:
            raise InboxError("duplicate JSON property")
        obj[key] = value
    return obj


class EventInbox:
    """Append-only single-host SQLite WAL inbox with per-emitter HMAC authentication.

    Invariants:
    - A redelivered identical event returns its original offset; no double insert.
    - Same (run,event_id) with changed bytes is a conflict.
    - Same (run,attempt,emitter,seq) with another event is a conflict.
    - Each event receives a collector UTC timestamp from a trusted clock.
    - The HMAC key never enters DB rows, logs, or exceptions.
    - An inbox receipt means *durably observed metadata*, NOT provider success.

    The SQLite database must live on a local disk, not a network filesystem.
    This class is not a distributed coordination primitive or verifier.
    """

    def __init__(self, db_path: str | Path, emitter_keys: Mapping[str, bytes],
                 *, clock: Callable[[], datetime] | None = None,
                 max_records: int = MAX_EVENTS,
                 max_storage_bytes: int = 128 * 1024 * 1024) -> None:
        if type(max_records) is not int or not 1 <= max_records <= MAX_EVENTS:
            raise InboxError("invalid inbox event capacity")
        if type(max_storage_bytes) is not int or max_storage_bytes < 4096:
            raise InboxError("invalid inbox storage capacity")
        self._max_records = max_records
        self._max_storage_bytes = max_storage_bytes
        if not emitter_keys:
            raise InboxError("at least one authenticated emitter is required")
        self._keys: dict[str, bytes] = {}
        for identity, key in emitter_keys.items():
            if not isinstance(identity, str) or not _STABLE_ID.fullmatch(identity):
                raise InboxError("invalid emitter identity")
            if not isinstance(key, bytes) or len(key) < 32:
                raise InboxError("each emitter key must have at least 32 random bytes")
            self._keys[identity] = bytes(key)
        self._path = Path(db_path)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        if self._path.exists() and not self._path.is_file():
            raise InboxError("database path must be a regular file")
        if not self._path.parent.is_dir():
            raise InboxError("database parent folder does not exist")
        if not self._path.exists():
            try:
                fd = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                pass
            else:
                os.close(fd)
        with closing(self._connect()) as db:
            mode = db.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if str(mode).lower() != "wal":
                raise InboxError("SQLite WAL mode unavailable")
            db.execute("""
                CREATE TABLE IF NOT EXISTS ingress_event (
                    offset INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    attempt_id TEXT NOT NULL,
                    emitter_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    event_id TEXT NOT NULL,
                    raw_sha256 TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    UNIQUE(run_id, event_id),
                    UNIQUE(run_id, attempt_id, emitter_id, seq)
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS ingress_by_run ON ingress_event(run_id, offset)")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(str(self._path), timeout=15, isolation_level=None)
        db.execute("PRAGMA busy_timeout=15000")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def ingest(self, payload: bytes, *, identity: str, signature_hex: str) -> IngestReceipt:
        """Authenticate and append; returns stable receipt, never performs business actions."""
        key = self._keys.get(identity) if isinstance(identity, str) else None
        if key is None:
            raise InboxError("unauthorized emitter")
        if not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_LINE_BYTES:
            raise InboxError("invalid or oversized event")
        if not isinstance(signature_hex, str) or not _SIG.fullmatch(signature_hex):
            raise InboxError("invalid event signature")
        expected = hmac.new(key, payload, sha256).hexdigest()
        if not hmac.compare_digest(expected, signature_hex.lower()):
            raise InboxError("invalid event signature")
        try:
            parsed = json.loads(payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys)
        except (UnicodeError, ValueError) as exc:
            raise InboxError("invalid JSON event") from exc
        try:
            event = Event.parse(parsed)
        except TraceError as exc:
            raise InboxError("event violates metadata-only schema") from exc
        if event.emitter_id != identity:
            raise InboxError("emitter identity mismatch")
        # Hash the semantic, strictly parsed JSON event, not wire whitespace or
        # object-key ordering. The wire bytes remain individually HMAC-signed.
        canonical = json.dumps(parsed, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":")).encode("utf-8")
        digest = sha256(canonical).hexdigest()

        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                existing = db.execute(
                    "SELECT offset, raw_sha256, attempt_id, emitter_id, seq "
                    "FROM ingress_event WHERE run_id=? AND event_id=?",
                    (event.run_id, event.event_id)).fetchone()
                if existing:
                    offset, old_hash, attempt, emitter, seq = existing
                    if (old_hash, attempt, emitter, seq) == (
                            digest, event.attempt_id, event.emitter_id, event.seq):
                        db.commit()
                        return IngestReceipt(offset, True)
                    raise InboxError("event ID collision")
                seq_used = db.execute(
                    "SELECT event_id FROM ingress_event WHERE run_id=? AND attempt_id=? "
                    "AND emitter_id=? AND seq=?",
                    (event.run_id, event.attempt_id, event.emitter_id, event.seq)).fetchone()
                if seq_used:
                    raise InboxError("emitter sequence collision")
                # Capacity checks occur *after* checking exact duplicate replay:
                # a lost receipt can still be deduplicated when the queue is full.
                current_offset = db.execute(
                    "SELECT seq FROM sqlite_sequence WHERE name='ingress_event'").fetchone()
                if current_offset and current_offset[0] >= self._max_records:
                    raise InboxError("inbox capacity exhausted; archive and rotate under operator control")
                wal = Path(str(self._path) + "-wal")
                disk_used = self._path.stat().st_size + (
                    wal.stat().st_size if wal.exists() else 0)
                if disk_used >= self._max_storage_bytes:
                    raise InboxError("inbox storage capacity exhausted; pause emitters")
                observed = self._clock()
                if (not isinstance(observed, datetime) or observed.tzinfo is None
                        or observed.utcoffset() != timezone.utc.utcoffset(observed)):
                    raise InboxError("collector clock must be UTC")
                normalized = dict(parsed)
                normalized["observed_at"] = observed.isoformat()
                metadata = json.dumps(normalized, ensure_ascii=False,
                                      sort_keys=True, separators=(",", ":"))
                cur = db.execute(
                    "INSERT INTO ingress_event(run_id,attempt_id,emitter_id,seq,event_id,raw_sha256,payload) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (event.run_id, event.attempt_id, event.emitter_id, event.seq,
                     event.event_id, digest, metadata))
                offset = cur.lastrowid
                db.commit()
                return IngestReceipt(offset, False)
            except Exception:
                db.rollback()
                raise

    def read_run(self, run_id: str, *, after_offset: int = 0,
                 limit: int = 1000) -> list[StoredEvent]:
        """Page immutable metadata in durable ingestion order; caller controls authorization."""
        if not isinstance(run_id, str) or not _STABLE_ID.fullmatch(run_id):
            raise InboxError("invalid run ID")
        if type(after_offset) is not int or after_offset < 0:
            raise InboxError("invalid cursor")
        if type(limit) is not int or not 1 <= limit <= 5000:
            raise InboxError("invalid page size")
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT offset, payload FROM ingress_event WHERE run_id=? AND offset>? "
                "ORDER BY offset LIMIT ?", (run_id, after_offset, limit)).fetchall()
        return [StoredEvent(offset, Event.parse(json.loads(raw))) for offset, raw in rows]

    def health(self) -> InboxHealth:
        """Operator-only storage-health snapshot; never reports agent success.

        A healthy database does not imply a healthy collector input channel.
        Silence can mean no configured emitters, a host outage, or a failed
        upstream transport; compare with explicit source heartbeats.
        """
        with closing(self._connect()) as db:
            quick = db.execute("PRAGMA quick_check(1)").fetchone()
            mode = str(db.execute("PRAGMA journal_mode").fetchone()[0])
            rows, highest = db.execute(
                "SELECT COUNT(*), MAX(offset) FROM ingress_event").fetchone()
            last = db.execute(
                "SELECT payload FROM ingress_event ORDER BY offset DESC LIMIT 1").fetchone()
        observed = Event.parse(json.loads(last[0])).observed_at.isoformat() if last else None
        wal_path = Path(str(self._path) + "-wal")
        return InboxHealth(
            quick_check_ok=bool(quick and quick[0] == "ok"), journal_mode=mode,
            row_count=int(rows), last_offset=int(highest or 0),
            last_observed_at=observed,
            db_bytes=self._path.stat().st_size,
            wal_bytes=wal_path.stat().st_size if wal_path.exists() else 0,
        )

    def backup_to(self, destination: str | Path) -> int:
        """Create a point-in-time SQLite backup without overwriting any target.

        Backup is an explicit operator action, never an autonomous effect.
        The SQLite Online Backup API is required for WAL consistency; a raw
        filesystem copy of the live *.db is not a trustworthy backup. The
        temporary file is unpublished until verified, then hard-linked to a
        non-existing target atomically on a local filesystem.
        """
        dest = Path(destination)
        if not dest.parent.is_dir():
            raise InboxError("backup parent folder does not exist")
        if dest.exists():
            raise InboxError("backup destination already exists")
        fd, staging = tempfile.mkstemp(prefix=".hermes-inbox-backup-", suffix=".db",
                                       dir=str(dest.parent))
        os.close(fd)
        stage = Path(staging)
        try:
            with closing(self._connect()) as source, closing(sqlite3.connect(staging)) as out:
                source.backup(out)
                quick = out.execute("PRAGMA quick_check(1)").fetchone()
                if not quick or quick[0] != "ok":
                    raise InboxError("backup verification failed")
                count = int(out.execute("SELECT COUNT(*) FROM ingress_event").fetchone()[0])
            # The original target must not be clobbered by a racing creator.
            # An atomic same-filesystem hard link fails when the name exists.
            try:
                os.link(staging, dest)
            except FileExistsError as exc:
                raise InboxError("backup destination already exists") from exc
            except OSError as exc:
                raise InboxError("backup could not be published atomically") from exc
            return count
        finally:
            stage.unlink(missing_ok=True)
