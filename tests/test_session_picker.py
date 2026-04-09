"""Unit tests for the Python session picker."""

from __future__ import annotations

from click.testing import CliRunner

from silc import __main__ as main_mod
from silc.utils.session_picker import (
    PickerChoice,
    SessionRow,
    build_picker_rows,
    move_selection,
    run_session_picker,
)


def test_build_picker_rows_keeps_create_last():
    rows = [
        SessionRow(
            name="alpha",
            port=20001,
            shell="bash",
            cwd="/tmp/a",
            alive=True,
            command="echo alpha",
        ),
        SessionRow(name="beta", port=20002, shell="zsh", cwd="/tmp/b", alive=False),
    ]

    menu_rows = build_picker_rows(rows)

    assert [row.kind for row in menu_rows] == ["session", "session", "create"]
    assert menu_rows[-1].label == "Create new session here"
    assert "cmd echo alpha" in menu_rows[0].label


def test_move_selection_supports_navigation():
    assert move_selection(0, "down", 3) == 1
    assert move_selection(0, "up", 3) == 2
    assert move_selection(0, "k", 3) == 2
    assert move_selection(2, "j", 3) == 0
    assert move_selection(2, "home", 3) == 0
    assert move_selection(0, "end", 3) == 2


def test_pick_launches_native_tui_for_existing_session(monkeypatch):
    calls: dict[str, object] = {}

    monkeypatch.setattr(
        main_mod,
        "run_session_picker",
        lambda: PickerChoice(kind="session", port=20001),
    )
    monkeypatch.setattr(
        main_mod,
        "_launch_native_tui_client",
        lambda port: calls.setdefault("port", port),
    )

    runner = CliRunner()
    result = runner.invoke(main_mod.cli, ["pick"])

    assert result.exit_code == 0
    assert calls["port"] == 20001


def test_pick_starts_new_session_with_native_tui(monkeypatch):
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        main_mod,
        "run_session_picker",
        lambda: PickerChoice(kind="create"),
    )

    def fake_start(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs

    monkeypatch.setattr(main_mod.start, "callback", fake_start)

    runner = CliRunner()
    result = runner.invoke(main_mod.cli, ["pick"])

    assert result.exit_code == 0
    assert captured["kwargs"]["launch_native_tui"] is True


def test_picker_uses_injectable_app_runner_without_terminal():
    captured: dict[str, object] = {}

    def fake_fetch():
        return [
            SessionRow(name="alpha", port=20001, shell="bash", cwd=None, alive=True)
        ], None

    def fake_runner(rows):
        captured["rows"] = list(rows)
        return PickerChoice(kind="session", port=20001)

    result = run_session_picker(fetch_rows=fake_fetch, app_runner=fake_runner)

    assert result == PickerChoice(kind="session", port=20001)
    assert [row.kind for row in captured["rows"]] == ["session", "create"]


def test_picker_keeps_create_action_available_when_roster_fetch_fails():
    output: list[str] = []

    def fake_fetch():
        return [], "SILC daemon is not running"

    def fake_runner(rows):
        assert rows[-1].label == "Create new session here"
        return PickerChoice(kind="create")

    result = run_session_picker(
        writer=output.append,
        fetch_rows=fake_fetch,
        app_runner=fake_runner,
    )

    assert result == PickerChoice(kind="create")
    assert any("SILC daemon is not running" in line for line in output)
