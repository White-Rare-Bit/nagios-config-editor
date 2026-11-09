"""Staging API routes — shadow copy architecture.

All mutations operate on a shadow copy of the config directory.
Apply copies changed files back to the original.
"""

import logging
import uuid

from flask import Blueprint, jsonify, request

from ..audit_service import log_audit

from .helpers import (
    format_audit_user,
    get_audit_user_identity,
    get_backup_manager,
    get_config,
    get_shadow_manager,
)
from .mutation import public_lock_status, staging_owner

bp = Blueprint("staging", __name__)
logger = logging.getLogger("nagios_bulk_editor.staging")


# =========================================================================
# Internal helpers
# =========================================================================


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
    """Clear staging — destroy shadow copy. Only the lock owner may do this."""
    with staging_owner() as sm:
        if not sm.has_shadow():
            return jsonify({"success": True})

        lock_status = sm.get_lock_status()
        result = sm.destroy_shadow()
        if result.success:
            log_audit(
                action="discard",
                user=format_audit_user(
                    name=lock_status.get("user_name"), email=lock_status.get("user_email"),
                ),
            )
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
    """Apply all staged changes to disk. Only the lock owner may do this."""
    bm = get_backup_manager()
    force = request.args.get("force", "").lower() == "true"

    with staging_owner() as sm:
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
    """Undo the last snapshot. Only the lock owner may do this."""
    with staging_owner() as sm:
        result = sm.undo()
    return jsonify({"success": result.success, "error": result.error})


@bp.route("/api/staging/lock", methods=["GET"])
def api_get_lock_status():
    """Get lock status: who holds it, and whether the caller does.

    The owner's session id is never returned; see public_lock_status().
    """
    return jsonify({"success": True, "data": public_lock_status()})


@bp.route("/api/staging/lock/break", methods=["POST"])
def api_break_lock():
    """Force break the lock — destroys shadow copy.

    Deliberately open to non-owners: it is the way out when the owner is
    gone. It discards their staged work, so it is always written to the
    audit log with both parties named.
    """
    sm = get_shadow_manager()
    lock_status = sm.get_lock_status()
    result = sm.break_lock()
    if result.success and lock_status.get("locked"):
        log_audit(
            action="lock_break",
            user=format_audit_user(get_audit_user_identity()),
            owner=format_audit_user(
                name=lock_status.get("user_name"), email=lock_status.get("user_email"),
            ),
        )
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
