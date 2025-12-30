import re
from silc.utils.shell_detect import ShellInfo


def test_get_sentinel_command_variants():
    uuid = "abcd"
    # Bash-like shells
    for shell_type in ["bash", "zsh", "sh"]:
        info = ShellInfo(shell_type, "/bin/bash", re.compile(r".*$"))
        cmd = info.get_sentinel_command(uuid)
        assert cmd == f'; echo "__SILC_DONE_{uuid}__:$?"'
    # Windows cmd
    info_cmd = ShellInfo("cmd", "cmd.exe", re.compile(r"[A-Z]:\\.*>"))
    assert (
        info_cmd.get_sentinel_command(uuid)
        == f" & echo __SILC_DONE_{uuid}__:%ERRORLEVEL%"
    )
    # PowerShell
    info_pwsh = ShellInfo("pwsh", "pwsh.exe", re.compile(r"PS .*>"))
    assert (
        info_pwsh.get_sentinel_command(uuid)
        == f'; echo "__SILC_DONE_{uuid}__:$LASTEXITCODE"'
    )
    # Unknown fallback
    info_unknown = ShellInfo("unknown", "/bin/unknown", re.compile(r".*$"))
    assert info_unknown.get_sentinel_command(uuid) == f'; echo "__SILC_DONE_{uuid}__"'
