"""Smoke test for session token enforcement on the session API."""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import json
import socket
import time

import pytest
import requests
from fastapi.testclient import TestClient

import silc.daemon.manager as manager_module
import tests.test_daemon as test_daemon_module
from silc.api.server import create_app
from silc.core.raw_buffer import RawByteBuffer
from silc.daemon import kill_daemon
from silc.daemon.manager import DAEMON_PORT, SilcDaemon
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


@pytest.mark.asyncio
async def test_session_requires_token_for_remote_requests() -> None:
    """Remote clients must provide the session token, local CLI calls do not."""
    kill_daemon(port=DAEMON_PORT)
    _shutdown_daemon()
    await asyncio.sleep(1)

    daemon = SilcDaemon()
    task = asyncio.create_task(daemon.start())
    await wait_for_daemon_start(daemon, timeout=10)

    try:
        token = "test-token-123"

        resp = requests.post(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions",
            json={"is_global": True, "token": token},
            timeout=15,
        )
        assert resp.status_code == 200
        session_port = resp.json()["port"]

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
    finally:
        daemon._shutdown_event.set()
        try:
            await asyncio.wait_for(task, timeout=5)
        except asyncio.TimeoutError:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        _shutdown_daemon()


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
