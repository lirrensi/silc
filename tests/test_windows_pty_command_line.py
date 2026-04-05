"""Regression tests for Windows PTY command-line construction."""

from __future__ import annotations

import subprocess

from silc.core.pty_manager import WindowsPTY


def test_windows_pty_joins_command_list_with_windows_rules(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _DummyProcess:
        pid = 1234

    class _DummyPtyProcess:
        @staticmethod
        def spawn(command, env=None, cwd=None):
            captured["command"] = command
            captured["env"] = dict(env or {})
            captured["cwd"] = cwd
            return _DummyProcess()

    class _DummyWinptyModule:
        PtyProcess = _DummyPtyProcess

    monkeypatch.setattr(
        WindowsPTY, "_load_winpty_module", lambda self: _DummyWinptyModule()
    )

    command = [
        r"C:\Windows\System32\cmd.exe",
        "/k",
        r'call "C:\Users\rx\001_Code\100_M\SILC\static\scripts\cmd\bootstrap.cmd"',
    ]

    WindowsPTY(command, env={}, cwd=r"C:\Users\rx\001_Code\100_M\SILC")

    assert captured["command"] == subprocess.list2cmdline(command)
