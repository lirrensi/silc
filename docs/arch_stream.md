# Architecture: Stream

This document describes `silc/stream/`.

## Overview

The stream subsystem writes session output to files in two modes:

- **render** — overwrite the file with the current rendered terminal state
- **append** — append only novel lines using deduplication

## Scope Boundary

Owns:

- file streaming tasks
- deduplication logic
- stream REST endpoints
- stream CLI commands

Does not own:

- session behavior (`silc/core/`)
- daemon behavior (`silc/daemon/`)
- general CLI parsing (`silc/__main__.py`)

## Key Modules

| Module | Role |
|---|---|
| `silc/stream/config.py` | `StreamConfig` and `StreamMode` |
| `silc/stream/streaming_service.py` | Background file streaming tasks |
| `silc/stream/deduplicator.py` | Exact + fuzzy line deduplication |
| `silc/stream/api_endpoints.py` | `/stream/*` routes |
| `silc/stream/cli_commands.py` | CLI entry points |

## Data Models

### `StreamMode`

```python
class StreamMode(str, Enum):
    RENDER = "render"
    APPEND = "append"
```

### `StreamConfig`

```python
class StreamConfig(BaseModel):
    mode: StreamMode
    filename: str
    interval: int = 5
    window_size: int = 2000
    similarity_threshold: float = 0.85
    max_file_size_mb: int = 100
    rotation_policy: Literal["none", "size", "time"] = "size"
```

Current behavior uses `mode`, `filename`, `interval`, `window_size`, and `similarity_threshold`. Rotation fields are accepted but not enforced by the service.

## StreamingService

State:

```python
session
active_streams: dict[str, asyncio.Task]
deduplicator: LineDeduplicator
```

Methods:

- `start_stream(config)` — start a task
- `stop_stream(filename)` — cancel a task
- `get_stream_status()` — report task state
- `stop_all_streams()` — stop every task

## Render Mode

- Overwrites the target file using `session.get_rendered_output()`.
- Writes through a temp file and `os.replace()` for atomicity.
- Sleeps for `config.interval` between writes.

Current limitation: the CLI accepts `--lines`, but the render task currently uses a fixed internal line depth of `120`.

## Append Mode

- Reads the session buffer tail and the file tail.
- Uses `LineDeduplicator.compute_diff()` to remove duplicates.
- Appends only novel lines.

## Deduplication

`LineDeduplicator` uses two stages:

1. exact matching on normalized lines
2. fuzzy matching with `difflib.SequenceMatcher`

Normalization strips ANSI color codes, collapses whitespace, and lowercases text.

## REST API

Mounted at `/stream` on the session API.

- `POST /stream/start` — start a stream from `StreamConfig`
- `POST /stream/stop` — stop by filename
- `GET /stream/status` — report active streams

`/stream/start` returns `{"status":"started","filename":...,"mode":...}`.

## CLI Commands

The current command names are:

- `silc <port|name> stream-file-render`
- `silc <port|name> stream-file-append`
- `silc <port|name> stream-stop`
- `silc <port|name> stream-status`

### `stream-file-render`

- default filename: `silc_<port>.txt`
- options: `--name`, `--sec`, `--lines`

### `stream-file-append`

- default filename: `silc_<port>_append.txt`
- options: `--name`, `--sec`, `--window`, `--threshold`

### Auth

- The CLI tries `GET /token` and sends `Authorization: Bearer <token>` when a token exists.

## Error Handling

- Duplicate filenames return `400`.
- Missing streams return `404` from the API / a friendly CLI error.
- Connection and timeout failures are reported to the user.
