"""Git integration routes — shadow copy architecture."""

import logging

from flask import Blueprint, jsonify, request

from audit_service import log_audit
from file_operations import is_safe_path

from .helpers import (
    format_audit_user,
    get_audit_user_identity,
    get_config_path,
    get_git_service,
    get_service,
    get_shadow_manager,
)

bp = Blueprint("git", __name__)
logger = logging.getLogger(__name__)


def _check_shadow_lock(session_id, operation="git"):
    """Check if shadow is locked by another session.

    Returns:
        Error response tuple (jsonify, status_code) if locked, or None if OK.

    """
    if not session_id:
        return None
    sm = get_shadow_manager()
    if not sm.has_shadow():
        return None
    if sm.can_modify(session_id):
        return None
    lock_status = sm.get_lock_status()
    logger.warning("Lock conflict on %s: session_id=%s, lock_owner=%s",
                   operation, session_id, lock_status.get("session_id"))
    return jsonify({
        "error": "Another user has pending changes. Wait for them to commit or discard.",
        "locked": True,
        "lockOwner": lock_status,
    }), 423


def _resolve_user_identity(data):
    """Resolve user identity from request body, falling back to shadow lock state.

    Returns:
        Tuple of (user_name, user_email) - either may be None.

    """
    user_name = data.get("user_name", "").strip() if data.get("user_name") else None
    user_email = data.get("user_email", "").strip() if data.get("user_email") else None

    if not user_name or not user_email:
        sm = get_shadow_manager()
        if sm.has_shadow():
            lock_status = sm.get_lock_status()
            user_name = user_name or lock_status.get("user_name")
            user_email = user_email or lock_status.get("user_email")

    return user_name, user_email


def _validate_commit_files(files, config_path):
    """Validate file paths for a commit.

    Returns:
        Error response tuple if invalid, or None if all valid.

    """
    for filepath in files:
        safe_result = is_safe_path(filepath, config_path)
        if not safe_result.success:
            logger.warning("Commit path validation failed: file=%s, error=%s",
                           filepath, safe_result.error)
            return jsonify({"error": f"Invalid file path: {safe_result.error}"}), 400
    return None


def _write_commit_audit_log(commit_hash, message, user_name, user_email, initialized):
    """Write audit log entry for a git commit."""
    user = format_audit_user(name=user_name, email=user_email)
    if initialized:
        log_audit(
            action="git_initialized", user=user,
            commit_hash=commit_hash, message=message,
        )
        return

    log_audit(action="git_commit", user=user, commit_hash=commit_hash, message=message)


@bp.route("/api/git/identity", methods=["GET"])
def api_git_identity_get():
    """Get the identity of the current lock owner from shadow lock state."""
    try:
        sm = get_shadow_manager()
        if not sm.has_shadow():
            return jsonify({
                "user_name": "",
                "user_email": "",
                "is_configured": False,
                "has_lock": False,
            })

        lock_status = sm.get_lock_status()
        user_name = lock_status.get("user_name", "")
        user_email = lock_status.get("user_email", "")

        return jsonify({
            "user_name": user_name,
            "user_email": user_email,
            "is_configured": bool(user_name and user_email),
            "has_lock": True,
        })

    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500


@bp.route("/api/git/identity", methods=["POST"])
def api_git_identity_set():
    """Update user identity in shadow lock state.

    Requires X-Session-Id header. Only the lock owner can update identity.
    """
    session_id = request.headers.get("X-Session-Id")
    if not session_id:
        return jsonify({"error": "X-Session-Id header required"}), 400

    lock_error = _check_shadow_lock(session_id)
    if lock_error:
        return lock_error

    data = request.get_json() or {}
    error = _validate_identity_input(data)
    if error:
        return error

    user_name = data.get("user_name", "").strip()
    user_email = data.get("user_email", "").strip()

    try:
        sm = get_shadow_manager()
        if not sm.has_shadow():
            # Create shadow to store identity
            result = sm.create_shadow(session_id, user_name, user_email)
            if not result.success:
                return jsonify({"error": result.error or "Failed to create shadow"}), 500
            # Point service at shadow
            service = get_service()
            service.config_path = sm._config_dir
            service.reload()
        else:
            # Update lock file with new identity
            import json
            import os
            lock_file = sm._lock_file
            if os.path.isfile(lock_file):
                with open(lock_file) as f:
                    lock_data = json.load(f)
                lock_data["user_name"] = user_name
                lock_data["user_email"] = user_email
                with open(lock_file, "w") as f:
                    json.dump(lock_data, f, indent=2)

        return jsonify({"success": True, "user_name": user_name, "user_email": user_email})

    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500


