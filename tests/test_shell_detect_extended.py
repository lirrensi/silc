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


def test_available_shell_choices_windows_prefers_pwsh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shell_detect.sys, "platform", "win32")
    monkeypatch.setattr(
        shell_detect.shutil,
        "which",
        lambda name: {
            "pwsh": "C:/Program Files/PowerShell/7/pwsh.exe",
            "pwsh.exe": "C:/Program Files/PowerShell/7/pwsh.exe",
            "powershell": "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
            "powershell.exe": "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
            "cmd": "C:/Windows/System32/cmd.exe",
            "cmd.exe": "C:/Windows/System32/cmd.exe",
        }.get(name),
    )

    choices = shell_detect.get_available_shell_choices()

    assert [choice.type for choice in choices] == ["pwsh", "powershell", "cmd"]
    assert choices[0].label == "PowerShell"


def test_available_shell_choices_posix_prefers_current_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shell_detect.sys, "platform", "linux")
    monkeypatch.setenv("SHELL", "/usr/bin/zsh")
    monkeypatch.setattr(shell_detect.shutil, "which", lambda name: f"/usr/bin/{name}")

    choices = shell_detect.get_available_shell_choices()

    assert [choice.type for choice in choices] == ["zsh", "bash", "sh"]
    assert choices[0].label == "Zsh"
