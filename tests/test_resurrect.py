"""Tests for session persistence and resurrect feature."""

import json
from pathlib import Path

import pytest

from silc.utils.persistence import (
    SESSIONS_FILE,
    append_session_to_json,
    read_sessions_json,
    remove_session_from_json,
    write_sessions_json,
)


def test_read_sessions_json_empty(tmp_path, monkeypatch):
    """Test reading when file doesn't exist."""
    monkeypatch.setattr(
        "silc.utils.persistence.SESSIONS_FILE", tmp_path / "sessions.json"
    )
    from silc.utils import persistence

    persistence.SESSIONS_FILE = tmp_path / "sessions.json"

    result = read_sessions_json()
    assert result == []


def test_write_and_read_sessions_json(tmp_path):
    """Test write/read roundtrip."""
    from silc.utils import persistence

    persistence.SESSIONS_FILE = tmp_path / "sessions.json"

    sessions = [{"port": 20000, "name": "test", "shell": "bash"}]
    write_sessions_json(sessions)

    result = read_sessions_json()
    assert len(result) == 1
    assert result[0]["name"] == "test"


def test_append_session_to_json(tmp_path):
    """Test appending a session."""
    from silc.utils import persistence

    persistence.SESSIONS_FILE = tmp_path / "sessions.json"

    append_session_to_json({"port": 20000, "name": "first"})
    append_session_to_json({"port": 20001, "name": "second"})

    result = read_sessions_json()
    assert len(result) == 2


def test_append_replaces_duplicate(tmp_path):
    """Test that appending with same port/name replaces existing."""
    from silc.utils import persistence

    persistence.SESSIONS_FILE = tmp_path / "sessions.json"

    append_session_to_json({"port": 20000, "name": "original"})
    append_session_to_json({"port": 20000, "name": "replaced"})

    result = read_sessions_json()
    assert len(result) == 1
    assert result[0]["name"] == "replaced"


def test_remove_session_from_json(tmp_path):
    """Test removing a session by port."""
    from silc.utils import persistence

    persistence.SESSIONS_FILE = tmp_path / "sessions.json"

    write_sessions_json(
        [
            {"port": 20000, "name": "first"},
            {"port": 20001, "name": "second"},
        ]
    )

    remove_session_from_json(20000)

    result = read_sessions_json()
    assert len(result) == 1
    assert result[0]["port"] == 20001
