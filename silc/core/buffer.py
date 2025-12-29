"""Ring buffer to retain terminal output without unbounded memory growth."""

from __future__ import annotations

from collections import deque
from typing import Iterable, List, Tuple


class RingBuffer:
    """Store the latest terminal lines with cursor-based read semantics."""

    def __init__(self, maxlen: int = 1000):
        self.maxlen = maxlen
        self.lines: deque[str] = deque(maxlen=maxlen)
        self.cursor: int = 0
        self._start_index: int = 0

    def append(self, data: bytes) -> None:
        text = data.decode("utf-8", errors="replace")
        for line in text.splitlines():
            if len(self.lines) == self.maxlen:
                self._start_index += 1
            self.lines.append(line)
            self.cursor += 1

    def get_last(self, n: int = 100) -> List[str]:
        return list(self.lines)[-n:]

    def get_since(self, cursor: int) -> Tuple[List[str], int]:
        cursor = max(cursor, self._start_index)
        buffer_list = list(self.lines)
        relative_start = cursor - self._start_index
        relative_start = min(max(relative_start, 0), len(buffer_list))
        new_lines = buffer_list[relative_start:]
        new_cursor = self._start_index + len(buffer_list)
        return new_lines, new_cursor

    def clear(self) -> None:
        self.lines.clear()
        self.cursor = 0
        self._start_index = 0


__all__ = ["RingBuffer"]
