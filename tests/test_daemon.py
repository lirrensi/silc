# FILE: tests/test_daemon.py
# PURPOSE: Verify daemon lifecycle, registry behavior, session persistence, and websocket event emission.
# OWNS: Daemon API coverage, session registry checks, and session event integration tests.
# DOCS: docs/arch_daemon.md, docs/product.md, agent_chat/plan_shutdown_preserve_records_2026-04-05.md

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
import uvicorn
from fastapi.testclient import TestClient

from silc.daemon.manager import DAEMON_PORT, SilcDaemon
from silc.daemon.pidfile import read_pidfile, remove_pidfile, write_pidfile
from silc.daemon.registry import SessionRegistry
from silc.daemon.runtime import SessionState
from silc.utils import persistence


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

    def get_snapshot_bytes(self) -> bytes:
        return f"snapshot:{self.session_id}".encode("utf-8")

    async def start(self) -> None:
        return None

    async def close(self) -> None:
        self.closed = True

    async def force_kill(self) -> None:
        self.killed = True


class _RouteTestSession(_EventTestSession):
    def __init__(self, port: int, name: str, session_id: str) -> None:
        super().__init__(port, name, session_id)
        self.output_calls: list[tuple[int, bool]] = []
        self.input_calls: list[str] = []
        self.run_calls: list[tuple[str, int]] = []
        self.signal_calls: list[str] = []
        self.resize_calls: list[tuple[int, int]] = []

    def get_status(self) -> dict:
        return {
            "session_id": self.session_id,
            "port": self.port,
            "name": self.name,
            "title": self.title,
            "cwd": self.cwd,
            "title_updated_at": self.title_updated_at.isoformat() + "Z",
            "alive": True,
            "tui_active": False,
            "idle_seconds": 3,
            "waiting_for_input": False,
            "last_line": "ready>",
            "run_locked": False,
        }

    def get_output(self, lines: int = 100, raw: bool = False) -> str:
        self.output_calls.append((lines, raw))
        data = ["line-1", "line-2", "line-3"]
        if lines > 0:
            data = data[-lines:]
        if raw:
            return "\n".join(data)
        return "\n".join(data)

    def get_snapshot_bytes(self) -> bytes:
        return b"snapshot-bytes"

    async def write_input(self, text: str) -> None:
        self.input_calls.append(text)

    async def run_command(self, command: str, timeout: int) -> dict:
        self.run_calls.append((command, timeout))
        return {"output": f"ran:{command}", "exit_code": 0, "status": "completed"}

    async def interrupt(self) -> None:
        self.signal_calls.append("interrupt")

    async def send_sigterm(self) -> None:
        self.signal_calls.append("sigterm")

    async def send_sigkill(self) -> None:
        self.signal_calls.append("sigkill")

    async def clear_screen(self) -> None:
        self.signal_calls.append("clear")

    def resize(self, rows: int, cols: int) -> None:
        self.resize_calls.append((rows, cols))


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
    """Best-effort full cleanup for the daemon test module."""
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

    try:
        from silc.daemon.pidfile import kill_daemon as kill_daemon_process

        kill_daemon_process(port=DAEMON_PORT, force=True, timeout=2.0)
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


def test_list_sessions_marks_dormant_records() -> None:
    daemon = SilcDaemon(enable_hard_exit=False)
    daemon.registry.add(20021, "sleeping", "sess-dormant", "bash")

    client = TestClient(daemon._create_daemon_api())
    resp = client.get("/sessions")

    assert resp.status_code == 200
    session = resp.json()[0]
    assert session["dormant"] is True
    assert session["runtime_state"] == "dormant"


def test_resolve_session_target_prefers_port_then_name() -> None:
    daemon = SilcDaemon(enable_hard_exit=False)
    port_entry = daemon.registry.add(20022, "alpha", "sess-alpha", "bash")
    name_entry = daemon.registry.add(20023, "beta", "sess-beta", "bash")

    resolved_port, _ = daemon._resolve_session_target("20022", operation="resolve")
    resolved_name, _ = daemon._resolve_session_target("beta", operation="resolve")

    assert resolved_port.port == port_entry.port
    assert resolved_name.port == name_entry.port


