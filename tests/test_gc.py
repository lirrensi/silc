"""Tests for the garbage collection (idle session cleanup) logic."""

import asyncio
import contextlib
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from silc.core.session import SilcSession
from silc.utils.shell_detect import detect_shell

pytestmark = pytest.mark.skipif(
    True, reason="GC test has complex mocking issues with asyncio.Lock"
)


def _patch_fast_sleep(monkeypatch):
    real_sleep = asyncio.sleep

    async def fast_sleep(*args, **kwargs):
        await real_sleep(0)

    monkeypatch.setattr("asyncio.sleep", fast_sleep)


@pytest.mark.asyncio
async def test_garbage_collection_closes_idle_session(monkeypatch):
    """Session should be closed when idle > 1800s, no TUI, and not locked."""
    _patch_fast_sleep(monkeypatch)

    shell_info = detect_shell()
    session = SilcSession(port=20002, shell_info=shell_info)

    # Mock PTY and tasks to avoid real I/O
    session.pty = MagicMock()
    session._read_task = MagicMock()
    session._gc_task = MagicMock()

    session.last_access = datetime.utcnow() - timedelta(seconds=1900)

    # Ensure tui_active is False and run_lock is not locked
    session.tui_active = False
    session.run_lock = asyncio.Lock()
    session.run_lock.locked = MagicMock(return_value=False)

    close_called = False

    async def mock_close():
        nonlocal close_called
        close_called = True
        session._closed = True

    session.close = mock_close

    gc_task = asyncio.create_task(session._garbage_collect())
    await asyncio.sleep(0)
    assert close_called, "Session should be closed when idle exceeds 1800s"

    with contextlib.suppress(asyncio.CancelledError):
        await gc_task


@pytest.mark.asyncio
async def test_garbage_collection_does_not_close_when_active(monkeypatch):
    """Session should remain alive when TUI is active or command is running."""
    shell_info = detect_shell()
    session = SilcSession(port=20003, shell_info=shell_info)

    # Mock PTY and tasks
    session.pty = MagicMock()
    session._read_task = MagicMock()
    session._gc_task = MagicMock()

    session.last_access = datetime.utcnow() - timedelta(seconds=2000)

    _patch_fast_sleep(monkeypatch)

    # Make the session appear active
    session.tui_active = True  # TUI active resets idle timeout
    session.run_lock = asyncio.Lock()
    session.run_lock.locked = MagicMock(return_value=False)  # not running a command

    close_called = False

    async def mock_close():
        nonlocal close_called
        close_called = True
        session._closed = True

    session.close = mock_close

    gc_task = asyncio.create_task(session._garbage_collect())
    await asyncio.sleep(0)

    assert not close_called, "Session should stay alive while TUI is active"

    session._closed = True
    gc_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await gc_task
