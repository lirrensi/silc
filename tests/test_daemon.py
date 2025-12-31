"""Tests for SILC daemon functionality."""

import asyncio
import contextlib
import pytest
import requests

from silc.daemon.manager import SilcDaemon, DAEMON_PORT
from silc.daemon.pidfile import write_pidfile, read_pidfile, remove_pidfile


@pytest.mark.asyncio
async def test_daemon_starts_and_stops() -> None:
    """Test that daemon can start and stop cleanly."""
    daemon = SilcDaemon()

    # Start in background
    task = asyncio.create_task(daemon.start())

    # Wait a bit for daemon to initialize
    await asyncio.sleep(1)

    # Check daemon is running
    assert daemon.is_running()

    # Stop daemon
    daemon._shutdown_event.set()

    # Wait for cleanup
    await asyncio.sleep(1)

    # Check daemon stopped
    assert not daemon.is_running()


@pytest.mark.asyncio
async def test_daemon_creates_session() -> None:
    """Test that daemon can create sessions."""
    daemon = SilcDaemon()

    # Start daemon
    task = asyncio.create_task(daemon.start())
    await asyncio.sleep(1)

    try:
        # Create session via API
        import time

        time.sleep(0.5)  # Wait for API to be ready
        resp = requests.post(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions", json={}, timeout=5
        )
        assert resp.status_code == 200

        session_data = resp.json()
        assert "port" in session_data
        assert "session_id" in session_data
        assert "shell" in session_data

        # Check session is in registry
        assert session_data["port"] in daemon.sessions
        assert session_data["port"] in daemon.registry._sessions

    finally:
        daemon._shutdown_event.set()
        await asyncio.sleep(1)


@pytest.mark.asyncio
async def test_daemon_creates_session_with_requested_port() -> None:
    """Test that request payload port is honored."""
    daemon = SilcDaemon()
    task = asyncio.create_task(daemon.start())
    await asyncio.sleep(1)

    try:
        import time

        time.sleep(0.5)
        requested_port = 20500
        resp = requests.post(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions",
            json={"port": requested_port},
            timeout=5,
        )
        assert resp.status_code == 200
        session_data = resp.json()
        assert session_data["port"] == requested_port

    finally:
        daemon._shutdown_event.set()
        await asyncio.sleep(1)


@pytest.mark.asyncio
async def test_daemon_rejects_duplicate_port() -> None:
    """Ensure requesting an occupied port returns HTTP 400."""
    daemon = SilcDaemon()
    task = asyncio.create_task(daemon.start())
    await asyncio.sleep(1)

    try:
        import time

        time.sleep(0.5)
        requested_port = 20510

        resp = requests.post(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions",
            json={"port": requested_port},
            timeout=5,
        )
        resp.raise_for_status()

        second_resp = requests.post(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions",
            json={"port": requested_port},
            timeout=5,
        )
        assert second_resp.status_code == 400
        assert "already in use" in second_resp.json().get("detail", "")
        assert requested_port in daemon.sessions
    finally:
        daemon._shutdown_event.set()
        await asyncio.sleep(1)


@pytest.mark.asyncio
async def test_daemon_lists_sessions() -> None:
    """Test that daemon can list sessions."""
    daemon = SilcDaemon()

    # Start daemon
    task = asyncio.create_task(daemon.start())
    await asyncio.sleep(1)

    try:
        import time

        time.sleep(0.5)

        # Create two sessions
        resp1 = requests.post(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions", json={}, timeout=5
        )
        resp2 = requests.post(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions", json={}, timeout=5
        )

        # List sessions
        resp = requests.get(f"http://127.0.0.1:{DAEMON_PORT}/sessions", timeout=5)
        assert resp.status_code == 200

        sessions = resp.json()
        assert len(sessions) == 2

    finally:
        daemon._shutdown_event.set()
        await asyncio.sleep(1)


@pytest.mark.asyncio
async def test_daemon_closes_session() -> None:
    """Test that daemon can close specific sessions."""
    daemon = SilcDaemon()

    # Start daemon
    task = asyncio.create_task(daemon.start())
    await asyncio.sleep(1)

    try:
        import time

        time.sleep(0.5)

        # Create session
        resp = requests.post(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions", json={}, timeout=5
        )
        port = resp.json()["port"]

        # Close session
        resp = requests.delete(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions/{port}", timeout=5
        )
        assert resp.status_code == 200

        # Check session removed
        assert port not in daemon.sessions

    finally:
        daemon._shutdown_event.set()
        await asyncio.sleep(1)


@pytest.mark.asyncio
async def test_daemon_killall_cleans_all_sessions() -> None:
    """Test that killall removes every session and stops the daemon."""
    daemon = SilcDaemon()

    task = asyncio.create_task(daemon.start())
    await asyncio.sleep(1)

    try:
        import time

        time.sleep(0.5)

        for _ in range(2):
            resp = requests.post(
                f"http://127.0.0.1:{DAEMON_PORT}/sessions", json={}, timeout=5
            )
            resp.raise_for_status()

        resp = requests.post(
            f"http://127.0.0.1:{DAEMON_PORT}/killall", timeout=5
        )
        assert resp.status_code == 200

        await asyncio.sleep(0.5)
        assert not daemon.sessions
        assert not daemon.registry._sessions
    finally:
        daemon._shutdown_event.set()
        try:
            await asyncio.wait_for(task, timeout=2)
        except asyncio.TimeoutError:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await asyncio.sleep(1)


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
    from silc.daemon.registry import SessionRegistry

    registry = SessionRegistry()

    # Add session
    entry = registry.add(21000, "test123", "bash")
    assert entry.port == 21000
    assert entry.session_id == "test123"
    assert entry.shell_type == "bash"

    # Get session
    retrieved = registry.get(21000)
    assert retrieved is not None
    assert retrieved.port == 21000

    # List sessions
    sessions = registry.list_all()
    assert len(sessions) == 1

    # Remove session
    registry.remove(21000)
    assert registry.get(21000) is None


def test_registry_timeout_cleanup() -> None:
    """Test that registry cleans up timed-out sessions."""
    from silc.daemon.registry import SessionRegistry
    from datetime import datetime, timedelta

    registry = SessionRegistry()

    # Add session with old timestamp
    old_time = datetime.utcnow() - timedelta(seconds=2000)
    entry = registry.add(21000, "test123", "bash")
    entry.last_access = old_time

    # Clean up
    cleaned = registry.cleanup_timeout(timeout_seconds=1800)
    assert 21000 in cleaned
    assert registry.get(21000) is None
