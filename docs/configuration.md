# SILC Configuration

SILC can be configured through:
1. **Configuration file**: `silc.toml` in your SILC data directory
2. **Environment variables**: `SILC_*` prefixed variables
3. **Default values**: Built-in defaults

Configuration priority (highest to lowest):
1. Environment variables
2. Configuration file
3. Default values

## Configuration File Location

The configuration file is located at:
- **Linux/macOS**: `~/.silc/silc.toml`
- **Windows**: `%APPDATA%\silc\silc.toml`

You can copy the example configuration from `docs/silc.toml.example` to get started.

## Configuration Options

### Port Configuration (`[ports]`)

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `daemon_start` | int | 19999 | Starting port for daemon |
| `daemon_end` | int | 20000 | Ending port for daemon |
| `session_start` | int | 20000 | Starting port for sessions |
| `session_end` | int | 21000 | Ending port for sessions |
| `max_attempts` | int | 10 | Maximum ports to try when finding available port |

**Environment Variables:**
- `SILC_DAEMON_PORT_START`
- `SILC_DAEMON_PORT_END`
- `SILC_SESSION_PORT_START`
- `SILC_SESSION_PORT_END`
- `SILC_PORT_MAX_ATTEMPTS`

**Example:**
```toml
[ports]
session_start = 20000
session_end = 21000
max_attempts = 10
```

### Path Configuration (`[paths]`)

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `data_dir` | string | `~/.silc` or `%APPDATA%\silc` | Data directory for SILC |
| `log_dir` | string | `<data_dir>/logs` | Log directory |

**Environment Variables:**
- `SILC_DATA_DIR`
- `SILC_LOG_DIR`

**Example:**
```toml
[paths]
data_dir = "/custom/path/to/silc"
log_dir = "/custom/path/to/silc/logs"
```

### TLS Configuration (`[tls]`)

⚠️ **Warning**: TLS is currently experimental. Only enable if you have valid certificates.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | false | Enable TLS/SSL for daemon and sessions |
| `cert_path` | string | null | Path to TLS certificate file |
| `key_path` | string | null | Path to TLS private key file |

**Environment Variables:**
- `SILC_TLS_ENABLED` (1/true/yes/on to enable)
- `SILC_TLS_CERT_PATH`
- `SILC_TLS_KEY_PATH`

**Example:**
```toml
[tls]
enabled = true
cert_path = "/path/to/cert.pem"
key_path = "/path/to/key.pem"
```

### Token Configuration (`[tokens]`)

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `length` | int | 32 | Length of generated API tokens |
| `require_token` | bool | true | Require API token for non-localhost connections |

**Environment Variables:**
- `SILC_TOKEN_LENGTH`
- `SILC_REQUIRE_TOKEN` (1/true/yes/on to require)

**Example:**
```toml
[tokens]
length = 32
require_token = true
```

### Session Configuration (`[sessions]`)

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `default_timeout` | int | 600 | Default command timeout in seconds (10 minutes) |
| `max_buffer_bytes` | int | 5242880 | Maximum buffer size for command output (5MB) |
| `idle_timeout` | int | 1800 | Session idle timeout in seconds (30 minutes) |
| `gc_interval` | int | 60 | Garbage collection interval in seconds (1 minute) |

**Environment Variables:**
- `SILC_COMMAND_TIMEOUT`
- `SILC_MAX_BUFFER_BYTES`
- `SILC_IDLE_TIMEOUT`
- `SILC_GC_INTERVAL`

**Example:**
```toml
[sessions]
default_timeout = 600
max_buffer_bytes = 5242880
idle_timeout = 1800
gc_interval = 60
```

### Logging Configuration (`[logging]`)

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `max_log_lines` | int | 1000 | Maximum lines to keep in log files |
| `log_level` | string | INFO | Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |

**Environment Variables:**
- `SILC_MAX_LOG_LINES`
- `SILC_LOG_LEVEL`

**Example:**
```toml
[logging]
max_log_lines = 1000
log_level = "INFO"
```

## Common Configuration Scenarios

### Scenario 1: Custom Port Range

If you need to use a different port range (e.g., due to firewall restrictions):

```toml
[ports]
session_start = 30000
session_end = 31000
```

