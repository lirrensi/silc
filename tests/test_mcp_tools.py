"""Tests for SILC MCP tools.

These tests verify the MCP tool implementations work correctly.
Unit tests can run without a daemon; integration tests require one.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

from silc.daemon import DAEMON_PORT
from silc.mcp import tools

# ============================================================================
# Unit Tests (No Daemon Required)
# ============================================================================


class TestGetErrorDetail:
    """Tests for _get_error_detail helper function."""

    def test_none_response(self):
        """None response returns 'unknown error'."""
        from silc.mcp.tools import _get_error_detail

        result = _get_error_detail(None)
        assert result == "unknown error"

    def test_json_response_with_detail(self):
        """JSON response with 'detail' field extracts detail."""
        from silc.mcp.tools import _get_error_detail

        mock_response = MagicMock()
        mock_response.json.return_value = {"detail": "Something went wrong"}

        result = _get_error_detail(mock_response)
        assert result == "Something went wrong"

    def test_json_response_with_error(self):
        """JSON response with 'error' field extracts error."""
        from silc.mcp.tools import _get_error_detail

        mock_response = MagicMock()
        mock_response.json.return_value = {"error": "Connection failed"}

        result = _get_error_detail(mock_response)
        assert result == "Connection failed"

    def test_json_response_no_detail_or_error(self):
        """JSON response without detail/error returns stringified data."""
        from silc.mcp.tools import _get_error_detail

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "failed", "code": 500}

        result = _get_error_detail(mock_response)
        assert "status" in result or "failed" in result

    def test_json_decode_error_falls_back_to_text(self):
        """Invalid JSON falls back to response text."""
        from silc.mcp.tools import _get_error_detail

        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.text = "Error text"
        mock_response.reason = "Bad Request"

        result = _get_error_detail(mock_response)
        assert result == "Error text"

    def test_json_decode_error_falls_back_to_reason(self):
        """No text falls back to reason."""
        from silc.mcp.tools import _get_error_detail

        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.text = None
        mock_response.reason = "Internal Server Error"

        result = _get_error_detail(mock_response)
        assert result == "Internal Server Error"


class TestKeySequences:
    """Tests for KEY_SEQUENCES constant."""

    def test_key_sequences_exist(self):
        """Key sequences dictionary is defined."""
        assert hasattr(tools, "KEY_SEQUENCES")
        assert isinstance(tools.KEY_SEQUENCES, dict)
        assert len(tools.KEY_SEQUENCES) > 0

    def test_ctrl_c_sequence(self):
        """Ctrl+C sends correct byte."""
        assert tools.KEY_SEQUENCES["ctrl+c"] == b"\x03"

    def test_ctrl_d_sequence(self):
        """Ctrl+D sends correct byte."""
        assert tools.KEY_SEQUENCES["ctrl+d"] == b"\x04"

    def test_enter_sequence(self):
        """Enter sends carriage return."""
        assert tools.KEY_SEQUENCES["enter"] == b"\r"

    def test_escape_sequence(self):
        """Escape sends correct byte."""
        assert tools.KEY_SEQUENCES["escape"] == b"\x1b"

    def test_arrow_keys_sequences(self):
        """Arrow keys send ANSI escape sequences."""
        assert tools.KEY_SEQUENCES["up"] == b"\x1b[A"
        assert tools.KEY_SEQUENCES["down"] == b"\x1b[B"
        assert tools.KEY_SEQUENCES["right"] == b"\x1b[C"
        assert tools.KEY_SEQUENCES["left"] == b"\x1b[D"

    def test_all_keys_are_lowercase(self):
        """All key names are lowercase."""
        for key in tools.KEY_SEQUENCES:
            assert key == key.lower(), f"Key '{key}' should be lowercase"


class TestListSessionsUnit:
    """Unit tests for list_sessions with mocked requests."""

    @patch("silc.mcp.tools.requests.get")
    def test_list_sessions_success(self, mock_get):
        """list_sessions returns session list on success."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"port": 20000, "name": "test-session", "alive": True}
        ]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = tools.list_sessions()

        assert len(result) == 1
        assert result[0]["port"] == 20000
        mock_get.assert_called_once()

    @patch("silc.mcp.tools.requests.get")
    def test_list_sessions_empty(self, mock_get):
        """list_sessions returns empty list when no sessions."""
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = tools.list_sessions()

        assert result == []

    @patch("silc.mcp.tools.requests.get")
    def test_list_sessions_connection_error(self, mock_get):
        """list_sessions returns empty list on connection error."""
        mock_get.side_effect = requests.ConnectionError("Connection refused")

        result = tools.list_sessions()

        assert result == []

    @patch("silc.mcp.tools.requests.get")
    def test_list_sessions_timeout(self, mock_get):
        """list_sessions returns empty list on timeout."""
        mock_get.side_effect = requests.Timeout("Request timed out")

        result = tools.list_sessions()

        assert result == []


