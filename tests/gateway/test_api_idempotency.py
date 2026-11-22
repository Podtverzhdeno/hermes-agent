"""Regression coverage for in-process API idempotency semantics."""

import asyncio
from unittest.mock import AsyncMock, patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
import pytest

from gateway.config import PlatformConfig
from gateway.idempotency import (
    IdempotencyCache, IdempotencyConflict, IdempotencyOverloaded,
    request_fingerprint,
)
from gateway.platforms.api_server import APIServerAdapter


@pytest.mark.asyncio
async def test_same_key_parallel_runs_once():
    cache = IdempotencyCache()
    calls = 0
    gate = asyncio.Event()

    async def compute():
        nonlocal calls
        calls += 1
        await gate.wait()
        return {"ok": True}

    a = asyncio.create_task(cache.get_or_set("key", "fp", compute))
    b = asyncio.create_task(cache.get_or_set("key", "fp", compute))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert calls == 1
    gate.set()
    assert await asyncio.gather(a, b) == [{"ok": True}] * 2


@pytest.mark.asyncio
async def test_key_collision_fails_before_and_after_completion():
    cache = IdempotencyCache()
    gate = asyncio.Event()
    task = asyncio.create_task(cache.get_or_set("key", "A", lambda: gate.wait()))
    await asyncio.sleep(0)
    with pytest.raises(IdempotencyConflict):
        await cache.get_or_set("key", "B", lambda: None)
    gate.set()
    await task
    with pytest.raises(IdempotencyConflict):
        await cache.get_or_set("key", "B", lambda: None)


@pytest.mark.asyncio
async def test_cancelled_client_does_not_cancel_shared_work():
    cache = IdempotencyCache()
    gate = asyncio.Event()
    calls = 0

    async def compute():
        nonlocal calls
        calls += 1
        await gate.wait()
        return 42

    a = asyncio.create_task(cache.get_or_set("k", "f", compute))
    await asyncio.sleep(0)
    a.cancel()
    with pytest.raises(asyncio.CancelledError):
        await a
    gate.set()
    assert await cache.get_or_set("k", "f", compute) == 42
    assert calls == 1


@pytest.mark.asyncio
async def test_error_is_not_cached():
    cache = IdempotencyCache()
    calls = 0

    async def compute():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("not ready")
        return "ok"

    with pytest.raises(RuntimeError):
        await cache.get_or_set("k", "f", compute)
    assert await cache.get_or_set("k", "f", compute) == "ok"
    assert calls == 2


@pytest.mark.asyncio
async def test_capacity_only_applies_to_distinct_active_keys():
    cache = IdempotencyCache(max_items=1)
    gate = asyncio.Event()
    a = asyncio.create_task(cache.get_or_set("k1", "f1", lambda: gate.wait()))
    await asyncio.sleep(0)
    with pytest.raises(IdempotencyOverloaded):
        await cache.get_or_set("k2", "f2", lambda: gate.wait())
    gate.set()
    await a


@pytest.mark.asyncio
async def test_expired_cached_result_recomputes():
    cache = IdempotencyCache(ttl_seconds=.001)
    count = 0

    async def compute():
        nonlocal count
        count += 1
        return count

    assert await cache.get_or_set("k", "f", compute) == 1
    await asyncio.sleep(.005)
    assert await cache.get_or_set("k", "f", compute) == 2


def test_fingerprint_canonical_and_session_scoped():
    assert request_fingerprint({"a": 1, "b": [2, 3]}, "s") == (
        request_fingerprint({"b": [2, 3], "a": 1}, "s")
    )
    assert request_fingerprint({"a": 1}, "s1") != request_fingerprint({"a": 1}, "s2")


def _make_app(adapter):
    app = web.Application()
    app.router.add_post("/v1/chat/completions", adapter._handle_chat_completions)
    app.router.add_post("/v1/responses", adapter._handle_responses)
    return app


@pytest.mark.asyncio
async def test_endpoint_coalesces_same_request_and_preserves_identity():
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={}))
    gate = asyncio.Event()

    async def run_agent(**kwargs):
        await gate.wait()
        return (
            {"final_response": "hello"},
            {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
        )

    body = {"model": "hermes-agent", "messages": [{"role": "user", "content": "ping"}]}
    headers = {"Idempotency-Key": "same-key"}
    async with TestClient(TestServer(_make_app(adapter))) as client:
        with patch.object(adapter, "_run_agent", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = run_agent
            first = asyncio.create_task(
                client.post("/v1/chat/completions", json=body, headers=headers)
            )
            await asyncio.sleep(0)
            second = asyncio.create_task(
                client.post("/v1/chat/completions", json=body, headers=headers)
            )
            await asyncio.sleep(.01)
            gate.set()
            resp1, resp2 = await asyncio.gather(first, second)
            data1, data2 = await asyncio.gather(resp1.json(), resp2.json())
            assert resp1.status == 200 and resp2.status == 200
            assert data1 == data2
            assert resp1.headers["X-Hermes-Session-Id"] == (
                resp2.headers["X-Hermes-Session-Id"]
            )
            assert mock_run.call_count == 1


@pytest.mark.asyncio
async def test_endpoint_rejects_reused_key_with_other_payload():
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={}))
    async with TestClient(TestServer(_make_app(adapter))) as client:
        with patch.object(adapter, "_run_agent", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = ({"final_response": "ok"}, {})
            r1 = await client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "A"}]},
                headers={"Idempotency-Key": "shared"},
            )
            assert r1.status == 200
            r2 = await client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "B"}]},
                headers={"Idempotency-Key": "shared"},
            )
            assert r2.status == 409
            assert (await r2.json())["error"]["code"] == "idempotency_key_conflict"
            assert mock_run.call_count == 1


