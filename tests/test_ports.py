import socket
import sys
from contextlib import closing

import pytest

from silc.utils.ports import bind_port, find_available_port


def _lock_socket(sock: socket.socket) -> None:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)


def test_find_available_port_within_range() -> None:
    port = find_available_port(start=25030, end=25040)
    assert 25030 <= port < 25040

    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", port))
        sock.listen(1)


@pytest.mark.skipif(
    sys.platform.startswith("win32"),
    reason="Windows socket locking has compatibility issues with SO_EXCLUSIVEADDRUSE",
)
def test_find_available_port_raises_when_exhausted() -> None:
    occupied_sockets = []
    try:
        for port in range(25050, 25052):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            _lock_socket(sock)
            sock.bind(("127.0.0.1", port))
            sock.listen(1)
            occupied_sockets.append(sock)

        with pytest.raises(RuntimeError):
            find_available_port(start=25050, end=25052)
    finally:
        for sock in occupied_sockets:
            sock.close()


@pytest.mark.skipif(
    sys.platform.startswith("win32"), reason="Windows socket locking order differs"
)
def test_bind_port_raises_for_conflicting_port() -> None:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        _lock_socket(sock)
        sock.bind(("127.0.0.1", 26000))
        sock.listen(1)

        with pytest.raises(OSError):
            bind_port("127.0.0.1", 26000)
