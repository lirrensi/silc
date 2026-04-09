"""Smoke tests for the manager and session web asset routes."""

# FILE: tests/test_web_ui_routes.py
# PURPOSE: Verify the daemon serves the manager and session web builds from their separate static paths.
# OWNS: Static web asset path smoke tests for /ui and /web.
# EXPORTS: pytest test cases only.
# DOCS: agent_chat/plan_web_shell_split_2026-04-09.md

from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

import silc.api.server as session_server
import silc.daemon.manager as manager_module
from silc.api.server import create_app
from silc.daemon.manager import SilcDaemon


def test_session_web_route_redirects_and_serves_assets(tmp_path, monkeypatch) -> None:
    static_root = tmp_path / "silc" / "api"
    web_dir = tmp_path / "static" / "web"
    assets_dir = web_dir / "assets"
    assets_dir.mkdir(parents=True)
    (web_dir / "index.html").write_text(
        '<!doctype html><script type="module" src="./assets/main.js"></script>',
        encoding="utf-8",
    )
    (assets_dir / "main.js").write_text(
        "console.log('session asset')", encoding="utf-8"
    )

    monkeypatch.setattr(
        session_server, "Path", lambda *_args, **_kwargs: static_root / "server.py"
    )

    client = TestClient(
        create_app(SimpleNamespace(session_id="session-1", api_token=None))
    )

    response = client.get("/web", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/web/"

    html_response = client.get("/web/")
    asset_response = client.get("/web/assets/main.js")

    assert html_response.status_code == 200
    assert "./assets/main.js" in html_response.text
    assert asset_response.status_code == 200
    assert "session asset" in asset_response.text


def test_manager_session_web_route_serves_without_redirect_and_keeps_assets(
    tmp_path, monkeypatch
) -> None:
    static_root = tmp_path / "silc" / "daemon"
    web_dir = tmp_path / "static" / "web"
    assets_dir = web_dir / "assets"
    assets_dir.mkdir(parents=True)
    (web_dir / "index.html").write_text(
        '<!doctype html><script type="module" src="./assets/main.js"></script>',
        encoding="utf-8",
    )
    (assets_dir / "main.js").write_text("console.log('daemon asset')", encoding="utf-8")

    monkeypatch.setattr(
        manager_module, "Path", lambda *_args, **_kwargs: static_root / "manager.py"
    )

    daemon = SilcDaemon(enable_hard_exit=False)
    daemon._resolve_session_target = lambda key, operation: (  # type: ignore[method-assign]
        SimpleNamespace(port=int(key)),
        SimpleNamespace(session=SimpleNamespace()),
    )
    client = TestClient(daemon._create_daemon_api())

    response = client.get("/sessions/1234/web", follow_redirects=False)
    html_response = client.get("/sessions/1234/web/")
    asset_response = client.get("/sessions/1234/web/assets/main.js")

    assert response.status_code == 200
    assert "location" not in response.headers
    assert "./assets/main.js" in response.text
    assert "/web/assets/main.js" not in response.text
    assert html_response.status_code == 200
    assert "./assets/main.js" in html_response.text
    assert "/web/assets/main.js" not in html_response.text
    assert asset_response.status_code == 200
    assert "daemon asset" in asset_response.text
