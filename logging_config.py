"""
Logging Configuration - Persistent configuration for the operation logger.

Now reads from config/settings.json for unified configuration.
Provides backward compatibility functions for existing code.
"""

from operation_logger import LogConfig
from server_config import get_logging_config, update_logging_config as _update_logging_config


def load_config() -> LogConfig:
    """Load logging configuration from server config.

    This is the main entry point for getting logging configuration.
    Reads from config/settings.json logging section.
    """
    cfg = get_logging_config()
    return LogConfig(
        level=cfg.log_level,
        log_dir=cfg.log_dir,
        filename=cfg.log_filename,
        max_size_mb=cfg.max_file_size_mb,
        max_backup_files=cfg.max_backup_files,
        enabled=cfg.enabled,
    )


def save_config(config: LogConfig) -> None:
    """Save logging configuration to server config.

    Persists to config/settings.json logging section.
    """
    _update_logging_config({
        'enabled': config.enabled,
        'log_level': config.level,
        'log_dir': config.log_dir,
        'log_filename': config.filename,
        'max_file_size_mb': config.max_size_mb,
        'max_backup_files': config.max_backup_files,
    })
