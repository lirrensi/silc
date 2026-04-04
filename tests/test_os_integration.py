"""Tests for SILC OS integration installers."""

from __future__ import annotations

from pathlib import Path

import pytest

from silc.os_integration import install_os_integration, uninstall_os_integration


def _patch_platform(monkeypatch: pytest.MonkeyPatch, platform: str) -> None:
    from silc import os_integration as os_mod

    monkeypatch.setattr(os_mod.sys, "platform", platform)


def _patch_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    from silc import os_integration as os_mod

    monkeypatch.setattr(os_mod.Path, "home", staticmethod(lambda: home))


def test_install_and_uninstall_linux_integration(tmp_path, monkeypatch):
    _patch_platform(monkeypatch, "linux")
    _patch_home(monkeypatch, tmp_path)

    created = install_os_integration()

    helper = tmp_path / ".silc" / "os-integration" / "silc-start-here.py"
    nautilus = (
        tmp_path / ".local" / "share" / "nautilus" / "scripts" / "SILC Start Here"
    )
    dolphin = (
        tmp_path
        / ".local"
        / "share"
        / "kio"
        / "servicemenus"
        / "silc-start-here.desktop"
    )
    thunar = tmp_path / ".config" / "Thunar" / "uca.xml"

    assert str(helper) in created
    assert nautilus.exists()
    assert dolphin.exists()
    assert thunar.exists()
    assert "SILC Start Here" in thunar.read_text(encoding="utf-8")
    assert str(helper) in dolphin.read_text(encoding="utf-8")
    assert helper.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3")

    removed = uninstall_os_integration()

    assert str(helper) in removed
    assert not helper.exists()
    assert not nautilus.exists()
    assert not dolphin.exists()
    assert not thunar.exists()


def test_install_and_uninstall_macos_integration(tmp_path, monkeypatch):
    _patch_platform(monkeypatch, "darwin")
    _patch_home(monkeypatch, tmp_path)

    created = install_os_integration()

    helper = tmp_path / ".silc" / "os-integration" / "silc-start-here.py"
    workflow = tmp_path / "Library" / "Services" / "SILC Start.workflow"
    info_plist = workflow / "Contents" / "Info.plist"
    document_wflow = workflow / "Contents" / "document.wflow"

    assert str(helper) in created
    assert workflow.exists()
    assert info_plist.exists()
    assert document_wflow.exists()
    assert "SILC Start Here" in info_plist.read_text(encoding="utf-8")
    assert str(helper) in document_wflow.read_text(encoding="utf-8")

    removed = uninstall_os_integration()

    assert str(workflow) in removed
    assert not helper.exists()
    assert not workflow.exists()


def test_install_and_uninstall_windows_integration(tmp_path, monkeypatch):
    _patch_platform(monkeypatch, "win32")
    _patch_home(monkeypatch, tmp_path)

    registry_calls: dict[str, list[str]] = {"created": [], "deleted": []}

    class FakeKey:
        def __init__(self, path: str):
            self.path = path

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeWinReg:
        HKEY_CURRENT_USER = object()
        KEY_READ = 1
        KEY_WRITE = 2
        REG_SZ = 1

        def CreateKeyEx(self, root, path, *args, **kwargs):
            registry_calls["created"].append(path)
            return FakeKey(path)

        def SetValueEx(self, key, value_name, reserved, reg_type, value):
            registry_calls.setdefault("values", []).append(str(value))

        def OpenKey(self, root, path, *args, **kwargs):
            raise FileNotFoundError

        def EnumKey(self, key, index):
            raise OSError

        def DeleteKey(self, root, path):
            registry_calls["deleted"].append(path)

    from silc import os_integration as os_mod

    monkeypatch.setitem(os_mod.sys.modules, "winreg", FakeWinReg())

    created = install_os_integration()

    helper = tmp_path / ".silc" / "os-integration" / "silc-start-here.py"
    assert str(helper) in created
    assert any(path.endswith("SilcStartHere") for path in registry_calls["created"])
    assert helper.exists()

    removed = uninstall_os_integration()

    assert str(helper) in removed
    assert helper.exists() is False
