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
    IdempotencyUncertainOutcome,
    _agent_run_outcome,
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
async def test_failed_keyed_execution_is_fenced_until_reconciliation():
    """A lost tool ACK must NOT cause a second external effect."""
    cache = _IdempotencyCache()
    tries = 0
    external_commits = 0

    async def work():
        nonlocal tries, external_commits
        tries += 1
        external_commits += 1
        # The effect committed, but the result acknowledgement was lost.
        raise RuntimeError("ACK lost after external commit")

    with pytest.raises(RuntimeError):
        await cache.get_or_set("key-effect", "fp", work)
    await asyncio.sleep(0)
    with pytest.raises(IdempotencyUncertainOutcome):
        await cache.get_or_set("key-effect", "fp", work)
    assert tries == 1
    assert external_commits == 1


@pytest.mark.asyncio
async def test_unknown_outcome_does_not_expire_from_short_success_ttl():
    cache = _IdempotencyCache(ttl_seconds=0)
    tries = 0

    async def fails():
        nonlocal tries
        tries += 1
        raise RuntimeError("unknown completion")

    with pytest.raises(RuntimeError):
        await cache.get_or_set("key", "fp", fails)
    await asyncio.sleep(0)
    with pytest.raises(IdempotencyUncertainOutcome):
        await cache.get_or_set("key", "fp", fails)
    assert tries == 1


@pytest.mark.asyncio
async def test_hundred_concurrent_same_key_calls_one_agent():
    cache = _IdempotencyCache()
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def work():
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        return "same"

    tasks = [
        asyncio.create_task(cache.get_or_set("hundred", "fp", work))
        for _ in range(100)
    ]
    await entered.wait()
    await asyncio.sleep(0)
    assert calls == 1
    release.set()
    assert await asyncio.gather(*tasks) == ["same"] * 100
    assert calls == 1



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


@pytest.mark.asyncio
async def test_sse_agent_exception_reports_failure_instead_of_success():
    adapter = _adapter()

    async def fails(**kwargs):
        raise RuntimeError("DO_NOT_DISCLOSE_EXCEPTION_TEXT")

    adapter._run_agent = fails
    headers = {"Authorization": "Bearer test-key"}
    async with TestClient(TestServer(_app(adapter))) as client:
        response = await client.post("/v1/chat/completions", json={
            "messages": [{"role": "user", "content": "hi"}], "stream": True,
        }, headers=headers)
        assert response.status == 200
        text = await response.text()
        assert "agent_execution_failed" in text
        assert "finish_reason" not in text or '"finish_reason": "stop"' not in text
        assert "DO_NOT_DISCLOSE_EXCEPTION_TEXT" not in text
        assert text.endswith("data: [DONE]\n\n")
    adapter._response_store.close()


@pytest.mark.asyncio
async def test_invalid_non_object_json_rejected_before_agent_run():
    adapter = _adapter()
    count = 0

    async def fake_run(**kwargs):
        nonlocal count
        count += 1
        return {"final_response": "unexpected"}, {}

    adapter._run_agent = fake_run
    headers = {"Authorization": "Bearer test-key"}
    async with TestClient(TestServer(_app(adapter))) as client:
        for endpoint in ("/v1/chat/completions", "/v1/responses"):
            for invalid in ([], "a-string", 17, None):
                if invalid is None:
                    result = await client.post(
                        endpoint, data="null",
                        headers={**headers, "Content-Type": "application/json"},
                    )
                else:
                    result = await client.post(endpoint, json=invalid, headers=headers)
                assert result.status == 400
                assert (await result.json())["error"]["code"] == "invalid_body"
        assert count == 0
    adapter._response_store.close()


