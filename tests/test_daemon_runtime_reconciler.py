"""Focused tests for daemon record-first runtime reconciliation."""

# FILE: tests/test_daemon_runtime_reconciler.py
# PURPOSE: Prove daemon ownership stays with desired records while runtime can fail and be replaced.
# OWNS: Targeted tests for record survival, generation safety, and runtime replacement behavior.
# EXPORTS: pytest test cases only.
# DOCS: agent_chat/plan_daemon_rewrite_2026-04-05.md, docs/arch_daemon.md

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from silc.daemon.manager import SilcDaemon
from silc.daemon.runtime import (
    SessionState,
    bump_runtime_generation,
    create_runtime_for_record,
)


class _FakeSession:
    def __init__(self, port: int, name: str, session_id: str = "sess-1") -> None:
        self.port = port
        self.name = name
        self.session_id = session_id
        self.title = ""
        self.cwd = None
        self.api_token = None
        self.shell_info = SimpleNamespace(type="bash")
        self.pty = SimpleNamespace(pid=12345)
        self.closed = False
        self.killed = False

    def get_status(self) -> dict:
        return {"alive": True, "idle_seconds": 0}

    async def close(self) -> None:
        self.closed = True

    async def force_kill(self) -> None:
        self.killed = True


async def _post_json(daemon: SilcDaemon, path: str, payload: dict) -> httpx.Response:
    transport = httpx.ASGITransport(app=daemon._create_daemon_api())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(path, json=payload)


async def _get_json(daemon: SilcDaemon, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=daemon._create_daemon_api())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


@pytest.mark.asyncio
async def test_create_failure_keeps_record_and_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    daemon = SilcDaemon(enable_hard_exit=False)
    monkeypatch.setattr(daemon, "_find_available_session_port", lambda: 20001)
    monkeypatch.setattr(
        daemon, "_validate_session_launch", lambda *args, **kwargs: None
    )

    async def fail_construct(*args, **kwargs):
        raise RuntimeError("pty failed")

    monkeypatch.setattr(daemon, "_construct_session", fail_construct)

    resp = await _post_json(daemon, "/sessions", {"name": "alpha", "shell": "bash"})

    assert resp.status_code == 500
    payload = resp.json()
    assert payload["operation"] == "create_session"
    assert daemon.registry.get(20001) is not None
    runtime = daemon.runtime_by_port[20001]
    assert runtime.state == SessionState.BACKOFF
    assert runtime.next_retry_at is not None
    assert daemon.sessions.get(20001) is None


@pytest.mark.asyncio
async def test_server_failure_keeps_record_and_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    daemon = SilcDaemon(enable_hard_exit=False)
    monkeypatch.setattr(daemon, "_find_available_session_port", lambda: 20002)
    monkeypatch.setattr(
        daemon, "_validate_session_launch", lambda *args, **kwargs: None
    )

    async def fake_construct(*args, **kwargs):
        return _FakeSession(20002, "beta", session_id="sess-2")

    async def fake_start(*args, **kwargs):
        return None

    def fail_server(*args, **kwargs):
        raise RuntimeError("server failed")

    monkeypatch.setattr(daemon, "_construct_session", fake_construct)
    monkeypatch.setattr(daemon, "_start_session_with_timeout", fake_start)
    monkeypatch.setattr(daemon, "_create_session_server", fail_server)

    resp = await _post_json(daemon, "/sessions", {"name": "beta", "shell": "bash"})

    assert resp.status_code == 500
    assert daemon.registry.get(20002) is not None
    runtime = daemon.runtime_by_port[20002]
    assert runtime.state == SessionState.BACKOFF
    assert runtime.last_error


@pytest.mark.asyncio
async def test_restart_preserves_record_and_bumps_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    daemon = SilcDaemon(enable_hard_exit=False)
    entry = daemon.registry.add(20003, "gamma", "sess-3", "bash")
    runtime = create_runtime_for_record(entry)
    runtime.generation = 3
    runtime.session = _FakeSession(20003, "gamma", session_id="sess-3")
    runtime.server = SimpleNamespace(should_exit=False)
    daemon.runtime_by_port[20003] = runtime
    daemon.sessions[20003] = runtime.session
    daemon.servers[20003] = runtime.server

    async def fake_realize(entry, runtime, preserve_session_id=None):
        runtime = bump_runtime_generation(runtime)
        runtime.session = _FakeSession(
            entry.port, entry.name, session_id=preserve_session_id or entry.session_id
        )
        runtime.server = SimpleNamespace(should_exit=False)
        runtime.state = SessionState.RUNNING
        daemon.runtime_by_port[entry.port] = runtime
        daemon.sessions[entry.port] = runtime.session
        daemon.servers[entry.port] = runtime.server
        return runtime

    monkeypatch.setattr(daemon, "_realize_runtime", fake_realize)

    resp = await _post_json(daemon, "/sessions/20003/restart", {})

    assert resp.status_code == 200
    assert daemon.registry.get(20003) is not None
    runtime = daemon.runtime_by_port[20003]
    assert runtime.generation == 4
    assert runtime.session is not None
    assert runtime.session.session_id == "sess-3"


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["close", "kill"])
async def test_close_and_kill_remove_records(
    monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    daemon = SilcDaemon(enable_hard_exit=False)
    entry = daemon.registry.add(
        20004 if action == "close" else 20005,
        f"{action}-session",
        f"sess-{action}",
        "bash",
    )
    runtime = create_runtime_for_record(entry)
    runtime.session = _FakeSession(entry.port, entry.name, session_id=entry.session_id)
    runtime.server = SimpleNamespace(should_exit=False)
    daemon.runtime_by_port[entry.port] = runtime
    daemon.sessions[entry.port] = runtime.session
    daemon.servers[entry.port] = runtime.server

    port = entry.port
    resp = await _post_json(daemon, f"/sessions/{port}/{action}", {})

    assert resp.status_code == 200
    assert daemon.registry.get(port) is None
    assert port not in daemon.runtime_by_port


@pytest.mark.asyncio
async def test_stale_generation_callback_is_ignored() -> None:
    daemon = SilcDaemon(enable_hard_exit=False)
    entry = daemon.registry.add(20006, "delta", "sess-6", "bash")
    runtime = create_runtime_for_record(entry)
    runtime.generation = 7
    runtime.session = _FakeSession(20006, "delta", session_id="sess-6")
    daemon.runtime_by_port[20006] = runtime

    class _DummyTask:
        def cancelled(self) -> bool:
            return False

        def exception(self):
            raise AssertionError("stale generation should not be inspected")

    daemon._handle_session_task_done(20006, 6, _DummyTask())

    assert daemon.runtime_by_port[20006].generation == 7
    assert daemon.runtime_by_port[20006].state == SessionState.STARTING


@pytest.mark.asyncio
async def test_idle_time_does_not_delete_desired_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    daemon = SilcDaemon(enable_hard_exit=False)
    entry = daemon.registry.add(20007, "idle-session", "sess-7", "bash")
    entry.last_access = entry.last_access.replace(year=2000)

    def fail_cleanup_timeout(*args, **kwargs):
        raise AssertionError("daemon must not delete desired sessions by idle timeout")

    monkeypatch.setattr(daemon.registry, "cleanup_timeout", fail_cleanup_timeout)

    resp = await _get_json(daemon, "/sessions")

    assert resp.status_code == 200
    assert daemon.registry.get(20007) is not None
