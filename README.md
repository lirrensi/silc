# SILC (Shared Interactive Linked CMD)

# ⚠️ work in progress...

SILC bridges an interactive terminal session with an HTTP API so both humans and agents can read, write, and orchestrate commands in the same shell.

## Requirements

- **Python >= 3.12** (required)
- Windows, Linux, or macOS

## Installation

### Using pipx (recommended)

```bash
pipx install git+https://github.com/lirrensi/silc.git
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

### Quick Start (5 minutes)

1. **Install SILC:**
   ```bash
   pip install -e .
   ```

2. **Start the daemon:**
   ```bash
   silc start
   ```

3. **Create a session:**
   ```bash
   # Session will be created on an available port (20000-21000)
   silc create
   ```

4. **Run commands:**
   ```bash
   # Replace 20000 with your actual session port
   silc 20000 run "echo hello world"
   silc 20000 run "ls -la"
   silc 20000 run "pwd"
   ```

5. **View output:**
   ```bash
   silc 20000 out
   ```

6. **Check session status:**
   ```bash
   silc 20000 status
   ```

7. **List all sessions:**
   ```bash
   silc list
   ```

8. **Stop the daemon:**
   ```bash
   silc shutdown
   ```

### Common Commands

- `silc start` - Start the SILC daemon
- `silc create` - Create a new session (auto-assigns port)
- `silc create --port 20000` - Create session on specific port
- `silc <port> run "<command>"` - Run a command in the session
- `silc <port> out` - View session output
- `silc <port> status` - Check session status
- `silc <port> clear` - Clear session buffer
- `silc list` - List all active sessions
- `silc shutdown` - Gracefully stop the daemon
- `silc killall` - Force kill all sessions and daemon

## Configuration

SILC can be configured through a `silc.toml` file or environment variables.

### Configuration File

Create a configuration file at:
- **Linux/macOS**: `~/.silc/silc.toml`
- **Windows**: `%APPDATA%\silc\silc.toml`

Copy the example configuration:
```bash
# Linux/macOS
cp docs/silc.toml.example ~/.silc/silc.toml

# Windows
copy docs\silc.toml.example %APPDATA%\silc\silc.toml
```

### Common Configuration Options

```toml
[ports]
session_start = 20000
session_end = 21000

[sessions]
default_timeout = 600  # 10 minutes
max_buffer_bytes = 5242880  # 5MB

[logging]
log_level = "INFO"
```

### Environment Variables

You can also configure SILC using environment variables:

```bash
# Custom port range
export SILC_SESSION_PORT_START=20000
export SILC_SESSION_PORT_END=21000

# Custom data directory
export SILC_DATA_DIR=/custom/path/to/silc

# Command timeout (seconds)
export SILC_COMMAND_TIMEOUT=600

# Log level
export SILC_LOG_LEVEL=INFO
```

For complete configuration documentation, see [docs/configuration.md](docs/configuration.md).

## Docker mode: API-first shell access

Run SILC in Docker for a sandboxed shell with HTTP API access. This is useful when you want:

- A clean, isolated shell environment
- Easy HTTP API without managing host processes
- Consistent environment across different machines
- Ability to give agents a disposable workspace

```bash
# Build and start the SILC daemon in Docker
docker-compose up -d

# Access sessions via HTTP
curl http://localhost:19999/sessions
curl http://localhost:20000/status
curl http://localhost:20000/out

# Or use the CLI from outside the container
silc 20000 out
silc 20000 run "ls -la"
```

**Note**: In Docker mode, the shell runs inside the container. You won't have access to your host files or environment. This is intentional for isolation and sandboxing.

## Current implementation

- CLI scaffolding for all planned SILC commands.
- Simplified session, buffer, and output-cleaning helpers.
- FastAPI endpoints and a Textual TUI that can be wired into the server.
- Cross-platform PTY wiring: `pywinpty` on Windows and the standard `pty` module on Unix.

## Next steps

1. Harden `SilcSession.run_command` sentinel detection (time-outs, exit code reporting, queued runs).
2. Expand integration tests to cover the API endpoints, TUI refresh, and multiple concurrent clients.
3. Add buffering persistence/rotation and auth for exposed sockets before shipping a release.

## TUI Binary

SILC includes a native TUI component built with Rust. The installer will automatically download the appropriate binary for your platform.

### Building the TUI Binary Locally

If you want to build the TUI binary yourself, navigate to the `tui_client` directory:

```bash
cd tui_client

