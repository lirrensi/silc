"""Session-port adapter smoke tests."""

# FILE: tests/test_session_adapter.py
# PURPOSE: Verify the loopback session-port adapter rewrites requests into daemon session routes.
# OWNS: Adapter request-line rewriting, daemon header forwarding, and adapter shutdown behavior.
# EXPORTS: pytest test cases only.
# DOCS: agent_chat/plan_daemon_session_adapters_2026-04-08.md

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import json
import socket

import httpx
import pytest
import uvicorn
import websockets

from silc.core.raw_buffer import RawByteBuffer
from silc.daemon.events import encode_ws_frame
from silc.daemon.manager import SilcDaemon
from silc.daemon.runtime import SessionState, create_runtime_for_record
from silc.daemon.session_adapter import SessionPortAdapter


def _parse_headers(raw: bytes) -> dict[str, str]:
    lines = raw.decode("iso-8859-1").split("\r\n")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line or ":" not in line:
            continue
        name, value = line.split(":", 1)
        headers[name.lower()] = value.strip()
    return headers


def _decode_ws_frame(frame: bytes) -> tuple[dict[str, object], bytes]:
    header_length = int.from_bytes(frame[:4], "big")
    header = json.loads(frame[4 : 4 + header_length].decode("utf-8"))
    return header, frame[4 + header_length :]


