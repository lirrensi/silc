"""Tests for session shell bootstrap launch wiring."""

from __future__ import annotations

import re

from silc.core import session as session_module
from silc.core.session import SilcSession
from silc.utils.shell_detect import ShellInfo


class _DummyPTY:
    def __init__(self) -> None:
        self.resized = None

    async def read(self, size: int = 1024) -> bytes:
        return b""

    async def write(self, data: bytes) -> None:
        return None

    def resize(self, rows: int, cols: int) -> None:
        self.resized = (rows, cols)

    def kill(self) -> None:
        return None

    def is_alive(self) -> bool:
        return True

    def send_sigterm(self) -> None:
        return None

    def send_sigkill(self) -> None:
        return None


def test_session_uses_static_bootstrap_launch_spec(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_create_pty(shell_cmd, env, cwd=None):
        captured["shell_cmd"] = shell_cmd
        captured["env"] = dict(env)
        captured["cwd"] = cwd
        return _DummyPTY()

    monkeypatch.setattr(session_module, "create_pty", fake_create_pty)

    info = ShellInfo("pwsh", "pwsh.exe", re.compile(r"PS .*>"))
    session = SilcSession(
        port=20001, name="bootstrap-test", shell_info=info, cwd="C:/tmp"
    )

    shell_cmd = captured["shell_cmd"]
    assert isinstance(shell_cmd, list)
    assert any("bootstrap.ps1" in part for part in shell_cmd)
    assert captured["cwd"] == "C:/tmp"
    assert "shell_cmd" in captured
    assert session.pty.resized == (30, 120)
