"""Textual-based TUI for viewing and sending commands to SILC sessions."""

from __future__ import annotations

import asyncio
import contextlib
import json

import requests
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Static
from websockets import connect
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

try:
    from par_term_emu_core_rust import Terminal
except ImportError:  # pragma: no cover
    Terminal = None

KEY_SEQUENCES: dict[str, str] = {
    "enter": "\r",
    "tab": "\t",
    "backspace": "\x7f",
    "delete": "\x1b[3~",
    "insert": "\x1b[2~",
    "up": "\x1b[A",
    "down": "\x1b[B",
    "left": "\x1b[D",
    "right": "\x1b[C",
    "home": "\x1b[H",
    "end": "\x1b[F",
    "pageup": "\x1b[5~",
    "pagedown": "\x1b[6~",
    "escape": "\x1b",
    "ctrl+c": "\x03",
    "ctrl+d": "\x04",
}

MAX_OUTPUT_CHARS = 32_000
TERMINAL_COLS = 120
TERMINAL_ROWS = 30
WS_RECONNECT_DELAY = 1.0


class TerminalOutput(Static):
    """Widget that renders terminal text."""

    can_focus = True

    async def on_key(self, event: events.Key) -> None:
        handler = getattr(self.app, "_handle_terminal_key", None)
        if handler:
            await handler(event)
            event.stop()


class SilcTUI(App):
    CSS = """
    SilcTUI {
        background: #1e1e1e;
    }

    TerminalOutput {
        height: 30;
        width: 120;
        min-height: 30;
        min-width: 120;
        background: #0f0f0f;
        color: #ffffff;
        padding: 1 1 1 1;
        padding-bottom: 1;
        margin-bottom: 1;
        border: round #272727;
        overflow-y: auto;
    }

    Footer {
        dock: bottom;
    }
    """

    def __init__(self, port: int):
        super().__init__()
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self._send_queue: asyncio.Queue[str] | None = None
        self._ws_task: asyncio.Task | None = None
        self._raw_output = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield TerminalOutput(id="output")
        yield Footer()

    async def on_mount(self) -> None:
        self._send_queue = asyncio.Queue()
        await self._send_resize(TERMINAL_ROWS, TERMINAL_COLS)
        await self._load_initial_output()
        output_widget = self.query_one("#output", TerminalOutput)
        self.set_focus(output_widget)
        self._ws_task = asyncio.create_task(self._run_websocket())

    async def on_unmount(self) -> None:
        if self._ws_task:
            self._ws_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ws_task

    async def _run_websocket(self) -> None:
        ws_url = f"ws://127.0.0.1:{self.port}/ws"
        while self.is_running:
            try:
                async with connect(ws_url) as websocket:
                    sender = asyncio.create_task(self._websocket_sender(websocket))
                    receiver = asyncio.create_task(self._websocket_receiver(websocket))
                    done, pending = await asyncio.wait(
                        [sender, receiver],
                        return_when=asyncio.FIRST_EXCEPTION,
                    )
                    for task in pending:
                        task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await task
            except asyncio.CancelledError:
                break
            except (
                ConnectionRefusedError,
                ConnectionClosedError,
                ConnectionClosedOK,
                OSError,
            ):
                await self._append_output(
                    "\r\n--- WebSocket disconnected, retrying ---\r\n"
                )
                await asyncio.sleep(WS_RECONNECT_DELAY)
            except Exception:
                await self._append_output("\r\n--- WebSocket error, retrying ---\r\n")
                await asyncio.sleep(WS_RECONNECT_DELAY)
            else:
                await self._append_output("\r\n--- WebSocket connection closed ---\r\n")
                await asyncio.sleep(WS_RECONNECT_DELAY)

    async def _websocket_receiver(self, websocket) -> None:
        while True:
            try:
                message = await websocket.recv()
            except (ConnectionClosedError, ConnectionClosedOK, asyncio.CancelledError):
                break
            decoded = message
            try:
                payload = json.loads(message)
                if payload.get("event") == "update":
                    decoded = payload.get("data", "")
            except json.JSONDecodeError:
                decoded = message
            if decoded:
                await self._append_output(decoded)

    async def _websocket_sender(self, websocket) -> None:
        queue = self._send_queue
        if queue is None:
            return
        while True:
            try:
                chunk = await queue.get()
            except asyncio.CancelledError:
                break
            if not chunk:
                continue
            payload = json.dumps({"event": "type", "text": chunk, "nonewline": True})
            try:
                await websocket.send(payload)
            except asyncio.CancelledError:
                break
            except (ConnectionClosedError, ConnectionClosedOK):
                break

    async def _append_output(self, data: str) -> None:
        if not data:
            return
        self._raw_output += data
        if len(self._raw_output) > MAX_OUTPUT_CHARS:
            self._raw_output = self._raw_output[-MAX_OUTPUT_CHARS:]
        output_widget = self.query_one("#output", TerminalOutput)
        output_widget.update(self._render_output())

    def _render_output(self) -> Text:
        """Render the current buffer either via par-term or as ANSI text."""
        if Terminal is None:
            return Text.from_ansi(self._raw_output)
        return self._render_with_par_term()

    def _render_with_par_term(self) -> Text:
        """Run the raw stream through par-term so the widget shows the real screen."""
        assert Terminal is not None
        term = Terminal(TERMINAL_COLS, TERMINAL_ROWS)
        term.process_str(self._raw_output)
        lines = term.content().split("\n")
        if len(lines) > TERMINAL_ROWS:
            lines = lines[-TERMINAL_ROWS:]
        elif len(lines) < TERMINAL_ROWS:
            lines.extend([""] * (TERMINAL_ROWS - len(lines)))
        return Text("\n".join(lines))

    def _map_key_event(self, event: events.Key) -> str | None:
        normalized = event.key.lower()
        if normalized in KEY_SEQUENCES:
            return KEY_SEQUENCES[normalized]
        if event.control and event.character:
            character = event.character.lower()
            if "a" <= character <= "z":
                return chr(ord(character) - ord("a") + 1)
        if event.character:
            return event.character
        return None

    async def _handle_terminal_key(self, event: events.Key) -> None:
        mapped = self._map_key_event(event)
        if mapped:
            await self._enqueue_input(mapped)

    async def on_key(self, event: events.Key) -> None:
        if event.default_prevented:
            return
        await self._handle_terminal_key(event)

    async def _enqueue_input(self, value: str) -> None:
        if not value or self._send_queue is None:
            return
        await self._send_queue.put(value)

    async def _send_resize(self, rows: int, cols: int) -> None:
        params = {"rows": rows, "cols": cols}
        try:
            requests.post(f"{self.base_url}/resize", params=params)
        except requests.RequestException:
            pass

    async def _load_initial_output(self) -> None:
        initial = await asyncio.to_thread(self._fetch_initial_output)
        if initial:
            await self._append_output(initial)

    def _fetch_initial_output(self) -> str:
        try:
            resp = requests.get(f"{self.base_url}/raw", timeout=2)
            if resp.ok:
                return resp.json().get("output", "")
        except requests.RequestException:
            pass
        return ""


async def launch_tui(port: int) -> None:
    app = SilcTUI(port)
    await app.run_async()


__all__ = ["SilcTUI", "launch_tui"]
