"""Command-line interface entrypoint for SILC."""

from __future__ import annotations

# Adjust sys.path to include a sibling virtual environment (venv or venv-win) when running from a .pyz.
import sys
import pathlib
import sysconfig

script_path = pathlib.Path(sys.argv[0]).resolve()
repo_root = script_path.parent.parent
venv_name = "venv-win" if sys.platform.startswith("win") else "venv"
venv_path = repo_root / venv_name
if sys.platform.startswith("win"):
    site_pkg = venv_path / "Lib" / "site-packages"
else:
    site_pkg = (
        venv_path
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )
if site_pkg.is_dir():
    sys.path.insert(0, str(site_pkg))


import asyncio
import secrets
import subprocess
import time
import webbrowser
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import click
import requests
import uvicorn

from silc.api.server import create_app
from silc.core.session import SilcSession
from silc.tui.app import launch_tui
from silc.utils.ports import find_available_port
from .utils.shell_detect import detect_shell
from silc.daemon import is_daemon_running, kill_daemon, DAEMON_PORT


def _daemon_url(path: str) -> str:
    return f"http://127.0.0.1:{DAEMON_PORT}{path}"


def _daemon_available(timeout: float = 2.0) -> bool:
    try:
        requests.get(_daemon_url("/sessions"), timeout=timeout)
        return True
    except requests.RequestException:
        return False


def _daemon_port_open(timeout: float = 0.2) -> bool:
    """Best-effort check whether something is listening on the daemon port."""

    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex(("127.0.0.1", DAEMON_PORT)) == 0


def _wait_for_daemon_stop(timeout: float = 10.0) -> bool:
    """Wait until the daemon port is closed (or a deadline is reached)."""

    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _daemon_port_open(timeout=0.15):
            return True
        time.sleep(0.2)
    return not _daemon_port_open(timeout=0.15)


def _wait_for_daemon_start(timeout: float = 10.0) -> bool:
    """Wait until daemon is available to accept requests (or deadline reached)."""

    deadline = time.time() + timeout
    while time.time() < deadline:
        if _daemon_available(timeout=0.5):
            return True
        time.sleep(0.3)
    return _daemon_available(timeout=0.5)


def _wait_for_daemon_start_with_logs(timeout: float = 10.0) -> bool:
    """Wait until daemon is available, showing startup logs as they appear."""
    from silc.utils.persistence import DAEMON_LOG, LOGS_DIR

    deadline = time.time() + timeout
    last_log_size = 0

    if DAEMON_LOG.exists():
        last_log_size = DAEMON_LOG.stat().st_size

    while time.time() < deadline:
        if _daemon_available(timeout=0.5):
            return True

        time.sleep(0.3)

        if DAEMON_LOG.exists():
            try:
                current_size = DAEMON_LOG.stat().st_size
                if current_size > last_log_size:
                    new_content = DAEMON_LOG.read_bytes()[last_log_size:].decode(
                        "utf-8", errors="replace"
                    )
                    for line in new_content.splitlines():
                        if line.strip():
                            click.echo(f"  [daemon] {line}", err=False)
                    last_log_size = current_size
            except Exception:
                pass

    return _daemon_available(timeout=0.5)


def _show_daemon_error_details() -> None:
    """Show available error information from daemon startup."""
    try:
        from silc.utils.persistence import DAEMON_LOG, LOGS_DIR

        if DAEMON_LOG.exists():
            click.echo(f"\n📋 Daemon log: {DAEMON_LOG}", err=True)
            try:
                last_lines = DAEMON_LOG.read_text(encoding="utf-8").splitlines()
                if last_lines:
                    click.echo("Last 20 log lines:", err=True)
                    for line in last_lines[-20:]:
                        click.echo(f"  {line}", err=True)
            except Exception:
                click.echo("  (unable to read log)", err=True)
        else:
            click.echo(f"\n📋 Daemon log not found at: {DAEMON_LOG}", err=True)

        stderr_log = LOGS_DIR / "daemon_stderr.log"
        if stderr_log.exists():
            click.echo(f"\n📋 Daemon stderr: {stderr_log}", err=True)
            try:
                stderr_content = stderr_log.read_text(encoding="utf-8")
                if stderr_content:
                    click.echo("Last 20 lines:", err=True)
                    for line in stderr_content.splitlines()[-20:]:
                        click.echo(f"  {line}", err=True)
            except Exception:
                click.echo("  (unable to read stderr)", err=True)
    except Exception as e:
        click.echo(f"\n⚠️  Could not fetch daemon error details: {e}", err=True)


