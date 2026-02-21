"""Silc daemon that manages multiple shell sessions."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
import sys
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Dict

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from silc.api.server import create_app
from silc.core.session import SilcSession
from silc.daemon.pidfile import remove_pidfile, write_pidfile
from silc.daemon.registry import SessionRegistry
from silc.utils.names import generate_name, is_valid_name
from silc.utils.persistence import (
    DAEMON_LOG,
    LOGS_DIR,
    append_session_to_json,
    cleanup_session_log,
    get_session_log_path,
    remove_session_from_json,
    rotate_daemon_log,
    write_daemon_log,
)
from silc.utils.ports import bind_port, find_available_port
from silc.utils.shell_detect import detect_shell


def setup_uvicorn_logging():
    """Configure uvicorn logging to write to daemon log file."""
    logger = logging.getLogger("uvicorn")
    logger.setLevel(logging.INFO)

    handler = logging.FileHandler(DAEMON_LOG, mode="a", encoding="utf-8")
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "[%(asctime)s] %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.setLevel(logging.INFO)
    access_logger.addHandler(handler)


DAEMON_PORT = 19999


class SessionCreateRequest(BaseModel):
    port: int | None = None
    name: str | None = None
    is_global: bool = False
    token: str | None = None
    shell: str | None = None
    cwd: str | None = None


class SilcDaemon:
    """Main daemon managing multiple SILC sessions."""

    def __init__(self, *, enable_hard_exit: bool | None = None):
        # Hard-exit is needed for the detached daemon mode (Windows in particular)
        # but must be disabled for in-process tests.
        if enable_hard_exit is None:
            enable_hard_exit = os.environ.get("PYTEST_CURRENT_TEST") is None

        self._enable_hard_exit = enable_hard_exit

        self.registry = SessionRegistry()
        self.sessions: Dict[int, SilcSession] = {}
        self.servers: Dict[int, uvicorn.Server] = {}
        self._session_sockets: Dict[int, socket.socket] = {}
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._restart_event = asyncio.Event()
        self._daemon_api_app = self._create_daemon_api()
        self._session_tasks: Dict[int, asyncio.Task] = {}
        self._cleanup_tasks: Dict[int, asyncio.Task[None]] = {}
        self._daemon_server: uvicorn.Server | None = None

    def _create_daemon_api(self) -> FastAPI:
        """Create daemon management API."""
        app = FastAPI(title="Silc Daemon")

        @app.on_event("startup")
        async def startup_event():
            write_daemon_log("Daemon API is ready to accept requests")

        # Mount static files for assets (must be before catch-all routes)
        static_dir = Path(__file__).parent.parent.parent / "static" / "manager"
        if static_dir.exists():
            app.mount(
                "/assets",
                StaticFiles(directory=str(static_dir / "assets")),
                name="assets",
            )

        @app.get("/", response_class=HTMLResponse)
        @app.get("/index.html", response_class=HTMLResponse)
        async def manager_ui() -> HTMLResponse:
            """Serve the manager web UI."""
            static_dir = Path(__file__).parent.parent.parent / "static" / "manager"
            index_path = static_dir / "index.html"
            if index_path.exists():
                with open(index_path, "r", encoding="utf-8") as f:
                    return HTMLResponse(f.read())
            return HTMLResponse("<h1>Manager UI not found</h1>")

        @app.get("/{path:path}", response_class=HTMLResponse)
        async def serve_spa(path: str) -> HTMLResponse:
            """Serve SPA fallback - return index.html for client-side routing."""
            # Serve index.html for any path that falls through (Vue Router handles it)
            return await manager_ui()

        @app.post("/sessions")
        async def create_session(
            port: int | None = None, request: SessionCreateRequest | None = None
        ):
            """Create a new session."""
            selected_port = port
            is_global = False
            token: str | None = None
            shell: str | None = None
            cwd: str | None = None
            session_name: str | None = None
            if selected_port is None and request:
                selected_port = request.port
                is_global = request.is_global
                token = request.token
                shell = request.shell
                cwd = request.cwd
                session_name = request.name
            if selected_port is None:
                selected_port = find_available_port(20000, 21000)

            if selected_port in self.sessions:
                raise HTTPException(
                    status_code=400, detail=f"Port {selected_port} already in use"
                )

            # Handle name validation and generation
            if session_name:
                session_name = session_name.lower().strip()
                if not is_valid_name(session_name):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid name format. Must match [a-z][a-z0-9-]*[a-z0-9]",
                    )
                if self.registry.name_exists(session_name):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Session name '{session_name}' is already in use",
                    )
            else:
                # Auto-generate name
                for _ in range(10):  # Try 10 times to avoid collision
                    session_name = generate_name()
                    if not self.registry.name_exists(session_name):
                        break
                else:
                    raise HTTPException(
                        status_code=500,
                        detail="Failed to generate unique session name",
                    )

            session_socket = self._reserve_session_socket(selected_port, is_global)
            try:
                # Handle shell override
                if shell:
                    from silc.utils.shell_detect import get_shell_info_by_type

                    shell_info = get_shell_info_by_type(shell)
                    if shell_info is None:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Unknown shell type: {shell}. Supported: bash, zsh, sh, pwsh, cmd",
                        )
                else:
                    shell_info = detect_shell()
                session = SilcSession(
                    selected_port, session_name, shell_info, api_token=token, cwd=cwd
                )
                await session.start()

                self.sessions[selected_port] = session
                entry = self.registry.add(
                    selected_port,
                    session_name,
                    session.session_id,
                    shell_info.type,
                    is_global=is_global,
                )
                # Persist to sessions.json
                append_session_to_json(
                    {
                        "port": selected_port,
                        "name": session_name,
                        "session_id": session.session_id,
                        "shell": shell_info.type,
                        "is_global": is_global,
                        "cwd": cwd,
                        "created_at": entry.created_at.isoformat() + "Z",
                    }
                )

                server = self._create_session_server(session, is_global=is_global)
                self.servers[selected_port] = server

                # Start session server in background
                task = asyncio.create_task(server.serve(sockets=[session_socket]))
                self._session_tasks[selected_port] = task
                self._attach_session_task(selected_port, task)

                # Log if session is globally accessible
                if is_global:
                    write_daemon_log(
                        f"Session {selected_port} is globally accessible on 0.0.0.0 (RCE RISK)"
                    )
                    write_daemon_log(
                        "WARNING: --global flag exposes session on all network interfaces."
                    )
                    write_daemon_log(
                        "WARNING: API tokens are sent over plaintext HTTP - NOT SECURE."
                    )
                    write_daemon_log(
                        "WARNING: Only use on trusted home networks, NEVER on public internet."
                    )
                    write_daemon_log(
                        "WARNING: Consider using SSH tunneling or reverse proxy with TLS for remote access."
                    )
            except Exception:
                self._close_session_socket(selected_port)
                raise

            write_daemon_log(
                f"Session created: port={selected_port}, name={session_name}, id={session.session_id}"
            )

            return {
                "port": selected_port,
                "name": session_name,
                "session_id": session.session_id,
                "shell": shell_info.type,
            }

        @app.get("/sessions")
        async def list_sessions():
            """List all sessions."""
            sessions = []
            for entry in self.registry.list_all():
                session = self.sessions.get(entry.port)
                if not session:
                    try:
                        self._ensure_cleanup_task(entry.port)
                    except RuntimeError:
                        write_daemon_log(
                            f"Failed to schedule cleanup for port={entry.port} during listing"
                        )
                    continue

                status = session.get_status()
                if status["alive"]:
                    sessions.append(
                        {
                            "port": entry.port,
                            "name": entry.name,
                            "session_id": entry.session_id,
                            "shell": entry.shell_type,
                            "idle_seconds": status["idle_seconds"],
                            "alive": status["alive"],
                        }
                    )
                else:
                    try:
                        self._ensure_cleanup_task(entry.port)
                    except RuntimeError:
                        write_daemon_log(
                            f"Failed to schedule cleanup for port={entry.port} during listing"
                        )

            return sessions

        @app.get("/resolve/{name}")
        async def resolve_session(name: str):
            """Resolve session name to session info."""
            entry = self.registry.get_by_name(name)
            if not entry:
                raise HTTPException(
                    status_code=404, detail=f"Session '{name}' not found"
                )

            session = self.sessions.get(entry.port)
            return {
                "port": entry.port,
                "name": entry.name,
                "session_id": entry.session_id,
                "shell": entry.shell_type,
                "idle_seconds": (datetime.utcnow() - entry.last_access).total_seconds(),
                "alive": session is not None and session.pty.pid is not None,
            }

        @app.delete("/sessions/{port}")
        async def close_session(port: int):
            """Close a specific session."""
            if port not in self.sessions:
                raise HTTPException(status_code=404, detail="Session not found")

            await self._ensure_cleanup_task(port)
            return {"status": "closed"}

        @app.post("/shutdown")
        async def shutdown():
            """Graceful shutdown: close all sessions and stop the daemon.

            Must be bounded: never hang forever.
            """

            write_daemon_log("Shutdown requested")

            loop = asyncio.get_running_loop()
            deadline = loop.time() + 30.0
            ports = list(self.sessions.keys())

            for port in ports:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    write_daemon_log(
                        "Shutdown exceeded 30s budget; leaving remaining sessions for killall"
                    )
                    break
                try:
                    await asyncio.wait_for(
                        self._ensure_cleanup_task(port), timeout=remaining
                    )
                except asyncio.TimeoutError:
                    write_daemon_log(f"Shutdown timeout closing session: port={port}")
                except Exception as exc:
                    write_daemon_log(
                        f"Shutdown error closing session: port={port}, error={exc}"
                    )

            self._shutdown_event.set()
            if self._daemon_server:
                self._daemon_server.should_exit = True

            # If asyncio.run() is stuck on stubborn tasks, force-exit after a grace period.
            if self._enable_hard_exit:
                asyncio.create_task(self._hard_exit_after(delay=30.0, exit_code=0))

            return {"status": "shutdown"}

        @app.post("/killall")
        async def killall():
            """Force kill: close all sessions and terminate daemon.

            This is the "absolute nuke" path.
            """

            write_daemon_log("Killall requested")

            ports = list(self.sessions.keys())
            for port in ports:
                session = self.sessions.get(port)
                if session:
                    try:
                        await asyncio.wait_for(session.force_kill(), timeout=1.0)
                    except asyncio.TimeoutError:
                        write_daemon_log(
                            f"Timeout force-killing session PTY: port={port}"
                        )
                    except Exception as exc:
                        write_daemon_log(
                            f"Error force-killing session PTY: port={port}, error={exc}"
                        )

                try:
                    await asyncio.wait_for(self._ensure_cleanup_task(port), timeout=2.0)
                except asyncio.TimeoutError:
                    write_daemon_log(f"Timeout cleaning session: port={port}")
                except Exception as exc:
                    write_daemon_log(
                        f"Error cleaning session: port={port}, error={exc}"
                    )

            self._shutdown_event.set()
            if self._daemon_server:
                self._daemon_server.should_exit = True

            # Ensure the process is actually gone even if uvicorn/asyncio is wedged.
            if self._enable_hard_exit:
                asyncio.create_task(self._hard_exit_after(delay=0.25, exit_code=1))

            return {"status": "killed"}

        @app.post("/restart-server")
        async def restart_server():
            """Restart the HTTP server without killing sessions."""
            write_daemon_log("Server restart requested")
            self._restart_event.set()
            return {"status": "restarting"}

        @app.post("/resurrect")
        async def resurrect():
            """Resurrect sessions from sessions.json."""
            write_daemon_log("Resurrect requested")
            result = await self._resurrect_sessions()
            return result

        return app

    def _create_session_server(
        self, session: SilcSession, is_global: bool = False
    ) -> uvicorn.Server:
        """Create uvicorn server for a session."""
        app = create_app(session)
        config = uvicorn.Config(
            app,
            host="0.0.0.0" if is_global else "127.0.0.1",
            port=session.port,
            log_level="info",
            access_log=True,
        )
        return uvicorn.Server(config)

    def _attach_session_task(self, port: int, task: asyncio.Task[None]) -> None:
        task.add_done_callback(partial(self._handle_session_task_done, port))

    def _handle_session_task_done(self, port: int, task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if not exc:
            return
        write_daemon_log(f"Session server failed: port={port}, error={exc}")
        if port not in self.sessions:
            return
        try:
            self._ensure_cleanup_task(port)
        except RuntimeError:
            write_daemon_log(
                f"Failed to schedule cleanup for port={port} after server error"
            )

    def _ensure_cleanup_task(self, port: int) -> asyncio.Task[None]:
        """Ensure a cleanup task exists for the given port."""
        task = self._cleanup_tasks.get(port)
        if task and not task.done():
            return task
        task = asyncio.create_task(self._cleanup_session(port))
        self._cleanup_tasks[port] = task
        task.add_done_callback(lambda t, port=port: self._cleanup_tasks.pop(port, None))
        return task

    def _reserve_session_socket(
        self, port: int, is_global: bool = False
    ) -> socket.socket:
        try:
            sock = bind_port("0.0.0.0" if is_global else "127.0.0.1", port)
        except OSError as exc:
            raise HTTPException(
                status_code=400, detail=f"Port {port} already in use"
            ) from exc
        self._session_sockets[port] = sock
        return sock

    async def _kill_processes_on_port(self, port: int) -> None:
        """Kill processes listening on a specific session port.

        This is called during session cleanup to ensure any orphaned shell
        processes are terminated. Unlike startup cleanup, this targets only
        the specific session port being cleaned up.

        Safety:
        - Only kills processes listening on the exact port
        - Verifies process matches shell patterns
        - Kills entire process tree (children included)
        """
        import psutil

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, lambda: self._kill_processes_on_port_sync(port)
            )
        except Exception as exc:
            write_daemon_log(f"Error killing processes on port {port}: {exc}")

    def _kill_processes_on_port_sync(self, port: int) -> None:
        """Synchronous version of process killing."""
        import psutil

        try:
            conns = psutil.net_connections(kind="inet")
        except Exception:
            return

        # Shell patterns to match (case-insensitive)
        shell_patterns = ["powershell.exe", "pwsh.exe", "cmd.exe", "bash", "sh", "zsh"]

        for conn in conns:
            try:
                if not conn.laddr:
                    continue
                if conn.status != psutil.CONN_LISTEN:
                    continue
                if conn.laddr.port != port:
                    continue
                if not conn.pid:
                    continue

                pid = conn.pid

                try:
                    proc = psutil.Process(pid)

                    # Verify it's a shell process
                    try:
                        cmdline = " ".join(proc.cmdline()).lower()
                    except Exception:
                        cmdline = ""

                    is_shell = any(pattern in cmdline for pattern in shell_patterns)
                    if not is_shell:
                        continue

                    # Kill process and all children
                    children = proc.children(recursive=True)
                    all_procs = [proc] + children
                    for p in all_procs:
                        try:
                            p.terminate()
                        except psutil.NoSuchProcess:
                            pass
                        except Exception:
                            pass

                    gone, alive = psutil.wait_procs(all_procs, timeout=1.0)
                    for p in alive:
                        try:
                            p.kill()
                        except psutil.NoSuchProcess:
                            pass
                        except Exception:
                            pass
                    psutil.wait_procs(alive, timeout=0.3)

                    write_daemon_log(
                        f"Killed orphaned shell process PID {pid} on port {port}"
                    )
                except psutil.NoSuchProcess:
                    pass
                except Exception as exc:
                    write_daemon_log(f"Error killing PID {pid}: {exc}")
            except Exception:
                continue

    def _close_session_socket(self, port: int) -> None:
        sock = self._session_sockets.pop(port, None)
        if not sock:
            return
        try:
            sock.close()
        except OSError:
            pass

    async def _cleanup_session(self, port: int) -> None:
        """Cleanup a session: close server, close session, cleanup registry.

        This path must be *bounded* (never hang forever). The daemon shutdown
        sequence relies on cleanup completing even when uvicorn/PTY teardown is
        flaky on some platforms.
        """

        # Get task and server before cleanup
        task = self._session_tasks.pop(port, None)
        server = self.servers.pop(port, None)

        # Ask server to exit first
        if server:
            server.should_exit = True

        # Close listening socket early so the port is released even if uvicorn is stuck.
        self._close_session_socket(port)

        # Cancel and await the task (bounded)
        if task:
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=2.0)
            except asyncio.CancelledError:
                pass
            except asyncio.TimeoutError:
                write_daemon_log(
                    f"Timeout waiting for session server task to cancel: port={port}"
                )
            except Exception as exc:
                write_daemon_log(
                    f"Error awaiting session server task during cleanup: port={port}, error={exc}"
                )

        # Close session (this should kill PTY processes)
        session = self.sessions.pop(port, None)
        if session:
            try:
                await asyncio.wait_for(session.close(), timeout=2.0)
            except asyncio.TimeoutError:
                write_daemon_log(f"Timeout closing session PTY: port={port}")
            except Exception as exc:
                write_daemon_log(f"Error closing session PTY: port={port}, error={exc}")

            # Kill any orphaned processes still listening on this port
            await self._kill_processes_on_port(port)

        # Remove from registry
        self.registry.remove(port)

        # Remove from persistent registry
        remove_session_from_json(port)

        # Cleanup log
        cleanup_session_log(port)

        write_daemon_log(f"Session closed: port={port}")

    async def _resurrect_sessions(self) -> dict:
        """Restore sessions from sessions.json. Returns result summary."""
        from silc.utils.persistence import read_sessions_json

        result = {"restored": [], "failed": []}
        sessions = read_sessions_json()

        if not sessions:
            write_daemon_log("No sessions to resurrect")
            return result

        write_daemon_log(f"Resurrecting {len(sessions)} sessions...")

        for entry in sessions:
            name = entry.get("name")
            shell = entry.get("shell")
            cwd = entry.get("cwd")
            is_global = entry.get("is_global", False)
            original_port = entry.get("port")

            if not name or not shell:
                result["failed"].append({"name": name, "reason": "missing_fields"})
                continue

            # Check for name collision
            if self.registry.name_exists(name):
                result["failed"].append({"name": name, "reason": "name_collision"})
                write_daemon_log(f"Resurrect skip: name '{name}' already exists")
                continue

            # Find available port (try original first)
            port = original_port
            if port and port in self.sessions:
                port = find_available_port(20000, 21000)

            if port is None:
                port = find_available_port(20000, 21000)

            try:
                session_socket = self._reserve_session_socket(port, is_global)
            except OSError:
                # Port still taken, try another
                try:
                    port = find_available_port(20000, 21000)
                    session_socket = self._reserve_session_socket(port, is_global)
                except OSError as exc:
                    result["failed"].append(
                        {"name": name, "reason": f"port_unavailable: {exc}"}
                    )
                    write_daemon_log(f"Resurrect failed: port unavailable for '{name}'")
                    continue

            try:
                # Get shell info
                from silc.utils.shell_detect import get_shell_info_by_type

                shell_info = get_shell_info_by_type(shell)
                if shell_info is None:
                    self._close_session_socket(port)
                    result["failed"].append(
                        {"name": name, "reason": f"unknown_shell: {shell}"}
                    )
                    continue

                # Create session
                session = SilcSession(port, name, shell_info, cwd=cwd)
                await session.start()

                self.sessions[port] = session
                registry_entry = self.registry.add(
                    port, name, session.session_id, shell_info.type, is_global
                )

                server = self._create_session_server(session, is_global=is_global)
                self.servers[port] = server

                task = asyncio.create_task(server.serve(sockets=[session_socket]))
                self._session_tasks[port] = task
                self._attach_session_task(port, task)

                status = (
                    "restored"
                    if original_port and port == original_port
                    else "relocated"
                )
                result["restored"].append(
                    {
                        "port": port,
                        "name": name,
                        "status": status,
                        "original_port": (
                            original_port if status == "relocated" else None
                        ),
                    }
                )
                write_daemon_log(f"Resurrected: {name} on port {port}")

                # Update sessions.json with actual port
                append_session_to_json(
                    {
                        "port": port,
                        "name": name,
                        "session_id": session.session_id,
                        "shell": shell_info.type,
                        "is_global": is_global,
                        "cwd": cwd,
                        "created_at": registry_entry.created_at.isoformat() + "Z",
                    }
                )

            except Exception as exc:
                self._close_session_socket(port)
                result["failed"].append({"name": name, "reason": str(exc)})
                write_daemon_log(f"Resurrect failed for '{name}': {exc}")

        return result

    async def _garbage_collect(self) -> None:
        """Periodic garbage collection of idle sessions."""
        while self._running and not self._shutdown_event.is_set():
            await asyncio.sleep(60)

            # Cleanup timed out sessions
            cleaned_ports = self.registry.cleanup_timeout(timeout_seconds=1800)
            for port in cleaned_ports:
                await self._ensure_cleanup_task(port)

            # Rotate daemon log
            rotate_daemon_log(max_lines=1000)

    async def _watch_shutdown(self) -> None:
        """Propagate shutdown events to the uvicorn server and cleanup sessions."""
        await self._shutdown_event.wait()

        write_daemon_log("Graceful shutdown initiated")

        loop = asyncio.get_running_loop()
        deadline = loop.time() + 30.0
        ports = list(self.sessions.keys())

        for port in ports:
            remaining = deadline - loop.time()
            if remaining <= 0:
                write_daemon_log(
                    "Shutdown exceeded 30s budget; leaving remaining sessions"
                )
                break
            try:
                await asyncio.wait_for(
                    self._ensure_cleanup_task(port), timeout=remaining
                )
            except asyncio.TimeoutError:
                write_daemon_log(f"Shutdown timeout closing session: port={port}")
            except Exception as exc:
                write_daemon_log(
                    f"Shutdown error closing session: port={port}, error={exc}"
                )

        if self._daemon_server:
            self._daemon_server.should_exit = True

    async def _watch_restart(self) -> None:
        """Watch for restart requests and restart the HTTP server."""
        while self._running and not self._shutdown_event.is_set():
            await self._restart_event.wait()
            if self._shutdown_event.is_set():
                return

            write_daemon_log("Restarting HTTP server...")

            # Stop current server
            if self._daemon_server:
                self._daemon_server.should_exit = True
                # Give it time to drain connections
                await asyncio.sleep(0.5)

            # Recreate and restart
            self._daemon_api_app = self._create_daemon_api()
            config = uvicorn.Config(
                self._daemon_api_app,
                host="127.0.0.1",
                port=DAEMON_PORT,
                log_level="info",
                access_log=True,
            )
            self._daemon_server = uvicorn.Server(config)

            # Clear the restart event before serving
            self._restart_event.clear()

            # Start serving in a new task (we're in a background task)
            asyncio.create_task(self._daemon_server.serve())

            write_daemon_log("HTTP server restarted")

            # Small delay to prevent tight restart loops
            await asyncio.sleep(0.1)

    def _setup_signals(self) -> None:
        """Setup signal handlers for graceful shutdown."""

        def handle_signal(signum, frame):
            write_daemon_log(f"Received signal {signum}, shutting down...")
            self._shutdown_event.set()
            if self._daemon_server:
                self._daemon_server.should_exit = True

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

    async def _hard_exit_after(self, *, delay: float, exit_code: int) -> None:
        """Hard-exit the daemon process after a delay.

        Used as a watchdog for cases where uvicorn/asyncio teardown can wedge and
        keep the python process alive (Windows seems especially prone to this).
        """

        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return

        # Best-effort cleanup so subsequent `start` commands can recover.
        try:
            remove_pidfile()
        except Exception:
            pass

        os._exit(exit_code)

    async def start(self) -> None:
        """Start the daemon."""
        if self._running:
            return

        setup_uvicorn_logging()
        write_daemon_log("Starting Silc daemon...")

        import psutil

        from silc.daemon.pidfile import read_pidfile

        # Check for existing daemon process (skip in test mode)
        if self._enable_hard_exit:
            existing_pid = read_pidfile()
            if existing_pid:
                try:
                    proc = psutil.Process(existing_pid)
                    if proc.is_running():
                        write_daemon_log(
                            f"Existing daemon process found (PID {existing_pid}), aborting startup"
                        )
                        write_daemon_log("Use 'silc shutdown' or 'silc killall' first")
                        raise RuntimeError(
                            f"Daemon already running (PID {existing_pid}). "
                            "Use 'silc shutdown' or 'silc killall' to stop it."
                        )
                except psutil.NoSuchProcess:
                    write_daemon_log(
                        f"Stale PID file found (PID {existing_pid}), cleaning up..."
                    )

        write_pidfile(os.getpid())
        self._running = True
        self._setup_signals()

        # Resurrect persisted sessions
        await self._resurrect_sessions()

        # Create daemon server
        daemon_config = uvicorn.Config(
            self._daemon_api_app,
            host="127.0.0.1",
            port=DAEMON_PORT,
            log_level="info",
            access_log=True,
        )
        self._daemon_server = uvicorn.Server(daemon_config)

        # Start GC task
        gc_task = asyncio.create_task(self._garbage_collect())
        shutdown_watcher = asyncio.create_task(self._watch_shutdown())
        restart_watcher = asyncio.create_task(self._watch_restart())

        # Run daemon server
        try:
            await self._daemon_server.serve()
        finally:
            # Cleanup on exit
            gc_task.cancel()
            shutdown_watcher.cancel()
            restart_watcher.cancel()
            remove_pidfile()
            write_daemon_log("Silc daemon stopped")
            self._running = False

    def is_running(self) -> bool:
        """Check if daemon is running."""
        return self._running


__all__ = ["SilcDaemon", "DAEMON_PORT"]
