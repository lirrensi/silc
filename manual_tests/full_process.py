#!/usr/bin/env python3
"""
Integration‑style test that demonstrates the full workflow:
1. Start a silc server on an ephemeral port
2. Open a session (run a command)
3. Send input to the session
4. Close the session
The script is intentionally simple – it just calls the `silc` CLI via subprocess
and prints the raw output, so it can be used as a standalone executable
instead of a pytest test case.
"""

import subprocess
import time
import socket
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def _free_port() -> int:
    """Allocate and return an unused TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _run(port: int, cmd: str) -> tuple[str, str, int]:
    """
    Execute a silc sub‑command.

    Args:
        port: Port where the server is listening.
        cmd: Command string, e.g. "run \"echo hi\"", "in \"text\"", "close".

    Returns:
        (stdout, stderr, returncode)
    """
    full_cmd = ["python", "-m", "silc", str(port), cmd]
    result = subprocess.run(
        full_cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip(), result.stderr.strip(), result.returncode


def _wait_for_server(port: int, timeout: float = 5.0) -> None:
    """Block until the server accepts connections or timeout expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return  # success
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"Server did not start on port {port} within {timeout}s")


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------
def main() -> int:
    PORT = _free_port()

    # 1️⃣ Start the silc server (background subprocess)
    server_proc = subprocess.Popen(
        ["python", "-m", "silc", "start", str(PORT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_server(PORT)

        # 2️⃣ Open a session by running a command
        print('[run] Executing: run "echo hello"')
        out, err, rc = _run(PORT, 'run "echo hello"')
        print(f"   stdout: {out!r}, stderr: {err!r}, rc: {rc}")
        if rc != 0:
            print("Error: run command failed", file=sys.stderr)
            return 1

        # 3️⃣ Type some text into the session
        print('[in] Sending: in "typed text"')
        out, err, rc = _run(PORT, 'in "typed text"')
        print(f"   stdout: {out!r}, stderr: {err!r}, rc: {rc}")
        if rc != 0:
            print("Error: in command failed", file=sys.stderr)
            return 1

        # 4️⃣ Close the session
        print("[close] Closing session")
        out, err, rc = _run(PORT, "close")
        print(f"   stdout: {out!r}, stderr: {err!r}, rc: {rc}")
        if rc != 0:
            print("Error: close command failed", file=sys.stderr)
            return 1

    finally:
        # Ensure the server process is terminated
        server_proc.terminate()
        server_proc.wait()

    print("\nAll steps completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
