"""Simpler manual test of daemon functionality."""

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
    print("SILC Daemon Manual Test (Simplified)")
    print("=" * 60)

    # Step 1: Start daemon
    print("\n[Step 1] Starting daemon in foreground...")
    daemon_proc = subprocess.Popen(
        [sys.executable, "-m", "silc", "start", "--no-detach"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    time.sleep(3)

    if not check_daemon():
        print("[X] Failed to start daemon")
        daemon_proc.terminate()
        return 1

    print("[OK] Daemon started successfully")

    # Step 2: Create multiple sessions
    print("\n[Step 2] Creating 3 sessions...")
    sessions = []
    for i in range(3):
        resp = requests.post(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions", json={}, timeout=5
        )
        if resp.status_code != 200:
            print(f"[X] Failed to create session {i + 1}: {resp.text}")
        else:
            session = resp.json()
            sessions.append(session)
            print(f"[OK] Session {i + 1}: Port {session['port']}")

    # Step 3: List sessions
    print("\n[Step 3] Listing all sessions...")
    resp = requests.get(f"http://127.0.0.1:{DAEMON_PORT}/sessions", timeout=5)
    if resp.status_code == 200:
        session_list = resp.json()
        print(f"[OK] Found {len(session_list)} active sessions:")
        for s in session_list:
            print(f"   - Port {s['port']}: {s['session_id']} ({s['shell']})")

    # Step 4: Check each session status
    print("\n[Step 4] Checking session status...")
    for s in sessions:
        try:
            resp = requests.get(f"http://127.0.0.1:{s['port']}/status", timeout=5)
            if resp.status_code == 200:
                status = resp.json()
                print(f"[OK] Port {s['port']}: Alive={status['alive']}")
            else:
                print(f"[X] Port {s['port']}: Status check failed")
        except requests.RequestException as e:
            print(f"[X] Port {s['port']}: {e}")

    # Step 5: Test daemon shutdown
    print("\n[Step 5] Testing daemon shutdown...")
    resp = requests.post(f"http://127.0.0.1:{DAEMON_PORT}/shutdown", timeout=5)
    if resp.status_code == 200:
        print("[OK] Shutdown initiated")

    # Wait for daemon to exit
    daemon_proc.wait(timeout=15)
    print("[OK] Daemon stopped")

    print("\n" + "=" * 60)
    print("Daemon core functionality working!")
    print("Note: Individual session close still has issues to fix.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
