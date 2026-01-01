"""Byte-accurate buffer that preserves raw PTY output for replay and parsing."""

from __future__ import annotations

from typing import List, Tuple


class RawByteBuffer:
    """Store PTY bytes along with a cursor so callers can replay ranges."""

    def __init__(self, maxlen: int = 65536) -> None:
        self.maxlen = maxlen
        self._buffer = bytearray()
        self._start_offset = 0
        self._total_bytes = 0
        self.cursor = 0

    def append(self, data: bytes) -> None:
        """Add new bytes and trim the buffer to honor maxlen."""
        if not data:
            return

        self._buffer.extend(data)
        self._total_bytes += len(data)
        self.cursor = self._total_bytes

        if len(self._buffer) <= self.maxlen:
            return

        overflow = len(self._buffer) - self.maxlen
        del self._buffer[:overflow]
        self._start_offset += overflow

    def get_last(self, lines: int | None = 100) -> List[str]:
        """Return the decoded text split into the last N logical lines."""
        if not self._buffer:
            return []

        decoded = self._buffer.decode("utf-8", errors="replace")
        split_lines = decoded.splitlines()
        if lines is None or lines >= len(split_lines):
            return split_lines
        return split_lines[-lines:]

    def get_since(self, cursor: int) -> Tuple[bytes, int]:
        """Return all bytes that were appended since ``cursor``."""
        if cursor < self._start_offset:
            cursor = self._start_offset

        if cursor > self._total_bytes:
            cursor = self._total_bytes

        start_index = cursor - self._start_offset
        start_index = max(start_index, 0)
        if start_index >= len(self._buffer):
            return b"", self._total_bytes

        chunk = bytes(self._buffer[start_index:])
        return chunk, self._total_bytes

    def clear(self) -> None:
        """Reset the buffer to an empty state."""
        self._buffer.clear()
        self._start_offset = 0
        self._total_bytes = 0
        self.cursor = 0

    def get_bytes(self) -> bytes:
        """Return a copy of the queued bytes for rehydration."""
        return bytes(self._buffer)


__all__ = ["RawByteBuffer"]
