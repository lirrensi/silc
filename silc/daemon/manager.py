"""Silc daemon that manages multiple shell sessions."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
import sys
from functools import partial
from pathlib import Path
from typing import Dict

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from silc.api.server import create_app
from silc.core.session import SilcSession
from silc.daemon.registry import SessionRegistry
from silc.daemon.pidfile import remove_pidfile, write_pidfile
from silc.utils.persistence import (
    DAEMON_LOG,
    LOGS_DIR,
    cleanup_session_log,
    get_session_log_path,
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
        self._daemon_api_app = self._create_daemon_api()
        self._session_tasks: Dict[int, asyncio.Task] = {}
        self._cleanup_tasks: Dict[int, asyncio.Task[None]] = {}
        self._daemon_server: uvicorn.Server | None = None

    def _create_daemon_api(self) -> FastAPI:
        """Create daemon management API."""
        app = FastAPI(title="Silc Daemon")

        @app.post("/sessions")
        async def create_session(
            port: int | None = None, request: SessionCreateRequest | None = None
        ):
            """Create a new session."""
            selected_port = port
            if selected_port is None and request:
                selected_port = request.port
            if selected_port is None:
                selected_port = find_available_port(20000, 21000)

            if selected_port in self.sessions:
                raise HTTPException(
                    status_code=400, detail=f"Port {selected_port} already in use"
                )

            session_socket = self._reserve_session_socket(selected_port)
            try:
                shell_info = detect_shell()
                session = SilcSession(selected_port, shell_info)
                await session.start()

                self.sessions[selected_port] = session
                entry = self.registry.add(
                    selected_port, session.session_id, shell_info.type
                )

                server = self._create_session_server(session)
                self.servers[selected_port] = server

                # Start session server in background
                task = asyncio.create_task(server.serve(sockets=[session_socket]))
                self._session_tasks[selected_port] = task
                self._attach_session_task(selected_port, task)
            except Exception:
                self._close_session_socket(selected_port)
                raise

            write_daemon_log(
                f"Session created: port={selected_port}, id={session.session_id}"
            )

            return {
                "port": selected_port,
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

        return app

    def _create_session_server(self, session: SilcSession) -> uvicorn.Server:
        """Create uvicorn server for a session."""
        app = create_app(session)
        config = uvicorn.Config(
            app,
            host="127.0.0.1",
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

    def _reserve_session_socket(self, port: int) -> socket.socket:
        try:
            sock = bind_port("127.0.0.1", port)
        except OSError as exc:
            raise HTTPException(
                status_code=400, detail=f"Port {port} already in use"
            ) from exc
        self._session_sockets[port] = sock
        return sock

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

        # Close session
        session = self.sessions.pop(port, None)
        if session:
            try:
                await asyncio.wait_for(session.close(), timeout=2.0)
            except asyncio.TimeoutError:
                write_daemon_log(f"Timeout closing session PTY: port={port}")
            except Exception as exc:
                write_daemon_log(f"Error closing session PTY: port={port}, error={exc}")

        # Remove from registry
        self.registry.remove(port)

        # Cleanup log
        cleanup_session_log(port)

        write_daemon_log(f"Session closed: port={port}")

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
        """Propagate shutdown events to the uvicorn server."""
        await self._shutdown_event.wait()
        if self._daemon_server:
            self._daemon_server.should_exit = True

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
        write_pidfile(os.getpid())
        self._running = True
        self._setup_signals()

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

        # Run daemon server
        try:
            await self._daemon_server.serve()
        finally:
            # Cleanup on exit
            gc_task.cancel()
            shutdown_watcher.cancel()
            remove_pidfile()
            write_daemon_log("Silc daemon stopped")
            self._running = False

    def is_running(self) -> bool:
        """Check if daemon is running."""
        return self._running


__all__ = ["SilcDaemon", "DAEMON_PORT"]
