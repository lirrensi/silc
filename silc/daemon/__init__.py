"""Silc daemon for managing multiple shell sessions."""

from __future__ import annotations

from silc.daemon.manager import DAEMON_PORT, SilcDaemon
from silc.daemon.pidfile import (
    is_daemon_running,
    kill_daemon,
    read_pidfile,
    remove_pidfile,
    write_pidfile,
)
from silc.daemon.registry import SessionEntry, SessionRegistry

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