def test_daemon_session_routes_use_shared_key_resolution() -> None:
    daemon = SilcDaemon(enable_hard_exit=False)
    entry = daemon.registry.add(20024, "alpha", "sess-route", "bash")
    session = _RouteTestSession(entry.port, entry.name, entry.session_id)
    daemon.runtime_by_port[entry.port] = SimpleNamespace(
        session=session, state=SessionState.RUNNING
    )

    client = TestClient(daemon._create_daemon_api())

    status = client.get("/sessions/alpha/status")
    assert status.status_code == 200
    assert status.json()["name"] == "alpha"

    status_by_port = client.get("/sessions/20024/status")
    assert status_by_port.status_code == 200
    assert status_by_port.json()["port"] == 20024

    out = client.get("/sessions/alpha/out?lines=2")
    assert out.status_code == 200
    assert out.json()["output"] == "line-2\nline-3"

    raw = client.get("/sessions/20024/raw?lines=1")
    assert raw.status_code == 200
    assert raw.json()["output"] == "line-3"

    run = client.post("/sessions/alpha/run", content="echo hi")
    assert run.status_code == 200
    assert run.json()["output"] == "ran:echo hi"

    interrupt = client.post("/sessions/alpha/interrupt")
    assert interrupt.status_code == 200
    resize = client.post("/sessions/20024/resize?rows=24&cols=80")
    assert resize.status_code == 200

    assert session.output_calls == [(2, False), (1, True)]
    assert session.run_calls == [("echo hi", 60)]
    assert session.signal_calls == ["interrupt"]
    assert session.resize_calls == [(24, 80)]


def test_daemon_session_snapshot_and_logs_fallback_without_live_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    daemon = SilcDaemon(enable_hard_exit=False)
    entry = daemon.registry.add(20025, "sleepy", "sess-snapshot", "bash")

    monkeypatch.setattr(
        "silc.daemon.manager.read_session_snapshot",
        lambda session_id: b"frozen-bytes",
    )
    monkeypatch.setattr(
        "silc.daemon.manager.read_session_log",
        lambda port, tail_lines=None: "line-a\nline-b",
    )

    client = TestClient(daemon._create_daemon_api())

    status = client.get("/sessions/sleepy/status")
    assert status.status_code == 200
    assert status.json()["dormant"] is True

    snapshot = client.get("/sessions/20025/snapshot")
    assert snapshot.status_code == 200
    assert snapshot.content == b"frozen-bytes"

    logs = client.get("/sessions/sleepy/logs?tail=10")
    assert logs.status_code == 200
    assert logs.json()["logs"] == "line-a\nline-b"


def test_create_session_rejects_numeric_only_name() -> None:
    daemon = SilcDaemon(enable_hard_exit=False)
    client = TestClient(daemon._create_daemon_api())

    resp = client.post("/sessions", json={"name": "123", "shell": "bash"})

    assert resp.status_code == 400
    assert "Invalid name format" in str(resp.json()["detail"])