Or via environment variable:
```bash
export SILC_SESSION_PORT_START=30000
export SILC_SESSION_PORT_END=31000
```

### Scenario 2: Custom Data Directory

If you want to store SILC data in a different location:

```toml
[paths]
data_dir = "/mnt/storage/silc"
log_dir = "/mnt/storage/silc/logs"
```

Or via environment variable:
```bash
export SILC_DATA_DIR=/mnt/storage/silc
```

### Scenario 3: Longer Command Timeout

If you need to run commands that take longer than 10 minutes:

```toml
[sessions]
default_timeout = 3600  # 1 hour
```

Or via environment variable:
```bash
export SILC_COMMAND_TIMEOUT=3600
```

### Scenario 4: Larger Buffer Size

If you need to capture more output:

```toml
[sessions]
max_buffer_bytes = 10485760  # 10MB
```

Or via environment variable:
```bash
export SILC_MAX_BUFFER_BYTES=10485760
```

### Scenario 5: Debug Logging

If you need to troubleshoot issues:

```toml
[logging]
log_level = "DEBUG"
```

Or via environment variable:
```bash
export SILC_LOG_LEVEL=DEBUG
```

## Reloading Configuration

Configuration is loaded when SILC starts. To apply configuration changes:

1. Stop the daemon: `silc shutdown`
2. Make your configuration changes
3. Start the daemon: `silc start`

## Security Considerations

### TLS Configuration

⚠️ **Important**: When using `--global` flag to bind sessions to `0.0.0.0`:
- Tokens are sent over plaintext HTTP by default
- Only use on trusted home networks
- Never expose to the public internet without TLS

To enable TLS:
1. Obtain valid SSL/TLS certificates
2. Configure TLS in `silc.toml`:
   ```toml
   [tls]
   enabled = true
   cert_path = "/path/to/cert.pem"
   key_path = "/path/to/key.pem"
   ```
3. Restart SILC daemon

### Token Security

- Keep your API tokens secret
- Use strong, unique tokens
- Regularly rotate tokens
- Never share tokens over unencrypted channels

### File Permissions

Ensure your configuration file has appropriate permissions:
- Linux/macOS: `chmod 600 ~/.silc/silc.toml`
- Windows: Restrict access to your user account only

## Troubleshooting

### Configuration Not Applied

If configuration changes don't seem to take effect:

1. Verify the configuration file location:
   ```bash
   # Linux/macOS
   cat ~/.silc/silc.toml

   # Windows
   type %APPDATA%\silc\silc.toml
   ```

2. Check for syntax errors:
   ```bash
   python -c "import toml; toml.load(open('~/.silc/silc.toml'))"
   ```

3. Restart the daemon after making changes

### Port Conflicts

If you see "Port already in use" errors:

1. Check what's using the port:
   ```bash
   # Linux/macOS
   lsof -i :20000

   # Windows
   netstat -ano | findstr :20000
   ```

2. Adjust the port range in configuration:
   ```toml
   [ports]
   session_start = 21000
   session_end = 22000
   ```

### Permission Errors

If you see permission errors:

1. Ensure the data directory is writable:
   ```bash
   # Linux/macOS
   chmod 755 ~/.silc

   # Windows
   # Check folder permissions in File Explorer
   ```

2. Use a custom data directory if needed:
   ```bash
   export SILC_DATA_DIR=/tmp/silc
   ```

## Example Full Configuration

```toml
# SILC Configuration Example

[ports]
daemon_start = 19999
daemon_end = 20000
session_start = 20000
session_end = 21000
max_attempts = 10

[paths]
data_dir = "/home/user/.silc"
log_dir = "/home/user/.silc/logs"

[tls]
enabled = false
# cert_path = "/path/to/cert.pem"
# key_path = "/path/to/key.pem"

[tokens]
length = 32
require_token = true

[sessions]
default_timeout = 600
max_buffer_bytes = 5242880
idle_timeout = 1800
gc_interval = 60

[logging]
max_log_lines = 1000
log_level = "INFO"
```

## Additional Resources

- [README.md](../README.md) - Main documentation
- [commands_and_api.md](commands_and_api.md) - CLI and API reference
- [proposals.md](proposals.md) - Feature proposals and roadmap