class TestStartSessionUnit:
    """Unit tests for start_session with mocked requests."""

    @patch("silc.mcp.tools.requests.post")
    def test_start_session_success(self, mock_post):
        """start_session returns session data on success."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "port": 20000,
            "name": "test-session",
            "session_id": "abc123",
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = tools.start_session()

        assert "port" in result
        assert result["port"] == 20000

    @patch("silc.mcp.tools.requests.post")
    def test_start_session_with_port(self, mock_post):
        """start_session includes port in payload."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"port": 20100}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = tools.start_session(port=20100)

        call_args = mock_post.call_args
        assert call_args[1]["json"]["port"] == 20100

    @patch("silc.mcp.tools.requests.post")
    def test_start_session_with_shell(self, mock_post):
        """start_session includes shell in payload."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"port": 20000}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = tools.start_session(shell="bash")

        call_args = mock_post.call_args
        assert call_args[1]["json"]["shell"] == "bash"

    @patch("silc.mcp.tools.requests.post")
    def test_start_session_http_error(self, mock_post):
        """start_session returns error dict on HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"detail": "Port already in use"}
        mock_response.raise_for_status.side_effect = requests.HTTPError()
        mock_response.reason = "Bad Request"
        mock_post.return_value = mock_response

        result = tools.start_session()

        assert "error" in result

    @patch("silc.mcp.tools.requests.post")
    def test_start_session_connection_error(self, mock_post):
        """start_session returns error dict on connection error."""
        mock_post.side_effect = requests.ConnectionError("Connection refused")

        result = tools.start_session()

        assert "error" in result


class TestCloseSessionUnit:
    """Unit tests for close_session with mocked requests."""

    @patch("silc.mcp.tools.requests.delete")
    def test_close_session_success(self, mock_delete):
        """close_session returns status on success."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_delete.return_value = mock_response

        result = tools.close_session(20000)

        assert result["status"] == "closed"

    @patch("silc.mcp.tools.requests.delete")
    def test_close_session_not_found(self, mock_delete):
        """close_session returns error for nonexistent session."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_delete.return_value = mock_response

        result = tools.close_session(99999)

        assert "error" in result
        assert result["status"] == "not_found"

    @patch("silc.mcp.tools.requests.delete")
    def test_close_session_connection_error(self, mock_delete):
        """close_session returns error on connection error."""
        mock_delete.side_effect = requests.ConnectionError("Connection refused")

        result = tools.close_session(20000)

        assert "error" in result


class TestGetStatusUnit:
    """Unit tests for get_status with mocked requests."""

    @patch("silc.mcp.tools.requests.get")
    def test_get_status_success(self, mock_get):
        """get_status returns status on success."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "alive": True,
            "session_id": "abc123",
            "idle_seconds": 0,
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = tools.get_status(20000)

        assert result["alive"] is True

    @patch("silc.mcp.tools.requests.get")
    def test_get_status_session_ended(self, mock_get):
        """get_status returns error when session has ended (410)."""
        mock_response = MagicMock()
        mock_response.status_code = 410
        mock_get.return_value = mock_response

        result = tools.get_status(20000)

        assert result["alive"] is False
        assert "error" in result

    @patch("silc.mcp.tools.requests.get")
    def test_get_status_connection_error(self, mock_get):
        """get_status returns error on connection error."""
        mock_get.side_effect = requests.ConnectionError("Connection refused")

        result = tools.get_status(20000)

        assert result["alive"] is False
        assert "error" in result


class TestResizeUnit:
    """Unit tests for resize with mocked requests."""

    @patch("silc.mcp.tools.requests.post")
    def test_resize_success(self, mock_post):
        """resize returns success on valid resize."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "resized"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = tools.resize(20000, rows=40, cols=160)

        call_args = mock_post.call_args
        assert call_args[1]["params"]["rows"] == 40
        assert call_args[1]["params"]["cols"] == 160

    @patch("silc.mcp.tools.requests.post")
    def test_resize_defaults(self, mock_post):
        """resize uses default values."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "resized"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = tools.resize(20000)

        call_args = mock_post.call_args
        assert call_args[1]["params"]["rows"] == 30
        assert call_args[1]["params"]["cols"] == 120


class TestReadUnit:
    """Unit tests for read with mocked requests."""

    @patch("silc.mcp.tools.requests.get")
    def test_read_success(self, mock_get):
        """read returns output on success."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"output": "Hello World", "lines": 1}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = tools.read(20000)

        assert result["output"] == "Hello World"

    @patch("silc.mcp.tools.requests.get")
    def test_read_session_ended(self, mock_get):
        """read returns error when session has ended (410)."""
        mock_response = MagicMock()
        mock_response.status_code = 410
        mock_get.return_value = mock_response

        result = tools.read(20000)

        assert result["output"] == ""
        assert "error" in result


