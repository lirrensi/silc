"""Shared daemon settings defaults and merge helpers."""

# FILE: silc/daemon/settings.py
# PURPOSE: Define daemon-owned shared settings defaults and merge utilities.
# OWNS: Shared settings schema defaults, deep merge behavior, alias normalization, and path-to-payload helpers.
# EXPORTS: DaemonSettings, DEFAULT_DAEMON_SETTINGS, deep_merge_settings, build_path_update.
# DOCS: agent_chat/plan_theme_preset_allowlist_sync_2026-04-08.md

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Mapping

DEFAULT_MANAGER_THEME_PRESET = "amoled"
DEFAULT_TERMINAL_THEME_PRESET = "amoled"

LIGHT_THEME_PRESETS = frozenset({"github", "vercel", "solarized"})
ALL_THEME_PRESETS = LIGHT_THEME_PRESETS | frozenset(
    {
        "oc-2",
        "amoled",
        "dracula",
        "nord",
        "gruvbox",
        "catppuccin",
        "tokyo-night",
        "rose-pine",
        "one-dark",
        "monokai",
        "everforest",
    }
)

DEFAULT_DAEMON_SETTINGS: dict[str, Any] = {
    "ui": {
        "managerTheme": DEFAULT_MANAGER_THEME_PRESET,
        "themePreference": "dark",
    },
    "terminal": {
        "themePreset": DEFAULT_TERMINAL_THEME_PRESET,
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


def _legacy_mode_from_preset(preset: str) -> str:
    return "light" if preset in LIGHT_THEME_PRESETS else "dark"


def _coerce_theme_preset(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    if value in ALL_THEME_PRESETS:
        return value

    if value == "light":
        return "github"

    if value in {"dark", "system"}:
        return DEFAULT_MANAGER_THEME_PRESET

    return None


def normalize_settings(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """Normalize canonical daemon settings names and keep legacy aliases in sync."""

    if raw is None:
        return {}

    normalized = deepcopy(dict(raw))

    ui = normalized.get("ui")
    if isinstance(ui, Mapping):
        ui_dict = deepcopy(dict(ui))
        manager_theme = _coerce_theme_preset(ui_dict.get("managerTheme"))
        if manager_theme is None:
            manager_theme = _coerce_theme_preset(ui_dict.get("themePreference"))
        if manager_theme is not None:
            ui_dict["managerTheme"] = manager_theme
            ui_dict["themePreference"] = _legacy_mode_from_preset(manager_theme)
        normalized["ui"] = ui_dict

    terminal = normalized.get("terminal")
    if isinstance(terminal, Mapping):
        terminal_dict = deepcopy(dict(terminal))
        terminal_theme = _coerce_theme_preset(terminal_dict.get("themePreset"))
        if terminal_theme is None:
            terminal_theme = _coerce_theme_preset(terminal_dict.get("theme"))
        if terminal_theme is not None:
            terminal_dict["themePreset"] = terminal_theme
            terminal_dict["theme"] = _legacy_mode_from_preset(terminal_theme)
        normalized["terminal"] = terminal_dict

    return normalized


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
        return cls(
            values=deep_merge_settings(DEFAULT_DAEMON_SETTINGS, normalize_settings(raw))
        )

    def merged(self, update: Mapping[str, Any]) -> "DaemonSettings":
        return DaemonSettings(
            values=deep_merge_settings(self.values, normalize_settings(update))
        )

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self.values)


__all__ = [
    "DaemonSettings",
    "DEFAULT_DAEMON_SETTINGS",
    "deep_merge_settings",
    "build_path_update",
]
