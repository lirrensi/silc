"""Silc data directories and persistence helpers."""

# FILE: silc/utils/persistence.py
# PURPOSE: Own daemon/session persistence paths, log files, and one-shot snapshot storage helpers.
# OWNS: Data directory resolution, log rotation, sessions.json persistence, and raw snapshot file I/O.
# EXPORTS: Snapshot helpers, log helpers, and sessions.json helpers used by the daemon and CLI.
# DOCS: agent_chat/plan_dormant_resurrect_snapshots_2026-04-06.md, docs/arch_daemon.md

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from silc.config import get_config


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
    """Resolve default data directory if not configured."""
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


def get_data_dir() -> Path:
    """Get the data directory from config or resolve default."""
    config = get_config()
    if config.paths.data_dir:
        return config.paths.data_dir
    return _resolve_data_dir()


def get_logs_dir() -> Path:
    """Get the logs directory from config or resolve default."""
    config = get_config()
    if config.paths.log_dir:
        return config.paths.log_dir
    return get_data_dir() / "logs"


DATA_DIR = get_data_dir()
LOGS_DIR = get_logs_dir()
if not _is_writable_directory(LOGS_DIR):
    LOGS_DIR = DATA_DIR
DAEMON_LOG = LOGS_DIR / "daemon.log"


def get_session_log_path(port: int) -> Path:
    """Get log file path for a session."""
    return LOGS_DIR / f"session_{port}.log"


def rotate_daemon_log(max_lines: int | None = None) -> None:
    """Keep only last N lines in daemon log.

    Args:
        max_lines: Maximum number of lines to keep. If None, uses config default.
    """
    if max_lines is None:
        from silc.config import get_config

        max_lines = get_config().logging.max_log_lines

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


def remove_session_artifacts() -> None:
    """Delete persisted session state and session-specific logs."""

    try:
        if SESSIONS_FILE.exists():
            SESSIONS_FILE.unlink()
    except OSError:
        pass

    try:
        if SNAPSHOTS_DIR.exists():
            shutil.rmtree(SNAPSHOTS_DIR, ignore_errors=True)
    except OSError:
        pass

    try:
        if LOGS_DIR.exists():
            for path in LOGS_DIR.glob("session_*.log"):
                try:
                    path.unlink()
                except OSError:
                    pass
    except OSError:
        pass


def purge_silc_data() -> None:
    """Delete all SILC data directories and artifacts."""

    from silc.config import get_config

    config = get_config()
    paths = []
    if config.paths.data_dir is not None:
        paths.append(config.paths.data_dir)
    if config.paths.log_dir is not None:
        paths.append(config.paths.log_dir)

    seen: set[Path] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        try:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.exists():
                path.unlink()
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


def rotate_session_log(port: int, max_lines: int | None = None) -> None:
    """Keep only last N lines in session log.

    Args:
        port: Session port number
        max_lines: Maximum number of lines to keep. If None, uses config default.
    """
    if max_lines is None:
        from silc.config import get_config

        max_lines = get_config().logging.max_log_lines

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


# Session persistence for resurrect feature
SESSIONS_FILE = DATA_DIR / "sessions.json"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"


_SESSION_SNAPSHOT_RE = re.compile(r"^session_(?P<session_id>[^\\/]+)\.bin$")


def get_session_snapshot_path(session_id: str) -> Path:
    """Return the snapshot file path for one session id."""

    return SNAPSHOTS_DIR / f"session_{session_id}.bin"


def write_session_snapshot(session_id: str, data: bytes) -> None:
    """Write a raw session snapshot atomically when possible."""

    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_path = get_session_snapshot_path(session_id)
    temp_file: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            delete=False,
            dir=SNAPSHOTS_DIR,
            prefix=".session_",
            suffix=".tmp",
        ) as handle:
            handle.write(data)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
            temp_file = Path(handle.name)
        temp_file.replace(snapshot_path)
    except OSError:
        snapshot_path.write_bytes(data)
    finally:
        if temp_file is not None:
            try:
                if temp_file.exists() and temp_file != snapshot_path:
                    temp_file.unlink()
            except OSError:
                pass


