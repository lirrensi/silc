"""Configuration management for SILC.

This module handles loading and accessing configuration from:
1. silc.toml file in the data directory
2. Environment variables (SILC_* prefix)
3. Default values

Environment variables override config file values, which override defaults.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import toml


@dataclass
class PortConfig:
    """Port range configuration."""

    daemon_start: int = 19999
    daemon_end: int = 20000
    session_start: int = 20000
    session_end: int = 21000
    max_attempts: int = 10


@dataclass
class PathConfig:
    """Directory path configuration."""

    data_dir: Path | None = None
    log_dir: Path | None = None


@dataclass
class TLSConfig:
    """TLS/SSL configuration."""

    enabled: bool = False
    cert_path: str | None = None
    key_path: str | None = None


@dataclass
class TokenConfig:
    """API token configuration."""

    length: int = 32
    require_token: bool = True


@dataclass
class SessionConfig:
    """Session behavior configuration."""

    default_timeout: int = 600  # 10 minutes
    max_buffer_bytes: int = 5 * 1024 * 1024  # 5MB
    idle_timeout: int = 1800  # 30 minutes
    gc_interval: int = 60  # 1 minute


@dataclass
class LoggingConfig:
    """Logging configuration."""

    max_log_lines: int = 1000
    log_level: str = "INFO"


@dataclass
class Config:
    """Main configuration container."""

    ports: PortConfig = field(default_factory=PortConfig)
    paths: PathConfig = field(default_factory=PathConfig)
    tls: TLSConfig = field(default_factory=TLSConfig)
    tokens: TokenConfig = field(default_factory=TokenConfig)
    sessions: SessionConfig = field(default_factory=SessionConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    def __post_init__(self) -> None:
        """Resolve paths after initialization."""
        if self.paths.data_dir is None:
            # Resolve data directory from environment or use default
            data_dir_str = os.environ.get("SILC_DATA_DIR")
            if data_dir_str:
                self.paths.data_dir = Path(data_dir_str)
            else:
                # Default: ~/.silc on Unix or %APPDATA%/silc on Windows
                if sys.platform == "win32":
                    self.paths.data_dir = Path(os.environ.get("APPDATA", "")) / "silc"
                else:
                    self.paths.data_dir = Path.home() / ".silc"
        if self.paths.log_dir is None:
            self.paths.log_dir = self.paths.data_dir / "logs"


def _get_env_int(key: str, default: int) -> int:
    """Get integer from environment variable."""
    value = os.environ.get(key)
    if value is not None:
        try:
            return int(value)
        except ValueError:
            pass
    return default


def _get_env_bool(key: str, default: bool) -> bool:
    """Get boolean from environment variable."""
    value = os.environ.get(key)
    if value is not None:
        return value.lower() in ("1", "true", "yes", "on")
    return default


def _get_env_str(key: str, default: str | None) -> str | None:
    """Get string from environment variable."""
    return os.environ.get(key, default)


def _get_env_path(key: str, default: Path | None) -> Path | None:
    """Get path from environment variable."""
    value = os.environ.get(key)
    if value:
        return Path(value)
    return default


def _load_config_file() -> dict[str, Any]:
    """Load configuration from silc.toml file."""
    # Resolve data directory directly (avoiding circular import)
    if sys.platform == "win32":
        data_dir = Path(os.environ.get("APPDATA", "")) / "silc"
    else:
        data_dir = Path.home() / ".silc"

    config_path = data_dir / "silc.toml"
    if not config_path.exists():
        return {}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return toml.load(f)
    except (OSError, toml.TomlDecodeError):
        return {}


def _apply_env_overrides(config: Config) -> Config:
    """Apply environment variable overrides to config."""
    # Port overrides
    config.ports.daemon_start = _get_env_int(
        "SILC_DAEMON_PORT_START", config.ports.daemon_start
    )
    config.ports.daemon_end = _get_env_int(
        "SILC_DAEMON_PORT_END", config.ports.daemon_end
    )
    config.ports.session_start = _get_env_int(
        "SILC_SESSION_PORT_START", config.ports.session_start
    )
    config.ports.session_end = _get_env_int(
        "SILC_SESSION_PORT_END", config.ports.session_end
    )
    config.ports.max_attempts = _get_env_int(
        "SILC_PORT_MAX_ATTEMPTS", config.ports.max_attempts
    )

    # Path overrides
    config.paths.data_dir = _get_env_path("SILC_DATA_DIR", config.paths.data_dir)
    config.paths.log_dir = _get_env_path("SILC_LOG_DIR", config.paths.log_dir)

    # TLS overrides
    config.tls.enabled = _get_env_bool("SILC_TLS_ENABLED", config.tls.enabled)
    config.tls.cert_path = _get_env_str("SILC_TLS_CERT_PATH", config.tls.cert_path)
    config.tls.key_path = _get_env_str("SILC_TLS_KEY_PATH", config.tls.key_path)

    # Token overrides
    config.tokens.length = _get_env_int("SILC_TOKEN_LENGTH", config.tokens.length)
    config.tokens.require_token = _get_env_bool(
        "SILC_REQUIRE_TOKEN", config.tokens.require_token
    )

    # Session overrides
    config.sessions.default_timeout = _get_env_int(
        "SILC_COMMAND_TIMEOUT", config.sessions.default_timeout
    )
    config.sessions.max_buffer_bytes = _get_env_int(
        "SILC_MAX_BUFFER_BYTES", config.sessions.max_buffer_bytes
    )
    config.sessions.idle_timeout = _get_env_int(
        "SILC_IDLE_TIMEOUT", config.sessions.idle_timeout
    )
    config.sessions.gc_interval = _get_env_int(
        "SILC_GC_INTERVAL", config.sessions.gc_interval
    )

    # Logging overrides
    config.logging.max_log_lines = _get_env_int(
        "SILC_MAX_LOG_LINES", config.logging.max_log_lines
    )
    config.logging.log_level = (
        _get_env_str("SILC_LOG_LEVEL", config.logging.log_level)
        or config.logging.log_level
    )

    return config


def _apply_file_config(config: Config, file_config: dict[str, Any]) -> Config:
    """Apply configuration from file to config object."""
    if "ports" in file_config:
        ports = file_config["ports"]
        config.ports.daemon_start = ports.get("daemon_start", config.ports.daemon_start)
        config.ports.daemon_end = ports.get("daemon_end", config.ports.daemon_end)
        config.ports.session_start = ports.get(
            "session_start", config.ports.session_start
        )
        config.ports.session_end = ports.get("session_end", config.ports.session_end)
        config.ports.max_attempts = ports.get("max_attempts", config.ports.max_attempts)

    if "paths" in file_config:
        paths = file_config["paths"]
        if "data_dir" in paths:
            config.paths.data_dir = Path(paths["data_dir"])
        if "log_dir" in paths:
            config.paths.log_dir = Path(paths["log_dir"])

    if "tls" in file_config:
        tls = file_config["tls"]
        config.tls.enabled = tls.get("enabled", config.tls.enabled)
        config.tls.cert_path = tls.get("cert_path", config.tls.cert_path)
        config.tls.key_path = tls.get("key_path", config.tls.key_path)

    if "tokens" in file_config:
        tokens = file_config["tokens"]
        config.tokens.length = tokens.get("length", config.tokens.length)
        config.tokens.require_token = tokens.get(
            "require_token", config.tokens.require_token
        )

    if "sessions" in file_config:
        sessions = file_config["sessions"]
        config.sessions.default_timeout = sessions.get(
            "default_timeout", config.sessions.default_timeout
        )
        config.sessions.max_buffer_bytes = sessions.get(
            "max_buffer_bytes", config.sessions.max_buffer_bytes
        )
        config.sessions.idle_timeout = sessions.get(
            "idle_timeout", config.sessions.idle_timeout
        )
        config.sessions.gc_interval = sessions.get(
            "gc_interval", config.sessions.gc_interval
        )

    if "logging" in file_config:
        logging = file_config["logging"]
        config.logging.max_log_lines = logging.get(
            "max_log_lines", config.logging.max_log_lines
        )
        config.logging.log_level = logging.get("log_level", config.logging.log_level)

    return config


def load_config() -> Config:
    """Load configuration from defaults, file, and environment.

    Priority (highest to lowest):
    1. Environment variables (SILC_*)
    2. silc.toml file
    3. Default values

    Returns:
        Config: The loaded configuration object
    """
    config = Config()

    # Apply file config
    file_config = _load_config_file()
    if file_config:
        config = _apply_file_config(config, file_config)

    # Apply environment overrides (highest priority)
    config = _apply_env_overrides(config)

    return config


# Global config instance
_config: Config | None = None


def get_config() -> Config:
    """Get the global configuration instance.

    Returns:
        Config: The configuration object
    """
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config() -> Config:
    """Reload configuration from file and environment.

    Returns:
        Config: The reloaded configuration object
    """
    global _config
    _config = load_config()
    return _config


__all__ = [
    "Config",
    "PortConfig",
    "PathConfig",
    "TLSConfig",
    "TokenConfig",
    "SessionConfig",
    "LoggingConfig",
    "load_config",
    "get_config",
    "reload_config",
]
