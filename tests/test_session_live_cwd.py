# FILE: tests/test_session_live_cwd.py
# PURPOSE: Verify live cwd prompt updates are tracked without requiring a PTY backend.
# OWNS: Session cwd listener and status coverage using a dummy PTY.
# DOCS: agent_chat/plan_hidden_cwd_prompt_2026-04-05.md

from __future__ import annotations

from dataclasses import dataclass
import re

from silc.core.session import SilcSession
from silc.utils.shell_detect import ShellInfo


@dataclass
class _DummyPTY:
    async def read(self, size: int) -> bytes:
        return b""

    async def write(self, data: bytes) -> None:
        return None

    def resize(self, rows: int, cols: int) -> None:
        return None

    def is_alive(self) -> bool:
        return True

    def kill(self) -> None:
        return None

    def send_sigterm(self) -> None:
        return None

    def send_sigkill(self) -> None:
        return None


def test_session_status_tracks_live_cwd(monkeypatch) -> None:
    monkeypatch.setattr(
        "silc.core.session.create_pty", lambda *args, **kwargs: _DummyPTY()
    )

    shell_info = ShellInfo("pwsh", "pwsh.exe", re.compile(r".*"))
    session = SilcSession(
        port=20003,
        name="cwd-test",
        shell_info=shell_info,
        cwd="/tmp/seed",
    )
    events: list[str] = []
    session.add_cwd_listener(lambda updated: events.append(updated.cwd or ""))

    session._apply_cwd("/tmp/project")

    status = session.get_status()
    assert status["cwd"] == "/tmp/project"
    assert events == ["/tmp/project"]


def test_session_status_uses_incremental_metadata(monkeypatch) -> None:
    monkeypatch.setattr(
        "silc.core.session.create_pty", lambda *args, **kwargs: _DummyPTY()
    )

    shell_info = ShellInfo("pwsh", "pwsh.exe", re.compile(r".*"))
    session = SilcSession(port=20004, name="status-test", shell_info=shell_info)

    session._update_status_metadata(b"__SILC_BEGIN_deadbeef__\r\nworking...\r\nready]")
    monkeypatch.setattr(
        session,
        "get_rendered_output",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("render used")),
    )

    status = session.get_status()

    assert status["last_line"] == "ready]"
    assert status["waiting_for_input"] is True
