from pathlib import Path
from types import SimpleNamespace

import pytest

from silc.daemon.settings import build_path_update, deep_merge_settings
from silc.utils import persistence


def _patch_log_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    monkeypatch.setattr(persistence, "LOGS_DIR", logs_dir)
    monkeypatch.setattr(persistence, "DAEMON_LOG", logs_dir / "daemon.log")
    return logs_dir


def _patch_settings_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(persistence, "SETTINGS_FILE", settings_file)
    return settings_file


def test_daemon_log_rotation_trims_old_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_log_paths(tmp_path, monkeypatch)

    persistence.write_daemon_log("first")
    persistence.write_daemon_log("second")
    persistence.write_daemon_log("third")

    persistence.rotate_daemon_log(max_lines=2)
    lines = persistence.DAEMON_LOG.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert "first" not in "\n".join(lines)


def test_session_logs_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_log_paths(tmp_path, monkeypatch)
    port = 45000

    persistence.write_session_log(port, "first entry")
    persistence.write_session_log(port, "second entry")
    content = persistence.read_session_log(port)
    assert "first entry" in content
    assert "second entry" in content

    persistence.rotate_session_log(port, max_lines=1)
    trimmed = persistence.read_session_log(port)
    assert "first entry" not in trimmed
    assert "second entry" in trimmed

    persistence.cleanup_session_log(port)
    assert persistence.read_session_log(port) == ""


def test_remove_session_artifacts_clears_session_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    logs_dir = _patch_log_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(persistence, "SESSIONS_FILE", tmp_path / "sessions.json")
    monkeypatch.setattr(persistence, "SNAPSHOTS_DIR", tmp_path / "snapshots")

    persistence.SESSIONS_FILE.write_text('{"sessions": []}', encoding="utf-8")
    persistence.SNAPSHOTS_DIR.mkdir(parents=True)
    persistence.write_session_snapshot("abc123", b"snapshot")
    session_log = logs_dir / "session_12345.log"
    session_log.write_text("session log", encoding="utf-8")
    persistence.DAEMON_LOG.write_text("daemon log", encoding="utf-8")

    persistence.remove_session_artifacts()

    assert not persistence.SESSIONS_FILE.exists()
    assert not persistence.SNAPSHOTS_DIR.exists()
    assert not session_log.exists()
    assert persistence.DAEMON_LOG.exists()


def test_purge_silc_data_removes_data_and_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    log_dir = tmp_path / "logs"
    data_dir.mkdir()
    log_dir.mkdir()
    (data_dir / "sessions.json").write_text('{"sessions": []}', encoding="utf-8")
    (log_dir / "daemon.log").write_text("daemon log", encoding="utf-8")

    fake_config = SimpleNamespace(
        paths=SimpleNamespace(data_dir=data_dir, log_dir=log_dir)
    )
    monkeypatch.setattr("silc.config.get_config", lambda: fake_config)

    persistence.purge_silc_data()

    assert not data_dir.exists()
    assert not log_dir.exists()


def test_settings_json_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_file = _patch_settings_path(tmp_path, monkeypatch)

    payload = {
        "ui": {"themePreference": "dark"},
        "terminal": {"fontSize": 18, "theme": "light"},
    }

    persistence.write_settings_json(payload)

    assert settings_file.exists()
    assert persistence.read_settings_json() == payload


def test_settings_helpers_deep_merge_nested_values() -> None:
    base = {
        "ui": {"themePreference": "system"},
        "terminal": {"fontSize": 15, "cursorBlink": True},
    }
    update = build_path_update("terminal.fontSize", 20)

    merged = deep_merge_settings(base, update)

    assert merged == {
        "ui": {"themePreference": "system"},
        "terminal": {"fontSize": 20, "cursorBlink": True},
    }
