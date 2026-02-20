#!/usr/bin/env python3
"""
Simple test script that mimics the full workflow:
1. Open a shell session via the CLI
2. Type some input
3. Close the session
The script uses subprocess to call the local `silc` command-line tool.
"""

import subprocess
import sys
import time


def _run(
    port: int, cmd: tuple[str, ...], timeout: float = 15.0
) -> tuple[str, str, int]:
    """
    Execute a silc command.

    Args:
        port: The port number where the server is listening.
        cmd: The command tuple to pass to silc (e.g. ("run", "echo", "hi")).
        timeout: Seconds to wait for the CLI command to complete.

    Returns:
        A tuple of (stdout, stderr, returncode).
    """
    full_cmd = [sys.executable, "-m", "silc", str(port), *cmd]
    result = subprocess.run(
        full_cmd,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    return result.stdout.strip(), result.stderr.strip(), result.returncode


def _shutdown_daemon() -> None:
    subprocess.run(
        [sys.executable, "-m", "silc", "shutdown"],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )


def test_open_type_close():
    """Run a complete open → type → close cycle."""
    _shutdown_daemon()
    PORT = 12345  # Choose an unused port for the test

    try:
        # 1️⃣ Open a session by running a command (allow a longer timeout for startup)
        out, err, rc = _run(PORT, ("run", "echo", "hello"), timeout=20)
        print(f"[run] stdout: {out}, stderr: {err}, rc: {rc}")
        assert rc == 0, f"run command failed with rc={rc}"
        time.sleep(10)  # give the shell time to settle before piping input

        # 2️⃣ Type some text into the session
        out, err, rc = _run(PORT, ("in", "typed text"), timeout=5)
        print(f"[in] stdout: {out}, stderr: {err}, rc: {rc}")
        assert rc == 0, f"in command failed with rc={rc}"

        # 3️⃣ Close the session
        out, err, rc = _run(PORT, ("close",), timeout=5)
        print(f"[close] stdout: {out}, stderr: {err}, rc: {rc}")
        assert rc == 0, f"close command failed with rc={rc}"
    finally:
        _shutdown_daemon()


if __name__ == "__main__":
    test_open_type_close()
