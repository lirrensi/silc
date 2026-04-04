"""OSC control-sequence parsers used by the PTY read loop."""

from __future__ import annotations

from dataclasses import dataclass, field

OSC_ESCAPE = 0x1B
OSC_BELL = 0x07
OSC_ST = ord("\\")


@dataclass
class OscTitleParser:
    """Extract terminal titles from OSC 0/2 sequences."""

    _state: str = "idle"
    _buffer: bytearray = field(default_factory=bytearray)

    def feed(self, data: bytes) -> list[str]:
        titles: list[str] = []

        for byte in data:
            if self._state == "idle":
                if byte == OSC_ESCAPE:
                    self._state = "escape"
                continue

            if self._state == "escape":
                if byte == ord("]"):
                    self._buffer.clear()
                    self._state = "osc"
                else:
                    self._state = "idle"
                continue

            if self._state == "osc":
                if byte == OSC_BELL:
                    title = self._finalize()
                    if title is not None:
                        titles.append(title)
                    continue

                if byte == OSC_ESCAPE:
                    self._state = "osc_escape"
                    continue

                self._buffer.append(byte)
                continue

            if self._state == "osc_escape":
                if byte == OSC_ST:
                    title = self._finalize()
                    if title is not None:
                        titles.append(title)
                else:
                    self._buffer.append(OSC_ESCAPE)
                    if byte == OSC_BELL:
                        title = self._finalize()
                        if title is not None:
                            titles.append(title)
                    else:
                        self._buffer.append(byte)
                        self._state = "osc"

        return titles

    def _finalize(self) -> str | None:
        payload = self._buffer.decode("utf-8", errors="replace")
        self._buffer.clear()
        self._state = "idle"

        if ";" not in payload:
            return None

        command, title = payload.split(";", 1)
        if command not in {"0", "2"}:
            return None

        return title


__all__ = ["OscTitleParser"]