def _validate_identity_input(data):
    """Validate user identity fields from request data.

    Returns:
        Error response tuple if invalid, or None if valid.

    """
    user_name = data.get("user_name", "").strip()
    user_email = data.get("user_email", "").strip()

    if not user_name or not user_email:
        return jsonify({"error": "Both user_name and user_email are required"}), 400
    if "@" not in user_email or "." not in user_email:
        return jsonify({"error": "Invalid email format"}), 400
    return None


@bp.route("/api/git/status", methods=["GET"])
def api_git_status():
    """Get git status of config directory."""
    try:
        git_svc = get_git_service()
        result = git_svc.get_status()
        if not result.success:
            return jsonify({"error": result.error}), 500

        status = result.data
        return jsonify({
            "is_repo": status.is_repo,
            "branch": status.branch,
            "files": [{"path": f.path, "status": f.status, "status_code": f.status_code,
                        "staged": f.staged, "unstaged": f.unstaged}
                       for f in status.files],
            "has_changes": status.has_changes,
            **({"error": status.error} if status.error else {}),
        })
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"Failed to get git status: {e!s}"}), 500


@bp.route("/api/git/diff", methods=["POST"])
def api_git_diff():
    """Get git diff for a file or all changes."""
    config_path = get_config_path()
    data = request.get_json() or {}

    filepath = data.get("file")
    staged = data.get("staged", False)
    full_file = data.get("fullFile", True)
    context_lines = data.get("contextLines")

    if filepath:
        safe_result = is_safe_path(filepath, config_path)
        if not safe_result.success:
            return jsonify({"error": safe_result.error}), 400

    try:
        git_svc = get_git_service()
        result = git_svc.get_diff(filepath=filepath, staged=staged, full_file=full_file,
                                  context_lines=context_lines)
        if not result.success:
            return jsonify({"error": result.error}), 500

        return jsonify({
            "success": True,
            "diff": result.data,
            "file": filepath,
        })
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"Failed to get diff: {e!s}"}), 500


@bp.route("/api/git/commit", methods=["POST"])
def api_git_commit():
    """Commit changes to git."""
    data = request.get_json() or {}
    logger.info("Git commit: message=%s", data.get("message", "")[:100])

    message = data.get("message", "").strip()
    if not message:
        return jsonify({"error": "Commit message is required"}), 400

    session_id = request.headers.get("X-Session-Id")
    lock_error = _check_shadow_lock(session_id, "commit")
    if lock_error:
        return lock_error

    precondition_error = _validate_commit_preconditions(data)
    if precondition_error:
        return precondition_error

    try:
        return _execute_commit(data, message, session_id)
    except Exception as e:  # noqa: BLE001
        logger.error("Git commit failed: %s", e)
        return jsonify({"error": f"Failed to commit: {e!s}"}), 500


def _validate_commit_preconditions(data):
    """Validate identity and file paths for a commit.

    Returns:
        Error response tuple if invalid, or None if all valid.

    """
    user_name, user_email = _resolve_user_identity(data)
    if not user_name or not user_email:
        return jsonify({
            "error": "Please set your name and email in Settings before committing.",
            "needsConfig": True,
        }), 400

    files = data.get("files", [])
    if files:
        return _validate_commit_files(files, get_config_path())
    return None


