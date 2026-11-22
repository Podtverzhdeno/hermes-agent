"""Regression tests for browser session cleanup and screenshot recovery."""

from unittest.mock import patch


class TestScreenshotPathRecovery:
    def test_extracts_standard_absolute_path(self):
        from tools.browser_tool import _extract_screenshot_path_from_text

        assert (
            _extract_screenshot_path_from_text("Screenshot saved to /tmp/foo.png")
            == "/tmp/foo.png"
        )

    def test_extracts_quoted_absolute_path(self):
        from tools.browser_tool import _extract_screenshot_path_from_text

        assert (
            _extract_screenshot_path_from_text(
                "Screenshot saved to '/Users/david/.hermes/browser_screenshots/shot.png'"
            )
            == "/Users/david/.hermes/browser_screenshots/shot.png"
        )


class TestBrowserCleanup:
    def setup_method(self):
        from tools import browser_tool

        self.browser_tool = browser_tool
        self.orig_active_sessions = browser_tool._active_sessions.copy()
        self.orig_session_last_activity = browser_tool._session_last_activity.copy()
        self.orig_recording_sessions = browser_tool._recording_sessions.copy()
        self.orig_cleanup_done = browser_tool._cleanup_done

    def teardown_method(self):
        self.browser_tool._active_sessions.clear()
        self.browser_tool._active_sessions.update(self.orig_active_sessions)
        self.browser_tool._session_last_activity.clear()
        self.browser_tool._session_last_activity.update(self.orig_session_last_activity)
        self.browser_tool._recording_sessions.clear()
        self.browser_tool._recording_sessions.update(self.orig_recording_sessions)
        self.browser_tool._cleanup_done = self.orig_cleanup_done

    def test_cleanup_browser_clears_tracking_state(self):
        browser_tool = self.browser_tool
        browser_tool._active_sessions["task-1"] = {
            "session_name": "sess-1",
            "bb_session_id": None,
        }
        browser_tool._session_last_activity["task-1"] = 123.0

        with (
            patch("tools.browser_tool._maybe_stop_recording") as mock_stop,
            patch(
                "tools.browser_tool._run_browser_command",
                return_value={"success": True},
            ) as mock_run,
            patch("tools.browser_tool.os.path.exists", return_value=False),
        ):
            browser_tool.cleanup_browser("task-1")

        assert "task-1" not in browser_tool._active_sessions
        assert "task-1" not in browser_tool._session_last_activity
        mock_stop.assert_called_once_with("task-1")
        mock_run.assert_called_once_with("task-1", "close", [], timeout=10)

    def test_browser_close_delegates_to_cleanup_browser(self):
        import json

        browser_tool = self.browser_tool
        browser_tool._active_sessions["task-2"] = {"session_name": "sess-2"}

        with patch("tools.browser_tool.cleanup_browser") as mock_cleanup:
            result = json.loads(browser_tool.browser_close("task-2"))

        assert result == {"success": True, "closed": True}
        mock_cleanup.assert_called_once_with("task-2")

    def test_emergency_cleanup_clears_all_tracking_state(self):
        browser_tool = self.browser_tool
        browser_tool._cleanup_done = False
        browser_tool._active_sessions["task-1"] = {"session_name": "sess-1"}
        browser_tool._active_sessions["task-2"] = {"session_name": "sess-2"}
        browser_tool._session_last_activity["task-1"] = 1.0
        browser_tool._session_last_activity["task-2"] = 2.0
        browser_tool._recording_sessions.update({"task-1", "task-2"})

        with patch("tools.browser_tool.cleanup_all_browsers") as mock_cleanup_all:
            browser_tool._emergency_cleanup_all_sessions()

        mock_cleanup_all.assert_called_once_with()
        assert browser_tool._active_sessions == {}
        assert browser_tool._session_last_activity == {}
        assert browser_tool._recording_sessions == set()
        assert browser_tool._cleanup_done is True

    def test_browser_close_reports_external_cdp_session_detached_not_process_closed(self):
        import json

        browser_tool = self.browser_tool
        browser_tool._active_sessions["attached-task"] = {
            "session_name": "cdp_12345678",
            "bb_session_id": None,
            "cdp_url": "ws://127.0.0.1:9223/devtools/browser/test",
            "features": {"cdp_override": True},
        }
        with patch("tools.browser_tool.cleanup_browser") as cleanup:
            response = json.loads(browser_tool.browser_close("attached-task"))
        cleanup.assert_called_once_with("attached-task")
        assert response == {
            "success": True, "closed": True,
            "browser_process_closed": False, "external_cdp_detached": True,
        }

    def test_cleanup_external_cdp_keeps_owner_browser_and_other_sessions(self):
        """Closing one attached CDP lease must not send Browser.close or kill Edge."""
        browser_tool = self.browser_tool
        browser_tool._active_sessions["attached-task"] = {
            "session_name": "cdp_12345678",
            "bb_session_id": None,
            "cdp_url": "ws://127.0.0.1:9223/devtools/browser/test",
            "features": {"cdp_override": True},
        }
        browser_tool._active_sessions["other-task"] = {
            "session_name": "h_other",
            "bb_session_id": None,
            "cdp_url": None,
            "features": {"local": True},
        }
        browser_tool._session_last_activity["attached-task"] = 123.0
        browser_tool._session_last_activity["other-task"] = 124.0
        with (
            patch("tools.browser_tool._maybe_stop_recording") as stop_record,
            patch("tools.browser_tool._run_browser_command") as cli,
            patch("tools.browser_tool.os.kill") as terminate_pid,
            patch("tools.browser_tool.shutil.rmtree") as remove_socket,
        ):
            browser_tool.cleanup_browser("attached-task")
        assert "attached-task" not in browser_tool._active_sessions
        assert "attached-task" not in browser_tool._session_last_activity
        assert "other-task" in browser_tool._active_sessions
        stop_record.assert_called_once_with("attached-task")
        cli.assert_not_called()
        terminate_pid.assert_not_called()
        remove_socket.assert_not_called()

    def test_attached_idle_cleanup_is_non_destructive(self):
        """Inactivity cleanup must never terminate an externally attached browser."""
        browser_tool = self.browser_tool
        browser_tool._active_sessions["attached-task"] = {
            "session_name": "cdp_12345678",
            "bb_session_id": None,
            "cdp_url": "ws://127.0.0.1:9223/devtools/browser/test",
            "features": {"cdp_override": True},
        }
        browser_tool._session_last_activity["attached-task"] = 1.0
        with (
            patch("tools.browser_tool._maybe_stop_recording"),
            patch("tools.browser_tool._run_browser_command") as cli,
            patch("tools.browser_tool.os.kill") as terminate_pid,
            patch("tools.browser_tool.shutil.rmtree") as remove_socket,
            patch("tools.browser_tool.time.time", return_value=10000.0),
        ):
            browser_tool._cleanup_inactive_browser_sessions()
        assert "attached-task" not in browser_tool._active_sessions
        cli.assert_not_called()
        terminate_pid.assert_not_called()
        remove_socket.assert_not_called()

    def test_local_cleanup_retains_existing_close_semantics(self):
        """Local Hermes-owned browser keeps the current graceful CLI close."""
        browser_tool = self.browser_tool
        browser_tool._active_sessions["local-task"] = {
            "session_name": "h_local",
            "bb_session_id": None,
            "cdp_url": None,
            "features": {"local": True},
        }
        with (
            patch("tools.browser_tool._maybe_stop_recording"),
            patch("tools.browser_tool._run_browser_command", return_value={"success": True}) as cli,
            patch("tools.browser_tool.os.path.exists", return_value=False),
        ):
            browser_tool.cleanup_browser("local-task")
        cli.assert_called_once_with("local-task", "close", [], timeout=10)
        assert "local-task" not in browser_tool._active_sessions

    def test_attached_exit_cleanup_is_non_destructive(self):
        """Process-exit cleanup must forget Hermes state, not terminate Edge."""
        browser_tool = self.browser_tool
        browser_tool._cleanup_done = False
        browser_tool._active_sessions["attached-task"] = {
            "session_name": "cdp_12345678",
            "bb_session_id": None,
            "cdp_url": "ws://127.0.0.1:9223/devtools/browser/test",
            "features": {"cdp_override": True},
        }
        with (
            patch("tools.browser_tool._maybe_stop_recording"),
            patch("tools.browser_tool._run_browser_command") as cli,
            patch("tools.browser_tool.os.kill") as terminate_pid,
            patch("tools.browser_tool.shutil.rmtree") as remove_socket,
        ):
            browser_tool._emergency_cleanup_all_sessions()
        cli.assert_not_called()
        terminate_pid.assert_not_called()
        remove_socket.assert_not_called()
        assert browser_tool._cleanup_done is True
        assert browser_tool._active_sessions == {}
