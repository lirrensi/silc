from pathlib import Path

import pytest

from silc.utils import persistence


def _patch_log_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    monkeypatch.setattr(persistence, "LOGS_DIR", logs_dir)
    monkeypatch.setattr(persistence, "DAEMON_LOG", logs_dir / "daemon.log")
    return logs_dir


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
