"""Staging API routes — shadow copy architecture.

All mutations operate on a shadow copy of the config directory.
Apply copies changed files back to the original.
"""

import logging
import os
import uuid

from flask import Blueprint, jsonify, request

from ..audit_service import log_audit

from .helpers import (
    format_audit_user,
    get_backup_manager,
    get_config,
    get_config_path,
    get_server_config,
    get_service,
    get_shadow_manager,
    make_relative_path,
)

bp = Blueprint("staging", __name__)
logger = logging.getLogger("nagios_bulk_editor.staging")


# =========================================================================
# Internal helpers
# =========================================================================


def _restore_service_to_original_roots():
    """Reset the service to point at original config roots after apply/destroy.

    Reads original roots from the shadow manager's root_map (before destroy)
    or from the discovery stored in app.extensions.
    """
    from flask import current_app

    service = get_service()
    sm = get_shadow_manager()

    # Try root_map first (available before shadow is destroyed)
    root_map = sm.get_root_map()
    if root_map:
        original_dirs = list(root_map.values())
        service.set_roots(cfg_dirs=original_dirs, cfg_files=[])
    else:
        # Fall back to discovery stored at app init
        discovery = current_app.extensions.get("discovery", {})
        accessible_dirs = [d["path"] for d in discovery.get("directories", []) if d["accessible"]]
        cfg_files = discovery.get("cfg_files", [])
        if accessible_dirs or cfg_files:
            service.set_roots(cfg_dirs=accessible_dirs, cfg_files=cfg_files)
        else:
            # Last resort: use primary_dir from server config
            server_config = get_server_config()
            if server_config and server_config.paths.primary_dir:
                service.set_roots(cfg_dirs=[server_config.paths.primary_dir], cfg_files=[])

    service.reload()


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
            from ..validator import NagiosValidator

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

    # Restore service to original roots before destroying shadow
    _restore_service_to_original_roots()
    result = sm.destroy_shadow()
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
    changed_keys = sm.get_changed_object_keys()
    return jsonify({
        "success": True,
        "data": {
            "totalCount": len(changed_keys),
            "changedObjectKeys": changed_keys,
            "undoCount": sm.get_undo_count(),
            "changedFiles": len(sm.get_changed_files()),
        },
    })


@bp.route("/api/staging/apply", methods=["POST"])
def api_apply_staging():
    """Apply all staged changes to disk."""
    sm = get_shadow_manager()
    bm = get_backup_manager()
    force = request.args.get("force", "").lower() == "true"

    # Get lock info for audit before apply destroys it
    lock_status = sm.get_lock_status() if sm.has_shadow() else {}
    user_name = lock_status.get("user_name", "")
    user_email = lock_status.get("user_email", "")

    result = sm.apply(backup_manager=bm, force=force)

    if not result.success:
        if result.error == "conflicts":
            return jsonify({
                "success": False,
                "error": "conflicts",
                "conflicts": result.data["conflicts"],
            }), 409
        return jsonify({"success": False, "error": result.error}), 500

    # Reload service to pick up applied changes (now on original config)
    _restore_service_to_original_roots()

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
    # Restore service to original roots before breaking lock
    if sm.has_shadow():
        _restore_service_to_original_roots()
    result = sm.break_lock()
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
        f["diff"] = sm.get_file_diff(f["path"], context_lines=context_lines,
                                         display_path=f.get("display_path", ""))
    return jsonify({"success": True, "data": {"files": files}})
