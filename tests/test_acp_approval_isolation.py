"""Regression checks for ACP permission isolation under concurrent execution.

These checks deliberately avoid invoking a real terminal, browser or model.
"""
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

import importlib

# tools.__init__ exports a callable named terminal_tool, not the submodule.
terminal_tool = importlib.import_module("tools.terminal_tool")


def test_parallel_scopes_never_route_permissions_to_another_session(monkeypatch):
    global_callback = lambda *_: "global"
    monkeypatch.setattr(terminal_tool, "_approval_callback", global_callback)
    barrier = threading.Barrier(2)

    def in_session(expected):
        callback = lambda *_: expected
        with terminal_tool.scoped_approval_callback(callback):
            barrier.wait(timeout=5)
            return terminal_tool._effective_approval_callback()("cmd", "description")

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(in_session, "session-a")
        b = pool.submit(in_session, "session-b")
        assert a.result(timeout=10) == "session-a"
        assert b.result(timeout=10) == "session-b"

    # The ordinary CLI callback remains intact in the caller's context.
    assert terminal_tool._effective_approval_callback() is global_callback


def test_scoped_callback_resets_even_on_exception(monkeypatch):
    global_callback = lambda *_: "global"
    monkeypatch.setattr(terminal_tool, "_approval_callback", global_callback)
    callback = lambda *_: "session"

    with pytest.raises(RuntimeError, match="crash"):
        with terminal_tool.scoped_approval_callback(callback):
            assert terminal_tool._effective_approval_callback() is callback
            raise RuntimeError("crash")

    assert terminal_tool._effective_approval_callback() is global_callback


def test_explicit_none_scope_never_falls_back_to_cli_callback(monkeypatch):
    global_callback = lambda *_: "global"
    monkeypatch.setattr(terminal_tool, "_approval_callback", global_callback)
    with terminal_tool.scoped_approval_callback(None):
        assert terminal_tool._effective_approval_callback() is None
    assert terminal_tool._effective_approval_callback() is global_callback


def test_dangerous_command_guard_uses_scoped_callback(monkeypatch):
    seen = []

    def fake_guard(command, env_type, approval_callback, enforce_callback=False):
        seen.append((approval_callback, enforce_callback))
        return {"allowed": False}

    monkeypatch.setattr(terminal_tool, "_check_dangerous_command_impl", fake_guard)
    callback = lambda *_: "deny"
    with terminal_tool.scoped_approval_callback(callback):
        terminal_tool._check_dangerous_command("dangerous", "local")
    assert seen == [(callback, True)]


def test_acp_unknown_permission_option_fails_closed(monkeypatch):
    from acp_adapter import permissions

    class DummyAllowedOutcome:
        def __init__(self, option_id):
            self.option_id = option_id

    monkeypatch.setattr(permissions, "AllowedOutcome", DummyAllowedOutcome)

    async def request_permission_fn(**kwargs):
        return SimpleNamespace(outcome=DummyAllowedOutcome("unexpected-option"))

    async def check():
        loop = asyncio.get_running_loop()
        callback = permissions.make_approval_callback(
            request_permission_fn, loop, "session-a", timeout=2.0
        )
        return await asyncio.to_thread(callback, "command", "description")

    assert asyncio.run(check()) == "deny"


def test_acp_scope_disables_noninteractive_yolo_bypass(monkeypatch):
    from tools import approval

    monkeypatch.setenv("HERMES_YOLO_MODE", "1")
    monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)
    monkeypatch.delenv("HERMES_GATEWAY_SESSION", raising=False)
    monkeypatch.setattr(
        approval, "detect_dangerous_command",
        lambda _: (True, "danger", "Dangerous operation"),
    )
    called = []

    def deny(command, description, *, allow_permanent=True):
        called.append(allow_permanent)
        return "deny"

    with terminal_tool.scoped_approval_callback(deny):
        outcome = terminal_tool._check_dangerous_command("dangerous", "local")
    assert outcome["approved"] is False
    assert called == [False]


def test_acp_combined_guard_denies_even_when_config_mode_off(monkeypatch):
    from tools import approval
    from tools import tirith_security

    monkeypatch.setattr(approval, "_get_approval_mode", lambda: "off")
    monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)
    monkeypatch.delenv("HERMES_GATEWAY_SESSION", raising=False)
    monkeypatch.delenv("HERMES_EXEC_ASK", raising=False)
    monkeypatch.setattr(
        approval, "detect_dangerous_command",
        lambda _: (True, "danger", "Dangerous operation"),
    )
    monkeypatch.setattr(
        tirith_security, "check_command_security",
        lambda _: {"action": "allow", "findings": [], "summary": ""},
    )
    calls = []

    def deny(command, description, *, allow_permanent=True):
        calls.append(allow_permanent)
        return "deny"

    with terminal_tool.scoped_approval_callback(deny):
        outcome = terminal_tool._check_all_guards("dangerous", "local")
    assert outcome["approved"] is False
    assert calls == [False]


def test_acp_approval_fails_closed_without_connected_client(monkeypatch):
    from tools import approval

    monkeypatch.setattr(approval, "detect_dangerous_command",
                        lambda _: (True, "danger", "Dangerous"))
    monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)
    monkeypatch.delenv("HERMES_GATEWAY_SESSION", raising=False)
    with terminal_tool.scoped_approval_callback(None):
        outcome = terminal_tool._check_dangerous_command("dangerous", "local")
    assert outcome["approved"] is False


def test_permission_bridge_accepts_allow_permanent_keyword(monkeypatch):
    from acp_adapter import permissions

    class DummyAllowedOutcome:
        def __init__(self, option_id):
            self.option_id = option_id

    monkeypatch.setattr(permissions, "AllowedOutcome", DummyAllowedOutcome)
    captured = []

    async def request_permission_fn(**kwargs):
        captured.append([option.option_id for option in kwargs["options"]])
        return SimpleNamespace(outcome=DummyAllowedOutcome("allow_once"))

    async def run():
        loop = asyncio.get_running_loop()
        cb = permissions.make_approval_callback(
            request_permission_fn, loop, "session-a", timeout=2.0,
        )
        return await asyncio.to_thread(cb, "cmd", "description", allow_permanent=False)

    assert asyncio.run(run()) == "once"
    assert captured == [["allow_once", "deny"]]


@pytest.mark.parametrize("backend", ["docker", "singularity", "modal", "daytona"])
def test_acp_scope_does_not_silently_bypass_container_commands(monkeypatch, backend):
    from tools import approval

    monkeypatch.setattr(
        approval, "detect_dangerous_command",
        lambda _: (True, "danger", "Dangerous operation"),
    )
    calls = []

    def reject(command, description, *, allow_permanent=True):
        calls.append(backend)
        return "deny"

    with terminal_tool.scoped_approval_callback(reject):
        outcome = terminal_tool._check_dangerous_command("dangerous", backend)
    assert outcome["approved"] is False
    assert calls == [backend]
