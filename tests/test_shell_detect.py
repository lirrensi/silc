"""Tests for shell bootstrap loading and invocation quoting."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from silc.utils.shell_detect import ShellInfo


@pytest.mark.parametrize(
    ("shell_type", "expected_snippets"),
    [
        ("bash", ["bootstrap.sh", "--rcfile", "__silc_exec() {", "PROMPT_COMMAND"]),
        ("zsh", ["precmd", "__silc_exec() {"]),
        ("sh", ["__silc_exec() {"]),
        (
            "pwsh",
            [
                "bootstrap.ps1",
                "-NoExit",
                "SilcOriginalPrompt",
                "function global:prompt {",
                "function global:__silc_exec($cmd, $token) {",
                "633;cwd=",
            ],
        ),
        (
            "powershell",
            [
                "bootstrap.ps1",
                "-NoExit",
                "SilcOriginalPrompt",
                "function global:prompt {",
                "function global:__silc_exec($cmd, $token) {",
                "633;cwd=",
            ],
        ),
        ("cmd", ["bootstrap.cmd", "doskey __silc_exec", "__silc_exec.bat", "/k"]),
    ],
)
def test_build_launch_spec_points_at_bootstrap_scripts(
    shell_type: str, expected_snippets: list[str]
) -> None:
    info = ShellInfo(shell_type, "/bin/shell", re.compile(r".*$"))
    spec = info.build_launch_spec()

    argv_text = " ".join(spec.argv)
    assert argv_text
    if shell_type == "bash":
        assert "--login" in argv_text
        assert "--noprofile" not in argv_text
    if shell_type == "zsh":
        assert "-l" in argv_text
    for snippet in expected_snippets:
        assert snippet in argv_text or snippet in _bootstrap_text(info)

    if shell_type in {"pwsh", "powershell"}:
        bootstrap = _bootstrap_text(info)
        assert "Set-StrictMode" not in bootstrap
        assert "Get-Item function:prompt" in bootstrap
        assert "__silc_render_prompt" in bootstrap

    if shell_type == "zsh":
        assert "ZDOTDIR" in spec.env
        wrapper_dir = Path(spec.env["ZDOTDIR"])
        rcfile = wrapper_dir / ".zshrc"
        assert rcfile.exists()
        assert "bootstrap.zsh" in rcfile.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("shell_type", "command", "token", "expected_fragment"),
    [
        ("bash", "whoami", "abcd", "__silc_exec whoami abcd"),
        ("zsh", "ls -l", "1234", "__silc_exec 'ls -l' 1234"),
        ("pwsh", "dir", "deadbeef", "__silc_exec 'dir' 'deadbeef'"),
        (
            "powershell",
            "dir",
            "deadbeef",
            "__silc_exec 'dir' 'deadbeef'",
        ),
        ("cmd", "whoami", "token", '__silc_exec "whoami" token'),
    ],
)
def test_build_helper_invocation(
    shell_type: str, command: str, token: str, expected_fragment: str
) -> None:
    info = ShellInfo(shell_type, "/bin/shell", re.compile(r".*$"))
    invocation = info.build_helper_invocation(command, token)
    assert expected_fragment in invocation


def test_cmd_launch_spec_uses_direct_bootstrap_path() -> None:
    info = ShellInfo("cmd", "cmd.exe", re.compile(r".*$"))
    spec = info.build_launch_spec()

    assert spec.argv[1] == "/k"
    assert spec.argv[2] == str(info.get_bootstrap_script_path())


def test_bash_bootstrap_sources_user_bashrc() -> None:
    info = ShellInfo("bash", "/bin/bash", re.compile(r".*$"))
    bootstrap = _bootstrap_text(info)

    assert "/etc/profile" in bootstrap
    assert ".bash_profile" in bootstrap
    assert ".bash_login" in bootstrap
    assert ".profile" in bootstrap
    assert "/etc/bash.bashrc" in bootstrap or "/etc/bashrc" in bootstrap
    assert ".bashrc" in bootstrap
    assert "PROMPT_COMMAND" in bootstrap


def test_zsh_launch_spec_sources_user_rc_before_bootstrap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("silc.utils.shell_detect.Path.home", lambda: tmp_path)
    user_rc = tmp_path / ".zshrc"
    user_rc.write_text("export SILC_TEST=1\n", encoding="utf-8")

    info = ShellInfo("zsh", "/bin/zsh", re.compile(r".*$"))
    spec = info.build_launch_spec()

    assert "-l" in " ".join(spec.argv)
    wrapper_dir = Path(spec.env["ZDOTDIR"])
    assert (wrapper_dir / ".zshenv").exists()
    assert (wrapper_dir / ".zprofile").exists()
    assert (wrapper_dir / ".zlogin").exists()
    rcfile = wrapper_dir / ".zshrc"
    content = rcfile.read_text(encoding="utf-8")

    if Path("/etc/zshrc").exists():
        assert "/etc/zshrc" in content
    assert str(user_rc) in content
    assert content.index(str(user_rc)) < content.index("bootstrap.zsh")


def _bootstrap_text(info: ShellInfo) -> str:
    path = info.get_bootstrap_script_path()
    return path.read_text(encoding="utf-8")
