"""API ingress must reject unsupported retry semantics before running an agent.

These tests target the GPT bridge draft branch and require aiohttp + pytest-asyncio.
"""

from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from gateway.config import PlatformConfig
from gateway.platforms.api_server import APIServerAdapter


def app_and_adapter():
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={}))
    app = web.Application()
    app["api_server_adapter"] = adapter
    app.router.add_post("/v1/chat/completions", adapter._handle_chat_completions)
    return app, adapter


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body, headers, error_code",
    [
        ([], {}, "invalid_body"),
        ({"messages": [17]}, {}, "invalid_messages"),
        ({"messages": [{"role": "user", "content": "hello"}], "stream": "false"},
         {}, "invalid_stream"),
        ({"messages": [{"role": "user", "content": "hello"}], "stream": True},
         {"Idempotency-Key": "must-not-be-ignored"}, "unsupported_idempotency_mode"),
        ({"messages": [{"role": "user", "content": "hello"}]},
         {"Idempotency-Key": ""}, "invalid_idempotency_key"),
    ],
    ids=[
        "json-root-is-list", "nonobject-message", "string-stream-flag",
        "keyed-stream-must-not-run", "blank-idempotency-key",
    ],
)
async def test_invalid_api_request_fails_before_agent_dispatch(body, headers, error_code):
    app, adapter = app_and_adapter()
    agent = AsyncMock(side_effect=AssertionError("unexpected agent execution"))
    with patch.object(adapter, "_run_agent", agent):
        async with TestClient(TestServer(app)) as client:
            response = await client.post("/v1/chat/completions", json=body, headers=headers)
            assert response.status == 400
            payload = await response.json()
            assert payload["error"]["code"] == error_code
    agent.assert_not_awaited()
