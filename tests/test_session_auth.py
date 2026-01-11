"""Smoke test for session token enforcement on the session API."""

from __future__ import annotations

import asyncio
import contextlib
import socket
import time

import pytest
import requests

import silc.daemon.manager as manager_module
import tests.test_daemon as test_daemon_module
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
