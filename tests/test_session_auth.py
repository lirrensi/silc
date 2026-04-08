"""Smoke test for session token enforcement on the session API."""

# FILE: tests/test_session_auth.py
# PURPOSE: Cover session auth and targeted websocket cleanup behavior for session and daemon APIs.
# OWNS: Token enforcement smoke tests plus focused websocket regression tests.
# EXPORTS: pytest test cases only.
# DOCS: agent_chat/plan_daemon_websocket_cleanup_2026-04-08.md

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import json
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from types import SimpleNamespace

import pytest
import requests
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import silc.daemon.manager as manager_module
import tests.test_daemon as test_daemon_module
from silc.api.server import create_app
from silc.core.raw_buffer import RawByteBuffer
from silc.daemon import kill_daemon
from silc.daemon.manager import DAEMON_PORT, SilcDaemon
from silc.daemon.runtime import SessionState
from tests.test_daemon import _shutdown_daemon, wait_for_daemon_start


def _find_remote_host() -> str | None:
    """Return a non-loopback IP for this host or None if unavailable."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
    except OSError:
        return None
    if ip.startswith("127.") or ip == "0.0.0.0":
        return None
    return ip


def _pick_free_daemon_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _pick_free_session_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


CUSTOM_DAEMON_PORT = _pick_free_daemon_port()
manager_module.DAEMON_PORT = CUSTOM_DAEMON_PORT
test_daemon_module.DAEMON_PORT = CUSTOM_DAEMON_PORT
DAEMON_PORT = CUSTOM_DAEMON_PORT


class _CorsSession:
    session_id = "cors-test"
    api_token = None
    tui_active = False

    def get_status(self) -> dict:
        return {"alive": True, "tui_active": self.tui_active}

    def resize(self, rows: int, cols: int) -> None:
        self.rows = rows
        self.cols = cols


class _WsSession:
    def __init__(self) -> None:
        self.session_id = "ws-test"
        self.api_token = None
        self.title = ""
        self.title_updated_at = dt.datetime.utcnow()
        self.cwd = None
        self.tui_active = False
        self.buffer = RawByteBuffer()
        self._output_event = asyncio.Event()
        self._title_listeners = []
        self._cwd_listeners = []
        self._output_listeners = []

    def get_status(self) -> dict:
        return {"alive": True, "tui_active": self.tui_active}

    def add_title_listener(self, listener):
        self._title_listeners.append(listener)

    def remove_title_listener(self, listener):
        with contextlib.suppress(ValueError):
            self._title_listeners.remove(listener)

    def add_cwd_listener(self, listener):
        self._cwd_listeners.append(listener)

    def remove_cwd_listener(self, listener):
        with contextlib.suppress(ValueError):
            self._cwd_listeners.remove(listener)

    def add_output_listener(self, listener):
        self._output_listeners.append(listener)

    def remove_output_listener(self, listener):
        with contextlib.suppress(ValueError):
            self._output_listeners.remove(listener)

    def push_output(self, data: bytes) -> None:
        self.buffer.append(data)
        self._output_event.set()
        for listener in list(self._output_listeners):
            listener(self, data)

    def get_snapshot_bytes(self) -> bytes:
        return self.buffer.get_bytes()


class _BlockingOutputEvent:
    def __init__(self) -> None:
        import threading

        self.started = threading.Event()
        self.cancelled = threading.Event()

    async def wait(self) -> None:
        self.started.set()
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            self.cancelled.set()
            raise

    def clear(self) -> None:
        return None

    def set(self) -> None:
        return None


class _DaemonWsSession(_WsSession):
    def __init__(self, port: int, name: str, session_id: str) -> None:
        super().__init__()
        self.port = port
        self.name = name
        self.session_id = session_id
        self.closed = False
        self.write_input_calls: list[str] = []

    async def close(self) -> None:
        self.closed = True

    async def write_input(self, text: str) -> None:
        self.write_input_calls.append(text)


class _TrackedWebSocket:
    def __init__(self) -> None:
        self.closed = False
        self.close_calls: list[tuple[int, str]] = []

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.closed = True
        self.close_calls.append((code, reason or ""))


def _register_daemon_ws_session(
    daemon: SilcDaemon,
    *,
    port: int,
    name: str = "daemon-ws",
    session_id: str = "sess-daemon-ws",
) -> tuple[object, _DaemonWsSession]:
    entry = daemon.registry.add(port, name, session_id, "bash", title=name)
    session = _DaemonWsSession(port, name, session_id)
    runtime = SimpleNamespace(
        generation=1,
        session=session,
        state=SessionState.RUNNING,
        server=None,
        server_task=None,
        socket=None,
    )
    daemon.runtime_by_port[port] = runtime
    daemon.sessions[port] = session
    return entry, session


def _run_with_timeout(callback, *, timeout: float = 2.0):
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(callback)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError as exc:
            raise AssertionError(
                f"operation timed out after {timeout} seconds"
            ) from exc


@pytest.mark.asyncio
async def test_session_requires_token_for_remote_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Remote clients must provide the session token, local CLI calls do not."""
    kill_daemon(port=DAEMON_PORT)
    _shutdown_daemon()
    await asyncio.sleep(1)

    daemon = SilcDaemon()

    class _AuthSession:
        def __init__(self, port: int, name: str, api_token: str | None) -> None:
            self.port = port
            self.name = name
            self.session_id = "auth-test"
            self.api_token = api_token
            self.title = "auth-test"
            self.title_updated_at = dt.datetime.utcnow()
            self.cwd = None
            self.shell_info = SimpleNamespace(type="bash")
            self.tui_active = False
            self.buffer = RawByteBuffer()
            self._output_event = asyncio.Event()

        def get_status(self) -> dict:
            return {"alive": True, "tui_active": self.tui_active}

        def get_snapshot_bytes(self) -> bytes:
            return b""

        async def close(self) -> None:
            return None

    async def fake_construct(*args, **kwargs):
        port = int(args[0])
        name = str(args[1])
        api_token = args[3] if len(args) > 3 else kwargs.get("api_token")
        return _AuthSession(port, name, api_token)

    async def fake_start(*args, **kwargs):
        return None

    monkeypatch.setattr(daemon, "_construct_session", fake_construct)
    monkeypatch.setattr(daemon, "_start_session_with_timeout", fake_start)
    monkeypatch.setattr(daemon, "_validate_session_launch", lambda *a, **k: None)
    task = asyncio.create_task(daemon.start())
    await wait_for_daemon_start(daemon, timeout=10)

    try:
        token = "test-token-123"

        session_port = _pick_free_session_port()
        entry = daemon.registry.add(
            session_port,
            "auth-test",
            "auth-test",
            "bash",
            is_global=True,
            title="auth-test",
        )
        runtime = daemon._get_or_create_runtime(
            entry, api_token=token, title="auth-test"
        )
        await daemon._realize_runtime(entry, runtime, preserve_session_id="auth-test")

        time.sleep(0.5)

        remote_host = _find_remote_host()
        if not remote_host:
            pytest.skip("No non-loopback address available to simulate remote access")

        remote_url = f"http://{remote_host}:{session_port}/status"

        try:
            remote_resp = requests.get(remote_url, timeout=5)
        except requests.RequestException as exc:
            pytest.skip(f"Cannot reach session via remote interface ({exc})")

        assert remote_resp.status_code == 401

        wrong_header = {"Authorization": "Bearer wrong-token"}
        wrong_resp = requests.get(remote_url, headers=wrong_header, timeout=5)
        assert wrong_resp.status_code == 403

        good_header = {"Authorization": f"Bearer {token}"}
        good_resp = requests.get(remote_url, headers=good_header, timeout=5)
        assert good_resp.status_code == 200

        local_url = f"http://127.0.0.1:{session_port}/status"
        local_resp = requests.get(local_url, timeout=5)
        assert local_resp.status_code == 200

        token_resp = requests.get(f"http://127.0.0.1:{session_port}/token", timeout=5)
        assert token_resp.status_code == 200
        assert token_resp.json()["token"] == token
    finally:
        daemon._shutdown_event.set()
        try:
            await asyncio.wait_for(task, timeout=5)
        except asyncio.TimeoutError:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        _shutdown_daemon()
        monkeypatch.undo()


