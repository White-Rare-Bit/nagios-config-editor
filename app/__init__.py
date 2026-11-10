"""Nagios Bulk Editor - Flask Web Application

A web interface for bulk editing Nagios configuration files.
"""

import logging
import os
import warnings

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException
from flask_compress import Compress

from .backup_manager import BackupManager
from .config_discovery import discover_config_roots
from .git_service import GitService
from .logging_setup import apply_runtime_settings, log_error_responses, setup_logging
from . import server_config as _server_config_module
from .nagios_service import NagiosService
from .server_config import load_config as load_server_config
from .process_lock import ProcessLock
from .shadow_copy_manager import ShadowCopyManager

logger = logging.getLogger(__name__)


def _setup_logging(app, server_config, log_dir_override=None):
    """Install the app.log/audit.log handlers (see logging_setup)."""
    log_cfg = server_config.logging
    log_dir = log_dir_override or log_cfg.log_dir or "logs"
    setup_logging(log_cfg, log_dir)
    # Where the log viewer and settings page find the files
    app.extensions["log_dir"] = log_dir


def _settings_signature():
    """Identify the current contents of config/settings.json without reading it."""
    try:
        st = os.stat(_server_config_module.CONFIG_FILE)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def mark_settings_current(app):
    """Record that this app's services match config/settings.json as it is now."""
    app.extensions["settings_signature"] = _settings_signature()


def init_services(app, server_config):
    """Build the services for ``server_config`` and store them on ``app``.

    Used at startup, after a settings change, and when a worker notices that
    another worker saved new settings. All services are created before any is
    stored, so a failure leaves the previous set in place.
    """
    config_path = app.extensions.get("config_path_override")

    # Discover config roots from nagios.cfg (or use config_path override)
    if config_path:
        # Test/override mode: single directory, no discovery
        accessible_dirs = [os.path.abspath(config_path)]
        cfg_files = []
        discovery = {"directories": [], "cfg_files": [], "resource_file": ""}
    else:
        # Production mode: discover from nagios.cfg
        discovery = discover_config_roots(
            server_config.paths.nagios_cfg,
            extra_cfg_dirs=server_config.paths.extra_cfg_dirs,
        )
        accessible_dirs = [d["path"] for d in discovery["directories"] if d["accessible"]]
        cfg_files = discovery["cfg_files"]

        # Update resource_cfg from discovery
        if discovery["resource_file"]:
            server_config.paths.resource_cfg = discovery["resource_file"]

    # Logical paths are symlink-resolved everywhere (the parser resolves them),
    # so resolve the roots once here.
    accessible_dirs = [os.path.realpath(d) for d in accessible_dirs]

    # Set primary_dir default (always override in test/config_path mode)
    if config_path:
        server_config.paths.primary_dir = accessible_dirs[0]
    elif not server_config.paths.primary_dir and accessible_dirs:
        server_config.paths.primary_dir = accessible_dirs[0]

    # Primary dir: where Git lives and where backups go by default
    primary_dir = server_config.paths.primary_dir or "./sample-config"
    backup_path = server_config.backup_path

    # Shadow copy manager: owns all on-disk staging state for every root
    shadow_path = server_config.shadow_path
    if not shadow_path:
        shadow_path = os.path.join(os.path.dirname(os.path.abspath(primary_dir)), ".shadow")
    shadow_manager = ShadowCopyManager(cfg_dirs=accessible_dirs, shadow_base_path=shadow_path)
    # A shadow that matches these roots is a staging session in progress (this
    # may be one of several workers starting, or a restart) and is kept. Only
    # one made for a different set of roots is removed.
    shadow_manager.discard_if_stale()

    service = NagiosService(
        cfg_dirs=accessible_dirs, cfg_files=cfg_files, shadow_manager=shadow_manager,
    )
    backup_manager = BackupManager(
        primary_dir, backup_path, cfg_dirs=accessible_dirs or None,
    )
    git_service = GitService(primary_dir, lock_path=shadow_manager.lock_file("git"))

    # Store in app.extensions for access via current_app
    app.extensions["service"] = service
    app.extensions["shadow"] = shadow_manager
    app.extensions["backup"] = backup_manager
    app.extensions["git"] = git_service
    app.extensions["server_config"] = server_config
    app.extensions["discovery"] = discovery
    # Serialises whole mutation requests across workers (see routes/mutation.py)
    app.extensions["mutation_lock"] = ProcessLock(shadow_manager.lock_file("mutation"))
    mark_settings_current(app)


