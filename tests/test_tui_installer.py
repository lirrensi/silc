"""Tests for native TUI binary discovery."""

# FILE: tests/test_tui_installer.py
# PURPOSE: Verify native TUI lookup uses only the repo-style tui_client/dist contract.
# OWNS: Positive and negative coverage for ensure_native_tui_binary.
# EXPORTS: test_finds_binary_from_tui_client_dist, test_missing_binary_in_tui_client_dist_raises_installer_error.
# DOCS: agent_chat/plan_zip_distribution_2026-04-10.md, docs/arch_tui.md

from __future__ import annotations

from pathlib import Path

import pytest

from silc.tui import installer


def test_finds_binary_from_tui_client_dist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project_root = tmp_path / "project"
    dist_dir = project_root / "tui_client" / "dist"
    dist_dir.mkdir(parents=True)
    binary = dist_dir / (
        "silc-tui.exe" if installer.sys.platform.startswith("win") else "silc-tui"
    )
    binary.write_text("echo silc", encoding="utf-8")
    binary.chmod(0o755)

    monkeypatch.setattr(installer, "PROJECT_ROOT", project_root)

    resolved = installer.ensure_native_tui_binary()

    assert resolved == binary.resolve()


def test_missing_binary_in_tui_client_dist_raises_installer_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(installer, "PROJECT_ROOT", Path("C:/missing/project"))

    with pytest.raises(installer.InstallerError):
        installer.ensure_native_tui_binary()
