"""Regression tests for safe idempotent GPT/OpenAI-compatible API calls."""

import asyncio
from unittest.mock import MagicMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from gateway.config import PlatformConfig
from gateway.platforms.api_server import (
    APIServerAdapter,
    ResponseStore,
    _IdempotencyCache,
    IdempotencyConflictError,
    IdempotencyCapacityError,
)


@pytest.mark.asyncio
async def test_same_key_while_running_joins_one_execution():
    cache = _IdempotencyCache()
    release = asyncio.Event()
    entered = asyncio.Event()
    count = 0

    async def compute():
        nonlocal count
        count += 1
        entered.set()
        await release.wait()
        return {"id": "same-response"}

    first = asyncio.create_task(cache.get_or_set("k", "fp", compute))
    await entered.wait()
    second = asyncio.create_task(cache.get_or_set("k", "fp", compute))
    await asyncio.sleep(0)
    assert count == 1
    release.set()
    assert await first == await second == {"id": "same-response"}
    assert await cache.get_or_set("k", "fp", compute) == {"id": "same-response"}
    assert count == 1


@pytest.mark.asyncio
async def test_reused_key_with_different_fingerprint_rejected():
    cache = _IdempotencyCache()

    async def compute():
        return "ok"

    assert await cache.get_or_set("k", "first", compute) == "ok"
    with pytest.raises(IdempotencyConflictError):
        await cache.get_or_set("k", "second", compute)


@pytest.mark.asyncio
async def test_pending_key_conflict_does_not_replace_first():
    cache = _IdempotencyCache()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def compute():
        entered.set()
        await release.wait()
        return 42

    first = asyncio.create_task(cache.get_or_set("k", "first", compute))
    await entered.wait()
    with pytest.raises(IdempotencyConflictError):
        await cache.get_or_set("k", "changed", compute)
    release.set()
    assert await first == 42


@pytest.mark.asyncio
async def test_cancelling_waiter_does_not_cancel_shared_execution():
    cache = _IdempotencyCache()
    entered = asyncio.Event()
    release = asyncio.Event()
    count = 0

    async def compute():
        nonlocal count
        count += 1
        entered.set()
        await release.wait()
        return 5

    first = asyncio.create_task(cache.get_or_set("k", "fp", compute))
    await entered.wait()
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    second = asyncio.create_task(cache.get_or_set("k", "fp", compute))
    release.set()
    assert await second == 5
    assert count == 1


@pytest.mark.asyncio
async def test_capacity_does_not_evict_pending_operation():
    cache = _IdempotencyCache(max_items=1)
    release = asyncio.Event()
    entered = asyncio.Event()

    async def work():
        entered.set()
        await release.wait()
        return 1

    running = asyncio.create_task(cache.get_or_set("k1", "fp", work))
    await entered.wait()
    with pytest.raises(IdempotencyCapacityError):
        await cache.get_or_set("k2", "fp", work)
    release.set()
    assert await running == 1


@pytest.mark.asyncio
async def test_failed_result_not_cached():
    cache = _IdempotencyCache()
    tries = 0

    async def work():
        nonlocal tries
        tries += 1
        if tries == 1:
            raise RuntimeError("offline")
        return "success"

    with pytest.raises(RuntimeError):
        await cache.get_or_set("k", "fp", work)
    # Allow completion callback to run and evict the failed task.
    await asyncio.sleep(0)
    assert await cache.get_or_set("k", "fp", work) == "success"
    assert tries == 2


def _app(adapter):
    app = web.Application()
    app.router.add_post("/v1/chat/completions", adapter._handle_chat_completions)
    app.router.add_post("/v1/responses", adapter._handle_responses)
    return app


def _adapter():
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={"key": "test-key"}))
    adapter._response_store.close()
    adapter._response_store = ResponseStore(db_path=":memory:")
    return adapter


