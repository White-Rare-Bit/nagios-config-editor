"""Settings and logging management routes."""

import json
import os
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request, send_file

from audit_service import (
    get_audit_log_dir,
    get_audit_log_path,
    rotate_audit_log,
)
from operation_logger import LogConfig
from server_config import save_config as save_server_config
from validator import verify_nagios_binary

from .helpers import (
    get_op_logger,
    get_server_config,
)

bp = Blueprint("settings", __name__)


@bp.route("/api/settings", methods=["GET"])
def api_get_settings():
    """Get current settings."""
    server_config = get_server_config()
    if not server_config:
        return jsonify({})

    return jsonify({
        "nagios_config_path": server_config.nagios_config_path,
        "backup_path": server_config.backup_path,
        "nagios_bin": server_config.nagios_bin,
        "nagios_cfg": server_config.nagios_cfg,
    })


@bp.route("/api/settings", methods=["POST"])
def api_update_settings():
    """Update settings and persist to config/settings.json."""
    server_config = get_server_config()
    if not server_config:
        return jsonify({"error": "Server config not initialized"}), 500

    data = request.get_json() or {}
    updated = []
    errors = []

    if "nagios_config_path" in data:
        _update_config_path(server_config, data["nagios_config_path"], updated, errors)
    if "backup_path" in data:
        _update_backup_path(server_config, data["backup_path"], updated, errors)
    if "nagios_bin" in data:
        _update_nagios_bin(server_config, data["nagios_bin"], updated, errors)
    if "nagios_cfg" in data:
        server_config.paths.nagios_cfg = data["nagios_cfg"]
        updated.append("nagios_cfg")

    if updated and not errors:
        try:
            save_server_config(server_config)
        except Exception as e:
            errors.append(f"Failed to save config: {e}")

    return jsonify({
        "success": len(errors) == 0,
        "updated": updated,
        "errors": errors,
        "config": {
            "nagios_config_path": server_config.nagios_config_path,
            "backup_path": server_config.backup_path,
            "nagios_bin": server_config.nagios_bin,
            "nagios_cfg": server_config.nagios_cfg,
        },
    })


def _update_config_path(server_config, path, updated, errors):
    """Update the Nagios config directory path.

    F-05: Creates all services BEFORE updating config to prevent inconsistent state.
    Appends to updated/errors lists in place.
    """
    if not os.path.isdir(path):
        errors.append(f"Invalid directory: {path}")
        return

    op_logger = get_op_logger()
    import file_operations
    from backup_manager import BackupManager
    from git_service import GitService
    from nagios_service import NagiosService
    from staging_manager import StagingManager

    normalized_path = os.path.abspath(path)

    try:
        new_staging = StagingManager(normalized_path, op_logger=op_logger)
        new_service = NagiosService(normalized_path, new_staging, op_logger=op_logger)
        _ = new_service.parser  # Force init to catch config errors early
        new_backup = BackupManager(normalized_path, server_config.backup_path, op_logger=op_logger)
        new_git = GitService(normalized_path, op_logger=op_logger)

        server_config.paths.nagios_config_path = normalized_path
        file_operations.set_logger(op_logger)
        current_app.extensions["service"] = new_service
        current_app.extensions["staging"] = new_staging
        current_app.extensions["backup"] = new_backup
        current_app.extensions["git"] = new_git
        updated.append("nagios_config_path")
    except Exception as e:
        errors.append(f"Failed to initialize services for path: {e}")


