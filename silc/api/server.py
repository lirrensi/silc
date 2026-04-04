"""FastAPI server exposing SILC session controls."""

from __future__ import annotations

import asyncio
import json
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
from fastapi.responses import HTMLResponse, StreamingResponse

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

    @app.post("/reset", dependencies=[Depends(_require_token)])
    async def reset_terminal() -> dict:
        _check_alive()
        await session.reset_terminal()
        return {"status": "reset"}

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
        await websocket.accept()

        previous_websocket: WebSocket | None = None
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

        async def safe_send(payload: dict[str, str]) -> None:
            async with send_lock:
                await websocket.send_json(payload)

        def title_listener(updated_session: SilcSession) -> None:
            if updated_session is not session:
                return

            async def _send_title() -> None:
                if active_websocket is not websocket:
                    return
                try:
                    await safe_send(
                        {
                            "event": "title",
                            "title": updated_session.title,
                            "title_updated_at": (
                                updated_session.title_updated_at.isoformat() + "Z"
                            ),
                        }
                    )
                except Exception:
                    pass

            asyncio.create_task(_send_title())

        session.add_title_listener(title_listener)

        async def send_updates() -> None:
            cursor = session.buffer.cursor
            while True:
                new_bytes, cursor = session.buffer.get_since(cursor)
                if new_bytes:
                    await safe_send(
                        {
                            "event": "update",
                            "data": new_bytes.decode("utf-8", errors="replace"),
                        }
                    )
                await asyncio.sleep(0.1)

        sender_task = asyncio.create_task(send_updates())
        try:
            while True:
                data = await websocket.receive_text()
                try:
                    message = json.loads(data)
                    event_type = message.get("event")
                    if event_type == "type":
                        text = message.get("text", "")
                        nonewline = message.get("nonewline", False)

                        if nonewline:
                            await session.write_input(text)
                        else:
                            # Match /in endpoint behavior: strip newlines, add platform newline
                            text = text.rstrip("\r\n")
                            newline = "\r\n" if sys.platform == "win32" else "\n"
                            text += newline
                            await session.write_input(text)
                    elif event_type == "load_history":
                        raw_bytes = session.buffer.get_bytes()
                        await safe_send(
                            {
                                "event": "history",
                                "data": raw_bytes.decode("utf-8", errors="replace"),
                            }
                        )
                        await safe_send(
                            {
                                "event": "title",
                                "title": session.title,
                                "title_updated_at": session.title_updated_at.isoformat()
                                + "Z",
                            }
                        )
                except json.JSONDecodeError:
                    pass
        except WebSocketDisconnect:
            pass
        finally:
            session.remove_title_listener(title_listener)
            async with active_websocket_lock:
                if active_websocket is websocket:
                    active_websocket = None
                    session.tui_active = False
            sender_task.cancel()
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
