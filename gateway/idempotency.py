"""In-process idempotency for the Hermes API adapter.

The single-flight guarantee applies to one asyncio event loop / adapter only.
It does not substitute for durable, cross-process claim/lease coordination.
"""

import asyncio
from collections import OrderedDict
from hashlib import sha256
import json
import logging
import time
from typing import Any, Dict

logger = logging.getLogger(__name__)


class IdempotencyConflict(Exception):
    """An idempotency key was previously used with another fingerprint."""


class IdempotencyOverloaded(Exception):
    """Maximum simultaneous unique idempotent operations reached."""


def request_fingerprint(body: Dict[str, Any], session_id: str = "") -> str:
    """Return a canonical fingerprint for the entire request and session."""
    payload = {"body": body, "session_id": session_id}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False)
    return sha256(raw.encode("utf-8")).hexdigest()


class IdempotencyCache:
    """Bounded, event-loop-local cache with shielded in-flight coalescing.

    No await occurs between the key lookup and task registration, making
    that sequence atomic to coroutine peers on the SAME event loop.
    An HTTP request cancellation does not cancel the shared operation.
    """

    def __init__(self, max_items: int = 1000, ttl_seconds: float = 300):
        if max_items < 1 or ttl_seconds <= 0:
            raise ValueError("Positive max_items and ttl_seconds are required")
        self._max_items = max_items
        self._ttl_seconds = ttl_seconds
        self._completed = OrderedDict()
        self._inflight = {}

    def _purge(self) -> None:
        now = time.monotonic()
        for key, value in list(self._completed.items()):
            if now - value["completed_at"] >= self._ttl_seconds:
                self._completed.pop(key, None)
        while len(self._completed) > self._max_items:
            self._completed.popitem(last=False)

    async def get_or_set(self, key: str, fingerprint: str, compute_coro):
        self._purge()
        completed = self._completed.get(key)
        if completed is not None:
            if completed["fingerprint"] != fingerprint:
                raise IdempotencyConflict()
            self._completed.move_to_end(key)
            return completed["value"]

        active = self._inflight.get(key)
        if active is not None:
            if active["fingerprint"] != fingerprint:
                raise IdempotencyConflict()
            task = active["task"]
        else:
            if len(self._inflight) >= self._max_items:
                raise IdempotencyOverloaded()

            async def execute():
                try:
                    value = await compute_coro()
                    self._completed[key] = {
                        "value": value,
                        "fingerprint": fingerprint,
                        "completed_at": time.monotonic(),
                    }
                    self._purge()
                    return value
                finally:
                    current = self._inflight.get(key)
                    if current is not None and current["task"] is asyncio.current_task():
                        self._inflight.pop(key, None)

            task = asyncio.create_task(execute())
            self._inflight[key] = {"fingerprint": fingerprint, "task": task}

            def observe_completion(done):
                # Consume exceptions even when every HTTP waiter disconnected.
                if not done.cancelled():
                    failure = done.exception()
                    if failure is not None:
                        logger.warning("Idempotent operation failed: %s", type(failure).__name__)

            task.add_done_callback(observe_completion)

        return await asyncio.shield(task)
