# Repository Guidelines

## Project Structure & Module Organization
- `silc/` is the Python package that owns the CLI (`__main__.py`), the FastAPI endpoints (`silc/api/`), the session helpers (`silc/core/`), the Textual UI (`silc/tui/`), and utility helpers (`silc/utils/`). Reference `Implementation_plan.md` for a visual tree of how the submodules fit together.
- `tests/` mirrors production files with `tests/test_session.py` and helper cases that target the buffer, PTY, and session lifecycle behaviors described in `README.md`.
- Supporting scripts such as `main.py` and `debug_winpty.py` demonstrate entry points or Windows plumbing; treat them as launch aids rather than part of the core package.
- Metadata and dependency pins live in `pyproject.toml`, so keep build requirements aligned with the `fastapi`, `textual`, and `pywinpty` ranges declared there.

## Build, Test, and Development Commands
- `pip install -e .` bootstraps the `silc` console script and installs production dependencies so you can run `silc start` directly.
- `pip install -e .[test]` pulls in `pytest`/`pytest-asyncio` extras referenced in `pyproject.toml` before exercising the test suite.
- `silc start [--port PORT] [--global]` launches a session, spins up the FastAPI server documented in `silc/api/server.py`, and opens the TUI; use `--global` carefully because it binds to `0.0.0.0`.
- `silc <PORT> run "<cmd>"`, `silc <PORT> out`, `silc <PORT> in "<text>"`, and `silc <PORT> status` exercise the agent-facing API routes and mimic the HTTP examples in `Implementation_plan.md`.
- `pytest tests/` validates the session, symlinked PTY, and buffer helpers in `tests/`; rerun after any change to `silc/core/` or `silc/api/`.

## Coding Style & Naming Conventions
- Follow standard Python conventions: 4-space indentation, snake_case for functions, camelCase only for Pydantic models if already defined in `silc/api/models.py`, and keep modules small (each file focuses on one responsibility like `session.py`, `buffer.py`, etc.).
- Prefer explicit return types and type hints because the project already annotates `SilcSession` methods and helper functions; keep docstrings short but descriptive.
- Sequence logging/debug helpers through `click.echo` or `print` in CLI entry points and avoid excessive inline comments beyond the docstrings provided.

## Testing Guidelines
- Tests rely on `pytest` plus `pytest-asyncio` for async session coverage; see `tests/test_session.py` for the canonical patterns.
- Name new tests `test_*` and keep them grouped with existing ones under `tests/` so runners pick them up automatically.
- When a test touches the PTY or session lifecycle, reuse fixtures that mirror `silc/core/session.py` behavior (e.g., setting up a `SilcSession` and awaiting `start()`).
- Document any manual verification (e.g., `silc start` → `curl http://localhost:PORT/status`) inside the relevant test case so reviewers know how you exercised the feature.

## Commit & Pull Request Guidelines
- The repository is still empty, so create new commits with concise summaries like `feat: add queueing for run command` or `fix: normalize shell output before API`. Keep bodies brief and reference files touched.
- Pull requests should describe the change, link to any related issue when available, and list commands you ran (e.g., `pytest tests/`). Include screenshots or terminal output only when the change alters the TUI or CLI behavior.
- Tag reviewers with context: describe the session/command you tested (`silc start`, `silc <port> run`, etc.) and mention any known limitations (timeouts, locking).

## Security & Configuration Tips
- The `silc start --global` option exposes the HTTP API on all interfaces; firewall or VPN the host before using it on untrusted networks.
- Sessions idle for over an hour with no child processes are garbage-collected, so test automation should ping the session periodically or override that behavior in `silc/core/session.py` before relying on long-running commands.