def _execute_commit(data, message, session_id):
    """Execute the git commit after preconditions are validated.

    Returns:
        Flask response.

    """
    user_name, user_email = _resolve_user_identity(data)
    files = data.get("files", [])
    auto_init = data.get("auto_init", False)

    git_svc = get_git_service()

    result = git_svc.commit(
        message=message, files=files or None,
        user_name=user_name, user_email=user_email, auto_init=auto_init,
    )

    if not result.success:
        return _handle_commit_failure(result)

    commit_hash = result.data["commit_hash"]
    initialized = result.data["initialized"]
    _write_commit_audit_log(commit_hash, message, user_name, user_email, initialized)

    # Destroy shadow on successful commit
    sm = get_shadow_manager()
    if sm.has_shadow():
        sm.destroy_shadow()
        # Point service back at original config
        service = get_service()
        service.config_path = sm.config_path
        service.reload()

    return jsonify({
        "success": True, "commit_hash": commit_hash, "message": message,
        "output": result.data["output"], "initialized": initialized,
    })


def _handle_commit_failure(result):
    """Handle a failed git commit result.

    Returns:
        Flask response tuple.

    """
    if "nothing to commit" in (result.error or "").lower():
        return jsonify({
            "success": False, "error": "Nothing to commit",
            "message": "Working directory is clean",
        })
    return jsonify({"error": result.error}), 400


@bp.route("/api/git/discard", methods=["POST"])
def api_git_discard():
    """Discard changes to a file."""
    config_path = get_config_path()
    data = request.get_json() or {}

    filepath = data.get("file")
    logger.info("Git discard file: %s", filepath)

    if not filepath:
        return jsonify({"error": "File path is required"}), 400

    session_id = request.headers.get("X-Session-Id")
    lock_error = _check_shadow_lock(session_id, "discard_file")
    if lock_error:
        return lock_error

    safe_result = is_safe_path(filepath, config_path)
    if not safe_result.success:
        logger.warning("Discard file path validation failed: file=%s, error=%s",
                       filepath, safe_result.error)
        return jsonify({"error": safe_result.error}), 400

    try:
        git_svc = get_git_service()
        result = git_svc.discard(filepath)
        if not result.success:
            return jsonify({"error": result.error}), 400

        if result.data["action"] == "restored":
            get_service().reload()

        return jsonify({"success": True, "action": result.data["action"]})

    except Exception as e:  # noqa: BLE001
        logger.error("Git discard file failed: file=%s, error=%s", filepath, e)
        return jsonify({"error": f"Failed to discard changes: {e!s}"}), 500


@bp.route("/api/git/discard-all", methods=["POST"])
def api_git_discard_all():
    """Discard all uncommitted changes."""
    logger.info("Git discard all")

    session_id = request.headers.get("X-Session-Id")
    lock_error = _check_shadow_lock(session_id, "discard_all")
    if lock_error:
        return lock_error

    try:
        git_svc = get_git_service()
        result = git_svc.discard_all()

        if not result.success:
            return jsonify({
                "error": result.error,
                "commands": result.data.get("commands", []) if result.data else [],
            }), 400

        # Reload config to reflect changes
        get_service().reload()

        # Destroy shadow if present
        sm = get_shadow_manager()
        if sm.has_shadow():
            sm.destroy_shadow()
            service = get_service()
            service.config_path = sm.config_path
            service.reload()

        # Write audit log entry for discard
        identity = get_audit_user_identity()
        log_audit(
            action="git_discarded", user=format_audit_user(identity),
            description="Discarded all uncommitted changes",
        )

        return jsonify({
            "success": True,
            "commands": result.data["commands"],
        })

    except Exception as e:  # noqa: BLE001
        logger.error("Git discard all failed: %s", e)
        return jsonify({"error": f"Failed to discard changes: {e!s}"}), 500


