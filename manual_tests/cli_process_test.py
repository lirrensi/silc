#!/usr/bin/env python3
"""
Simple test script that mimics the full workflow:
1. Open a shell session via the CLI
2. Type some input
3. Close the session
The script uses subprocess to call the local `silc` command-line tool.
"""

import subprocess
import time


def _run(port: int, cmd: str) -> tuple[str, str, int]:
    """
    Execute a silc command.

    Args:
        port: The port number where the server is listening.
        cmd: The command string to pass to silc (e.g. "run \"echo hi\"").

    Returns:
        A tuple of (stdout, stderr, returncode).
    """
    # The CLI is invoked as `python -m silc <port> <subcommand> "<args>"`.
    # Using `run` starts a command in the session, `in` sends text,
    # and `close` terminates the session.
    full_cmd = ["python", "-m", "silc", str(port), cmd]
    result = subprocess.run(
        full_cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip(), result.stderr.strip(), result.returncode


def test_open_type_close():
    """Run a complete open → type → close cycle."""
    PORT = 12345  # Choose an unused port for the test

    # 1️⃣ Open a session by running a command
    out, err, rc = _run(PORT, 'run "echo hello"')
    print(f"[run] stdout: {out}, stderr: {err}, rc: {rc}")
    assert rc == 0, f"run command failed with rc={rc}"

    # 2️⃣ Type some text into the session
    out, err, rc = _run(PORT, 'in "typed text"')
    print(f"[in] stdout: {out}, stderr: {err}, rc: {rc}")
    assert rc == 0, f"in command failed with rc={rc}"

    # 3️⃣ Close the session
    out, err, rc = _run(PORT, "close")
    print(f"[close] stdout: {out}, stderr: {err}, rc: {rc}")
    assert rc == 0, f"close command failed with rc={rc}"


if __name__ == "__main__":
    test_open_type_close()
