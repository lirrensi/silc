"""Session registry for tracking active sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict


@dataclass
class SessionEntry:
    """Registry entry for a session."""

    port: int
    session_id: str
    shell_type: str
    created_at: datetime
    last_access: datetime = field(default_factory=datetime.utcnow)

    def update_access(self) -> None:
        """Update last_access timestamp."""
        self.last_access = datetime.utcnow()


class SessionRegistry:
    """In-memory registry of active sessions."""

    def __init__(self):
        self._sessions: Dict[int, SessionEntry] = {}

    def add(self, port: int, session_id: str, shell_type: str) -> SessionEntry:
        """Add a new session entry."""
        entry = SessionEntry(
            port=port,
            session_id=session_id,
            shell_type=shell_type,
            created_at=datetime.utcnow(),
        )
        self._sessions[port] = entry
        return entry

    def remove(self, port: int) -> SessionEntry | None:
        """Remove a session entry."""
        return self._sessions.pop(port, None)

    def get(self, port: int) -> SessionEntry | None:
        """Get a session entry."""
        entry = self._sessions.get(port)
        if entry:
            entry.update_access()
        return entry

    def list_all(self) -> list[SessionEntry]:
        """List all sessions sorted by port."""
        return sorted(self._sessions.values(), key=lambda s: s.port)

    def cleanup_timeout(self, timeout_seconds: int = 1800) -> list[int]:
        """Remove sessions idle longer than timeout. Returns list of ports cleaned."""
        now = datetime.utcnow()
        to_remove = []
        for port, entry in self._sessions.items():
            idle_seconds = (now - entry.last_access).total_seconds()
            if idle_seconds > timeout_seconds:
                to_remove.append(port)
        for port in to_remove:
            self._sessions.pop(port)
        return to_remove


__all__ = ["SessionEntry", "SessionRegistry"]
