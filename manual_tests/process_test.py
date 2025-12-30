#!/usr/bin/env python3
"""
Standalone script that demonstrates the full workflow:
1. Start a silc server on a random free port
2. Run a command to open a session
3. Send input to that session
4. Close the session

The script is intended to be executed directly (python -m tests/process_test.py)
and prints the raw output of each step, avoiding any test framework.
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
    full_cmd = ["python", "-m", "silc", str(port), command]
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

        # 2️⃣ Open – run a command inside the session
        print('[run] Executing: run "echo hello"')
        out, err, rc = _run(PORT, 'run "echo hello"')
        print(f"   stdout={out!r}, stderr={err!r}, rc={rc}")
        if rc != 0:
            print("Error: run command failed", file=sys.stderr)
            return 1

        # Give the command a moment to finish if it doesn't exit instantly
        time.sleep(0.5)

        # 3️⃣ Type – send text to the session
        print('[in] Sending: in "typed text"')
        out, err, rc = _run(PORT, 'in "typed text"')
        print(f"   stdout={out!r}, stderr={err!r}, rc={rc}")
        if rc != 0:
            print("Error: in command failed", file=sys.stderr)
            return 1

        # 4️⃣ Close – terminate the session
        print("[close] Closing the session")
        out, err, rc = _run(PORT, "close")
        print(f"   stdout={out!r}, stderr={err!r}, rc={rc}")
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