@pytest.mark.asyncio
async def test_endpoint_returns_no_internal_exception_details():
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={}))
    async with TestClient(TestServer(_make_app(adapter))) as client:
        with patch.object(
            adapter, "_run_agent", new_callable=AsyncMock,
            side_effect=RuntimeError("secret token")
        ):
            r = await client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "A"}]},
                headers={"Idempotency-Key": "err"},
            )
            assert r.status == 500
            assert "secret token" not in await r.text()


@pytest.mark.asyncio
async def test_responses_retry_preserves_id_and_commits_once():
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={}))
    headers = {"Idempotency-Key": "resp-key"}
    payload = {"model": "hermes-agent", "input": "hello", "store": True}
    async with TestClient(TestServer(_make_app(adapter))) as client:
        with patch.object(adapter, "_run_agent", new_callable=AsyncMock) as run:
            run.return_value = ({"final_response": "world"}, {
                "input_tokens": 2, "output_tokens": 3, "total_tokens": 5,
            })
            first = await client.post("/v1/responses", json=payload, headers=headers)
            assert first.status == 200
            first_data = await first.json()
            second = await client.post("/v1/responses", json=payload, headers=headers)
            assert second.status == 200
            second_data = await second.json()
            assert first_data == second_data
            assert first_data["id"].startswith("resp_")
            assert run.call_count == 1
            assert adapter._response_store.get(first_data["id"]) is not None


@pytest.mark.asyncio
async def test_responses_parallel_retry_runs_once():
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={}))
    gate = asyncio.Event()
    async def delayed(**kwargs):
        await gate.wait()
        return {"final_response": "done"}, {}
    async with TestClient(TestServer(_make_app(adapter))) as client:
        with patch.object(adapter, "_run_agent", new_callable=AsyncMock) as run:
            run.side_effect = delayed
            body = {"input": "hello"}
            headers = {"Idempotency-Key": "pending-responses"}
            a = asyncio.create_task(client.post("/v1/responses", json=body, headers=headers))
            await asyncio.sleep(0)
            b = asyncio.create_task(client.post("/v1/responses", json=body, headers=headers))
            await asyncio.sleep(.01)
            gate.set()
            ra, rb = await asyncio.gather(a, b)
            assert ra.status == rb.status == 200
            assert await ra.json() == await rb.json()
            assert run.call_count == 1


@pytest.mark.asyncio
async def test_responses_conflict_and_endpoint_namespace():
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={}))
    headers = {"Idempotency-Key": "shared-across-paths"}
    async with TestClient(TestServer(_make_app(adapter))) as client:
        with patch.object(adapter, "_run_agent", new_callable=AsyncMock) as run:
            run.return_value = ({"final_response": "ok"}, {})
            r1 = await client.post("/v1/responses", json={"input": "hello"}, headers=headers)
            assert r1.status == 200
            r2 = await client.post("/v1/responses", json={"input": "different"}, headers=headers)
            assert r2.status == 409
            assert (await r2.json())["error"]["code"] == "idempotency_key_conflict"
            chat = await client.post("/v1/chat/completions", json={
                "messages": [{"role": "user", "content": "hello"}],
            }, headers=headers)
            assert chat.status == 200  # Separate API operation namespace.
            assert run.call_count == 2


@pytest.mark.asyncio
async def test_responses_agent_error_never_caches_false_success():
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={}))
    async with TestClient(TestServer(_make_app(adapter))) as client:
        with patch.object(adapter, "_run_agent", new_callable=AsyncMock) as run:
            run.return_value = ({"error": "provider returned secret value"}, {})
            r = await client.post("/v1/responses",
                                  json={"input": "hello"},
                                  headers={"Idempotency-Key": "secret-failure"})
            assert r.status == 500
            assert "secret value" not in await r.text()
            r2 = await client.post("/v1/responses",
                                   json={"input": "hello"},
                                   headers={"Idempotency-Key": "secret-failure"})
            assert r2.status == 500
            assert run.call_count == 2  # Failure isn't cached.
