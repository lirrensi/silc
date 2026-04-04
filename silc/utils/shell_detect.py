"""Tiny helpers to detect the active shell and generate sentinel commands."""

from __future__ import annotations

import os
import re
import shlex
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Pattern


@dataclass
class ShellInfo:
    type: str
    path: str
    prompt_pattern: Pattern[str]

    def get_helper_function(self) -> str | None:
        """Return a shell-specific helper definition that prints SILC markers."""

        if self.type in {"pwsh", "powershell"}:
            return (
                "function __silc_exec($cmd, $token) { "
                '$prompt = "PS $($PWD.Path)> "; '  # Build prompt string
                "Write-Host -NoNewline $prompt; "  # Print prompt
                "Write-Host $cmd; "  # Print command
                'Write-Host "__SILC_BEGIN_${token}__"; '
                "Invoke-Expression $cmd; "
                "$exitCode = $LASTEXITCODE; "
                "if ($null -eq $exitCode) { $exitCode = 0 }; "
                'Write-Host "__SILC_END_${token}__:${exitCode}" '
                "}"
            )

        if self.type in {"bash", "zsh", "sh"}:
            return (
                "__silc_exec() { "
                'printf "__SILC_BEGIN_$2__\\n"; '
                'eval "$1"; '
                'printf "__SILC_END_$2__:%d\\n" $?; '
                "}"
            )

        if self.type == "cmd":
            helper_path = self._ensure_cmd_helper()
            return f'doskey __silc_exec=call "{helper_path}" $1 $2'

        # Default to POSIX helper for any other shell type.
        return (
            "__silc_exec() { "
            'printf "__SILC_BEGIN_$2__\\n"; '
            'eval "$1"; '
            'printf "__SILC_END_$2__:%d\\n" $?; '
            "}"
        )

    def build_helper_invocation(self, command: str, token: str) -> str:
        """Construct the single-line invocation that calls the helper."""

        if self.type in {"pwsh", "powershell"}:
            escaped = command.replace("'", "''")
            return f"__silc_exec '{escaped}' '{token}'"

        if self.type in {"bash", "zsh", "sh"}:
            return f"__silc_exec {shlex.quote(command)} {shlex.quote(token)}"

        if self.type == "cmd":
            escaped = command.replace('"', '""')
            return f'__silc_exec "{escaped}" {token}'

        return f"__silc_exec {shlex.quote(command)} {shlex.quote(token)}"

    def _ensure_cmd_helper(self) -> str:
        script_path = Path(tempfile.gettempdir()) / "__silc_exec.bat"
        if script_path.exists():
            return str(script_path)

        script_content = (
            "@echo off\r\n"
            "echo __SILC_BEGIN_%2__\r\n"
            "call %1\r\n"
            "echo __SILC_END_%2__:%ERRORLEVEL%\r\n"
        )
        script_path.write_text(script_content, encoding="utf-8")
        return str(script_path)


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


def get_shell_info_by_type(shell_type: str) -> ShellInfo | None:
    """Get ShellInfo for a specific shell type, or None if unknown."""
    shell_type = shell_type.lower()

    if shell_type == "pwsh":
        path = _resolve_executable("pwsh", "pwsh.exe") or "pwsh.exe"
        return ShellInfo("pwsh", path, re.compile(r"PS .*>"))
    if shell_type == "powershell":
        path = _resolve_executable("powershell", "powershell.exe") or "powershell.exe"
        return ShellInfo("powershell", path, re.compile(r"PS .*>"))
    if shell_type == "cmd":
        path = (
            _resolve_executable(os.environ.get("COMSPEC", ""), "cmd", "cmd.exe")
            or "cmd.exe"
        )
        return ShellInfo("cmd", path, re.compile(r"[A-Z]:\\.*>"))
    if shell_type == "bash":
        path = _resolve_executable(os.environ.get("SHELL", ""), "bash") or "bash"
        return ShellInfo("bash", path, re.compile(r".*[$#] $"))
    if shell_type == "zsh":
        path = _resolve_executable(os.environ.get("SHELL", ""), "zsh") or "zsh"
        return ShellInfo("zsh", path, re.compile(r".*[%#$] $"))
    if shell_type == "sh":
        path = _resolve_executable(os.environ.get("SHELL", ""), "sh") or "sh"
        return ShellInfo("sh", path, re.compile(r"[$#] $"))

    return None


@dataclass(frozen=True)
class ShellChoice:
    type: str
    label: str
    path: str


def _shell_label(shell_type: str) -> str:
    return {
        "pwsh": "PowerShell",
        "powershell": "Windows PowerShell",
        "cmd": "Command Prompt",
        "bash": "Bash",
        "zsh": "Zsh",
        "sh": "Shell",
    }.get(shell_type, shell_type)


def _resolve_executable(*candidates: str) -> str | None:
    for candidate in candidates:
        if not candidate:
            continue

        if Path(candidate).is_file():
            return candidate

        resolved = shutil.which(candidate)
        if resolved:
            return resolved

    return None


def _available_shell_choices_windows() -> list[ShellChoice]:
    choices: list[ShellChoice] = []

    for shell_type, candidates in [
        ("pwsh", ("pwsh", "pwsh.exe")),
        ("powershell", ("powershell", "powershell.exe")),
        ("cmd", (os.environ.get("COMSPEC", ""), "cmd", "cmd.exe")),
    ]:
        path = _resolve_executable(*candidates)
        if path:
            choices.append(ShellChoice(shell_type, _shell_label(shell_type), path))

    return choices


def _available_shell_choices_posix() -> list[ShellChoice]:
    choices: list[ShellChoice] = []
    current_shell = os.environ.get("SHELL", "")
    current_shell_type = Path(current_shell).name.lower() if current_shell else ""

    preferred_order = []
    if current_shell_type in {"bash", "zsh", "sh"}:
        preferred_order.append(current_shell_type)
    for shell_type in ("zsh", "bash", "sh"):
        if shell_type not in preferred_order:
            preferred_order.append(shell_type)

    for shell_type in preferred_order:
        if (
            current_shell
            and Path(current_shell).name.lower() == shell_type
            and Path(current_shell).is_file()
        ):
            path = current_shell
        else:
            path = _resolve_executable(shell_type)
        if path:
            choices.append(ShellChoice(shell_type, _shell_label(shell_type), path))

    return choices


def get_available_shell_choices() -> list[ShellChoice]:
    """Return the shell choices that appear to be installed on this system."""

    if sys.platform == "win32":
        return _available_shell_choices_windows()

    return _available_shell_choices_posix()


__all__ = [
    "ShellChoice",
    "ShellInfo",
    "detect_shell",
    "get_available_shell_choices",
    "get_shell_info_by_type",
]
