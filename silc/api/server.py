# FILE: silc/api/server.py
# PURPOSE: Expose session HTTP and websocket controls for SILC sessions.
# OWNS: FastAPI endpoints, websocket framing, auth, and websocket lifecycle.
# EXPORTS: create_app - build a per-session FastAPI app.
# DOCS: agent_chat/plan_ws_binary_framing_2026-04-05.md

"""FastAPI server exposing SILC session controls."""

from __future__ import annotations

import asyncio
import json
import struct
import sys
from ipaddress import AddressValueError, ip_address
from pathlib import Path

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response, StreamingResponse

from ..core.cleaner import clean_output
from ..core.session import SilcSession
from ..stream import api_endpoints
from ..stream.streaming_service import StreamingService
from ..utils.persistence import read_session_log


def create_app(session: SilcSession) -> FastAPI:
    def _client_is_local(host: str | None) -> bool:
        if not host:
            return False
        if host.lower() == "localhost":
            return True
        if "%" in host:
            host = host.split("%", 1)[0]
        try:
            addr = ip_address(host)
        except AddressValueError:
            return False
        if addr.is_loopback:
            return True
        ipv4_mapped = getattr(addr, "ipv4_mapped", None)
        if ipv4_mapped and ipv4_mapped.is_loopback:
            return True
        return False

    def _require_token(request: Request) -> None:
        token = session.api_token
        if not token:
            return
        client = request.client
        client_host = client[0] if client else None
        if _client_is_local(client_host):
            return

        auth_header = request.headers.get("authorization")
        if not auth_header:
            raise HTTPException(status_code=401, detail="Missing API token")

        parts = auth_header.strip().split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid Authorization header")

        provided = parts[1].strip()
        if provided != token:
            raise HTTPException(status_code=403, detail="Invalid API token")

    def _verify_websocket_token(websocket: WebSocket) -> bool:
        token = session.api_token
        if not token:
            return True
        client = websocket.client
        client_host = client[0] if client else None
        if _client_is_local(client_host):
            return True
        provided = websocket.query_params.get("token")
        return provided == token

    app = FastAPI(
        title=f"SILC Session {session.session_id}",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Create streaming service instance
    streaming_service = StreamingService(session)
    active_websocket: WebSocket | None = None
    active_websocket_lock = asyncio.Lock()

    # Override the streaming service dependency
    def get_streaming_service_override() -> StreamingService:
        return streaming_service

    # Override the dependency in the streaming endpoints module
    app.dependency_overrides[api_endpoints.get_streaming_service] = (
        get_streaming_service_override
    )

    # Include streaming router with authentication
    app.include_router(api_endpoints.router, dependencies=[Depends(_require_token)])

    def encode_ws_frame(header: dict[str, object], payload: bytes = b"") -> bytes:
        header_bytes = json.dumps(
            header, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return struct.pack(">I", len(header_bytes)) + header_bytes + payload

    def decode_ws_frame(frame: bytes) -> tuple[dict[str, object], bytes]:
        if len(frame) < 4:
            raise ValueError("frame too short")

        header_length = struct.unpack(">I", frame[:4])[0]
        if len(frame) < 4 + header_length:
            raise ValueError("frame truncated")

        header_bytes = frame[4 : 4 + header_length]
        payload = frame[4 + header_length :]

        try:
            header = json.loads(header_bytes.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise ValueError("invalid frame header encoding") from exc
        except json.JSONDecodeError as exc:
            raise ValueError("invalid frame header json") from exc

        if not isinstance(header, dict):
            raise ValueError("frame header must be object")

        return header, payload

    def _check_alive() -> None:
        """Check if session is alive, raise exception if not."""
        if not session.get_status()["alive"]:
            raise HTTPException(status_code=410, detail="Session has ended")

    @app.get("/status", dependencies=[Depends(_require_token)])
    async def get_status() -> dict:
        status = session.get_status()
        if not status["alive"]:
            raise HTTPException(status_code=410, detail="Session has ended")
        return status

    @app.get("/out", dependencies=[Depends(_require_token)])
    async def get_output(lines: int = 100) -> dict:
        _check_alive()
        output = session.get_output(lines)
        return {"output": output, "lines": len(output.splitlines())}

    @app.get("/raw", dependencies=[Depends(_require_token)])
    async def get_raw_output(lines: int = 100) -> dict:
        _check_alive()
        output = session.get_output(lines, raw=True)
        return {"output": output, "lines": len(output.splitlines())}

    @app.get("/snapshot", dependencies=[Depends(_require_token)])
    async def get_snapshot() -> Response:
        _check_alive()
        return Response(
            content=session.get_snapshot_bytes(),
            media_type="application/octet-stream",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/logs", dependencies=[Depends(_require_token)])
    async def get_logs(tail: int = 100) -> dict:
        _check_alive()
        log_content = read_session_log(session.port, tail_lines=tail)
        lines = log_content.splitlines() if log_content else []
        return {"logs": log_content, "lines": len(lines)}

    @app.get("/stream", dependencies=[Depends(_require_token)])
    async def stream_output() -> StreamingResponse:
        _check_alive()

        async def generator():
            cursor = session.buffer.cursor
            while True:
                new_bytes, cursor = session.buffer.get_since(cursor)
                if new_bytes:
                    decoded = new_bytes.decode("utf-8", errors="replace").splitlines()
                    if decoded:
                        yield f"data: {clean_output(decoded)}\n\n"
                await asyncio.sleep(0.5)

        return StreamingResponse(generator(), media_type="text/event-stream")

    @app.post("/in", dependencies=[Depends(_require_token)])
    async def send_input(request: Request, nonewline: bool = False) -> dict:
        _check_alive()
        body = await request.body()
        text = body.decode("utf-8", errors="replace")

        # STRIP all line endings first!
        text = text.rstrip("\r\n")

        # Add platform line ending (unless nonewline flag)
        if not nonewline:
            text += "\r\n" if sys.platform == "win32" else "\n"

        await session.write_input(text)
        return {"status": "sent"}

    @app.post("/run", dependencies=[Depends(_require_token)])
    async def run_command(request: Request, timeout: int = 60) -> dict:
        _check_alive()
        body = await request.body()
        if not body:
            return {
                "error": "No command provided",
                "status": "bad_request",
            }
        text = body.decode("utf-8", errors="replace")
        command = text
        resolved_timeout = timeout
        try:
            payload = json.loads(text)
            command = payload.get("command", "")
            resolved_timeout = payload.get("timeout", timeout)
        except json.JSONDecodeError:
            pass

        command = command.rstrip("\r\n")
        return await session.run_command(command, resolved_timeout)

    @app.post("/interrupt", dependencies=[Depends(_require_token)])
    async def interrupt() -> dict:
        _check_alive()
        await session.interrupt()
        return {"status": "interrupted"}

    @app.post("/sigterm", dependencies=[Depends(_require_token)])
    async def sigterm() -> dict:
        _check_alive()
        await session.send_sigterm()
        return {"status": "sigterm_sent"}

    @app.post("/sigkill", dependencies=[Depends(_require_token)])
    async def sigkill() -> dict:
        _check_alive()
        await session.send_sigkill()
        return {"status": "sigkill_sent"}

    @app.post("/clear", dependencies=[Depends(_require_token)])
    async def clear_screen() -> dict:
        _check_alive()
        await session.clear_screen()
        return {"status": "cleared"}

    @app.post("/resize", dependencies=[Depends(_require_token)])
    async def resize(rows: int, cols: int) -> dict:
        _check_alive()
        session.resize(rows, cols)
        return {"status": "resized", "rows": rows, "cols": cols}

    # /tui/activate and /tui/deactivate endpoints removed; tui_active is managed via websocket connection

    @app.get("/token", dependencies=[Depends(_require_token)])
    async def token() -> dict[str, str | None]:
        """Expose the current session token (if any) for local helpers."""
        return {"token": session.api_token}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        nonlocal active_websocket

        if not _verify_websocket_token(websocket):
            await websocket.close(code=1008, reason="Invalid API token")
            return

        mode = websocket.query_params.get("mode", "interactive")
        if mode not in {"interactive", "preview"}:
            await websocket.close(code=1002, reason="Unsupported websocket mode")
            return

        await websocket.accept()

        previous_websocket: WebSocket | None = None
        if mode == "interactive":
            async with active_websocket_lock:
                previous_websocket = active_websocket
                active_websocket = websocket
                session.tui_active = True

            if previous_websocket is not None and previous_websocket is not websocket:
                try:
                    await previous_websocket.close(
                        code=4002, reason="Session claimed by another client"
                    )
                except RuntimeError:
                    pass

        send_lock = asyncio.Lock()

        async def safe_send_frame(
            header: dict[str, object], payload: bytes = b""
        ) -> None:
            async with send_lock:
                await websocket.send_bytes(encode_ws_frame(header, payload))

        async def send_output_chunks() -> None:
            cursor = session.buffer.cursor
            while True:
                await session._output_event.wait()
                session._output_event.clear()

                while True:
                    new_bytes, cursor = session.buffer.get_since(cursor)
                    if not new_bytes:
                        break
                    if active_websocket is not websocket:
                        return
                    try:
                        await safe_send_frame({"type": "output"}, new_bytes)
                    except Exception:
                        return

        def title_listener(updated_session: SilcSession) -> None:
            if updated_session is not session:
                return

            async def _send_title() -> None:
                if active_websocket is not websocket:
                    return
                try:
                    await safe_send_frame(
                        {
                            "type": "title",
                            "title": updated_session.title,
                            "title_updated_at": (
                                updated_session.title_updated_at.isoformat() + "Z"
                            ),
                        }
                    )
                except Exception:
                    pass

            asyncio.create_task(_send_title())

        def cwd_listener(updated_session: SilcSession) -> None:
            if updated_session is not session:
                return

            async def _send_cwd() -> None:
                if active_websocket is not websocket:
                    return
                try:
                    await safe_send_frame({"type": "cwd", "cwd": updated_session.cwd})
                except Exception:
                    pass

            asyncio.create_task(_send_cwd())

        if mode == "interactive":
            session.add_title_listener(title_listener)
            session.add_cwd_listener(cwd_listener)
            sender_task = asyncio.create_task(send_output_chunks())
        else:
            sender_task = None
        try:
            while True:
                try:
                    frame = await websocket.receive_bytes()
                except WebSocketDisconnect:
                    raise
                except RuntimeError:
                    await websocket.close(
                        code=1002, reason="Expected binary websocket frame"
                    )
                    return

                try:
                    header, payload = decode_ws_frame(frame)
                except ValueError:
                    await websocket.close(code=1002, reason="Malformed websocket frame")
                    return

                message_type = header.get("type")
                if message_type == "input":
                    if mode != "interactive":
                        await websocket.close(
                            code=1002, reason="Preview websocket is read-only"
                        )
                        return
                    nonewline = bool(header.get("nonewline", False))
                    text = payload.decode("utf-8", errors="replace")

                    if nonewline:
                        await session.write_input(text)
                    else:
                        text = text.rstrip("\r\n")
                        newline = "\r\n" if sys.platform == "win32" else "\n"
                        await session.write_input(text + newline)
                elif message_type == "load_history":
                    await safe_send_frame(
                        {"type": "history"}, session.buffer.get_bytes()
                    )
                else:
                    await websocket.close(
                        code=1002, reason="Unsupported websocket message"
                    )
                    return
        except WebSocketDisconnect:
            pass
        finally:
            if mode == "interactive":
                session.remove_title_listener(title_listener)
                session.remove_cwd_listener(cwd_listener)
                async with active_websocket_lock:
                    if active_websocket is websocket:
                        active_websocket = None
                        session.tui_active = False
                if sender_task is not None:
                    try:
                        await sender_task
                    except asyncio.CancelledError:
                        pass

    @app.get("/web", response_class=HTMLResponse)
    async def web_ui() -> HTMLResponse:
        static_dir = Path(__file__).parent.parent.parent / "static" / "web"
        index_path = static_dir / "index.html"
        if index_path.exists():
            with open(index_path, "r", encoding="utf-8") as f:
                return HTMLResponse(f.read())
        return HTMLResponse("<h1>Web UI not found</h1>")

    return app
