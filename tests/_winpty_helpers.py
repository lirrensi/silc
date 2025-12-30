"""Shared helpers for the Windows winpty smoke tests."""

from __future__ import annotations

import signal
import time
from typing import Any

import pytest


def _load_winpty_module() -> Any:
    try:
        import winpty as module
    except ImportError:
        pytest.skip("winpty/pywinpty bindings are required on Windows")
    return module


def spawn_winpty_process(command: str | None = None) -> Any:
    module = _load_winpty_module()
    shell_command = command or "cmd.exe"
    if hasattr(module, "PtyProcess"):
        return module.PtyProcess.spawn(shell_command, env=None)
    if hasattr(module, "PTY"):
        pty = module.PTY(cols=80, rows=24)
        return pty.spawn(shell_command, env=None)
    pytest.skip("winpty module does not expose a spawnable PTY")


def decode_chunk(chunk: bytes | str | None) -> str:
    if not chunk:
        return ""
    if isinstance(chunk, bytes):
        return chunk.decode("utf-8", errors="ignore")
    return chunk


def normalize_chunk(chunk: bytes | str | None) -> bytes:
    if not chunk:
        return b""
    if isinstance(chunk, str):
        return chunk.encode("utf-8", errors="ignore")
    return chunk


def collect_output(process: Any, expected: str, timeout: float = 2.0) -> str:
    deadline = time.time() + timeout
    fragments: list[str] = []
    while time.time() < deadline:
        chunk = process.read(4096)
        decoded = decode_chunk(chunk)
        if decoded:
            fragments.append(decoded)
            if expected in decoded:
                return "".join(fragments)
        else:
            time.sleep(0.05)
    pytest.fail(
        f"Timed out waiting for {expected!r} (timeout={timeout}s). Output so far: {''.join(fragments)}"
    )


def terminate_process(process: Any) -> None:
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            process.kill(sig)
            return
        except TypeError:
            break
        except Exception:
            continue
    try:
        process.kill()
    except Exception:
        pass
