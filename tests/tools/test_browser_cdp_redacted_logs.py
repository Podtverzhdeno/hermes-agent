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


def _exercise_cdp_child(tmp_path, caplog, *, stdout_text, stderr_text, rc):
    import os
    from tools.browser_tool import _run_browser_command

    websocket = f"wss://user:{SECRET}@example.test:9223/devtools/browser/{SECRET}"
    session = {"session_name": "cdp_test", "cdp_url": websocket}
    class FakeProcess:
        returncode = rc
        def wait(self, timeout=None):
            return rc
        def kill(self):
            pass

    def fake_popen(cmd_parts, *, stdout, stderr, stdin, env):
        assert "--cdp" in cmd_parts
        assert websocket in cmd_parts
        os.write(stdout, stdout_text.encode())
        os.write(stderr, stderr_text.encode())
        return FakeProcess()

    with caplog.at_level(logging.DEBUG, logger="tools.browser_tool"):
        with patch("tools.browser_tool._find_agent_browser", return_value="agent-browser"), \
             patch("tools.browser_tool._get_session_info", return_value=session), \
             patch("tools.browser_tool._socket_safe_tmpdir", return_value=str(tmp_path)), \
             patch("tools.interrupt.is_interrupted", return_value=False), \
             patch("tools.browser_tool.subprocess.Popen", side_effect=fake_popen):
            return _run_browser_command("opaque-task", "click", ["@e1"], timeout=3)


def test_cdp_subprocess_nonjson_stdout_and_stderr_are_not_logged_or_returned(tmp_path, caplog):
    result = _exercise_cdp_child(tmp_path, caplog, stdout_text=f"bad output: {SECRET}",
                                 stderr_text=f"failed to connect {SECRET}", rc=1)
    assert not result["success"]
    assert SECRET not in caplog.text
    assert SECRET not in str(result)
    assert "devtools/browser" not in caplog.text


def test_cdp_subprocess_empty_stdout_does_not_log_cmd_prefix_with_cdp_url(tmp_path, caplog):
    result = _exercise_cdp_child(tmp_path, caplog, stdout_text="",
                                 stderr_text=f"connection error: {SECRET}", rc=0)
    assert result["success"]
    assert SECRET not in caplog.text
    assert "devtools/browser" not in caplog.text


def test_cdp_subprocess_structured_error_return_does_not_echo_credentials(tmp_path, caplog):
    import json
    raw = json.dumps({"success": False, "error": f"CDP failure: {SECRET}",
                      "message": f"untrusted diagnostic {SECRET}",
                      "url": f"wss://{SECRET}@example.test",
                      "data": {"stderr": f"ws://{SECRET}"},
                      "code": "tab_gone"})
    result = _exercise_cdp_child(tmp_path, caplog, stdout_text=raw,
                                 stderr_text=f"failed: {SECRET}", rc=1)
    assert not result["success"]
    assert result["code"] == "tab_gone"
    assert SECRET not in caplog.text
    assert SECRET not in str(result)


def test_cdp_subprocess_exception_redacts_secret_bearing_exception(tmp_path, caplog):
    from tools.browser_tool import _run_browser_command

    session = {"session_name": "cdp_test", "cdp_url": f"wss://{SECRET}@example.test"}
    with caplog.at_level(logging.WARNING, logger="tools.browser_tool"):
        with patch("tools.browser_tool._find_agent_browser", return_value="agent-browser"), \
             patch("tools.browser_tool._get_session_info", return_value=session), \
             patch("tools.browser_tool._socket_safe_tmpdir", return_value=str(tmp_path)), \
             patch("tools.interrupt.is_interrupted", return_value=False), \
             patch("tools.browser_tool.subprocess.Popen", side_effect=RuntimeError(SECRET)):
            result = _run_browser_command("opaque-task", "click", ["@e1"], timeout=3)
    assert not result["success"]
    assert SECRET not in caplog.text
    assert SECRET not in str(result)
    capture_dir = tmp_path / "agent-browser-cdp_test"
    assert not (capture_dir / "_stdout_click").exists()
    assert not (capture_dir / "_stderr_click").exists()


def test_cdp_timeout_removes_raw_child_capture_files(tmp_path, caplog):
    import os
    import subprocess
    from tools.browser_tool import _run_browser_command

    class TimedProcess:
        returncode = -9
        def wait(self, timeout=None):
            if timeout is not None:
                raise subprocess.TimeoutExpired("agent-browser", timeout)
            return -9
        def kill(self):
            pass

    def fake_popen(cmd_parts, *, stdout, stderr, stdin, env):
        os.write(stdout, f"stdout contains: {SECRET}".encode())
        os.write(stderr, f"stderr contains: {SECRET}".encode())
        return TimedProcess()

    session = {"session_name": "cdp_test", "cdp_url": f"wss://{SECRET}@example.test"}
    with caplog.at_level(logging.WARNING, logger="tools.browser_tool"):
        with patch("tools.browser_tool._find_agent_browser", return_value="agent-browser"), \
             patch("tools.browser_tool._get_session_info", return_value=session), \
             patch("tools.browser_tool._socket_safe_tmpdir", return_value=str(tmp_path)), \
             patch("tools.interrupt.is_interrupted", return_value=False), \
             patch("tools.browser_tool.subprocess.Popen", side_effect=fake_popen):
            result = _run_browser_command("opaque-task", "click", ["@e1"], timeout=3)
    assert not result["success"]
    assert SECRET not in caplog.text
    assert SECRET not in str(result)
    capture_dir = tmp_path / "agent-browser-cdp_test"
    assert not (capture_dir / "_stdout_click").exists()
    assert not (capture_dir / "_stderr_click").exists()


def test_cdp_subprocess_unrecognized_structured_code_is_not_echoed(tmp_path, caplog):
    import json
    raw = json.dumps({"success": False, "error": SECRET, "code": SECRET,
                      "details": {"private_url": f"wss://{SECRET}"}})
    result = _exercise_cdp_child(tmp_path, caplog, stdout_text=raw,
                                 stderr_text=f"failed: {SECRET}", rc=1)
    assert not result["success"]
    assert result["code"] == "cdp_command_failed"
    assert SECRET not in str(result)
    assert SECRET not in caplog.text
