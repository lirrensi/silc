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
    for snippet in expected_snippets:
        assert snippet in argv_text or snippet in _bootstrap_text(info)

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


def _bootstrap_text(info: ShellInfo) -> str:
    path = info.get_bootstrap_script_path()
    return path.read_text(encoding="utf-8")
