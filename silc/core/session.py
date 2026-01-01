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
    from pyte import Stream, screens
except ImportError:  # pragma: no cover
    pyte = None  # type: ignore[assignment]
    Stream = None
    screens = None

from ..core.cleaner import clean_output
from ..core.raw_buffer import RawByteBuffer
from ..core.pty_manager import create_pty, PTYBase
from ..utils.shell_detect import ShellInfo


OSC_SEQUENCE = re.compile(r"\x1b\][^\x1b]*(?:\x1b\\|\x07)")


SILC_SENTINEL_PATTERN = re.compile(r"__SILC_(?:BEGIN|END)_\w+__")


class SilcSession:
    def __init__(self, port: int, shell_info: ShellInfo):
        self.port = port
        self.shell_info = shell_info
        self.session_id = str(uuid.uuid4())[:8]
        self.pty: PTYBase = create_pty(shell_info.path, os.environ.copy())

        self.buffer = RawByteBuffer(maxlen=65536)
        self.created_at = datetime.utcnow()
        self.last_access = datetime.utcnow()
        self.last_output = datetime.utcnow()

        self.run_lock = asyncio.Lock()
        self.input_lock = asyncio.Lock()

        self.screen_columns = 120
        self.screen_rows = 30
        self.screen: "pyte.screen.Screen" | None = None
        self.stream: "Stream" | None = None
        if screens and Stream:
            self.screen = screens.HistoryScreen(self.screen_columns, self.screen_rows)
            self.stream = Stream(self.screen)
        self.pty.resize(self.screen_rows, self.screen_columns)

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
            data = text.encode("utf-8", errors="replace")
            await self.pty.write(data)
            await asyncio.sleep(0.05)
        self.last_access = datetime.utcnow()

    def get_output(self, lines: int = 100, raw: bool = False) -> str:
        """Get output from the session.

        Args:
            lines: Number of lines to return
            raw: If True, return raw decoded buffer; if False, return rendered screen

        Returns:
            The requested output as a string
        """
        self.last_access = datetime.utcnow()
        if raw:
            snapshot = self.buffer.get_last(lines)
            return "\n".join(snapshot)
        return self.get_rendered_output(lines)

    def get_rendered_output(self, lines: int | None = None) -> str:
        """Get a snapshot of what the terminal screen currently displays.

        This is the 'human view' - what you'd see if you looked at the terminal.
        """
        if self.screen is None:
            # Fallback: raw buffer cleaned
            snapshot = self.buffer.get_last(lines or 100)
            output = clean_output(snapshot)
            return self._remove_sentinels(output)

        # Get the rendered screen from pyte
        rows = list(self.screen.display)
        rendered_lines = [line.rstrip() for line in rows]

        if lines is not None and lines < len(rendered_lines):
            rendered_lines = rendered_lines[-lines:]

        # Filter out empty lines, sentinel lines, and wrapper command echoes
        filtered_lines = []
        for line in rendered_lines:
            # Skip lines that are just sentinel markers
            if SILC_SENTINEL_PATTERN.search(line) and not any(
                c for c in line if c not in " _" and not c.isalnum()
            ):
                continue

            # Skip wrapper command echoes (PowerShell's Write-Host + command structure)
            if "Write-Host '__SILC_" in line or "echo __SILC_" in line:
                continue
            # Skip lines that look like part of the wrapper command being typed
            if "'__SILC_" in line or "__SILC_END_" in line:
                continue

            filtered_lines.append(line)

        # Remove trailing empty lines
        while filtered_lines and not filtered_lines[-1].strip():
            filtered_lines.pop()

        return "\n".join(filtered_lines)

    def resize(self, rows: int, cols: int) -> None:
        """Adjust the PTY and renderer to the new terminal dimensions."""
        rows = max(1, rows)
        cols = max(1, cols)
        self.screen_rows = rows
        self.screen_columns = cols
        self.pty.resize(rows, cols)
        if screens and Stream:
            self.screen = screens.HistoryScreen(cols, rows)
            self.stream = Stream(self.screen)
            self._rehydrate_screen()

    def _rehydrate_screen(self) -> None:
        """Replay the buffered bytes through pyte after a resize."""
        if self.stream is None:
            return
        raw_bytes = self.buffer.get_bytes()
        if not raw_bytes:
            return
        decoded = raw_bytes.decode("utf-8", errors="replace")
        self.stream.feed(decoded)

    def _remove_sentinels(self, text: str) -> str:
        """Remove sentinel marker lines from fallback output."""
        lines = text.split("\n")
        filtered = [line for line in lines if not SILC_SENTINEL_PATTERN.search(line)]
        return "\n".join(filtered)

    async def run_command(self, cmd: str, timeout: int = 60) -> dict:
        if self.run_lock.locked():
            return {
                "error": "Another run command is already executing",
                "status": "busy",
            }

        async with self.run_lock:
            run_token = str(uuid.uuid4())[:8]
            cursor = self.buffer.cursor
            newline = "\r\n" if sys.platform == "win32" else "\n"

            # Reset any partial input state
            await self.pty.write(b"\x03")
            await asyncio.sleep(0.05)

            # Build the wrapped command
            wrapped = self.shell_info.wrap_command(cmd, run_token, newline)

            # Write command directly to PTY bypassing write_input
            # This avoids the echo/line-editing issues with interactive input
            data = (wrapped + newline).encode("utf-8", errors="replace")
            await self.pty.write(data)
            await asyncio.sleep(0.05)

            loop = asyncio.get_running_loop()
            deadline = loop.time() + timeout

            begin_marker = f"__SILC_BEGIN_{run_token}__"
            end_pattern = re.compile(rf"__SILC_END_{run_token}__:(-?\d+)")

            collected = ""
            started = False

            while loop.time() < deadline:
                chunk, cursor = self.buffer.get_since(cursor)
                if not chunk:
                    await asyncio.sleep(0.05)
                    continue

                decoded = chunk.decode("utf-8", errors="replace")
                collected += decoded

                if not started:
                    index = collected.find(begin_marker)
                    if index < 0:
                        # Keep only the tail so a split marker can still be detected.
                        if len(collected) > len(begin_marker):
                            collected = collected[-len(begin_marker) :]
                        await asyncio.sleep(0.05)
                        continue

                    # Drop everything up to and including the BEGIN marker line.
                    after = collected[index + len(begin_marker) :].lstrip("\r")
                    nl = after.find("\n")
                    if nl == -1:
                        # Wait for the rest of the BEGIN line to arrive.
                        collected = after
                        await asyncio.sleep(0.05)
                        continue

                    collected = after[nl + 1 :]
                    started = True

                match = end_pattern.search(collected)
                if match:
                    output_text = collected[: match.start()].rstrip("\r\n")
                    exit_code = int(match.group(1))
                    raw_lines = output_text.replace("\r\n", "\n").split("\n")
                    return {
                        "output": clean_output(raw_lines),
                        "exit_code": exit_code,
                        "status": "completed",
                    }

                await asyncio.sleep(0.05)

            # Timeout: best-effort return what we have collected (BEGIN may or may not be present).
            chunk, _ = self.buffer.get_since(cursor)
            fallback_text = collected
            if chunk:
                fallback_text += chunk.decode("utf-8", errors="replace")
            fallback_lines = fallback_text.replace("\r\n", "\n").split("\n")
            return {
                "output": clean_output(fallback_lines),
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