def _update_backup_path(server_config, path, updated, errors):
    """Update the backup directory path. Creates directory if needed."""
    if path and not os.path.isdir(path):
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as e:
            errors.append(f"Cannot create backup directory: {e}")
            return

    server_config.paths.backup_path = path or None

    op_logger = get_op_logger()
    from backup_manager import BackupManager
    backup_manager = BackupManager(
        server_config.nagios_config_path, server_config.backup_path, op_logger=op_logger,
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


@bp.route("/api/settings/logging", methods=["GET"])
def api_get_logging_settings():
    """Get logging configuration and file info."""
    op_logger = get_op_logger()
    if not op_logger:
        return jsonify({"error": "Logger not initialized"}), 500

    cfg = op_logger.config
    return jsonify({
        "enabled": cfg.enabled,
        "log_level": cfg.level,
        "log_dir": cfg.log_dir,
        "log_filename": cfg.filename,
        "max_file_size_mb": cfg.max_size_mb,
        "max_backup_files": cfg.max_backup_files,
        "log_file_path": str(op_logger.get_log_file_path()),
        "log_file_size": op_logger.get_log_file_size(),
        "rotated_files": [str(f) for f in op_logger.get_rotated_files()],
    })


@bp.route("/api/settings/logging", methods=["POST"])
def api_update_logging_settings():
    """Update logging configuration, persist, and reconfigure."""
    op_logger = get_op_logger()
    if not op_logger:
        return jsonify({"error": "Logger not initialized"}), 500

    data = request.get_json() or {}
    new_config = LogConfig(
        level=data.get("log_level", op_logger.config.level),
        log_dir=data.get("log_dir", op_logger.config.log_dir),
        filename=data.get("log_filename", op_logger.config.filename),
        max_size_mb=data.get("max_file_size_mb", op_logger.config.max_size_mb),
        max_backup_files=data.get("max_backup_files", op_logger.config.max_backup_files),
        enabled=data.get("enabled", op_logger.config.enabled),
    )

    # Update in-memory server config
    server_config = get_server_config()
    if server_config:
        server_config.logging.enabled = new_config.enabled
        server_config.logging.log_level = new_config.level
        server_config.logging.log_dir = new_config.log_dir
        server_config.logging.log_filename = new_config.filename
        server_config.logging.max_file_size_mb = new_config.max_size_mb
        server_config.logging.max_backup_files = new_config.max_backup_files

    # Persist to config/settings.json
    save_server_config(server_config)
    op_logger.reconfigure(new_config)

    return jsonify({"success": True, "config": {
        "enabled": new_config.enabled,
        "log_level": new_config.level,
        "log_dir": new_config.log_dir,
        "log_filename": new_config.filename,
        "max_file_size_mb": new_config.max_size_mb,
        "max_backup_files": new_config.max_backup_files,
    }})


@bp.route("/api/logs/operations", methods=["GET"])
def api_get_operation_logs():
    """Read recent log entries with optional filtering."""
    op_logger = get_op_logger()
    if not op_logger:
        return jsonify({"error": "Logger not initialized"}), 500

    limit = request.args.get("limit", 100, type=int)
    level_filter = request.args.get("level", "").upper()

    log_path = op_logger.get_log_file_path()
    if not log_path.exists():
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
    """Download the full log file."""
    op_logger = get_op_logger()
    if not op_logger:
        return jsonify({"error": "Logger not initialized"}), 500

    log_path = op_logger.get_log_file_path()
    if not log_path.exists():
        return jsonify({"error": "Log file not found"}), 404

    return send_file(str(log_path), mimetype="application/x-ndjson",
                     as_attachment=True, download_name=log_path.name)


@bp.route("/api/logs/frontend", methods=["POST"])
def api_frontend_log():
    """Receive debug logs from frontend and write to file."""
    import logging
    logger = logging.getLogger("nagios_bulk_editor.frontend")

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
            logger.error(log_message)
        elif level == "warning":
            logger.warning(log_message)
        elif level == "info":
            logger.info(log_message)
        else:
            logger.debug(log_message)

    return jsonify({"success": True})


@bp.route("/api/audit-log", methods=["GET"])
def api_get_audit_log():
    """Get the audit log."""
    # Use None to get default project root path, ensuring consistency with write_audit_log()
    audit_path = get_audit_log_path(None)
    if not os.path.exists(audit_path):
        return jsonify({"entries": []})

    try:
        with open(audit_path) as f:
            data = json.load(f)
        return jsonify(data)
    except (OSError, json.JSONDecodeError) as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/audit-log", methods=["POST"])
def api_save_audit_log():
    """Save an audit log entry."""
    # Use None to get default project root path, ensuring consistency with write_audit_log()
    audit_path = get_audit_log_path(None)

    try:
        entries = []
        if os.path.exists(audit_path):
            with open(audit_path) as f:
                data = json.load(f)
                entries = data.get("entries", [])

        new_entry = request.json
        entries.append(new_entry)

        entries = rotate_audit_log(entries)

        with open(audit_path, "w") as f:
            json.dump({"entries": entries}, f, indent=2)

        return jsonify({"success": True})
    except (OSError, json.JSONDecodeError) as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/audit-log/clear", methods=["POST"])
def api_clear_audit_log():
    """Clear the audit log."""
    # Use None to get default project root path, ensuring consistency with write_audit_log()
    audit_path = get_audit_log_path(None)

    try:
        with open(audit_path, "w") as f:
            json.dump({"entries": []}, f)
        return jsonify({"success": True})
    except OSError as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/audit-log/archives", methods=["GET"])
def api_list_audit_archives():
    """List all archived audit log files."""
    # Use None to get default project root path, ensuring consistency with write_audit_log()
    log_dir = get_audit_log_dir(None)

    archives = []
    try:
        for filename in os.listdir(log_dir):
            if filename.startswith("audit_log_") and filename.endswith(".json"):
                filepath = os.path.join(log_dir, filename)
                stat = os.stat(filepath)
                archives.append({
                    "filename": filename,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })

        archives.sort(key=lambda x: x["filename"], reverse=True)

        return jsonify({"archives": archives})
    except OSError as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/audit-log/archives/<filename>", methods=["GET"])
def api_get_audit_archive(filename):
    """Get a specific archived audit log."""
    if not filename.startswith("audit_log_") or not filename.endswith(".json"):
        return jsonify({"error": "Invalid archive filename"}), 400
    if "/" in filename or "\\" in filename or ".." in filename:
        return jsonify({"error": "Invalid archive filename"}), 400

    log_dir = get_audit_log_dir()
    filepath = os.path.join(log_dir, filename)

    if not os.path.exists(filepath):
        return jsonify({"error": "Archive not found"}), 404

    try:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)
    except (OSError, json.JSONDecodeError) as e:
        return jsonify({"error": str(e)}), 500
