"""FastAPI server exposing SILC session controls."""

from __future__ import annotations

import asyncio
import json
import sys

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, HTMLResponse
from pathlib import Path

from ..core.cleaner import clean_output
from ..core.session import SilcSession


def create_app(session: SilcSession) -> FastAPI:
    app = FastAPI(title=f"SILC Session {session.session_id}")

    def _check_alive() -> None:
        """Check if session is alive, raise exception if not."""
        if not session.get_status()["alive"]:
            raise HTTPException(status_code=410, detail="Session has ended")

    @app.get("/status")
    async def get_status() -> dict:
        status = session.get_status()
        if not status["alive"]:
            raise HTTPException(status_code=410, detail="Session has ended")
        return status

    @app.get("/out")
    async def get_output(lines: int = 100) -> dict:
        _check_alive()
        output = session.get_output(lines)
        return {"output": output, "lines": len(output.splitlines())}

    @app.get("/raw")
    async def get_raw_output(lines: int = 100) -> dict:
        _check_alive()
        output = session.get_output(lines, raw=True)
        return {"output": output, "lines": len(output.splitlines())}

    @app.get("/stream")
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

    @app.post("/in")
    async def send_input(request: Request, nonewline: bool = False) -> dict:
        _check_alive()
        body = await request.body()
        text = body.decode("utf-8", errors="replace")
        if not nonewline and text and not text.endswith(("\r\n", "\n")):
            text += "\r\n" if sys.platform == "win32" else "\n"
        await session.write_input(text)
        return {"status": "sent"}

    @app.post("/run")
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

    @app.post("/interrupt")
    async def interrupt() -> dict:
        _check_alive()
        await session.interrupt()
        return {"status": "interrupted"}

    @app.post("/clear")
    async def clear_buffer() -> dict:
        _check_alive()
        await session.clear_buffer()
        return {"status": "cleared"}

    @app.post("/resize")
    async def resize(rows: int, cols: int) -> dict:
        _check_alive()
        session.resize(rows, cols)
        return {"status": "resized", "rows": rows, "cols": cols}

    @app.post("/close")
    async def close() -> dict:
        await session.close()
        return {"status": "closed"}

    @app.post("/kill")
    async def kill() -> dict:
        await session.force_kill()
        return {"status": "killed"}

    @app.post("/tui/activate")
    async def activate_tui() -> dict:
        session.tui_active = True
        return {"status": "tui_active"}

    @app.post("/tui/deactivate")
    async def deactivate_tui() -> dict:
        session.tui_active = False
        return {"status": "tui_inactive"}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()

        async def send_updates():
            cursor = session.buffer.cursor
            while True:
                new_bytes, cursor = session.buffer.get_since(cursor)
                if new_bytes:
                    await websocket.send_json(
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
                    if message.get("event") == "type":
                        text = message.get("text", "")
                        if text:
                            newline = "\r\n" if sys.platform == "win32" else "\n"
                            if not text.endswith(("\r\n", "\n")):
                                text += newline
                            await session.write_input(text)
                except json.JSONDecodeError:
                    pass
        except WebSocketDisconnect:
            pass
        finally:
            sender_task.cancel()
            try:
                await sender_task
            except asyncio.CancelledError:
                pass

    @app.get("/web", response_class=HTMLResponse)
    async def web_ui() -> HTMLResponse:
        static_dir = Path(__file__).parent.parent.parent / "static"
        index_path = static_dir / "index.html"
        if index_path.exists():
            with open(index_path, "r", encoding="utf-8") as f:
                return HTMLResponse(f.read())
        return HTMLResponse("<h1>Web UI not found</h1>")

    return app
