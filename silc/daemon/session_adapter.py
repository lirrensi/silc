# FILE: silc/daemon/session_adapter.py
# PURPOSE: Proxy live session-port clients to the daemon session routes without running per-session ASGI servers.
# OWNS: Tiny loopback TCP adapters, request-line rewriting, daemon forwarding headers, and websocket/raw-byte tunneling.
# EXPORTS: SessionPortAdapter - async session-port listener compatible with the daemon lifecycle.
# DOCS: agent_chat/plan_daemon_session_adapters_2026-04-08.md

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from typing import Iterable


def _split_request_target(target: str) -> tuple[str, str]:
    if "?" in target:
        path, query = target.split("?", 1)
        return path, f"?{query}"
    return target, ""


def _rewrite_target(target: str, session_port: int) -> str:
    path, query = _split_request_target(target)
    if path == "/":
        path = "/web"
    if not path.startswith("/sessions/"):
        path = f"/sessions/{session_port}{path}"
    return f"{path}{query}"


def _uses_public_web_asset_base(target: str) -> bool:
    path, _query = _split_request_target(target)
    return path in {"/web", "/web/"}


def _parse_header_lines(header_blob: bytes) -> tuple[str, list[tuple[str, str]]]:
    text = header_blob.decode("iso-8859-1", errors="replace")
    lines = text.split("\r\n")
    request_line = lines[0]
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        headers.append((name.strip(), value.lstrip()))
    return request_line, headers


def _format_headers(
    request_line: str,
    headers: Iterable[tuple[str, str]],
) -> bytes:
    header_lines = [request_line]
    for name, value in headers:
        header_lines.append(f"{name}: {value}")
    header_lines.append("")
    header_lines.append("")
    return "\r\n".join(header_lines).encode("iso-8859-1", errors="replace")


def _header_value(headers: list[tuple[str, str]], name: str) -> str | None:
    target = name.lower()
    for header_name, value in headers:
        if header_name.lower() == target:
            return value
    return None


def _replace_or_append_header(
    headers: list[tuple[str, str]], name: str, value: str
) -> list[tuple[str, str]]:
    target = name.lower()
    updated: list[tuple[str, str]] = []
    replaced = False
    for header_name, header_value in headers:
        if header_name.lower() == target:
            if not replaced:
                updated.append((name, value))
                replaced = True
            continue
        updated.append((header_name, header_value))
    if not replaced:
        updated.append((name, value))
    return updated


def _rewrite_html_asset_paths(body: bytes) -> bytes:
    return body.replace(b"./assets/", b"/web/assets/")


