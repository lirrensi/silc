# Architecture: Stream (File Output Streaming)

This document describes the file output streaming service. Complete enough to rewrite `silc/stream/` from scratch.

---

## Overview

The streaming service exports terminal output to files:

- **Render mode** — Overwrite file with current TUI state
- **Append mode** — Append new lines with deduplication

---

## Scope Boundary

**This component owns:**
- Streaming task management
- File output operations
- Line deduplication
- Streaming configuration

**This component does NOT own:**
- Session logic (see [arch_core.md](arch_core.md))
- API endpoints (see [arch_api.md](arch_api.md))
- CLI parsing (see [arch_cli.md](arch_cli.md))

**Boundary interfaces:**
- Receives: `SilcSession` instance
- Exposes: `StreamingService` class, CLI commands

---

## Dependencies

### External Packages

| Package | Purpose | Version |
|---------|---------|---------|
| `aiofiles` | Async file I/O | any |
| `pydantic` | Configuration models | any |

### Internal Modules

| Module | Purpose |
|--------|---------|
| `silc/core/session.py` | Session access |

---

## Data Models

### `StreamMode`

```python
class StreamMode(str, Enum):
    RENDER = "render"   # Overwrite file with current TUI state
    APPEND = "append"   # Append only new/changed lines
```

### `StreamConfig`

```python
class StreamConfig(BaseModel):
    mode: StreamMode
    filename: str
    interval: int = 5              # Refresh interval (seconds)
    window_size: int = 2000        # Deduplication window (lines)
    similarity_threshold: float = 0.85  # Fuzzy match threshold
    max_file_size_mb: int = 100    # Max file size before rotation
    rotation_policy: Literal["none", "size", "time"] = "size"
```

---

## StreamingService

### Methods

| Method | Description |
|--------|-------------|
| `start_stream(config)` | Start a new streaming task |
| `stop_stream(filename)` | Stop a streaming task |
| `get_stream_status()` | Get status of all streams |
| `stop_all_streams()` | Stop all streaming tasks |

### Implementation

```python
class StreamingService:
    def __init__(self, session: SilcSession):
        self.session = session
        self.active_streams: Dict[str, asyncio.Task] = {}
        self.deduplicator = LineDeduplicator()
    
    async def start_stream(self, config: StreamConfig) -> str:
        if config.filename in self.active_streams:
            raise ValueError(f"Stream already active for file: {config.filename}")
        
        self.deduplicator = LineDeduplicator(
            window_size=config.window_size,
            similarity_threshold=config.similarity_threshold,
        )
        
        if config.mode == StreamMode.RENDER:
            task = asyncio.create_task(self._stream_render_task(config))
        else:
            task = asyncio.create_task(self._stream_append_task(config))
        
        self.active_streams[config.filename] = task
        return config.filename
```

---

## Render Mode

Overwrites file with current rendered terminal state.

```python
async def _stream_render_task(self, config: StreamConfig):
    while True:
        try:
            # Get rendered output (same as TUI)
            output = self.session.get_rendered_output(lines=120)
            
            # Atomic write (temp file + rename)
            temp_file = f"{config.filename}.tmp"
            async with aiofiles.open(temp_file, "w") as f:
                await f.write(output)
            
            os.replace(temp_file, config.filename)
            
            await asyncio.sleep(config.interval)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Render stream error: {e}")
            await asyncio.sleep(config.interval)
```

---

## Append Mode

Appends new lines with deduplication.

```python
async def _stream_append_task(self, config: StreamConfig):
    while True:
        try:
            # Get current buffer lines
            buffer_content = self.session.buffer.get_last(config.window_size)
            new_lines = buffer_content.splitlines()
            
            # Read existing file tail
            existing_lines = await self._read_file_tail(
                config.filename, config.window_size
            )
            
            # Compute diff using deduplicator
            lines_to_append = self.deduplicator.compute_diff(
                existing_lines, new_lines
            )
            
            # Append if there are new lines
            if lines_to_append:
                async with aiofiles.open(config.filename, "a") as f:
                    await f.write("\n".join(lines_to_append) + "\n")
            
            await asyncio.sleep(config.interval)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Append stream error: {e}")
            await asyncio.sleep(config.interval)
```

---

## Line Deduplication

### `LineDeduplicator`

```python
class LineDeduplicator:
    def __init__(self, window_size: int = 2000, similarity_threshold: float = 0.85):
        self.window_size = window_size
        self.similarity_threshold = similarity_threshold
    
    def compute_diff(self, existing: list[str], new: list[str]) -> list[str]:
        # Compare new lines against existing
        # Return only lines that are new or significantly different
        pass
```

### Algorithm

1. Take last `window_size` lines from existing file
2. Compare against new lines using fuzzy matching
3. Return lines that don't match existing lines above threshold

---

## CLI Commands

### `silc <port> stream-render`

```python
@cli.port_subcommands.command()
@click.argument("filename")
@click.option("--interval", default=5)
def stream_file_render(ctx, filename, interval):
    config = StreamConfig(
        mode=StreamMode.RENDER,
        filename=filename,
        interval=interval,
    )
    # POST to /stream/start
```

### `silc <port> stream-append`

```python
@cli.port_subcommands.command()
@click.argument("filename")
@click.option("--interval", default=5)
def stream_file_append(ctx, filename, interval):
    config = StreamConfig(
        mode=StreamMode.APPEND,
        filename=filename,
        interval=interval,
    )
    # POST to /stream/start
```

### `silc <port> stream-stop`

```python
@cli.port_subcommands.command()
@click.argument("filename")
def stream_stop(ctx, filename):
    # POST to /stream/stop
```

### `silc <port> stream-status`

```python
@cli.port_subcommands.command()
def stream_status(ctx):
    # GET /stream/status
```

---

## API Endpoints

The streaming service exposes additional endpoints via `api_endpoints.py`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/stream/start` | Start streaming |
| `POST` | `/stream/stop` | Stop streaming |
| `GET` | `/stream/status` | Get streaming status |

---

## Contracts / Invariants

| Invariant | Description |
|-----------|-------------|
| Single stream per file | Only one stream per filename allowed |
| Atomic writes | Render mode uses temp file + rename |
| Bounded memory | Deduplication window limits memory usage |
| Graceful cancellation | Tasks are properly cancelled on stop |

---

## Design Decisions

| Decision | Why | Confidence |
|----------|-----|------------|
| Async file I/O | Non-blocking operation | High |
| Atomic writes | Prevent partial file reads | High |
| Fuzzy deduplication | Handle minor output variations | Medium |
| Per-session service | Isolation between sessions | High |

---

## Implementation Pointers

- **Repos/paths:** `silc/stream/`
- **Entry points:** `StreamingService(session)`
- **Key files:**
  - `streaming_service.py` — Service implementation
  - `config.py` — Configuration models
  - `deduplicator.py` — Line deduplication
  - `cli_commands.py` — CLI commands
  - `api_endpoints.py` — API endpoints

---

## Performance Considerations

| Aspect | Value | Notes |
|--------|-------|-------|
| Default interval | 5s | Balance between freshness and I/O |
| Window size | 2000 lines | Deduplication memory limit |
| Max file size | 100MB | Before rotation |
