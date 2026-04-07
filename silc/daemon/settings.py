"""Shared daemon settings defaults and merge helpers."""

# FILE: silc/daemon/settings.py
# PURPOSE: Define daemon-owned shared settings defaults and merge utilities.
# OWNS: Shared settings schema defaults, deep merge behavior, and path-to-payload helpers.
# EXPORTS: DaemonSettings, DEFAULT_DAEMON_SETTINGS, deep_merge_settings, build_path_update.
# DOCS: agent_chat/plan_daemon_settings_store_2026-04-08.md

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Mapping

DEFAULT_DAEMON_SETTINGS: dict[str, Any] = {
    "ui": {"themePreference": "system"},
    "terminal": {
        "theme": "dark",
        "cols": 120,
        "rows": 30,
        "scrollback": 5000,
        "fontFamily": 'Menlo, Monaco, "Courier New", monospace',
        "fontSize": 15,
        "lineHeight": 1.05,
        "cursorBlink": True,
    },
}


def deep_merge_settings(
    base: Mapping[str, Any], update: Mapping[str, Any]
) -> dict[str, Any]:
    """Deep-merge two mapping objects without mutating either input."""

    merged = deepcopy(dict(base))
    for key, value in update.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, Mapping):
            merged[key] = deep_merge_settings(existing, value)
        else:
            merged[key] = deepcopy(value)
    return merged


def build_path_update(path: str, value: Any) -> dict[str, Any]:
    """Build a nested mapping update from a dotted path and leaf value."""

    parts = [segment for segment in path.split(".") if segment]
    if not parts:
        raise ValueError("Settings path cannot be empty")

    update: Any = deepcopy(value)
    for segment in reversed(parts):
        update = {segment: update}
    return update


@dataclass(slots=True)
class DaemonSettings:
    """In-memory representation of the daemon settings payload."""

    values: dict[str, Any] = field(
        default_factory=lambda: deepcopy(DEFAULT_DAEMON_SETTINGS)
    )

    @classmethod
    def load(cls, raw: Mapping[str, Any] | None = None) -> "DaemonSettings":
        if raw is None:
            return cls()
        return cls(values=deep_merge_settings(DEFAULT_DAEMON_SETTINGS, raw))

    def merged(self, update: Mapping[str, Any]) -> "DaemonSettings":
        return DaemonSettings(values=deep_merge_settings(self.values, update))

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self.values)


__all__ = [
    "DaemonSettings",
    "DEFAULT_DAEMON_SETTINGS",
    "deep_merge_settings",
    "build_path_update",
]
