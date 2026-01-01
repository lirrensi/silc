"""Session orchestration that ties the PTY, buffer, and API surface together."""

from __future__ import annotations

import asyncio
import os
import re
import sys
import uuid
from datetime import datetime
from typing import Optional

try:
    import pyte
except ImportError:  # pragma: no cover
    pyte = None  # type: ignore[assignment]

from ..core.buffer import RingBuffer
from ..core.cleaner import ANSI_ESCAPE, clean_output
from ..core.pty_manager import create_pty, PTYBase
from ..utils.shell_detect import ShellInfo


OSC_SEQUENCE = re.compile(r"\x1b\][^\x1b]*(?:\x1b\\|\x07)")


def _strip_control(line: str) -> str:
    cleaned = OSC_SEQUENCE.sub("", line)
    cleaned = ANSI_ESCAPE.sub("", cleaned)
    return cleaned.replace("\r", "")


def _is_prompt_line(line: str, prompt_pattern: re.Pattern[str]) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return bool(prompt_pattern.match(stripped))


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

        self.screen_columns = 120
        self.screen_rows = 30
        self.screen: "pyte.screen.Screen" | None = None
        self.stream: "pyte.Stream" | None = None
        if pyte:
            self.screen = pyte.Screen(self.screen_columns, self.screen_rows)
            self.stream = pyte.Stream(self.screen)

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
                    if self.stream:
                        decoded = data.decode("utf-8", errors="replace")
                        self.stream.feed(decoded)
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
        if raw:
            snapshot = self.buffer.get_last(lines)
            return "\n".join(snapshot)
        return self.get_rendered_output(lines)

    def get_rendered_output(self, lines: int | None = None) -> str:
        if self.screen is None:
            snapshot = self.buffer.get_last(lines or 100)
            output = clean_output(snapshot)
            # Remove sentinel lines
            return self._remove_sentinels(output)

        rows = list(self.screen.display)
        rendered_lines = [line.rstrip() for line in rows]
        if not any(line.strip() for line in rendered_lines):
            snapshot = self.buffer.get_last(lines or 100)
            output = clean_output(snapshot)
            return self._remove_sentinels(output)
        
        if lines is not None and lines < len(rendered_lines):
            rendered_lines = rendered_lines[-lines:]
        
        # Filter out sentinel lines before joining
        filtered_lines = [
            line for line in rendered_lines
            if not re.search(r'__SILC_DONE_\w+__', line)
        ]
        
        return "\n".join(filtered_lines).rstrip()

    def _remove_sentinels(self, text: str) -> str:
        """Remove sentinel marker lines from output."""
        lines = text.split('\n')
        filtered = [
            line for line in lines
            if not re.search(r'__SILC_DONE_\w+__', line)
        ]
        return '\n'.join(filtered)

    async def run_command(self, cmd: str, timeout: int = 60) -> dict:
        if self.run_lock.locked():
            return {
                "error": "Another run command is already executing",
                "status": "busy",
            }

        async with self.run_lock:
            sentinel_uuid = str(uuid.uuid4())[:8]
            sentinel = f"__SILC_DONE_{sentinel_uuid}__"
            cursor = self.buffer.cursor
            suffix = self.shell_info.get_sentinel_command(sentinel_uuid)
            full_cmd = cmd + suffix

            newline = "\r\n" if sys.platform == "win32" else "\n"
            await self.write_input(full_cmd + newline)
            loop = asyncio.get_running_loop()
            deadline = loop.time() + timeout

            output_lines: list[str] = []
            sentinel_matcher = re.compile(rf"^{re.escape(sentinel)}\s*:\s*(-?\d+)")
            while loop.time() < deadline:
                new_lines, cursor = self.buffer.get_since(cursor)
                for line in new_lines:
                    clean_line = _strip_control(line)
                    stripped = clean_line.lstrip()
                    match = sentinel_matcher.match(stripped)
                    if match:
                        exit_code = int(match.group(1))
                        return {
                            "output": clean_output(output_lines),
                            "exit_code": exit_code,
                            "status": "completed",
                        }
                    if _is_prompt_line(clean_line, self.shell_info.prompt_pattern):
                        continue
                    output_lines.append(clean_line)
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

        tasks: list[asyncio.Task[None]] = []
        if self._read_task:
            self._read_task.cancel()
            tasks.append(self._read_task)
        if self._gc_task:
            self._gc_task.cancel()
            tasks.append(self._gc_task)

        # Kill the PTY first to unblock any pending reads.
        self.pty.kill()

        # Best-effort wait for tasks to unwind. Never hang forever.
        for task in tasks:
            try:
                await asyncio.wait_for(task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception:
                pass

        self._read_task = None
        self._gc_task = None

    async def force_kill(self) -> None:
        self._closed = True

        tasks: list[asyncio.Task[None]] = []
        if self._read_task:
            self._read_task.cancel()
            tasks.append(self._read_task)
        if self._gc_task:
            self._gc_task.cancel()
            tasks.append(self._gc_task)

        self.pty.kill()

        for task in tasks:
            try:
                await asyncio.wait_for(task, timeout=0.5)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception:
                pass

        self._read_task = None
        self._gc_task = None


__all__ = ["SilcSession"]
