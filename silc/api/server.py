"""FastAPI server exposing SILC session controls."""

from __future__ import annotations

import asyncio
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from ..core.cleaner import clean_output
from ..core.session import SilcSession
from .models import InputRequest, RunRequest


def create_app(session: SilcSession) -> FastAPI:
    app = FastAPI(title=f"SILC Session {session.session_id}")

    @app.get("/status")
    async def get_status() -> dict:
        return session.get_status()

    @app.get("/out")
    async def get_output(lines: int = 100, raw: bool = False) -> dict:
        output = session.get_output(lines, raw)
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
    async def send_input(payload: InputRequest) -> dict:
        await session.write_input(payload.text)
        return {"status": "sent"}

    @app.post("/run")
    async def run_command(payload: RunRequest) -> dict:
        return await session.run_command(payload.command, payload.timeout)

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

    return app
