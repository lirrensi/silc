#!/usr/bin/env python3
"""
Minimal script that runs the full open → type → close workflow using the silc CLI.
Execute with: python -m tests/new_process_test.py
"""

import socket
import subprocess
import sys
import time


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _run(port: int, cmd: str) -> tuple[str, str, int]:
    result = subprocess.run(
        ["python", "-m", "silc", str(port), cmd],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip(), result.stderr.strip(), result.returncode


def _wait_for_server(port: int, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"Server did not start on port {port}")


def main() -> int:
    PORT = _free_port()
    server_proc = subprocess.Popen(
        ["python", "-m", "silc", "start", str(PORT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_server(PORT)
        # Open session
        out, err, rc = _run(PORT, 'run "echo start"')
        print(f"[run] rc={rc}")
        if rc:
            return 1
        time.sleep(0.5)
        # Type input
        out, err, rc = _run(PORT, 'in "hello world"')
        print(f"[in] rc={rc}")
        if rc:
            return 1
        # Close session
        out, err, rc = _run(PORT, "close")
        print(f"[close] rc={rc}")
        if rc:
            return 1
    finally:
        server_proc.terminate()
        server_proc.wait()
    print("Workflow completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
