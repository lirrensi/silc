"""Silc daemon that manages multiple shell sessions."""

# FILE: silc/daemon/manager.py
# PURPOSE: Run the daemon API and contain request, watcher, and session failures so they do not crash the daemon.
# OWNS: Daemon API routes, session server lifecycle, restart/shutdown watchers, and daemon-level failure boundaries.
# EXPORTS: SilcDaemon (daemon lifecycle manager), DAEMON_PORT (default daemon API port).
# DOCS: docs/arch_api.md, docs/arch_daemon.md

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import signal
import socket
import sys
import traceback
from dataclasses import asdict
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Dict

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
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
from silc.utils.shell_detect import ShellInfo, detect_shell, get_available_shell_choices


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
MAX_SESSIONS = 100  # Prevent resource exhaustion
SESSION_START_TIMEOUT_SECONDS = 10.0


def _exception_detail(exc: BaseException) -> str:
    if isinstance(exc, HTTPException):
        if isinstance(exc.detail, dict):
            detail = exc.detail.get("detail") or exc.detail.get("error")
            if detail:
                return str(detail)
        elif exc.detail:
            return str(exc.detail)
    detail = str(exc)
    return detail if detail else exc.__class__.__name__


def _capture_exception_traceback(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def _build_daemon_error_payload(
    *,
    error: str,
    detail: str,
    operation: str,
    traceback_text: str = "",
) -> dict[str, str]:
    return {
        "error": error,
        "detail": detail,
        "operation": operation,
        "traceback": traceback_text,
    }


def _log_daemon_exception(operation: str, exc: BaseException) -> str:
    detail = _exception_detail(exc)
    traceback_text = _capture_exception_traceback(exc)
    write_daemon_log(
        f"Daemon operation failed: operation={operation}, error={exc.__class__.__name__}: {detail}"
    )
    write_daemon_log(f"{operation} traceback:\n{traceback_text}")
    return traceback_text


def _build_logged_daemon_exception_payload(
    operation: str,
    exc: BaseException,
    *,
    error: str = "Internal daemon error",
) -> dict[str, str]:
    traceback_text = _log_daemon_exception(operation, exc)
    return _build_daemon_error_payload(
        error=error,
        detail=_exception_detail(exc),
        operation=operation,
        traceback_text=traceback_text,
    )


def _build_validation_error_payload(
    operation: str, detail: str, *, error: str = "Invalid daemon request"
) -> dict[str, str]:
    return _build_daemon_error_payload(
        error=error,
        detail=detail,
        operation=operation,
    )


def _request_operation_label(request: Request) -> str:
    route = request.scope.get("route")
    name = getattr(route, "name", None)
    if name:
        return str(name)
    path = request.url.path.strip("/").replace("/", "_")
    return path or "root"


class SessionCreateRequest(BaseModel):
    port: int | None = None
    name: str | None = None
    is_global: bool = False
    token: str | None = None
    shell: str | None = None
    cwd: str | None = None


class SilcDaemon:
    """Main daemon managing multiple SILC sessions."""

    def __init__(
        self,
        *,
        enable_hard_exit: bool | None = None,
        host: str = "127.0.0.1",
        share_mode: bool = False,
    ):
        # Hard-exit is needed for the detached daemon mode (Windows in particular)
        # but must be disabled for in-process tests.
        if enable_hard_exit is None:
            enable_hard_exit = os.environ.get("PYTEST_CURRENT_TEST") is None

        self._enable_hard_exit = enable_hard_exit
        self._host = host
        self._share_mode = share_mode

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
        self._session_create_lock = asyncio.Lock()  # Serialize session creation

    def _create_daemon_api(self) -> FastAPI:
        """Create daemon management API."""
        app = FastAPI(title="Silc Daemon")

        @app.exception_handler(HTTPException)
        async def handle_http_exception(
            request: Request, exc: HTTPException
        ) -> JSONResponse:
            del request
            if isinstance(exc.detail, dict):
                content = exc.detail
            else:
                content = {"error": str(exc.detail)}
            return JSONResponse(status_code=exc.status_code, content=content)

        @app.exception_handler(Exception)
        async def handle_unexpected_exception(
            request: Request, exc: Exception
        ) -> JSONResponse:
            payload = _build_logged_daemon_exception_payload(
                _request_operation_label(request), exc
            )
            return JSONResponse(status_code=500, content=payload)

        @app.on_event("startup")
        async def startup_event():
            write_daemon_log("Daemon API is ready to accept requests")

        # Mount static files for manager UI assets under /ui/assets.
        # check_dir=False lets the daemon keep serving once a later build creates the files.
        manager_static_dir = Path(__file__).parent.parent.parent / "static" / "manager"
        app.mount(
            "/ui/assets",
            StaticFiles(directory=str(manager_static_dir / "assets"), check_dir=False),
            name="ui-assets",
        )

        @app.get("/", response_class=HTMLResponse)
        async def root_redirect() -> HTMLResponse:
            """Redirect root to UI."""
            return HTMLResponse(
                '<html><head><meta http-equiv="refresh" content="0;url=/ui/"></head>'
                "<body>Redirecting to <a href='/ui/'>SILC Manager UI</a>...</body></html>"
            )

        @app.get("/ui", response_class=HTMLResponse)
        @app.get("/ui/", response_class=HTMLResponse)
        @app.get("/ui/{path:path}", response_class=HTMLResponse)
        async def manager_ui(path: str = "") -> HTMLResponse:
            """Serve the manager web UI (SPA fallback for all /ui/* routes)."""
            index_path = manager_static_dir / "index.html"
            if index_path.exists():
                with open(index_path, "r", encoding="utf-8") as f:
                    return HTMLResponse(f.read())
            return HTMLResponse("<h1>Manager UI not found</h1>")

        @app.post("/sessions")
        async def create_session(
            port: int | None = None, request: SessionCreateRequest | None = None
        ):
            """Create a new session."""
            operation = "create_session"
            selected_port = port
            is_global = False
            token: str | None = None
            shell: str | None = None
            cwd: str | None = None
            session_name: str | None = None
            session: SilcSession | None = None
            task: asyncio.Task[None] | None = None
            try:
                async with self._session_create_lock:
                    if selected_port is None and request:
                        selected_port = request.port
                        is_global = request.is_global
                        token = request.token
                        shell = request.shell
                        cwd = request.cwd
                        session_name = request.name
                    is_global = is_global or self._share_mode
                    if selected_port is None:
                        selected_port = self._find_available_session_port()

                    if selected_port in self.sessions:
                        raise HTTPException(
                            status_code=400,
                            detail=_build_validation_error_payload(
                                operation, f"Port {selected_port} already in use"
                            ),
                        )

                    if len(self.sessions) >= MAX_SESSIONS:
                        raise HTTPException(
                            status_code=400,
                            detail=_build_validation_error_payload(
                                operation,
                                f"Maximum session count ({MAX_SESSIONS}) reached. Close unused sessions.",
                            ),
                        )

                    if session_name:
                        session_name = session_name.lower().strip()
                        if not is_valid_name(session_name):
                            raise HTTPException(
                                status_code=400,
                                detail=_build_validation_error_payload(
                                    operation,
                                    "Invalid name format. Must match [a-z][a-z0-9-]*[a-z0-9]",
                                ),
                            )
                        if self.registry.name_exists(session_name):
                            raise HTTPException(
                                status_code=400,
                                detail=_build_validation_error_payload(
                                    operation,
                                    f"Session name '{session_name}' is already in use",
                                ),
                            )
                    else:
                        for _ in range(10):
                            session_name = generate_name()
                            if not self.registry.name_exists(session_name):
                                break
                        else:
                            raise RuntimeError("Failed to generate unique session name")

                    if shell:
                        from silc.utils.shell_detect import get_shell_info_by_type

                        shell_info = get_shell_info_by_type(shell)
                        if shell_info is None:
                            raise HTTPException(
                                status_code=400,
                                detail=_build_validation_error_payload(
                                    operation,
                                    f"Unknown shell type: {shell}. Supported: bash, zsh, sh, pwsh, powershell, cmd",
                                ),
                            )
                    else:
                        shell_info = detect_shell()

                    try:
                        self._validate_session_launch(shell_info, cwd)
                    except ValueError as exc:
                        raise HTTPException(
                            status_code=400,
                            detail=_build_validation_error_payload(
                                operation, _exception_detail(exc)
                            ),
                        ) from exc

                    try:
                        self._reserve_session_socket(selected_port, is_global)
                    except HTTPException as exc:
                        raise HTTPException(
                            status_code=400,
                            detail=_build_validation_error_payload(
                                operation, _exception_detail(exc)
                            ),
                        ) from exc

                    try:
                        session = await self._construct_session(
                            selected_port,
                            session_name,
                            shell_info,
                            api_token=token,
                            cwd=cwd,
                        )
                        await self._start_session_with_timeout(session)

                        self.sessions[selected_port] = session
                        entry = self.registry.add(
                            selected_port,
                            session_name,
                            session.session_id,
                            shell_info.type,
                            cwd=cwd,
                            is_global=is_global,
                        )
                        append_session_to_json(entry.to_json())

                        server = self._create_session_server(
                            session, is_global=is_global
                        )
                        self.servers[selected_port] = server

                        task = asyncio.create_task(
                            server.serve(sockets=[self._session_sockets[selected_port]])
                        )
                        self._session_tasks[selected_port] = task
                        self._attach_session_task(selected_port, task)
                    except Exception:
                        await self._discard_partial_session_state(
                            selected_port,
                            operation=operation,
                            session=session,
                            task=task,
                        )
                        raise

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

                assert selected_port is not None
                assert session_name is not None
                assert session is not None
                write_daemon_log(
                    f"Session created: port={selected_port}, name={session_name}, id={session.session_id}"
                )

                return {
                    "port": selected_port,
                    "name": session_name,
                    "title": session.title,
                    "session_id": session.session_id,
                    "shell": shell_info.type,
                    "cwd": cwd,
                }
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

        @app.get("/sessions")
        async def list_sessions():
            """List all sessions."""
            operation = "list_sessions"
            try:
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
                                "title": entry.title,
                                "session_id": entry.session_id,
                                "shell": entry.shell_type,
                                "cwd": session.cwd,
                                "title_updated_at": entry.title_updated_at.isoformat()
                                + "Z",
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
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

        @app.get("/defaults")
        async def get_defaults():
            """Expose daemon-side defaults for manager UI helpers."""
            operation = "get_defaults"
            try:
                shell_choices = get_available_shell_choices()
                return {
                    "cwd": str(Path.home()),
                    "share_mode": self._share_mode,
                    "manager_url": self._get_manager_url(),
                    "shell": (
                        shell_choices[0].type if shell_choices else detect_shell().type
                    ),
                    "shell_options": [asdict(choice) for choice in shell_choices],
                }
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

        @app.get("/resolve/{name}")
        async def resolve_session(name: str):
            """Resolve session name to session info."""
            operation = "resolve_session"
            try:
                entry = self.registry.get_by_name(name)
                if not entry:
                    raise HTTPException(
                        status_code=404, detail=f"Session '{name}' not found"
                    )

                session = self.sessions.get(entry.port)
                return {
                    "port": entry.port,
                    "name": entry.name,
                    "title": entry.title,
                    "session_id": entry.session_id,
                    "shell": entry.shell_type,
                    "title_updated_at": entry.title_updated_at.isoformat() + "Z",
                    "idle_seconds": (
                        datetime.utcnow() - entry.last_access
                    ).total_seconds(),
                    "alive": session is not None and session.pty.pid is not None,
                }
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

        @app.post("/sessions/{port}/close")
        async def close_session(port: int):
            """Gracefully close a session."""
            operation = "close_session"
            try:
                if port not in self.sessions:
                    raise HTTPException(status_code=404, detail="Session not found")

                await self._ensure_cleanup_task(port)
                return {"status": "closed"}
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

        @app.post("/sessions/{port}/kill")
        async def kill_session(port: int):
            """Force kill a session."""
            operation = "kill_session"
            try:
                if port not in self.sessions:
                    raise HTTPException(status_code=404, detail="Session not found")

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

                await self._ensure_cleanup_task(port)
                return {"status": "killed"}
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

        @app.post("/sessions/{port}/restart")
        async def restart_session(port: int):
            """Restart a session with the same port, name, cwd, and shell type."""
            operation = "restart_session"
            new_session: SilcSession | None = None
            new_task: asyncio.Task[None] | None = None
            try:
                if port not in self.sessions:
                    raise HTTPException(status_code=404, detail="Session not found")

                session = self.sessions.get(port)
                if not session:
                    raise HTTPException(status_code=404, detail="Session not found")

                name = session.name
                shell_info = session.shell_info
                cwd = session.cwd
                api_token = session.api_token
                is_global = False

                entry = self.registry.get(port)
                if entry:
                    is_global = getattr(entry, "is_global", False)

                session_socket = self._session_sockets.get(port)
                target_port = port

                try:
                    await asyncio.wait_for(session.force_kill(), timeout=1.0)
                except asyncio.TimeoutError:
                    write_daemon_log(
                        f"Timeout force-killing session PTY during restart: port={port}"
                    )
                except Exception as exc:
                    write_daemon_log(
                        f"Error force-killing session PTY during restart: port={port}, error={exc}"
                    )

                self.sessions.pop(port, None)

                old_task = self._session_tasks.pop(port, None)
                if old_task:
                    old_task.cancel()
                    try:
                        await asyncio.wait_for(old_task, timeout=1.0)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass

                self.servers.pop(port, None)

                try:
                    self._validate_session_launch(shell_info, cwd)

                    if not session_socket:
                        try:
                            self._reserve_session_socket(target_port, is_global)
                        except HTTPException:
                            target_port = find_available_port(20000, 21000)
                            self._reserve_session_socket(target_port, is_global)

                    new_session = await self._construct_session(
                        target_port,
                        name,
                        shell_info,
                        api_token=api_token,
                        cwd=cwd,
                    )
                    await self._start_session_with_timeout(new_session)

                    self.sessions[target_port] = new_session

                    self.registry.remove(port)
                    self.registry.add(
                        target_port,
                        name,
                        new_session.session_id,
                        shell_info.type,
                        cwd=cwd,
                        is_global=is_global,
                    )
                    append_session_to_json(self.registry.get(target_port).to_json())

                    server = self._create_session_server(
                        new_session, is_global=is_global
                    )
                    self.servers[target_port] = server

                    new_task = asyncio.create_task(
                        server.serve(sockets=[self._session_sockets[target_port]])
                    )
                    self._session_tasks[target_port] = new_task
                    self._attach_session_task(target_port, new_task)
                    port = target_port
                except Exception:
                    failed_port = (
                        target_port if target_port in self._session_sockets else port
                    )
                    await self._discard_partial_session_state(
                        failed_port,
                        operation=operation,
                        session=new_session,
                        task=new_task,
                    )
                    raise

                write_daemon_log(f"Session restarted: port={port}, name={name}")

                return {
                    "status": "restarted",
                    "port": port,
                    "name": name,
                    "title": new_session.title,
                    "shell": shell_info.type,
                }
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

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
            operation = "restart_server"
            try:
                write_daemon_log("Server restart requested")
                self._restart_event.set()
                return {"status": "restarting"}
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

        @app.post("/resurrect")
        async def resurrect():
            """Resurrect sessions from sessions.json."""
            operation = "resurrect"
            try:
                write_daemon_log("Resurrect requested")
                result = await self._resurrect_sessions()
                return result
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

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

    def _handle_session_title_change(self, session: SilcSession) -> None:
        """Persist a live title change from a running session."""
        entry = self.registry.update_title(
            session.port, session.title, updated_at=session.title_updated_at
        )
        if not entry:
            return

        append_session_to_json(entry.to_json())

    def _attach_session_task(self, port: int, task: asyncio.Task[None]) -> None:
        task.add_done_callback(partial(self._handle_session_task_done, port))

    async def _construct_session(
        self,
        port: int,
        name: str,
        shell_info: ShellInfo,
        *,
        api_token: str | None = None,
        cwd: str | None = None,
        title: str | None = None,
    ) -> SilcSession:
        return await asyncio.wait_for(
            asyncio.to_thread(
                SilcSession,
                port,
                name,
                shell_info,
                api_token,
                cwd,
                title,
                self._handle_session_title_change,
            ),
            timeout=SESSION_START_TIMEOUT_SECONDS,
        )

    async def _start_session_with_timeout(self, session: SilcSession) -> None:
        await asyncio.wait_for(session.start(), timeout=SESSION_START_TIMEOUT_SECONDS)

    def _validate_session_launch(
        self, shell_info: ShellInfo, cwd: str | None = None
    ) -> None:
        if cwd:
            cwd_path = Path(cwd).expanduser()
            if not cwd_path.exists() or not cwd_path.is_dir():
                raise ValueError(f"Invalid cwd: {cwd}")

        shell_path = shell_info.path
        if not Path(shell_path).is_file() and not shutil.which(shell_path):
            raise ValueError(f"Shell executable not found: {shell_path}")

    async def _discard_partial_session_state(
        self,
        port: int,
        *,
        operation: str,
        session: SilcSession | None = None,
        task: asyncio.Task[None] | None = None,
    ) -> None:
        """Remove any partially-created session state after a failed start path."""

        server = self.servers.pop(port, None)
        if server:
            server.should_exit = True

        tracked_task = self._session_tasks.pop(port, None)
        tasks_to_cancel: list[asyncio.Task[None]] = []
        if tracked_task:
            tasks_to_cancel.append(tracked_task)
        if task and task is not tracked_task:
            tasks_to_cancel.append(task)

        for task_to_cancel in tasks_to_cancel:
            task_to_cancel.cancel()
            try:
                await asyncio.wait_for(task_to_cancel, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception as cleanup_exc:
                _log_daemon_exception(f"{operation}_rollback_task", cleanup_exc)

        tracked_session = self.sessions.pop(port, None)
        sessions_to_close: list[SilcSession] = []
        if tracked_session:
            sessions_to_close.append(tracked_session)
        if session and session is not tracked_session:
            sessions_to_close.append(session)

        for session_to_close in sessions_to_close:
            try:
                await asyncio.wait_for(session_to_close.close(), timeout=2.0)
            except asyncio.TimeoutError:
                write_daemon_log(
                    f"Timeout closing partial session during rollback: operation={operation}, port={port}"
                )
            except Exception as cleanup_exc:
                _log_daemon_exception(f"{operation}_rollback_session", cleanup_exc)

        self._close_session_socket(port)
        try:
            self.registry.remove(port)
        except Exception as cleanup_exc:
            _log_daemon_exception(f"{operation}_rollback_registry", cleanup_exc)
        try:
            remove_session_from_json(port)
        except Exception as cleanup_exc:
            _log_daemon_exception(f"{operation}_rollback_persistence", cleanup_exc)

    def _handle_session_task_done(self, port: int, task: asyncio.Task[None]) -> None:
        operation = "handle_session_task_done"
        try:
            if task.cancelled():
                return
            try:
                exc = task.exception()
            except Exception as task_exc:
                _log_daemon_exception(f"{operation}_task_exception", task_exc)
                return
            if not exc:
                return
            _log_daemon_exception(f"{operation}_session_server_port_{port}", exc)
            if port not in self.sessions:
                return
            try:
                self._ensure_cleanup_task(port)
            except RuntimeError as cleanup_exc:
                _log_daemon_exception(
                    f"{operation}_schedule_cleanup_port_{port}", cleanup_exc
                )
        except Exception as exc:
            _log_daemon_exception(operation, exc)

    def _ensure_cleanup_task(self, port: int) -> asyncio.Task[None]:
        """Ensure a cleanup task exists for the given port."""
        task = self._cleanup_tasks.get(port)
        if task and not task.done():
            return task
        task = asyncio.create_task(self._cleanup_session(port))
        self._cleanup_tasks[port] = task
        task.add_done_callback(lambda t, port=port: self._cleanup_tasks.pop(port, None))
        return task

    def _find_available_session_port(
        self, start: int = 20000, end: int = 21000, max_attempts: int = 100
    ) -> int:
        """Find an available port for a new session.

        This checks both daemon's internal session registry and actual port binding.
        """
        attempts = 0
        for port in range(start, end):
            if attempts >= max_attempts:
                break
            attempts += 1

            # Skip ports already used by daemon
            if port in self.sessions or port in self._session_sockets:
                continue

            # Try to actually bind the port
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("127.0.0.1", port))
                sock.close()
                return port
            except OSError:
                continue

        raise RuntimeError(
            f"Could not find an available port in range {start}-{end} after {max_attempts} attempts."
        )

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
            is_global = entry.get("is_global", False) or self._share_mode
            original_port = entry.get("port")
            port = original_port
            session: SilcSession | None = None
            task: asyncio.Task[None] | None = None

            try:
                if not name or not shell:
                    raise ValueError("missing_fields")

                if self.registry.name_exists(name):
                    write_daemon_log(f"Resurrect skip: name '{name}' already exists")
                    raise ValueError("name_collision")

                if port and port in self.sessions:
                    port = find_available_port(20000, 21000)

                if port is None:
                    port = find_available_port(20000, 21000)

                try:
                    self._reserve_session_socket(port, is_global)
                except HTTPException:
                    port = find_available_port(20000, 21000)
                    self._reserve_session_socket(port, is_global)

                from silc.utils.shell_detect import get_shell_info_by_type

                shell_info = get_shell_info_by_type(shell)
                if shell_info is None:
                    raise ValueError(f"unknown_shell: {shell}")

                self._validate_session_launch(shell_info, cwd)

                session = await self._construct_session(
                    port,
                    name,
                    shell_info,
                    cwd=cwd,
                    title=entry.get("title", ""),
                )
                await self._start_session_with_timeout(session)

                self.sessions[port] = session
                registry_entry = self.registry.add(
                    port,
                    name,
                    session.session_id,
                    shell_info.type,
                    cwd=cwd,
                    is_global=is_global,
                )

                server = self._create_session_server(session, is_global=is_global)
                self.servers[port] = server

                task = asyncio.create_task(
                    server.serve(sockets=[self._session_sockets[port]])
                )
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
                append_session_to_json(registry_entry.to_json())
            except Exception as exc:
                failure_name = name or "<unknown>"
                failure_reason = _exception_detail(exc)
                if port is not None:
                    await self._discard_partial_session_state(
                        port,
                        operation="resurrect_session",
                        session=session,
                        task=task,
                    )
                result["failed"].append(
                    {"name": failure_name, "reason": failure_reason}
                )
                _log_daemon_exception(f"resurrect_session_{failure_name}", exc)

        return result

    async def _garbage_collect(self) -> None:
        """Periodic garbage collection: log rotation only.

        Sessions never expire - they stay alive indefinitely.
        Idle tracking is kept for status/metrics only.
        """
        try:
            while self._running and not self._shutdown_event.is_set():
                try:
                    await asyncio.sleep(60)

                    rotate_daemon_log(max_lines=1000)
                except asyncio.CancelledError:
                    return
                except Exception as exc:
                    _log_daemon_exception("garbage_collect", exc)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            _log_daemon_exception("garbage_collect", exc)

    async def _watch_shutdown(self) -> None:
        """Propagate shutdown events to the uvicorn server and cleanup sessions."""
        operation = "watch_shutdown"
        try:
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
                    _log_daemon_exception(f"{operation}_cleanup_port_{port}", exc)

            if self._daemon_server:
                self._daemon_server.should_exit = True
        except asyncio.CancelledError:
            return
        except Exception as exc:
            _log_daemon_exception(operation, exc)

    async def _watch_restart(self) -> None:
        """Watch for restart requests and restart the HTTP server."""
        operation = "watch_restart"
        try:
            while self._running and not self._shutdown_event.is_set():
                try:
                    await self._restart_event.wait()
                except asyncio.CancelledError:
                    return

                if self._shutdown_event.is_set():
                    return

                try:
                    write_daemon_log("Restarting HTTP server...")

                    if self._daemon_server:
                        self._daemon_server.should_exit = True
                        await asyncio.sleep(0.5)

                    self._daemon_api_app = self._create_daemon_api()
                    config = uvicorn.Config(
                        self._daemon_api_app,
                        host=self._host,
                        port=DAEMON_PORT,
                        log_level="info",
                        access_log=True,
                    )
                    self._daemon_server = uvicorn.Server(config)
                    self._restart_event.clear()
                    asyncio.create_task(self._daemon_server.serve())

                    write_daemon_log("HTTP server restarted")
                    await asyncio.sleep(0.1)
                except asyncio.CancelledError:
                    return
                except Exception as exc:
                    self._restart_event.clear()
                    _log_daemon_exception(operation, exc)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            _log_daemon_exception(operation, exc)

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

        try:
            await self._resurrect_sessions()
        except Exception as exc:
            _log_daemon_exception("start_resurrect_sessions", exc)

        # Create daemon server
        daemon_config = uvicorn.Config(
            self._daemon_api_app,
            host=self._host,
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
            try:
                await self._daemon_server.serve()
            except Exception as exc:
                _log_daemon_exception("start_daemon_server", exc)
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

    def _get_manager_url(self) -> str:
        host = self._get_share_host() if self._share_mode else "127.0.0.1"
        return f"http://{host}:{DAEMON_PORT}/ui/"

    def _get_share_host(self) -> str:
        if not self._share_mode:
            return "127.0.0.1"

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                candidate = sock.getsockname()[0]
                if candidate and not candidate.startswith("127."):
                    return candidate
        except OSError:
            pass

        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                candidate = info[4][0]
                if candidate and not candidate.startswith("127."):
                    return candidate
        except OSError:
            pass

        return "127.0.0.1"


__all__ = ["SilcDaemon", "DAEMON_PORT"]
