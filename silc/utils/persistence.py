"""Silc data directories and persistence helpers."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


def _create_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        return True
    except OSError:
        return False


def _is_writable_directory(path: Path) -> bool:
    if not _create_dir(path):
        return False
    test_file = path / ".silc_write_test"
    try:
        test_file.write_text("", encoding="utf-8")
        test_file.unlink()
        return True
    except OSError:
        return False


def _resolve_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", "")) / "silc"
    else:
        base = Path.home() / ".silc"

    if _is_writable_directory(base):
        return base

    fallback = Path(tempfile.gettempdir()) / "silc"
    if _is_writable_directory(fallback):
        return fallback

    return fallback


DATA_DIR = _resolve_data_dir()
LOGS_DIR = DATA_DIR / "logs"
if not _is_writable_directory(LOGS_DIR):
    LOGS_DIR = DATA_DIR
DAEMON_LOG = LOGS_DIR / "daemon.log"


def get_session_log_path(port: int) -> Path:
    """Get log file path for a session."""
    return LOGS_DIR / f"session_{port}.log"


def rotate_daemon_log(max_lines: int = 1000) -> None:
    """Keep only last N lines in daemon log."""
    if not DAEMON_LOG.exists():
        return
    lines = DAEMON_LOG.read_text(encoding="utf-8").splitlines()
    if len(lines) > max_lines:
        DAEMON_LOG.write_text("\n".join(lines[-max_lines:]) + "\n", encoding="utf-8")


def cleanup_session_log(port: int) -> None:
    """Delete session log file."""
    log_path = get_session_log_path(port)
    try:
        if log_path.exists():
            log_path.unlink()
    except OSError:
        pass


def write_daemon_log(message: str) -> None:
    """Append to daemon log."""
    import datetime

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(DAEMON_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except OSError:
        pass


def write_session_log(port: int, message: str) -> None:
    """Append to session log."""
    import datetime

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_path = get_session_log_path(port)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except OSError:
        pass


def rotate_session_log(port: int, max_lines: int = 1000) -> None:
    """Keep only last N lines in session log."""
    log_path = get_session_log_path(port)
    if not log_path.exists():
        return
    lines = log_path.read_text(encoding="utf-8").splitlines()
    if len(lines) > max_lines:
        log_path.write_text("\n".join(lines[-max_lines:]) + "\n", encoding="utf-8")


def read_session_log(port: int, tail_lines: int | None = None) -> str:
    """Read session log file."""
    log_path = get_session_log_path(port)
    if not log_path.exists():
        return ""
    lines = log_path.read_text(encoding="utf-8").splitlines()
    if tail_lines:
        lines = lines[-tail_lines:]
    return "\n".join(lines)


__all__ = [
    "DATA_DIR",
    "LOGS_DIR",
    "DAEMON_LOG",
    "get_session_log_path",
    "rotate_daemon_log",
    "cleanup_session_log",
    "write_daemon_log",
    "write_session_log",
    "rotate_session_log",
    "read_session_log",
]
