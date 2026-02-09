"""File and folder management routes."""

import os
import shutil

from flask import Blueprint, jsonify, request

from file_operations import is_safe_path as file_ops_is_safe_path

from .helpers import (
    get_audit_user_identity,
    get_backup_manager,
    get_config_path,
    get_parser_for_modification,
    get_service,
    get_staging_manager,
    operation_response,
)

bp = Blueprint("files", __name__)


def is_safe_path(path: str, base_dir: str = None):
    """Wrapper that provides get_config_path() as default for base_dir.

    Returns:
        OperationResult with success=True if safe, success=False with error if unsafe.

    """
    if base_dir is None:
        base_dir = get_config_path()
    return file_ops_is_safe_path(path, base_dir)


def ensure_staging_lock(session_id: str) -> tuple:
    """Ensure session has staging lock. Returns (success, error_response).

    If no staging exists, creates it and acquires the lock for this session.
    """
    if not session_id:
        return False, (jsonify({"error": "X-Session-Id header required"}), 400)

    sm = get_staging_manager()

    # Check current lock status
    owner = sm.get_lock_owner()

    if owner is None:
        # No lock exists - acquire it
        identity = get_audit_user_identity()
        staging = {
            "sessionId": session_id,
            "userName": identity.get("userName", ""),
            "userEmail": identity.get("userEmail", ""),
        }
        if not sm.save_staging(staging).success:
            return False, (jsonify({"error": "Failed to acquire staging lock"}), 500)
        return True, None

    if owner == session_id:
        # Already own the lock
        return True, None

    # Locked by another session
    return False, (jsonify({
        "error": "Staging is locked by another user",
        "locked": True,
    }), 423)


# ─────────────────────────────────────────────────────────────────────
# Validation helpers (reduce return counts in route handlers)
# ─────────────────────────────────────────────────────────────────────

def _validate_move_paths(data):
    """Validate sourcePath and targetFolder from request data.

    Returns (abs_source, abs_target_folder, error_response).
    error_response is None on success, or a (jsonify, status) tuple on failure.
    """
    source_path = data.get("sourcePath")
    target_folder = data.get("targetFolder")

    if not source_path:
        return None, None, (jsonify({"error": "sourcePath required"}), 400)
    if not target_folder:
        return None, None, (jsonify({"error": "targetFolder required"}), 400)

    config_path = get_config_path()
    abs_source = os.path.abspath(source_path)
    abs_target_folder = os.path.abspath(target_folder)

    if not abs_source.startswith(os.path.abspath(config_path)):
        return None, None, (jsonify({"error": "Source path must be within config directory"}), 400)
    if not abs_target_folder.startswith(os.path.abspath(config_path)):
        return None, None, (jsonify({"error": "Target folder must be within config directory"}), 400)

    return abs_source, abs_target_folder, None


def _validate_relocate_paths(data):
    """Validate source_path and target_folder from relocate request data.

    Returns (source_path, target_folder, error_response).
    error_response is None on success, or a (jsonify, status) tuple on failure.
    """
    source_path = data.get("source_path")
    target_folder = data.get("target_folder")

    if not source_path:
        return None, None, (jsonify({"error": "source_path is required"}), 400)
    if not target_folder:
        return None, None, (jsonify({"error": "target_folder is required"}), 400)

    return os.path.normpath(source_path), os.path.normpath(target_folder), None


def _validate_relocate_file_exists(source_path, new_path):
    """Validate that source exists, is a file, and target doesn't already exist.

    Returns error_response (None on success, or a (jsonify, status) tuple on failure).
    """
    if not os.path.exists(source_path):
        return (jsonify({"error": f"Source file not found: {source_path}"}), 404)
    if not os.path.isfile(source_path):
        return (jsonify({"error": f"Source is not a file: {source_path}"}), 400)
    if os.path.exists(new_path):
        return (jsonify({"error": f"Target file already exists: {new_path}"}), 400)
    return None


def _validate_relocate_folder_exists(source_path, target_folder, new_path):
    """Validate that source exists, is a folder, target is valid, and doesn't already exist.

    Returns error_response (None on success, or a (jsonify, status) tuple on failure).
    """
    if not os.path.exists(source_path):
        return (jsonify({"error": f"Source folder not found: {source_path}"}), 404)
    if not os.path.isdir(source_path):
        return (jsonify({"error": f"Source is not a folder: {source_path}"}), 400)
    if target_folder == source_path or target_folder.startswith(source_path + os.sep):
        return (jsonify({"error": "Cannot move folder into itself"}), 400)
    if os.path.exists(new_path):
        return (jsonify({"error": f"Target folder already exists: {new_path}"}), 400)
    return None


