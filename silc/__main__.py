"""Command-line interface entrypoint for SILC."""

from __future__ import annotations

import asyncio
from typing import Optional

import click
import requests
import uvicorn

from .api.server import create_app
from .core.session import SilcSession
from .tui.app import launch_tui
from .utils.ports import find_available_port
from .utils.shell_detect import detect_shell


SESSION_REGISTRY: dict[int, SilcSession] = {}


def _build_server(session: SilcSession, host: str) -> uvicorn.Server:
    app = create_app(session)
    config = uvicorn.Config(app, host=host, port=session.port, log_level="info")
    return uvicorn.Server(config)


@click.group()
def cli() -> None:
    """SILC CLI commands."""


@cli.command()
@click.option("--port", type=int, default=None, help="Port to bind.")
@click.option("--global", "is_global", is_flag=True, help="Bind to 0.0.0.0.")
def start(port: Optional[int], is_global: bool) -> None:
    """Start a new SILC session."""
    port = port or find_available_port(20000, 21000)
    shell_info = detect_shell()
    session = SilcSession(port, shell_info)
    SESSION_REGISTRY[port] = session

    async def _serve() -> None:
        await session.start()
        host = "0.0.0.0" if is_global else "127.0.0.1"
        server = _build_server(session, host)
        click.echo(f"✨ SILC session started at port {port}")
        click.echo(f"   Session ID: {session.session_id}")
        click.echo(f"   Shell: {shell_info.type}")
        click.echo(f"   Use: silc {port} out")
        click.echo(f"   Open TUI: silc open {port}")
        await server.serve()

    asyncio.run(_serve())


@cli.command()
@click.argument("port", type=int)
@click.argument("lines", default=100, type=int)
def out(port: int, lines: int) -> None:
    """Fetch the latest output."""
    resp = requests.get(f"http://127.0.0.1:{port}/out", params={"lines": lines})
    print(resp.json().get("output", ""))


@cli.command(name="in")
@click.argument("port", type=int)
@click.argument("text", nargs=-1)
def in_(port: int, text: tuple[str, ...]) -> None:
    """Send raw input to the session."""
    text_str = " ".join(text)
    resp = requests.post(f"http://127.0.0.1:{port}/in", json={"text": text_str})
    print(resp.json().get("status"))


@cli.command()
@click.argument("port", type=int)
@click.argument("command", nargs=-1)
@click.option("--timeout", default=60)
def run(port: int, command: tuple[str, ...], timeout: int) -> None:
    """Run a command inside the SILC shell."""
    cmd = " ".join(command)
    resp = requests.post(
        f"http://127.0.0.1:{port}/run", json={"command": cmd, "timeout": timeout}
    )
    result = resp.json()
    print(result.get("output", ""))
    if err := result.get("error"):
        click.echo(f"Error: {err}", err=True)


@cli.command()
@click.argument("port", type=int)
def status(port: int) -> None:
    """Show session status."""
    resp = requests.get(f"http://127.0.0.1:{port}/status")
    status_info = resp.json()
    click.echo(f"Session: {status_info.get('session_id')}")
    click.echo(f"Alive: {status_info.get('alive')}")
    click.echo(f"Idle: {status_info.get('idle_seconds')}s")
    if status_info.get("waiting_for_input"):
        click.echo(f"⚠️  Waiting for input: {status_info.get('last_line')}")


@cli.command(name="list")
def list_sessions() -> None:
    """List registered sessions for this process."""
    if SESSION_REGISTRY:
        for port, session in SESSION_REGISTRY.items():
            click.echo(f"{port}: {session.session_id} ({session.shell_info.type})")
    else:
        click.echo("No sessions registered yet.")


@cli.command()
@click.argument("port", type=int)
def open(port: int) -> None:
    """Open the Textual TUI."""
    asyncio.run(launch_tui(port))


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
