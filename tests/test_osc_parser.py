"""Tests for OSC title parsing and registry title updates."""

from silc.core.osc import OscTitleParser
from silc.daemon.registry import SessionRegistry


def test_osc_title_parser_handles_bel_and_st() -> None:
    parser = OscTitleParser()

    assert parser.feed(b"noise \x1b]0;first") == []
    assert parser.feed(b" title\x07 more") == ["first title"]
    assert parser.feed(b"\x1b]2;second\x1b\\") == ["second"]


def test_registry_update_title_updates_persistence_shape() -> None:
    registry = SessionRegistry()
    registry.add(20000, "test-session", "abc12345", "bash")

    assert registry.get(20000).title == ""

    entry = registry.update_title(20000, "new terminal title")

    assert entry is not None
    assert entry.title == "new terminal title"
    assert entry.to_json()["title"] == "new terminal title"
