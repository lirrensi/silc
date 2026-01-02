"""PID file management for Silc daemon."""

from __future__ import annotations

import sys

from silc.utils.persistence import DATA_DIR

PID_FILE = DATA_DIR / "daemon.pid"


def write_pidfile(pid: int) -> None:
    """Write daemon PID to file."""
    try:
        PID_FILE.write_text(str(pid), encoding="utf-8")
    except OSError:
        pass


def read_pidfile() -> int | None:
    """Read daemon PID from file. Returns None if not found."""
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except (ValueError, IOError):
        return None


def remove_pidfile() -> None:
    """Remove PID file."""
    try:
        if PID_FILE.exists():
            PID_FILE.unlink()
    except OSError:
        pass


def is_daemon_running() -> bool:
    """Check if daemon process is running.

    Notes:
        This is intentionally lightweight (PID file + psutil). The CLI may do an
        additional HTTP probe when it needs to confirm responsiveness.
    """

    import psutil

    pid = read_pidfile()
    if pid is None:
        return False
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return False

    # pid_exists() can be true for recycled PIDs; still treat it as running if we
    # can resolve the process.
    return proc.is_running()


def _pids_listening_on_port(port: int) -> set[int]:
    """Best-effort lookup of PIDs that LISTEN on localhost ports.

    Used as a fallback when the PID file is stale/missing.
    """

    import psutil

    pids: set[int] = set()
    try:
        conns = psutil.net_connections(kind="inet")
    except Exception:
        return pids

    for conn in conns:
        try:
            if not conn.laddr:
                continue
            if conn.status != psutil.CONN_LISTEN:
                continue
            if conn.laddr.port != port:
                continue
            if conn.pid:
                pids.add(conn.pid)
        except Exception:
            continue

    return pids


def _terminate_process_tree(pid: int, *, timeout: float, force: bool) -> bool:
    import psutil

    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return False

    # Kill children first (common with uvicorn + executor threads / subprocesses)
    try:
        children = proc.children(recursive=True)
    except Exception:
        children = []

    for child in children:
        try:
            child.terminate()
        except psutil.NoSuchProcess:
            pass
        except Exception:
            pass

    try:
        proc.terminate()
    except psutil.NoSuchProcess:
        return True
    except Exception:
        pass

    gone: list[psutil.Process] = []
    alive: list[psutil.Process] = []
    try:
        gone, alive = psutil.wait_procs([proc, *children], timeout=timeout)
    except Exception:
        alive = [proc, *children]

    if not alive:
        return True

    if not force:
        return False

    for p in alive:
        try:
            p.kill()
        except psutil.NoSuchProcess:
            pass
        except Exception:
            pass

    try:
        psutil.wait_procs(alive, timeout=max(0.5, timeout))
    except Exception:
        pass

    return True


def kill_daemon(
    *, timeout: float = 2.0, force: bool = True, port: int | None = None
) -> bool:
    """Kill daemon process.

    - Prefer PID file.
    - Optionally also kill anything listening on the daemon port (fallback for
      stale PID files / orphaned processes).
    """

    pid = read_pidfile()
    pids: set[int] = set()
    if pid is not None:
        pids.add(pid)
    if port is not None:
        pids |= _pids_listening_on_port(port)

    killed_any = False
    for target_pid in sorted(pids):
        killed_any |= _terminate_process_tree(target_pid, timeout=timeout, force=force)

    # Always remove PID file so subsequent `start` can recover.
    remove_pidfile()

    return killed_any


__all__ = [
    "write_pidfile",
    "read_pidfile",
    "remove_pidfile",
    "is_daemon_running",
    "kill_daemon",
]
