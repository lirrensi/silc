"""Daemon event transport helpers and manager websocket broadcasting."""

# FILE: silc/daemon/events.py
# PURPOSE: Serialize daemon session snapshots and broadcast daemon-level websocket events through the shared binary frame envelope.
# OWNS: Daemon event headers, websocket frame encoding, manager websocket client registration, and session snapshot serialization.
# EXPORTS: DaemonEventBroadcaster, build_manager_event_header, encode_ws_frame, serialize_session_snapshot, serialize_session_snapshots.
# DOCS: agent_chat/plan_daemon_manager_events_2026-04-05.md

from __future__ import annotations

import asyncio
import json
import struct
from typing import Any

from fastapi import WebSocket
from pyee.asyncio import AsyncIOEventEmitter

from silc.daemon.registry import SessionEntry
from silc.daemon.runtime import SessionRuntime


def _iso8601_z(value: object) -> str | None:
    if value is None or not hasattr(value, "isoformat"):
        return None
    return f"{value.isoformat()}Z"


def encode_ws_frame(header: dict[str, object], payload: bytes = b"") -> bytes:
    """Encode a websocket frame using the shared SILC binary envelope."""

    header_bytes = json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return struct.pack(">I", len(header_bytes)) + header_bytes + payload


def serialize_session_snapshot(
    entry: SessionEntry, runtime: SessionRuntime | None = None
) -> dict[str, object]:
    """Return the stable daemon session snapshot shape used by manager clients."""

    session = runtime.session if runtime else None
    status: dict[str, Any] | None = None
    if session is not None:
        try:
            raw_status = session.get_status()
        except Exception:
            raw_status = None
        if isinstance(raw_status, dict):
            status = raw_status

    cwd = entry.cwd
    if status is not None and status.get("cwd") is not None:
        cwd = status["cwd"]

    return {
        "port": entry.port,
        "name": entry.name,
        "title": entry.title,
        "session_id": entry.session_id,
        "shell": entry.shell_type,
        "cwd": cwd,
        "title_updated_at": _iso8601_z(entry.title_updated_at),
        "idle_seconds": status.get("idle_seconds") if status is not None else None,
        "alive": bool(status and status.get("alive")),
        "runtime_state": runtime.state.value if runtime else None,
    }


def serialize_session_snapshots(
    entries: list[SessionEntry], runtimes_by_port: dict[int, SessionRuntime]
) -> list[dict[str, object]]:
    return [
        serialize_session_snapshot(entry, runtimes_by_port.get(entry.port))
        for entry in entries
    ]


def build_manager_event_header(
    event_type: str,
    session: dict[str, object] | None = None,
    **fields: object,
) -> dict[str, object]:
    """Build one manager event header with a required namespaced type."""

    header: dict[str, object] = {"type": event_type}
    if session is not None:
        header["session"] = session
    header.update(fields)
    return header


class DaemonEventBroadcaster:
    """Track manager websocket clients and publish framed daemon events."""

    def __init__(self) -> None:
        self.emitter = AsyncIOEventEmitter()
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def publish(self, header: dict[str, object]) -> None:
        self.emitter.emit("daemon-event", header)
        await self._broadcast(header)

    async def register(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._clients.add(websocket)

    async def unregister(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(websocket)

    async def _broadcast(self, header: dict[str, object]) -> None:
        frame = encode_ws_frame(header)
        async with self._lock:
            clients = tuple(self._clients)

        stale_clients: list[WebSocket] = []
        for websocket in clients:
            try:
                await websocket.send_bytes(frame)
            except Exception:
                stale_clients.append(websocket)

        if not stale_clients:
            return

        async with self._lock:
            for websocket in stale_clients:
                self._clients.discard(websocket)
