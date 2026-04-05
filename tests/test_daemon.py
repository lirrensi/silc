# FILE: tests/test_daemon.py
# PURPOSE: Verify daemon lifecycle, registry behavior, session persistence, and websocket event emission.
# OWNS: Daemon API coverage, session registry checks, and session event integration tests.
# DOCS: docs/arch_daemon.md, agent_chat/plan_manager_qol_2026-04-05.md

"""Tests for SILC daemon functionality.

This module tests the daemon lifecycle, session management, and registry operations.
Tests are designed to work on Windows and Unix platforms.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import socket
import struct
import subprocess
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from silc.daemon.manager import DAEMON_PORT, SilcDaemon
from silc.daemon.pidfile import read_pidfile, remove_pidfile, write_pidfile
from silc.daemon.registry import SessionRegistry
from silc.daemon.runtime import SessionState


def _decode_ws_frame(frame: bytes) -> tuple[dict, bytes]:
    header_length = struct.unpack(">I", frame[:4])[0]
    header = json.loads(frame[4 : 4 + header_length].decode("utf-8"))
    payload = frame[4 + header_length :]
    return header, payload


async def _post_daemon_json(
    daemon: SilcDaemon, path: str, payload: dict
) -> httpx.Response:
    transport = httpx.ASGITransport(app=daemon._create_daemon_api())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(path, json=payload)


class _EventTestSession:
    def __init__(self, port: int, name: str, session_id: str) -> None:
        self.port = port
        self.name = name
        self.session_id = session_id
        self.title = ""
        self.cwd = None
        self.title_updated_at = datetime.utcnow()
        self.api_token = None
        self.closed = False
        self.killed = False

    def get_status(self) -> dict:
        return {"alive": True, "idle_seconds": 0, "cwd": self.cwd}

    async def start(self) -> None:
        return None

    async def close(self) -> None:
        self.closed = True

    async def force_kill(self) -> None:
        self.killed = True


class _DummyServer:
    def __init__(self) -> None:
        self.should_exit = False

    async def serve(self, sockets=None) -> None:
        while not self.should_exit:
            await asyncio.sleep(0.01)


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


async def wait_for_daemon_start(
    daemon: SilcDaemon | None = None, timeout: float = 15.0
) -> bool:
    """Compatibility helper for tests that wait on the daemon API."""
    _ = daemon
    return await _wait_for_daemon_api(timeout=timeout)


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
    assert entry.title == ""
    assert entry.session_id == "test123"
    assert entry.shell_type == "bash"
    assert entry.to_json()["title"] == ""

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


def test_daemon_events_websocket_sends_initial_snapshot() -> None:
    daemon = SilcDaemon(enable_hard_exit=False)
    daemon.registry.add(20000, "alpha", "sess-1", "bash", cwd="/tmp")

    client = TestClient(daemon._create_daemon_api())
    with client.websocket_connect("/events") as websocket:
        frame = websocket.receive_bytes()

    header, payload = _decode_ws_frame(frame)
    assert payload == b""
    assert header["type"] == "session/snapshot"
    assert header["sessions"][0]["port"] == 20000


@pytest.mark.asyncio
async def test_create_session_publishes_created_and_updated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    daemon = SilcDaemon(enable_hard_exit=False)
    published: list[str] = []

    async def record_publish(header: dict[str, object]) -> None:
        published.append(str(header["type"]))

    async def fake_construct(*args, **kwargs):
        return _EventTestSession(20011, "events-create", "sess-create")

    monkeypatch.setattr(daemon, "_find_available_session_port", lambda: 20011)
    monkeypatch.setattr(
        daemon, "_validate_session_launch", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(daemon, "_construct_session", fake_construct)
    monkeypatch.setattr(
        daemon, "_reserve_session_socket", lambda *args, **kwargs: object()
    )
    monkeypatch.setattr(daemon, "_attach_session_task", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        daemon, "_create_session_server", lambda *args, **kwargs: _DummyServer()
    )
    monkeypatch.setattr(daemon.events, "publish", record_publish)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=daemon._create_daemon_api()),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/sessions", json={"name": "events-create", "shell": "bash"}
        )

    assert resp.status_code == 200
    assert "session/created" in published
    assert "session/updated" in published


@pytest.mark.asyncio
async def test_rename_session_updates_name_and_publishes_events(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from silc.utils import persistence

    monkeypatch.setattr(persistence, "SESSIONS_FILE", tmp_path / "sessions.json")

    daemon = SilcDaemon(enable_hard_exit=False)
    published: list[str] = []
    entry = daemon.registry.add(20015, "rename-me", "sess-rename", "bash")
    runtime = SimpleNamespace(
        session=_EventTestSession(entry.port, entry.name, entry.session_id),
        state=SessionState.RUNNING,
    )
    daemon.runtime_by_port[entry.port] = runtime
    daemon.sessions[entry.port] = runtime.session

    async def record_publish(header: dict[str, object]) -> None:
        published.append(str(header["type"]))

    monkeypatch.setattr(daemon.events, "publish", record_publish)

    resp = await _post_daemon_json(
        daemon, "/sessions/20015/rename", {"name": "renamed"}
    )

    assert resp.status_code == 200
    assert daemon.registry.get(20015).name == "renamed"
    assert daemon.sessions[20015].name == "renamed"
    assert published == ["session/renamed", "session/updated"]
    assert persistence.read_sessions_json()[0]["name"] == "renamed"


@pytest.mark.asyncio
async def test_rename_session_rejects_duplicate_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from silc.utils import persistence

    monkeypatch.setattr(persistence, "SESSIONS_FILE", tmp_path / "sessions.json")

    daemon = SilcDaemon(enable_hard_exit=False)
    daemon.registry.add(20016, "first", "sess-first", "bash")
    daemon.registry.add(20017, "second", "sess-second", "bash")

    resp = await _post_daemon_json(daemon, "/sessions/20016/rename", {"name": "second"})

    assert resp.status_code == 400
    assert "already in use" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_reorder_sessions_persists_order_and_broadcasts_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from silc.utils import persistence

    monkeypatch.setattr(persistence, "SESSIONS_FILE", tmp_path / "sessions.json")

    daemon = SilcDaemon(enable_hard_exit=False)
    published: list[str] = []
    daemon.registry.add(20018, "alpha", "sess-a", "bash")
    daemon.registry.add(20019, "beta", "sess-b", "bash")
    daemon.registry.add(20020, "gamma", "sess-c", "bash")
    daemon._persist_desired_sessions()

    async def record_publish(header: dict[str, object]) -> None:
        published.append(str(header["type"]))

    monkeypatch.setattr(daemon.events, "publish", record_publish)

    resp = await _post_daemon_json(
        daemon,
        "/sessions/reorder",
        {"ports": [20020, 20018, 20019]},
    )

    assert resp.status_code == 200
    assert [item["port"] for item in resp.json()["sessions"]] == [20020, 20018, 20019]
    assert [item["port"] for item in persistence.read_sessions_json()] == [
        20020,
        20018,
        20019,
    ]
    assert published == ["session/reordered", "session/snapshot"]


@pytest.mark.asyncio
async def test_title_change_publishes_title_changed_and_updated() -> None:
    daemon = SilcDaemon(enable_hard_exit=False)
    published: list[str] = []
    entry = daemon.registry.add(20012, "events-title", "sess-title", "bash")
    session = _EventTestSession(entry.port, entry.name, entry.session_id)
    session.title = "New title"
    runtime = SimpleNamespace(session=session, state=SessionState.RUNNING)
    daemon.runtime_by_port[entry.port] = runtime

    async def record_publish(header: dict[str, object]) -> None:
        published.append(str(header["type"]))

    daemon.events.publish = record_publish  # type: ignore[method-assign]
    daemon._handle_session_title_change(session)
    await asyncio.sleep(0)

    assert published == ["session/title_changed", "session/updated"]


@pytest.mark.asyncio
async def test_cwd_change_publishes_cwd_changed_and_updated() -> None:
    daemon = SilcDaemon(enable_hard_exit=False)
    published: list[str] = []
    entry = daemon.registry.add(20013, "events-cwd", "sess-cwd", "bash")
    session = _EventTestSession(entry.port, entry.name, entry.session_id)
    session.cwd = "/tmp/project"
    runtime = SimpleNamespace(session=session, state=SessionState.RUNNING, cwd=None)
    daemon.runtime_by_port[entry.port] = runtime

    async def record_publish(header: dict[str, object]) -> None:
        published.append(str(header["type"]))

    daemon.events.publish = record_publish  # type: ignore[method-assign]
    daemon._handle_session_cwd_change(session)
    await asyncio.sleep(0)

    assert published == ["session/cwd_changed", "session/updated"]


@pytest.mark.asyncio
async def test_remove_session_publishes_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    daemon = SilcDaemon(enable_hard_exit=False)
    published: list[str] = []
    entry = daemon.registry.add(20014, "events-remove", "sess-remove", "bash")
    runtime = SimpleNamespace(
        generation=1,
        session=_EventTestSession(entry.port, entry.name, entry.session_id),
        state=SessionState.RUNNING,
    )
    daemon.runtime_by_port[entry.port] = runtime

    async def fake_cleanup(*args, **kwargs) -> None:
        return None

    async def record_publish(header: dict[str, object]) -> None:
        published.append(str(header["type"]))

    monkeypatch.setattr(daemon, "_cleanup_runtime_generation", fake_cleanup)
    monkeypatch.setattr(daemon.events, "publish", record_publish)

    await daemon._remove_record_and_stop_reconciliation(entry.port)

    assert published == ["session/removed"]


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

    async with httpx.AsyncClient() as client:
        defaults_resp = await client.get(
            f"http://127.0.0.1:{DAEMON_PORT}/defaults", timeout=5.0
        )
    assert defaults_resp.status_code == 200
    defaults = defaults_resp.json()
    assert defaults["shell_options"]
    assert defaults["shell"] in {option["type"] for option in defaults["shell_options"]}


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
    assert session_data["title"] == "Bash"

    async with httpx.AsyncClient() as client:
        list_resp = await client.get(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions", timeout=5.0
        )
    assert list_resp.status_code == 200
    assert any(item["title"] == "Bash" for item in list_resp.json())

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