def test_session_api_allows_browser_resize_cors() -> None:
    session = _CorsSession()
    client = TestClient(create_app(session))

    resp = client.post(
        "/resize?rows=51&cols=146",
        headers={"Origin": "http://127.0.0.1:19999"},
    )

    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") is not None


def test_session_websocket_pushes_output_without_polling() -> None:
    session = _WsSession()
    client = TestClient(create_app(session))

    with client.websocket_connect("/ws") as websocket:
        session.push_output(b"\x1b[31mRED\x1b[0m")

        frame = websocket.receive_bytes()
        header_length = int.from_bytes(frame[:4], "big")
        header = json.loads(frame[4 : 4 + header_length].decode("utf-8"))
        payload = frame[4 + header_length :]

        assert header["type"] == "output"
        assert payload == b"\x1b[31mRED\x1b[0m"


def test_session_snapshot_endpoint_returns_raw_bytes() -> None:
    session = _WsSession()
    client = TestClient(create_app(session))

    session.push_output(b"\x1b[31mRED\x1b[0m")

    resp = client.get("/snapshot")

    assert resp.status_code == 200
    assert resp.content == b"\x1b[31mRED\x1b[0m"


def test_session_status_exposes_tui_active_flag() -> None:
    session = _WsSession()
    client = TestClient(create_app(session))

    resp = client.get("/status")
    assert resp.status_code == 200
    assert resp.json()["tui_active"] is False

    session.tui_active = True
    resp = client.get("/status")
    assert resp.status_code == 200
    assert resp.json()["tui_active"] is True


