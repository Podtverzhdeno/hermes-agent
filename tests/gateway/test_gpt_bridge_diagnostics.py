"""Contract regression tests for the Hermes OpenAI-compatible GPT bridge."""

import asyncio
import json
import logging
import uuid
from unittest.mock import patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from gateway.config import PlatformConfig
from gateway.platforms.api_server import APIServerAdapter
from gateway.gpt_bridge_diagnostics import (
    IdempotencyCache,
    IdempotencyInProgress,
    IdempotencyPayloadMismatch,
    canonical_fingerprint,
    scoped_idempotency_key,
    log_bridge_event,
)


def test_canonical_fingerprint_covers_full_body_and_key_order():
    assert canonical_fingerprint({"a": 1, "nested": {"z": 1, "a": 2}}) == canonical_fingerprint(
        {"nested": {"a": 2, "z": 1}, "a": 1}
    )
    assert canonical_fingerprint({"messages": [], "temperature": 0}) != canonical_fingerprint(
        {"messages": [], "temperature": 1}
    )


def test_idempotency_key_scoped_by_caller_and_session():
    a = scoped_idempotency_key("key", "Bearer A", "session-a")
    assert a != scoped_idempotency_key("key", "Bearer B", "session-a")
    assert a != scoped_idempotency_key("key", "Bearer A", "session-b")
    assert "Bearer" not in a
    assert len(a) == 64


@pytest.mark.asyncio
async def test_cache_replays_finished_result_only_once():
    cache = IdempotencyCache()
    executions = 0

    async def do_work():
        nonlocal executions
        executions += 1
        return {"ok": True}

    assert await cache.get_or_set("k", "fp", do_work) == {"ok": True}
    assert await cache.get_or_set("k", "fp", do_work) == {"ok": True}
    assert executions == 1
    with pytest.raises(IdempotencyPayloadMismatch):
        await cache.get_or_set("k", "other", do_work)


@pytest.mark.asyncio
async def test_inflight_same_key_is_rejected_not_run_twice():
    cache = IdempotencyCache()
    started, release = asyncio.Event(), asyncio.Event()
    executions = 0

    async def do_work():
        nonlocal executions
        executions += 1
        started.set()
        await release.wait()
        return "done"

    original = asyncio.create_task(cache.get_or_set("k", "fp", do_work))
    await asyncio.wait_for(started.wait(), 2)
    with pytest.raises(IdempotencyInProgress):
        await cache.get_or_set("k", "fp", do_work)
    with pytest.raises(IdempotencyPayloadMismatch):
        await cache.get_or_set("k", "different", do_work)
    release.set()
    assert await original == "done"
    assert await cache.get_or_set("k", "fp", do_work) == "done"
    assert executions == 1


@pytest.mark.asyncio
async def test_distinct_keys_can_progress_in_parallel():
    cache = IdempotencyCache()
    release = asyncio.Event()
    started = []

    async def compute(n):
        started.append(n)
        await release.wait()
        return n

    task_a = asyncio.create_task(cache.get_or_set("a", "fa", lambda: compute(1)))
    task_b = asyncio.create_task(cache.get_or_set("b", "fb", lambda: compute(2)))
    for _ in range(100):
        if len(started) == 2:
            break
        await asyncio.sleep(0)
    assert sorted(started) == [1, 2]
    release.set()
    assert await asyncio.gather(task_a, task_b) == [1, 2]


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_cancel_shared_work():
    cache = IdempotencyCache()
    started, release = asyncio.Event(), asyncio.Event()
    count = 0

    async def work():
        nonlocal count
        count += 1
        started.set()
        await release.wait()
        return 42

    waiter = asyncio.create_task(cache.get_or_set("k", "fp", work))
    await started.wait()
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    with pytest.raises(IdempotencyInProgress):
        await cache.get_or_set("k", "fp", work)
    release.set()
    for _ in range(100):
        if not cache._inflight:
            break
        await asyncio.sleep(0)
    assert await cache.get_or_set("k", "fp", work) == 42
    assert count == 1


@pytest.mark.asyncio
async def test_failure_not_cached_and_ttl_expires():
    cache = IdempotencyCache(ttl_seconds=0.01)
    executions = 0

    async def work():
        nonlocal executions
        executions += 1
        if executions == 1:
            raise RuntimeError("failed")
        return executions

    with pytest.raises(RuntimeError):
        await cache.get_or_set("k", "fp", work)
    await asyncio.sleep(0)
    assert await cache.get_or_set("k", "fp", work) == 2
    assert await cache.get_or_set("k", "fp", work) == 2
    await asyncio.sleep(0.02)
    assert await cache.get_or_set("k", "fp", work) == 3


