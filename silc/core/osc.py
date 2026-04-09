# FILE: silc/core/osc.py
# PURPOSE: Parse OSC title, hidden cwd, and hidden command markers from PTY output.
# OWNS: OSC payload framing, title extraction, and hidden metadata decoding.
# EXPORTS: OscTitleParser - extract OSC 0/2 titles; OscHiddenCwdParser - extract OSC 633 cwd markers; OscHiddenCommandParser - extract OSC 633 command markers.
# DOCS: agent_chat/plan_hidden_cwd_prompt_2026-04-05.md

"""OSC control-sequence parsers used by the PTY read loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import unquote

OSC_ESCAPE = 0x1B
OSC_BELL = 0x07
OSC_ST = ord("\\")


@dataclass
class _OscSequenceParser:
    _state: str = "idle"
    _buffer: bytearray = field(default_factory=bytearray)

    def feed(self, data: bytes) -> list[str]:
        items: list[str] = []

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
                    item = self._finalize()
                    if item is not None:
                        items.append(item)
                    continue

                if byte == OSC_ESCAPE:
                    self._state = "osc_escape"
                    continue

                self._buffer.append(byte)
                continue

            if self._state == "osc_escape":
                if byte == OSC_ST:
                    item = self._finalize()
                    if item is not None:
                        items.append(item)
                else:
                    self._buffer.append(OSC_ESCAPE)
                    if byte == OSC_BELL:
                        item = self._finalize()
                        if item is not None:
                            items.append(item)
                    else:
                        self._buffer.append(byte)
                        self._state = "osc"

        return items

    def _finalize(self) -> str | None:
        payload = self._buffer.decode("utf-8", errors="replace")
        self._buffer.clear()
        self._state = "idle"
        return self._parse_payload(payload)

    def _parse_payload(self, payload: str) -> str | None:
        raise NotImplementedError


@dataclass
class OscTitleParser(_OscSequenceParser):
    """Extract terminal titles from OSC 0/2 sequences."""

    def _parse_payload(self, payload: str) -> str | None:
        if ";" not in payload:
            return None

        command, title = payload.split(";", 1)
        if command not in {"0", "2"}:
            return None

        return title


@dataclass
class OscHiddenCwdParser(_OscSequenceParser):
    """Extract hidden cwd markers from OSC 633;cwd payloads."""

    def _parse_payload(self, payload: str) -> str | None:
        if not payload.startswith("633;cwd="):
            return None

        encoded_path = payload.removeprefix("633;cwd=")
        if not encoded_path:
            return None

        return unquote(encoded_path)


@dataclass
class OscHiddenCommandParser(_OscSequenceParser):
    """Extract hidden command markers from OSC 633;cmd payloads."""

    def _parse_payload(self, payload: str) -> str | None:
        if not payload.startswith("633;cmd="):
            return None

        command_text = payload.removeprefix("633;cmd=")
        if not command_text:
            return None

        return unquote(command_text)


__all__ = ["OscTitleParser", "OscHiddenCwdParser", "OscHiddenCommandParser"]
