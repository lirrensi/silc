"""Helpers for locating the native SILC TUI binary."""

# FILE: silc/tui/installer.py
# PURPOSE: Resolve the native SILC TUI binary from the active install tree or a local source checkout.
# OWNS: Native TUI path discovery and missing-binary errors for CLI launch.
# EXPORTS: InstallerError - lookup failure; ensure_native_tui_binary - local resolver.
# DOCS: agent_chat/plan_operation_eek_2026-04-10.md, docs/arch_tui.md

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable

PACKAGE_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]

BinaryProgress = Callable[[str], None]


class InstallerError(RuntimeError):
    """Raised when the native TUI binary cannot be found."""


def ensure_native_tui_binary(progress: BinaryProgress | None = None) -> Path:
    """Return a ready-to-run native TUI binary from local disk."""

    if progress:
        progress("Locating native TUI binary…")

    candidate = _find_native_tui_binary()
    if candidate is None:
        raise InstallerError(
            "Native TUI binary was not found in the active SILC install tree. "
            "Run the installer script again or repopulate tui_client/dist/silc-tui inside the installed tree."
        )
    return candidate


def _find_native_tui_binary() -> Path | None:
    for directory in _search_directories():
        candidate = _candidate_binary(directory)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def _search_directories() -> tuple[Path, ...]:
    return (PROJECT_ROOT / "tui_client" / "dist",)


def _candidate_binary(directory: Path) -> Path:
    name = "silc-tui.exe" if sys.platform.startswith("win") else "silc-tui"
    return directory / name
