"""Quick regression check that `winpty` can be imported and a PTY opened."""

import sys

import pytest

from tests._winpty_helpers import (
    collect_output,
    spawn_winpty_process,
    terminate_process,
)


@pytest.mark.skipif(sys.platform != "win32", reason="winpty is Windows-only")
def test_winpty_can_open_pty() -> None:
    """Spawn a lightweight PTY session and verify we get expected output."""

    process = spawn_winpty_process('cmd.exe /k "echo pywinpty ok"')
    try:
        assert "pywinpty ok" in collect_output(process, "pywinpty ok", timeout=10.0)
        process.write("echo followup ok\r\n")
        assert "followup ok" in collect_output(process, "followup ok", timeout=5.0)
    finally:
        terminate_process(process)