# Build for your platform
cargo build --release

# The binary will be in target/release/
```

### Building Release Artifacts

The repository includes a GitHub Actions workflow that automatically builds and releases TUI binaries for multiple platforms.

**To trigger a release:**

1. **Create a git tag:**
   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```

2. **Or manually trigger via GitHub:**
   - Go to Actions → "Build and Release TUI Binary"
   - Click "Run workflow"
   - Optionally mark as draft or pre-release

**What gets built:**

- **Linux**: `x86_64` and `aarch64` (ARM64)
- **macOS**: `x86_64` (Intel) and `aarch64` (Apple Silicon)
- **Windows**: `x86_64` (MSVC)

Each build produces a compressed archive:
- Linux: `.tar.gz`
- macOS: `.tar.gz`
- Windows: `.zip`

### Binary Distribution

The installer automatically:
1. Checks for a cached binary in the user's cache directory
2. If not found, fetches the latest release from GitHub
3. Downloads the appropriate asset for your platform
4. Extracts and installs the binary

**Cache location:**
- **Linux/macOS**: `~/.cache/silc/bin/`
- **Windows**: `%LOCALAPPDATA%\Cache\silc\bin\`

### Environment Variables

You can customize the binary distribution behavior:

```bash
# Custom binary installation directory
export SILC_TUI_BIN_DIR=/custom/path/to/bin

# Custom release repository
export SILC_TUI_RELEASE_REPO=lirrensi/silc

# Custom release API endpoint
export SILC_TUI_RELEASE_API=https://api.github.com/repos/lirrensi/silc/releases/latest
```

## Testing

Run `pytest` (after installing the `test` extras) to exercise the shell lifecycle cycle tests that create a session, send input, clean the buffer, and stop it.

## Troubleshooting

### Port already in use

If you see "Port already in use" errors:

```bash
# Check what's running on the port
# Linux/macOS:
lsof -i :19999  # daemon port
lsof -i :20000  # session port

# Windows:
netstat -ano | findstr :19999
netstat -ano | findstr :20000

# Kill the process if needed (replace PID with actual process ID)
# Linux/macOS:
kill -9 <PID>

# Windows:
taskkill /PID <PID> /F
```

### Daemon not starting

If the daemon fails to start:

1. Check if a daemon is already running:
   ```bash
   silc list
   ```

2. If it's running but unresponsive, force kill it:
   ```bash
   silc killall
   ```

3. Check the daemon log:
   ```bash
   # Linux/macOS:
   cat ~/.silc/logs/daemon.log

   # Windows:
   type %USERPROFILE%\.silc\logs\daemon.log
   ```

### Session not responding

If a session hangs or doesn't respond:

1. Check session status:
   ```bash
   silc <port> status
   ```

2. If it shows as busy, another command may be running. Wait or interrupt:
   ```bash
   silc <port> interrupt
   ```

3. If still unresponsive, close the session:
   ```bash
   silc close <port>
   ```

### Installation issues

If you encounter import errors:

1. Ensure you're using Python 3.12 or later:
   ```bash
   python --version
   ```

2. Reinstall with test dependencies:
   ```bash
   pip install -e .[test]
   ```

3. Verify all dependencies are installed:
   ```bash
   pip list | grep silc
   ```

## Security Considerations

⚠️ **Important Security Notes:**

### Real Shell Access
SILC provides **real shell access** to your system. This means:
- Commands run with your user permissions
- You can delete files, modify system settings, etc.
- **Never run untrusted commands** in SILC sessions
- Be cautious when sharing session access with agents or others

### Global Sessions (--global flag)
When using the `--global` flag to bind sessions to `0.0.0.0`:
- **Tokens are sent over plaintext HTTP** (not encrypted)
- Anyone on your network can intercept tokens
- **Only use on trusted home networks**
- **Never expose to the public internet**
- Consider using a VPN or reverse proxy with TLS for remote access

### Best Practices
1. **Never expose SILC to the public internet** without proper authentication and TLS
2. Use strong, unique API tokens
3. Regularly review session logs for suspicious activity
4. Close sessions when not in use
5. Keep SILC updated to the latest version
6. Use firewall rules to restrict access to SILC ports

### Recommended Setup for Remote Access
If you need remote access:
1. Use SSH tunneling instead of `--global`:
   ```bash
   ssh -L 19999:localhost:19999 user@remote-host
   ```
2. Or set up a reverse proxy with TLS (nginx, traefik, etc.)
3. Use VPN for secure network access
