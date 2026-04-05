"""Silc daemon for managing multiple shell sessions."""

from __future__ import annotations

from silc.daemon.pidfile import (
    is_daemon_running,
    kill_daemon,
    read_pidfile,
    remove_pidfile,
    write_pidfile,
)
from silc.daemon.registry import SessionEntry, SessionRegistry


def _load_daemon_manager():
    from silc.daemon.manager import DAEMON_PORT, SilcDaemon

    return DAEMON_PORT, SilcDaemon


def __getattr__(name: str):
    if name in {"DAEMON_PORT", "SilcDaemon"}:
        daemon_port, silc_daemon = _load_daemon_manager()
        globals()["DAEMON_PORT"] = daemon_port
        globals()["SilcDaemon"] = silc_daemon
        return globals()[name]
    raise AttributeError(name)


__all__ = [
    "SilcDaemon",
    "SessionEntry",
    "SessionRegistry",
    "is_daemon_running",
    "kill_daemon",
    "read_pidfile",
    "remove_pidfile",
    "write_pidfile",
    "DAEMON_PORT",
]
