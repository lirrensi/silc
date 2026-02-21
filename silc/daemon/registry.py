"""Session registry for tracking active sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict


@dataclass
class SessionEntry:
    """Registry entry for a session."""

    port: int
    name: str
    session_id: str
    shell_type: str
    created_at: datetime
    last_access: datetime = field(default_factory=datetime.utcnow)

    def update_access(self) -> None:
        """Update last_access timestamp."""
        self.last_access = datetime.utcnow()


class SessionRegistry:
    """In-memory registry of active sessions with dual index by port and name."""

    def __init__(self):
        self._sessions: Dict[int, SessionEntry] = {}
        self._name_index: Dict[str, int] = {}  # name -> port

    def add(
        self, port: int, name: str, session_id: str, shell_type: str
    ) -> SessionEntry:
        """Add a new session entry.

        Raises:
            ValueError: If name is already in use.
        """
        if name in self._name_index:
            raise ValueError(f"Session name '{name}' is already in use")

        entry = SessionEntry(
            port=port,
            name=name,
            session_id=session_id,
            shell_type=shell_type,
            created_at=datetime.utcnow(),
        )
        self._sessions[port] = entry
        self._name_index[name] = port
        return entry

    def remove(self, port: int) -> SessionEntry | None:
        """Remove a session entry."""
        entry = self._sessions.pop(port, None)
        if entry:
            self._name_index.pop(entry.name, None)
        return entry

    def get(self, port: int) -> SessionEntry | None:
        """Get a session entry by port."""
        entry = self._sessions.get(port)
        if entry:
            entry.update_access()
        return entry

    def get_by_name(self, name: str) -> SessionEntry | None:
        """Get a session entry by name."""
        port = self._name_index.get(name)
        if port is None:
            return None
        return self.get(port)

    def name_exists(self, name: str) -> bool:
        """Check if a name is already in use."""
        return name in self._name_index

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
            self.remove(port)
        return to_remove


__all__ = ["SessionEntry", "SessionRegistry"]