def test_settings_routes_merge_and_persist(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(persistence, "SETTINGS_FILE", tmp_path / "settings.json")

    daemon = SilcDaemon(enable_hard_exit=False)
    client = TestClient(daemon._create_daemon_api())

    get_resp = client.get("/settings")
    assert get_resp.status_code == 200
    assert get_resp.json()["ui"]["managerTheme"] == "amoled"
    assert get_resp.json()["ui"]["themePreference"] == "dark"

    post_resp = client.post(
        "/settings",
        json={
            "ui": {"managerTheme": "vercel"},
            "terminal": {"themePreset": "tokyo-night", "fontSize": 18},
        },
    )
    assert post_resp.status_code == 200
    payload = post_resp.json()
    assert payload["ui"]["managerTheme"] == "vercel"
    assert payload["ui"]["themePreference"] == "light"
    assert payload["terminal"]["themePreset"] == "tokyo-night"
    assert payload["terminal"]["theme"] == "dark"
    assert payload["terminal"]["fontSize"] == 18
    assert payload["terminal"]["cursorBlink"] is True

    persisted = persistence.read_settings_json()
    assert persisted["ui"]["managerTheme"] == "vercel"
    assert persisted["terminal"]["themePreset"] == "tokyo-night"
    assert persisted["terminal"]["fontSize"] == 18

    daemon_reload = SilcDaemon(enable_hard_exit=False)
    reload_client = TestClient(daemon_reload._create_daemon_api())
    reload_resp = reload_client.get("/settings")
    assert reload_resp.status_code == 200
    assert reload_resp.json()["ui"]["managerTheme"] == "vercel"


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

    await asyncio.sleep(0)

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


@pytest.mark.asyncio
async def test_cleanup_runtime_generation_ignores_cancelled_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    daemon = SilcDaemon(enable_hard_exit=False)
    entry = daemon.registry.add(20021, "cleanup-test", "sess-cleanup", "bash")
    session = _EventTestSession(entry.port, entry.name, entry.session_id)
    task = asyncio.create_task(asyncio.sleep(10))
    runtime = SimpleNamespace(
        generation=1,
        session=session,
        server=None,
        socket=None,
        server_task=task,
        state=SessionState.RUNNING,
    )
    daemon.runtime_by_port[entry.port] = runtime
    daemon._session_tasks[entry.port] = task

    monkeypatch.setattr(
        daemon, "_kill_processes_on_port", lambda *args, **kwargs: asyncio.sleep(0)
    )
    monkeypatch.setattr(daemon, "_close_session_socket", lambda *args, **kwargs: None)

    await daemon._cleanup_runtime_generation(
        entry.port, runtime.generation, remove_record=False
    )

    assert task.cancelled()


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
        print("[test_daemon_creates_session] posting create-session request")
        resp = await asyncio.wait_for(
            client.post(
                f"http://127.0.0.1:{DAEMON_PORT}/sessions",
                json={"name": "test-create-session"},
                timeout=30.0,
            ),
            timeout=60.0,
        )
        print("[test_daemon_creates_session] create-session response received")

    assert resp.status_code == 200
    session_data = resp.json()
    assert "port" in session_data
    assert "session_id" in session_data
    assert "shell" in session_data
    assert session_data["name"] == "test-create-session"
    assert session_data["title"]

    async with httpx.AsyncClient() as client:
        list_resp = await client.get(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions", timeout=5.0
        )
    assert list_resp.status_code == 200
    assert any(item["name"] == "test-create-session" for item in list_resp.json())

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
        print(
            "[test_daemon_creates_session_with_requested_port] posting create-session request"
        )
        resp = await asyncio.wait_for(
            client.post(
                f"http://127.0.0.1:{DAEMON_PORT}/sessions",
                json={"port": requested_port, "name": "test-port-session"},
                timeout=30.0,
            ),
            timeout=60.0,
        )
        print(
            "[test_daemon_creates_session_with_requested_port] create-session response received"
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
    await asyncio.sleep(3.0)

    # Verify session record is removed from the daemon registry/API
    async with httpx.AsyncClient() as client:
        list_resp = await client.get(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions", timeout=5.0
        )
    assert list_resp.status_code == 200
    assert port not in {item["port"] for item in list_resp.json()}


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

    # Verify session record is removed from the daemon registry/API
    async with httpx.AsyncClient() as client:
        list_resp = await client.get(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions", timeout=5.0
        )
    assert list_resp.status_code == 200
    assert port not in {item["port"] for item in list_resp.json()}


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


@pytest.mark.asyncio
async def test_shutdown_preserves_records_and_start_reload(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Shutdown should preserve records, and startup should reload them."""
    from silc.utils import persistence

    monkeypatch.setattr(persistence, "SESSIONS_FILE", tmp_path / "sessions.json")
    monkeypatch.setattr(persistence, "SNAPSHOTS_DIR", tmp_path / "snapshots")
    persistence.SNAPSHOTS_DIR = tmp_path / "snapshots"

    daemon = SilcDaemon(enable_hard_exit=False)
    entry = daemon.registry.add(20101, "preserve-me", "sess-preserve", "bash")
    daemon._persist_desired_sessions()

    runtime = SimpleNamespace(
        session=_EventTestSession(entry.port, entry.name, entry.session_id),
        generation=0,
        state=SessionState.RUNNING,
        server=None,
        server_task=None,
        socket=None,
        name=entry.name,
        shell_type=entry.shell_type,
        cwd=entry.cwd,
        is_global=entry.is_global,
    )
    daemon.runtime_by_port[entry.port] = runtime
    daemon.sessions[entry.port] = runtime.session

    resp = await _post_daemon_json(daemon, "/shutdown", {})

    assert resp.status_code == 200
    assert resp.json()["status"] == "shutdown"
    assert (
        persistence.read_session_snapshot(entry.session_id) == b"snapshot:sess-preserve"
    )
    assert daemon.registry.get(entry.port) is not None
    assert entry.port not in daemon.sessions
    assert entry.port not in daemon.runtime_by_port
    assert [item["port"] for item in persistence.read_sessions_json()] == [20101]

    restarted = SilcDaemon(enable_hard_exit=False)
    result = await restarted._load_persisted_desired_records()

    assert result["loaded"] == [{"port": 20101, "name": "preserve-me"}]
    assert restarted.registry.get(20101) is not None


@pytest.mark.asyncio
async def test_startup_loads_dormant_records_without_materializing_and_gc_orphans(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from silc.utils import persistence

    monkeypatch.setattr(persistence, "SESSIONS_FILE", tmp_path / "sessions.json")
    monkeypatch.setattr(persistence, "SNAPSHOTS_DIR", tmp_path / "snapshots")
    persistence.SNAPSHOTS_DIR = tmp_path / "snapshots"

    persistence.write_sessions_json(
        [
            {
                "port": 20111,
                "name": "sleeping",
                "title": "Bash",
                "session_id": "sess-sleep",
                "shell": "bash",
                "cwd": None,
                "is_global": False,
                "created_at": "2026-04-06T00:00:00Z",
                "title_updated_at": "2026-04-06T00:00:00Z",
            }
        ]
    )
    persistence.write_session_snapshot("sess-sleep", b"keep-me")
    persistence.write_session_snapshot("sess-orphan", b"drop-me")

    daemon = SilcDaemon(enable_hard_exit=False)

    async def fake_serve(self, *args, **kwargs):
        return None

    monkeypatch.setattr(uvicorn.Server, "serve", fake_serve)
    monkeypatch.setattr(
        "silc.daemon.manager.write_pidfile", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        "silc.daemon.manager.remove_pidfile", lambda *args, **kwargs: None
    )

    await daemon.start()

    assert daemon.registry.get(20111) is not None
    assert 20111 not in daemon.runtime_by_port
    assert persistence.read_session_snapshot("sess-sleep") == b"keep-me"
    assert persistence.read_session_snapshot("sess-orphan") == b""


@pytest.mark.asyncio
async def test_resurrect_materializes_dormant_sessions(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from silc.utils import persistence

    monkeypatch.setattr(persistence, "SESSIONS_FILE", tmp_path / "sessions.json")
    monkeypatch.setattr(persistence, "SNAPSHOTS_DIR", tmp_path / "snapshots")
    persistence.SNAPSHOTS_DIR = tmp_path / "snapshots"

    persistence.write_sessions_json(
        [
            {
                "port": 20121,
                "name": "wake-me",
                "title": "Bash",
                "session_id": "sess-wake",
                "shell": "bash",
                "cwd": None,
                "is_global": False,
                "created_at": "2026-04-06T00:00:00Z",
                "title_updated_at": "2026-04-06T00:00:00Z",
            }
        ]
    )

    daemon = SilcDaemon(enable_hard_exit=False)

    async def fake_realize(entry, runtime, preserve_session_id=None):
        runtime.session = _EventTestSession(
            entry.port, entry.name, session_id=preserve_session_id or entry.session_id
        )
        runtime.session.title = entry.title
        runtime.state = SessionState.RUNNING
        daemon.runtime_by_port[entry.port] = runtime
        daemon.sessions[entry.port] = runtime.session
        daemon.servers[entry.port] = SimpleNamespace(should_exit=False)
        return runtime

    monkeypatch.setattr(daemon, "_realize_runtime", fake_realize)

    resp = await _post_daemon_json(daemon, "/resurrect", {})

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["restored"] == [
        {
            "port": 20121,
            "name": "wake-me",
            "title": "Bash",
            "session_id": "sess-wake",
            "shell": "bash",
        }
    ]
    assert daemon.runtime_by_port[20121].state == SessionState.RUNNING
    assert daemon.registry.get(20121) is not None


@pytest.mark.asyncio
async def test_killall_removes_records(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Killall should delete desired records without shutting down the daemon."""
    from silc.utils import persistence

    monkeypatch.setattr(persistence, "SESSIONS_FILE", tmp_path / "sessions.json")
    monkeypatch.setattr(persistence, "SNAPSHOTS_DIR", tmp_path / "snapshots")
    persistence.SNAPSHOTS_DIR = tmp_path / "snapshots"

    daemon = SilcDaemon(enable_hard_exit=False)
    entry = daemon.registry.add(20102, "destroy-me", "sess-destroy", "bash")
    daemon._persist_desired_sessions()

    runtime = SimpleNamespace(
        session=_EventTestSession(entry.port, entry.name, entry.session_id),
        generation=0,
        state=SessionState.RUNNING,
        server=None,
        server_task=None,
        socket=None,
        name=entry.name,
        shell_type=entry.shell_type,
        cwd=entry.cwd,
        is_global=entry.is_global,
    )
    daemon.runtime_by_port[entry.port] = runtime
    daemon.sessions[entry.port] = runtime.session
    persistence.write_session_snapshot(entry.session_id, b"snapshot:sess-destroy")

    resp = await _post_daemon_json(daemon, "/killall", {})

    assert resp.status_code == 200
    assert resp.json()["status"] == "cleared"
    assert daemon.registry.get(entry.port) is None
    assert entry.port not in daemon.runtime_by_port
    assert persistence.read_sessions_json() == []
    assert persistence.read_session_snapshot(entry.session_id) == b""
    assert not daemon._shutdown_event.is_set()