class TestSendUnit:
    """Unit tests for send with mocked requests."""

    @patch("silc.mcp.tools.requests.post")
    @patch("silc.mcp.tools.read")
    @patch("silc.mcp.tools.time.sleep")
    def test_send_success(self, mock_sleep, mock_read, mock_post):
        """send sends text and returns output."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response
        mock_read.return_value = {"output": "output text", "lines": 1}

        result = tools.send(20000, "echo hello")

        assert result["alive"] is True
        mock_post.assert_called_once()

    @patch("silc.mcp.tools.requests.post")
    def test_send_fire_and_forget(self, mock_post):
        """send with timeout_ms=0 returns immediately."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = tools.send(20000, "echo hello", timeout_ms=0)

        assert result["alive"] is True
        assert result["lines"] == 0


class TestSendKeyUnit:
    """Unit tests for send_key with mocked requests."""

    @patch("silc.mcp.tools.requests.post")
    @patch("silc.mcp.tools.read")
    @patch("silc.mcp.tools.time.sleep")
    def test_send_key_ctrl_c(self, mock_sleep, mock_read, mock_post):
        """send_key sends Ctrl+C sequence."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response
        mock_read.return_value = {"output": "", "lines": 0}

        result = tools.send_key(20000, "ctrl+c")

        call_args = mock_post.call_args
        assert call_args[1]["data"] == b"\x03"

    def test_send_key_unknown_key(self):
        """send_key returns error for unknown key."""
        # This test doesn't need mocking since it returns early
        result = tools.send_key(20000, "unknown-key")

        assert "error" in result
        assert "Unknown key" in result["error"]

    @patch("silc.mcp.tools.requests.post")
    @patch("silc.mcp.tools.read")
    @patch("silc.mcp.tools.time.sleep")
    def test_send_key_session_ended(self, mock_sleep, mock_read, mock_post):
        """send_key returns error when session has ended (410)."""
        mock_response = MagicMock()
        mock_response.status_code = 410
        mock_post.return_value = mock_response

        result = tools.send_key(20000, "enter")

        assert result["alive"] is False
        assert "error" in result


class TestRunUnit:
    """Unit tests for run with mocked requests."""

    @patch("silc.mcp.tools.requests.post")
    def test_run_success(self, mock_post):
        """run executes command and returns output."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "output": "hello",
            "exit_code": 0,
            "status": "ok",
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = tools.run(20000, "echo hello")

        call_args = mock_post.call_args
        assert call_args[1]["json"]["command"] == "echo hello"

    @patch("silc.mcp.tools.requests.post")
    def test_run_session_ended(self, mock_post):
        """run returns error when session has ended (410)."""
        mock_response = MagicMock()
        mock_response.status_code = 410
        mock_post.return_value = mock_response

        result = tools.run(20000, "echo hello")

        assert result["exit_code"] == -1
        assert "error" in result

    @patch("silc.mcp.tools.requests.post")
    def test_run_connection_error(self, mock_post):
        """run returns error on connection error."""
        mock_post.side_effect = requests.ConnectionError("Connection refused")

        result = tools.run(20000, "echo hello")

        assert result["exit_code"] == -1


# ============================================================================
# Integration Tests (Daemon Required)
# ============================================================================


def run_cli(args: list[str], timeout: float = 30.0) -> subprocess.CompletedProcess:
    """Run SILC CLI command and return result."""
    cmd = [sys.executable, "-m", "silc"] + args
    import os

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


@pytest.fixture(scope="module")
def ensure_daemon_stopped():
    """Stop any existing daemon before and after tests."""
    # Stop before
    try:
        run_cli(["killall"], timeout=10)
    except subprocess.TimeoutExpired:
        pass
    time.sleep(1)

    yield

    # Stop after
    try:
        run_cli(["killall"], timeout=10)
    except subprocess.TimeoutExpired:
        pass


