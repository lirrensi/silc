"""Helper test for inspecting raw PTY output before decoding."""

import sys
import time

import pytest

from tests._winpty_helpers import (
    normalize_chunk,
    spawn_winpty_process,
    terminate_process,
)


@pytest.mark.skipif(sys.platform != "win32", reason="winpty is Windows-only")
def test_winpty_dump_raw_output() -> None:
    """Open a PTY, wait a second, read once, and print the raw bytes."""

    process = spawn_winpty_process()
    try:
        time.sleep(4)
        chunk = process.read(4096)
        normalized = normalize_chunk(chunk)
        print("raw chunk repr:", repr(normalized))
        assert normalized
    finally:
        terminate_process(process)


# test_winpty_dump_raw_output()
