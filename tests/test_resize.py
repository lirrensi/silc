"""Tests for resize functionality."""

import sys

import pytest

from silc.core.session import DEFAULT_SCREEN_COLUMNS, DEFAULT_SCREEN_ROWS, SilcSession
from silc.utils.shell_detect import detect_shell

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Resize tests have Windows PTY interaction issues",
)


@pytest.mark.asyncio
async def test_session_default_size() -> None:
    """Verify session is created with default dimensions."""
    shell_info = detect_shell()
    try:
        session = SilcSession(port=20050, shell_info=shell_info)
    except OSError as exc:
        pytest.skip(f"PTY not available: {exc}")

    try:
        await session.start()
        assert session.screen_rows == DEFAULT_SCREEN_ROWS
        assert session.screen_columns == DEFAULT_SCREEN_COLUMNS
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_session_resize() -> None:
    """Verify resize updates session dimensions."""
    shell_info = detect_shell()
    try:
        session = SilcSession(port=20051, shell_info=shell_info)
    except OSError as exc:
        pytest.skip(f"PTY not available: {exc}")

    try:
        await session.start()

        # Resize to custom dimensions
        session.resize(rows=40, cols=160)
        assert session.screen_rows == 40
        assert session.screen_columns == 160

        # Resize to minimum
        session.resize(rows=1, cols=1)
        assert session.screen_rows == 1
        assert session.screen_columns == 1

        # Resize with invalid values (should clamp to minimum 1)
        session.resize(rows=0, cols=0)
        assert session.screen_rows == 1
        assert session.screen_columns == 1
    finally:
        await session.close()