def read_session_snapshot(session_id: str) -> bytes:
    """Read a raw session snapshot or return empty bytes when unavailable."""

    snapshot_path = get_session_snapshot_path(session_id)
    try:
        return snapshot_path.read_bytes()
    except OSError:
        return b""


def remove_session_snapshot(session_id: str) -> None:
    """Delete one session snapshot if present."""

    snapshot_path = get_session_snapshot_path(session_id)
    try:
        snapshot_path.unlink()
    except OSError:
        pass


def list_session_snapshot_ids() -> set[str]:
    """List session ids that currently have snapshot files."""

    if not SNAPSHOTS_DIR.exists():
        return set()

    session_ids: set[str] = set()
    for path in SNAPSHOTS_DIR.iterdir():
        if not path.is_file():
            continue
        match = _SESSION_SNAPSHOT_RE.match(path.name)
        if match:
            session_ids.add(match.group("session_id"))
    return session_ids


def garbage_collect_session_snapshots(valid_session_ids: set[str]) -> list[str]:
    """Delete orphan snapshot files and return removed session ids."""

    if not SNAPSHOTS_DIR.exists():
        return []

    removed: list[str] = []
    for path in SNAPSHOTS_DIR.iterdir():
        if not path.is_file():
            continue
        match = _SESSION_SNAPSHOT_RE.match(path.name)
        if not match:
            continue
        session_id = match.group("session_id")
        if session_id in valid_session_ids:
            continue
        try:
            path.unlink()
            removed.append(session_id)
        except OSError:
            pass
    return removed


def read_sessions_json() -> list[dict]:
    """Read sessions.json, return empty list if not exists or invalid."""
    if not SESSIONS_FILE.exists():
        return []
    try:
        content = SESSIONS_FILE.read_text(encoding="utf-8")
        data = json.loads(content)
        return data.get("sessions", [])
    except (json.JSONDecodeError, OSError):
        return []


def write_sessions_json(sessions: list[dict]) -> None:
    """Write sessions list to sessions.json atomically."""
    SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {"sessions": sessions}
    # Write to temp file then rename for atomicity
    temp_file = SESSIONS_FILE.with_suffix(".tmp")
    try:
        temp_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        temp_file.rename(SESSIONS_FILE)
    except OSError:
        # Fallback: direct write if rename fails (Windows edge case)
        SESSIONS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    finally:
        try:
            temp_file.unlink()
        except OSError:
            pass


def append_session_to_json(session: dict) -> None:
    """Append or replace a session entry in sessions.json without reordering others."""
    sessions = read_sessions_json()
    for index, existing in enumerate(sessions):
        if existing.get("port") == session.get("port"):
            sessions[index] = session
            break
    else:
        sessions.append(session)
    write_sessions_json(sessions)


def remove_session_from_json(port: int) -> None:
    """Remove a session entry by port from sessions.json."""
    sessions = read_sessions_json()
    sessions = [s for s in sessions if s.get("port") != port]
    write_sessions_json(sessions)


__all__ = [
    "DATA_DIR",
    "LOGS_DIR",
    "DAEMON_LOG",
    "SESSIONS_FILE",
    "SNAPSHOTS_DIR",
    "get_session_snapshot_path",
    "write_session_snapshot",
    "read_session_snapshot",
    "remove_session_snapshot",
    "list_session_snapshot_ids",
    "garbage_collect_session_snapshots",
    "get_session_log_path",
    "rotate_daemon_log",
    "cleanup_session_log",
    "remove_session_artifacts",
    "purge_silc_data",
    "write_daemon_log",
    "write_session_log",
    "rotate_session_log",
    "read_session_log",
    "read_sessions_json",
    "write_sessions_json",
    "append_session_to_json",
    "remove_session_from_json",
]
