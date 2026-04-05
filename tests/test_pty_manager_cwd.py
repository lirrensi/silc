# FILE: tests/test_pty_manager_cwd.py
# PURPOSE: Verify PTY launch cwd validation and fallback behavior.
# OWNS: create_pty cwd normalization for valid and invalid launch paths.
# DOCS: agent_chat/plan_hidden_cwd_prompt_2026-04-05.md

from __future__ import annotations

from pathlib import Path

from silc.core import pty_manager


class _CapturePTY:
    def __init__(self, shell_cmd, env, cwd=None):
        self.cwd = cwd


def test_create_pty_falls_back_to_home_for_invalid_cwd(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(pty_manager.sys, "platform", "linux")
    monkeypatch.setattr(pty_manager.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(pty_manager, "UnixPTY", _CapturePTY)

    pty = pty_manager.create_pty(cwd=str(tmp_path / "missing"))

    assert pty.cwd == str(tmp_path)


def test_create_pty_preserves_valid_cwd(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(pty_manager.sys, "platform", "linux")
    monkeypatch.setattr(pty_manager.Path, "home", lambda: Path("/unused-home"))
    monkeypatch.setattr(pty_manager, "UnixPTY", _CapturePTY)

    pty = pty_manager.create_pty(cwd=str(tmp_path))

    assert pty.cwd == str(tmp_path)
