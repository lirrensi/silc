# AGENTS.md

## Overview

`SharedShell` is a Python‑first CLI and FastAPI service that manages terminal sessions and a Textual UI.

The repository is centered around the `silc/` package, with tests in `tests/` and documentation in `docs/`.

## Build & Install

```bash
# Editable install with production dependencies
pip install -e .

# Editable install with test dependencies
pip install -e .[test]
```

The console script `silc` is exposed after the editable install.

```bash
silc start --port 8000   # launches server and TUI
```

## Linting & Formatting

The project uses **Black**, **isort**, **flake8**, and **mypy**.  All tools are configured via `pyproject.toml` and a `pre‑commit` hook.

```bash
# Run all linters
pre-commit run --all-files
```

### Black
- 88‑character line width.
- Hook rewrites files; no `--check`.

### isort
- Groups: `stdlib`, `thirdparty`, `localfolder`.
- Alphabetical within groups.
- Imports sorted before the first non‑import.

### flake8
- Syntax, unused imports, style.
- Ignores `E501`.

### mypy
- Type check `silc/` with `--strict`.

## Type Checking

```bash
mypy silc/
```

2011first CLI and FastAPI service that manages terminal sessions and a Textual UI.

The repository is centered around the `silc/` package, with tests in `tests/` and documentation in `docs/`.

## Build & Install

```bash
# Editable install with production dependencies
pip install -e .

# Editable install with test dependencies
pip install -e .[test]
```

The console script `silc` is exposed after the editable install.

```bash
silc start --port 8000   # launches server and TUI
```

## Linting & Formatting

The project uses **Black**, **isort**, **flake8**, and **mypy**.  All tools are configured via `pyproject.toml` and a `pre‑commit` hook.

```bash
# Run all linters
pre-commit run --all-files
```

### Black
- 88‑character line width.
- Hook rewrites files; no `--check`.

### isort
- Groups: `stdlib`, `thirdparty`, `localfolder`.
- Alphabetical within groups.
- Imports sorted before the first non‑import.

### flake8
- Syntax, unused imports, style.
- Ignores `E501`.

### mypy
- Type check `silc/` with `--strict`.

## Type Checking

```bash
mypy silc/
```

All public functions must have explicit return types.

## Testing

The test suite is powered by **pytest** with **pytest‑asyncio**.

```bash
pytest tests/
```

### Running a Single Test

```bash
# By test path and name
pytest tests/test_session.py::TestSession::test_start

# By marker
pytest -m integration
```

## Code Style Guidelines

### Imports
1. Order: `stdlib`, `thirdparty`, `local`.
2. Blank line between groups.
3. Prefer `from module import Class`.

### Formatting
- Run `pre-commit` before commits.
- Single‑line docstrings for simple functions.
- No trailing whitespace.
- End files with a single newline.

### Type Hints
- Use `typing.*` instead of bare types.
- Avoid `Any` unless necessary.

### Naming
- Modules: `snake_case`.
- Functions/Methods: `snake_case`.
- Classes: `PascalCase`.
- Constants: `UPPER_SNAKE_CASE`.
- Pydantic models: `CamelCase`.

### Error Handling
- Specific exceptions (`ValueError`, custom `SilcError`).
- Log with `logging.exception`.
- Do not swallow exceptions without retry.

### Logging
- Use `logging` module, default `INFO`.
- Configure a `StreamHandler` in `silc/__init__.py`.
- Avoid printing directly from library code.

## Development Workflow

1. Branch off `main`.
2. Keep PRs focused.
3. Run `pre-commit run --all-files` locally.
4. Run full test suite before pushing.
5. `git push --set-upstream origin <branch>`.

## Commit & Pull Request Guidelines

- Conventional Commits: `feat:`, `fix:`, `chore:`, `refactor:`.
- Subject < 72 chars.
- Body explains *why*.
- Attach test failures or screenshots if relevant.

## Pre‑commit Hooks

```bash
pre-commit install
```

## CI Configuration

The CI runs on GitHub Actions:
1. Checkout.
2. Python 3.11.
3. Install dependencies.
4. `pre-commit run --all-files`.
5. `pytest tests/`.

## Cursor Rules

No `.cursor` or `.cursorrules` files.

## Copilot Rules

No `.github/copilot‑instructions.md`.

## Useful Commands

```bash
# Compile all .py files
python -m compileall .

# Coverage report
pytest --cov=silc tests/

# Lint single file
flake8 silc/core/session.py
```

---

*This file is for internal use by automated agents and developers.  Keep it up‑to‑date as tooling or conventions change.*
