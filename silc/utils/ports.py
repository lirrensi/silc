"""Port management helpers for SILC server discovery."""

from __future__ import annotations

import socket
from contextlib import closing
from typing import Iterable

from silc.config import get_config


def find_available_port(
    start: int | None = None, end: int | None = None, max_attempts: int | None = None
) -> int:
    """Find an available port in the specified range.

    Args:
        start: Starting port number. If None, uses config default.
        end: Ending port number. If None, uses config default.
        max_attempts: Maximum number of ports to try. If None, uses config default.

    Returns:
        Available port number

    Raises:
        RuntimeError: If no available port found in range
    """
    config = get_config()

    if start is None:
        start = config.ports.session_start
    if end is None:
        end = config.ports.session_end
    if max_attempts is None:
        max_attempts = config.ports.max_attempts

    attempts = 0
    for port in range(start, end):
        if attempts >= max_attempts:
            break
        attempts += 1

        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port

    raise RuntimeError(
        f"Could not find an available port in range {start}-{end} after {max_attempts} attempts. "
        "All ports may be in use or blocked."
    )


def bind_port(host: str, port: int, backlog: int = 64) -> socket.socket:
    """Bind to the supplied host/port and return the listening socket."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setblocking(False)
    try:
        sock.bind((host, port))
        sock.listen(backlog)
    except OSError:
        sock.close()
        raise
    return sock


__all__ = ["find_available_port", "bind_port"]
