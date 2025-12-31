"""FastAPI server exposing SILC session controls."""

from __future__ import annotations

import asyncio
import json
import sys

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from ..core.cleaner import clean_output
from ..core.session import SilcSession


def create_app(session: SilcSession) -> FastAPI:
    app = FastAPI(title=f"SILC Session {session.session_id}")

    @app.get("/status")
    async def get_status() -> dict:
        return session.get_status()

    @app.get("/out")
    async def get_output(lines: int = 100) -> dict:
        output = session.get_output(lines)
        return {"output": output, "lines": len(output.splitlines())}

    @app.get("/raw")
    async def get_raw_output(lines: int = 100) -> dict:
        output = session.get_output(lines, raw=True)
        return {"output": output, "lines": len(output.splitlines())}

    @app.get("/stream")
    async def stream_output() -> StreamingResponse:
        async def generator():
            cursor = session.buffer.cursor
            while True:
                new_lines, cursor = session.buffer.get_since(cursor)
                if new_lines:
                    yield f"data: {clean_output(new_lines)}\n\n"
                await asyncio.sleep(0.5)

        return StreamingResponse(generator(), media_type="text/event-stream")

    @app.post("/in")
    async def send_input(request: Request, nonewline: bool = False) -> dict:
        body = await request.body()
        text = body.decode("utf-8", errors="replace")
        if (
            not nonewline
            and text
            and not text.endswith(("\r\n", "\n"))
        ):
            text += "\r\n" if sys.platform == "win32" else "\n"
        await session.write_input(text)
        return {"status": "sent"}

    @app.post("/run")
    async def run_command(request: Request, timeout: int = 60) -> dict:
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
        await session.interrupt()
        return {"status": "interrupted"}

    @app.post("/clear")
    async def clear() -> dict:
        await session.clear_buffer()
        return {"status": "cleared"}

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

    return app
