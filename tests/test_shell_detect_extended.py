import pytest

from silc.utils import shell_detect


def test_detect_shell_unix_prefers_zsh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shell_detect.sys, "platform", "linux")
    monkeypatch.setenv("SHELL", "/usr/bin/zsh")

    info = shell_detect.detect_shell()
    assert info.type == "zsh"
    assert info.prompt_pattern.pattern == ".*[%#$] $"


def test_detect_shell_unix_falls_back_to_sh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shell_detect.sys, "platform", "linux")
    monkeypatch.setenv("SHELL", "/usr/bin/dash")

    info = shell_detect.detect_shell()
    assert info.type == "sh"
    assert info.prompt_pattern.pattern == "[$#] $"


def test_detect_shell_windows_pwsh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shell_detect.sys, "platform", "win32")
    monkeypatch.setenv("PSModulePath", "C:\\Modules")
    monkeypatch.delenv("SHELL", raising=False)

    info = shell_detect.detect_shell()
    assert info.type == "pwsh"
    assert info.prompt_pattern.pattern == "PS .*>"


def test_detect_shell_windows_cmd(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shell_detect.sys, "platform", "win32")
    monkeypatch.delenv("PSModulePath", raising=False)
    monkeypatch.delenv("SHELL", raising=False)

    info = shell_detect.detect_shell()
    assert info.type == "cmd"
    assert info.prompt_pattern.pattern == "[A-Z]:\\\\.*>"
