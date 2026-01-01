"""Textual-based TUI for viewing and sending commands to SILC sessions."""

from __future__ import annotations

from textual import events
from textual.app import App, ComposeResult
from rich.text import Text
from textual.widgets import Footer, Header, Input, Static

import requests


class TerminalOutput(Static):
    """Widget that renders terminal text."""


class SilcTUI(App):
    CSS = """
    TerminalOutput {
        height: 1fr;
        background: black;
        color: white;
        overflow-y: scroll;
    }

    Input {
        dock: bottom;
        padding: 0 1;
        background: #111;
        color: white;
        min-height: 1;
    }
    """

    def __init__(self, port: int):
        super().__init__()
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self._input_widget: Input | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield TerminalOutput(id="output")
        yield Input(placeholder="Type command and press Enter", id="prompt")
        yield Footer()

    async def on_mount(self) -> None:
        self.set_interval(0.5, self._update_output)
        self._input_widget = self.query_one("#prompt", Input)
        if self._input_widget is not None:
            self.set_focus(self._input_widget)
        rows, cols = self._current_dimensions()
        await self._send_resize(rows, cols)

    async def _update_output(self) -> None:
        try:
            resp = requests.get(f"{self.base_url}/out?lines=50")
            output = resp.json().get("output", "")
            rendered = Text.from_ansi(output)
            self.query_one("#output", TerminalOutput).update(rendered)
        except requests.RequestException:
            pass

    async def on_resize(self, event: events.Resize) -> None:
        await self._send_resize(event.height, event.width)

    async def _send_resize(self, rows: int, cols: int) -> None:
        params = {"rows": rows, "cols": cols}
        try:
            requests.post(f"{self.base_url}/resize", params=params)
        except requests.RequestException:
            pass

    def _current_dimensions(self) -> tuple[int, int]:
        size = self.console.size
        return size.height, size.width

    async def _post_to_input(self, payload: str, nonewline: bool = False) -> None:
        params = {"nonewline": "true"} if nonewline else {}
        headers = {"Content-Type": "text/plain; charset=utf-8"}
        try:
            requests.post(
                f"{self.base_url}/in",
                params=params,
                data=payload,
                headers=headers,
            )
        except requests.RequestException:
            pass

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        payload = event.value
        event.input.value = ""
        await self._post_to_input(payload)

    async def on_key(self, event: events.Key) -> None:
        if self._input_widget is None or not self._input_widget.has_focus:
            return

        if event.character == "\x03":
            await self._post_to_input("\x03", nonewline=True)
            event.stop()
            return

        if event.character == "\x04":
            await self._post_to_input("\x04", nonewline=True)
            event.stop()
            return


async def launch_tui(port: int) -> None:
    app = SilcTUI(port)
    await app.run_async()


__all__ = ["SilcTUI", "launch_tui"]