def _sync_settings_from_disk():
    """Apply settings another worker saved: rebuild services, re-apply logging.

    Settings changes are written to config/settings.json; that file is the
    only thing workers share, so each one checks it before serving a request
    (one stat(); the file is only re-read when it changed).
    """
    from flask import current_app

    app = current_app
    if _settings_signature() == app.extensions.get("settings_signature"):
        return
    try:
        fresh = load_server_config()
        # Level and rotation apply live; log_dir needs a restart.
        apply_runtime_settings(fresh.logging)
        init_services(app, fresh)
        logger.info("Settings changed on disk; services reinitialised")
    except Exception:
        # Keep serving with the previous services rather than fail every request.
        logger.exception("Failed to reinitialise services after settings change")
        mark_settings_current(app)


def _register_error_contract(app):
    """Give every API error the same JSON shape: {"success": false, "error": "..."}."""
    from .routes.mutation import ApiError

    @app.errorhandler(ApiError)
    def _api_error(e):
        return jsonify({"success": False, "error": e.message, **e.extra}), e.status

    @app.errorhandler(HTTPException)
    def _http_error(e):
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "error": e.description or e.name}), e.code
        return e

    @app.after_request
    def _uniform_error_body(response):
        if response.status_code < 400 or not response.is_json:  # noqa: PLR2004
            return response
        body = response.get_json(silent=True)
        if not isinstance(body, dict):
            return response
        if body.get("success") is False and isinstance(body.get("error"), str) and body["error"]:
            return response
        body["success"] = False
        if not isinstance(body.get("error"), str) or not body["error"]:
            body["error"] = f"Request failed ({response.status_code})"
        response.set_data(jsonify(body).get_data())
        return response


def create_app(config_path: str | None = None, log_dir_override: str | None = None) -> Flask:
    """Create a new, independent Flask application.

    Importing this package has no side effects; each call builds its own app
    with its own services. Several apps over the same config directory behave
    like several worker processes: they share only what is on disk.

    Args:
        config_path: Optional override for Nagios config path (single
            directory, no nagios.cfg discovery)
        log_dir_override: Optional override for log directory (used by tests)

    Returns:
        A new Flask application instance

    """
    app = Flask(__name__)
    Compress(app)

    # Secret key: use environment variable or generate random key at startup
    flask_secret_key = os.environ.get("FLASK_SECRET_KEY")
    if flask_secret_key:
        app.secret_key = flask_secret_key
    else:
        app.secret_key = os.urandom(24).hex()
        warnings.warn(
            "FLASK_SECRET_KEY not set - using randomly generated key. "
            "Sessions will not persist across restarts. "
            "Set FLASK_SECRET_KEY environment variable for production use.",
            UserWarning,
            stacklevel=2,
        )

    # Load server configuration from config/settings.json (with env var overrides)
    server_config = load_server_config()

    # Configure stdlib logging
    _setup_logging(app, server_config, log_dir_override)

    app.extensions["config_path_override"] = config_path
    init_services(app, server_config)

    from .routes import register_blueprints
    register_blueprints(app)
    _register_error_contract(app)
    # Record every 5xx in app.log (after_request hooks run last-registered
    # first; the message is read from "error", which every error body has).
    app.after_request(log_error_responses)
    app.before_request(_sync_settings_from_disk)

    return app
