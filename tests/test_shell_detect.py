import re

import pytest

from silc.utils.shell_detect import ShellInfo


@pytest.mark.parametrize(
    ("shell_type", "expected_snippets"),
    [
        (
            "bash",
            [
                "__SILC_BEGIN_abcd__",
                "ec=$?",
                "__SILC_END_abcd__:$ec",
            ],
        ),
        (
            "zsh",
            [
                "__SILC_BEGIN_abcd__",
                "ec=$?",
                "__SILC_END_abcd__:$ec",
            ],
        ),
        (
            "sh",
            [
                "__SILC_BEGIN_abcd__",
                "ec=$?",
                "__SILC_END_abcd__:$ec",
            ],
        ),
        (
            "cmd",
            [
                "__SILC_BEGIN_abcd__",
                "__SILC_END_abcd__:%ERRORLEVEL%",
            ],
        ),
        (
            "pwsh",
            [
                "__SILC_BEGIN_abcd__",
                "__SILC_END_abcd__:",
                "$LASTEXITCODE",
            ],
        ),
        (
            "unknown",
            [
                "__SILC_BEGIN_abcd__",
                "ec=$?",
                "__SILC_END_abcd__:$ec",
            ],
        ),
    ],
)
def test_wrap_command_inserts_markers(shell_type: str, expected_snippets: list[str]):
    info = ShellInfo(shell_type, "/bin/shell", re.compile(r".*$"))
    wrapped = info.wrap_command("echo test", "abcd", "\n")
    assert "echo test" in wrapped
    for snippet in expected_snippets:
        assert snippet in wrapped
