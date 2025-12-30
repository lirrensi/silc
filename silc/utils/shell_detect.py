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
            return f'; echo "__SILC_DONE_{uuid}__:$?"'
        if self.type == "cmd":
            return f" & echo __SILC_DONE_{uuid}__:%ERRORLEVEL%"
        if self.type == "pwsh":
            return f'; echo "__SILC_DONE_{uuid}__:$LASTEXITCODE"'
        return f'; echo "__SILC_DONE_{uuid}__"'


def detect_shell() -> ShellInfo:
    """Detect current shell, with safe fallback if detection fails."""
    try:
        if sys.platform == "win32":
            # PowerShell detection
            if os.environ.get("PSModulePath"):
                return ShellInfo("pwsh", "pwsh.exe", re.compile(r"PS .*>"))
            # Fallback to cmd.exe
            return ShellInfo("cmd", "cmd.exe", re.compile(r"[A-Z]:\\.*>"))
        # Unix-like detection
        shell_path = os.environ.get("SHELL", "/bin/bash")
        shell_name = os.path.basename(shell_path)
        if "zsh" in shell_name:
            return ShellInfo("zsh", shell_path, re.compile(r".*[%#$] $"))
        if "bash" in shell_name:
            return ShellInfo("bash", shell_path, re.compile(r".*[$#] $"))
        # Generic POSIX shell fallback
        return ShellInfo("sh", shell_path, re.compile(r"[$#] $"))
    except Exception:
        # Ultimate fallback to /bin/sh
        return ShellInfo("sh", "/bin/sh", re.compile(r"[$#] $"))


__all__ = ["ShellInfo", "detect_shell"]
