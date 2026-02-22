"""MCP tool implementations."""

from __future__ import annotations

import json
import os
import time
from typing import Any

import requests

from silc.daemon import DAEMON_PORT


def _get_error_detail(response: requests.Response | None) -> str:
    """Extract error detail from response."""
    if response is None:
        return "unknown error"
    try:
        data = response.json()
    except ValueError:
        return response.text or response.reason or "unknown error"
    return data.get("detail") or data.get("error") or str(data)


def list_sessions() -> list[dict[str, Any]]:
    """List all active SILC sessions."""
    try:
        resp = requests.get(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions", timeout=(3.0, 10.0)
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException:
        return []


def start_session(
    port: int | None = None,
    shell: str | None = None,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Create a new SILC session."""
    # Default cwd to MCP server's current directory
    if cwd is None:
        cwd = os.getcwd()

    payload: dict[str, Any] = {}
    if port is not None:
        payload["port"] = port
    if shell is not None:
        payload["shell"] = shell
    if cwd is not None:
        payload["cwd"] = cwd

    try:
        resp = requests.post(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions",
            json=payload,
            timeout=(3.0, 30.0),
        )
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        return {"error": str(e), "detail": _get_error_detail(e.response)}
    except requests.RequestException as e:
        return {"error": str(e)}


def close_session(port: int) -> dict[str, Any]:
    """Close a SILC session."""
    try:
        resp = requests.delete(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions/{port}",
            timeout=(3.0, 10.0),
        )
        if resp.status_code == 404:
            return {"error": "Session not found", "status": "not_found"}
        resp.raise_for_status()
        return {"status": "closed"}
    except requests.RequestException as e:
        return {"error": str(e)}


def get_status(port: int) -> dict[str, Any]:
    """Get status of a SILC session."""
    try:
        resp = requests.get(
            f"http://127.0.0.1:{port}/status",
            timeout=(3.0, 10.0),
        )
        if resp.status_code == 410:
            return {"alive": False, "error": "Session has ended"}
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        return {"alive": False, "error": str(e)}


def resize(port: int, rows: int = 30, cols: int = 120) -> dict[str, Any]:
    """Resize a SILC session terminal."""
    try:
        resp = requests.post(
            f"http://127.0.0.1:{port}/resize",
            params={"rows": rows, "cols": cols},
            timeout=(3.0, 10.0),
        )
        if resp.status_code == 410:
            return {"error": "Session has ended", "status": "not_found"}
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        return {"error": str(e)}


def read(port: int, lines: int = 100) -> dict[str, Any]:
    """Read output from a SILC session."""
    try:
        resp = requests.get(
            f"http://127.0.0.1:{port}/out",
            params={"lines": lines},
            timeout=(3.0, 30.0),
        )
        if resp.status_code == 410:
            return {"output": "", "error": "Session has ended"}
        resp.raise_for_status()
        data = resp.json()
        return {
            "output": data.get("output", ""),
            "lines": data.get("lines", 0),
        }
    except requests.RequestException as e:
        return {"output": "", "error": str(e)}


def send(port: int, text: str, timeout_ms: int = 5000) -> dict[str, Any]:
    """Send text to a SILC session and wait for output."""
    try:
        # Send the text
        resp = requests.post(
            f"http://127.0.0.1:{port}/in",
            data=(text + "\n").encode("utf-8"),
            headers={"Content-Type": "text/plain; charset=utf-8"},
            timeout=(3.0, 10.0),
        )
        if resp.status_code == 410:
            return {"output": "", "alive": False, "error": "Session has ended"}
        resp.raise_for_status()

        # If timeout_ms is 0, return immediately (fire-and-forget)
        if timeout_ms == 0:
            return {"output": "", "alive": True, "lines": 0}

        # Wait and read output
        time.sleep(timeout_ms / 1000.0)
        result = read(port, lines=100)
        result["alive"] = True
        return result
    except requests.RequestException as e:
        return {"output": "", "alive": False, "error": str(e)}


# Key name to byte sequence mapping
KEY_SEQUENCES: dict[str, bytes] = {
    "ctrl+c": b"\x03",
    "ctrl+d": b"\x04",
    "ctrl+z": b"\x1a",
    "ctrl+l": b"\x0c",
    "ctrl+r": b"\x12",
    "enter": b"\r",
    "escape": b"\x1b",
    "tab": b"\t",
    "backspace": b"\x7f",
    "delete": b"\x1b[3~",
    "up": b"\x1b[A",
    "down": b"\x1b[B",
    "right": b"\x1b[C",
    "left": b"\x1b[D",
    "home": b"\x1b[H",
    "end": b"\x1b[F",
}


def send_key(port: int, key: str) -> dict[str, Any]:
    """Send a special key to a SILC session."""
    key_lower = key.lower()
    if key_lower not in KEY_SEQUENCES:
        return {
            "output": "",
            "alive": True,
            "error": f"Unknown key: {key}. Supported: {', '.join(KEY_SEQUENCES.keys())}",
        }

    sequence = KEY_SEQUENCES[key_lower]

    try:
        resp = requests.post(
            f"http://127.0.0.1:{port}/in",
            data=sequence,
            headers={"Content-Type": "application/octet-stream"},
            timeout=(3.0, 10.0),
        )
        if resp.status_code == 410:
            return {"output": "", "alive": False, "error": "Session has ended"}
        resp.raise_for_status()

        # Brief delay then read output
        time.sleep(0.1)
        result = read(port, lines=50)
        result["alive"] = True
        return result
    except requests.RequestException as e:
        return {"output": "", "alive": False, "error": str(e)}


def run(port: int, command: str, timeout_ms: int = 60000) -> dict[str, Any]:
    """Execute a command with exit code capture (native shell only)."""
    try:
        command_timeout = timeout_ms // 1000
        resp = requests.post(
            f"http://127.0.0.1:{port}/run",
            json={"command": command, "timeout": command_timeout},
            timeout=(3.0, command_timeout + 10.0),
        )
        if resp.status_code == 410:
            return {
                "output": "",
                "exit_code": -1,
                "status": "error",
                "error": "Session has ended",
            }
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        return {"output": "", "exit_code": -1, "status": "error", "error": str(e)}


__all__ = [
    "list_sessions",
    "start_session",
    "close_session",
    "get_status",
    "resize",
    "read",
    "send",
    "send_key",
    "run",
    "KEY_SEQUENCES",
]
