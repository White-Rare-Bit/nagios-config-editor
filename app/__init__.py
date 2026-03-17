"""Nagios Bulk Editor - Flask Web Application

A web interface for bulk editing Nagios configuration files.
"""

import logging
import os
import warnings
from logging.handlers import RotatingFileHandler

from flask import Flask

from .backup_manager import BackupManager
from .config_discovery import discover_config_roots
from .git_service import GitService
from .nagios_service import NagiosService
from .server_config import ServerConfig
from .server_config import load_config as load_server_config
from .shadow_copy_manager import ShadowCopyManager

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

    # Configure stdlib logging
    _setup_logging(_server_config, log_dir_override)

    # Discover config roots from nagios.cfg (or use config_path override)
    if config_path:
        # Test/override mode: single directory, no discovery
        accessible_dirs = [os.path.abspath(config_path)]
        cfg_files = []
        discovery = {"directories": [], "cfg_files": [], "resource_file": ""}
    else:
        # Production mode: discover from nagios.cfg
        discovery = discover_config_roots(
            _server_config.paths.nagios_cfg,
            extra_cfg_dirs=_server_config.paths.extra_cfg_dirs,
        )
        accessible_dirs = [d["path"] for d in discovery["directories"] if d["accessible"]]
        cfg_files = discovery["cfg_files"]

        # Update resource_cfg from discovery
        if discovery["resource_file"]:
            _server_config.paths.resource_cfg = discovery["resource_file"]

    # Set primary_dir default
    if not _server_config.paths.primary_dir and accessible_dirs:
        _server_config.paths.primary_dir = accessible_dirs[0]

    # Primary dir for backward-compat services (backup, git)
    primary_dir = _server_config.paths.primary_dir or "./sample-config"
    backup_path = _server_config.backup_path

    # Initialize service instances with multi-root support
    service = NagiosService(cfg_dirs=accessible_dirs, cfg_files=cfg_files)
    backup_manager = BackupManager(primary_dir, backup_path)

    # Shadow copy manager with multi-root support
    shadow_path = _server_config.shadow_path
    if not shadow_path:
        shadow_path = os.path.join(os.path.dirname(os.path.abspath(primary_dir)), ".shadow")
    shadow_manager = ShadowCopyManager(cfg_dirs=accessible_dirs, shadow_base_path=shadow_path)
    # Clear stale shadow from previous server session
    if shadow_manager.has_shadow():
        logger.info("Clearing stale shadow copy from previous session")
        shadow_manager.destroy_shadow()

    # Initialize git service (uses primary dir)
    git_service = GitService(primary_dir)

    # Store in app.extensions for access via current_app
    app.extensions["service"] = service
    app.extensions["shadow"] = shadow_manager
    app.extensions["backup"] = backup_manager
    app.extensions["git"] = git_service
    app.extensions["server_config"] = _server_config
    app.extensions["discovery"] = discovery

    # Register blueprints only once
    if "blueprints_registered" not in app.extensions:
        from .routes import register_blueprints
        register_blueprints(app)
        app.extensions["blueprints_registered"] = True

    return app


def get_config_path() -> str:
    """Get current Nagios config path."""
    if _server_config:
        return _server_config.paths.primary_dir or "./sample-config"
    return "./sample-config"


# Initialize app services with default config
create_app()

