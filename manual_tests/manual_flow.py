#!/usr/bin/env python3
"""
Manual flow test – a straightforward script that demonstrates the
complete lifecycle of a silc session using the CLI:

1. Start a session (run a command)
2. Send input to that session
3. Close the session

The script is meant to be executed directly (python -m tests/manual_flow.py)
and prints the raw output of each step, making it easy to see the
behaviour without involving a test framework.
"""

import subprocess
import sys
from pathlib import Path


def _run(port: int, command: str) -> tuple[str, str, int]:
    """Execute a silc sub‑command on the given port."""
    full_cmd = ["python", "-m", "silc", str(port), command]
    result = subprocess.run(
        full_cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip(), result.stderr.strip(), result.returncode


def _find_free_port() -> int:
    """Reserve and return an unused TCP port."""
    sock = subprocess.Popen(
        [
            "python",
            "-c",
            "import socket; s=socket.socket(); s.bind(('',0)); print(s.getsockname()[1]); s.close()",
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    port = int(sock.stdout.read().strip())
    sock.wait()
    return port


def main() -> int:
    PORT = _find_free_port()

    # 1️⃣ Open – run a command inside the session
    print("[run] Starting command 'ls -l' in session")
    out, err, rc = _run(PORT, 'run "ls -l"')
    print(f"   stdout={out!r}, stderr={err!r}, rc={rc}")
    if rc != 0:
        print("Failed to start command", file=sys.stderr)
        return 1

    # Give the command a moment to finish (if it doesn't exit instantly)
    time.sleep(0.5)

    # 2️⃣ Type – send text to the session
    print("[in] Sending 'echo hello world'")
    out, err, rc = _run(PORT, 'in "echo hello world"')
    print(f"   stdout={out!r}, stderr={err!r}, rc={rc}")
    if rc != 0:
        print("Failed to send input", file=sys.stderr)
        return 1

    # 3️⃣ Close – terminate the session
    print("[close] Closing the session")
    out, err, rc = _run(PORT, "close")
    print(f"   stdout={out!r}, stderr={err!r}, rc={rc}")
    if rc != 0:
        print("Failed to close session", file=sys.stderr)
        return 1

    print("\nManual flow completed successfully.")
    return 0


if __name__ == "__main__":
    import time

    sys.exit(main())
