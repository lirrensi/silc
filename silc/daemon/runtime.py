"""Daemon-side runtime model for a desired session record."""

# FILE: silc/daemon/runtime.py
# PURPOSE: Track mutable daemon runtime state for a desired session record without conflating it with persistence.
# OWNS: Session runtime state, generation tracking, backoff timing, and logging/status formatting helpers.
# EXPORTS: SessionState (runtime lifecycle labels), SessionRuntime (per-record runtime state), create_runtime_for_record, bump_runtime_generation, record_runtime_failure, runtime_backoff_expired, format_runtime_state.
# DOCS: docs/arch_daemon.md

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum

from silc.daemon.registry import SessionEntry


class SessionState(str, Enum):
    """Lifecycle state for a desired session's runtime."""

    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    BACKOFF = "backoff"
    STOPPING = "stopping"
    STOPPED = "stopped"


@dataclass
class SessionRuntime:
    """Mutable runtime owned by the daemon for one desired record."""

    port: int
    generation: int = 0
    state: SessionState = SessionState.STARTING
    session: object | None = None
    server: object | None = None
    socket: object | None = None
    server_task: object | None = None
    last_error: str = ""
    last_traceback: str = ""
    restart_count: int = 0
    next_retry_at: datetime | None = None
    name: str = ""
    shell_type: str = ""
    cwd: str | None = None
    api_token: str | None = None
    title: str = ""
    is_global: bool = False


def create_runtime_for_record(
    entry: SessionEntry,
    *,
    generation: int = 0,
    state: SessionState = SessionState.STARTING,
    api_token: str | None = None,
    title: str | None = None,
) -> SessionRuntime:
    """Create a fresh runtime snapshot for a desired record."""

    return SessionRuntime(
        port=entry.port,
        generation=generation,
        state=state,
        name=entry.name,
        shell_type=entry.shell_type,
        cwd=entry.cwd,
        title=entry.title if title is None else title,
        is_global=entry.is_global,
        api_token=api_token,
    )


def bump_runtime_generation(runtime: SessionRuntime) -> SessionRuntime:
    """Return a runtime copy for the next generation."""

    return replace(
        runtime,
        generation=runtime.generation + 1,
        state=SessionState.STARTING,
        last_error="",
        last_traceback="",
        next_retry_at=None,
    )


def record_runtime_failure(
    runtime: SessionRuntime,
    *,
    error: str,
    traceback_text: str = "",
    backoff_seconds: float = 3.0,
) -> SessionRuntime:
    """Return runtime updated for a launch or supervision failure."""

    restart_count = runtime.restart_count + 1
    delay = min(30.0, backoff_seconds * max(1, restart_count))
    return replace(
        runtime,
        state=SessionState.BACKOFF,
        last_error=error,
        last_traceback=traceback_text,
        restart_count=restart_count,
        next_retry_at=datetime.utcnow() + timedelta(seconds=delay),
    )


def runtime_backoff_expired(
    runtime: SessionRuntime, now: datetime | None = None
) -> bool:
    """Return True when the runtime can be retried after backoff."""

    if runtime.next_retry_at is None:
        return True
    if now is None:
        now = datetime.utcnow()
    return now >= runtime.next_retry_at


def format_runtime_state(runtime: SessionRuntime) -> str:
    """Format runtime state for logs and status responses."""

    retry_at = runtime.next_retry_at.isoformat() + "Z" if runtime.next_retry_at else ""
    return (
        f"port={runtime.port} generation={runtime.generation} state={runtime.state.value} "
        f"restarts={runtime.restart_count} retry_at={retry_at} error={runtime.last_error}"
    ).strip()


__all__ = [
    "SessionState",
    "SessionRuntime",
    "create_runtime_for_record",
    "bump_runtime_generation",
    "record_runtime_failure",
    "runtime_backoff_expired",
    "format_runtime_state",
]
