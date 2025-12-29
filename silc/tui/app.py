"""Textual-based TUI for viewing and sending commands to SILC sessions."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Vertical
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
    }
    """

    def __init__(self, port: int):
        super().__init__()
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"

    def compose(self) -> ComposeResult:
        yield Header()
        yield TerminalOutput(id="output")
        yield Input(placeholder="Type command and press Enter")
        yield Footer()

    async def on_mount(self) -> None:
        self.set_interval(0.5, self._update_output)

    async def _update_output(self) -> None:
        try:
            resp = requests.get(f"{self.base_url}/out?raw=true&lines=50")
            output = resp.json().get("output", "")
            self.query_one("#output", TerminalOutput).update(output)
        except requests.RequestException:
            pass

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        try:
            requests.post(f"{self.base_url}/in", json={"text": text + "\n"})
        except requests.RequestException:
            pass
        event.input.value = ""


async def launch_tui(port: int) -> None:
    app = SilcTUI(port)
    await app.run_async()


__all__ = ["SilcTUI", "launch_tui"]
