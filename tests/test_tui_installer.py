"""Tests for native TUI release asset selection."""

from __future__ import annotations

import pytest

from silc.tui import installer


def _patch_platform(monkeypatch: pytest.MonkeyPatch, system: str, machine: str) -> None:
    monkeypatch.setattr(installer.platform, "system", lambda: system)
    monkeypatch.setattr(installer.platform, "machine", lambda: machine)


def test_choose_asset_prefers_tui_asset(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_platform(monkeypatch, "Linux", "x86_64")

    release = {
        "assets": [
            {"name": "silc-linux-x86_64", "browser_download_url": "app"},
            {"name": "silc-tui-linux-x86_64", "browser_download_url": "tui"},
        ]
    }

    asset = installer._choose_asset_for_platform(release)

    assert asset["name"] == "silc-tui-linux-x86_64"


def test_choose_asset_rejects_non_tui_assets(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_platform(monkeypatch, "Linux", "x86_64")

    release = {"assets": [{"name": "silc-linux-x86_64", "browser_download_url": "app"}]}

    with pytest.raises(installer.InstallerError):
        installer._choose_asset_for_platform(release)
