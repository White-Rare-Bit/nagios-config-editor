"""Nagios Bulk Editor - Flask Web Application

A web interface for bulk editing Nagios configuration files.
"""

import logging
import os
import warnings

from flask import Flask, current_app

import file_operations
from backup_manager import BackupManager
from git_service import GitService
from nagios_service import NagiosService
from operation_logger import LogConfig, OperationLogger
from server_config import ServerConfig
from server_config import load_config as load_server_config
from staging_manager import StagingManager

logger = logging.getLogger("nagios_bulk_editor")

# Server configuration - loaded from config/settings.json with env var overrides
_server_config: ServerConfig | None = None

# Create the Flask app instance (module-level for route decorators)
app = Flask(__name__)

# Secret key: use environment variable or generate random key at startup
_flask_secret_key = os.environ.get("FLASK_SECRET_KEY")
if _flask_secret_key:
    app.secret_key = _flask_secret_key
else:
    app.secret_key = os.urandom(24).hex()
    warnings.warn(
        "FLASK_SECRET_KEY not set - using randomly generated key. "
        "Sessions will not persist across restarts. "
        "Set FLASK_SECRET_KEY environment variable for production use.",
        UserWarning,
        stacklevel=2,
    )


def create_app(config_path: str | None = None) -> Flask:
    """Initialize or reinitialize Flask application services.

    This function initializes the module-level app's extensions with the given
    config path. It returns the module-level app instance to ensure routes
    are available.

    Args:
        config_path: Optional override for Nagios config path

    Returns:
        The module-level Flask application instance with reinitialized services

    """
    global _server_config

    # Load server configuration from config/settings.json (with env var overrides)
    _server_config = load_server_config()

    # Use provided config_path or fall back to server config
    nagios_config_path = config_path or _server_config.nagios_config_path
    if config_path:
        # Update server config if override provided
        _server_config.paths.nagios_config_path = os.path.abspath(config_path)
    backup_path = _server_config.backup_path

    # Initialize operation logger from server config
    log_cfg = _server_config.logging
    log_config = LogConfig(
        level=log_cfg.log_level,
        log_dir=log_cfg.log_dir,
        filename=log_cfg.log_filename,
        max_size_mb=log_cfg.max_file_size_mb,
        max_backup_files=log_cfg.max_backup_files,
        enabled=log_cfg.enabled,
    )
    op_logger = OperationLogger(log_config)

    # Initialize service instances with logger
    staging_manager = StagingManager(nagios_config_path, op_logger=op_logger)
    service = NagiosService(nagios_config_path, staging_manager, op_logger=op_logger)
    backup_manager = BackupManager(nagios_config_path, backup_path, op_logger=op_logger)
    file_operations.set_logger(op_logger)

    # Initialize git service
    git_service = GitService(nagios_config_path, op_logger=op_logger)

    # Store in app.extensions for access via current_app
    app.extensions["service"] = service
    app.extensions["staging"] = staging_manager
    app.extensions["backup"] = backup_manager
    app.extensions["op_logger"] = op_logger
    app.extensions["git"] = git_service
    app.extensions["server_config"] = _server_config

    # Register blueprints only once
    if "blueprints_registered" not in app.extensions:
        from routes import register_blueprints
        register_blueprints(app)
        app.extensions["blueprints_registered"] = True

    return app


def get_config_path() -> str:
    """Get current Nagios config path."""
    if _server_config:
        return _server_config.nagios_config_path
    return "./sample-config"


def get_server_config() -> ServerConfig | None:
    """Get the server configuration."""
    return _server_config


def get_service() -> NagiosService:
    """Get the NagiosService instance."""
    return current_app.extensions["service"]


def get_staging_manager() -> StagingManager:
    """Get the staging manager."""
    return current_app.extensions["staging"]


def get_op_logger() -> OperationLogger:
    """Get the operation logger."""
    return current_app.extensions.get("op_logger")


# Initialize app services with default config
create_app()


if __name__ == "__main__":
    print("Nagios Bulk Editor")  # noqa: T201
    print(f"Config path: {get_config_path()}")  # noqa: T201
    print("Starting server on http://localhost:8080")  # noqa: T201
    app.run(debug=True, host="127.0.0.1", port=8080)
