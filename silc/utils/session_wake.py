"""Helpers for waking dormant SILC sessions before client interaction."""

from __future__ import annotations

import time
from typing import Any

import requests

DAEMON_BASE_URL = "http://127.0.0.1:19999"


def get_daemon_session(port: int, *, timeout: float = 2.0) -> dict[str, Any] | None:
    """Return the daemon registry entry for a port, if present."""

    resp = requests.get(f"{DAEMON_BASE_URL}/sessions", timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, list):
        return None

    for entry in payload:
        if isinstance(entry, dict) and entry.get("port") == port:
            return entry
    return None


def wait_for_session_ready(
    port: int,
    *,
    timeout: float = 15.0,
    poll_interval: float = 0.25,
) -> dict[str, Any] | None:
    """Wait for a session port to come back and report alive."""

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = requests.get(f"http://127.0.0.1:{port}/status", timeout=2.0)
            if resp.ok:
                payload = resp.json()
                if isinstance(payload, dict) and payload.get("alive") is True:
                    return payload
        except requests.RequestException:
            pass
        except ValueError:
            pass

        time.sleep(poll_interval)

    return None


def wake_session_if_dormant(
    port: int,
    *,
    timeout: float = 15.0,
) -> dict[str, Any] | None:
    """Wake a dormant session synchronously before interaction.

    Returns the current daemon session record, or the live session status after
    waking. Non-dormant sessions are left untouched.
    """

    session = get_daemon_session(port)
    if session is None:
        return None

    if session.get("dormant"):
        resp = requests.post(f"{DAEMON_BASE_URL}/sessions/{port}/restart", timeout=30)
        resp.raise_for_status()

        ready = wait_for_session_ready(port, timeout=timeout)
        if ready is not None:
            return ready

    return session