# ═══════════════════════════════════════════════════════════════════════
# Route handlers
# ═══════════════════════════════════════════════════════════════════════

@bp.route("/api/files")
def api_files():
    """Get list of all .cfg files in the config directory."""
    config_dir = get_config_path()
    files = []

    if os.path.exists(config_dir):
        for root, dirs, filenames in os.walk(config_dir):
            # Skip backup directories
            dirs[:] = [d for d in dirs if d not in ("backups", "backup")]
            for filename in filenames:
                if filename.endswith(".cfg"):
                    files.append(os.path.join(root, filename))

    return jsonify({"files": sorted(files)})


@bp.route("/api/folders", methods=["GET"])
def api_list_folders():
    """List all folders in the config directory."""
    config_dir = get_config_path()
    folders = []

    if os.path.exists(config_dir):
        for root, dirs, files in os.walk(config_dir):
            # Skip backup directories
            dirs[:] = [d for d in dirs if d not in ["backups", "backup"] and not d.startswith(".")]

            for d in dirs:
                folder_path = os.path.join(root, d)
                folders.append(folder_path)

    return jsonify({"folders": sorted(folders)})


@bp.route("/api/files/create", methods=["POST"])
def api_create_file():
    """Stage a file creation (TRUE STAGING - doesn't create on disk yet).

    The file will be created when user clicks "Apply".
    """
    # S-04: Validate BEFORE acquiring lock to prevent lock on validation failure
    data = request.get_json() or {}
    file_path = data.get("path")

    if not file_path:
        return jsonify({"error": "path is required"}), 400

    # Ensure .cfg extension
    if not file_path.endswith(".cfg"):
        file_path += ".cfg"

    # Validate filename doesn't contain invalid characters (path separators in filename part)
    filename = os.path.basename(file_path)
    import re
    if re.search(r'[/\\:*?"<>|]', filename):
        return jsonify({"error": 'Filename cannot contain / \\ : * ? " < > |'}), 400

    # Security check - validate path is within config directory
    safe_result = is_safe_path(file_path)
    if not safe_result.success:
        return jsonify({"error": safe_result.error}), 400

    # Normalize the path
    config_path = get_config_path()
    if not os.path.isabs(file_path):
        file_path = os.path.normpath(os.path.join(config_path, file_path))
    else:
        file_path = os.path.normpath(file_path)

    # Check if file already exists
    if os.path.exists(file_path):
        return jsonify({"error": "File already exists"}), 400

    # Only acquire lock after all validation passes
    session_id = request.headers.get("X-Session-Id")
    success, error = ensure_staging_lock(session_id)
    if not success:
        return error

    # Stage the file creation instead of creating immediately
    sm = get_staging_manager()
    result = sm.stage_file_creation(file_path)

    return operation_response(result, {
        "path": file_path,
        "staged": True,
        "operationId": result.data,
        "message": "File creation staged. Use Apply to create on disk.",
    })


@bp.route("/api/folders", methods=["POST"])
def api_create_folder():
    """Stage a folder creation (TRUE STAGING - doesn't create on disk yet).

    Expects JSON:
    - path: Full path of the folder to create

    The folder will be created when user clicks "Apply".
    """
    # S-04: Validate BEFORE acquiring lock to prevent lock on validation failure
    data = request.get_json() or {}
    folder_path = data.get("path")

    if not folder_path:
        return jsonify({"error": "path required"}), 400

    # Validate folder name doesn't contain invalid characters
    folder_name = os.path.basename(folder_path.rstrip("/"))
    import re
    if re.search(r'[\\:*?"<>|]', folder_name):
        return jsonify({"error": 'Folder name cannot contain \\ : * ? " < > |'}), 400

    # Security: ensure path is within config directory
    config_path = get_config_path()
    abs_folder_path = os.path.abspath(folder_path)
    if not abs_folder_path.startswith(os.path.abspath(config_path)):
        return jsonify({"error": "Path must be within config directory"}), 400

    # Only acquire lock after all validation passes
    session_id = request.headers.get("X-Session-Id")
    success, error = ensure_staging_lock(session_id)
    if not success:
        return error

    # Stage the folder creation instead of creating immediately
    sm = get_staging_manager()
    result = sm.stage_folder_creation(abs_folder_path)

    if result.success:
        return jsonify({
            "success": True,
            "path": abs_folder_path,
            "staged": True,
            "operationId": result.data,
            "message": "Folder creation staged. Use Apply to create on disk.",
        })
    return jsonify({"error": result.error or "Failed to stage folder creation"}), 500


