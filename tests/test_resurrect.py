"""Tests for session persistence and resurrect feature."""

import pytest

from silc.utils.persistence import (
    SESSIONS_FILE,
    append_session_to_json,
    garbage_collect_session_snapshots,
    list_session_snapshot_ids,
    read_session_snapshot,
    read_sessions_json,
    remove_session_from_json,
    remove_session_snapshot,
    write_session_snapshot,
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

    sessions = [
        {
            "port": 20000,
            "name": "test",
            "title": "test",
            "shell": "bash",
            "title_updated_at": "2026-01-01T00:00:00Z",
        }
    ]
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
    append_session_to_json({"port": 20000, "name": "replaced", "title": "updated"})

    result = read_sessions_json()
    assert len(result) == 1
    assert result[0]["name"] == "replaced"
    assert result[0]["title"] == "updated"


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


def test_session_snapshot_helpers(tmp_path, monkeypatch):
    from silc.utils import persistence

    monkeypatch.setattr(persistence, "SNAPSHOTS_DIR", tmp_path / "snapshots")
    persistence.SNAPSHOTS_DIR = tmp_path / "snapshots"

    write_session_snapshot("abc123", b"hello world")
    assert read_session_snapshot("abc123") == b"hello world"
    assert list_session_snapshot_ids() == {"abc123"}

    write_session_snapshot("orphan", b"bye")
    removed = garbage_collect_session_snapshots({"abc123"})

    assert removed == ["orphan"]
    assert read_session_snapshot("orphan") == b""

    remove_session_snapshot("abc123")
    assert read_session_snapshot("abc123") == b""