@bp.route("/api/git/clear-history", methods=["POST"])
def api_git_clear_history():
    """Clear all git history and reinitialize with a fresh commit."""
    logger.warning("Git clear history requested")

    session_id = request.headers.get("X-Session-Id")
    lock_error = _check_shadow_lock(session_id, "clear_history")
    if lock_error:
        return lock_error

    try:
        data = request.get_json() or {}
        user_name = data.get("user_name", "").strip() if data.get("user_name") else None
        user_email = data.get("user_email", "").strip() if data.get("user_email") else None

        if not user_name or not user_email:
            return jsonify({
                "error": "Please set your name and email in Settings before clearing history.",
                "needsConfig": True,
            }), 400

        git_svc = get_git_service()
        result = git_svc.clear_history(user_name=user_name, user_email=user_email)
        if not result.success:
            return jsonify({"error": result.error}), 400

        log_audit(
            action="git_clear_history", user=format_audit_user(name=user_name, email=user_email),
            description="Cleared all git history and reinitialized repository",
        )

        return jsonify({"success": True, "message": result.data["message"]})

    except Exception as e:  # noqa: BLE001
        logger.error("Git clear history failed: %s", e)
        return jsonify({"error": f"Failed to clear history: {e!s}"}), 500


@bp.route("/api/git/log", methods=["GET"])
def api_git_log():
    """Get git commit history."""
    limit = request.args.get("limit", 50, type=int)

    try:
        git_svc = get_git_service()
        result = git_svc.get_log(limit=limit)
        if not result.success:
            return jsonify({"error": result.error}), 400

        data = result.data
        commits = [{"hash": c.hash, "hash_short": c.hash_short, "author": c.author,
                    "date": c.date, "message": c.message,
                    "matches_working_dir": c.matches_working_dir}
                   for c in data.get("commits", [])]

        response = {
            "is_repo": data.get("is_repo", False),
            "commits": commits,
        }
        if "matching_commit" in data:
            response["matching_commit"] = data["matching_commit"]
        if "error" in data:
            response["error"] = data["error"]
        if "message" in data:
            response["message"] = data["message"]
        return jsonify(response)

    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"Failed to get log: {e!s}"}), 500


@bp.route("/api/git/restore", methods=["POST"])
def api_git_restore():
    """Restore working directory to a specific commit.

    Requires X-Session-Id header. Rejects if shadow is locked by another session.
    Destroys shadow on successful restore.
    """
    data = request.get_json() or {}

    commit_hash = data.get("commit")

    if not commit_hash:
        return jsonify({"error": "Commit hash is required"}), 400

    session_id = request.headers.get("X-Session-Id")
    lock_error = _check_shadow_lock(session_id, "restore")
    if lock_error:
        return lock_error

    # Validate commit hash format (prevent injection)
    if not commit_hash.replace("-", "").isalnum():
        return jsonify({"error": "Invalid commit hash format"}), 400

    try:
        git_svc = get_git_service()
        result = git_svc.restore(commit_hash)

        if not result.success:
            status_code = 404 if "not found" in (result.error or "").lower() else 400
            return jsonify({"error": result.error}), status_code

        # Reload config to reflect changes
        get_service().reload()

        # Write audit log entry for git restore
        audit_identity = get_audit_user_identity()
        log_audit(
            action="git_restored", user=format_audit_user(audit_identity),
            commit_hash=commit_hash,
            commit_message=result.data["message"],
            deleted_files_count=len(result.data["deleted_files"]),
        )

        # Destroy shadow if present — restore replaces working dir
        sm = get_shadow_manager()
        if sm.has_shadow():
            sm.destroy_shadow()
            service = get_service()
            service.config_path = sm.config_path
            service.reload()

        return jsonify({
            "success": True,
            "commit": result.data["commit"],
            "message": result.data["message"],
            "had_uncommitted_changes": result.data["had_uncommitted_changes"],
            "stashed": result.data["stashed"],
            "deleted_files": result.data["deleted_files"],
        })

    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"Failed to restore: {e!s}"}), 500
