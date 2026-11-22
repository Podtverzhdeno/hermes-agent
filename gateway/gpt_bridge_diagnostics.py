"""Content-free diagnostics and process-local idempotency for the GPT API bridge.

This is deliberately NOT the authoritative durable ledger. Cross-process
deduplication and external-effect reconciliation belong to autopilot/ledger.
"""

import asyncio
from collections import OrderedDict
from datetime import datetime, timezone
import hashlib
import json
import logging
import time
from typing import Any, Callable, Awaitable


class IdempotencyInProgress(Exception):
    """A matching request is currently executing; reply 409, do not dispatch."""


class IdempotencyPayloadMismatch(Exception):
    """An idempotency key was reused with a different payload; reply 422."""


def canonical_fingerprint(body: dict) -> str:
    """Fingerprint the whole JSON payload, not an incomplete field subset."""
    encoded = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def scoped_idempotency_key(key: str, authorization: str = "",
                           client_session_id: str = "") -> str:
    """Avoid cross-session/caller cache aliasing; never persist raw auth data."""
    raw = "\x00".join((authorization, client_session_id, key))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class IdempotencyCache:
    """Process-local, event-loop-owned cache with single-flight rejection.

    Different keys execute concurrently. A duplicate in flight is rejected
    immediately (409), not awaited, because waiting clients may disconnect.
    Waiter cancellation does not cancel the underlying computation; the task
    finishes and is cached in its done callback. Do not use this as a
    cluster-wide or external-side-effect exactly-once guarantee.
    """

    def __init__(self, max_items: int = 1000, ttl_seconds: int = 300):
        if max_items < 1 or ttl_seconds <= 0:
            raise ValueError("max_items and ttl_seconds must be positive")
        self._store: OrderedDict[str, tuple[str, Any, float]] = OrderedDict()
        self._inflight: dict[str, tuple[str, asyncio.Task]] = {}
        self._ttl = ttl_seconds
        self._max = max_items

    def _purge(self) -> None:
        now = time.monotonic()
        for key, (_, _, timestamp) in list(self._store.items()):
            if now - timestamp > self._ttl:
                self._store.pop(key, None)
        while len(self._store) > self._max:
            self._store.popitem(last=False)

    async def get_or_set(self, key: str, fingerprint: str,
                         compute_coro: Callable[[], Awaitable[Any]]) -> Any:
        self._purge()
        cached = self._store.get(key)
        if cached is not None:
            if cached[0] != fingerprint:
                raise IdempotencyPayloadMismatch()
            self._store.move_to_end(key)
            return cached[1]

        active = self._inflight.get(key)
        if active is not None:
            if active[0] != fingerprint:
                raise IdempotencyPayloadMismatch()
            raise IdempotencyInProgress()

        task = asyncio.create_task(compute_coro())
        self._inflight[key] = (fingerprint, task)

        def finalize(done: asyncio.Task) -> None:
            current = self._inflight.get(key)
            if current is None or current[1] is not done:
                return
            self._inflight.pop(key, None)
            try:
                result = done.result()
            except BaseException:
                # An unsuccessful/unknown operation must never be cached
                # as success. Reconciliation of tool side effects is separate.
                return
            self._store[key] = (fingerprint, result, time.monotonic())
            self._store.move_to_end(key)
            self._purge()

        task.add_done_callback(finalize)
        return await asyncio.shield(task)


def log_bridge_event(logger: logging.Logger, run_id: str, event: str,
                     *, reason_code: str | None = None,
                     session_id: str | None = None) -> None:
    """Structured operational event; deliberately never accepts raw payloads.

    These are process logs only; they are not durable transition commits.
    The event is safe to export to an ordinary app log sink.
    """
    record = {
        "schema_version": 1,
        "run_id": run_id,
        "event": event,
        "reason_code": reason_code,
        "session_hash": (
            hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:16]
            if session_id else None
        ),
        "transport": "openai_compat",
        "ts_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
    }
    logger.info("hermes.gpt_bridge %s", json.dumps(record, sort_keys=True))
