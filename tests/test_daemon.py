"""Tests for SILC daemon functionality."""

import asyncio
import contextlib
import subprocess
import sys
from typing import Generator

import httpx
import pytest

from silc.daemon.manager import DAEMON_PORT, SilcDaemon
from silc.daemon.pidfile import read_pidfile, remove_pidfile, write_pidfile


def _shutdown_daemon() -> None:
    try:
        subprocess.run(
            [sys.executable, "-m", "silc", "shutdown"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        pass


@pytest.fixture
async def daemon_fixture():
    """Fixture that provides a running daemon and cleans up after test."""
    _shutdown_daemon()
    await asyncio.sleep(1)

    daemon = SilcDaemon()
    task = asyncio.create_task(daemon.start())
    await wait_for_daemon_start(daemon, timeout=10)

    yield daemon

    # Cleanup
    daemon._shutdown_event.set()
    try:
        await asyncio.wait_for(task, timeout=5)
    except asyncio.TimeoutError:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    _shutdown_daemon()
    try:
        subprocess.run(
            [sys.executable, "-m", "silc", "shutdown"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        pass


async def wait_for_daemon_start(daemon, timeout=10):
    import asyncio
    import socket

    # Give daemon time to start up
    await asyncio.sleep(2)

    # Check if port is listening (simple socket check)
    deadline = asyncio.get_running_loop().time() + (timeout - 2)
    while asyncio.get_running_loop().time() < deadline:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        try:
            sock.connect(("127.0.0.1", DAEMON_PORT))
            sock.close()
            return
        except socket.timeout:
            sock.close()
            await asyncio.sleep(0.3)
        except OSError:
            sock.close()
            await asyncio.sleep(0.3)

    raise AssertionError("Daemon did not become available within timeout")


@pytest.mark.asyncio
async def test_daemon_starts_and_stops(daemon_fixture) -> None:
    """Test that daemon can start and stop cleanly."""
    daemon = daemon_fixture

    # Stop daemon
    daemon._shutdown_event.set()


@pytest.mark.asyncio
async def test_daemon_creates_session() -> None:
    """Test that daemon can create sessions."""
    _shutdown_daemon()
    await asyncio.sleep(1)
    daemon = SilcDaemon()

    # Start daemon
    task = asyncio.create_task(daemon.start())
    await wait_for_daemon_start(daemon, timeout=10)

    try:
        # Create session via API
        await asyncio.sleep(0.5)  # Wait for API to be ready
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"http://127.0.0.1:{DAEMON_PORT}/sessions", json={}, timeout=15
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
        await asyncio.sleep(0.5)
        requested_port = 20500
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"http://127.0.0.1:{DAEMON_PORT}/sessions",
                json={"port": requested_port},
                timeout=15,
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
        await asyncio.sleep(0.5)
        requested_port = 20510

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"http://127.0.0.1:{DAEMON_PORT}/sessions",
                json={"port": requested_port},
                timeout=15,
            )
        resp.raise_for_status()

        async with httpx.AsyncClient() as client:
            second_resp = await client.post(
                f"http://127.0.0.1:{DAEMON_PORT}/sessions",
                json={"port": requested_port},
                timeout=15,
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
        await asyncio.sleep(0.5)

        # Create two sessions
        async with httpx.AsyncClient() as client:
            resp1 = await client.post(
                f"http://127.0.0.1:{DAEMON_PORT}/sessions", json={}, timeout=15
            )
            resp2 = await client.post(
                f"http://127.0.0.1:{DAEMON_PORT}/sessions", json={}, timeout=15
            )

        # List sessions
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"http://127.0.0.1:{DAEMON_PORT}/sessions", timeout=15
            )
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
        await asyncio.sleep(0.5)

        # Create session
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"http://127.0.0.1:{DAEMON_PORT}/sessions", json={}, timeout=15
            )
        port = resp.json()["port"]

        # Close session
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"http://127.0.0.1:{DAEMON_PORT}/sessions/{port}", timeout=15
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
        await asyncio.sleep(0.5)

        for _ in range(2):
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"http://127.0.0.1:{DAEMON_PORT}/sessions", json={}, timeout=15
                )
            resp.raise_for_status()

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"http://127.0.0.1:{DAEMON_PORT}/killall", timeout=15
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
    from datetime import datetime, timedelta

    from silc.daemon.registry import SessionRegistry

    registry = SessionRegistry()

    # Add session with old timestamp
    old_time = datetime.utcnow() - timedelta(seconds=2000)
    entry = registry.add(21000, "test-session", "test123", "bash")
    entry.last_access = old_time

    # Clean up
    cleaned = registry.cleanup_timeout(timeout_seconds=1800)
    assert 21000 in cleaned
    assert registry.get(21000) is None