@dataclass(slots=True)
class SessionPortAdapter:
    session_port: int
    daemon_host: str = "127.0.0.1"
    daemon_port: int = 19999
    _server: asyncio.AbstractServer | None = field(default=None, init=False, repr=False)
    _should_exit: bool = field(default=False, init=False, repr=False)
    _stop_event: asyncio.Event = field(
        default_factory=asyncio.Event, init=False, repr=False
    )
    _connections: set[asyncio.StreamWriter] = field(
        default_factory=set, init=False, repr=False
    )

    @property
    def should_exit(self) -> bool:
        return self._should_exit

    @should_exit.setter
    def should_exit(self, value: bool) -> None:
        self._should_exit = bool(value)
        if self._should_exit:
            self._stop_event.set()
            for writer in list(self._connections):
                with contextlib.suppress(Exception):
                    writer.close()
            if self._server is not None:
                self._server.close()

    def is_serving(self) -> bool:
        return bool(
            self._server and self._server.is_serving() and not self._should_exit
        )

    async def serve(self, sockets: list[object] | None = None) -> None:
        sock = sockets[0] if sockets else None
        self._server = await asyncio.start_server(
            self._handle_client,
            sock=sock,
            start_serving=True,
        )
        try:
            await self._stop_event.wait()
        finally:
            if self._server is not None:
                self._server.close()
                with contextlib.suppress(Exception):
                    await self._server.wait_closed()
            for writer in list(self._connections):
                with contextlib.suppress(Exception):
                    writer.close()
                    await writer.wait_closed()

    async def _handle_client(
        self, client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter
    ) -> None:
        self._connections.add(client_writer)
        daemon_writer: asyncio.StreamWriter | None = None
        try:
            header_blob = await client_reader.readuntil(b"\r\n\r\n")
            request_line, headers = _parse_header_lines(header_blob[:-4])
            method, target, version = request_line.split(" ", 2)

            client_host = None
            peer = client_writer.get_extra_info("peername")
            if isinstance(peer, tuple) and peer:
                client_host = str(peer[0])

            is_websocket = False
            connection_header = _header_value(headers, "Connection") or ""
            upgrade_header = _header_value(headers, "Upgrade") or ""
            if (
                "upgrade" in connection_header.lower()
                and upgrade_header.lower() == "websocket"
            ):
                is_websocket = True

            forwarded_headers = _replace_or_append_header(
                headers, "X-Silc-Client-Host", client_host or "127.0.0.1"
            )
            if is_websocket:
                forwarded_headers = _replace_or_append_header(
                    forwarded_headers, "Connection", connection_header or "Upgrade"
                )
            else:
                forwarded_headers = _replace_or_append_header(
                    forwarded_headers, "Connection", "close"
                )

            rewritten_request_line = (
                f"{method} {_rewrite_target(target, self.session_port)} {version}"
            )
            outgoing_head = _format_headers(rewritten_request_line, forwarded_headers)

            try:
                daemon_reader, daemon_writer = await asyncio.open_connection(
                    self.daemon_host, self.daemon_port
                )
            except Exception:
                await self._write_gateway_failure(client_writer)
                return

            daemon_writer.write(outgoing_head)
            await daemon_writer.drain()

            if not is_websocket and _uses_public_web_asset_base(target):
                await self._forward_public_web_html(daemon_reader, client_writer)
                return

            relay_tasks = [
                asyncio.create_task(
                    self._relay_stream(client_reader, daemon_writer, close_target=True)
                ),
                asyncio.create_task(
                    self._relay_stream(daemon_reader, client_writer, close_target=False)
                ),
            ]
            done, pending = await asyncio.wait(
                relay_tasks, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            for task in done:
                with contextlib.suppress(Exception):
                    await task
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            return
        except Exception:
            with contextlib.suppress(Exception):
                await self._write_gateway_failure(client_writer)
        finally:
            self._connections.discard(client_writer)
            if daemon_writer is not None:
                with contextlib.suppress(Exception):
                    daemon_writer.close()
                    await daemon_writer.wait_closed()
            with contextlib.suppress(Exception):
                client_writer.close()
                await client_writer.wait_closed()

    async def _relay_stream(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        *,
        close_target: bool,
    ) -> None:
        try:
            while not self._should_exit:
                chunk = await reader.read(65536)
                if not chunk:
                    break
                writer.write(chunk)
                await writer.drain()
        finally:
            if close_target:
                with contextlib.suppress(Exception):
                    writer.close()

    async def _forward_public_web_html(
        self,
        daemon_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        response_head = await daemon_reader.readuntil(b"\r\n\r\n")
        status_line, headers = _parse_header_lines(response_head[:-4])
        content_length = _header_value(headers, "Content-Length")

        body = b""
        if content_length is not None:
            remaining = max(int(content_length), 0)
            if remaining:
                body = await daemon_reader.readexactly(remaining)
        else:
            body = await daemon_reader.read()

        content_type = (_header_value(headers, "Content-Type") or "").lower()
        if "text/html" in content_type:
            body = _rewrite_html_asset_paths(body)
            headers = _replace_or_append_header(
                headers, "Content-Length", str(len(body))
            )

        client_writer.write(_format_headers(status_line, headers) + body)
        await client_writer.drain()

    async def _write_gateway_failure(self, writer: asyncio.StreamWriter) -> None:
        body = b"Bad gateway"
        writer.write(
            b"HTTP/1.1 502 Bad Gateway\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            + f"Content-Length: {len(body)}\r\n".encode("ascii")
            + b"Connection: close\r\n\r\n"
            + body
        )
        await writer.drain()
