"""Terminal session picker helpers for `silc pick`."""

# FILE: silc/utils/session_picker.py
# PURPOSE: Build and run the prompt_toolkit session picker for `silc pick`.
# OWNS: Session roster normalization, picker row construction, selection math, and the interactive prompt_toolkit app.
# EXPORTS: SessionRow - normalized session data; PickerRow - rendered menu row; PickerChoice - picker result; fetch_session_rows - daemon roster fetch; build_picker_rows - menu rows; move_selection - index navigation; run_session_picker - public picker entrypoint; run_session_picker_app - injectable app runner.
# DOCS: docs/spec.md, docs/arch_cli.md, docs/arch_tui.md

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Sequence

import click
import requests
from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import AnyFormattedText, StyleAndTextTuples
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Frame

from silc.daemon import DAEMON_PORT


@dataclass(frozen=True, slots=True)
class SessionRow:
    name: str
    port: int
    shell: str | None
    cwd: str | None
    alive: bool


@dataclass(frozen=True, slots=True)
class PickerRow:
    kind: Literal["session", "create"]
    label: str
    session: SessionRow | None = None


@dataclass(frozen=True, slots=True)
class PickerChoice:
    kind: Literal["session", "create"]
    port: int | None = None


AppRunner = Callable[[Sequence[PickerRow]], PickerChoice | None]
Writer = Callable[[str], None]


def fetch_session_rows(timeout: float = 5.0) -> tuple[list[SessionRow], str | None]:
    """Fetch and normalize the daemon session roster."""

    try:
        resp = requests.get(f"http://127.0.0.1:{DAEMON_PORT}/sessions", timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError):
        return [], "SILC daemon is not running"

    if not isinstance(payload, list):
        return [], "SILC daemon is not running"

    rows: list[SessionRow] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        port = item.get("port")
        if not isinstance(port, int):
            continue
        rows.append(
            SessionRow(
                name=str(item.get("name") or f"session-{port}"),
                port=port,
                shell=str(item.get("shell")) if item.get("shell") is not None else None,
                cwd=str(item.get("cwd")) if item.get("cwd") is not None else None,
                alive=bool(item.get("alive")),
            )
        )

    return rows, None


def build_picker_rows(session_rows: Sequence[SessionRow]) -> list[PickerRow]:
    """Build picker menu rows with create-new last."""

    rows = [
        PickerRow(kind="session", label=format_session_label(row), session=row)
        for row in session_rows
    ]
    rows.append(PickerRow(kind="create", label="Create new session here"))
    return rows


def format_session_label(session: SessionRow) -> str:
    """Format a picker row label for a session."""

    state = "alive" if session.alive else "ended"
    shell = session.shell or "?"
    cwd = _shorten_text(session.cwd or "?", 44)
    return f"{session.name}  •  port {session.port}  •  {shell}  •  {state}  •  {cwd}"


def move_selection(current: int, key: str, total_rows: int) -> int:
    """Move the highlighted row for a key press."""

    if total_rows <= 0:
        return 0
    if key in {"up", "k"}:
        return (current - 1) % total_rows
    if key in {"down", "j"}:
        return (current + 1) % total_rows
    if key == "home":
        return 0
    if key == "end":
        return total_rows - 1
    return current


def run_session_picker(
    *,
    writer: Writer = click.echo,
    fetch_rows: Callable[[], tuple[list[SessionRow], str | None]] = fetch_session_rows,
    app_runner: AppRunner | None = None,
) -> PickerChoice | None:
    """Fetch rows, render the picker, and return the chosen action."""

    rows, warning = fetch_rows()
    if warning:
        writer(warning)

    menu_rows = build_picker_rows(rows)
    if app_runner is None and not _interactive_terminal_available():
        return None

    runner = app_runner or run_session_picker_app
    return runner(menu_rows)


def run_session_picker_app(rows: Sequence[PickerRow]) -> PickerChoice | None:
    """Run the prompt_toolkit picker app for the provided rows."""

    app = _build_picker_application(rows)
    try:
        return app.run()
    except EOFError:
        return None


