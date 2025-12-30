
"""Tests for the garbage collection (idle session cleanup) logic."""

import asyncio
import sys
from unittest.mock import patch, MagicMock

import pytest

from silc.core.session import SilcSession
from silc.utils.shell_detect import detect_shell


# Helper to simulate the passing of time
class MockDatetime:
    def __init__(self, base):
        self.base = base

    def utcnow(self):
        # Increment base by 1 second each call for test stepping
        self.base += 1
        return self.base


@pytest.mark.asyncio
async def test_garbage_collection_closes_idle_session(monkeypatch):
    """Session should be closed when idle > 1800s, no TUI, and not locked."""
    shell_info = detect_shell()
    session = SilcSession(port=20002, shell_info=shell_info)

    # Mock PTY and tasks to avoid real I/O
    session.pty = MagicMock()
    session._read_task = MagicMock()
    session._gc_task = MagicMock()

    # Start the session (creates read and gc tasks)
    await session.start()

    # Patch datetime.utcnow to control idle calculation
    base_time = 1000  # arbitrary start timestamp
    mock_dt = MockDatetime(base_time)

    # Mock the close method to track that it gets called
    close_called = False

    async def mock_close():
        nonlocal close_called
        close_called = True

    session.close = mock_close

    # Patch datetime and asyncio.sleep
    monkeypatch.setattr("silc.core.session.datetime", mock_dt)
    monkeypatch.setattr("asyncio.sleep", lambda secs: asyncio.get_event_loop().create_future())

    # Advance time to just over 1800 seconds of idle
    # We need to simulate that last_access is far in the past
    # Set last_access manually via the session's attribute
    session.last_access = mock_dt.base - 1900  # 1900 seconds ago

    # Ensure tui_active is False and run_lock is not locked
    session.tui_active = False
    session.run_lock = asyncio.Lock()
    session.run_lock.locked = MagicMock(return_value=False)

    # Run the GC loop once (it runs in a task, but we can await its first iteration)
    # The GC loop checks the condition each iteration; we manually invoke the check
    # by calling the internal logic
    gc_coro = session._garbage_collect()
    # Advance enough to let the sleep happen and condition be evaluated
    await asyncio.sleep(0.001)  # let the patched sleep yield
    # At this point, the condition should be true and close should have been called
    assert close_called, "Session should be closed when idle exceeds 1800s"


@pytest.mark.asyncio
async def test_garbage_collection_does_not_close_when_active(monkeypatch):
    """Session should remain alive when TUI is active or command is running."""
    shell_info = detect_shell()
    session = SilcSession(port=20003, shell_info=shell_info)

    # Mock PTY and tasks
    session.pty = MagicMock()
    session._read_task = MagicMock()
    session._gc_task = MagicMock()

    await session.start()

    # Use a mock datetime that increments slowly
    base_time = 2000
    mock_dt = MockDatetime(base_time)
    monkeypatch.setattr("silc.core.session.datetime", mock_dt)
    monkeypatch.setattr("asyncio.sleep", lambda secs: asyncio.get_event_loop().create_future())

    # Make the session appear active
    session.tui_active = True  # TUI active resets idle timeout
    session.run_lock = asyncio.Lock()
    session.run_lock.locked = MagicMock(return_value=False)  # not running a command

    # Set last_access far in the past, but because tui_active is True, GC should not close
    session.last_access = base_time - 2000  # 2000s idle, but tui_active overrides

    # Mock close to detect if it was called
    close_called = False

    async def mock_close():
        nonlocal close_called
        close_called = True

    session.close = mock_close

    # Run GC loop briefly
    await session._garbage_collect()
    await asyncio.sleep(0.001)

    # Session should NOT be closed
    assert not close_called, "Session should stay alive while TUI is active"
</parameter>
</write_to_file>
</tool_call>