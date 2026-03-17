"""Settings and logging management routes."""

import json
import logging
import os

from flask import Blueprint, current_app, jsonify, request, send_file

from ..server_config import save_config as save_server_config
from ..validator import verify_nagios_binary

from .helpers import (
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

    if "backup_path" in paths_data:
        _update_backup_path(server_config, paths_data["backup_path"], updated, errors)
    if "nagios_bin" in paths_data:
        _update_nagios_bin(server_config, paths_data["nagios_bin"], updated, errors)

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
    if needs_rediscovery and not errors:
        _rediscover_and_reinit(server_config, errors)

    if updated and not errors:
        try:
            save_server_config(server_config)
        except (OSError, ValueError) as e:
            errors.append(f"Failed to save config: {e}")

    discovery = current_app.extensions.get("discovery", {})

    return jsonify({
        "success": len(errors) == 0,
        "updated": updated,
        "errors": errors,
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

    Called when nagios_cfg or extra_cfg_dirs changes. Creates all services
    BEFORE updating app.extensions to prevent inconsistent state.
    """
    from ..backup_manager import BackupManager
    from ..config_discovery import discover_config_roots
    from ..git_service import GitService
    from ..nagios_service import NagiosService
    from ..shadow_copy_manager import ShadowCopyManager

    try:
        discovery = discover_config_roots(
            server_config.paths.nagios_cfg,
            extra_cfg_dirs=server_config.paths.extra_cfg_dirs,
        )
        accessible_dirs = [d["path"] for d in discovery["directories"] if d["accessible"]]
        cfg_files = discovery["cfg_files"]

        if discovery["resource_file"]:
            server_config.paths.resource_cfg = discovery["resource_file"]
        if not server_config.paths.primary_dir and accessible_dirs:
            server_config.paths.primary_dir = accessible_dirs[0]

        primary_dir = server_config.paths.primary_dir or "./sample-config"

        new_service = NagiosService(cfg_dirs=accessible_dirs, cfg_files=cfg_files)
        _ = new_service.parser  # Force init to catch config errors early
        new_backup = BackupManager(primary_dir, server_config.backup_path)
        new_git = GitService(primary_dir)

        shadow_path = server_config.shadow_path
        if not shadow_path:
            shadow_path = os.path.join(os.path.dirname(os.path.abspath(primary_dir)), ".shadow")
        new_shadow = ShadowCopyManager(cfg_dirs=accessible_dirs, shadow_base_path=shadow_path)

        current_app.extensions["service"] = new_service
        current_app.extensions["shadow"] = new_shadow
        current_app.extensions["backup"] = new_backup
        current_app.extensions["git"] = new_git
        current_app.extensions["discovery"] = discovery
    except Exception as e:  # noqa: BLE001
        errors.append(f"Failed to reinitialize services: {e}")


def _update_backup_path(server_config, path, updated, errors):
    """Update the backup directory path. Creates directory if needed."""
    if path and not os.path.isdir(path):
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as e:
            errors.append(f"Cannot create backup directory: {e}")
            return

    server_config.paths.backup_path = path or None

    from ..backup_manager import BackupManager
    primary_dir = server_config.paths.primary_dir or "./sample-config"
    backup_manager = BackupManager(primary_dir, server_config.backup_path)
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


@bp.route("/api/settings/logging", methods=["GET"])
def api_get_logging_settings():
    """Get logging configuration and file info.

    TODO: Reimplement using stdlib logging configuration after logging overhaul.
    """
    server_config = get_server_config()
    if not server_config:
        return jsonify({"error": "Server config not initialized"}), 500

    log_cfg = server_config.logging
    return jsonify({
        "enabled": log_cfg.enabled,
        "log_level": log_cfg.log_level,
        "log_dir": log_cfg.log_dir,
        "log_filename": log_cfg.log_filename,
        "max_file_size_mb": log_cfg.max_file_size_mb,
        "max_backup_files": log_cfg.max_backup_files,
    })


@bp.route("/api/settings/logging", methods=["POST"])
def api_update_logging_settings():
    """Update logging configuration, persist, and reconfigure.

    TODO: Reimplement runtime log level changes using stdlib logging after logging overhaul.
    """
    server_config = get_server_config()
    if not server_config:
        return jsonify({"error": "Server config not initialized"}), 500

    data = request.get_json() or {}
    log_cfg = server_config.logging

    # Update in-memory server config with provided values (or keep existing)
    log_cfg.enabled = data.get("enabled", log_cfg.enabled)
    log_cfg.log_level = data.get("log_level", log_cfg.log_level)
    log_cfg.log_dir = data.get("log_dir", log_cfg.log_dir)
    log_cfg.log_filename = data.get("log_filename", log_cfg.log_filename)
    log_cfg.max_file_size_mb = data.get("max_file_size_mb", log_cfg.max_file_size_mb)
    log_cfg.max_backup_files = data.get("max_backup_files", log_cfg.max_backup_files)

    # Persist to config/settings.json
    save_server_config(server_config)

    return jsonify({"success": True, "config": {
        "enabled": log_cfg.enabled,
        "log_level": log_cfg.log_level,
        "log_dir": log_cfg.log_dir,
        "log_filename": log_cfg.log_filename,
        "max_file_size_mb": log_cfg.max_file_size_mb,
        "max_backup_files": log_cfg.max_backup_files,
    }})


@bp.route("/api/logs/operations", methods=["GET"])
def api_get_operation_logs():
    """Read recent log entries with optional filtering.

    TODO: Reimplement to read from stdlib logging file after logging overhaul.
    """
    server_config = get_server_config()
    if not server_config:
        return jsonify({"error": "Server config not initialized"}), 500

    limit = request.args.get("limit", 100, type=int)
    level_filter = request.args.get("level", "").upper()

    log_dir = server_config.logging.log_dir
    log_filename = server_config.logging.log_filename
    if not log_dir or not log_filename:
        return jsonify({"entries": [], "total": 0})

    log_path = os.path.join(log_dir, log_filename)
    if not os.path.exists(log_path):
        return jsonify({"entries": [], "total": 0})

    entries = []
    try:
        with open(log_path, encoding="utf-8") as f:
            lines = f.readlines()

        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if level_filter and entry.get("level") != level_filter:
                    continue
                entries.append(entry)
                if len(entries) >= limit:
                    break
            except json.JSONDecodeError:
                continue
    except OSError:
        pass

    return jsonify({"entries": entries, "total": len(lines) if "lines" in dir() else 0})


@bp.route("/api/logs/operations/download", methods=["GET"])
def api_download_operation_logs():
    """Download the full log file.

    TODO: Reimplement to locate stdlib logging file after logging overhaul.
    """
    server_config = get_server_config()
    if not server_config:
        return jsonify({"error": "Server config not initialized"}), 500

    log_dir = server_config.logging.log_dir
    log_filename = server_config.logging.log_filename
    if not log_dir or not log_filename:
        return jsonify({"error": "Log file path not configured"}), 404

    log_path = os.path.join(log_dir, log_filename)
    if not os.path.exists(log_path):
        return jsonify({"error": "Log file not found"}), 404

    return send_file(log_path, mimetype="application/x-ndjson",
                     as_attachment=True, download_name=log_filename)


@bp.route("/api/logs/frontend", methods=["POST"])
def api_frontend_log():
    """Receive debug logs from frontend and write to file."""
    frontend_logger = logging.getLogger("nagios_bulk_editor.frontend")

    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Handle both single log entry (dict) and batch entries (list)
    entries = data if isinstance(data, list) else [data]

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        level = entry.get("level", "debug").lower()
        message = entry.get("message", "")
        context = entry.get("context", {})

        log_message = f"[frontend] {message}"
        if context:
            log_message += f" | context: {json.dumps(context)}"

        if level == "error":
            frontend_logger.error(log_message)
        elif level == "warning":
            frontend_logger.warning(log_message)
        elif level == "info":
            frontend_logger.info(log_message)
        else:
            frontend_logger.debug(log_message)

    return jsonify({"success": True})