def _build_picker_application(
    rows: Sequence[PickerRow],
) -> Application[PickerChoice | None]:
    state = _PickerState(rows=list(rows))

    title = Window(
        content=FormattedTextControl(_title_text),
        height=1,
        dont_extend_height=True,
    )
    instructions = Window(
        content=FormattedTextControl(_instruction_text),
        height=1,
        dont_extend_height=True,
    )
    list_control = FormattedTextControl(
        text=lambda: _render_picker_rows(state.rows, state.selected_index),
        focusable=True,
    )
    list_window = Window(
        content=list_control,
        height=Dimension(min=1),
        always_hide_cursor=True,
        dont_extend_height=False,
    )
    footer = Window(
        content=FormattedTextControl(_footer_text),
        height=1,
        dont_extend_height=True,
    )

    body = HSplit(
        [
            title,
            instructions,
            _blank_line(),
            Frame(list_window, title="Sessions"),
            _blank_line(),
            footer,
        ]
    )

    kb = KeyBindings()
    _bind_navigation_keys(kb, state)
    _bind_selection_keys(kb, state)

    return Application(
        layout=Layout(body, focused_element=list_control),
        key_bindings=kb,
        style=_picker_style(),
        full_screen=False,
        mouse_support=False,
        erase_when_done=True,
    )


@dataclass(slots=True)
class _PickerState:
    rows: list[PickerRow]
    selected_index: int = 0


def _bind_navigation_keys(kb: KeyBindings, state: _PickerState) -> None:
    @kb.add("up")
    @kb.add("k")
    def _move_up(event) -> None:
        state.selected_index = move_selection(
            state.selected_index, "up", len(state.rows)
        )
        event.app.invalidate()

    @kb.add("down")
    @kb.add("j")
    def _move_down(event) -> None:
        state.selected_index = move_selection(
            state.selected_index, "down", len(state.rows)
        )
        event.app.invalidate()

    @kb.add("home")
    def _move_home(event) -> None:
        state.selected_index = move_selection(
            state.selected_index, "home", len(state.rows)
        )
        event.app.invalidate()

    @kb.add("end")
    def _move_end(event) -> None:
        state.selected_index = move_selection(
            state.selected_index, "end", len(state.rows)
        )
        event.app.invalidate()


def _bind_selection_keys(kb: KeyBindings, state: _PickerState) -> None:
    @kb.add("enter")
    def _accept(event) -> None:
        event.app.exit(result=_choice_for_selection(state))

    @kb.add("escape")
    @kb.add("c-c")
    def _cancel(event) -> None:
        event.app.exit(result=None)


def _choice_for_selection(state: _PickerState) -> PickerChoice | None:
    if not state.rows:
        return None
    row = state.rows[state.selected_index]
    if row.kind == "create":
        return PickerChoice(kind="create")
    if row.session is None:
        return None
    return PickerChoice(kind="session", port=row.session.port)


def _render_picker_rows(
    rows: Sequence[PickerRow], selected_index: int
) -> AnyFormattedText:
    fragments: StyleAndTextTuples = []
    for index, row in enumerate(rows):
        is_selected = index == selected_index
        prefix_style = "class:selected-prefix" if is_selected else "class:prefix"
        row_style = "class:selected-row" if is_selected else "class:row"
        fragments.append((prefix_style, "➜ " if is_selected else "  "))
        fragments.append((row_style, row.label))
        if index < len(rows) - 1:
            fragments.append(("", "\n"))
    return fragments


def _title_text() -> StyleAndTextTuples:
    return [("class:title", "Choose a session")]


def _instruction_text() -> StyleAndTextTuples:
    return [
        (
            "class:hint",
            "Up/Down or j/k to move • Home/End jump • Enter opens • Esc/C-c cancels",
        )
    ]


def _footer_text() -> StyleAndTextTuples:
    return [("class:footer", "Create-new row stays last.")]


def _blank_line() -> Window:
    return Window(content=FormattedTextControl(""), height=1, style="class:separator")


def _picker_style() -> Style:
    return Style.from_dict(
        {
            "title": "bold #9cdcfe",
            "hint": "#a6accd",
            "footer": "#7f8caa",
            "separator": "#2f3447",
            "prefix": "#6b7280",
            "row": "#d4d4d4",
            "selected-prefix": "bold #ffffff",
            "selected-row": "bold reverse #ffffff",
        }
    )


def _interactive_terminal_available() -> bool:
    return _stdin_is_tty() and _stdout_is_tty()


def _stdin_is_tty() -> bool:
    import sys

    return bool(getattr(sys.stdin, "isatty", lambda: False)())


def _stdout_is_tty() -> bool:
    import sys

    return bool(getattr(sys.stdout, "isatty", lambda: False)())


def _shorten_text(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return "..." + value[-(max_length - 3) :]
