"""Silc daemon that manages multiple shell sessions."""

# FILE: silc/daemon/manager.py
# PURPOSE: Run the daemon API and contain request, watcher, and session failures so they do not crash the daemon.
# OWNS: Daemon API routes, shared settings persistence, session server lifecycle, restart/shutdown watchers, and daemon-level failure boundaries.
# EXPORTS: SilcDaemon (daemon lifecycle manager), DAEMON_PORT (default daemon API port).
# DOCS: docs/arch_api.md, docs/arch_daemon.md, agent_chat/plan_daemon_settings_store_2026-04-08.md

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shutil
import signal
import socket
import struct
import sys
import traceback
import uuid
from dataclasses import asdict
from functools import partial
from pathlib import Path
from typing import Dict

import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from silc.core.cleaner import clean_output
from silc.core.session import SilcSession
from silc.daemon.events import (
    DaemonEventBroadcaster,
    build_manager_event_header,
    encode_ws_frame,
    serialize_session_snapshot,
    serialize_session_snapshots,
)
from silc.daemon.pidfile import remove_pidfile, write_pidfile
from silc.daemon.registry import SessionRegistry
from silc.daemon.runtime import (
    SessionRuntime,
    SessionState,
    bump_runtime_generation,
    create_runtime_for_record,
    format_runtime_state,
    record_runtime_failure,
    runtime_backoff_expired,
)
from silc.daemon.session_adapter import SessionPortAdapter
from silc.daemon.settings import DaemonSettings
from silc.stream.config import StreamConfig
from silc.stream.streaming_service import StreamingService
from silc.utils.names import generate_name, is_valid_name
from silc.utils.persistence import (
    DAEMON_LOG,
    LOGS_DIR,
    cleanup_session_log,
    garbage_collect_session_snapshots,
    get_session_log_path,
    read_session_log,
    read_session_snapshot,
    read_settings_json,
    remove_session_snapshot,
    rotate_daemon_log,
    write_daemon_log,
    write_session_snapshot,
    write_sessions_json,
    write_settings_json,
)
from silc.utils.ports import bind_port
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


class SessionRenameRequest(BaseModel):
    name: str


class SessionReorderRequest(BaseModel):
    ports: list[int]


def _shell_display_name(shell_info: ShellInfo) -> str:
    return {
        "pwsh": "PowerShell",
        "powershell": "Windows PowerShell",
        "cmd": "Command Prompt",
        "bash": "Bash",
        "zsh": "Zsh",
        "sh": "Shell",
    }.get(shell_info.type, shell_info.type)


def _client_is_local(host: str | None) -> bool:
    if not host:
        return False
    if host.lower() == "localhost":
        return True
    if "%" in host:
        host = host.split("%", 1)[0]
    try:
        from ipaddress import AddressValueError, ip_address

        addr = ip_address(host)
    except AddressValueError:
        return False
    if addr.is_loopback:
        return True
    ipv4_mapped = getattr(addr, "ipv4_mapped", None)
    return bool(ipv4_mapped and ipv4_mapped.is_loopback)


def _request_client_host(request: Request | WebSocket) -> str | None:
    headers = getattr(request, "headers", None)
    if headers is not None:
        forwarded = headers.get("x-silc-client-host") or headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",", 1)[0].strip() or None

    client = request.client
    return client[0] if client else None


