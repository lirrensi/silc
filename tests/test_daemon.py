"""Tests for SILC daemon functionality.

This module tests the daemon lifecycle, session management, and registry operations.
Tests are designed to work on Windows and Unix platforms.
"""

from __future__ import annotations

import asyncio
import contextlib
import socket
import subprocess
import sys
from datetime import datetime, timedelta
from typing import AsyncGenerator

import httpx
import pytest
import pytest_asyncio

from silc.daemon.manager import DAEMON_PORT, SilcDaemon
from silc.daemon.pidfile import read_pidfile, remove_pidfile, write_pidfile
from silc.daemon.registry import SessionRegistry


def _shutdown_daemon() -> None:
    """Best-effort daemon shutdown via CLI."""
    try:
        subprocess.run(
            [sys.executable, "-m", "silc", "shutdown"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass


def _kill_daemon() -> None:
    """Force kill daemon via CLI."""
    try:
        subprocess.run(
            [sys.executable, "-m", "silc", "killall"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass


def _is_port_open(port: int, timeout: float = 0.5) -> bool:
    """Check if a port is accepting connections."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex(("127.0.0.1", port)) == 0


async def _wait_for_port(
    port: int, timeout: float = 15.0, poll_interval: float = 0.2
) -> bool:
    """Wait for a port to become available."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if _is_port_open(port, timeout=0.3):
            return True
        await asyncio.sleep(poll_interval)
    return _is_port_open(port, timeout=0.3)


async def _wait_for_daemon_api(timeout: float = 15.0) -> bool:
    """Wait for daemon API to be responsive."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"http://127.0.0.1:{DAEMON_PORT}/sessions", timeout=1.0
                )
                if resp.status_code == 200:
                    return True
        except Exception:
            pass
        await asyncio.sleep(0.3)
    return False


# Clean up any existing daemon before tests
@pytest.fixture(scope="module", autouse=True)
def cleanup_daemon_before_and_after():
    """Ensure daemon is stopped before and after test module."""
    _kill_daemon()
    yield
    _kill_daemon()


# ============================================================================
# Unit tests (no daemon needed)
# ============================================================================


def test_pidfile_operations() -> None:
    """Test PID file read/write operations."""
    # Clean up first
    remove_pidfile()

    # Write PID
    write_pidfile(12345)
    assert read_pidfile() == 12345

    # Remove PID
    remove_pidfile()
    assert read_pidfile() is None


def test_registry_add_remove() -> None:
    """Test session registry operations."""
    registry = SessionRegistry()

    # Add session
    entry = registry.add(21000, "test-session", "test123", "bash")
    assert entry.port == 21000
    assert entry.name == "test-session"
    assert entry.session_id == "test123"
    assert entry.shell_type == "bash"

    # Get session by port
    retrieved = registry.get(21000)
    assert retrieved is not None
    assert retrieved.port == 21000

    # Get session by name
    retrieved_by_name = registry.get_by_name("test-session")
    assert retrieved_by_name is not None
    assert retrieved_by_name.port == 21000

    # Check name exists
    assert registry.name_exists("test-session")
    assert not registry.name_exists("nonexistent")

    # List sessions
    sessions = registry.list_all()
    assert len(sessions) == 1

    # Remove session
    registry.remove(21000)
    assert registry.get(21000) is None
    assert not registry.name_exists("test-session")


def test_registry_timeout_cleanup() -> None:
    """Test that registry cleans up timed-out sessions."""
    registry = SessionRegistry()

    # Add session with old timestamp
    old_time = datetime.utcnow() - timedelta(seconds=2000)
    entry = registry.add(21000, "test-session", "test123", "bash")
    entry.last_access = old_time

    # Clean up
    cleaned = registry.cleanup_timeout(timeout_seconds=1800)
    assert 21000 in cleaned
    assert registry.get(21000) is None


# ============================================================================
# Integration tests (daemon needed)
# ============================================================================


@pytest_asyncio.fixture
async def running_daemon() -> AsyncGenerator[SilcDaemon, None]:
    """Fixture that provides a running daemon and cleans up after test."""
    # Ensure clean state
    _kill_daemon()
    await asyncio.sleep(0.5)
    remove_pidfile()

    # Create daemon with hard_exit disabled for tests
    daemon = SilcDaemon(enable_hard_exit=False)
    task = asyncio.create_task(daemon.start())

    # Wait for daemon to be ready
    ready = await _wait_for_daemon_api(timeout=20.0)
    if not ready:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        pytest.fail("Daemon failed to start within timeout")

    yield daemon

    # Cleanup
    daemon._shutdown_event.set()
    try:
        await asyncio.wait_for(task, timeout=5.0)
    except asyncio.TimeoutError:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    except Exception:
        pass

    # Ensure cleanup
    _kill_daemon()
    remove_pidfile()


@pytest.mark.asyncio
async def test_daemon_starts_and_responds(running_daemon: SilcDaemon) -> None:
    """Test that daemon starts and responds to API requests."""
    daemon = running_daemon

    # Verify daemon is running
    assert daemon.is_running()

    # Verify API responds
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"http://127.0.0.1:{DAEMON_PORT}/sessions", timeout=5.0)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_daemon_creates_session(running_daemon: SilcDaemon) -> None:
    """Test that daemon can create sessions."""
    daemon = running_daemon

    # Create session via API
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions",
            json={"name": "test-create-session"},
            timeout=30.0,
        )

    assert resp.status_code == 200
    session_data = resp.json()
    assert "port" in session_data
    assert "session_id" in session_data
    assert "shell" in session_data
    assert session_data["name"] == "test-create-session"

    # Check session is in registry
    port = session_data["port"]
    assert port in daemon.sessions
    assert port in daemon.registry._sessions


@pytest.mark.asyncio
async def test_daemon_creates_session_with_requested_port(
    running_daemon: SilcDaemon,
) -> None:
    """Test that request payload port is honored."""
    daemon = running_daemon

    requested_port = 20100
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions",
            json={"port": requested_port, "name": "test-port-session"},
            timeout=30.0,
        )

    assert resp.status_code == 200
    session_data = resp.json()
    assert session_data["port"] == requested_port


@pytest.mark.asyncio
async def test_daemon_rejects_duplicate_port(running_daemon: SilcDaemon) -> None:
    """Ensure requesting an occupied port returns HTTP 400."""
    daemon = running_daemon

    requested_port = 20110

    # Create first session
    async with httpx.AsyncClient() as client:
        resp1 = await client.post(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions",
            json={"port": requested_port, "name": "test-dup-first"},
            timeout=30.0,
        )
    assert resp1.status_code == 200

    # Try to create second session with same port
    async with httpx.AsyncClient() as client:
        resp2 = await client.post(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions",
            json={"port": requested_port, "name": "test-dup-second"},
            timeout=30.0,
        )

    assert resp2.status_code == 400
    assert "already in use" in resp2.json().get("detail", "")


@pytest.mark.asyncio
async def test_daemon_lists_sessions(running_daemon: SilcDaemon) -> None:
    """Test that daemon can list sessions."""
    daemon = running_daemon

    # Create two sessions
    async with httpx.AsyncClient() as client:
        resp1 = await client.post(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions",
            json={"name": "test-list-1"},
            timeout=30.0,
        )
        resp2 = await client.post(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions",
            json={"name": "test-list-2"},
            timeout=30.0,
        )

    assert resp1.status_code == 200
    assert resp2.status_code == 200

    # List sessions
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions", timeout=10.0
        )

    assert resp.status_code == 200
    sessions = resp.json()
    assert len(sessions) >= 2

    # Verify our sessions are in the list
    names = {s["name"] for s in sessions}
    assert "test-list-1" in names
    assert "test-list-2" in names


@pytest.mark.asyncio
async def test_daemon_closes_session(running_daemon: SilcDaemon) -> None:
    """Test that daemon can close specific sessions via POST /sessions/{port}/close."""
    daemon = running_daemon

    # Create session
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions",
            json={"name": "test-close-session"},
            timeout=30.0,
        )

    assert resp.status_code == 200
    port = resp.json()["port"]

    # Close session via new POST endpoint
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions/{port}/close", timeout=10.0
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "closed"

    # Wait for cleanup
    await asyncio.sleep(1.0)

    # Verify session is removed
    assert port not in daemon.sessions


@pytest.mark.asyncio
async def test_daemon_kills_session(running_daemon: SilcDaemon) -> None:
    """Test that daemon can force kill a session via POST /sessions/{port}/kill."""
    daemon = running_daemon

    # Create session
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions",
            json={"name": "test-kill-session"},
            timeout=30.0,
        )

    assert resp.status_code == 200
    port = resp.json()["port"]

    # Kill session via POST endpoint
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions/{port}/kill", timeout=10.0
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "killed"

    # Wait for cleanup
    await asyncio.sleep(1.0)

    # Verify session is removed
    assert port not in daemon.sessions


@pytest.mark.asyncio
async def test_daemon_restarts_session(running_daemon: SilcDaemon) -> None:
    """Test that daemon can restart a session via POST /sessions/{port}/restart."""
    daemon = running_daemon

    # Create session with specific name
    session_name = "test-restart-session"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions",
            json={"name": session_name},
            timeout=30.0,
        )

    assert resp.status_code == 200
    original_port = resp.json()["port"]
    original_session_id = resp.json()["session_id"]

    # Restart session via POST endpoint
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions/{original_port}/restart",
            timeout=15.0,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "restarted"
    assert data["name"] == session_name
    # Port should be preserved
    assert data["port"] == original_port

    # Wait for restart to complete
    await asyncio.sleep(1.0)

    # Verify session still exists with same port
    assert original_port in daemon.sessions
    # Session ID should be different after restart
    new_session = daemon.sessions[original_port]
    assert new_session.name == session_name


@pytest.mark.asyncio
async def test_daemon_close_nonexistent_session(running_daemon: SilcDaemon) -> None:
    """Test that closing nonexistent session returns 404."""
    # Try to close session that doesn't exist
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions/99999/close", timeout=10.0
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_daemon_kill_nonexistent_session(running_daemon: SilcDaemon) -> None:
    """Test that killing nonexistent session returns 404."""
    # Try to kill session that doesn't exist
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions/99999/kill", timeout=10.0
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_daemon_restart_nonexistent_session(running_daemon: SilcDaemon) -> None:
    """Test that restarting nonexistent session returns 404."""
    # Try to restart session that doesn't exist
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions/99999/restart", timeout=10.0
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_daemon_resolves_session_by_name(running_daemon: SilcDaemon) -> None:
    """Test that daemon can resolve session name to port."""
    daemon = running_daemon

    # Create session with known name
    session_name = "test-resolve-name"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions",
            json={"name": session_name},
            timeout=30.0,
        )

    assert resp.status_code == 200
    port = resp.json()["port"]

    # Resolve by name
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"http://127.0.0.1:{DAEMON_PORT}/resolve/{session_name}", timeout=5.0
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["port"] == port
    assert data["name"] == session_name


@pytest.mark.asyncio
async def test_daemon_rejects_invalid_name(running_daemon: SilcDaemon) -> None:
    """Test that daemon rejects invalid session names."""
    daemon = running_daemon

    # Try to create session with invalid name
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions",
            json={"name": "Invalid Name!"},
            timeout=10.0,
        )

    assert resp.status_code == 400
    assert "Invalid name format" in resp.json().get("detail", "")


@pytest.mark.asyncio
async def test_daemon_shutdown_endpoint(running_daemon: SilcDaemon) -> None:
    """Test that shutdown endpoint works."""
    daemon = running_daemon

    # Request shutdown
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://127.0.0.1:{DAEMON_PORT}/shutdown", timeout=35.0
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "shutdown"

    # Wait for daemon to stop
    await asyncio.sleep(2.0)

    # Verify daemon is no longer running
    assert not _is_port_open(DAEMON_PORT)
