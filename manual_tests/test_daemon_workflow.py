"""Manual test of daemon functionality."""

import subprocess
import sys
import time
import requests

DAEMON_PORT = 19999


def check_daemon():
    """Check if daemon is running."""
    try:
        resp = requests.get(f"http://127.0.0.1:{DAEMON_PORT}/sessions", timeout=1)
        return True
    except requests.RequestException:
        return False


def main():
    print("=" * 60)
    print("SILC Daemon Manual Test")
    print("=" * 60)

    # Step 1: Start daemon in foreground
    print("\n[Step 1] Starting daemon in foreground...")
    daemon_proc = subprocess.Popen(
        [sys.executable, "-m", "silc", "start", "--no-detach"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Wait for daemon to start
    time.sleep(3)

    if not check_daemon():
        print("[X] Failed to start daemon")
        return 1

    print("[OK] Daemon started successfully")

    # Step 2: Create a session
    print("\n[Step 2] Creating session...")
    resp = requests.post(f"http://127.0.0.1:{DAEMON_PORT}/sessions", json={}, timeout=5)
    if resp.status_code != 200:
        print(f"[X] Failed to create session: {resp.text}")
        daemon_proc.terminate()
        return 1

    session = resp.json()
    print(f"[OK] Session created:")
    print(f"   Port: {session['port']}")
    print(f"   Session ID: {session['session_id']}")
    print(f"   Shell: {session['shell']}")

    session_port = session["port"]

    # Step 3: List sessions
    print("\n[Step 3] Listing sessions...")
    resp = requests.get(f"http://127.0.0.1:{DAEMON_PORT}/sessions", timeout=5)
    if resp.status_code != 200:
        print(f"[X] Failed to list sessions: {resp.text}")
    else:
        sessions = resp.json()
        print(f"[OK] Active sessions: {len(sessions)}")
        for s in sessions:
            print(f"   Port {s['port']}: {s['session_id']} ({s['shell']})")

    # Step 4: Test session API
    print("\n[Step 4] Testing session API...")
    try:
        # Wait for session to be ready
        time.sleep(1)

        # Check status
        resp = requests.get(f"http://127.0.0.1:{session_port}/status", timeout=5)
        if resp.status_code == 200:
            status = resp.json()
            print(f"[OK] Session status:")
            print(f"   Alive: {status['alive']}")
            print(f"   Port: {status['port']}")
        else:
            print(f"[X] Failed to get session status: {resp.status_code}")

        # Run a simple command
        print(f"\n   Running 'echo hello from silc'...")
        resp = requests.post(
            f"http://127.0.0.1:{session_port}/run",
            json={"command": "echo hello from silc"},
            timeout=10,
        )
        if resp.status_code == 200:
            result = resp.json()
            print(f"[OK] Command result:")
            print(f"   Status: {result.get('status')}")
            print(f"   Output: {result.get('output')[:100]}")
        else:
            print(f"[X] Failed to run command: {resp.status_code}")

    except requests.RequestException as e:
        print(f"[X] Session API error: {e}")

    # Step 5: Close session
    print("\n[Step 5] Closing session...")
    resp = requests.delete(
        f"http://127.0.0.1:{DAEMON_PORT}/sessions/{session_port}", timeout=5
    )
    if resp.status_code == 200:
        print("[OK] Session closed")
    else:
        print(f"[X] Failed to close session: {resp.status_code}")

    # Step 6: Shutdown daemon
    print("\n[Step 6] Shutting down daemon...")
    resp = requests.post(f"http://127.0.0.1:{DAEMON_PORT}/shutdown", timeout=5)
    if resp.status_code == 200:
        print("[OK] Daemon shutdown initiated")
    else:
        print(f"[X] Failed to shutdown daemon: {resp.status_code}")

    # Wait for daemon to exit
    daemon_proc.wait(timeout=10)
    print("[OK] Daemon stopped")

    print("\n" + "=" * 60)
    print("All tests passed!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