def decode_ws_frame(frame: bytes) -> tuple[dict[str, object], bytes]:
    """Decode a websocket frame using the shared SILC binary envelope."""

    if len(frame) < 4:
        raise ValueError("frame too short")

    header_length = struct.unpack(">I", frame[:4])[0]
    if len(frame) < 4 + header_length:
        raise ValueError("frame truncated")

    header_bytes = frame[4 : 4 + header_length]
    payload = frame[4 + header_length :]

    try:
        header = json.loads(header_bytes.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError("invalid frame header encoding") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("invalid frame header json") from exc

    if not isinstance(header, dict):
        raise ValueError("frame header must be object")

    return header, payload


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
        self.servers: Dict[int, object] = {}
        self._session_sockets: Dict[int, socket.socket] = {}
        self.runtime_by_port: Dict[int, SessionRuntime] = {}
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._restart_event = asyncio.Event()
        self._reconcile_event = asyncio.Event()
        self.events = DaemonEventBroadcaster()
        self.shared_settings = DaemonSettings.load(read_settings_json())
        self._daemon_api_app = self._create_daemon_api()
        self._session_tasks: Dict[int, asyncio.Task] = {}
        self._cleanup_tasks: Dict[int, asyncio.Task[None]] = {}
        self._streaming_services: Dict[int, StreamingService] = {}
        self._active_session_websockets: Dict[int, WebSocket | None] = {}
        self._active_session_websocket_locks: Dict[int, asyncio.Lock] = {}
        self._daemon_server: uvicorn.Server | None = None
        self._registry_lock = (
            asyncio.Lock()
        )  # Serialize registry mutations and persistence

    def _is_active_session_websocket(self, port: int, websocket: WebSocket) -> bool:
        return self._active_session_websockets.get(port) is websocket

    async def _claim_active_session_websocket(
        self, port: int, websocket: WebSocket, session: SilcSession
    ) -> WebSocket | None:
        active_websocket_lock = self._active_session_websocket_locks.setdefault(
            port, asyncio.Lock()
        )
        async with active_websocket_lock:
            previous_websocket = self._active_session_websockets.get(port)
            self._active_session_websockets[port] = websocket
            session.tui_active = True
            return previous_websocket

    async def _release_active_session_websocket(
        self, port: int, websocket: WebSocket, session: SilcSession
    ) -> None:
        active_websocket_lock = self._active_session_websocket_locks.get(port)
        if active_websocket_lock is None:
            if self._active_session_websockets.get(port) is websocket:
                self._active_session_websockets.pop(port, None)
                session.tui_active = False
            return

        async with active_websocket_lock:
            if self._active_session_websockets.get(port) is websocket:
                self._active_session_websockets.pop(port, None)
                session.tui_active = False

    async def _close_tracked_session_websocket(
        self,
        port: int,
        *,
        code: int = 1001,
        reason: str = "Session ended",
    ) -> None:
        active_websocket_lock = self._active_session_websocket_locks.get(port)
        if active_websocket_lock is None:
            tracked_websocket = self._active_session_websockets.pop(port, None)
        else:
            async with active_websocket_lock:
                tracked_websocket = self._active_session_websockets.pop(port, None)

        runtime = self.runtime_by_port.get(port)
        tracked_session = self.sessions.get(port) or (
            runtime.session if runtime else None
        )
        if tracked_session is not None:
            tracked_session.tui_active = False

        if tracked_websocket is None:
            return

        with contextlib.suppress(Exception):
            await tracked_websocket.close(code=code, reason=reason)

    def _resolve_session_target(self, key: str, *, operation: str) -> tuple:
        normalized_key = key.strip()
        if not normalized_key:
            raise HTTPException(
                status_code=404,
                detail=_build_validation_error_payload(operation, "Session not found"),
            )

        if normalized_key.isdigit():
            port = int(normalized_key)
            entry = self._get_desired_entry_for_port(port)
            if entry is None:
                raise HTTPException(status_code=404, detail="Session not found")
            return entry, self.runtime_by_port.get(port)

        entry = self._get_desired_entry_for_name(normalized_key)
        if entry is None:
            raise HTTPException(
                status_code=404,
                detail=f"Session '{normalized_key}' not found",
            )
        return entry, self.runtime_by_port.get(entry.port)

    def _require_session_token(self, request: Request, session: SilcSession) -> None:
        token = session.api_token
        if not token:
            return

        client_host = _request_client_host(request)
        if _client_is_local(client_host):
            return

        auth_header = request.headers.get("authorization")
        if not auth_header:
            raise HTTPException(status_code=401, detail="Missing API token")

        parts = auth_header.strip().split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid Authorization header")

        if parts[1].strip() != token:
            raise HTTPException(status_code=403, detail="Invalid API token")

    def _session_status_payload(self, entry, runtime) -> dict[str, object]:
        session = runtime.session if runtime else None
        if session is not None:
            try:
                status = session.get_status()
            except Exception:
                status = None
            if isinstance(status, dict):
                status["runtime_state"] = runtime.state.value if runtime else "dormant"
                status["dormant"] = False
                return status

        payload = serialize_session_snapshot(entry, runtime)
        payload.update(
            {
                "tui_active": False,
                "waiting_for_input": False,
                "last_line": "",
                "run_locked": False,
            }
        )
        if runtime is None:
            payload["dormant"] = True
        return payload

    def _decode_snapshot_output(self, snapshot_bytes: bytes, *, raw: bool) -> str:
        lines = snapshot_bytes.decode("utf-8", errors="replace").splitlines()
        if raw:
            return "\n".join(lines)
        return clean_output(lines)

    def _read_session_snapshot_bytes(self, entry, runtime) -> bytes:
        session = runtime.session if runtime else None
        if session is not None:
            try:
                return session.get_snapshot_bytes()
            except Exception:
                pass
        return read_session_snapshot(entry.session_id)

    def _session_is_alive(self, session: SilcSession) -> bool:
        try:
            return bool(session.get_status().get("alive"))
        except Exception:
            return False

    def _get_streaming_service(
        self, port: int, session: SilcSession
    ) -> StreamingService:
        service = self._streaming_services.get(port)
        if service is None or service.session is not session:
            service = StreamingService(session)
            self._streaming_services[port] = service
        return service

    async def _stop_streaming_service(self, port: int) -> None:
        service = self._streaming_services.pop(port, None)
        if service is None:
            return
        with contextlib.suppress(Exception):
            await service.stop_all_streams()

    def _resolve_active_session_target(
        self, key: str, *, operation: str
    ) -> tuple[object, object, SilcSession]:
        entry, runtime = self._resolve_session_target(key, operation=operation)
        session = runtime.session if runtime else None
        if session is None or not self._session_is_alive(session):
            raise HTTPException(status_code=410, detail="Session has ended")
        return entry, runtime, session

    async def _wake_session_target(self, key: str, request: Request) -> dict:
        operation = "session_wake"
        async with self._registry_lock:
            entry, runtime = self._resolve_session_target(key, operation=operation)
            session = runtime.session if runtime else None

            if session is not None:
                self._require_session_token(request, session)
                if self._session_is_alive(session):
                    return {
                        "status": "awake",
                        "port": entry.port,
                        "name": entry.name,
                        "title": entry.title,
                        "shell": entry.shell_type,
                    }

                await self._cleanup_runtime_generation(
                    entry.port,
                    runtime.generation,
                    remove_record=False,
                    ignore_generation_mismatch=True,
                )

            runtime = self._get_or_create_runtime(entry)
            runtime = await self._realize_runtime(
                entry, runtime, preserve_session_id=entry.session_id
            )
            return {
                "status": "woken",
                "port": entry.port,
                "name": entry.name,
                "title": runtime.session.title if runtime.session else entry.title,
                "shell": entry.shell_type,
            }

    async def _unload_session_target(self, key: str, request: Request) -> dict:
        operation = "session_unload"
        async with self._registry_lock:
            entry, runtime = self._resolve_session_target(key, operation=operation)
            session = runtime.session if runtime else None
            if session is not None:
                self._require_session_token(request, session)

            if runtime is None:
                return {
                    "status": "unloaded",
                    "port": entry.port,
                    "name": entry.name,
                    "title": entry.title,
                    "shell": entry.shell_type,
                }

            await self._cleanup_runtime_generation(
                entry.port,
                runtime.generation,
                remove_record=False,
                ignore_generation_mismatch=True,
            )
            self.runtime_by_port.pop(entry.port, None)
            return {
                "status": "unloaded",
                "port": entry.port,
                "name": entry.name,
                "title": entry.title,
                "shell": entry.shell_type,
            }

    async def _sigint_session_target(self, key: str, request: Request) -> dict:
        operation = "session_sigint"
        _entry, _runtime, session = self._resolve_active_session_target(
            key, operation=operation
        )
        self._require_session_token(request, session)
        await session.interrupt()
        return {"status": "sigint_sent"}

    def _create_daemon_api(self) -> FastAPI:
        """Create daemon management API."""
        app = FastAPI(title="Silc Daemon")
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
        )

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
            try:
                async with self._registry_lock:
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
                    is_global = is_global or self._share_mode
                    if selected_port is None:
                        selected_port = self._find_available_session_port()

                    if self._get_desired_entry_for_port(selected_port):
                        raise HTTPException(
                            status_code=400,
                            detail=_build_validation_error_payload(
                                operation, f"Port {selected_port} already in use"
                            ),
                        )

                    if len(self.registry.list_all()) >= MAX_SESSIONS:
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

                    assert selected_port is not None
                    assert session_name is not None
                    desired_session_id = uuid.uuid4().hex[:8]
                    initial_title = _shell_display_name(shell_info)
                    entry = self.registry.add(
                        selected_port,
                        session_name,
                        desired_session_id,
                        shell_info.type,
                        cwd=cwd,
                        title=initial_title,
                        is_global=is_global,
                    )
                    self._persist_desired_sessions()
                    runtime = self._get_or_create_runtime(
                        entry, api_token=token, title=initial_title
                    )

                    try:
                        runtime = await self._realize_runtime(
                            entry,
                            runtime,
                            preserve_session_id=desired_session_id,
                        )
                    except Exception as exc:
                        payload = _build_logged_daemon_exception_payload(operation, exc)
                        return JSONResponse(status_code=500, content=payload)

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
                assert runtime.session is not None
                write_daemon_log(
                    f"Session created: port={selected_port}, name={session_name}, id={runtime.session.session_id}"
                )
                asyncio.create_task(
                    self._publish_session_event("session/created", entry)
                )

                return {
                    "port": selected_port,
                    "name": session_name,
                    "title": runtime.session.title,
                    "session_id": runtime.session.session_id,
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
                return self._list_session_snapshots()
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

        @app.post("/sessions/{port}/rename")
        async def rename_session(port: int, request: SessionRenameRequest):
            """Rename a session in place."""
            operation = "rename_session"
            try:
                async with self._registry_lock:
                    entry = self._get_desired_entry_for_port(port)
                    if not entry:
                        raise HTTPException(status_code=404, detail="Session not found")

                    session_name = request.name.lower().strip()
                    if not is_valid_name(session_name):
                        raise HTTPException(
                            status_code=400,
                            detail=_build_validation_error_payload(
                                operation,
                                "Invalid name format. Must match [a-z][a-z0-9-]*[a-z0-9]",
                            ),
                        )

                    existing = self.registry.get_by_name(session_name)
                    if existing is not None and existing.port != port:
                        raise HTTPException(
                            status_code=400,
                            detail=_build_validation_error_payload(
                                operation,
                                f"Session name '{session_name}' is already in use",
                            ),
                        )

                    updated_entry = self.registry.rename(port, session_name)
                    if updated_entry is None:
                        raise HTTPException(status_code=404, detail="Session not found")

                    runtime = self.runtime_by_port.get(port)
                    if runtime is not None:
                        runtime.name = session_name
                        if runtime.session is not None:
                            runtime.session.name = session_name

                    self._persist_desired_sessions()
                    await self._publish_session_event("session/renamed", updated_entry)

                    return self._serialize_session_entry(updated_entry)
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

        @app.post("/sessions/reorder")
        async def reorder_sessions(request: SessionReorderRequest):
            """Reorder active sessions and persist the new order."""
            operation = "reorder_sessions"
            try:
                async with self._registry_lock:
                    self.registry.reorder(request.ports)
                    self._persist_desired_sessions()
                    await self.events.publish(
                        build_manager_event_header(
                            "session/reordered",
                            sessions=self._list_session_snapshots(),
                            ports=request.ports,
                        )
                    )
                    await self._publish_session_snapshot()
                    return {"sessions": self._list_session_snapshots()}
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail=_build_validation_error_payload(operation, str(exc)),
                ) from exc
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

        @app.get("/settings")
        async def get_settings():
            """Return the current shared daemon settings."""

            return self.shared_settings.to_dict()

        @app.post("/settings")
        async def update_settings(request: Request):
            """Deep-merge a JSON object into the shared daemon settings."""

            operation = "update_settings"
            try:
                try:
                    payload = await request.json()
                except (json.JSONDecodeError, ValueError) as exc:
                    raise HTTPException(
                        status_code=400,
                        detail=_build_validation_error_payload(
                            operation, "Request body must be valid JSON"
                        ),
                    ) from exc
                if not isinstance(payload, dict):
                    raise HTTPException(
                        status_code=400,
                        detail=_build_validation_error_payload(
                            operation, "Settings update must be a JSON object"
                        ),
                    )

                async with self._registry_lock:
                    self.shared_settings = self.shared_settings.merged(payload)
                    settings_payload = self.shared_settings.to_dict()
                    write_settings_json(settings_payload)
                    return settings_payload
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

        @app.get("/resolve/{key}")
        async def resolve_session(key: str):
            """Resolve a session target using the shared port-first/name-second rule."""
            operation = "resolve_session"
            try:
                entry, _runtime = self._resolve_session_target(key, operation=operation)
                return self._serialize_session_entry(entry)
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

        @app.get("/sessions/{key}/status")
        async def session_status(key: str, request: Request) -> dict[str, object]:
            operation = "session_status"
            try:
                entry, runtime = self._resolve_session_target(key, operation=operation)
                session = runtime.session if runtime else None
                if session is not None:
                    self._require_session_token(request, session)
                return self._session_status_payload(entry, runtime)
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

        @app.get("/sessions/{key}/out")
        async def session_out(key: str, request: Request, lines: int = 100) -> dict:
            operation = "session_out"
            try:
                entry, runtime = self._resolve_session_target(key, operation=operation)
                session = runtime.session if runtime else None
                if session is not None:
                    self._require_session_token(request, session)
                    output = session.get_output(lines)
                else:
                    snapshot_bytes = self._read_session_snapshot_bytes(entry, runtime)
                    output = self._decode_snapshot_output(snapshot_bytes, raw=False)
                    if lines > 0:
                        output = "\n".join(output.splitlines()[-lines:])
                return {"output": output, "lines": len(output.splitlines())}
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

        @app.get("/sessions/{key}/raw")
        async def session_raw(key: str, request: Request, lines: int = 100) -> dict:
            operation = "session_raw"
            try:
                entry, runtime = self._resolve_session_target(key, operation=operation)
                session = runtime.session if runtime else None
                if session is not None:
                    self._require_session_token(request, session)
                    output = session.get_output(lines, raw=True)
                else:
                    snapshot_bytes = self._read_session_snapshot_bytes(entry, runtime)
                    output = self._decode_snapshot_output(snapshot_bytes, raw=True)
                    if lines > 0:
                        output = "\n".join(output.splitlines()[-lines:])
                return {"output": output, "lines": len(output.splitlines())}
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

        @app.get("/sessions/{key}/snapshot")
        async def session_snapshot(key: str, request: Request) -> Response:
            operation = "session_snapshot"
            try:
                entry, runtime = self._resolve_session_target(key, operation=operation)
                session = runtime.session if runtime else None
                if session is not None:
                    self._require_session_token(request, session)
                    snapshot_bytes = session.get_snapshot_bytes()
                else:
                    snapshot_bytes = self._read_session_snapshot_bytes(entry, runtime)
                if not snapshot_bytes:
                    raise HTTPException(
                        status_code=404, detail="Session snapshot not found"
                    )
                return Response(
                    content=snapshot_bytes,
                    media_type="application/octet-stream",
                    headers={"Cache-Control": "no-store"},
                )
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

        @app.get("/sessions/{key}/logs")
        async def session_logs(key: str, request: Request, tail: int = 100) -> dict:
            operation = "session_logs"
            try:
                entry, runtime = self._resolve_session_target(key, operation=operation)
                session = runtime.session if runtime else None
                if session is not None:
                    self._require_session_token(request, session)
                    log_content = read_session_log(session.port, tail_lines=tail)
                else:
                    log_content = read_session_log(entry.port, tail_lines=tail)
                lines = log_content.splitlines() if log_content else []
                return {"logs": log_content, "lines": len(lines)}
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

        @app.post("/sessions/{key}/in")
        async def session_in(
            key: str, request: Request, nonewline: bool = False
        ) -> dict:
            operation = "session_in"
            try:
                entry, runtime, session = self._resolve_active_session_target(
                    key, operation=operation
                )
                self._require_session_token(request, session)
                body = await request.body()
                text = body.decode("utf-8", errors="replace")
                text = text.rstrip("\r\n")
                if not nonewline:
                    text += "\r\n" if sys.platform == "win32" else "\n"
                await session.write_input(text)
                _ = entry, runtime
                return {"status": "sent"}
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

        @app.post("/sessions/{key}/run")
        async def session_run(key: str, request: Request, timeout: int = 60) -> dict:
            operation = "session_run"
            try:
                entry, runtime, session = self._resolve_active_session_target(
                    key, operation=operation
                )
                self._require_session_token(request, session)
                body = await request.body()
                if not body:
                    return {"error": "No command provided", "status": "bad_request"}
                text = body.decode("utf-8", errors="replace")
                command = text
                resolved_timeout = timeout
                try:
                    payload = json.loads(text)
                    command = payload.get("command", "")
                    resolved_timeout = payload.get("timeout", timeout)
                except json.JSONDecodeError:
                    pass
                command = command.rstrip("\r\n")
                _ = entry, runtime
                return await session.run_command(command, resolved_timeout)
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

        @app.post("/sessions/{key}/wake")
        async def session_wake(key: str, request: Request) -> dict:
            operation = "session_wake"
            try:
                return await self._wake_session_target(key, request)
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

        @app.post("/sessions/{key}/unload")
        async def session_unload(key: str, request: Request) -> dict:
            operation = "session_unload"
            try:
                return await self._unload_session_target(key, request)
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

        @app.post("/sessions/{key}/sigint")
        async def session_sigint(key: str, request: Request) -> dict:
            operation = "session_sigint"
            try:
                return await self._sigint_session_target(key, request)
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

        @app.post("/sessions/{key}/interrupt")
        async def session_interrupt(key: str, request: Request) -> dict:
            operation = "session_interrupt"
            try:
                return await self._sigint_session_target(key, request)
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

        @app.post("/sessions/{key}/sigterm")
        async def session_sigterm(key: str, request: Request) -> dict:
            operation = "session_sigterm"
            try:
                _entry, _runtime, session = self._resolve_active_session_target(
                    key, operation=operation
                )
                self._require_session_token(request, session)
                await session.send_sigterm()
                return {"status": "sigterm_sent"}
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

        @app.post("/sessions/{key}/sigkill")
        async def session_sigkill(key: str, request: Request) -> dict:
            operation = "session_sigkill"
            try:
                _entry, _runtime, session = self._resolve_active_session_target(
                    key, operation=operation
                )
                self._require_session_token(request, session)
                await session.send_sigkill()
                return {"status": "sigkill_sent"}
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

        @app.post("/sessions/{key}/clear")
        async def session_clear(key: str, request: Request) -> dict:
            operation = "session_clear"
            try:
                _entry, _runtime, session = self._resolve_active_session_target(
                    key, operation=operation
                )
                self._require_session_token(request, session)
                await session.clear_screen()
                return {"status": "cleared"}
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

        @app.post("/sessions/{key}/resize")
        async def session_resize(
            key: str, request: Request, rows: int, cols: int
        ) -> dict:
            operation = "session_resize"
            try:
                _entry, _runtime, session = self._resolve_active_session_target(
                    key, operation=operation
                )
                self._require_session_token(request, session)
                session.resize(rows, cols)
                return {"status": "resized", "rows": rows, "cols": cols}
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

        @app.get("/sessions/{key}/token")
        async def session_token(key: str, request: Request) -> dict[str, str | None]:
            operation = "session_token"
            try:
                _entry, runtime, session = self._resolve_active_session_target(
                    key, operation=operation
                )
                self._require_session_token(request, session)
                _ = runtime
                return {"token": session.api_token}
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

        @app.get("/sessions/{key}/web", response_class=HTMLResponse)
        async def session_web(key: str) -> HTMLResponse:
            operation = "session_web"
            try:
                entry, runtime = self._resolve_session_target(key, operation=operation)
                session = runtime.session if runtime else None
                if session is None:
                    raise HTTPException(status_code=410, detail="Session has ended")

                static_dir = Path(__file__).parent.parent.parent / "static" / "web"
                index_path = static_dir / "index.html"
                if index_path.exists():
                    with open(index_path, "r", encoding="utf-8") as f:
                        return HTMLResponse(f.read())
                _ = entry
                return HTMLResponse("<h1>Web UI not found</h1>")
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

        @app.websocket("/sessions/{key}/ws")
        async def session_websocket(key: str, websocket: WebSocket) -> None:
            operation = "session_websocket"
            try:
                entry, runtime = self._resolve_session_target(key, operation=operation)
                session = runtime.session if runtime else None
                if session is None:
                    await websocket.close(code=4100, reason="Session has ended")
                    return

                token = session.api_token
                if token:
                    client_host = _request_client_host(websocket)
                    if not _client_is_local(client_host):
                        provided = websocket.query_params.get("token")
                        if provided != token:
                            await websocket.close(code=1008, reason="Invalid API token")
                            return

                mode = websocket.query_params.get("mode", "interactive")
                if mode not in {"interactive", "preview"}:
                    await websocket.close(
                        code=1002, reason="Unsupported websocket mode"
                    )
                    return

                await websocket.accept()

                previous_websocket: WebSocket | None = None

                if mode == "interactive":
                    previous_websocket = await self._claim_active_session_websocket(
                        entry.port, websocket, session
                    )

                    if (
                        previous_websocket is not None
                        and previous_websocket is not websocket
                    ):
                        with contextlib.suppress(RuntimeError):
                            await previous_websocket.close(
                                code=4002,
                                reason="Session claimed by another client",
                            )

                send_lock = asyncio.Lock()
                send_queue: asyncio.Queue[tuple[dict[str, object], bytes]] = (
                    asyncio.Queue(maxsize=16)
                )
                event_loop = asyncio.get_running_loop()
                connection_closed = False

                async def safe_send_frame(
                    header: dict[str, object], payload: bytes = b""
                ) -> None:
                    if connection_closed:
                        raise RuntimeError("websocket already closing")
                    if mode == "interactive" and not self._is_active_session_websocket(
                        entry.port, websocket
                    ):
                        raise RuntimeError(
                            "websocket no longer owns interactive session"
                        )
                    async with send_lock:
                        if connection_closed:
                            raise RuntimeError("websocket already closing")
                        if (
                            mode == "interactive"
                            and not self._is_active_session_websocket(
                                entry.port, websocket
                            )
                        ):
                            raise RuntimeError(
                                "websocket no longer owns interactive session"
                            )
                        await websocket.send_bytes(encode_ws_frame(header, payload))

                def enqueue_send_frame(
                    header: dict[str, object], payload: bytes = b""
                ) -> None:
                    if connection_closed:
                        return
                    if mode == "interactive" and not self._is_active_session_websocket(
                        entry.port, websocket
                    ):
                        return

                    def _queue_frame() -> None:
                        if connection_closed:
                            return
                        try:
                            send_queue.put_nowait((header, payload))
                        except asyncio.QueueFull:
                            with contextlib.suppress(asyncio.QueueEmpty):
                                send_queue.get_nowait()
                            with contextlib.suppress(asyncio.QueueFull):
                                send_queue.put_nowait((header, payload))

                    with contextlib.suppress(RuntimeError):
                        event_loop.call_soon_threadsafe(_queue_frame)

                async def send_output_chunks() -> None:
                    cursor = session.buffer.cursor
                    while True:
                        queue_task = asyncio.create_task(send_queue.get())
                        output_task = asyncio.create_task(session._output_event.wait())

                        try:
                            done, pending = await asyncio.wait(
                                {queue_task, output_task},
                                return_when=asyncio.FIRST_COMPLETED,
                            )
                        except asyncio.CancelledError:
                            queue_task.cancel()
                            output_task.cancel()
                            with contextlib.suppress(Exception):
                                await asyncio.gather(
                                    queue_task, output_task, return_exceptions=True
                                )
                            raise

                        for pending_task in pending:
                            pending_task.cancel()
                        with contextlib.suppress(Exception):
                            await asyncio.gather(*pending, return_exceptions=True)

                        if queue_task in done:
                            try:
                                header, payload = queue_task.result()
                                await safe_send_frame(header, payload)
                            except asyncio.CancelledError:
                                raise
                            except Exception:
                                return
                            continue

                        session._output_event.clear()

                        while True:
                            new_bytes, cursor = session.buffer.get_since(cursor)
                            if not new_bytes:
                                break
                            try:
                                await safe_send_frame({"type": "output"}, new_bytes)
                            except asyncio.CancelledError:
                                raise
                            except Exception:
                                return

                def title_listener(updated_session: SilcSession) -> None:
                    if updated_session is not session:
                        return
                    enqueue_send_frame(
                        {
                            "type": "title",
                            "title": updated_session.title,
                            "title_updated_at": (
                                updated_session.title_updated_at.isoformat() + "Z"
                            ),
                        }
                    )

                def cwd_listener(updated_session: SilcSession) -> None:
                    if updated_session is not session:
                        return
                    enqueue_send_frame({"type": "cwd", "cwd": updated_session.cwd})

                if mode == "interactive":
                    session.add_title_listener(title_listener)
                    session.add_cwd_listener(cwd_listener)
                    sender_task = asyncio.create_task(send_output_chunks())
                else:
                    sender_task = None

                try:
                    while True:
                        try:
                            frame = await websocket.receive_bytes()
                        except WebSocketDisconnect:
                            raise
                        except RuntimeError:
                            await websocket.close(
                                code=1002, reason="Expected binary websocket frame"
                            )
                            return

                        try:
                            header, payload = decode_ws_frame(frame)
                        except ValueError:
                            await websocket.close(
                                code=1002, reason="Malformed websocket frame"
                            )
                            return

                        message_type = header.get("type")
                        if message_type == "input":
                            if mode != "interactive":
                                await websocket.close(
                                    code=1002,
                                    reason="Preview websocket is read-only",
                                )
                                return
                            nonewline = bool(header.get("nonewline", False))
                            text = payload.decode("utf-8", errors="replace")

                            if nonewline:
                                await session.write_input(text)
                            else:
                                text = text.rstrip("\r\n")
                                newline = "\r\n" if sys.platform == "win32" else "\n"
                                await session.write_input(text + newline)
                        elif message_type == "load_history":
                            await safe_send_frame(
                                {"type": "history"}, session.buffer.get_bytes()
                            )
                        else:
                            await websocket.close(
                                code=1002, reason="Unsupported websocket message"
                            )
                            return
                except WebSocketDisconnect:
                    pass
                finally:
                    connection_closed = True
                    if mode == "interactive":
                        session.remove_title_listener(title_listener)
                        session.remove_cwd_listener(cwd_listener)
                        if sender_task is not None:
                            sender_task.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await sender_task
                        await self._release_active_session_websocket(
                            entry.port, websocket, session
                        )
            except HTTPException:
                raise
            except Exception as exc:
                await websocket.close(code=1011, reason=_exception_detail(exc)[:120])
                _log_daemon_exception(operation, exc)

        @app.post("/sessions/{key}/stream/start")
        async def session_stream_start(key: str, request: Request) -> dict[str, str]:
            operation = "session_stream_start"
            try:
                entry, runtime, session = self._resolve_active_session_target(
                    key, operation=operation
                )
                self._require_session_token(request, session)
                service = self._get_streaming_service(entry.port, session)
                body = await request.body()
                payload = body.decode("utf-8", errors="replace")
                if not payload:
                    raise HTTPException(status_code=400, detail="Invalid stream config")
                try:
                    config = StreamConfig.model_validate_json(body)
                except AttributeError:
                    config = StreamConfig.parse_raw(body)
                except Exception as exc:
                    raise HTTPException(
                        status_code=400, detail="Invalid stream config"
                    ) from exc
                filename = await service.start_stream(config)
                _ = runtime
                return {"status": "started", "filename": filename, "mode": config.mode}
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

        @app.post("/sessions/{key}/stream/stop")
        async def session_stream_stop(key: str, request: Request) -> dict[str, str]:
            operation = "session_stream_stop"
            try:
                entry, runtime, session = self._resolve_active_session_target(
                    key, operation=operation
                )
                self._require_session_token(request, session)
                service = self._get_streaming_service(entry.port, session)
                filename = ""
                try:
                    data = await request.json()
                    if isinstance(data, dict):
                        filename = str(data.get("filename", "")).strip()
                except Exception:
                    payload = await request.body()
                    filename = payload.decode("utf-8", errors="replace").strip()
                if not filename:
                    raise HTTPException(status_code=400, detail="Missing filename")
                stopped = await service.stop_stream(filename)
                if not stopped:
                    raise HTTPException(
                        status_code=404,
                        detail=f"No active stream found for: {filename}",
                    )
                _ = entry, runtime
                return {"status": "stopped", "filename": filename}
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=_build_logged_daemon_exception_payload(operation, exc),
                ) from exc

        @app.get("/sessions/{key}/stream/status")
        async def session_stream_status(
            key: str, request: Request
        ) -> dict[str, object]:
            operation = "session_stream_status"
            try:
                entry, runtime, session = self._resolve_active_session_target(
                    key, operation=operation
                )
                self._require_session_token(request, session)
                service = self._get_streaming_service(entry.port, session)
                _ = runtime
                return {"status": "success", "streams": service.get_stream_status()}
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
                async with self._registry_lock:
                    if not self._get_desired_entry_for_port(port):
                        raise HTTPException(status_code=404, detail="Session not found")

                    await self._remove_record_and_stop_reconciliation(port)
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
                async with self._registry_lock:
                    entry = self._get_desired_entry_for_port(port)
                    if not entry:
                        raise HTTPException(status_code=404, detail="Session not found")

                    runtime = self.runtime_by_port.get(port)
                    session = runtime.session if runtime else None
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

                    await self._remove_record_and_stop_reconciliation(port)
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
            try:
                async with self._registry_lock:
                    entry = self._get_desired_entry_for_port(port)
                    if not entry:
                        raise HTTPException(status_code=404, detail="Session not found")

                    runtime = self._get_or_create_runtime(entry)
                    runtime.state = SessionState.STOPPING
                    session = runtime.session
                    if session:
                        await self._persist_runtime_snapshot(port)
                        with contextlib.suppress(Exception):
                            await asyncio.wait_for(session.force_kill(), timeout=1.0)

                    await self._cleanup_runtime_generation(
                        port,
                        runtime.generation,
                        remove_record=False,
                        ignore_generation_mismatch=True,
                    )

                    runtime = self._get_or_create_runtime(entry)
                    runtime = await self._realize_runtime(
                        entry,
                        runtime,
                        preserve_session_id=entry.session_id,
                    )

                    write_daemon_log(
                        f"Session restarted: port={port}, name={entry.name}"
                    )
                    await self._publish_session_event("session/restarted", entry)

                    return {
                        "status": "restarted",
                        "port": port,
                        "name": entry.name,
                        "title": (
                            runtime.session.title if runtime.session else entry.title
                        ),
                        "shell": entry.shell_type,
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
            """Graceful shutdown: close live sessions, preserve records, and stop the daemon.

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
                    await self._persist_runtime_snapshot(port)
                    await asyncio.wait_for(
                        self._ensure_cleanup_task(port, remove_record=False),
                        timeout=remaining,
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

        @app.websocket("/events")
        async def daemon_events(websocket: WebSocket) -> None:
            await websocket.accept()
            await self.events.register(websocket)
            try:
                await websocket.send_bytes(
                    encode_ws_frame(
                        build_manager_event_header(
                            "session/snapshot",
                            sessions=self._list_session_snapshots(),
                        )
                    )
                )
                while True:
                    await websocket.receive()
            except (WebSocketDisconnect, RuntimeError):
                pass
            finally:
                await self.events.unregister(websocket)

        @app.post("/killall")
        async def killall():
            """Clear all sessions and session artifacts while keeping the daemon alive."""

            write_daemon_log("Killall requested")

            async with self._registry_lock:
                ports = [entry.port for entry in self.registry.list_all()]
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
                        await self._remove_record_and_stop_reconciliation(port)
                    except HTTPException:
                        continue
                    except Exception as exc:
                        write_daemon_log(
                            f"Error clearing session: port={port}, error={exc}"
                        )

            write_daemon_log(f"Killall complete: cleared {len(ports)} session(s)")
            return {"status": "cleared", "removed": len(ports)}

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

    def _get_desired_entry_for_port(self, port: int):
        return self.registry.get(port)

    def _get_desired_entry_for_name(self, name: str):
        return self.registry.get_by_name(name)

    def _serialize_session_entry(self, entry) -> dict[str, object]:
        return serialize_session_snapshot(entry, self.runtime_by_port.get(entry.port))

    def _list_session_snapshots(self) -> list[dict[str, object]]:
        return serialize_session_snapshots(
            self.registry.list_all(), self.runtime_by_port
        )

    def _persist_desired_sessions(self) -> None:
        write_sessions_json([entry.to_json() for entry in self.registry.list_all()])

    async def _publish_session_snapshot(self) -> None:
        await self.events.publish(
            build_manager_event_header(
                "session/snapshot", sessions=self._list_session_snapshots()
            )
        )

    async def _publish_session_event(self, event_type: str, entry) -> None:
        snapshot = self._serialize_session_entry(entry)
        await self.events.publish(build_manager_event_header(event_type, snapshot))
        await self.events.publish(
            build_manager_event_header("session/updated", snapshot)
        )

    async def _publish_removed_session_event(self, snapshot: dict[str, object]) -> None:
        await self.events.publish(
            build_manager_event_header("session/removed", snapshot)
        )

    def _get_or_create_runtime(
        self,
        entry,
        *,
        api_token: str | None = None,
        title: str | None = None,
    ) -> SessionRuntime:
        runtime = self.runtime_by_port.get(entry.port)
        if runtime is None:
            runtime = create_runtime_for_record(
                entry,
                api_token=api_token,
                title=title,
            )
            self.runtime_by_port[entry.port] = runtime
            return runtime

        runtime.name = entry.name
        runtime.shell_type = entry.shell_type
        runtime.cwd = entry.cwd
        runtime.is_global = entry.is_global
        if api_token is not None:
            runtime.api_token = api_token
        if title is not None:
            runtime.title = title
        return runtime

    def _build_runtime_launch_context(self, entry, runtime: SessionRuntime) -> dict:
        from silc.utils.shell_detect import get_shell_info_by_type

        shell_info = get_shell_info_by_type(entry.shell_type)
        if shell_info is None:
            raise ValueError(f"unknown_shell: {entry.shell_type}")

        return {
            "shell_info": shell_info,
            "cwd": runtime.cwd if runtime.cwd is not None else entry.cwd,
            "api_token": runtime.api_token,
            "title": runtime.title,
            "is_global": runtime.is_global,
        }

    def _schedule_reconcile(self) -> None:
        self._reconcile_event.set()

    def _runtime_is_alive(self, runtime: SessionRuntime) -> bool:
        session = runtime.session
        if not session:
            return False
        try:
            return bool(session.get_status().get("alive"))
        except Exception:
            return False

    def _runtime_server_is_alive(self, runtime: SessionRuntime) -> bool:
        server = runtime.server
        task = runtime.server_task
        if task:
            try:
                if not task.done():
                    return True
            except Exception:
                return False
            if task.cancelled():
                return False
            try:
                if task.exception() is not None:
                    return False
            except Exception:
                return False
        if hasattr(server, "is_serving"):
            try:
                return bool(server.is_serving())
            except Exception:
                return False
        return False

    async def _cleanup_runtime_generation(
        self,
        port: int,
        generation: int,
        *,
        remove_record: bool = False,
        ignore_generation_mismatch: bool = False,
    ) -> None:
        runtime = self.runtime_by_port.get(port)
        if not runtime:
            return
        if runtime.generation != generation and not ignore_generation_mismatch:
            return

        server = runtime.server or self.servers.pop(port, None)
        if server:
            server.should_exit = True

        task = self._session_tasks.pop(port, None) or runtime.server_task
        if task:
            task.cancel()
            with contextlib.suppress(
                asyncio.CancelledError, asyncio.TimeoutError, OSError
            ):
                await asyncio.wait_for(task, timeout=2.0)
            if not task.cancelled():
                with contextlib.suppress(Exception):
                    task.exception()

        session = self.sessions.pop(port, None) or runtime.session
        if session:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(session.close(), timeout=2.0)

        with contextlib.suppress(Exception):
            await self._stop_streaming_service(port)

        await self._close_tracked_session_websocket(
            port, code=1012, reason="Session runtime stopped"
        )
        self._active_session_websocket_locks.pop(port, None)

        with contextlib.suppress(Exception):
            await self._kill_processes_on_port(port)

        self._close_session_socket(port)

        runtime.session = None
        runtime.server = None
        runtime.server_task = None
        runtime.socket = None

        if remove_record:
            snapshot = None
            entry = self.registry.get(port)
            if entry is not None:
                snapshot = serialize_session_snapshot(entry, runtime)
            removed_entry = self.registry.remove(port)
            if removed_entry is not None:
                remove_session_snapshot(removed_entry.session_id)
            self._persist_desired_sessions()
            cleanup_session_log(port)
            runtime.state = SessionState.STOPPED
            self.runtime_by_port.pop(port, None)
            write_daemon_log(f"Session closed: port={port}")
            if snapshot is not None:
                await self._publish_removed_session_event(snapshot)
        else:
            if runtime.state != SessionState.STOPPING:
                runtime.state = SessionState.DEGRADED

    async def _remove_record_and_stop_reconciliation(self, port: int) -> None:
        entry = self._get_desired_entry_for_port(port)
        if not entry:
            raise HTTPException(status_code=404, detail="Session not found")

        snapshot = self._serialize_session_entry(entry)

        removed_entry = self.registry.remove(port)
        if removed_entry is not None:
            remove_session_snapshot(removed_entry.session_id)
        self._persist_desired_sessions()
        self._reconcile_event.set()

        runtime = self.runtime_by_port.get(port)
        if runtime:
            runtime.state = SessionState.STOPPING
            await self._cleanup_runtime_generation(
                port,
                runtime.generation,
                remove_record=False,
                ignore_generation_mismatch=True,
            )
            self.runtime_by_port.pop(port, None)
        cleanup_session_log(port)
        await self._publish_removed_session_event(snapshot)

    async def _load_persisted_desired_records(self) -> dict:
        from silc.utils.persistence import read_sessions_json

        result = {"loaded": [], "failed": []}
        for record in read_sessions_json():
            try:
                port = int(record["port"])
                name = str(record["name"])
                session_id = str(record.get("session_id") or uuid.uuid4().hex[:8])
                shell_type = str(record["shell"])
                cwd = record.get("cwd")
                title = str(record.get("title") or "")
                is_global = bool(record.get("is_global", False) or self._share_mode)

                if self.registry.get(port) or self.registry.name_exists(name):
                    continue

                entry = self.registry.add(
                    port,
                    name,
                    session_id,
                    shell_type,
                    cwd=cwd,
                    title=title,
                    is_global=is_global,
                )
                result["loaded"].append({"port": port, "name": name})
            except Exception as exc:
                result["failed"].append(
                    {"port": record.get("port"), "reason": _exception_detail(exc)}
                )
                _log_daemon_exception("load_persisted_desired_record", exc)

        return result

    async def _realize_runtime(
        self,
        entry,
        runtime: SessionRuntime,
        *,
        preserve_session_id: str | None = None,
    ) -> SessionRuntime:
        runtime = self._get_or_create_runtime(entry)
        runtime = bump_runtime_generation(runtime)
        runtime.state = SessionState.STARTING
        runtime.last_error = ""
        runtime.last_traceback = ""
        runtime.next_retry_at = None
        self.runtime_by_port[entry.port] = runtime

        session: SilcSession | None = None
        task: asyncio.Task[None] | None = None
        server: SessionPortAdapter | None = None

        try:
            launch_context = self._build_runtime_launch_context(entry, runtime)
            socket_handle = self._reserve_session_socket(
                entry.port, launch_context["is_global"]
            )
            runtime.socket = socket_handle

            session = await self._construct_session(
                entry.port,
                entry.name,
                launch_context["shell_info"],
                api_token=launch_context["api_token"],
                cwd=launch_context["cwd"],
                title=launch_context["title"],
            )
            if preserve_session_id:
                session.session_id = preserve_session_id
            else:
                session.session_id = entry.session_id

            await self._start_session_with_timeout(session)

            server = self._create_session_server(
                session, is_global=launch_context["is_global"]
            )
            task = asyncio.create_task(server.serve(sockets=[socket_handle]))

            runtime.session = session
            runtime.server = server
            runtime.server_task = task
            runtime.state = SessionState.RUNNING

            self.sessions[entry.port] = session
            self.servers[entry.port] = server
            self._session_tasks[entry.port] = task
            self._attach_session_task(entry.port, runtime.generation, task)
            self._schedule_reconcile()
            asyncio.create_task(self._publish_session_event("session/started", entry))
            return runtime
        except Exception as exc:
            await self._discard_partial_session_state(
                entry.port,
                operation="realize_runtime",
                session=session,
                task=task,
                remove_record=False,
            )
            runtime = self.runtime_by_port.get(entry.port, runtime)
            runtime = record_runtime_failure(
                runtime,
                error=_exception_detail(exc),
                traceback_text=_capture_exception_traceback(exc),
            )
            self.runtime_by_port[entry.port] = runtime
            write_daemon_log(format_runtime_state(runtime))
            self._schedule_reconcile()
            if isinstance(exc, HTTPException):
                raise
            raise

    async def _persist_runtime_snapshot(self, port: int) -> None:
        entry = self._get_desired_entry_for_port(port)
        runtime = self.runtime_by_port.get(port)
        session = runtime.session if runtime else None
        if not entry or session is None:
            return

        try:
            snapshot_bytes = session.get_snapshot_bytes()
        except Exception as exc:
            write_daemon_log(
                f"Failed to capture session snapshot: port={port}, session_id={entry.session_id}, error={exc}"
            )
            return

        try:
            write_session_snapshot(entry.session_id, snapshot_bytes)
            write_daemon_log(
                f"Saved session snapshot: port={port}, session_id={entry.session_id}, bytes={len(snapshot_bytes)}"
            )
        except Exception as exc:
            write_daemon_log(
                f"Failed to write session snapshot: port={port}, session_id={entry.session_id}, error={exc}"
            )

    async def _ensure_runtime_server(
        self, entry, runtime: SessionRuntime
    ) -> SessionRuntime:
        session = runtime.session or self.sessions.get(entry.port)
        if not session:
            raise RuntimeError("Missing live session for adapter replacement")

        runtime = self._get_or_create_runtime(entry)
        runtime = bump_runtime_generation(runtime)
        runtime.state = SessionState.STARTING
        runtime.last_error = ""
        runtime.last_traceback = ""
        runtime.next_retry_at = None
        self.runtime_by_port[entry.port] = runtime

        socket_handle = runtime.socket or self._session_sockets.get(entry.port)
        if socket_handle is None:
            socket_handle = self._reserve_session_socket(entry.port, runtime.is_global)
        runtime.socket = socket_handle

        server = self._create_session_server(session, is_global=runtime.is_global)
        task = asyncio.create_task(server.serve(sockets=[socket_handle]))

        runtime.session = session
        runtime.server = server
        runtime.server_task = task
        runtime.state = SessionState.RUNNING

        self.sessions[entry.port] = session
        self.servers[entry.port] = server
        self._session_tasks[entry.port] = task
        self._attach_session_task(entry.port, runtime.generation, task)
        self._schedule_reconcile()
        return runtime

    async def _reconcile_record(
        self, entry, *, materialize_missing: bool = False
    ) -> None:
        runtime = self.runtime_by_port.get(entry.port)
        if runtime is None:
            if not materialize_missing:
                return
            runtime = self._get_or_create_runtime(entry)
        if runtime.state == SessionState.STARTING:
            return
        if runtime.state in {SessionState.STOPPING, SessionState.STOPPED}:
            return
        if runtime.state == SessionState.BACKOFF and not runtime_backoff_expired(
            runtime
        ):
            return

        if not self._runtime_is_alive(runtime):
            await self._cleanup_runtime_generation(
                entry.port, runtime.generation, remove_record=False
            )
            runtime = self._get_or_create_runtime(entry)
            await self._realize_runtime(
                entry, runtime, preserve_session_id=entry.session_id
            )
            return

        if not self._runtime_server_is_alive(runtime):
            runtime.server = None
            runtime.server_task = None
            await self._ensure_runtime_server(entry, runtime)
            return

        runtime.state = SessionState.RUNNING

    async def _reconcile_desired_sessions_once(
        self, *, materialize_missing: bool = False
    ) -> None:
        for entry in self.registry.list_all():
            try:
                await self._reconcile_record(
                    entry, materialize_missing=materialize_missing
                )
            except Exception as exc:
                runtime = self._get_or_create_runtime(entry)
                runtime = record_runtime_failure(
                    runtime,
                    error=_exception_detail(exc),
                    traceback_text=_capture_exception_traceback(exc),
                    backoff_seconds=2.0,
                )
                self.runtime_by_port[entry.port] = runtime
                write_daemon_log(format_runtime_state(runtime))

    async def _reconcile_loop(self) -> None:
        while self._running and not self._shutdown_event.is_set():
            self._reconcile_event.clear()
            try:
                await self._reconcile_desired_sessions_once(materialize_missing=False)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                _log_daemon_exception("reconcile_loop", exc)
            try:
                await asyncio.wait_for(self._reconcile_event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                return

    def _create_session_server(
        self, session: SilcSession, is_global: bool = False
    ) -> SessionPortAdapter:
        """Create a lightweight adapter for a live session port."""

        del is_global
        return SessionPortAdapter(
            session_port=session.port,
            daemon_host="127.0.0.1",
            daemon_port=DAEMON_PORT,
        )

    def _handle_session_title_change(self, session: SilcSession) -> None:
        """Persist a live title change from a running session."""
        entry = self.registry.update_title(
            session.port, session.title, updated_at=session.title_updated_at
        )
        if not entry:
            return

        self._persist_desired_sessions()
        asyncio.create_task(self._publish_session_event("session/title_changed", entry))

    def _handle_session_cwd_change(self, session: SilcSession) -> None:
        """Persist a live cwd change from a running session."""
        entry = self.registry.update_cwd(session.port, session.cwd)
        runtime = self.runtime_by_port.get(session.port)
        if runtime is not None:
            runtime.cwd = session.cwd
        if not entry:
            return

        self._persist_desired_sessions()
        asyncio.create_task(self._publish_session_event("session/cwd_changed", entry))

    def _attach_session_task(
        self, port: int, generation: int, task: asyncio.Task[None]
    ) -> None:
        task.add_done_callback(
            partial(self._handle_session_task_done, port, generation)
        )

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
                self._handle_session_cwd_change,
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
        remove_record: bool = True,
    ) -> None:
        """Remove any partially-created session state after a failed start path."""

        runtime = self.runtime_by_port.get(port)
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
        with contextlib.suppress(Exception):
            await self._stop_streaming_service(port)
        await self._close_tracked_session_websocket(
            port, code=1011, reason="Session startup failed"
        )
        self._active_session_websocket_locks.pop(port, None)

        if runtime:
            runtime.session = None
            runtime.server = None
            runtime.server_task = None
            runtime.socket = None

        if remove_record:
            try:
                removed_entry = self.registry.remove(port)
                if removed_entry is not None:
                    remove_session_snapshot(removed_entry.session_id)
            except Exception as cleanup_exc:
                _log_daemon_exception(f"{operation}_rollback_registry", cleanup_exc)
            try:
                self._persist_desired_sessions()
            except Exception as cleanup_exc:
                _log_daemon_exception(f"{operation}_rollback_persistence", cleanup_exc)

    def _handle_session_task_done(
        self, port: int, generation: int, task: asyncio.Task[None]
    ) -> None:
        operation = "handle_session_task_done"
        try:
            runtime = self.runtime_by_port.get(port)
            if not runtime or runtime.generation != generation:
                return
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
            runtime.server = None
            runtime.server_task = None
            runtime = record_runtime_failure(
                runtime,
                error=_exception_detail(exc),
                traceback_text=_capture_exception_traceback(exc),
                backoff_seconds=1.0,
            )
            self.runtime_by_port[port] = runtime
            self._schedule_reconcile()
        except Exception as exc:
            _log_daemon_exception(operation, exc)

    def _ensure_cleanup_task(
        self, port: int, *, remove_record: bool = True
    ) -> asyncio.Task[None]:
        """Ensure a cleanup task exists for the given port."""
        task = self._cleanup_tasks.get(port)
        if task and not task.done():
            return task
        task = asyncio.create_task(
            self._cleanup_session(port, remove_record=remove_record)
        )
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
            if (
                port in self.runtime_by_port
                or port in self._session_sockets
                or self.registry.get(port)
            ):
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

    async def _cleanup_session(self, port: int, *, remove_record: bool = True) -> None:
        """Cleanup a session: close server, close session, cleanup registry.

        This path must be *bounded* (never hang forever). The daemon shutdown
        sequence relies on cleanup completing even when uvicorn/PTY teardown is
        flaky on some platforms.
        """

        runtime = self.runtime_by_port.get(port)
        entry = self._get_desired_entry_for_port(port)

        if runtime:
            runtime.state = SessionState.STOPPING
            await self._cleanup_runtime_generation(
                port,
                runtime.generation,
                remove_record=remove_record and bool(entry),
                ignore_generation_mismatch=True,
            )
            self.runtime_by_port.pop(port, None)
            cleanup_session_log(port)
            with contextlib.suppress(Exception):
                await self._stop_streaming_service(port)
            return

        if entry:
            if not remove_record:
                cleanup_session_log(port)
                return
            snapshot = serialize_session_snapshot(entry, runtime)
            removed_entry = self.registry.remove(port)
            if removed_entry is not None:
                remove_session_snapshot(removed_entry.session_id)
            self._persist_desired_sessions()
            cleanup_session_log(port)
            write_daemon_log(f"Session closed: port={port}")
            await self._publish_removed_session_event(snapshot)

    async def _resurrect_sessions(self) -> dict:
        """Load desired records from sessions.json and reconcile them."""

        result = await self._load_persisted_desired_records()
        restored: list[dict[str, object]] = []
        if not self.registry.list_all():
            write_daemon_log("No sessions to resurrect")
            result["restored"] = restored
            return result

        write_daemon_log(
            f"Loaded {len(self.registry.list_all())} desired sessions; materializing..."
        )

        for entry in self.registry.list_all():
            runtime_before = self.runtime_by_port.get(entry.port)
            was_live = runtime_before is not None and self._runtime_is_alive(
                runtime_before
            )
            try:
                await self._reconcile_record(entry, materialize_missing=True)
            except Exception as exc:
                result["failed"].append(
                    {
                        "port": entry.port,
                        "name": entry.name,
                        "reason": _exception_detail(exc),
                    }
                )
                _log_daemon_exception("resurrect_sessions_materialize", exc)
                continue

            runtime_after = self.runtime_by_port.get(entry.port)
            if not was_live and runtime_after and self._runtime_is_alive(runtime_after):
                restored.append(
                    {
                        "port": entry.port,
                        "name": entry.name,
                        "title": (
                            runtime_after.session.title
                            if runtime_after.session
                            else entry.title
                        ),
                        "session_id": entry.session_id,
                        "shell": entry.shell_type,
                    }
                )

        result["restored"] = restored
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
                    await self._persist_runtime_snapshot(port)
                    await asyncio.wait_for(
                        self._ensure_cleanup_task(port, remove_record=False),
                        timeout=remaining,
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
                        write_daemon_log(
                            "Use 'silc shutdown' or 'silc full-reset' first"
                        )
                        raise RuntimeError(
                            f"Daemon already running (PID {existing_pid}). "
                            "Use 'silc shutdown' or 'silc full-reset' to stop it."
                        )
                except psutil.NoSuchProcess:
                    write_daemon_log(
                        f"Stale PID file found (PID {existing_pid}), cleaning up..."
                    )

        write_pidfile(os.getpid())
        self._running = True
        self._setup_signals()

        try:
            await self._load_persisted_desired_records()
            valid_session_ids = {entry.session_id for entry in self.registry.list_all()}
            removed_snapshot_ids = garbage_collect_session_snapshots(valid_session_ids)
            if removed_snapshot_ids:
                write_daemon_log(
                    f"Removed {len(removed_snapshot_ids)} orphan session snapshot(s): {', '.join(sorted(removed_snapshot_ids))}"
                )
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
        reconcile_task = asyncio.create_task(self._reconcile_loop())

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
            reconcile_task.cancel()
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