@bp.route("/api/files/move", methods=["POST"])
def api_move_file():
    """Stage a file move (TRUE STAGING - doesn't move on disk yet).

    Expects JSON:
    - sourcePath: Current file path
    - targetFolder: Destination folder path

    The file will be moved when user clicks "Apply".
    """
    data = request.get_json() or {}
    abs_source, abs_target_folder, err = _validate_move_paths(data)
    if err:
        return err

    if not os.path.isfile(abs_source):
        return jsonify({"error": "Source file does not exist"}), 404

    # Calculate target path
    file_name = os.path.basename(abs_source)
    target_path = os.path.join(abs_target_folder, file_name)

    # Only acquire lock after all validation passes
    session_id = request.headers.get("X-Session-Id")
    success, error = ensure_staging_lock(session_id)
    if not success:
        return error

    # Stage the file move instead of moving immediately
    sm = get_staging_manager()
    result = sm.stage_file_move(abs_source, target_path)

    if result.success:
        return jsonify({
            "success": True,
            "newPath": target_path,
            "staged": True,
            "operationId": result.data,
            "message": "File move staged. Use Apply to move on disk.",
        })
    return jsonify({"error": result.error or "Failed to stage file move"}), 500


@bp.route("/api/folders/move", methods=["POST"])
def api_move_folder():
    """Stage a folder move (TRUE STAGING - doesn't move on disk yet).

    Expects JSON:
    - sourcePath: Current folder path
    - targetFolder: Destination parent folder path

    The folder will be moved when user clicks "Apply".
    """
    data = request.get_json() or {}
    abs_source, abs_target_folder, err = _validate_move_paths(data)
    if err:
        return err

    if not os.path.isdir(abs_source):
        return jsonify({"error": "Source folder does not exist"}), 404

    # S-03: Prevent circular folder move (moving folder into itself or descendant)
    if abs_target_folder == abs_source or abs_target_folder.startswith(abs_source + os.sep):
        return jsonify({"error": "Cannot move folder into itself or a descendant"}), 400

    # Calculate target path
    folder_name = os.path.basename(abs_source)
    target_path = os.path.join(abs_target_folder, folder_name)

    # Only acquire lock after all validation passes
    session_id = request.headers.get("X-Session-Id")
    success, error = ensure_staging_lock(session_id)
    if not success:
        return error

    # Stage the folder move instead of moving immediately
    sm = get_staging_manager()
    result = sm.stage_folder_move(abs_source, target_path)

    if result.success:
        return jsonify({
            "success": True,
            "newPath": target_path,
            "staged": True,
            "operationId": result.data,
            "message": "Folder move staged. Use Apply to move on disk.",
        })
    return jsonify({"error": result.error or "Failed to stage folder move"}), 500


@bp.route("/api/files/relocate", methods=["POST"])
def api_relocate_file():
    """Move a config file to a different folder."""
    try:
        bm = get_backup_manager()
        data = request.get_json() or {}

        source_path, target_folder, err = _validate_relocate_paths(data)
        if err:
            return err

        # Calculate new path
        file_name = os.path.basename(source_path)
        new_path = os.path.join(target_folder, file_name)

        err = _validate_relocate_file_exists(source_path, new_path)
        if err:
            return err

        with get_parser_for_modification() as p:
            # Create backup before moving
            backup_path = bm.create_backup("relocate_file")

            # Create target folder if it doesn't exist
            os.makedirs(target_folder, exist_ok=True)

            # Move the file
            shutil.move(source_path, new_path)

            # Update all objects in parser to reflect new path
            for obj in p.objects:
                if obj.source_file == source_path:
                    obj.source_file = new_path

        # Reload config
        get_service().reload()

        return jsonify({
            "success": True,
            "old_path": source_path,
            "new_path": new_path,
            "backup": backup_path,
        })
    except (OSError, PermissionError, shutil.Error) as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to relocate file: {e!s}"}), 500


@bp.route("/api/folders/relocate", methods=["POST"])
def api_relocate_folder():
    """Move a folder to a different parent folder."""
    try:
        bm = get_backup_manager()
        data = request.get_json() or {}

        source_path, target_folder, err = _validate_relocate_paths(data)
        if err:
            return err

        print(f"[folder-relocate] source_path: {source_path}, target_folder: {target_folder}")

        # Calculate new path
        folder_name = os.path.basename(source_path)
        new_path = os.path.join(target_folder, folder_name)

        print(f"[folder-relocate] new_path: {new_path}")

        err = _validate_relocate_folder_exists(source_path, target_folder, new_path)
        if err:
            return err

        with get_parser_for_modification() as p:
            # Create backup before moving
            backup_path = bm.create_backup("relocate_folder")

            # Create target folder if it doesn't exist
            os.makedirs(target_folder, exist_ok=True)

            # Move the folder
            shutil.move(source_path, new_path)

            # Update all objects in parser to reflect new paths
            for obj in p.objects:
                if obj.source_file.startswith(source_path + os.sep):
                    # Replace the old folder path with the new one
                    obj.source_file = new_path + obj.source_file[len(source_path):]

        # Reload config
        get_service().reload()

        return jsonify({
            "success": True,
            "old_path": source_path,
            "new_path": new_path,
            "backup": backup_path,
        })
    except (OSError, PermissionError, shutil.Error) as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to relocate folder: {e!s}"}), 500


