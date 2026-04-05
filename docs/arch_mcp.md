# Architecture: MCP Server

This document describes `silc/mcp/`.

## Overview

The MCP server exposes SILC to AI agents over stdio JSON-RPC.

It provides:

- universal send/read tools
- special key injection
- session lifecycle helpers
- status and resize helpers
- a command runner for native shells

## Scope Boundary

Owns:

- MCP protocol wiring
- tool definitions and handlers
- stdio transport lifecycle

Does not own:

- daemon lifecycle (`silc/daemon/`)
- per-session HTTP behavior (`silc/api/server.py`)
- PTY behavior (`silc/core/`)

## Tools

### `send(port, text, timeout_ms=5000)`

- posts `text + "\n"` to `/in`
- waits `timeout_ms`
- reads `/out`
- `timeout_ms=0` is fire-and-forget

### `read(port, lines=100)`

- reads `/out`
- marked read-only

### `send_key(port, key)`

- maps keys like `ctrl+c`, `enter`, arrows, etc. to byte sequences
- posts them to `/in`

### `list_sessions()`

- reads the daemon session list
- marked read-only

### `start_session(port?, shell?, cwd?)`

- posts to `POST /sessions`
- defaults `cwd` to the MCP process working directory
- defaults shell detection to the daemon side

### `close_session(port)`

- current code still issues `DELETE /sessions/{port}`; the daemon close route is `POST /sessions/{port}/close`, so this is a known compatibility gap

### `get_status(port)`

- reads `/status`
- marked read-only

### `resize(port, rows=30, cols=120)`

- posts to `/resize?rows=&cols=`

### `run(port, command, timeout_ms=60000)`

- posts JSON `{"command": ..., "timeout": ...}` to `/run`
- only reliable in native shells where the helper wrapper is injected

## Response Shapes

- `send` and `read` return JSON text with `output`, `lines`, and `alive` where relevant.
- `run` returns the session API response, including `completed`, `timeout`, `busy`, or `error`.

## Key Mappings

Supported keys include:

- `ctrl+c`, `ctrl+d`, `ctrl+z`, `ctrl+l`, `ctrl+r`
- `enter`, `escape`, `tab`, `backspace`, `delete`
- `up`, `down`, `left`, `right`, `home`, `end`

## Error Handling

- Transport errors return a structured JSON error payload.
- Missing sessions are reported as not found or ended.
- Unsupported keys return an explicit key list.

## Design Notes

- `send` is the universal, agent-friendly tool.
- `run` is convenience-only and depends on shell helpers.
- `read`, `list_sessions`, and `get_status` are safe to auto-approve.