@pytest.mark.asyncio
async def test_request_id_correlates_response_and_metadata_only_events(caplog):
    import logging
    from gateway.platforms.api_server import request_trace_middleware

    adapter = _adapter()
    async def fake_run(**kwargs):
        return {"final_response": "ok"}, {}

    adapter._run_agent = fake_run
    app = web.Application(middlewares=[request_trace_middleware])
    app["api_server_adapter"] = adapter
    app.router.add_post("/v1/chat/completions", adapter._handle_chat_completions)
    caplog.set_level(logging.INFO, logger="gateway.platforms.api_server")
    async with TestClient(TestServer(app)) as client:
        result = await client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "SENSITIVE_CANARY_CONTENT"}]},
            headers={"Authorization": "Bearer test-key"},
        )
        assert result.status == 200
        request_id = result.headers["X-Hermes-Request-Id"]
        assert request_id.startswith("hrq_")
        text = caplog.text
        assert request_id in text
        assert '"event":"request_accepted"' in text
        assert '"event":"request_finished"' in text
        assert "SENSITIVE_CANARY_CONTENT" not in text
        assert "test-key" not in text
    adapter._response_store.close()


@pytest.mark.asyncio
async def test_non_loopback_without_auth_key_rejected_at_bind_time():
    config = PlatformConfig(enabled=True, extra={"host": "0.0.0.0", "port": 0, "key": ""})
    adapter = APIServerAdapter(config)
    assert await adapter.connect() is False
    assert adapter._runner is None
    adapter._response_store.close()


def test_cors_exposes_tracing_and_session_headers():
    from gateway.platforms.api_server import _CORS_HEADERS
    assert "X-Hermes-Session-Id" in _CORS_HEADERS["Access-Control-Allow-Headers"]
    assert "X-Hermes-Session-Id" in _CORS_HEADERS["Access-Control-Expose-Headers"]
    assert "X-Hermes-Request-Id" in _CORS_HEADERS["Access-Control-Expose-Headers"]


@pytest.mark.asyncio
async def test_responses_prior_unknown_effect_returns_conflict_no_second_call():
    adapter = _adapter()
    calls = 0

    async def agent_with_lost_ack(**kwargs):
        nonlocal calls
        calls += 1
        raise RuntimeError("provider may have committed operation")

    adapter._run_agent = agent_with_lost_ack
    headers = {"Authorization": "Bearer test-key", "Idempotency-Key": "lost-ack"}
    payload = {"input": "perform unsafe write"}
    async with TestClient(TestServer(_app(adapter))) as client:
        first = await client.post("/v1/responses", json=payload, headers=headers)
        assert first.status == 500
        await asyncio.sleep(0)
        retry = await client.post("/v1/responses", json=payload, headers=headers)
        assert retry.status == 409
        assert (await retry.json())["error"]["code"] == "execution_outcome_unknown"
        assert calls == 1
    adapter._response_store.close()


@pytest.mark.parametrize("result,expected", [
    ({"completed": True, "final_response": "ok"}, "succeeded"),
    ({"completed": False, "final_response": "partial"}, "incomplete"),
    ({"interrupted": True, "completed": False, "final_response": "partial"}, "interrupted"),
    ({"failed": True, "error": "failed"}, "failed"),
    ({"error": "failed", "final_response": None}, "failed"),
    ({"final_response": "old runner"}, "succeeded"),
    (None, "failed"),
])
def test_runner_outcome_precedence(result, expected):
    assert _agent_run_outcome(result) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("runner_result,expected_reason", [
    ({"final_response": "summary", "completed": False}, "incomplete"),
    ({"final_response": "interrupted", "completed": False, "interrupted": True}, "interrupted"),
])
async def test_chat_incomplete_run_does_not_claim_success(runner_result, expected_reason):
    adapter = _adapter()

    async def fake_run(**kwargs):
        return runner_result, {}

    adapter._run_agent = fake_run
    async with TestClient(TestServer(_app(adapter))) as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hi"}]},
            headers={"Authorization": "Bearer test-key"},
        )
        assert resp.status == 200
        assert resp.headers["X-Hermes-Agent-Outcome"] == expected_reason
        assert (await resp.json())["choices"][0]["finish_reason"] == "length"
    adapter._response_store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("runner_result,expected_reason", [
    ({"final_response": "partial", "completed": False}, "agent_incomplete"),
    ({"final_response": "partial", "completed": False, "interrupted": True}, "agent_interrupted"),
])
async def test_responses_incomplete_run_is_not_completed(runner_result, expected_reason):
    adapter = _adapter()

    async def fake_run(**kwargs):
        return runner_result, {}

    adapter._run_agent = fake_run
    async with TestClient(TestServer(_app(adapter))) as client:
        resp = await client.post(
            "/v1/responses", json={"input": "hi"},
            headers={"Authorization": "Bearer test-key"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "incomplete"
        assert data["incomplete_details"]["reason"] == expected_reason
    adapter._response_store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("runner_result,reason", [
    ({"failed": True, "error": "SECRET_RUNNER_MESSAGE", "completed": False},
     "agent_reported_failed"),
    ({"interrupted": True, "completed": False, "final_response": "partial"},
     "agent_interrupted"),
])
async def test_sse_reported_stop_not_false_success(runner_result, reason):
    adapter = _adapter()

    async def fake_run(**kwargs):
        return runner_result, {}

    adapter._run_agent = fake_run
    async with TestClient(TestServer(_app(adapter))) as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hi"}], "stream": True},
            headers={"Authorization": "Bearer test-key"},
        )
        assert resp.status == 200
        wire = await resp.text()
        assert reason in wire
        assert '"finish_reason": "stop"' not in wire
        assert "SECRET_RUNNER_MESSAGE" not in wire
    adapter._response_store.close()


@pytest.mark.asyncio
async def test_sse_incomplete_run_marks_length_not_stop():
    adapter = _adapter()

    async def fake_run(**kwargs):
        return {"completed": False, "final_response": "partial"}, {}

    adapter._run_agent = fake_run
    async with TestClient(TestServer(_app(adapter))) as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hi"}], "stream": True},
            headers={"Authorization": "Bearer test-key"},
        )
        assert resp.status == 200
        wire = await resp.text()
        assert '"finish_reason": "length"' in wire
        assert '"finish_reason": "stop"' not in wire
    adapter._response_store.close()