def test_daemon_websocket_disconnect_does_not_hang_cleanup() -> None:
    daemon = SilcDaemon(enable_hard_exit=False)
    entry, session = _register_daemon_ws_session(daemon, port=_pick_free_session_port())

    def connect_receive_and_disconnect() -> tuple[dict[str, object], bytes]:
        with TestClient(daemon._create_daemon_api()) as client:
            with client.websocket_connect(f"/sessions/{entry.port}/ws") as websocket:
                session.push_output(b"daemon-output")
                frame = websocket.receive_bytes()
                return manager_module.decode_ws_frame(frame)

    header, payload = _run_with_timeout(connect_receive_and_disconnect)

    assert header["type"] == "output"
    assert payload == b"daemon-output"
    assert daemon._active_session_websockets.get(entry.port) is None
    assert session.tui_active is False


def test_daemon_websocket_replacement_closes_previous_connection() -> None:
    daemon = SilcDaemon(enable_hard_exit=False)
    entry, session = _register_daemon_ws_session(
        daemon,
        port=_pick_free_session_port(),
        name="replace-ws",
        session_id="sess-replace",
    )

    def replace_connection() -> tuple[bool, bool]:
        with TestClient(daemon._create_daemon_api()) as client:
            with client.websocket_connect(f"/sessions/{entry.port}/ws") as first:
                assert session.tui_active is True
                with client.websocket_connect(f"/sessions/{entry.port}/ws") as second:
                    with pytest.raises(WebSocketDisconnect):
                        first.receive_bytes()
                    second.send_bytes(
                        manager_module.encode_ws_frame(
                            {"type": "input", "nonewline": True}, b"pwd"
                        )
                    )
                    assert session.write_input_calls == ["pwd"]
                    return (
                        session.tui_active,
                        daemon._active_session_websockets.get(entry.port) is not None,
                    )

    tui_active_during_replacement, has_active_socket = _run_with_timeout(
        replace_connection
    )

    assert tui_active_during_replacement is True
    assert has_active_socket is True
    assert daemon._active_session_websockets.get(entry.port) is None
    assert session.tui_active is False


