"""Cross-platform PTY management for SILC sessions."""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from abc import ABC, abstractmethod
from typing import Any, Mapping, Optional


class PTYBase(ABC):
    """Abstract PTY interface used by SILC session logic."""

    def __init__(self, shell_cmd: Optional[str], env: Mapping[str, str]):
        self.shell_cmd = shell_cmd
        self.env = dict(env)
        self.pid: int | None = None

    @abstractmethod
    async def read(self, size: int = 1024) -> bytes: ...

    @abstractmethod
    async def write(self, data: bytes) -> None: ...

    @abstractmethod
    def resize(self, rows: int, cols: int) -> None: ...

    @abstractmethod
    def kill(self) -> None: ...


class StubPTY(PTYBase):
    """Fallback PTY used when a platform-specific backend cannot be loaded."""

    async def read(self, size: int = 1024) -> bytes:
        await asyncio.sleep(0.1)
        return b""

    async def write(self, data: bytes) -> None:
        await asyncio.sleep(0.01)

    def resize(self, rows: int, cols: int) -> None:
        return None

    def kill(self) -> None:
        return None


class UnixPTY(PTYBase):
    """Unix PTY backed by the standard library `pty` module."""

    def __init__(self, shell_cmd: Optional[str], env: Mapping[str, str]):
        super().__init__(shell_cmd, env)
        import fcntl
        import pty
        import struct
        import termios

        self._master_fd, slave_fd = pty.openpty()
        self._slave_fd = slave_fd

        shell = shell_cmd or os.environ.get("SHELL", "/bin/bash")
        if isinstance(shell, str):
            args = [shell]
        else:
            args = list(shell)

        self._process = subprocess.Popen(
            args,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env=self.env,
            close_fds=True,
            preexec_fn=os.setsid,
        )
        self.pid = self._process.pid
        os.close(slave_fd)
        self._struct = struct
        self._termios = termios
        self._fcntl = fcntl

    async def read(self, size: int = 1024) -> bytes:
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, os.read, self._master_fd, size)
        except OSError:
            return b""

    async def write(self, data: bytes) -> None:
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, os.write, self._master_fd, data)
        except OSError:
            return None

    def resize(self, rows: int, cols: int) -> None:
        dims = self._struct.pack("HHHH", rows, cols, 0, 0)
        self._fcntl.ioctl(self._master_fd, self._termios.TIOCSWINSZ, dims)

    def kill(self) -> None:
        import psutil

        if self.pid:
            try:
                proc = psutil.Process(self.pid)
                try:
                    proc.kill()
                except psutil.NoSuchProcess:
                    pass
            except psutil.NoSuchProcess:
                pass
            except Exception:
                pass

        if hasattr(self, "_master_fd"):
            try:
                os.close(self._master_fd)
            except OSError:
                pass


class WindowsPTY(PTYBase):
    """Windows PTY via the pywinpty/winpty bindings."""

    def __init__(self, shell_cmd: Optional[str], env: Mapping[str, str]):
        super().__init__(shell_cmd, env)
        self._pty_handle: Any | None = None
        winpty_module = self._load_winpty_module()
        command = shell_cmd or os.environ.get("COMSPEC", "cmd.exe")
        if hasattr(winpty_module, "PtyProcess"):
            self._process = winpty_module.PtyProcess.spawn(command, env=self.env)
        elif hasattr(winpty_module, "PTY"):
            self._pty_handle = winpty_module.PTY(cols=120, rows=30)
            self._process = self._pty_handle.spawn(command, env=self.env)
        else:
            raise RuntimeError("winpty/pywinpty does not expose a usable PTY backend.")
        self.pid = getattr(self._process, "pid", None)

    async def read(self, size: int = 1024) -> bytes:
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, self._read_sync, size)
        except OSError:
            return b""

    async def write(self, data: bytes) -> None:
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, self._write_sync, data)
        except OSError:
            return None

    def resize(self, rows: int, cols: int) -> None:
        """Resize the underlying Windows PTY.

        The `winpty.PtyProcess` backend exposes `setwinsize(rows, cols)` (not
        `set_size`). If we fail to resize here, the backend stays at its default
        dimensions (commonly 80x24) while the web UI assumes 120x30, which can
        cause prompt/cursor drift and output/input interleaving.
        """

        # PtyProcess API (winpty 3.x)
        target = getattr(self._process, "setwinsize", None)
        if callable(target):
            try:
                target(rows, cols)
            except OSError:
                pass
            return

        # Legacy API variants
        target = getattr(self._process, "set_size", None)
        if callable(target):
            try:
                target(rows, cols)
            except OSError:
                pass
            return

        if self._pty_handle and hasattr(self._pty_handle, "set_size"):
            try:
                self._pty_handle.set_size(rows, cols)
            except OSError:
                pass

    def kill(self) -> None:
        import psutil

        pid = getattr(self._process, "pid", None)
        if pid:
            try:
                proc = psutil.Process(pid)
                children = proc.children(recursive=True)
                all_procs = [proc] + children

                for p in all_procs:
                    try:
                        p.terminate()
                    except psutil.NoSuchProcess:
                        pass
                    except Exception:
                        pass

                gone, alive = psutil.wait_procs(all_procs, timeout=0.5)
                for p in alive:
                    try:
                        p.kill()
                    except psutil.NoSuchProcess:
                        pass
                    except Exception:
                        pass
                psutil.wait_procs(alive, timeout=0.3)
            except psutil.NoSuchProcess:
                pass
            except Exception:
                pass

        for method_name in ("kill", "terminate", "close"):
            method = getattr(self._process, method_name, None)
            if callable(method):
                try:
                    method()
                except OSError:
                    pass
                except Exception:
                    pass
                break
        if self._pty_handle and hasattr(self._pty_handle, "close"):
            try:
                self._pty_handle.close()
            except OSError:
                pass

    def _read_sync(self, size: int) -> bytes:
        chunk = self._process.read(size)
        if not chunk:
            return b""
        if isinstance(chunk, str):
            return chunk.encode("utf-8", errors="replace")
        return chunk

    def _write_sync(self, data: bytes) -> None:
        try:
            self._process.write(data)
        except TypeError:
            self._process.write(data.decode("utf-8", errors="replace"))


    def _load_winpty_module(self) -> Any:
        """Load the winpty module required for Windows PTY support.

        Returns:
            The winpty module

        Raises:
            RuntimeError: If winpty is not installed
        """
        try:
            import winpty as module
        except ImportError as winpty_error:
            raise RuntimeError(
                "winpty is required on Windows to run SILC."
            ) from winpty_error
        return module


def create_pty(
    shell_cmd: Optional[str] = None, env: Optional[Mapping[str, str]] = None
) -> PTYBase:
    """Factory that returns the best available PTY implementation."""

    env = dict(env or os.environ.copy())
    if sys.platform == "win32":
        return WindowsPTY(shell_cmd, env)
    if sys.platform.startswith("linux") or sys.platform == "darwin":
        return UnixPTY(shell_cmd, env)
    return StubPTY(shell_cmd, env)


__all__ = ["PTYBase", "StubPTY", "create_pty"]
