import re
from pathlib import Path

import pytest

from silc.utils import shell_detect
from silc.utils.shell_detect import ShellInfo


@pytest.mark.parametrize(
    ("shell_type", "expected_snippets"),
    [
        (
            "bash",
            ["__silc_exec() {", "__SILC_BEGIN_$2__", "__SILC_END_$2__"],
        ),
        (
            "zsh",
            ["__silc_exec() {", "__SILC_BEGIN_$2__", "__SILC_END_$2__"],
        ),
        (
            "sh",
            ["__silc_exec() {", "__SILC_BEGIN_$2__", "__SILC_END_$2__"],
        ),
        (
            "pwsh",
            [
                "function __silc_exec($cmd, $token) {",
                "__SILC_BEGIN_${token}__",
                "__SILC_END_${token}__",
            ],
        ),
        (
            "cmd",
            ["doskey __silc_exec", "__silc_exec.bat"],
        ),
    ],
)
def test_get_helper_function_contains_markers(
    shell_type: str,
    expected_snippets: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    tmp_dir = tmp_path / "shell"
    tmp_dir.mkdir()

    if shell_type == "cmd":
        monkeypatch.setattr(
            shell_detect.tempfile,
            "gettempdir",
            lambda: str(tmp_dir),
        )

    info = ShellInfo(shell_type, "/bin/shell", re.compile(r".*$"))
    helper = info.get_helper_function()
    assert helper is not None
    assert "\n" not in helper
    for snippet in expected_snippets:
        assert snippet in helper

    if shell_type == "cmd":
        helper_file = tmp_dir / "__silc_exec.bat"
        assert helper_file.exists()


@pytest.mark.parametrize(
    ("shell_type", "command", "token", "expected_fragment"),
    [
        ("bash", "whoami", "abcd", "__silc_exec whoami abcd"),
        ("zsh", "ls -l", "1234", "__silc_exec 'ls -l' 1234"),
        ("pwsh", "dir", "deadbeef", "__silc_exec 'dir' 'deadbeef'"),
        ("cmd", "whoami", "token", '__silc_exec "whoami" token'),
    ],
)
def test_build_helper_invocation(
    shell_type: str, command: str, token: str, expected_fragment: str
):
    info = ShellInfo(shell_type, "/bin/shell", re.compile(r".*$"))
    invocation = info.build_helper_invocation(command, token)
    assert expected_fragment in invocation