def test_daemon_websocket_disconnect_cancels_blocked_sender_task() -> None:
    daemon = SilcDaemon(enable_hard_exit=False)
    entry, session = _register_daemon_ws_session(
        daemon,
        port=_pick_free_session_port(),
        name="blocked-sender",
        session_id="sess-blocked-sender",
    )
    blocking_event = _BlockingOutputEvent()
    session._output_event = blocking_event

    def connect_and_disconnect() -> None:
        with TestClient(daemon._create_daemon_api()) as client:
            with client.websocket_connect(f"/sessions/{entry.port}/ws"):
                assert session.tui_active is True

    _run_with_timeout(connect_and_disconnect)

    assert blocking_event.started.wait(timeout=1.0)
    assert blocking_event.cancelled.wait(timeout=1.0)
    assert daemon._active_session_websockets.get(entry.port) is None
    assert session.tui_active is False


def test_daemon_websocket_queues_title_and_cwd_updates() -> None:
    daemon = SilcDaemon(enable_hard_exit=False)
    entry, session = _register_daemon_ws_session(
        daemon,
        port=_pick_free_session_port(),
        name="listener-queue",
        session_id="sess-listener-queue",
    )

    def receive_listener_updates() -> list[dict[str, object]]:
        with TestClient(daemon._create_daemon_api()) as client:
            with client.websocket_connect(f"/sessions/{entry.port}/ws") as websocket:
                session.title = "Queued title"
                session.title_updated_at = dt.datetime.utcnow()
                for listener in list(session._title_listeners):
                    listener(session)

                session.cwd = "/tmp/queued"
                for listener in list(session._cwd_listeners):
                    listener(session)

                title_frame = manager_module.decode_ws_frame(websocket.receive_bytes())[
                    0
                ]
                cwd_frame = manager_module.decode_ws_frame(websocket.receive_bytes())[0]
                return [title_frame, cwd_frame]

    frames = _run_with_timeout(receive_listener_updates)

    assert frames[0]["type"] == "title"
    assert frames[0]["title"] == "Queued title"
    assert str(frames[0]["title_updated_at"]).endswith("Z")
    assert frames[1] == {"type": "cwd", "cwd": "/tmp/queued"}
    assert daemon._active_session_websockets.get(entry.port) is None
    assert session.tui_active is False


@pytest.mark.asyncio
async def test_cleanup_runtime_generation_closes_tracked_websocket() -> None:
    daemon = SilcDaemon(enable_hard_exit=False)
    entry, session = _register_daemon_ws_session(
        daemon,
        port=_pick_free_session_port(),
        name="cleanup-ws",
        session_id="sess-cleanup-ws",
    )
    tracked_websocket = _TrackedWebSocket()
    daemon._active_session_websockets[entry.port] = tracked_websocket  # type: ignore[assignment]
    daemon._active_session_websocket_locks[entry.port] = asyncio.Lock()
    session.tui_active = True

    async def _noop_kill_processes(*args, **kwargs) -> None:
        return None

    daemon._kill_processes_on_port = _noop_kill_processes  # type: ignore[method-assign]
    daemon._close_session_socket = lambda *args, **kwargs: None  # type: ignore[method-assign]

    runtime = daemon.runtime_by_port[entry.port]
    await daemon._cleanup_runtime_generation(
        entry.port, runtime.generation, remove_record=False
    )

    assert tracked_websocket.closed is True
    assert tracked_websocket.close_calls == [(1012, "Session runtime stopped")]
    assert daemon._active_session_websockets.get(entry.port) is None
    assert entry.port not in daemon._active_session_websocket_locks
    assert session.tui_active is False
