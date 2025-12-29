"""Tiny helpers to detect the active shell and generate sentinel commands."""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from typing import Pattern


@dataclass
class ShellInfo:
    type: str
    path: str
    prompt_pattern: Pattern[str]

    def get_sentinel_command(self, uuid: str) -> str:
        if self.type in {"bash", "zsh", "sh"}:
            return f"; echo \"__SILC_DONE_{uuid}__:$?\""
        if self.type == "cmd":
            return f" & echo __SILC_DONE_{uuid}__:%ERRORLEVEL%"
        if self.type == "pwsh":
            return f"; echo \"__SILC_DONE_{uuid}__:$LASTEXITCODE\""
        return f"; echo \"__SILC_DONE_{uuid}__\""


def detect_shell() -> ShellInfo:
    if sys.platform == "win32":
        if os.environ.get("PSModulePath"):
            return ShellInfo("pwsh", "pwsh.exe", re.compile(r"PS .*>"))
        return ShellInfo("cmd", "cmd.exe", re.compile(r"[A-Z]:\\.*>"))
    shell_path = os.environ.get("SHELL", "/bin/bash")
    shell_name = os.path.basename(shell_path)
    if "zsh" in shell_name:
        prompt = re.compile(r".*[%#$] $")
        return ShellInfo("zsh", shell_path, prompt)
    if "bash" in shell_name:
        prompt = re.compile(r".*[$#] $")
        return ShellInfo("bash", shell_path, prompt)
    prompt = re.compile(r"[$#] $")
    return ShellInfo(shell_name or "sh", shell_path, prompt)


__all__ = ["ShellInfo", "detect_shell"]
