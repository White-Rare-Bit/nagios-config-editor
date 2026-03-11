"""Staging API routes — shadow copy architecture.

All mutations operate on a shadow copy of the config directory.
Apply copies changed files back to the original.
"""

import logging
import os
import uuid

from flask import Blueprint, jsonify, request

from audit_service import log_audit

from .helpers import (
    format_audit_user,
    get_backup_manager,
    get_config,
    get_config_path,
    get_service,
    get_shadow_manager,
)

bp = Blueprint("staging", __name__)
logger = logging.getLogger("nagios_bulk_editor.staging")


# =========================================================================
# Internal helpers
# =========================================================================


def _make_relative_path(path):
    """Convert an absolute path to a path relative to the config directory's parent.

    For config_path=/etc/nagios/objects and path=/etc/nagios/objects/hosts.cfg,
    returns "objects/hosts.cfg". This preserves the config dir name while
    stripping server filesystem structure from audit logs.
    """
    if not path:
        return path
    config_path = get_config_path()
    if config_path and path.startswith(config_path):
        return os.path.relpath(path, os.path.dirname(config_path))
    return path


def _run_post_apply_validation():
    """Run nagios -v validation after a successful apply.

    Returns:
        Validation result dict, or None if validation was not requested/possible

    """
    try:
        config = get_config()
        nagios_bin = config.get("nagios_bin", "")
        nagios_cfg = config.get("nagios_cfg", "")
        if nagios_bin and nagios_cfg:
            from validator import NagiosValidator

            validator = NagiosValidator(nagios_bin, nagios_cfg)
            val_result = validator.validate()
            return val_result.to_dict()
        return {
            "success": None,
            "skipped": True,
            "message": "Nagios binary or config path not configured",
        }
    except Exception as e:  # noqa: BLE001
        return {
            "success": None,
            "skipped": True,
            "message": f"Validation failed to run: {e!s}",
        }


def _get_existing_folders(config_path):
    """Get list of existing non-hidden subdirectories under config_path.

    Args:
        config_path: Base configuration directory path

    Returns:
        List of absolute folder paths

    """
    existing_folders = []
    try:
        for root, dirs, _files in os.walk(config_path):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            rel_path = os.path.relpath(root, config_path)
            if rel_path != ".":
                existing_folders.append(os.path.join(config_path, rel_path))
    except OSError:
        pass
    return existing_folders


# =========================================================================
# Routes
# =========================================================================


@bp.route("/api/staging", methods=["GET"])
def api_get_staging():
    """Get current staged changes (file-level diff)."""
    sm = get_shadow_manager()
    if not sm.has_shadow():
        return jsonify({"success": True, "data": {"changes": [], "totalCount": 0}})
    changes = sm.get_changed_files()
    return jsonify({
        "success": True,
        "data": {
            "changes": changes,
            "totalCount": sm.get_changed_object_count(),
        },
    })


@bp.route("/api/staging", methods=["DELETE"])
def api_delete_staging():
    """Clear staging — destroy shadow copy."""
    sm = get_shadow_manager()
    if not sm.has_shadow():
        return jsonify({"success": True})

    # Reload service to point back at original config
    result = sm.destroy_shadow()
    if result.success:
        service = get_service()
        service.config_path = sm.config_path
        service.reload()
    return jsonify({"success": result.success, "error": result.error})


@bp.route("/api/staging/info", methods=["GET"])
def api_get_staging_info():
    """Get lightweight summary of staging (counts only)."""
    sm = get_shadow_manager()
    if not sm.has_shadow():
        return jsonify({
            "success": True,
            "data": {"totalCount": 0, "undoCount": 0, "changedFiles": 0},
        })
    return jsonify({
        "success": True,
        "data": {
            "totalCount": sm.get_changed_object_count(),
            "undoCount": sm.get_undo_count(),
            "changedFiles": len(sm.get_changed_files()),
        },
    })


@bp.route("/api/staging/apply", methods=["POST"])
def api_apply_staging():
    """Apply all staged changes to disk."""
    sm = get_shadow_manager()
    bm = get_backup_manager()

    # Get lock info for audit before apply destroys it
    lock_status = sm.get_lock_status() if sm.has_shadow() else {}
    user_name = lock_status.get("user_name", "")
    user_email = lock_status.get("user_email", "")

    result = sm.apply(backup_manager=bm)
    if result.success:
        # Reload service to pick up applied changes (now on original config)
        service = get_service()
        service.config_path = sm.config_path
        service.reload()

        # Audit log
        changed = result.data.get("changed_files", []) if result.data else []
        if changed:
            txn = uuid.uuid4().hex[:8]
            user = format_audit_user(name=user_name, email=user_email)
            log_audit(
                action="apply",
                user=user,
                txn=txn,
                files_changed=len(changed),
            )

        # Post-apply validation
        validation = _run_post_apply_validation()

        return jsonify({
            "success": True,
            "data": result.data,
            "validation": validation,
        })

    return jsonify({"success": False, "error": result.error}), 500


@bp.route("/api/staging/undo", methods=["POST"])
def api_staging_undo():
    """Undo the last snapshot."""
    sm = get_shadow_manager()
    session_id = request.headers.get("X-Session-Id")
    if sm.has_shadow() and not sm.can_modify(session_id):
        return jsonify({"success": False, "error": "Not lock owner"}), 423

    result = sm.undo()
    if result.success:
        # Reload service parser to reflect undo
        service = get_service()
        service.reload()
    return jsonify({"success": result.success, "error": result.error})


@bp.route("/api/staging/lock", methods=["GET"])
def api_get_lock_status():
    """Get lock status."""
    sm = get_shadow_manager()
    return jsonify({"success": True, "data": sm.get_lock_status()})


@bp.route("/api/staging/lock/break", methods=["POST"])
def api_break_lock():
    """Force break the lock — destroys shadow copy."""
    sm = get_shadow_manager()
    result = sm.break_lock()
    if result.success:
        service = get_service()
        service.config_path = sm.config_path
        service.reload()
    return jsonify({"success": result.success, "error": result.error})


@bp.route("/api/staging/diff", methods=["GET"])
def api_staging_diff():
    """Get file diffs between shadow and original."""
    sm = get_shadow_manager()
    if not sm.has_shadow():
        return jsonify({"success": True, "data": {"files": []}})
    context_lines = request.args.get("context_lines", 3, type=int)
    files = sm.get_changed_files()
    for f in files:
        f["diff"] = sm.get_file_diff(f["path"], context_lines=context_lines)
    return jsonify({"success": True, "data": {"files": files}})
