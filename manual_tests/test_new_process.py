#!/usr/bin/env python3
"""
Standalone script that demonstrates the full open → type → close workflow
using the silc CLI. Execute with `python -m tests/new_process_tests.py`.

The script:
1. Finds an unused TCP port.
2. Starts the silc server on that port.
3. Runs a command to open a session.
4. Sends input to the session.
5. Closes the session.

All step outputs are printed for easy observation.
"""

import socket
import subprocess
import sys
import time


def _free_port() -> int:
    """Allocate and return an unused TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _run(port: int, command: str) -> tuple[str, str, int]:
    """Execute a silc sub‑command on the given port."""
    result = subprocess.run(
        ["python", "-m", "silc", str(port), command],
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
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"Server did not start on port {port} within {timeout}s")


def main() -> int:
    PORT = _free_port()

    # Start silc server in the background
    server_proc = subprocess.Popen(
        ["python", "-m", "silc", "start", str(PORT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_server(PORT)

        # 1️⃣ Open a session by running a command
        print('[run] Executing: run "echo hello"')
        out, err, rc = _run(PORT, 'run "echo hello"')
        print(f"   stdout={out!r}, stderr={err!r}, rc={rc}")
        if rc != 0:
            print("Error: run command failed", file=sys.stderr)
            return 1

        # Give the command a moment to finish if it doesn't exit instantly
        time.sleep(0.5)

        # 2️⃣ Type some input into the session
        print('[in] Sending: in "typed text"')
        out, err, rc = _run(PORT, 'in "typed text"')
        print(f"   stdout={out!r}, stderr={err!r}, rc={rc}")
        if rc != 0:
            print("Error: in command failed", file=sys.stderr)
            return 1

        # 3️⃣ Close the session
        print("[close] Closing session")
        out, err, rc = _run(PORT, "close")
        print(f"   stdout={out!r}, stderr={err!r}, rc={rc}")
        if rc != 0:
            print("Error: close command failed", file=sys.stderr)
            return 1

    finally:
        # Ensure the server process is terminated
        server_proc.terminate()
        server_proc.wait()

    print("\nFull workflow completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
