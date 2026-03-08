"""Backup management routes."""

import logging
import os

from flask import Blueprint, jsonify, request

from audit_service import log_audit
from staging_manager import StagingStatus

from .helpers import (
    format_audit_user,
    get_audit_user_identity,
    get_backup_manager,
    get_service,
    get_staging_manager,
)

bp = Blueprint("backups", __name__)
logger = logging.getLogger(__name__)


@bp.route("/api/backups", methods=["GET"])
def api_list_backups():
    """List all backups."""
    bm = get_backup_manager()
    return jsonify(bm.list_backups())


@bp.route("/api/backups", methods=["POST"])
def api_create_backup():
    """Create a new backup."""
    bm = get_backup_manager()
    data = request.get_json() or {}
    description = data.get("description", "Manual backup")
    logger.info("Create backup: description=%s", description)

    # Get user identity from request
    identity = get_audit_user_identity()
    user_name = identity.get("userName", "")
    user_email = identity.get("userEmail", "")

    backup_path = bm.create_backup(description, user_name=user_name, user_email=user_email)
    bm.cleanup_old_backups(keep_count=20)

    # Write audit log entry
    log_audit(
        action="backup_created",
        user=format_audit_user(identity),
        description=description,
        backup_path=os.path.basename(backup_path) if backup_path else None,
    )

    return jsonify({"success": True, "path": backup_path})


@bp.route("/api/backups/<backup_name>/restore", methods=["POST"])
def api_restore_backup(backup_name):
    """Restore from a backup."""
    logger.info("Restore backup: backup_name=%s", backup_name)
    # Check staging lock - restore requires lock ownership or no lock
    session_id = request.headers.get("X-Session-Id")
    data = request.get_json() or {}
    if session_id:
        staging_mgr = get_staging_manager()
        lock_owner = staging_mgr.get_lock_owner()
        if lock_owner and lock_owner != session_id:
            return jsonify({
                "error": "Another user has pending changes. Wait for them to commit or discard.",
                "locked": True,
            }), 423

    bm = get_backup_manager()
    try:
        # Get user identity from request body for the safety backup
        user_name = data.get("userName", "")
        user_email = data.get("userEmail", "")

        result = bm.restore_backup(backup_name, user_name=user_name, user_email=user_email)
        get_service().reload()

        # Get user identity for audit log
        identity = get_audit_user_identity()

        # Create staging lock so other sessions see the pending restore changes
        if session_id:
            staging_mgr = get_staging_manager()
            staging_mgr.save_staging({
                "sessionId": session_id,
                "userName": identity.get("userName", ""),
                "userEmail": identity.get("userEmail", ""),
                "status": StagingStatus.RESTORE_PENDING.value,
                "restoreType": "backup",
                "restoreFrom": backup_name,
            })

        # Write audit log entry
        log_audit(
            action="backup_restored",
            user=format_audit_user(identity),
            backup_name=backup_name,
        )

        return jsonify({"success": True, **result})
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@bp.route("/api/backups/all", methods=["DELETE"])
def api_delete_all_backups():
    """Delete all backups."""
    bm = get_backup_manager()
    backups = bm.list_backups()
    deleted_count = 0

    for backup in backups:
        if bm.delete_backup(backup["name"]):
            deleted_count += 1

    if deleted_count > 0:
        # Write audit log entry
        identity = get_audit_user_identity()
        log_audit(
            action="backups_deleted",
            user=format_audit_user(identity),
            deleted_count=deleted_count,
        )

    return jsonify({"success": True, "deleted_count": deleted_count})


@bp.route("/api/backups/<backup_name>", methods=["DELETE"])
def api_delete_backup(backup_name):
    """Delete a backup."""
    logger.info("Delete backup: backup_name=%s", backup_name)
    bm = get_backup_manager()
    if bm.delete_backup(backup_name):
        # Write audit log entry
        identity = get_audit_user_identity()
        log_audit(
            action="backup_deleted",
            user=format_audit_user(identity),
            backup_name=backup_name,
        )
        return jsonify({"success": True})
    return jsonify({"error": "Backup not found"}), 404
