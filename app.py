"""Nagios Bulk Editor - Flask Web Application

A web interface for bulk editing Nagios configuration files.
"""

import logging
import os
import warnings
from logging.handlers import RotatingFileHandler

from flask import Flask, current_app

from backup_manager import BackupManager
from git_service import GitService
from nagios_service import NagiosService
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


def _setup_logging(server_config, log_dir_override=None):
    """Configure stdlib logging with file handlers for app and audit logs."""
    log_cfg = server_config.logging
    log_dir = log_dir_override or log_cfg.log_dir or "logs"
    os.makedirs(log_dir, exist_ok=True)

    max_bytes = int((log_cfg.max_file_size_mb or 10) * 1024 * 1024)
    backup_count = log_cfg.max_backup_files or 5
    level = getattr(logging, (log_cfg.log_level or "INFO").upper(), logging.INFO)

    # App log — syslog-style format
    app_handler = RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=max_bytes, backupCount=backup_count,
    )
    app_formatter = logging.Formatter(
        fmt="%(asctime)s nagios-editor [%(levelname)s] %(name)s: %(message)s",
        datefmt="%b %d %H:%M:%S",
    )
    app_handler.setFormatter(app_formatter)
    app_handler.setLevel(level)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(app_handler)

    # Audit log — minimal format (timestamp + raw message)
    audit_handler = RotatingFileHandler(
        os.path.join(log_dir, "audit.log"),
        maxBytes=max_bytes, backupCount=backup_count,
    )
    audit_formatter = logging.Formatter(
        fmt="%(asctime)s %(message)s",
        datefmt="%b %d %H:%M:%S",
    )
    audit_handler.setFormatter(audit_formatter)
    audit_handler.setLevel(logging.INFO)

    audit_logger = logging.getLogger("audit")
    audit_logger.addHandler(audit_handler)
    audit_logger.propagate = False  # Don't duplicate audit lines into app.log

    # Suppress werkzeug request logs from app.log (floods with GET /api/... lines)
    logging.getLogger("werkzeug").propagate = False

    # Store config for settings page and log viewer
    app.extensions["log_dir"] = log_dir
    app.extensions["log_config"] = {
        "level": log_cfg.log_level or "INFO",
        "max_size_mb": log_cfg.max_file_size_mb or 10,
        "backup_count": log_cfg.max_backup_files or 5,
    }


def create_app(config_path: str | None = None, log_dir_override: str | None = None) -> Flask:
    """Initialize or reinitialize Flask application services.

    This function initializes the module-level app's extensions with the given
    config path. It returns the module-level app instance to ensure routes
    are available.

    Args:
        config_path: Optional override for Nagios config path
        log_dir_override: Optional override for log directory (used by tests)

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

    # Configure stdlib logging
    _setup_logging(_server_config, log_dir_override)

    # Initialize service instances
    staging_manager = StagingManager(nagios_config_path)
    # Clear stale locks from previous server session — no active sessions at startup
    if staging_manager.has_staging():
        logger.info("Clearing stale staging lock from previous session")
        staging_manager.clear_staging()
    service = NagiosService(nagios_config_path, staging_manager)
    backup_manager = BackupManager(nagios_config_path, backup_path)

    # Initialize git service
    git_service = GitService(nagios_config_path)

    # Store in app.extensions for access via current_app
    app.extensions["service"] = service
    app.extensions["staging"] = staging_manager
    app.extensions["backup"] = backup_manager
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



# Initialize app services with default config
create_app()


if __name__ == "__main__":
    print("Nagios Bulk Editor")  # noqa: T201
    print(f"Config path: {get_config_path()}")  # noqa: T201
    print("Starting server on http://localhost:8080")  # noqa: T201
    app.run(debug=True, host="127.0.0.1", port=8080)