def test_structured_log_omits_raw_session_and_any_payload(caplog):
    logger = logging.getLogger("test.hermes.bridge")
    secret = "user-private-credential-EXAMPLE"
    with caplog.at_level(logging.INFO, logger="test.hermes.bridge"):
        log_bridge_event(logger, "run-1", "failed", reason_code="STREAM_FAILED",
                         session_id=secret)
    combined = "\n".join(caplog.messages)
    assert secret not in combined
    assert '"run_id": "run-1"' in combined
    assert '"reason_code": "STREAM_FAILED"' in combined
    assert "session_hash" in combined


def _app_and_adapter():
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={}))
    app = web.Application()
    app["api_server_adapter"] = adapter
    app.router.add_post("/v1/chat/completions", adapter._handle_chat_completions)
    return app, adapter


def _chat_body(message="hello", stream=False):
    return {"model": "test", "messages": [{"role": "user", "content": message}],
            "stream": stream}


@pytest.mark.asyncio
async def test_http_parallel_same_key_409_different_body_422_and_replay():
    app, adapter = _app_and_adapter()
    started, release = asyncio.Event(), asyncio.Event()
    calls = 0
    idem = str(uuid.uuid4())

    async def mock_agent(**kwargs):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return ({"final_response": "ok"}, {"input_tokens": 1, "output_tokens": 1,
                                           "total_tokens": 2})

    with patch.object(adapter, "_run_agent", side_effect=mock_agent):
        async with TestClient(TestServer(app)) as client:
            pending = asyncio.create_task(client.post("/v1/chat/completions",
                         json=_chat_body(), headers={"Idempotency-Key": idem}))
            await asyncio.wait_for(started.wait(), timeout=2)
            active = await client.post("/v1/chat/completions", json=_chat_body(),
                                       headers={"Idempotency-Key": idem})
            assert active.status == 409
            assert (await active.json())["error"]["code"] == "idempotency_in_progress"
            mismatch = await client.post("/v1/chat/completions", json=_chat_body("different"),
                                         headers={"Idempotency-Key": idem})
            assert mismatch.status == 422
            release.set()
            first = await pending
            assert first.status == 200
            assert first.headers.get("X-Hermes-Run-Id")
            same = await client.post("/v1/chat/completions", json=_chat_body(),
                                     headers={"Idempotency-Key": idem})
            assert same.status == 200
            assert calls == 1


@pytest.mark.asyncio
async def test_sse_agent_exception_reports_error_without_normal_stop():
    app, adapter = _app_and_adapter()

    async def failing_agent(**kwargs):
        callback = kwargs.get("stream_delta_callback")
        callback("before")
        raise RuntimeError("UNSAFE_SECRET_SHOULD_NOT_APPEAR")

    with patch.object(adapter, "_run_agent", side_effect=failing_agent):
        async with TestClient(TestServer(app)) as client:
            response = await client.post("/v1/chat/completions",
                                         json=_chat_body(stream=True))
            assert response.status == 200
            run_id = response.headers.get("X-Hermes-Run-Id")
            assert run_id and len(run_id) == 32
            wire = await response.text()
            assert "before" in wire
            assert "event: hermes.error" in wire
            assert '"code": "STREAM_FAILED"' in wire
            assert run_id in wire
            assert '"finish_reason": "stop"' not in wire
            assert "UNSAFE_SECRET_SHOULD_NOT_APPEAR" not in wire
            assert "data: [DONE]" in wire


@pytest.mark.asyncio
async def test_sse_success_still_emits_normal_finish():
    app, adapter = _app_and_adapter()

    async def successful_agent(**kwargs):
        kwargs["stream_delta_callback"]("hello")
        return ({"final_response": "hello"}, {"total_tokens": 3})

    with patch.object(adapter, "_run_agent", side_effect=successful_agent):
        async with TestClient(TestServer(app)) as client:
            response = await client.post("/v1/chat/completions",
                                         json=_chat_body(stream=True))
            wire = await response.text()
            assert "hermes.error" not in wire
            assert '"finish_reason": "stop"' in wire
            assert "data: [DONE]" in wire
