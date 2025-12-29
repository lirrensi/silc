"""Output cleaning utilities that keep the API output agent-friendly."""

from __future__ import annotations

import re
from typing import Iterable, List

ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
PROGRESS_RE = re.compile(r"\d{1,3}%")


def clean_output(raw_lines: Iterable[str]) -> str:
    cleaned: List[str] = []

    for raw_line in raw_lines:
        line = raw_line

        if "\r" in line:
            line = line.split("\r")[-1]

        line = ANSI_ESCAPE.sub("", line)
        line = line.replace("\r\n", "\n").replace("\r", "\n")

        cleaned.append(line)

    cleaned = collapse_progress_bars(cleaned)

    result: List[str] = []
    blank_count = 0
    for line in cleaned:
        if line.strip():
            result.append(line)
            blank_count = 0
        else:
            blank_count += 1
            if blank_count <= 1:
                result.append(line)

    return "\n".join(result)


def collapse_progress_bars(lines: Iterable[str]) -> List[str]:
    collapsed: List[str] = []
    last_progress: str | None = None

    for line in lines:
        if PROGRESS_RE.search(line):
            last_progress = line
            continue

        if last_progress is not None:
            collapsed.append(last_progress)
            last_progress = None

        collapsed.append(line)

    if last_progress is not None:
        collapsed.append(last_progress)

    return collapsed


__all__ = ["clean_output", "collapse_progress_bars"]