@pytest.mark.asyncio
async def test_chat_retry_replays_same_ids_and_runs_agent_once():
    adapter = _adapter()
    calls = []
    async def fake_run(**kwargs):
        calls.append(kwargs)
        await asyncio.sleep(0.01)
        return {"final_response": "ok"}, {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3}
    adapter._run_agent = fake_run
    headers = {"Authorization": "Bearer test-key", "Idempotency-Key": "chat-retry"}
    payload = {"model": "hermes-agent", "messages": [{"role": "user", "content": "hello"}]}

    async with TestClient(TestServer(_app(adapter))) as client:
        first, second = await asyncio.gather(
            client.post("/v1/chat/completions", json=payload, headers=headers),
            client.post("/v1/chat/completions", json=payload, headers=headers),
        )
        assert first.status == second.status == 200
        data1, data2 = await first.json(), await second.json()
        assert data1 == data2
        assert first.headers["X-Hermes-Session-Id"] == second.headers["X-Hermes-Session-Id"]
        third = await client.post("/v1/chat/completions", json=payload, headers=headers)
        assert (await third.json()) == data1
        assert len(calls) == 1
    adapter._response_store.close()


@pytest.mark.asyncio
async def test_chat_conflicting_key_or_session_returns_409():
    adapter = _adapter()
    adapter._session_db = MagicMock()
    adapter._session_db.get_messages_as_conversation.return_value = []

    async def fake_run(**kwargs):
        return {"final_response": "ok"}, {}
    adapter._run_agent = fake_run
    headers = {"Authorization": "Bearer test-key", "Idempotency-Key": "same"}
    payload = {"messages": [{"role": "user", "content": "hello"}]}
    async with TestClient(TestServer(_app(adapter))) as client:
        ok = await client.post("/v1/chat/completions", json=payload, headers=headers)
        assert ok.status == 200
        changed = await client.post("/v1/chat/completions", json={
            "messages": [{"role": "user", "content": "different"}],
        }, headers=headers)
        assert changed.status == 409
        different_session = await client.post(
            "/v1/chat/completions", json=payload,
            headers={**headers, "X-Hermes-Session-Id": "other-session"},
        )
        assert different_session.status == 409
    adapter._response_store.close()


@pytest.mark.asyncio
async def test_responses_retry_replays_same_stored_response():
    adapter = _adapter()
    calls = 0
    async def fake_run(**kwargs):
        nonlocal calls
        calls += 1
        return {"final_response": "done", "messages": []}, {}
    adapter._run_agent = fake_run
    headers = {"Authorization": "Bearer test-key", "Idempotency-Key": "responses-key"}
    async with TestClient(TestServer(_app(adapter))) as client:
        results = []
        for _ in range(2):
            response = await client.post("/v1/responses", json={
                "input": "hi", "conversation": "conversation-a",
            }, headers=headers)
            assert response.status == 200
            results.append(await response.json())
        assert results[0] == results[1]
        assert len(adapter._response_store) == 1
        assert adapter._response_store.get_conversation("conversation-a") == results[0]["id"]
        assert calls == 1
    adapter._response_store.close()


@pytest.mark.asyncio
async def test_idempotency_is_endpoint_scoped_and_stream_is_rejected():
    adapter = _adapter()
    calls = 0
    async def fake_run(**kwargs):
        nonlocal calls
        calls += 1
        return {"final_response": "ok", "messages": []}, {}
    adapter._run_agent = fake_run
    headers = {"Authorization": "Bearer test-key", "Idempotency-Key": "shared-across-endpoints"}
    async with TestClient(TestServer(_app(adapter))) as client:
        chat = await client.post("/v1/chat/completions", json={
            "messages": [{"role": "user", "content": "hi"}],
        }, headers=headers)
        resp = await client.post("/v1/responses", json={"input": "hi"}, headers=headers)
        stream = await client.post("/v1/chat/completions", json={
            "stream": True,
            "messages": [{"role": "user", "content": "hi"}],
        }, headers=headers)
        assert chat.status == resp.status == 200
        assert stream.status == 400
        assert calls == 2
    adapter._response_store.close()
