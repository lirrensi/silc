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

    def wrap_command(self, command: str, token: str, newline: str) -> str:
        """Build a wrapper that prints BEGIN/END markers around a command.

        Uses Write-Host/echo to mark output boundaries in the PTY stream so run()
        can extract just the command's output (not prompts, echoes, or shell noise).
        """

        if self.type == "pwsh":
            begin = f"echo '__SILC_BEGIN_{token}__'"
            # For PowerShell cmdlets, use $? to check success; for external commands, use $LASTEXITCODE
            end = f'if ($?) {{ echo "__SILC_END_{token}__:0" }} else {{ echo "__SILC_END_{token}__:1" }}'
            return f"{begin}; {command}; {end}"

        if self.type == "cmd":
            begin = f"echo __SILC_BEGIN_{token}__"
            end = f"echo __SILC_END_{token}__:%ERRORLEVEL%"
            return newline.join([begin, command, end])

        # POSIX shells (bash/zsh/sh/unknown)
        begin = f'echo "__SILC_BEGIN_{token}__"'
        end = f'ec=$?; echo "__SILC_END_{token}__:$ec"'
        return f"{begin}; {command}; {end}"


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
