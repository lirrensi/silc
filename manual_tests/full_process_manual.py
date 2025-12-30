#!/usr/bin/env python3
"""
Manual script that demonstrates the full open → type → close workflow
using the silc CLI. Run with: python -m tests/full_process_manual.py
"""

import socket
import subprocess
import sys
import time


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _run(port: int, command: str) -> tuple[str, str, int]:
    result = subprocess.run(
        ["python", "-m", "silc", str(port), command],
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
    raise TimeoutError(f"Server did not start on port {port} within {timeout}s")


def main() -> int:
    PORT = _free_port()
    server_proc = subprocess.Popen(
        ["python", "-m", "silc", "start", str(PORT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_server(PORT)
        print('[run] Executing: run "echo hello"')
        out, err, rc = _run(PORT, 'run "echo hello"')
        print(f"   stdout={out!r}, stderr={err!r}, rc={rc}")
        if rc != 0:
            print("Error: run command failed", file=sys.stderr)
            return 1
        time.sleep(0.5)
        print('[in] Sending: in "test input"')
        out, err, rc = _run(PORT, 'in "test input"')
        print(f"   stdout={out!r}, stderr={err!r}, rc={rc}")
        if rc != 0:
            print("Error: in command failed", file=sys.stderr)
            return 1
        print("[close] Closing session")
        out, err, rc = _run(PORT, "close")
        print(f"   stdout={out!r}, stderr={err!r}, rc={rc}")
        if rc != 0:
            print("Error: close command failed", file=sys.stderr)
            return 1
    finally:
        server_proc.terminate()
        server_proc.wait()
    print("\nFull process completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
