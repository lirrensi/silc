"""Port management helpers for SILC server discovery."""

from __future__ import annotations

import socket
from contextlib import closing
from typing import Iterable


def find_available_port(start: int = 20000, end: int = 30000) -> int:
    for port in range(start, end):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("Could not find an available port in the requested range.")


__all__ = ["find_available_port"]