@pytest.mark.asyncio
async def test_http_failed_runner_reports_error_without_leakage():
    adapter = _adapter()

    async def fake_run(**kwargs):
        return {
            "failed": True, "completed": False, "error": "SENSITIVE_RUNNER_CONTENT",
            "final_response": None,
        }, {}

    adapter._run_agent = fake_run
    async with TestClient(TestServer(_app(adapter))) as client:
        for endpoint, payload in (
            ("/v1/responses", {"input": "hi"}),
            ("/v1/chat/completions", {"messages": [{"role": "user", "content": "hi"}]}),
        ):
            resp = await client.post(
                endpoint, json=payload,
                headers={"Authorization": "Bearer test-key"},
            )
            assert resp.status == 500
            content = await resp.text()
            assert "SENSITIVE_RUNNER_CONTENT" not in content
            assert "agent_execution_failed" in content
    adapter._response_store.close()


def test_response_store_alias_eviction_does_not_leave_stale_reference():
    store = ResponseStore(db_path=":memory:", max_size=1)
    try:
        store.put("resp_old", {"result": "old"}, conversation_name="old-chat")
        store.put("resp_new", {"result": "new"}, conversation_name="new-chat")
        assert store.get("resp_old") is None
        assert store.get_conversation("old-chat") is None
        assert store.get_conversation("new-chat") == "resp_new"
    finally:
        store.close()


def test_response_store_delete_removes_conversation_alias_atomically():
    store = ResponseStore(db_path=":memory:")
    try:
        store.put("resp_a", {"data": 1}, conversation_name="chat-a")
        store.put("resp_a", {"data": 2}, conversation_name="chat-b")
        assert store.delete("resp_a") is True
        assert store.get_conversation("chat-a") is None
        assert store.get_conversation("chat-b") is None
        assert store.delete("resp_a") is False
    finally:
        store.close()


def test_response_and_alias_both_rollback_after_sql_error():
    import sqlite3
    store = ResponseStore(db_path=":memory:")
    try:
        store._conn.execute(
            "CREATE TRIGGER deny_alias BEFORE INSERT ON conversations "
            "BEGIN SELECT RAISE(ABORT, 'simulated alias failure'); END;"
        )
        store._conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            store.put(
                "resp_new", {"content": "must_rollback"},
                conversation_name="failing_alias",
            )
        assert store.get("resp_new") is None
        assert store.get_conversation("failing_alias") is None
    finally:
        store.close()
