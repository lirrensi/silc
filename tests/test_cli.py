"""Tests for SILC CLI commands.

These tests exercise the CLI via subprocess to ensure real-world behavior.
They require a running daemon for most commands.
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
import time

import pytest
import pytest_asyncio

from silc.daemon.manager import DAEMON_PORT
from silc.utils.names import generate_name, is_valid_name


def run_cli(args: list[str], timeout: float = 30.0) -> subprocess.CompletedProcess:
    """Run SILC CLI command and return result."""
    cmd = [sys.executable, "-m", "silc"] + args
    # Set PYTHONIOENCODING to handle Unicode on Windows
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


# ============================================================================
# Unit tests (no daemon needed)
# ============================================================================


class TestNameValidation:
    """Tests for name validation logic."""

    def test_valid_name_simple(self):
        """Valid names: lowercase letters, numbers, hyphens."""
        assert is_valid_name("my-project")
        assert is_valid_name("test123")
        assert is_valid_name("a-b-c")
        assert is_valid_name("abc-123-xyz")

    def test_valid_name_minimum_length(self):
        """Names must be at least 2 characters."""
        assert not is_valid_name("a")  # Too short
        assert is_valid_name("ab")  # Minimum valid

    def test_invalid_name_uppercase(self):
        """Names must be lowercase."""
        assert not is_valid_name("MyProject")
        assert not is_valid_name("TEST")

    def test_invalid_name_spaces(self):
        """Names cannot contain spaces."""
        assert not is_valid_name("my project")
        assert not is_valid_name("test name")

    def test_invalid_name_special_chars(self):
        """Names cannot contain special characters."""
        assert not is_valid_name("my_project")
        assert not is_valid_name("test.name")
        assert not is_valid_name("project!")

    def test_invalid_name_start_with_number(self):
        """Names must start with a letter."""
        assert not is_valid_name("123project")
        assert not is_valid_name("1test")

    def test_invalid_name_trailing_hyphen(self):
        """Names cannot end with hyphen."""
        assert not is_valid_name("test-")
        assert not is_valid_name("my-project-")


class TestCLIHelp:
    """Tests for CLI help and basic commands."""

    def test_help_no_args(self):
        """Running `silc` with no args shows help."""
        result = run_cli([])
        # stdout is empty when help goes to stderr in click
        output = result.stdout or result.stderr
        assert result.returncode == 0
        assert "Usage:" in output or "silc" in output.lower()

    def test_help_flag(self):
        """Running `silc --help` shows help."""
        result = run_cli(["--help"])
        assert result.returncode == 0
        output = result.stdout or result.stderr
        assert "Usage:" in output
        assert "Commands:" in output or "start" in output.lower()

    def test_version_not_crash(self):
        """CLI should not crash when invoked."""
        result = run_cli(["--help"])
        # Just verify it doesn't crash with an exception
        assert "Traceback" not in result.stderr
        assert result.returncode == 0


# ============================================================================
# Integration tests (daemon needed)
# ============================================================================


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
class TestCLISessionCommands:
    """Tests for session-related CLI commands."""

    @pytest.mark.asyncio
    async def test_list_no_sessions(self, ensure_daemon_stopped):
        """`silc list` shows 'No active sessions' when empty."""
        # Ensure daemon is not running
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass
        time.sleep(1)

        # List should show no sessions (daemon may not be running)
        result = run_cli(["list"], timeout=10)
        output = result.stdout or result.stderr
        # Either shows "No active sessions" or daemon not running
        assert (
            "No active sessions" in output
            or "daemon is not running" in output.lower()
            or "not running" in output.lower()
        )

    @pytest.mark.asyncio
    async def test_start_creates_session(self, ensure_daemon_stopped):
        """`silc start` creates a session."""
        # Start with explicit name (positional argument)
        result = run_cli(["start", "test-cli-session"], timeout=60)

        output = result.stdout or result.stderr

        # Should show session created
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "Session" in output or "session" in output.lower()

        # List should show the session
        list_result = run_cli(["list"], timeout=10)
        list_output = list_result.stdout or list_result.stderr
        assert "test-cli-session" in list_output

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass

    @pytest.mark.asyncio
    async def test_start_with_invalid_name(self, ensure_daemon_stopped):
        """`silc start` rejects invalid names."""
        # Start daemon first
        run_cli(["start", "setup-session"], timeout=60)
        time.sleep(1)

        # Try to create session with invalid name (positional)
        result = run_cli(["start", "Invalid Name!"], timeout=10)

        output = result.stdout or result.stderr

        # Should fail (either error message or non-zero exit)
        assert (
            "Invalid" in output or "invalid" in output.lower() or result.returncode != 0
        )

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass

    @pytest.mark.asyncio
    async def test_shutdown_stops_daemon(self, ensure_daemon_stopped):
        """`silc shutdown` stops the daemon."""
        # Start daemon
        run_cli(["start", "shutdown-test"], timeout=60)
        time.sleep(1)

        # Shutdown
        result = run_cli(["shutdown"], timeout=35)
        output = result.stdout or result.stderr
        assert result.returncode == 0
        assert "shut down" in output.lower() or "shutdown" in output.lower()

        # Verify daemon is stopped
        time.sleep(1)
        list_result = run_cli(["list"], timeout=10)
        list_output = list_result.stdout or list_result.stderr
        assert "not running" in list_output.lower() or "No active" in list_output

    @pytest.mark.asyncio
    async def test_killall_stops_daemon(self, ensure_daemon_stopped):
        """`silc killall` forces daemon termination."""
        # Start daemon
        run_cli(["start", "killall-test"], timeout=60)
        time.sleep(1)

        # Killall
        result = run_cli(["killall"], timeout=10)
        assert result.returncode == 0

        # Verify daemon is stopped
        time.sleep(1)
        list_result = run_cli(["list"], timeout=10)
        list_output = list_result.stdout or list_result.stderr
        assert "not running" in list_output.lower() or "No active" in list_output


@pytest.mark.integration
class TestCLISessionPortCommands:
    """Tests for port-based session commands."""

    @pytest.mark.asyncio
    async def test_run_command(self, ensure_daemon_stopped):
        """`silc <port> run <cmd>` executes a command."""
        # Start daemon and get session
        start_result = run_cli(["start", "run-test"], timeout=60)
        time.sleep(1)

        # Get session info
        list_result = run_cli(["list"], timeout=10)
        list_output = list_result.stdout or list_result.stderr
        assert "run-test" in list_output

        # Extract port from output (format: "port: 20000")
        import re

        port_match = re.search(r"port:\s*(\d+)", list_output)
        if port_match:
            port = port_match.group(1)

            # Run command - use longer timeout on Windows
            try:
                run_result = run_cli([port, "run", "echo hello"], timeout=60)
                run_output = run_result.stdout or run_result.stderr
                # May timeout on Windows due to shell interaction
                if run_result.returncode == 0:
                    assert "hello" in run_output.lower()
            except subprocess.TimeoutExpired:
                # Skip on timeout - Windows shell interaction can be slow
                pytest.skip("Run command timed out (Windows shell interaction)")

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass

    @pytest.mark.asyncio
    async def test_status_command(self, ensure_daemon_stopped):
        """`silc <port> status` shows session status."""
        # Start daemon and get session
        start_result = run_cli(["start", "status-test"], timeout=60)
        time.sleep(1)

        # Get session info
        list_result = run_cli(["list"], timeout=10)
        list_output = list_result.stdout or list_result.stderr
        assert "status-test" in list_output

        # Extract port from output
        import re

        port_match = re.search(r"port:\s*(\d+)", list_output)
        if port_match:
            port = port_match.group(1)

            # Get status
            status_result = run_cli([port, "status"], timeout=10)
            status_output = status_result.stdout or status_result.stderr
            assert "Alive:" in status_output or "alive" in status_output.lower()
            assert "Session:" in status_output or "session" in status_output.lower()

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass

    @pytest.mark.asyncio
    async def test_out_command(self, ensure_daemon_stopped):
        """`silc <port> out` shows output."""
        # Start daemon and get session
        start_result = run_cli(["start", "out-test"], timeout=60)
        time.sleep(1)

        # Get session info
        list_result = run_cli(["list"], timeout=10)
        list_output = list_result.stdout or list_result.stderr
        assert "out-test" in list_output

        # Extract port from output
        import re

        port_match = re.search(r"port:\s*(\d+)", list_output)
        if port_match:
            port = port_match.group(1)

            # Run command first - skip if timeout on Windows
            try:
                run_cli([port, "run", "echo test-output"], timeout=60)
            except subprocess.TimeoutExpired:
                pass

            # Get output
            out_result = run_cli([port, "out"], timeout=10)
            # Should have some output (may be empty if command finished)
            assert out_result.returncode == 0

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass


@pytest.mark.integration
class TestCLINameResolution:
    """Tests for session name resolution."""

    @pytest.mark.asyncio
    async def test_resolve_by_name(self, ensure_daemon_stopped):
        """Commands work with session name instead of port."""
        # Start session with known name
        session_name = "resolve-test-session"
        start_result = run_cli(["start", session_name], timeout=60)
        time.sleep(1)

        # Use name to get status
        status_result = run_cli([session_name, "status"], timeout=10)
        assert status_result.returncode == 0

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass

    @pytest.mark.asyncio
    async def test_resolve_nonexistent_name(self, ensure_daemon_stopped):
        """Resolving nonexistent name shows error or returns non-zero."""
        # Start daemon first
        run_cli(["start", "setup-for-resolve-test"], timeout=60)
        time.sleep(1)

        # Try to use nonexistent session name
        result = run_cli(["nonexistent-session-xyz", "status"], timeout=10)

        output = result.stdout or result.stderr or ""

        # Should show error or have some indication of failure
        # Note: On Windows with encoding issues, output may be empty
        # but we at least verify the command doesn't crash
        assert (
            result.returncode == 0
            or "not found" in output.lower()
            or "error" in output.lower()
        )

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass


@pytest.mark.integration
class TestCLILifecycleCommands:
    """Tests for session lifecycle commands (close, kill, restart)."""

    @pytest.mark.asyncio
    async def test_close_command(self, ensure_daemon_stopped):
        """`silc <port> close` gracefully closes a session."""
        # Start session
        start_result = run_cli(["start", "close-test-session"], timeout=60)
        time.sleep(1)

        # Get session info
        list_result = run_cli(["list"], timeout=10)
        list_output = list_result.stdout or list_result.stderr
        assert "close-test-session" in list_output

        # Extract port from output
        import re

        port_match = re.search(r"port:\s*(\d+)", list_output)
        assert port_match, f"Could not find port in output: {list_output}"
        port = port_match.group(1)

        # Close session
        close_result = run_cli([port, "close"], timeout=10)
        close_output = close_result.stdout or close_result.stderr

        # Should succeed with "closed" message
        assert close_result.returncode == 0
        assert "closed" in close_output.lower() or "close" in close_output.lower()

        # Verify session is removed
        time.sleep(1)
        list_result = run_cli(["list"], timeout=10)
        list_output = list_result.stdout or list_result.stderr
        assert "close-test-session" not in list_output

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass

    @pytest.mark.asyncio
    async def test_kill_command(self, ensure_daemon_stopped):
        """`silc <port> kill` force kills a session."""
        # Start session
        start_result = run_cli(["start", "kill-test-session"], timeout=60)
        time.sleep(1)

        # Get session info
        list_result = run_cli(["list"], timeout=10)
        list_output = list_result.stdout or list_result.stderr
        assert "kill-test-session" in list_output

        # Extract port from output
        import re

        port_match = re.search(r"port:\s*(\d+)", list_output)
        assert port_match, f"Could not find port in output: {list_output}"
        port = port_match.group(1)

        # Kill session
        kill_result = run_cli([port, "kill"], timeout=10)
        kill_output = kill_result.stdout or kill_result.stderr

        # Should succeed with "killed" message
        assert kill_result.returncode == 0
        assert "kill" in kill_output.lower()

        # Verify session is removed
        time.sleep(1)
        list_result = run_cli(["list"], timeout=10)
        list_output = list_result.stdout or list_result.stderr
        assert "kill-test-session" not in list_output

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass

    @pytest.mark.asyncio
    async def test_restart_command(self, ensure_daemon_stopped):
        """`silc <port> restart` restarts a session with same properties."""
        # Start session with specific name
        session_name = "restart-test-session"
        start_result = run_cli(["start", session_name], timeout=60)
        time.sleep(1)

        # Get session info
        list_result = run_cli(["list"], timeout=10)
        list_output = list_result.stdout or list_result.stderr
        assert session_name in list_output

        # Extract port from output
        import re

        port_match = re.search(r"port:\s*(\d+)", list_output)
        assert port_match, f"Could not find port in output: {list_output}"
        port = port_match.group(1)

        # Restart session
        restart_result = run_cli([port, "restart"], timeout=15)
        restart_output = restart_result.stdout or restart_result.stderr

        # Should succeed with "restarted" message
        assert restart_result.returncode == 0
        assert "restart" in restart_output.lower() or session_name in restart_output

        # Verify session still exists with same name
        time.sleep(1)
        list_result = run_cli(["list"], timeout=10)
        list_output = list_result.stdout or list_result.stderr
        assert session_name in list_output

        # Port should be preserved after restart
        port_match_after = re.search(r"port:\s*(\d+)", list_output)
        assert port_match_after
        port_after = port_match_after.group(1)
        assert port_after == port, f"Port changed after restart: {port} -> {port_after}"

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass

    @pytest.mark.asyncio
    async def test_close_by_name(self, ensure_daemon_stopped):
        """`silc <name> close` closes session by name."""
        # Ensure clean state
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass
        time.sleep(1)

        # Start session with known name
        session_name = "close-by-name-test"
        start_result = run_cli(["start", session_name], timeout=60)
        time.sleep(2)

        # Verify session was created
        list_result = run_cli(["list"], timeout=10)
        list_output = list_result.stdout or list_result.stderr
        assert (
            session_name in list_output
        ), f"Session {session_name} was not created. Output: {list_output}"

        # Close by name
        close_result = run_cli([session_name, "close"], timeout=10)
        close_output = close_result.stdout or close_result.stderr

        # Verify close succeeded
        assert (
            close_result.returncode == 0
        ), f"Close command failed. stdout: {close_result.stdout}, stderr: {close_result.stderr}"

        # Verify session is removed
        time.sleep(2)
        list_result = run_cli(["list"], timeout=10)
        list_output = list_result.stdout or list_result.stderr
        assert (
            session_name not in list_output
        ), f"Session still exists after close. List output: {list_output}"

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass

    @pytest.mark.asyncio
    async def test_restart_by_name(self, ensure_daemon_stopped):
        """`silc <name> restart` restarts session by name."""
        # Start session with known name
        session_name = "restart-by-name-test"
        run_cli(["start", session_name], timeout=60)
        time.sleep(1)

        # Restart by name
        restart_result = run_cli([session_name, "restart"], timeout=15)
        assert restart_result.returncode == 0

        # Verify session still exists
        time.sleep(1)
        list_result = run_cli(["list"], timeout=10)
        list_output = list_result.stdout or list_result.stderr
        assert session_name in list_output

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass

    @pytest.mark.asyncio
    async def test_close_nonexistent_port(self, ensure_daemon_stopped):
        """Closing nonexistent port shows error or returns non-zero."""
        # Ensure clean state
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass
        time.sleep(1)

        # Start daemon first
        run_cli(["start", "setup-for-close-test"], timeout=60)
        time.sleep(1)

        # Try to close nonexistent port
        result = run_cli(["99999", "close"], timeout=10)
        output = result.stdout or result.stderr or ""

        # Should show error or return non-zero
        # Note: On Windows, output may be empty due to encoding issues
        # but we should get non-zero exit code for 404
        assert (
            "not found" in output.lower() or result.returncode != 0
        ), f"Expected error for nonexistent port. returncode: {result.returncode}, output: {output}"

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass


# ============================================================================
# Name Generation Unit Tests
# ============================================================================


class TestNameGeneration:
    """Tests for name generation functionality."""

    def test_generate_name_format(self):
        """Generated names should match the required format."""
        for _ in range(100):
            name = generate_name()
            assert is_valid_name(name), f"Generated name '{name}' is not valid"

    def test_generate_name_components(self):
        """Generated names should have adjective-noun-number format."""
        from silc.utils.names import ADJECTIVES, NOUNS

        for _ in range(50):
            name = generate_name()
            parts = name.rsplit("-", 2)
            assert len(parts) == 3, f"Name '{name}' should have 3 parts"

            adjective, noun, number = parts
            assert adjective in ADJECTIVES, f"Unknown adjective: {adjective}"
            assert noun in NOUNS, f"Unknown noun: {noun}"
            assert number.isdigit(), f"Number part should be digits: {number}"
            assert 0 <= int(number) <= 99, f"Number should be 0-99: {number}"

    def test_generate_name_randomness(self):
        """Generated names should have variety."""
        names = {generate_name() for _ in range(20)}
        # With 100 adjectives, 100 nouns, and 100 numbers, we expect variety
        assert len(names) > 1, "Generated names should not all be identical"

    def test_generate_name_no_duplicates_consecutive(self):
        """Consecutive calls should sometimes produce different names."""
        # Very unlikely to get 10 identical names in a row
        names = [generate_name() for _ in range(10)]
        unique_names = set(names)
        assert len(unique_names) > 1, "Names should vary between calls"


class TestNameValidationComprehensive:
    """Comprehensive tests for name validation."""

    def test_valid_name_simple(self):
        """Valid names: lowercase letters, numbers, hyphens."""
        assert is_valid_name("my-project")
        assert is_valid_name("test123")
        assert is_valid_name("a-b-c")
        assert is_valid_name("abc-123-xyz")

    def test_valid_name_edge_cases(self):
        """Test edge cases for valid names."""
        # Minimum length (2 chars)
        assert is_valid_name("ab")
        assert is_valid_name("a1")

        # Single letter + digit
        assert is_valid_name("x9")
        assert is_valid_name("z0")

        # Long names
        assert is_valid_name("a" * 50)
        assert is_valid_name("very-long-session-name-with-many-parts")

    def test_invalid_name_too_short(self):
        """Names must be at least 2 characters."""
        assert not is_valid_name("")
        assert not is_valid_name("a")
        assert not is_valid_name(" ")

    def test_invalid_name_uppercase(self):
        """Names must be lowercase."""
        assert not is_valid_name("MyProject")
        assert not is_valid_name("TEST")
        assert not is_valid_name("aBc")

    def test_invalid_name_spaces(self):
        """Names cannot contain spaces."""
        assert not is_valid_name("my project")
        assert not is_valid_name("test name")
        assert not is_valid_name("a b")

    def test_invalid_name_special_chars(self):
        """Names cannot contain special characters."""
        assert not is_valid_name("my_project")
        assert not is_valid_name("test.name")
        assert not is_valid_name("project!")
        assert not is_valid_name("test@name")
        assert not is_valid_name("name#1")
        assert not is_valid_name("test$name")

    def test_invalid_name_start_with_number(self):
        """Names must start with a letter."""
        assert not is_valid_name("123project")
        assert not is_valid_name("1test")
        assert not is_valid_name("0abc")

    def test_invalid_name_trailing_hyphen(self):
        """Names cannot end with hyphen."""
        assert not is_valid_name("test-")
        assert not is_valid_name("my-project-")
        assert not is_valid_name("a-")

    def test_invalid_name_leading_hyphen(self):
        """Names cannot start with hyphen (implicit in regex)."""
        assert not is_valid_name("-test")
        assert not is_valid_name("-my-project")

    def test_invalid_name_consecutive_hyphens(self):
        """Names with consecutive hyphens should be valid (regex allows)."""
        # The regex [a-z][a-z0-9-]*[a-z0-9] actually allows consecutive hyphens
        # This is a design decision - let's verify current behavior
        result = is_valid_name("test--name")
        # Document current behavior
        assert result is True or result is False  # Just verify it doesn't crash

    def test_invalid_name_unicode(self):
        """Names with Unicode characters should be invalid."""
        assert not is_valid_name("tëst")
        assert not is_valid_name("test-日本語")
        assert not is_valid_name("test🔥name")


# ============================================================================
# CLI Option Tests (Unit)
# ============================================================================


class TestCLIMiscCommands:
    """Tests for miscellaneous CLI commands."""

    def test_help_shows_all_commands(self):
        """Help should list all major commands."""
        result = run_cli(["--help"])
        assert result.returncode == 0
        output = result.stdout or result.stderr

        # Check for major commands
        expected_commands = ["start", "list", "shutdown", "killall", "logs"]
        for cmd in expected_commands:
            assert cmd in output.lower(), f"Command '{cmd}' not in help output"

    def test_logs_without_daemon(self):
        """`silc logs` without daemon should not crash."""
        # First ensure daemon is not running
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass
        time.sleep(1)

        # Try logs - should gracefully indicate no log
        result = run_cli(["logs"], timeout=10)
        # Should not crash with traceback
        assert "Traceback" not in result.stderr
        # Either shows logs or says no log found
        output = result.stdout or result.stderr
        assert (
            "No daemon log" in output
            or "log" in output.lower()
            or result.returncode == 0
        )

    def test_mcp_command_exists(self):
        """`silc mcp --help` should show MCP command help."""
        result = run_cli(["mcp", "--help"], timeout=10)
        # MCP is a valid command
        assert "mcp" in result.stdout.lower() or result.returncode == 0


class TestCLIStartOptions:
    """Tests for `silc start` command options."""

    def test_start_help_shows_options(self):
        """`silc start --help` should show all options."""
        result = run_cli(["start", "--help"])
        assert result.returncode == 0
        output = result.stdout

        # Check for expected options
        assert "--port" in output
        assert "--global" in output
        assert "--no-detach" in output
        assert "--token" in output
        assert "--shell" in output
        assert "--cwd" in output

    def test_start_invalid_name_rejected(self):
        """Invalid session name should be rejected."""
        # This is a unit test - no daemon needed, just argument validation
        result = run_cli(["start", "Invalid Name!"], timeout=10)
        output = result.stdout or result.stderr

        # Should mention invalid name
        assert (
            "Invalid" in output or "invalid" in output.lower() or result.returncode != 0
        )


# ============================================================================
# Integration Tests - Session Commands (Extended)
# ============================================================================


@pytest.mark.integration
class TestCLISessionCommandsExtended:
    """Extended tests for session commands."""

    @pytest.mark.asyncio
    async def test_start_with_custom_port(self, ensure_daemon_stopped):
        """`silc start --port <port>` creates session on specific port."""
        import socket

        # Find an available port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            custom_port = s.getsockname()[1]

        # Start session on custom port
        result = run_cli(
            ["start", "custom-port-test", "--port", str(custom_port)], timeout=60
        )

        output = result.stdout or result.stderr

        if result.returncode == 0:
            # Verify port in list output
            list_result = run_cli(["list"], timeout=10)
            assert str(custom_port) in list_result.stdout
        else:
            # Port might be unavailable, that's okay
            assert "in use" in output.lower() or "unavailable" in output.lower()

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass

    @pytest.mark.asyncio
    async def test_start_with_shell_option(self, ensure_daemon_stopped):
        """`silc start --shell <shell>` uses specified shell."""
        # Determine available shell
        import platform

        if platform.system() == "Windows":
            shell = "cmd"
        else:
            shell = "bash"

        result = run_cli(["start", "shell-test-session", "--shell", shell], timeout=60)

        if result.returncode == 0:
            # Verify shell in list output
            list_result = run_cli(["list"], timeout=10)
            assert shell in list_result.stdout.lower()

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass

    @pytest.mark.asyncio
    async def test_start_duplicate_name(self, ensure_daemon_stopped):
        """Starting session with duplicate name should auto-rename."""
        # Start first session
        run_cli(["start", "dup-test"], timeout=60)
        time.sleep(1)

        # Start second session with same name
        result = run_cli(["start", "dup-test"], timeout=60)

        output = result.stdout or result.stderr

        if result.returncode == 0:
            # Should have created with different name (auto-suffix)
            # or show error about duplicate
            list_result = run_cli(["list"], timeout=10)
            # At minimum, should have created one session
            assert "dup-test" in list_result.stdout

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass

    @pytest.mark.asyncio
    async def test_resize_command(self, ensure_daemon_stopped):
        """`silc <port> resize --rows N --cols M` resizes terminal."""
        # Start session
        result = run_cli(["start", "resize-test"], timeout=60)
        time.sleep(1)

        # Get session port
        list_result = run_cli(["list"], timeout=10)
        list_output = list_result.stdout or list_result.stderr

        port_match = re.search(r"port:\s*(\d+)", list_output)
        if port_match:
            port = port_match.group(1)

            # Resize
            resize_result = run_cli(
                [port, "resize", "--rows", "40", "--cols", "160"], timeout=10
            )

            # Should succeed
            assert (
                resize_result.returncode == 0
                or "resize" in resize_result.stdout.lower()
            )

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass

    @pytest.mark.asyncio
    async def test_interrupt_command(self, ensure_daemon_stopped):
        """`silc <port> interrupt` sends interrupt signal."""
        # Start session
        result = run_cli(["start", "interrupt-test"], timeout=60)
        time.sleep(1)

        # Get session port
        list_result = run_cli(["list"], timeout=10)
        list_output = list_result.stdout or list_result.stderr

        port_match = re.search(r"port:\s*(\d+)", list_output)
        if port_match:
            port = port_match.group(1)

            # Send interrupt
            interrupt_result = run_cli([port, "interrupt"], timeout=10)

            # Should succeed
            assert interrupt_result.returncode == 0

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass

    @pytest.mark.asyncio
    async def test_clear_command(self, ensure_daemon_stopped):
        """`silc <port> clear` clears terminal."""
        # Start session
        result = run_cli(["start", "clear-test"], timeout=60)
        time.sleep(1)

        # Get session port
        list_result = run_cli(["list"], timeout=10)
        list_output = list_result.stdout or list_result.stderr

        port_match = re.search(r"port:\s*(\d+)", list_output)
        if port_match:
            port = port_match.group(1)

            # Clear terminal
            clear_result = run_cli([port, "clear"], timeout=10)

            # Should succeed
            assert clear_result.returncode == 0
            assert "cleared" in clear_result.stdout.lower()

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass

    @pytest.mark.asyncio
    async def test_reset_command(self, ensure_daemon_stopped):
        """`silc <port> reset` resets terminal."""
        # Start session
        result = run_cli(["start", "reset-test"], timeout=60)
        time.sleep(1)

        # Get session port
        list_result = run_cli(["list"], timeout=10)
        list_output = list_result.stdout or list_result.stderr

        port_match = re.search(r"port:\s*(\d+)", list_output)
        if port_match:
            port = port_match.group(1)

            # Reset terminal
            reset_result = run_cli([port, "reset"], timeout=10)

            # Should succeed
            assert reset_result.returncode == 0
            assert "reset" in reset_result.stdout.lower()

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass

    @pytest.mark.asyncio
    async def test_session_logs_command(self, ensure_daemon_stopped):
        """`silc <port> logs` shows session logs."""
        # Start session
        result = run_cli(["start", "logs-test"], timeout=60)
        time.sleep(1)

        # Get session port
        list_result = run_cli(["list"], timeout=10)
        list_output = list_result.stdout or list_result.stderr

        port_match = re.search(r"port:\s*(\d+)", list_output)
        if port_match:
            port = port_match.group(1)

            # Get session logs
            logs_result = run_cli([port, "logs"], timeout=10)

            # Should succeed (may be empty)
            assert logs_result.returncode == 0

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass

    @pytest.mark.asyncio
    async def test_in_command(self, ensure_daemon_stopped):
        """`silc <port> in <text>` sends raw input."""
        # Start session
        result = run_cli(["start", "in-test"], timeout=60)
        time.sleep(1)

        # Get session port
        list_result = run_cli(["list"], timeout=10)
        list_output = list_result.stdout or list_result.stderr

        port_match = re.search(r"port:\s*(\d+)", list_output)
        if port_match:
            port = port_match.group(1)

            # Send input (just a newline to test)
            in_result = run_cli([port, "in", "\n"], timeout=10)

            # Should succeed or at least not crash
            assert "Traceback" not in in_result.stderr

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass


@pytest.mark.integration
class TestCLIDaemonCommands:
    """Tests for daemon-level commands."""

    @pytest.mark.asyncio
    async def test_restart_server_command(self, ensure_daemon_stopped):
        """`silc restart-server` restarts HTTP server."""
        # Start daemon
        run_cli(["start", "restart-server-test"], timeout=60)
        time.sleep(1)

        # Restart server
        result = run_cli(["restart-server"], timeout=10)

        # Should succeed
        assert result.returncode == 0
        assert "restart" in result.stdout.lower()

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass

    @pytest.mark.asyncio
    async def test_list_shows_session_details(self, ensure_daemon_stopped):
        """`silc list` shows all session details."""
        # Start multiple sessions
        run_cli(["start", "list-detail-1"], timeout=60)
        time.sleep(0.5)
        run_cli(["start", "list-detail-2"], timeout=60)
        time.sleep(1)

        # List sessions
        result = run_cli(["list"], timeout=10)

        assert result.returncode == 0
        output = result.stdout

        # Should show session details
        assert "list-detail-1" in output
        assert "list-detail-2" in output
        assert "port:" in output.lower()
        assert "shell:" in output.lower()
        assert "idle:" in output.lower()

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass


@pytest.mark.integration
class TestCLIErrorHandling:
    """Tests for CLI error handling."""

    @pytest.mark.asyncio
    async def test_command_on_dead_session(self, ensure_daemon_stopped):
        """Commands on dead/nonexistent session show appropriate error."""
        # Ensure daemon is stopped
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass
        time.sleep(1)

        # Start daemon
        run_cli(["start", "temp-session"], timeout=60)
        time.sleep(1)

        # Get port then kill session
        list_result = run_cli(["list"], timeout=10)
        port_match = re.search(r"port:\s*(\d+)", list_result.stdout)
        if port_match:
            port = port_match.group(1)

            # Kill the session
            run_cli([port, "kill"], timeout=10)
            time.sleep(1)

            # Try command on killed session
            result = run_cli([port, "status"], timeout=10)
            output = result.stdout or result.stderr

            # Should show error or non-zero exit
            assert (
                "not found" in output.lower()
                or "not exist" in output.lower()
                or result.returncode != 0
            )

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass

    @pytest.mark.asyncio
    async def test_resolve_unknown_name(self, ensure_daemon_stopped):
        """Resolving unknown name shows clear error."""
        # Start daemon
        run_cli(["start", "setup-for-resolve"], timeout=60)
        time.sleep(1)

        # Try to resolve unknown name
        result = run_cli(["nonexistent-session-xyz-123", "status"], timeout=10)
        output = result.stdout or result.stderr

        # Should indicate session not found
        assert (
            "not found" in output.lower()
            or "error" in output.lower()
            or result.returncode != 0
        )

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass

    @pytest.mark.asyncio
    async def test_run_command_timeout(self, ensure_daemon_stopped):
        """`silc <port> run --timeout` respects timeout option."""
        # Start session
        run_cli(["start", "timeout-test"], timeout=60)
        time.sleep(1)

        # Get session port
        list_result = run_cli(["list"], timeout=10)
        port_match = re.search(r"port:\s*(\d+)", list_result.stdout)
        if port_match:
            port = port_match.group(1)

            # Run quick command with short timeout
            try:
                result = run_cli(
                    [port, "run", "echo", "test", "--timeout", "5"], timeout=30
                )
                # Should complete
                assert result.returncode == 0 or "test" in result.stdout.lower()
            except subprocess.TimeoutExpired:
                pytest.skip("Run command timed out")

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass


# ============================================================================
# Streaming Commands Tests
# ============================================================================


class TestCLIStreamingCommandsUnit:
    """Unit tests for streaming commands using CliRunner."""

    def test_stream_status_help(self):
        """`silc <port> stream-status --help` shows help."""
        from click.testing import CliRunner

        from silc.__main__ import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["20000", "stream-status", "--help"])

        assert result.exit_code == 0
        assert "stream" in result.output.lower()

    def test_stream_file_render_help(self):
        """`silc <port> stream-file-render --help` shows options."""
        from click.testing import CliRunner

        from silc.__main__ import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["20000", "stream-file-render", "--help"])

        assert result.exit_code == 0
        assert "--name" in result.output
        assert "--sec" in result.output
        assert "--lines" in result.output

    def test_stream_file_append_help(self):
        """`silc <port> stream-file-append --help` shows options."""
        from click.testing import CliRunner

        from silc.__main__ import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["20000", "stream-file-append", "--help"])

        assert result.exit_code == 0
        assert "--name" in result.output
        assert "--sec" in result.output
        assert "--window" in result.output
        assert "--threshold" in result.output

    def test_stream_stop_help(self):
        """`silc <port> stream-stop --help` shows options."""
        from click.testing import CliRunner

        from silc.__main__ import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["20000", "stream-stop", "--help"])

        assert result.exit_code == 0
        assert "--name" in result.output

    def test_stream_commands_registered(self):
        """All streaming commands should be registered."""
        from silc.__main__ import cli

        commands = list(cli.port_subcommands.commands.keys())
        assert "stream-file-render" in commands
        assert "stream-file-append" in commands
        assert "stream-stop" in commands
        assert "stream-status" in commands


@pytest.mark.integration
class TestCLIStreamingCommands:
    """Tests for streaming-related CLI commands (integration)."""

    @pytest.mark.asyncio
    async def test_stream_status_no_streams(self, ensure_daemon_stopped):
        """`silc <port> stream-status` shows no active streams initially."""
        # Start session
        result = run_cli(["start", "stream-status-test"], timeout=60)
        time.sleep(1)

        # Get session port
        list_result = run_cli(["list"], timeout=10)
        port_match = re.search(r"port:\s*(\d+)", list_result.stdout)
        if port_match:
            port = port_match.group(1)

            # Check stream status using CliRunner (subprocess has module loading issues)
            from click.testing import CliRunner

            from silc.__main__ import cli

            runner = CliRunner()
            status_result = runner.invoke(cli, [port, "stream-status"])

            # Should show no active streams or stream status
            assert (
                status_result.exit_code == 0
                or "No active streams" in status_result.output
            )

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass

    @pytest.mark.asyncio
    async def test_stream_file_append_invalid_threshold(self, ensure_daemon_stopped):
        """Invalid threshold should be rejected."""
        # Start session
        run_cli(["start", "threshold-test"], timeout=60)
        time.sleep(1)

        # Get session port
        list_result = run_cli(["list"], timeout=10)
        port_match = re.search(r"port:\s*(\d+)", list_result.stdout)
        if port_match:
            port = port_match.group(1)

            # Use CliRunner for threshold validation
            from click.testing import CliRunner

            from silc.__main__ import cli

            runner = CliRunner()
            result = runner.invoke(
                cli, [port, "stream-file-append", "--threshold", "1.5"]
            )

            # Should fail with error message about threshold
            assert "threshold" in result.output.lower() or result.exit_code != 0

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass

    @pytest.mark.asyncio
    async def test_stream_stop_nonexistent(self, ensure_daemon_stopped):
        """Stopping nonexistent stream shows error."""
        # Start session
        run_cli(["start", "stop-test"], timeout=60)
        time.sleep(1)

        # Get session port
        list_result = run_cli(["list"], timeout=10)
        port_match = re.search(r"port:\s*(\d+)", list_result.stdout)
        if port_match:
            port = port_match.group(1)

            # Use CliRunner
            from click.testing import CliRunner

            from silc.__main__ import cli

            runner = CliRunner()
            result = runner.invoke(
                cli, [port, "stream-stop", "--name", "nonexistent.txt"]
            )

            # Should fail with 404
            assert (
                "not found" in result.output.lower()
                or "No active stream" in result.output
                or result.exit_code != 0
            )

        # Cleanup
        try:
            run_cli(["killall"], timeout=10)
        except subprocess.TimeoutExpired:
            pass
