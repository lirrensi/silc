# SILC (Shared Interactive Linked CMD)

SILC bridges an interactive terminal session with an HTTP API so both humans and agents can read, write, and orchestrate commands in the same shell.

## Installation

### Using pipx (recommended)

```bash
pipx install git+https://github.com/username/repo-name.git
```

### Using pip

```bash
pip install -e .
```

### Using standalone installer (no pip required)

**Windows:**
```cmd
install.bat
```

**Unix/Linux/macOS:**
```bash
chmod +x install.sh
./install.sh
```

The standalone installer will:
- Build the executable if not present in `dist/`
- Copy it to `~/silc` (Windows: `%USERPROFILE%\silc`)
- Add it to your PATH automatically

## Getting started

1. `silc start` to launch a new session.
2. Use `silc <port> out`, `silc <port> run`, or `silc <port> status` from another terminal, or open the TUI with `silc <port> open`.

## Current implementation

- CLI scaffolding for all planned SILC commands.
- Simplified session, buffer, and output-cleaning helpers.
- FastAPI endpoints and a Textual TUI that can be wired into the server.
- Cross-platform PTY wiring: `pywinpty` on Windows and the standard `pty` module on Unix.

## Next steps

1. Harden `SilcSession.run_command` sentinel detection (time-outs, exit code reporting, queued runs).
2. Expand integration tests to cover the API endpoints, TUI refresh, and multiple concurrent clients.
3. Add buffering persistence/rotation and auth for exposed sockets before shipping a release.

## Testing

Run `pytest` (after installing the `test` extras) to exercise the shell lifecycle cycle tests that create a session, send input, clean the buffer, and stop it.
