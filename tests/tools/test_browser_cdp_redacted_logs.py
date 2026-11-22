"""Regression tests: CDP discovery logs must never leak endpoint credentials."""
import logging
from unittest.mock import Mock, patch

from tools.browser_tool import _resolve_cdp_override


SECRET = "cdp_private_bearer_token_123"


def _mock_response(websocket_url):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"webSocketDebuggerUrl": websocket_url}
    return response


def test_successful_cdp_discovery_redacts_both_raw_and_discovered_urls(caplog):
    raw = f"https://user:{SECRET}@example.test:9223/?token={SECRET}"
    websocket = f"wss://user:{SECRET}@example.test:9223/devtools/browser/{SECRET}"
    with caplog.at_level(logging.INFO, logger="tools.browser_tool"):
        with patch("tools.browser_tool.requests.get", return_value=_mock_response(websocket)):
            result = _resolve_cdp_override(raw)
    assert result == websocket
    assert SECRET not in caplog.text
    assert "user:" not in caplog.text
    assert "devtools/browser" not in caplog.text


def test_failed_cdp_discovery_redacts_exception_message_and_url(caplog):
    raw = f"http://user:{SECRET}@example.test:9223?token={SECRET}"
    with caplog.at_level(logging.WARNING, logger="tools.browser_tool"):
        with patch("tools.browser_tool.requests.get", side_effect=RuntimeError(f"request failed: {SECRET}")):
            assert _resolve_cdp_override(raw) == raw
    assert SECRET not in caplog.text
    assert "user:" not in caplog.text


def test_missing_websocket_url_redacts_discovery_endpoint(caplog):
    raw = f"http://user:{SECRET}@example.test:9223?token={SECRET}"
    with caplog.at_level(logging.WARNING, logger="tools.browser_tool"):
        with patch("tools.browser_tool.requests.get", return_value=_mock_response(None)):
            assert _resolve_cdp_override(raw) == raw
    assert SECRET not in caplog.text
    assert "user:" not in caplog.text


def test_cdp_session_creation_does_not_log_browser_websocket_credentials(caplog):
    from tools.browser_tool import _create_cdp_session

    websocket = f"wss://user:{SECRET}@example.test:9223/devtools/browser/{SECRET}"
    with caplog.at_level(logging.INFO, logger="tools.browser_tool"):
        session = _create_cdp_session("opaque-task", websocket)
    assert session["cdp_url"] == websocket
    assert SECRET not in caplog.text
    assert "devtools/browser" not in caplog.text