def _fetch_session_token(port: int, timeout: float = 2.0) -> str | None:
    """Try to fetch the token for a running session (local only)."""
    try:
        resp = requests.get(f"http://127.0.0.1:{port}/token", timeout=timeout)
        resp.raise_for_status()
        return resp.json().get("token")
    except requests.RequestException:
        return None
    except ValueError:
        return None


def _get_session_entry(port: int) -> dict | None:
    """Return daemon session info for a specific port."""
    try:
        resp = requests.get(_daemon_url("/sessions"), timeout=5)
        resp.raise_for_status()
        sessions = resp.json()
    except requests.RequestException:
        return None

    for entry in sessions:
        if entry.get("port") == port:
            return entry
    return None


def _get_error_detail(response: requests.Response | None) -> str:
    if response is None:
        return "unknown error"
    try:
        data = response.json()
    except ValueError:
        return response.text or response.reason or "unknown error"
    msg = data.get("detail") or data.get("error")
    if not msg:
        msg = str(data)
    return msg or "unknown error"


SESSION_REGISTRY: dict[int, SilcSession] = {}


def _build_server(session: SilcSession, host: str) -> uvicorn.Server:
    app = create_app(session)
    config = uvicorn.Config(app, host=host, port=session.port, log_level="info")
    return uvicorn.Server(config)


class PortGroup(click.Group):
    def __init__(self, port: int, **kwargs):
        self.port = port
        super().__init__(**kwargs)

    def invoke(self, ctx):
        ctx.params["port"] = self.port
        return super().invoke(ctx)


class SilcCLI(click.Group):
    port_subcommands = click.Group()

    def get_command(self, ctx, cmd_name):
        if cmd_name.isdigit():
            return PortGroup(int(cmd_name), commands=self.port_subcommands.commands)
        return super().get_command(ctx, cmd_name)

    def list_commands(self, ctx):
        commands = super().list_commands(ctx)
        return [c for c in commands if c != "port"]


