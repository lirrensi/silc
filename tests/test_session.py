"""Tests that exercise the SILC shell lifecycle."""

import asyncio
import sys
import uuid

import pytest

from silc.core.session import SilcSession
from silc.utils.shell_detect import detect_shell


class _BatchBuffer:
    def __init__(self, batches):
        self.batches = batches
        self.call_index = 0
        self.cursor = 0

    def get_since(self, cursor: int):
        if self.call_index >= len(self.batches):
            return [], cursor
        batch = self.batches[self.call_index]
        self.call_index += 1
        self.cursor = cursor + len(batch)
        return batch, self.cursor


if sys.platform == "win32":
    pytest.importorskip("winpty", reason="pywinpty is required to run PTY tests on Windows")


async def _wait_for_output(session: SilcSession, text: str, timeout: float = 3.0) -> str:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        output = session.get_output(lines=50)
        if text in output:
            return output
        await asyncio.sleep(0.1)
    pytest.fail(f"Timed out waiting for {text!r} in session output")


@pytest.mark.asyncio
async def test_session_full_lifecycle() -> None:
    """Create a session, write input, run commands, and validate buffer/cleanup behavior."""
    shell_info = detect_shell()
    session = SilcSession(port=20001, shell_info=shell_info)

    await session.start()
    try:
        await session.write_input("echo lifecycle test\n")
        lifecycle_output = await _wait_for_output(session, "lifecycle test")
        assert "lifecycle test" in lifecycle_output

        await session.clear_buffer()
        assert session.buffer.get_last(1) == []

        run_result = await session.run_command("echo cycle", timeout=10)
        assert run_result["status"] == "completed"
        assert run_result["exit_code"] == 0
        assert "cycle" in run_result["output"]

        status = session.get_status()
        assert status["alive"]
        assert status["port"] == 20001
        assert not status["run_locked"]

        await session.write_input("echo buffer alive\n")
        buffer_output = await _wait_for_output(session, "buffer alive")
        assert "buffer alive" in buffer_output

        await session.interrupt()
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_run_command_ignores_prompt_line(monkeypatch) -> None:
    fixed_uuid = uuid.UUID("00000000-0000-0000-0000-000000000000")
    monkeypatch.setattr(uuid, "uuid4", lambda: fixed_uuid)
    sentinel = "__SILC_DONE_00000000__"
    prompt_line = f'PS Test> echo "{sentinel}:$?"'
    completion_line = f"{sentinel}:0"
    command_output = "desktop-ctsh072\\rx"

    shell_info = detect_shell()
    session = SilcSession(port=20002, shell_info=shell_info)
    session.buffer = _BatchBuffer([[prompt_line], [command_output], [completion_line]])

    async def noop_write(_text: str) -> None:
        return

    session.write_input = noop_write
    try:
        result = await session.run_command("ignore", timeout=3)
        assert result["status"] == "completed"
        assert result["exit_code"] == 0
        assert command_output in result["output"]
        assert prompt_line not in result["output"]
    finally:
        await session.close()
