"""Session orchestration that ties the PTY, buffer, and API surface together."""

from __future__ import annotations

import asyncio
import os
import re
import sys
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    try:
        from par_term_emu_core_rust import Terminal
    except ImportError:
        Terminal = None
else:
    try:
        from par_term_emu_core_rust import Terminal
    except ImportError:  # pragma: no cover
        Terminal = None

from ..core.cleaner import clean_output
from ..core.raw_buffer import RawByteBuffer
from ..core.pty_manager import create_pty, PTYBase
from ..utils.shell_detect import ShellInfo
from ..utils.persistence import rotate_session_log, write_session_log


OSC_BYTE_PATTERN = re.compile(rb"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
SILC_SENTINEL_PATTERN = re.compile(r"__SILC_(?:BEGIN|END)_\w+__")
HELPER_ECHO_FRAGMENTS = (
    "__silc_exec",
    "__SILC_BEGIN_",
    "__SILC_END_",
    'Write-Host "__SILC_',
    "Invoke-Expression $cmd",
)

# Security: Cap collected buffer to prevent DoS attacks
MAX_COLLECTED_BYTES = 5 * 1024 * 1024  # 5MB
DEFAULT_COMMAND_TIMEOUT = 600  # 10 minutes in seconds

# Buffer and PTY configuration
DEFAULT_BUFFER_SIZE = 65536  # 64KB buffer for PTY output
DEFAULT_READ_SIZE = 4096  # Default read chunk size from PTY
DEFAULT_SCREEN_COLUMNS = 120
DEFAULT_SCREEN_ROWS = 30

# Timing constants (in seconds)
HELPER_INJECTION_DELAY = 0.5  # Delay after injecting helper function
POLL_INTERVAL = 0.05  # Default poll interval for async operations
READ_POLL_INTERVAL = 0.1  # Poll interval when no data available
INTERRUPT_DELAY = 0.5  # Delay after sending interrupt signal
PROMPT_WAIT_TIMEOUT = 2.0  # Timeout for waiting for prompt
GC_INTERVAL_SECONDS = 60  # Garbage collection interval
SESSION_IDLE_TIMEOUT_SECONDS = 1800  # 30 minutes idle timeout
MAX_ACCUMULATOR_SIZE = 4096  # Max size for prompt accumulator

# Log rotation
MAX_LOG_LINES = 1000  # Maximum lines to keep in rotated logs


class SilcSession:
    def __init__(self, port: int, shell_info: ShellInfo, api_token: str | None = None):
        self.port = port
        self.shell_info = shell_info
        self.session_id = str(uuid.uuid4())[:8]
        self.api_token = api_token
        self.pty: PTYBase = create_pty(shell_info.path, os.environ.copy())

        self.buffer = RawByteBuffer(maxlen=DEFAULT_BUFFER_SIZE)
        self.created_at = datetime.utcnow()
        self.last_access = datetime.utcnow()
        self.last_output = datetime.utcnow()

        self.run_lock = asyncio.Lock()
        self.current_run_cmd: str | None = None
        self.input_lock = asyncio.Lock()

        self.screen_columns = DEFAULT_SCREEN_COLUMNS
        self.screen_rows = DEFAULT_SCREEN_ROWS
        self.has_par_term = Terminal is not None
        self.pty.resize(self.screen_rows, self.screen_columns)

        self._read_task: Optional[asyncio.Task[None]] = None
        self._gc_task: Optional[asyncio.Task[None]] = None
        self._closed = False
        self.tui_active = False
        self._helper_injected = False

    async def start(self) -> None:
        if self._read_task is not None:
            return
        self._read_task = asyncio.create_task(self._read_loop())
        await asyncio.sleep(0.5)
        await self._inject_helper()
        self._gc_task = asyncio.create_task(self._garbage_collect())

    async def _read_loop(self) -> None:
        while not self._closed:
            try:
                data = await self.pty.read(4096)
                if data:
                    self.buffer.append(data)
                    self.last_output = datetime.utcnow()
                    write_session_log(
                        self.port, f"OUTPUT: {data.decode('utf-8', errors='replace')}"
                    )
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
            self.rotate_logs()

    async def _ensure_helper_ready(self) -> None:
        if not self._helper_injected:
            await self._inject_helper()

    async def _inject_helper(self) -> None:
        if self._helper_injected:
            return
        helper = self.shell_info.get_helper_function()
        if helper:
            helper_text = helper if helper.endswith("\n") else helper + "\n"
            await self.pty.write(helper_text.encode("utf-8", errors="replace"))
            await self._wait_for_prompt()
            await asyncio.sleep(0.1)
            self.buffer.clear()
        self._helper_injected = True

    async def _wait_for_prompt(self, timeout: float = 2.0) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        cursor = self.buffer.cursor
        accumulator = ""
        pattern = self.shell_info.prompt_pattern

        while loop.time() < deadline:
            chunk, cursor = self.buffer.get_since(cursor)
            if chunk:
                decoded = chunk.decode("utf-8", errors="replace")
                accumulator += decoded
                if len(accumulator) > 4096:
                    accumulator = accumulator[-4096:]
                if pattern.search(accumulator):
                    return
            await asyncio.sleep(0.05)

    async def write_input(self, text: str) -> None:
        async with self.input_lock:
            data = text.encode("utf-8", errors="replace")
            await self.pty.write(data)
            await asyncio.sleep(0.05)
        self.last_access = datetime.utcnow()

    async def clear_screen(self) -> None:
        """Send a clear-screen sequence and refresh the prompt."""
        newline = "\r\n" if sys.platform == "win32" else "\n"
        sequence = f"\x1b[2J\x1b[H{newline}"
        self.buffer.clear()
        await self.pty.write(sequence.encode("utf-8", errors="replace"))
        self.last_access = datetime.utcnow()
        self.last_output = datetime.utcnow()

    async def reset_terminal(self) -> None:
        """Reset the terminal state and clear any buffered output."""
        newline = "\r\n" if sys.platform == "win32" else "\n"
        sequence = f"\x1bc{newline}"
        self.buffer.clear()
        await self.pty.write(sequence.encode("utf-8", errors="replace"))
        self.last_access = datetime.utcnow()
        self.last_output = datetime.utcnow()

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
        Uses stateless rendering: creates fresh terminal, feeds entire buffer, returns result.
        """
        if Terminal:
            term = Terminal(self.screen_columns, self.screen_rows)
            raw_bytes = self.buffer.get_bytes()
            decoded = raw_bytes.decode("utf-8", errors="replace")
            term.process_str(decoded)

            content = term.content()
            rendered_lines = content.split("\n")
            rendered_lines = [line.rstrip() for line in rendered_lines]

            filtered_lines = []
            for line in rendered_lines:
                if any(fragment in line for fragment in HELPER_ECHO_FRAGMENTS):
                    continue
                if SILC_SENTINEL_PATTERN.search(line):
                    continue
                filtered_lines.append(line)

            while filtered_lines and not filtered_lines[-1].strip():
                filtered_lines.pop()

            if lines is not None and lines < len(filtered_lines):
                filtered_lines = filtered_lines[-lines:]

            return "\n".join(filtered_lines)

        snapshot = self.buffer.get_last(lines or 100)
        output = clean_output(snapshot)
        return self._remove_sentinels(output)

    def resize(self, rows: int, cols: int) -> None:
        """Adjust the PTY and renderer to the new terminal dimensions."""
        rows = max(1, rows)
        cols = max(1, cols)
        self.screen_rows = rows
        self.screen_columns = cols
        self.pty.resize(rows, cols)

    def _remove_sentinels(self, text: str) -> str:
        """Remove sentinel marker lines from fallback output."""
        lines = text.split("\n")
        filtered = [line for line in lines if not SILC_SENTINEL_PATTERN.search(line)]
        return "\n".join(filtered)

    def rotate_logs(self) -> None:
            """Rotate session logs to keep size manageable."""
            rotate_session_log(self.port, max_lines=1000)

    async def run_command(self, cmd: str, timeout: int = DEFAULT_COMMAND_TIMEOUT) -> dict:
            # Capture the command being run for lock error reporting

        if self.run_lock.locked():
                return {
                    "error": "Another run command is already executing",
                    "status": "busy",
                    "running_cmd": self.current_run_cmd,
                }

        async with self.run_lock:
            self.current_run_cmd = cmd
            await self._ensure_helper_ready()
            run_token = str(uuid.uuid4())[:8]
            cursor = self.buffer.cursor
            newline = "\r\n" if sys.platform == "win32" else "\n"

            invocation = self.shell_info.build_helper_invocation(cmd, run_token)
            data = (invocation + newline).encode("utf-8", errors="replace")
            await self.pty.write(data)
            await asyncio.sleep(0.05)
            write_session_log(self.port, f"COMMAND: {cmd}")

            loop = asyncio.get_running_loop()
            deadline = loop.time() + timeout

            begin_marker = f"__SILC_BEGIN_{run_token}__".encode("utf-8")
            end_prefix = f"__SILC_END_{run_token}__:".encode("utf-8")

            collected = bytearray()
            started = False

            while loop.time() < deadline:
                chunk, cursor = self.buffer.get_since(cursor)
                if not chunk:
                    await asyncio.sleep(0.05)
                    continue

                collected.extend(chunk)

                # Security: Cap buffer to prevent DoS attacks
                if len(collected) > MAX_COLLECTED_BYTES:
                    await self.pty.write(b"\x03")  # Send Ctrl+C
                    await asyncio.sleep(INTERRUPT_DELAY)
                    self.current_run_cmd = None
                    return {
                        "output": "",
                        "exit_code": -1,
                        "status": "error",
                        "error": f"Command output exceeded {MAX_COLLECTED_BYTES} bytes limit",
                    }

                if not started:
                    begin_index = collected.find(begin_marker)
                    if begin_index < 0:
                        excess = len(collected) - len(begin_marker)
                        if excess > 0:
                            del collected[:excess]
                        await asyncio.sleep(0.05)
                        continue

                    del collected[: begin_index + len(begin_marker)]
                    started = True
                    while collected and collected[0] in (10, 13):
                        del collected[0]

                end_index = collected.find(end_prefix)
                if end_index < 0:
                    await asyncio.sleep(0.05)
                    continue

                tail = collected[end_index + len(end_prefix) :]
                newline_index: int | None = None
                for idx, byte in enumerate(tail):
                    if byte in (10, 13):
                        newline_index = idx
                        break

                if newline_index is None:
                    await asyncio.sleep(0.05)
                    continue

                exit_text = tail[:newline_index].decode("ascii", errors="ignore")
                exit_digits = "".join(
                    ch for ch in exit_text if ch.isdigit() or ch == "-"
                )
                exit_code = 0
                if exit_digits:
                    try:
                        exit_code = int(exit_digits)
                    except ValueError:
                        exit_code = 0

                output_bytes = bytes(collected[:end_index])
                output_bytes = OSC_BYTE_PATTERN.sub(b"", output_bytes)
                output_text = output_bytes.decode("utf-8", errors="replace")
                output_text = output_text.replace("\r\n", "\n").replace("\r", "\n")
                raw_lines = [
                    line
                    for line in output_text.split("\n")
                    if not SILC_SENTINEL_PATTERN.search(line)
                ]

                await asyncio.sleep(0.05)
                self.current_run_cmd = None
                return {
                    "output": clean_output(raw_lines),
                    "exit_code": exit_code,
                    "status": "completed",
                }

            chunk, _ = self.buffer.get_since(cursor)
            fallback_bytes = bytes(collected)
            if chunk:
                fallback_bytes += chunk
            fallback_text = (
                fallback_bytes.decode("utf-8", errors="replace")
                .replace("\r\n", "\n")
                .replace("\r", "\n")
            )
            fallback_lines = [
                line
                for line in fallback_text.split("\\n")
                if not SILC_SENTINEL_PATTERN.search(line)
            ]
            self.current_run_cmd = None
            return {
                "output": clean_output(fallback_lines),
                "status": "timeout",
                "error": f"Command did not complete in {timeout}s",
            }

    def get_status(self) -> dict:
        self.last_access = datetime.utcnow()
        rendered_output = self.get_output(lines=1)
        last_line = ""
        rendered_lines = rendered_output.splitlines()
        if rendered_lines:
            last_line = rendered_lines[-1]
        waiting = bool(last_line and last_line.strip().endswith((":?", "]")))
        return {
            "session_id": self.session_id,
            "port": self.port,
            "alive": self._read_task is not None and not self._read_task.done(),
            "idle_seconds": (datetime.utcnow() - self.last_output).seconds,
            "waiting_for_input": waiting,
            "last_line": last_line,
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
