"""Server Configuration - Centralized configuration management.

Consolidates all server-wide settings into config/settings.json with
automatic persistence and environment variable overrides.
"""

import contextlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Config directory relative to project root
CONFIG_DIR = Path(__file__).parent / "config"
CONFIG_FILE = CONFIG_DIR / "settings.json"

# Current schema version for future migrations
CONFIG_VERSION = 1


@dataclass
class LoggingConfig:
    """Logging configuration settings."""

    enabled: bool = True
    log_level: str = "INFO"
    log_dir: str = "logs"
    log_filename: str = "operations.jsonl"
    max_file_size_mb: int = 10
    max_backup_files: int = 5


@dataclass
class PathsConfig:
    """Path configuration settings."""

    nagios_config_path: str = "./sample-config"
    backup_path: str | None = None
    nagios_bin: str = "/usr/local/nagios/bin/nagios"
    nagios_cfg: str = "./sample-config/nagios.cfg"
    resource_cfg: str = ""


@dataclass
class ServerConfig:
    """Complete server configuration."""

    version: int = CONFIG_VERSION
    paths: PathsConfig = field(default_factory=PathsConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "version": self.version,
            "paths": asdict(self.paths),
            "logging": asdict(self.logging),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ServerConfig":
        """Create from dictionary (loaded from JSON)."""
        paths_data = data.get("paths", {})
        logging_data = data.get("logging", {})

        return cls(
            version=data.get("version", CONFIG_VERSION),
            paths=PathsConfig(
                nagios_config_path=paths_data.get("nagios_config_path", "./sample-config"),
                backup_path=paths_data.get("backup_path"),
                nagios_bin=paths_data.get("nagios_bin", "/usr/local/nagios/bin/nagios"),
                nagios_cfg=paths_data.get("nagios_cfg", "./sample-config/nagios.cfg"),
                resource_cfg=paths_data.get("resource_cfg", ""),
            ),
            logging=LoggingConfig(
                enabled=logging_data.get("enabled", True),
                log_level=logging_data.get("log_level", "INFO"),
                log_dir=logging_data.get("log_dir", "logs"),
                log_filename=logging_data.get("log_filename", "operations.jsonl"),
                max_file_size_mb=logging_data.get("max_file_size_mb", 10),
                max_backup_files=logging_data.get("max_backup_files", 5),
            ),
        )

    # Convenience accessors for backward compatibility
    @property
    def nagios_config_path(self) -> str:
        return self.paths.nagios_config_path

    @nagios_config_path.setter
    def nagios_config_path(self, value: str):
        self.paths.nagios_config_path = value

    @property
    def backup_path(self) -> str | None:
        return self.paths.backup_path

    @backup_path.setter
    def backup_path(self, value: str | None):
        self.paths.backup_path = value

    @property
    def nagios_bin(self) -> str:
        return self.paths.nagios_bin

    @nagios_bin.setter
    def nagios_bin(self, value: str):
        self.paths.nagios_bin = value

    @property
    def nagios_cfg(self) -> str:
        return self.paths.nagios_cfg

    @nagios_cfg.setter
    def nagios_cfg(self, value: str):
        self.paths.nagios_cfg = value


def get_config_dir() -> Path:
    """Get the config directory path."""
    return CONFIG_DIR


def ensure_config_dir() -> None:
    """Create config directory if it doesn't exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _apply_env_overrides(config: ServerConfig) -> ServerConfig:
    """Apply environment variable overrides to config.

    Environment variables take precedence over file settings.
    """
    # Path overrides
    if env_val := os.environ.get("NAGIOS_CONFIG_PATH"):
        config.paths.nagios_config_path = os.path.abspath(env_val)
    else:
        # Normalize the path from config
        config.paths.nagios_config_path = os.path.abspath(config.paths.nagios_config_path)

    if env_val := os.environ.get("BACKUP_PATH"):
        config.paths.backup_path = env_val

    if env_val := os.environ.get("NAGIOS_BIN"):
        config.paths.nagios_bin = env_val

    if env_val := os.environ.get("NAGIOS_CFG"):
        config.paths.nagios_cfg = env_val

    return config


def load_config() -> ServerConfig:
    """Load server configuration from file with environment overrides.

    Order of precedence (highest to lowest):
    1. Environment variables
    2. config/settings.json
    3. Default values
    """
    ensure_config_dir()

    config = ServerConfig()

    # Load from config file if it exists
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            config = ServerConfig.from_dict(data)
        except (json.JSONDecodeError, OSError):
            pass  # Use defaults

    # Apply environment variable overrides
    config = _apply_env_overrides(config)

    # If no config file exists, create one with defaults
    if not CONFIG_FILE.exists():
        save_config(config)

    return config


def save_config(config: ServerConfig) -> None:
    """Save server configuration to file.

    Note: Environment variables still override file settings on next load.
    """
    ensure_config_dir()

    # Update version to current
    config.version = CONFIG_VERSION

    content = json.dumps(config.to_dict(), indent=2) + "\n"
    fd, tmp_path = tempfile.mkstemp(dir=str(CONFIG_DIR), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(CONFIG_FILE))
    except:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def _apply_paths_updates(config: ServerConfig, paths_dict: dict) -> None:
    """Apply path updates from a dictionary to config.paths.

    nagios_config_path is normalized to absolute path; others are set directly.

    Args:
        config: ServerConfig to update
        paths_dict: Dictionary of path field updates

    """
    if "nagios_config_path" in paths_dict:
        config.paths.nagios_config_path = os.path.abspath(paths_dict["nagios_config_path"])
    for key in ("backup_path", "nagios_bin", "nagios_cfg"):
        if key in paths_dict:
            setattr(config.paths, key, paths_dict[key])


def _apply_logging_updates(config: ServerConfig, logging_dict: dict) -> None:
    """Apply logging updates from a dictionary to config.logging.

    Args:
        config: ServerConfig to update
        logging_dict: Dictionary of logging field updates

    """
    for key in ("enabled", "log_level", "log_dir", "log_filename",
                "max_file_size_mb", "max_backup_files"):
        if key in logging_dict:
            setattr(config.logging, key, logging_dict[key])


def update_config(updates: dict) -> ServerConfig:
    """Load config, apply updates, save, and return updated config.

    Args:
        updates: Dictionary of updates. Supports nested keys like:
                 {'paths': {'nagios_config_path': '/new/path'}}
                 or flat keys for convenience:
                 {'nagios_config_path': '/new/path'}

    Returns:
        Updated ServerConfig

    """
    config = load_config()

    # Handle flat key updates (backward compatibility)
    _apply_paths_updates(config, updates)

    # Handle nested paths updates
    if "paths" in updates and isinstance(updates["paths"], dict):
        _apply_paths_updates(config, updates["paths"])

    # Handle logging updates
    if "logging" in updates and isinstance(updates["logging"], dict):
        _apply_logging_updates(config, updates["logging"])

    save_config(config)
    return config


def get_logging_config() -> LoggingConfig:
    """Get just the logging configuration section."""
    return load_config().logging


def update_logging_config(updates: dict) -> LoggingConfig:
    """Update just the logging configuration section."""
    config = update_config({"logging": updates})
    return config.logging