@click.group(cls=SilcCLI, invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """SILC CLI commands."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command()
@click.option("--port", type=int, default=None, help="Port for session")
@click.option(
    "--global", "is_global", is_flag=True, help="Bind to 0.0.0.0 (for legacy mode)."
)
@click.option(
    "--no-detach", is_flag=True, help="Run daemon in foreground (not detached)."
)
@click.option(
    "--token",
    type=str,
    default=None,
    help="Custom token for remote session API (hex string).",
)
def start(
    port: Optional[int],
    is_global: bool,
    no_detach: bool,
    token: Optional[str],
) -> None:
    """Start a new SILC session (creates daemon if needed)."""
    normalized_token = token.strip() if token else None
    session_token: str | None = normalized_token
    generated_token = False
    if is_global and not session_token:
        session_token = secrets.token_hex(18)
        generated_token = True

    if session_token:
        auto_note = " (auto-generated)" if generated_token else ""
        click.echo(
            f"🔐 Session token{auto_note}: {session_token} "
            "(send via Authorization: Bearer <token>)"
        )

    if is_global:
        click.echo(
            click.style(
                "⚠️  SECURITY WARNING: --global exposes the session to the network.",
                fg="red",
                bold=True,
            ),
            err=True,
        )
        click.echo(
            click.style(
                "   This allows Remote Code Execution (RCE) on your machine!",
                fg="red",
                bold=True,
            ),
            err=True,
        )
        click.echo(
            click.style(
                "   Only use this on trusted networks behind a firewall.",
                fg="red",
            ),
            err=True,
        )
        click.echo("", err=True)
        if not normalized_token:
            click.echo(
                "   Re-run 'silc start --global --token <your-token>' to keep a stable "
                "token for remote clients.",
                err=True,
                fg="red",
            )

    daemon_responsive = _daemon_available()
    daemon_running = daemon_responsive or is_daemon_running()

    if daemon_running:
        if daemon_responsive:
            click.echo("✓ Daemon is already running and responsive", err=False)
        else:
            # Try to connect to verify it's responsive
            try:
                requests.get(_daemon_url("/sessions"), timeout=2)
                click.echo("✓ Daemon is running and responsive", err=False)
            except requests.RequestException:
                # Daemon is not responsive
                click.echo("⚠️  Daemon is running but unresponsive.", err=True)
                choice = input("Kill and restart daemon? [y/N]: ").strip().lower()
                if choice == "y":
                    kill_daemon(port=DAEMON_PORT, force=True, timeout=2.0)
                    time.sleep(1)
                else:
                    click.echo("Aborted.")
                    return
    else:
        # Daemon not running, start it
        if no_detach:
            click.echo("Starting daemon in foreground...")
            from silc.daemon.manager import SilcDaemon

            daemon = SilcDaemon()
            asyncio.run(daemon.start())
            return
        else:
            # Start detached daemon
            click.echo("Starting daemon in background...", err=False)
            _start_detached_daemon()
            click.echo("Waiting for daemon to start...", err=False)
            started = _wait_for_daemon_start_with_logs(timeout=10)
            if not started:
                click.echo(
                    "❌ Failed to start daemon (timed out waiting for it to be available)",
                    err=True,
                )
                _show_daemon_error_details()
                choice = (
                    input("Kill existing daemon process and restart? [y/N]: ")
                    .strip()
                    .lower()
                )
                if choice == "y":
                    kill_daemon(port=DAEMON_PORT, force=True, timeout=2.0)
                    time.sleep(1)
                    click.echo("Restarting daemon...", err=False)
                    _start_detached_daemon()
                    started = _wait_for_daemon_start_with_logs(timeout=10)
                    if not started:
                        click.echo(
                            "❌ Failed to start daemon again (timed out)",
                            err=True,
                        )
                        _show_daemon_error_details()
                        return
                else:
                    click.echo("Aborted.")
                    return
            else:
                click.echo("✓ Daemon started successfully", err=False)

    # Daemon is running, create session
    click.echo("Creating new session...", err=False)
    try:
        payload: dict[str, object] = {}
        if port is not None:
            payload["port"] = port
        if is_global:
            payload["is_global"] = True
        if session_token:
            payload["token"] = session_token
        resp = requests.post(_daemon_url("/sessions"), json=payload, timeout=5)
        resp.raise_for_status()
        session = resp.json()
        click.echo(f"✨ SILC session started at port {session['port']}")
        click.echo(f"   Session ID: {session['session_id']}")
        click.echo(f"   Shell: {session['shell']}")
        click.echo(f"   Use: silc {session['port']} out")
    except requests.HTTPError as e:
        response = e.response
        detail = _get_error_detail(response)
        if port and response and response.status_code == 400:
            existing = _get_session_entry(port)
            if existing:
                detail = f"Port {port} is already in use (existing session id {existing['session_id']})"
        click.echo(f"❌ Failed to create session: {detail}", err=True)
    except requests.RequestException as e:
        click.echo(f"❌ Failed to create session: {e}", err=True)


def _get_daemon_python_executable() -> str:
    """Prefer pythonw on Windows so no console is shown."""
    python = Path(sys.executable)
    if sys.platform == "win32":
        pythonw = python.with_name("pythonw.exe")
        if pythonw.exists():
            return str(pythonw)
    return str(python)


def _start_detached_daemon() -> None:
    """Start daemon in background (detached)."""
    python_exec = _get_daemon_python_executable()

    stderr_log_path = None
    try:
        from silc.utils.persistence import LOGS_DIR

        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        stderr_log_path = LOGS_DIR / "daemon_stderr.log"
        stderr_handle = open(stderr_log_path, "a", encoding="utf-8")
    except Exception:
        stderr_handle = subprocess.PIPE

    cmd = [python_exec, "-m", "silc", "daemon"]
    common_kwargs = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": stderr_handle,
    }

    if sys.platform == "win32":
        creationflags = (
            subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.DETACHED_PROCESS
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        subprocess.Popen(
            cmd,
            creationflags=creationflags,
            startupinfo=startupinfo,
            **common_kwargs,
        )
    else:
        subprocess.Popen(cmd, start_new_session=True, **common_kwargs)


@cli.command(name="daemon", hidden=True)
def run_as_daemon() -> None:
    """Internal command: run as daemon (do not call directly)."""
    from silc.daemon.manager import SilcDaemon

    daemon = SilcDaemon()
    asyncio.run(daemon.start())


@cli.group()
@click.argument("port", type=int)
def port(port: int) -> None:
    """Session-specific commands."""


@cli.port_subcommands.command()
@click.pass_context
@click.argument("lines", default=100, type=int)
def out(ctx: click.Context, lines: int) -> None:
    """Fetch the latest output."""
    port = ctx.parent.params["port"] if ctx.parent else 0 if ctx.parent else 0
    try:
        resp = requests.get(
            f"http://127.0.0.1:{port}/out", params={"lines": lines}, timeout=5
        )
        if resp.status_code == 410:
            click.echo(f"❌ Session on port {port} has ended", err=True)
            return
        resp.raise_for_status()
        print(resp.json().get("output", ""))
    except requests.RequestException as e:
        click.echo(f"❌ Session on port {port} does not exist", err=True)


@cli.port_subcommands.command(name="in")
@click.pass_context
@click.argument("text", nargs=-1)
def in_(ctx: click.Context, text: tuple[str, ...]) -> None:
    """Send raw input to the session."""
    port = ctx.parent.params["port"] if ctx.parent else 0 if ctx.parent else 0
    text_str = " ".join(text)
    try:
        resp = requests.post(
            f"http://127.0.0.1:{port}/in",
            data=text_str.encode("utf-8"),
            headers={"Content-Type": "text/plain; charset=utf-8"},
            timeout=5,
        )
        if resp.status_code == 410:
            click.echo(f"❌ Session on port {port} has ended", err=True)
            return
        resp.raise_for_status()
        print(resp.json().get("status"))
    except requests.RequestException:
        click.echo(f"❌ Session on port {port} does not exist", err=True)


@cli.port_subcommands.command()
@click.pass_context
@click.argument("command", nargs=-1)
@click.option("--timeout", default=60)
def run(ctx: click.Context, command: tuple[str, ...], timeout: int) -> None:
    """Run a command inside the SILC shell."""
    port = ctx.parent.params["port"] if ctx.parent else 0
    cmd = " ".join(command)
    try:
        resp = requests.post(
            f"http://127.0.0.1:{port}/run",
            json={"command": cmd, "timeout": timeout},
            timeout=120,
        )
        if resp.status_code == 410:
            click.echo(f"❌ Session on port {port} has ended", err=True)
            return
        resp.raise_for_status()
        result = resp.json()
        print(result.get("output", ""))
        if err := result.get("error"):
            click.echo(f"Error: {err}", err=True)
    except requests.RequestException:
        click.echo(f"❌ Session on port {port} does not exist", err=True)


@cli.port_subcommands.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show session status."""
    port = ctx.parent.params["port"] if ctx.parent else 0
    try:
        resp = requests.get(f"http://127.0.0.1:{port}/status", timeout=5)
        if resp.status_code == 410:
            click.echo(f"❌ Session on port {port} has ended", err=True)
            return
        resp.raise_for_status()
        status_info = resp.json()
        click.echo(f"Session: {status_info.get('session_id')}")
        click.echo(f"Alive: {status_info.get('alive')}")
        click.echo(f"Idle: {status_info.get('idle_seconds')}s")
        waiting_for_input = status_info.get("waiting_for_input")
        last_line = status_info.get("last_line") or ""
        click.echo(f"Waiting for input: {waiting_for_input}")
        if last_line:
            label = "⚠️  Waiting for input" if waiting_for_input else "Last line"
            click.echo(f"{label}: {last_line}")
    except requests.RequestException:
        click.echo(f"❌ Session on port {port} does not exist", err=True)


@cli.port_subcommands.command()
@click.pass_context
def clear(ctx: click.Context) -> None:
    """Clear the session buffer."""
    port = ctx.parent.params["port"] if ctx.parent else 0
    try:
        resp = requests.post(f"http://127.0.0.1:{port}/clear", timeout=5)
        if resp.status_code == 410:
            click.echo(f"❌ Session on port {port} has ended", err=True)
            return
        resp.raise_for_status()
        click.echo("✨ Session buffer cleared")
    except requests.RequestException:
        click.echo(f"❌ Session on port {port} does not exist", err=True)


@cli.port_subcommands.command()
@click.pass_context
def interrupt(ctx: click.Context) -> None:
    """Send interrupt signal (Ctrl+C) to the session."""
    port = ctx.parent.params["port"] if ctx.parent else 0
    try:
        resp = requests.post(f"http://127.0.0.1:{port}/interrupt", timeout=5)
        if resp.status_code == 410:
            click.echo(f"❌ Session on port {port} has ended", err=True)
            return
        resp.raise_for_status()
        click.echo("✨ Interrupt signal sent")
    except requests.RequestException:
        click.echo(f"❌ Session on port {port} does not exist", err=True)


@cli.port_subcommands.command()
@click.pass_context
@click.option("--rows", type=int, default=24, help="Number of rows")
@click.option("--cols", type=int, default=80, help="Number of columns")
def resize(ctx: click.Context, rows: int, cols: int) -> None:
    """Resize the session terminal."""
    port = ctx.parent.params["port"] if ctx.parent else 0
    try:
        resp = requests.post(
            f"http://127.0.0.1:{port}/resize",
            params={"rows": rows, "cols": cols},
            timeout=5,
        )
        if resp.status_code == 410:
            click.echo(f"❌ Session on port {port} has ended", err=True)
            return
        resp.raise_for_status()
        click.echo(f"✨ Terminal resized to {rows}x{cols}")
    except requests.RequestException:
        click.echo(f"❌ Session on port {port} does not exist", err=True)


@cli.port_subcommands.command()
@click.pass_context
def close(ctx: click.Context) -> None:
    """Close the session gracefully."""
    port = ctx.parent.params["port"] if ctx.parent else 0
    try:
        resp = requests.post(f"http://127.0.0.1:{port}/close", timeout=5)
        if resp.status_code == 410:
            click.echo(f"❌ Session on port {port} has already ended", err=True)
            return
        resp.raise_for_status()
        click.echo("✨ Session closed")
    except requests.RequestException:
        click.echo(f"❌ Session on port {port} does not exist", err=True)


@cli.port_subcommands.command()
@click.pass_context
def kill(ctx: click.Context) -> None:
    """Force kill the session."""
    port = ctx.parent.params["port"] if ctx.parent else 0
    try:
        resp = requests.post(f"http://127.0.0.1:{port}/kill", timeout=5)
        if resp.status_code == 410:
            click.echo(f"❌ Session on port {port} has already ended", err=True)
            return
        resp.raise_for_status()
        click.echo("💀 Session killed")
    except requests.RequestException:
        click.echo(f"❌ Session on port {port} does not exist", err=True)


@cli.command(name="list")
def list_sessions() -> None:
    """List all active sessions."""
    try:
        resp = requests.get(_daemon_url("/sessions"), timeout=5)
        sessions = resp.json()

        if not sessions:
            click.echo("No active sessions")
            return

        click.echo("Active sessions:")
        for s in sessions:
            status_icon = "✓" if s["alive"] else "✗"
            click.echo(
                f"  {s['port']:5} | {s['session_id']:8} | {s['shell']:6} | "
                f"idle: {s['idle_seconds']:4}s {status_icon}"
            )
    except requests.RequestException:
        click.echo("SILC daemon is not running")


@cli.command()
def shutdown() -> None:
    """Gracefully shutdown daemon (closes all sessions)."""

    try:
        # Daemon side is bounded (~30s), but give a small cushion.
        requests.post(_daemon_url("/shutdown"), timeout=35)
    except requests.RequestException:
        click.echo("SILC daemon is not running")
        return

    if _wait_for_daemon_stop(timeout=30):
        click.echo("✨ SILC daemon shut down (all sessions closed)")
        click.echo("SILC daemon is no longer running")
        return

    # If the daemon is wedged, enforce a hard stop.
    click.echo("⚠️  Shutdown timed out; forcing killall", err=True)
    kill_daemon(port=DAEMON_PORT, force=True, timeout=2.0)
    _wait_for_daemon_stop(timeout=5)
    click.echo("💀 SILC daemon and all sessions killed")
    click.echo("SILC daemon is no longer running")


@cli.command()
def killall() -> None:
    """Force kill daemon and all sessions."""

    # Best-effort API call first (lets daemon clean logs/ports), but never rely on it.
    try:
        requests.post(_daemon_url("/killall"), timeout=3)
    except requests.RequestException:
        pass

    kill_daemon(port=DAEMON_PORT, force=True, timeout=2.0)
    _wait_for_daemon_stop(timeout=5)
    click.echo("💀 SILC daemon and all sessions killed")


@cli.command()
@click.option("--tail", default=100, help="Number of lines to show from end")
def logs(tail: int) -> None:
    """Show daemon logs."""
    from silc.utils.persistence import DAEMON_LOG

    if not DAEMON_LOG.exists():
        click.echo("No daemon log found")
        return

    try:
        content = DAEMON_LOG.read_text(encoding="utf-8")
        lines = content.splitlines()
        if tail > 0:
            lines = lines[-tail:]
        for line in lines:
            click.echo(line)
    except Exception as e:
        click.echo(f"Error reading daemon log: {e}", err=True)


@cli.port_subcommands.command()
@click.pass_context
def open(ctx: click.Context) -> None:
    """Open the Textual TUI."""
    port = ctx.parent.params["port"] if ctx.parent else 0
    click.echo(
        "⚠️  'open' is deprecated and can hang for 2 seconds, but it will still "
        "launch the textual TUI.",
        err=True,
    )
    time.sleep(2)
    asyncio.run(launch_tui(port))


def _tui_dist_dir() -> Path | None:
    potential_roots = (
        Path(__file__).resolve().parents[1],
        repo_root,
        Path.cwd(),
    )
    for root in potential_roots:
        dist_dir = root / "tui_client" / "dist"
        if dist_dir.is_dir():
            return dist_dir
    return None


def _native_tui_binary_path(dist_dir: Path) -> Path | None:
    if sys.platform.startswith("win"):
        filename = "silc-tui-windows.exe"
    elif sys.platform.startswith("linux"):
        filename = "silc-tui-linux"
    else:
        return None
    return dist_dir / filename


def _launch_native_tui_client(port: int) -> None:
    dist_dir = _tui_dist_dir()
    if dist_dir is None:
        click.echo(
            "⚠️  Native TUI distribution directory is missing; build the native "
            "client via `tui_client` before running `tui`.",
            err=True,
        )
        return

    executable = _native_tui_binary_path(dist_dir)
    if executable is None:
        click.echo("⚠️  Native TUI client is not available on this platform", err=True)
        return

    if not executable.exists():
        click.echo(
            f"⚠️  Native TUI binary is missing at {executable}. "
            "Build it from `tui_client` before running `tui`.",
            err=True,
        )
        return

    ws_url = f"ws://127.0.0.1:{port}/ws"
    click.echo(f"✨ Launching native TUI client at {ws_url}")
    subprocess.run([str(executable), ws_url])


@cli.port_subcommands.command()
@click.pass_context
def tui(ctx: click.Context) -> None:
    """Open the native TUI client."""
    port = ctx.parent.params["port"] if ctx.parent else 0
    _launch_native_tui_client(port)


@cli.port_subcommands.command()
@click.pass_context
def web(ctx: click.Context) -> None:
    """Open the web UI in a browser."""
    port = ctx.parent.params["port"] if ctx.parent else 0
    token = _fetch_session_token(port)
    query = f"?{urlencode({'token': token})}" if token else ""
    web_url = f"http://127.0.0.1:{port}/web{query}"
    webbrowser.open_new_tab(web_url)
    click.echo(f"✨ Opening web UI at {web_url}")
    click.echo(web_url)


@cli.port_subcommands.command()
@click.pass_context
@click.option("--tail", default=100, help="Number of lines to show from end")
def logs(ctx: click.Context, tail: int) -> None:
    """Show session logs."""
    port = ctx.parent.params["port"] if ctx.parent else 0
    try:
        resp = requests.get(
            f"http://127.0.0.1:{port}/logs", params={"tail": tail}, timeout=5
        )
        if resp.status_code == 410:
            click.echo(f"❌ Session on port {port} has ended", err=True)
            return
        resp.raise_for_status()
        result = resp.json()
        log_content = result.get("logs", "")
        if log_content:
            click.echo(log_content)
        else:
            click.echo("No logs available for this session")
    except requests.RequestException:
        click.echo(f"❌ Session on port {port} does not exist", err=True)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