@bp.route("/api/files/<path:file_path>", methods=["DELETE"])
def api_delete_file(file_path):
    """Stage a file deletion (TRUE STAGING - doesn't delete from disk yet).

    The file_path is URL-encoded and relative to config directory.
    The file will be deleted when user clicks "Apply".
    """
    # S-04: Validate BEFORE acquiring lock to prevent lock on validation failure
    # Convert to absolute path
    config_path = get_config_path()
    abs_path = os.path.join(config_path, file_path)
    abs_path = os.path.abspath(abs_path)

    # Security: ensure path is within config directory
    if not abs_path.startswith(os.path.abspath(config_path)):
        return jsonify({"error": "Path must be within config directory"}), 400

    if not os.path.isfile(abs_path):
        return jsonify({"error": "File does not exist"}), 404

    # Only acquire lock after all validation passes
    session_id = request.headers.get("X-Session-Id")
    success, error = ensure_staging_lock(session_id)
    if not success:
        return error

    # Stage the file deletion instead of deleting immediately
    sm = get_staging_manager()
    result = sm.stage_file_deletion(abs_path)

    if result.success:
        return jsonify({
            "success": True,
            "staged": True,
            "operationId": result.data,
            "message": "File deletion staged. Use Apply to delete from disk.",
        })
    return jsonify({"error": result.error or "Failed to stage file deletion"}), 500


@bp.route("/api/folders/<path:folder_path>", methods=["DELETE"])
def api_delete_folder(folder_path):
    """Stage a folder deletion (TRUE STAGING - doesn't delete from disk yet).

    The folder_path is URL-encoded and relative to config directory.
    The folder will be deleted when user clicks "Apply".
    """
    # S-04: Validate BEFORE acquiring lock to prevent lock on validation failure
    # Convert to absolute path
    config_path = get_config_path()
    abs_path = os.path.join(config_path, folder_path)
    abs_path = os.path.abspath(abs_path)

    # Security: ensure path is within config directory
    if not abs_path.startswith(os.path.abspath(config_path)):
        return jsonify({"error": "Path must be within config directory"}), 400

    # Prevent deleting the config root
    if abs_path == os.path.abspath(config_path):
        return jsonify({"error": "Cannot delete config root directory"}), 400

    if not os.path.isdir(abs_path):
        return jsonify({"error": "Folder does not exist"}), 404

    # Only acquire lock after all validation passes
    session_id = request.headers.get("X-Session-Id")
    success, error = ensure_staging_lock(session_id)
    if not success:
        return error

    # Stage the folder deletion instead of deleting immediately
    sm = get_staging_manager()
    result = sm.stage_folder_deletion(abs_path)

    if result.success:
        return jsonify({
            "success": True,
            "staged": True,
            "operationId": result.data,
            "message": "Folder deletion staged. Use Apply to delete from disk.",
        })
    return jsonify({"error": result.error or "Failed to stage folder deletion"}), 500


@bp.route("/api/delete", methods=["POST"])
def api_delete_path():
    """Delete a file or folder."""
    data = request.get_json() or {}
    path = data.get("path")

    if not path:
        return jsonify({"error": "Path is required"}), 400

    config_path = get_config_path()

    # Resolve the path
    if not os.path.isabs(path):
        path = os.path.join(config_path, path)
    path = os.path.normpath(path)

    # Security check: path must be under config directory
    if not path.startswith(config_path + os.sep) and path != config_path:
        return jsonify({"error": "Path must be within config directory"}), 400

    # Don't allow deleting the config root
    if path == config_path:
        return jsonify({"error": "Cannot delete the config root directory"}), 400

    if not os.path.exists(path):
        return jsonify({"error": f"Path does not exist: {path}"}), 404

    try:
        bm = get_backup_manager()

        # Create backup before deleting
        backup_path = bm.create_backup("delete")

        is_dir = os.path.isdir(path)

        if is_dir:
            # Delete folder and all contents
            shutil.rmtree(path)
        else:
            # Delete single file
            os.remove(path)

        # Reload config
        get_service().reload()

        return jsonify({
            "success": True,
            "deleted_path": path,
            "was_directory": is_dir,
            "backup": backup_path,
        })
    except (OSError, PermissionError, shutil.Error) as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to delete: {e!s}"}), 500
