"""Session orchestration that ties the PTY, buffer, and API surface together."""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime
from typing import Optional

from ..core.buffer import RingBuffer
from ..core.cleaner import clean_output
from ..core.pty_manager import create_pty, PTYBase
from ..utils.shell_detect import ShellInfo


class SilcSession:
    def __init__(self, port: int, shell_info: ShellInfo):
        self.port = port
        self.shell_info = shell_info
        self.session_id = str(uuid.uuid4())[:8]
        self.pty: PTYBase = create_pty(shell_info.path, os.environ.copy())

        self.buffer = RingBuffer(maxlen=1000)
        self.created_at = datetime.utcnow()
        self.last_access = datetime.utcnow()
        self.last_output = datetime.utcnow()

        self.run_lock = asyncio.Lock()
        self.input_lock = asyncio.Lock()

        self._read_task: Optional[asyncio.Task[None]] = None
        self._gc_task: Optional[asyncio.Task[None]] = None
        self._closed = False
        self.tui_active = False

    async def start(self) -> None:
        if self._read_task is not None:
            return
        self._read_task = asyncio.create_task(self._read_loop())
        self._gc_task = asyncio.create_task(self._garbage_collect())

    async def _read_loop(self) -> None:
        while not self._closed:
            try:
                data = await self.pty.read(4096)
                if data:
                    self.buffer.append(data)
                    self.last_output = datetime.utcnow()
                else:
                    await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                break
            except Exception:
                break

    async def _garbage_collect(self) -> None:
        # GC runs every 60s; closes session if:
        # - idle > 1800s (30min)
        # - not actively used (tui_active is False)
        # - not currently running a command (run_lock not locked)
        # - no TUI connection
        while not self._closed:
            await asyncio.sleep(60)
            idle = (datetime.utcnow() - self.last_access).total_seconds()
            if idle > 1800 and not self.tui_active and not self.run_lock.locked():
                await self.close()
                break

    async def write_input(self, text: str) -> None:
        async with self.input_lock:
            await self.pty.write(text.encode("utf-8", errors="replace"))
            await asyncio.sleep(0.05)
        self.last_access = datetime.utcnow()

    def get_output(self, lines: int = 100, raw: bool = False) -> str:
        self.last_access = datetime.utcnow()
        snapshot = self.buffer.get_last(lines)
        if raw:
            return "\n".join(snapshot)
        return clean_output(snapshot)

    async def run_command(self, cmd: str, timeout: int = 60) -> dict:
        if self.run_lock.locked():
            return {
                "error": "Another run command is already executing",
                "status": "busy",
            }

        async with self.run_lock:
            sentinel_uuid = str(uuid.uuid4())[:8]
            sentinel = f"__SILC_DONE_{sentinel_uuid}__"
            full_cmd = cmd + self.shell_info.get_sentinel_command(sentinel_uuid)
            cursor = self.buffer.cursor

            await self.write_input(full_cmd + "\n")
            loop = asyncio.get_running_loop()
            deadline = loop.time() + timeout

            while loop.time() < deadline:
                new_lines, cursor = self.buffer.get_since(cursor)
                chunk = "\n".join(new_lines)
                if sentinel in chunk:
                    output_before, after = chunk.split(sentinel, 1)
                    exit_code = 0
                    for token in after.strip().split():
                        token = token.lstrip(":")
                        if token.lstrip("-").isdigit():
                            exit_code = int(token)
                            break
                    return {
                        "output": clean_output(output_before.splitlines()),
                        "exit_code": exit_code,
                        "status": "completed",
                    }
                await asyncio.sleep(0.25)

            new_lines, _ = self.buffer.get_since(cursor)
            return {
                "output": clean_output(new_lines),
                "status": "timeout",
                "error": f"Command did not complete in {timeout}s",
            }

    def get_status(self) -> dict:
        self.last_access = datetime.utcnow()
        last_line = self.buffer.get_last(1)
        waiting = bool(last_line and last_line[0].strip().endswith((":?", "]")))
        return {
            "session_id": self.session_id,
            "port": self.port,
            "alive": self._read_task is not None and not self._read_task.done(),
            "idle_seconds": (datetime.utcnow() - self.last_output).seconds,
            "waiting_for_input": waiting,
            "last_line": last_line[0] if last_line else "",
            "run_locked": self.run_lock.locked(),
        }

    async def interrupt(self) -> None:
        await self.pty.write(b"\x03")

    async def clear_buffer(self) -> None:
        self.buffer.clear()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.tui_active = False
        if self._read_task:
            self._read_task.cancel()
        if self._gc_task:
            self._gc_task.cancel()
        self.pty.kill()

    async def force_kill(self) -> None:
        self._closed = True
        if self._read_task:
            self._read_task.cancel()
        if self._gc_task:
            self._gc_task.cancel()
        self.pty.kill()


__all__ = ["SilcSession"]