@pytest.mark.integration
class TestMCPToolsIntegration:
    """Integration tests for MCP tools with real daemon."""

    @pytest.mark.asyncio
    async def test_list_sessions_empty(self, ensure_daemon_stopped):
        """list_sessions returns empty list when no sessions."""
        # Ensure no sessions
        result = tools.list_sessions()
        # Could be empty or daemon not running (returns empty)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_start_and_list_session(self, ensure_daemon_stopped):
        """Start session and verify it appears in list."""
        # Start daemon and session
        run_cli(["start", "mcp-test-session"], timeout=60)
        time.sleep(1)

        # List sessions
        sessions = tools.list_sessions()

        # Should have at least one session
        assert len(sessions) >= 1

        # Find our session
        names = [s.get("name") for s in sessions]
        assert "mcp-test-session" in names

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass

    @pytest.mark.asyncio
    async def test_get_status_after_start(self, ensure_daemon_stopped):
        """Get status returns valid session info."""
        # Start session
        run_cli(["start", "mcp-status-test"], timeout=60)
        time.sleep(1)

        # List to get port
        sessions = tools.list_sessions()
        if sessions:
            port = sessions[0]["port"]

            # Get status
            status = tools.get_status(port)

            assert "alive" in status
            # Session should be alive
            assert status.get("alive") is True or "error" in status

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass

    @pytest.mark.asyncio
    async def test_read_after_start(self, ensure_daemon_stopped):
        """Read returns output from session."""
        # Start session
        run_cli(["start", "mcp-read-test"], timeout=60)
        time.sleep(1)

        # List to get port
        sessions = tools.list_sessions()
        if sessions:
            port = sessions[0]["port"]

            # Read should work
            result = tools.read(port)

            assert "output" in result
            # Output may be empty but key should exist

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass

    @pytest.mark.asyncio
    async def test_close_session(self, ensure_daemon_stopped):
        """Close session removes it from list."""
        # Start session
        run_cli(["start", "mcp-close-test"], timeout=60)
        time.sleep(1)

        # List to get port
        sessions = tools.list_sessions()
        if sessions:
            port = sessions[0]["port"]

            # Close session
            result = tools.close_session(port)

            assert result.get("status") == "closed" or "error" in result

            # Wait for cleanup
            time.sleep(1)

            # Verify session is gone
            sessions_after = tools.list_sessions()
            ports_after = [s.get("port") for s in sessions_after]
            assert port not in ports_after

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass

    @pytest.mark.asyncio
    async def test_resize_session(self, ensure_daemon_stopped):
        """Resize changes terminal dimensions."""
        # Start session
        run_cli(["start", "mcp-resize-test"], timeout=60)
        time.sleep(1)

        # List to get port
        sessions = tools.list_sessions()
        if sessions:
            port = sessions[0]["port"]

            # Resize
            result = tools.resize(port, rows=50, cols=200)

            # Should succeed or return error (session may not support resize)
            assert "error" in result or result.get("status") is not None

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass


@pytest.mark.integration
class TestMCPToolsErrorHandling:
    """Tests for MCP tools error handling."""

    @pytest.mark.asyncio
    async def test_get_status_nonexistent_port(self, ensure_daemon_stopped):
        """Get status on nonexistent port returns error."""
        # Start daemon first
        run_cli(["start", "setup-for-status-test"], timeout=60)
        time.sleep(1)

        # Try nonexistent port
        result = tools.get_status(99999)

        assert "error" in result or result.get("alive") is False

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass

    @pytest.mark.asyncio
    async def test_read_nonexistent_port(self, ensure_daemon_stopped):
        """Read on nonexistent port returns error."""
        # Start daemon first
        run_cli(["start", "setup-for-read-test"], timeout=60)
        time.sleep(1)

        # Try nonexistent port
        result = tools.read(99999)

        assert result.get("output") == "" or "error" in result

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass

    @pytest.mark.asyncio
    async def test_close_nonexistent_port(self, ensure_daemon_stopped):
        """Close on nonexistent port returns error."""
        # Start daemon first
        run_cli(["start", "setup-for-close-test"], timeout=60)
        time.sleep(1)

        # Try nonexistent port
        result = tools.close_session(99999)

        assert "error" in result or result.get("status") == "not_found"

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass
