"""Settings and logging management routes."""

import json
import logging
import os

from flask import Blueprint, current_app, jsonify, request

from ..audit_service import log_audit
from ..logging_setup import LOG_LEVELS, apply_runtime_settings
from ..server_config import save_config as save_server_config
from ..validator import verify_nagios_binary

from .helpers import (
    format_audit_user,
    get_audit_user_identity,
    get_server_config,
)

bp = Blueprint("settings", __name__)
logger = logging.getLogger(__name__)


@bp.route("/api/settings", methods=["GET"])
def api_get_settings():
    """Get current settings including discovered config roots."""
    server_config = get_server_config()
    if not server_config:
        return jsonify({})

    discovery = current_app.extensions.get("discovery", {})

    return jsonify({
        "paths": {
            "nagios_cfg": server_config.paths.nagios_cfg,
            "nagios_bin": server_config.paths.nagios_bin,
            "backup_path": server_config.paths.backup_path,
            "shadow_path": server_config.paths.shadow_path,
            "resource_cfg": server_config.paths.resource_cfg,
            "extra_cfg_dirs": server_config.paths.extra_cfg_dirs,
            "primary_dir": server_config.paths.primary_dir,
        },
        "discovered": {
            "cfg_dirs": discovery.get("directories", []),
            "resource_file": discovery.get("resource_file", ""),
        },
    })


@bp.route("/api/settings", methods=["POST"])
def api_update_settings():
    """Update settings and persist to config/settings.json.

    Accepts nested paths dict: {"paths": {"nagios_cfg": "...", ...}}
    or flat keys for backward compat: {"backup_path": "...", ...}
    """
    server_config = get_server_config()
    if not server_config:
        return jsonify({"error": "Server config not initialized"}), 500

    data = request.get_json() or {}
    # Support both nested {"paths": {...}} and flat keys
    paths_data = data.get("paths", {})
    # Merge flat keys into paths_data for backward compat
    for key in ("backup_path", "nagios_bin", "nagios_cfg", "extra_cfg_dirs", "primary_dir"):
        if key in data and key not in paths_data:
            paths_data[key] = data[key]

    updated = []
    errors = []
    warnings = []  # Non-blocking validation issues (e.g. missing nagios binary)

    if "backup_path" in paths_data:
        _update_backup_path(server_config, paths_data["backup_path"], updated, errors)
    if "nagios_bin" in paths_data:
        _update_nagios_bin(server_config, paths_data["nagios_bin"], updated, warnings)

    # Simple field updates
    needs_rediscovery = False
    if "nagios_cfg" in paths_data:
        server_config.paths.nagios_cfg = paths_data["nagios_cfg"]
        updated.append("nagios_cfg")
        needs_rediscovery = True
    if "extra_cfg_dirs" in paths_data:
        server_config.paths.extra_cfg_dirs = list(paths_data["extra_cfg_dirs"])
        updated.append("extra_cfg_dirs")
        needs_rediscovery = True
    if "primary_dir" in paths_data:
        server_config.paths.primary_dir = paths_data["primary_dir"]
        updated.append("primary_dir")

    # Re-run discovery and reinitialize services if nagios_cfg or extra_dirs changed
    git_initialized = False
    if needs_rediscovery and not errors:
        _rediscover_and_reinit(server_config, errors)
        # Auto-init git repo in config directory if none exists
        if not errors:
            git_svc = current_app.extensions.get("git")
            if git_svc:
                git_dir = os.path.join(git_svc._config_path, ".git")
                if not os.path.isdir(git_dir):
                    init_result = git_svc.init_repo()
                    if init_result.success:
                        git_initialized = True
                    else:
                        logger.warning("Auto git init failed: %s", init_result.error)

    if updated and not errors:
        try:
            save_server_config(server_config)
            # This worker already runs the new settings; other workers see
            # the file change and reinitialise themselves.
            from .. import mark_settings_current
            mark_settings_current(current_app)
        except (OSError, ValueError) as e:
            logger.error("Failed to save settings: %s", e)
            errors.append(f"Failed to save config: {e}")
        else:
            log_audit(action="settings_update", user=format_audit_user(get_audit_user_identity()),
                      section="paths", changed=",".join(updated),
                      **{k: getattr(server_config.paths, k) for k in updated
                         if hasattr(server_config.paths, k)})

    discovery = current_app.extensions.get("discovery", {})

    return jsonify({
        "success": len(errors) == 0,
        "updated": updated,
        "errors": errors,
        "warnings": warnings,
        "git_initialized": git_initialized,
        "config": {
            "paths": {
                "nagios_cfg": server_config.paths.nagios_cfg,
                "nagios_bin": server_config.paths.nagios_bin,
                "backup_path": server_config.paths.backup_path,
                "extra_cfg_dirs": server_config.paths.extra_cfg_dirs,
                "primary_dir": server_config.paths.primary_dir,
            },
            "discovered": {
                "cfg_dirs": discovery.get("directories", []),
                "resource_file": discovery.get("resource_file", ""),
            },
        },
    })


def _rediscover_and_reinit(server_config, errors):
    """Re-run config discovery and reinitialize services.

    Called when nagios_cfg or extra_cfg_dirs changes. init_services creates
    all services BEFORE updating app.extensions to prevent inconsistent state.
    Other workers do the same when they see the saved settings file change.
    """
    from .. import init_services

    try:
        init_services(current_app, server_config)
        _ = current_app.extensions["service"].parser  # Force init to catch config errors early
    except Exception as e:  # noqa: BLE001
        logger.exception("Failed to reinitialize services after settings change")
        errors.append(f"Failed to reinitialize services: {e}")


def _update_backup_path(server_config, path, updated, errors):
    """Update the backup directory path. Creates directory if needed."""
    if path and not os.path.isdir(path):
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as e:
            logger.warning("Cannot create backup directory %s: %s", path, e)
            errors.append(f"Cannot create backup directory: {e}")
            return

    server_config.paths.backup_path = path or None

    from ..backup_manager import BackupManager
    primary_dir = server_config.paths.primary_dir or "./sample-config"
    backup_manager = BackupManager(
        primary_dir, server_config.backup_path,
        cfg_dirs=current_app.extensions["service"].cfg_dirs or None,
    )
    current_app.extensions["backup"] = backup_manager
    updated.append("backup_path")


def _update_nagios_bin(server_config, path, updated, errors):
    """Update the Nagios binary path with security verification."""
    if path:
        result = verify_nagios_binary(path)
        if result.success:
            server_config.paths.nagios_bin = path
            updated.append("nagios_bin")
        else:
            errors.append(f"Invalid Nagios binary: {result.error}")
    else:
        # Allow clearing the path
        server_config.paths.nagios_bin = path
        updated.append("nagios_bin")


@bp.route("/api/settings/browse", methods=["POST"])
def api_browse_directory():
    """List contents of a directory for browsing."""
    data = request.get_json() or {}
    path = data.get("path", "/")

    if not os.path.isabs(path):
        path = os.path.abspath(path)

    path = os.path.normpath(path)

    # D-06: Path traversal prevention for directory browser
    # Unlike file operations (which are confined to config_path via is_safe_path()),
    # this browse endpoint intentionally allows browsing the full filesystem for
    # initial setup. The '..' check prevents URL-encoded traversal attacks like
    # "/../../../etc/passwd" from reaching directories via normpath manipulation.
    # This is a defense-in-depth measure since normpath already resolves '..'
    # but could be bypassed with certain edge cases on some platforms.
    if ".." in path.split(os.sep):
        return jsonify({"error": "Invalid path"}), 400

    if not os.path.isdir(path):
        return jsonify({"error": "Not a valid directory"}), 400

    try:
        entries = []
        for entry in os.scandir(path):
            try:
                entries.append({
                    "name": entry.name,
                    "path": entry.path,
                    "is_dir": entry.is_dir(),
                    "is_file": entry.is_file(),
                })
            except PermissionError:
                continue

        entries.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))

        return jsonify({
            "path": path,
            "parent": os.path.dirname(path) if path != "/" else None,
            "entries": entries,
        })
    except PermissionError:
        return jsonify({"error": "Permission denied"}), 403


def _logging_settings_response(log_cfg):
    app_log = os.path.join(current_app.extensions.get("log_dir", log_cfg.log_dir), "app.log")
    try:
        size = os.path.getsize(app_log)
    except OSError:
        size = 0
    return {
        "log_level": log_cfg.log_level,
        "log_dir": log_cfg.log_dir,
        "max_file_size_mb": log_cfg.max_file_size_mb,
        "max_backup_files": log_cfg.max_backup_files,
        "log_file_path": app_log,
        "log_file_size": size,
    }


def _positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


@bp.route("/api/settings/logging", methods=["GET"])
def api_get_logging_settings():
    """Get logging configuration and the live app.log path and size."""
    server_config = get_server_config()
    if not server_config:
        return jsonify({"error": "Server config not initialized"}), 500
    return jsonify(_logging_settings_response(server_config.logging))


@bp.route("/api/settings/logging", methods=["POST"])
def api_update_logging_settings():
    """Update log level and rotation; persisted and applied without a restart.

    Other gunicorn workers pick the change up on their next request (the
    settings sync in app/__init__.py). log_dir is deliberately not settable
    here: where the app writes files belongs in config/settings.json.
    """
    server_config = get_server_config()
    if not server_config:
        return jsonify({"error": "Server config not initialized"}), 500

    data = request.get_json(silent=True) or {}
    if "log_dir" in data:
        return jsonify({"error": "log_dir can only be changed in config/settings.json "
                                 "(takes effect after a restart)"}), 400
    if "log_level" in data and str(data["log_level"]).upper() not in LOG_LEVELS:
        return jsonify({"error": f"log_level must be one of {', '.join(LOG_LEVELS)}"}), 400
    for key in ("max_file_size_mb", "max_backup_files"):
        if key in data and not _positive_int(data[key]):
            return jsonify({"error": f"{key} must be a positive integer"}), 400

    log_cfg = server_config.logging
    changed = {}
    if "log_level" in data:
        changed["log_level"] = str(data["log_level"]).upper()
    for key in ("max_file_size_mb", "max_backup_files"):
        if key in data:
            changed[key] = data[key]
    for key, value in changed.items():
        setattr(log_cfg, key, value)

    save_server_config(server_config)
    from .. import mark_settings_current
    mark_settings_current(current_app)
    apply_runtime_settings(log_cfg)
    if changed:
        log_audit(action="settings_update", user=format_audit_user(get_audit_user_identity()),
                  section="logging", changed=",".join(changed), **changed)

    return jsonify({"success": True, "config": _logging_settings_response(log_cfg)})


# Limits on browser-supplied log text. Anyone who can reach the app can post
# here, so it must not be able to flood app.log (rotating real entries away)
# or forge entries with embedded line breaks.
MAX_FRONTEND_BATCH = 100
MAX_FRONTEND_MESSAGE = 2000
MAX_FRONTEND_CONTEXT = 2000

# Every character str.splitlines() breaks on, written as a visible escape.
_LINE_BREAKS = str.maketrans({
    c: f"\\x{ord(c):02x}" if ord(c) < 0x100 else f"\\u{ord(c):04x}"
    for c in "\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029"
} | {"\n": "\\n", "\r": "\\r"})


def _one_line(text, limit):
    """Render untrusted text as a single, bounded log line fragment."""
    text = str(text).translate(_LINE_BREAKS)
    if len(text) > limit:
        text = text[:limit] + "...[truncated]"
    return text


@bp.route("/api/logs/frontend", methods=["POST"])
def api_frontend_log():
    """Receive debug logs from frontend and write to file."""
    frontend_logger = logging.getLogger("app.frontend")

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Handle both single log entry (dict) and batch entries (list)
    entries = data if isinstance(data, list) else [data]
    dropped = max(0, len(entries) - MAX_FRONTEND_BATCH)
    entries = entries[:MAX_FRONTEND_BATCH]

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        level = str(entry.get("level", "debug")).lower()
        message = _one_line(entry.get("message", ""), MAX_FRONTEND_MESSAGE)
        context = entry.get("context", {})

        log_message = f"[frontend] {message}"
        if context:
            log_message += " | context: " + _one_line(json.dumps(context), MAX_FRONTEND_CONTEXT)

        if level == "error":
            frontend_logger.error(log_message)
        elif level == "warning":
            frontend_logger.warning(log_message)
        elif level == "info":
            frontend_logger.info(log_message)
        else:
            frontend_logger.debug(log_message)

    if dropped:
        frontend_logger.warning("[frontend] batch too large: dropped %d entries", dropped)

    return jsonify({"success": True})


