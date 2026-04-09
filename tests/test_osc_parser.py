# FILE: tests/test_osc_parser.py
# PURPOSE: Verify OSC parsing for titles, hidden cwd markers, and hidden command markers.
# OWNS: Parser coverage for PTY prompt metadata and registry command/cwd persistence.
# DOCS: agent_chat/plan_hidden_cwd_prompt_2026-04-05.md

"""Tests for OSC title parsing and registry title updates."""

from silc.core.osc import OscHiddenCommandParser, OscHiddenCwdParser, OscTitleParser
from silc.daemon.registry import SessionRegistry


def test_osc_title_parser_handles_bel_and_st() -> None:
    parser = OscTitleParser()

    assert parser.feed(b"noise \x1b]0;first") == []
    assert parser.feed(b" title\x07 more") == ["first title"]
    assert parser.feed(b"\x1b]2;second\x1b\\") == ["second"]


def test_osc_cwd_parser_handles_encoded_paths() -> None:
    parser = OscHiddenCwdParser()

    assert parser.feed(b"noise \x1b]633;cwd=C%3A%5CTemp") == []
    assert parser.feed(b"%20Files\x07 more") == ["C:\\Temp Files"]
    assert parser.feed(b"\x1b]633;cwd=%2Ftmp%2Fproject\x1b\\") == ["/tmp/project"]


def test_osc_command_parser_handles_hidden_command_payloads() -> None:
    parser = OscHiddenCommandParser()

    assert parser.feed(b"noise \x1b]633;cmd=git status") == []
    assert parser.feed(b"\x07 more") == ["git status"]
    assert parser.feed(b"\x1b]633;cmd=echo hello\x1b\\") == ["echo hello"]


def test_registry_update_title_updates_persistence_shape() -> None:
    registry = SessionRegistry()
    registry.add(20000, "test-session", "abc12345", "bash")

    assert registry.get(20000).title == ""

    entry = registry.update_title(20000, "new terminal title")

    assert entry is not None
    assert entry.title == "new terminal title"
    assert entry.to_json()["title"] == "new terminal title"


def test_registry_update_cwd_updates_persistence_shape() -> None:
    registry = SessionRegistry()
    registry.add(20000, "test-session", "abc12345", "bash", cwd="/tmp")

    entry = registry.update_cwd(20000, "/tmp/project")

    assert entry is not None
    assert entry.cwd == "/tmp/project"
    assert entry.to_json()["cwd"] == "/tmp/project"


def test_registry_update_command_updates_persistence_shape() -> None:
    registry = SessionRegistry()
    registry.add(20000, "test-session", "abc12345", "bash")

    command = {
        "text": "echo hello",
        "source": "shell",
        "start_ts": "2026-04-09T00:00:00Z",
    }
    entry = registry.update_command(20000, command)

    assert entry is not None
    assert entry.command == command
    assert entry.to_json()["command"] == command
