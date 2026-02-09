"""CLI commands for stream-to-file functionality."""

from typing import Optional

import click
import requests

from silc.stream.config import StreamConfig, StreamMode


def get_token(port: int) -> Optional[str]:
    """Get authentication token from session.

    Args:
        port: Session port number

    Returns:
        API token if available, None otherwise
    """
    try:
        resp = requests.get(f"http://127.0.0.1:{port}/token", timeout=2)
        if resp.status_code == 200:
            return resp.json().get("token")
    except Exception:
        pass
    return None


@click.command("stream-file-render")
@click.option("--name", default=None, help="Output filename (default: silc_{port}.txt)")
@click.option("--sec", default=5, type=int, help="Refresh interval in seconds")
@click.option(
    "--lines", default=120, type=int, help="Number of lines to capture (default: 120)"
)
@click.pass_context
def stream_file_render(
    ctx: click.Context, name: Optional[str], sec: int, lines: int
) -> None:
    """Continuously write TUI state to file (overwrite mode).

    This command captures the current terminal state and writes it to a file,
    overwriting the file on each interval. Best for monitoring continuous
    processes that repaint the terminal.

    Examples:
        silc 20000 stream-file-render
        silc 20000 stream-file-render --name output.txt --sec 10
    """
    port = ctx.parent.params["port"]
    filename = name or f"silc_{port}.txt"

    config = StreamConfig(
        mode=StreamMode.RENDER,
        filename=filename,
        interval=sec,
    )

    token = get_token(port)
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    try:
        resp = requests.post(
            f"http://127.0.0.1:{port}/stream/start",
            json=config.dict(),
            headers=headers,
            timeout=5,
        )

        if resp.status_code == 200:
            click.echo(f"Started render stream to {filename} (interval: {sec}s)")
        else:
            error_detail = resp.json().get("detail", "Unknown error")
            click.echo(f"Error: {error_detail}", err=True)
            ctx.exit(1)

    except requests.exceptions.ConnectionError:
        click.echo(f"Error: Cannot connect to session on port {port}", err=True)
        ctx.exit(1)
    except requests.exceptions.Timeout:
        click.echo(f"Error: Connection timeout for port {port}", err=True)
        ctx.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)


@click.command("stream-file-append")
@click.option(
    "--name", default=None, help="Output filename (default: silc_{port}_append.txt)"
)
@click.option("--sec", default=5, type=int, help="Check interval in seconds")
@click.option(
    "--window", default=2000, type=int, help="Deduplication window size in lines"
)
@click.option(
    "--threshold",
    default=0.85,
    type=float,
    help="Similarity threshold for fuzzy matching (0.0-1.0)",
)
@click.pass_context
def stream_file_append(
    ctx: click.Context, name: Optional[str], sec: int, window: int, threshold: float
) -> None:
    """Append new/changed lines to file with deduplication.

    This command captures terminal output and appends only new or changed lines
    to the file, using intelligent deduplication to avoid duplicates. Best for
    logging command output and terminal sessions.

    The deduplication uses a two-stage approach:
    1. Exact match check (fast)
    2. Fuzzy matching for similar lines (configurable threshold)

    Examples:
        silc 20000 stream-file-append
        silc 20000 stream-file-append --name session.log --sec 2 --threshold 0.9
    """
    port = ctx.parent.params["port"]
    filename = name or f"silc_{port}_append.txt"

    # Validate threshold
    if not 0.0 <= threshold <= 1.0:
        click.echo("Error: --threshold must be between 0.0 and 1.0", err=True)
        ctx.exit(1)

    config = StreamConfig(
        mode=StreamMode.APPEND,
        filename=filename,
        interval=sec,
        window_size=window,
        similarity_threshold=threshold,
    )

    token = get_token(port)
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    try:
        resp = requests.post(
            f"http://127.0.0.1:{port}/stream/start",
            json=config.dict(),
            headers=headers,
            timeout=5,
        )

        if resp.status_code == 200:
            click.echo(
                f"Started append stream to {filename} (interval: {sec}s, threshold: {threshold})"
            )
        else:
            error_detail = resp.json().get("detail", "Unknown error")
            click.echo(f"Error: {error_detail}", err=True)
            ctx.exit(1)

    except requests.exceptions.ConnectionError:
        click.echo(f"Error: Cannot connect to session on port {port}", err=True)
        ctx.exit(1)
    except requests.exceptions.Timeout:
        click.echo(f"Error: Connection timeout for port {port}", err=True)
        ctx.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)


@click.command("stream-stop")
@click.option("--name", required=True, help="Filename of the stream to stop")
@click.pass_context
def stream_stop(ctx: click.Context, name: str) -> None:
    """Stop a streaming task.

    Examples:
        silc 20000 stream-stop --name output.txt
        silc 20000 stream-stop --name session.log
    """
    port = ctx.parent.params["port"]

    token = get_token(port)
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    try:
        resp = requests.post(
            f"http://127.0.0.1:{port}/stream/stop",
            json={"filename": name},
            headers=headers,
            timeout=5,
        )

        if resp.status_code == 200:
            click.echo(f"Stopped stream to {name}")
        elif resp.status_code == 404:
            click.echo(f"Error: No active stream found for {name}", err=True)
            ctx.exit(1)
        else:
            error_detail = resp.json().get("detail", "Unknown error")
            click.echo(f"Error: {error_detail}", err=True)
            ctx.exit(1)

    except requests.exceptions.ConnectionError:
        click.echo(f"Error: Cannot connect to session on port {port}", err=True)
        ctx.exit(1)
    except requests.exceptions.Timeout:
        click.echo(f"Error: Connection timeout for port {port}", err=True)
        ctx.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)


@click.command("stream-status")
@click.pass_context
def stream_status(ctx: click.Context) -> None:
    """Show status of all active streams.

    Examples:
        silc 20000 stream-status
    """
    port = ctx.parent.params["port"]

    token = get_token(port)
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    try:
        resp = requests.get(
            f"http://127.0.0.1:{port}/stream/status",
            headers=headers,
            timeout=5,
        )

        if resp.status_code == 200:
            data = resp.json()
            streams = data.get("streams", {})

            if not streams:
                click.echo("No active streams")
                return

            click.echo("Active streams:")
            for filename, status in streams.items():
                active = "active" if status.get("active") else "inactive"
                cancelled = " (cancelled)" if status.get("cancelled") else ""
                click.echo(f"  {filename}: {active}{cancelled}")
        else:
            error_detail = resp.json().get("detail", "Unknown error")
            click.echo(f"Error: {error_detail}", err=True)
            ctx.exit(1)

    except requests.exceptions.ConnectionError:
        click.echo(f"Error: Cannot connect to session on port {port}", err=True)
        ctx.exit(1)
    except requests.exceptions.Timeout:
        click.echo(f"Error: Connection timeout for port {port}", err=True)
        ctx.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