async def _wait_until(predicate, timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("condition was not met in time")


@pytest.mark.asyncio
async def test_session_port_adapter_rewrites_http_to_daemon_routes() -> None:
    seen: dict[str, object] = {}

    async def daemon_handler(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        header_blob = await reader.readuntil(b"\r\n\r\n")
        request_line = header_blob.split(b"\r\n", 1)[0].decode("iso-8859-1")
        seen["request_line"] = request_line
        seen["headers"] = _parse_headers(header_blob[:-4])

        body = b'{"status":"ok"}'
        writer.write(
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\n".encode("ascii")
            + b"Connection: close\r\n\r\n"
            + body
        )
        await writer.drain()
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()

    daemon_server = await asyncio.start_server(daemon_handler, "127.0.0.1", 0)
    daemon_port = daemon_server.sockets[0].getsockname()[1]

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setblocking(False)
    sock.bind(("127.0.0.1", 0))
    sock.listen(64)
    adapter_port = sock.getsockname()[1]

    adapter = SessionPortAdapter(
        session_port=20480,
        daemon_host="127.0.0.1",
        daemon_port=daemon_port,
    )
    adapter_task = asyncio.create_task(adapter.serve(sockets=[sock]))

    try:
        await asyncio.sleep(0.1)
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"http://127.0.0.1:{adapter_port}/status")

        assert resp.status_code == 200
        assert resp.text == '{"status":"ok"}'
        assert seen["request_line"] == "GET /sessions/20480/status HTTP/1.1"
        assert seen["headers"]["x-silc-client-host"] == "127.0.0.1"
        assert seen["headers"]["connection"] == "close"
    finally:
        adapter.should_exit = True
        with contextlib.suppress(Exception):
            await asyncio.wait_for(adapter_task, timeout=5)
        daemon_server.close()
        await daemon_server.wait_closed()


@pytest.mark.asyncio
async def test_session_port_adapter_keeps_public_web_path_without_redirect_and_rewrites_assets() -> (
    None
):
    seen: dict[str, object] = {}

    async def daemon_handler(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        header_blob = await reader.readuntil(b"\r\n\r\n")
        request_line = header_blob.split(b"\r\n", 1)[0].decode("iso-8859-1")
        seen["request_line"] = request_line

        body = b'<!doctype html><script type="module" src="./assets/main.js"></script>'
        writer.write(
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/html; charset=utf-8\r\n"
            + f"Content-Length: {len(body)}\r\n".encode("ascii")
            + b"Connection: close\r\n\r\n"
            + body
        )
        await writer.drain()
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()

    daemon_server = await asyncio.start_server(daemon_handler, "127.0.0.1", 0)
    daemon_port = daemon_server.sockets[0].getsockname()[1]

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setblocking(False)
    sock.bind(("127.0.0.1", 0))
    sock.listen(64)
    adapter_port = sock.getsockname()[1]

    adapter = SessionPortAdapter(
        session_port=20480,
        daemon_host="127.0.0.1",
        daemon_port=daemon_port,
    )
    adapter_task = asyncio.create_task(adapter.serve(sockets=[sock]))

    try:
        await asyncio.sleep(0.1)
        async with httpx.AsyncClient(follow_redirects=False) as client:
            resp = await client.get(f"http://127.0.0.1:{adapter_port}/web")

        assert resp.status_code == 200
        assert resp.headers.get("location") is None
        assert "/web/assets/main.js" in resp.text
        assert "./assets/main.js" not in resp.text
        assert seen["request_line"] == "GET /sessions/20480/web HTTP/1.1"
    finally:
        adapter.should_exit = True
        with contextlib.suppress(Exception):
            await asyncio.wait_for(adapter_task, timeout=5)
        daemon_server.close()
        await daemon_server.wait_closed()


@pytest.mark.asyncio
async def test_session_port_adapter_keeps_public_web_asset_base_with_trailing_slash() -> (
    None
):
    async def daemon_handler(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await reader.readuntil(b"\r\n\r\n")

        body = b'<!doctype html><script type="module" src="./assets/main.js"></script>'
        writer.write(
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/html; charset=utf-8\r\n"
            + f"Content-Length: {len(body)}\r\n".encode("ascii")
            + b"Connection: close\r\n\r\n"
            + body
        )
        await writer.drain()
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()

    daemon_server = await asyncio.start_server(daemon_handler, "127.0.0.1", 0)
    daemon_port = daemon_server.sockets[0].getsockname()[1]

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setblocking(False)
    sock.bind(("127.0.0.1", 0))
    sock.listen(64)
    adapter_port = sock.getsockname()[1]

    adapter = SessionPortAdapter(
        session_port=20480,
        daemon_host="127.0.0.1",
        daemon_port=daemon_port,
    )
    adapter_task = asyncio.create_task(adapter.serve(sockets=[sock]))

    try:
        await asyncio.sleep(0.1)
        async with httpx.AsyncClient(follow_redirects=False) as client:
            resp = await client.get(f"http://127.0.0.1:{adapter_port}/web/")

        assert resp.status_code == 200
        assert "/web/assets/main.js" in resp.text
        assert "./assets/main.js" not in resp.text
    finally:
        adapter.should_exit = True
        with contextlib.suppress(Exception):
            await asyncio.wait_for(adapter_task, timeout=5)
        daemon_server.close()
        await daemon_server.wait_closed()


@pytest.mark.asyncio
async def test_session_port_adapter_forwards_websocket_frames() -> None:
    def _pick_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]

    daemon_port = _pick_port()
    adapter_port = _pick_port()
    seen: dict[str, object] = {}

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setblocking(False)
    sock.bind(("127.0.0.1", adapter_port))
    sock.listen(64)

    async def daemon_handler(ws) -> None:
        seen["path"] = getattr(ws, "path", None) or getattr(
            getattr(ws, "request", None), "path", None
        )
        seen["connected"] = True
        try:
            await ws.send(encode_ws_frame({"type": "output"}, b"adapter-output"))
            incoming = await asyncio.wait_for(ws.recv(), timeout=5)
            assert isinstance(incoming, bytes)
            header, payload = _decode_ws_frame(incoming)
            seen["input_header"] = header
            seen["input_payload"] = payload
            await ws.wait_closed()
        finally:
            seen["closed"] = True

    server = await websockets.serve(daemon_handler, "127.0.0.1", daemon_port)

    adapter = SessionPortAdapter(
        session_port=20480,
        daemon_host="127.0.0.1",
        daemon_port=daemon_port,
    )
    adapter_task = asyncio.create_task(adapter.serve(sockets=[sock]))

    async def wait_for_port(port: int) -> None:
        deadline = asyncio.get_running_loop().time() + 5.0
        while asyncio.get_running_loop().time() < deadline:
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", port)
                writer.close()
                with contextlib.suppress(Exception):
                    await writer.wait_closed()
                return
            except OSError:
                await asyncio.sleep(0.05)
        raise AssertionError(f"port {port} did not open")

    try:
        await wait_for_port(daemon_port)
        await wait_for_port(adapter_port)

        async with websockets.connect(
            f"ws://127.0.0.1:{adapter_port}/ws?mode=interactive"
        ) as ws:
            await _wait_until(lambda: seen.get("connected") is True)
            assert seen["path"] == "/sessions/20480/ws?mode=interactive"

            frame = await asyncio.wait_for(ws.recv(), timeout=5)
            assert isinstance(frame, bytes)
            header, payload = _decode_ws_frame(frame)
            assert header["type"] == "output"
            assert payload == b"adapter-output"

            await ws.send(
                encode_ws_frame({"type": "input", "nonewline": True}, b"typed")
            )
            await _wait_until(lambda: seen.get("input_payload") == b"typed")
            assert seen["input_header"]["type"] == "input"
            assert seen["input_payload"] == b"typed"

        await asyncio.sleep(0.1)
        await _wait_until(lambda: seen.get("closed") is True)
    finally:
        adapter.should_exit = True
        with contextlib.suppress(Exception):
            await asyncio.wait_for(adapter_task, timeout=5)
        server.close()
        with contextlib.suppress(Exception):
            await server.wait_closed()
