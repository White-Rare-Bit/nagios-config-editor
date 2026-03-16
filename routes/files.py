"""File and folder management routes — shadow copy architecture.

All mutations operate directly on the shadow copy directory.
Read routes serve from shadow when active, otherwise from original.
"""

import logging
import os
import re
import shutil

from flask import Blueprint, jsonify, request

from file_operations import is_safe_path as file_ops_is_safe_path

from .helpers import (
    get_audit_user_identity,
    get_backup_manager,
    get_config_path,
    get_service,
    get_shadow_manager,
    operation_response,
)

bp = Blueprint("files", __name__)
logger = logging.getLogger("nagios_bulk_editor.files")


def is_safe_path(path: str, base_dir: str = None):
    """Wrapper that provides get_config_path() as default for base_dir.

    Returns:
        OperationResult with success=True if safe, success=False with error if unsafe.

    """
    if base_dir is None:
        base_dir = get_config_path()
    return file_ops_is_safe_path(path, base_dir)


def _get_active_config_path():
    """Return shadow config path if shadow is active, else original config path."""
    sm = get_shadow_manager()
    if sm.has_shadow():
        return sm._config_dir
    return get_config_path()


def ensure_shadow_lock(session_id: str) -> tuple:
    """Ensure session has shadow lock. Auto-creates shadow on first mutation.

    Returns (success, error_response). error_response is None on success.
    """
    if not session_id:
        return False, (jsonify({"error": "X-Session-Id header required"}), 400)

    sm = get_shadow_manager()

    if not sm.has_shadow():
        # First mutation — create shadow copy
        identity = get_audit_user_identity()
        result = sm.create_shadow(
            session_id,
            identity.get("userName", ""),
            identity.get("userEmail", ""),
        )
        if not result.success:
            return False, (jsonify({"error": result.error or "Failed to create shadow"}), 500)
        # Point service at shadow directory roots
        service = get_service()
        service.set_roots(cfg_dirs=sm.shadow_cfg_dirs, cfg_files=[])
        service.reload()
        return True, None

    if sm.can_modify(session_id):
        return True, None

    return False, (jsonify({
        "error": "Staging is locked by another user",
        "locked": True,
    }), 423)


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

    config_path = _get_active_config_path()
    abs_source = os.path.abspath(source_path)
    abs_target_folder = os.path.abspath(target_folder)

    if not abs_source.startswith(os.path.abspath(config_path)):
        return None, None, (jsonify({"error": "Source path must be within config directory"}), 400)
    if not abs_target_folder.startswith(os.path.abspath(config_path)):
        return None, None, (jsonify({"error": "Target folder must be within config directory"}), 400)

    return abs_source, abs_target_folder, None


# ═══════════════════════════════════════════════════════════════════════
# Read routes — serve from shadow when active
# ═══════════════════════════════════════════════════════════════════════


@bp.route("/api/files")
def api_files():
    """Get list of all .cfg files in the active config directory."""
    config_dir = _get_active_config_path()
    files = []

    if os.path.exists(config_dir):
        for root, dirs, filenames in os.walk(config_dir):
            dirs[:] = [d for d in dirs if d not in ("backups", "backup")]
            for filename in filenames:
                if filename.endswith(".cfg"):
                    files.append(os.path.join(root, filename))

    # Provide the original config dir name for display (shadow dir is named "config")
    from .helpers import get_server_config
    server_config = get_server_config()
    original_name = os.path.basename(server_config.paths.primary_dir) if server_config else ""
    return jsonify({
        "files": sorted(files),
        "config_path": config_dir,
        "config_display_name": original_name,
    })


@bp.route("/api/folders", methods=["GET"])
def api_list_folders():
    """List all folders in the active config directory."""
    config_dir = _get_active_config_path()
    folders = []

    if os.path.exists(config_dir):
        for root, dirs, _files in os.walk(config_dir):
            dirs[:] = [d for d in dirs if d not in ["backups", "backup"] and not d.startswith(".")]
            for d in dirs:
                folder_path = os.path.join(root, d)
                folders.append(folder_path)

    return jsonify({"folders": sorted(folders)})


# ═══════════════════════════════════════════════════════════════════════
# Mutation routes — operate on shadow copy
# ═══════════════════════════════════════════════════════════════════════


@bp.route("/api/files/create", methods=["POST"])
def api_create_file():
    """Create a file in the shadow copy directory."""
    data = request.get_json() or {}
    file_path = data.get("path")

    if not file_path:
        return jsonify({"error": "path is required"}), 400

    if not file_path.endswith(".cfg"):
        file_path += ".cfg"

    filename = os.path.basename(file_path)
    if re.search(r'[/\\:*?"<>|]', filename):
        return jsonify({"error": 'Filename cannot contain / \\ : * ? " < > |'}), 400

    safe_result = is_safe_path(file_path)
    if not safe_result.success:
        return jsonify({"error": safe_result.error}), 400

    # Acquire shadow lock
    session_id = request.headers.get("X-Session-Id")
    success, error = ensure_shadow_lock(session_id)
    if not success:
        return error

    sm = get_shadow_manager()
    config_path = sm._config_dir

    # Normalize path into shadow dir
    if not os.path.isabs(file_path):
        file_path = os.path.normpath(os.path.join(config_path, file_path))
    else:
        # Remap from original config to shadow
        orig_config = get_config_path()
        if file_path.startswith(orig_config):
            rel = os.path.relpath(file_path, orig_config)
            file_path = os.path.join(config_path, rel)
        file_path = os.path.normpath(file_path)

    if os.path.exists(file_path):
        return jsonify({"error": "File already exists"}), 400

    # Snapshot, then create the file directly
    rel_path = os.path.relpath(file_path, config_path)
    sm.snapshot_files([rel_path], f"create file {rel_path}")

    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w") as f:
        f.write("")

    # Reload parser to pick up new file
    get_service().reload()

    return jsonify({
        "success": True,
        "path": file_path,
        "message": "File created in shadow copy.",
    })


@bp.route("/api/folders", methods=["POST"])
def api_create_folder():
    """Create a folder in the shadow copy directory."""
    data = request.get_json() or {}
    folder_path = data.get("path")

    if not folder_path:
        return jsonify({"error": "path required"}), 400

    folder_name = os.path.basename(folder_path.rstrip("/"))
    if re.search(r'[\\:*?"<>|]', folder_name):
        return jsonify({"error": 'Folder name cannot contain \\ : * ? " < > |'}), 400

    # Acquire shadow lock
    session_id = request.headers.get("X-Session-Id")
    success, error = ensure_shadow_lock(session_id)
    if not success:
        return error

    sm = get_shadow_manager()
    config_path = sm._config_dir

    # Normalize path into shadow dir
    abs_folder_path = os.path.abspath(folder_path)
    orig_config = get_config_path()
    if abs_folder_path.startswith(os.path.abspath(orig_config)):
        rel = os.path.relpath(abs_folder_path, orig_config)
        abs_folder_path = os.path.join(config_path, rel)

    if not abs_folder_path.startswith(os.path.abspath(config_path)):
        return jsonify({"error": "Path must be within config directory"}), 400

    os.makedirs(abs_folder_path, exist_ok=True)

    return jsonify({
        "success": True,
        "path": abs_folder_path,
        "message": "Folder created in shadow copy.",
    })


@bp.route("/api/files/move", methods=["POST"])
def api_move_file():
    """Move a file within the shadow copy directory."""
    session_id = request.headers.get("X-Session-Id")
    success, error = ensure_shadow_lock(session_id)
    if not success:
        return error

    data = request.get_json() or {}
    abs_source, abs_target_folder, err = _validate_move_paths(data)
    if err:
        return err

    if not os.path.isfile(abs_source):
        return jsonify({"error": "Source file does not exist"}), 404

    file_name = os.path.basename(abs_source)
    target_path = os.path.join(abs_target_folder, file_name)

    sm = get_shadow_manager()
    config_path = sm._config_dir

    # Snapshot affected files before move
    rel_source = os.path.relpath(abs_source, config_path)
    rel_target = os.path.relpath(target_path, config_path)
    sm.snapshot_files([rel_source, rel_target], f"move file {rel_source}")

    os.makedirs(abs_target_folder, exist_ok=True)
    shutil.move(abs_source, target_path)

    get_service().reload()

    return jsonify({
        "success": True,
        "newPath": target_path,
        "message": "File moved in shadow copy.",
    })


@bp.route("/api/folders/move", methods=["POST"])
def api_move_folder():
    """Move a folder within the shadow copy directory."""
    session_id = request.headers.get("X-Session-Id")
    success, error = ensure_shadow_lock(session_id)
    if not success:
        return error

    data = request.get_json() or {}
    abs_source, abs_target_folder, err = _validate_move_paths(data)
    if err:
        return err

    if not os.path.isdir(abs_source):
        return jsonify({"error": "Source folder does not exist"}), 404

    if abs_target_folder == abs_source or abs_target_folder.startswith(abs_source + os.sep):
        return jsonify({"error": "Cannot move folder into itself or a descendant"}), 400

    folder_name = os.path.basename(abs_source)
    target_path = os.path.join(abs_target_folder, folder_name)

    sm = get_shadow_manager()
    config_path = sm._config_dir

    # Snapshot all .cfg files in the source folder
    files_to_snapshot = []
    for root, _dirs, filenames in os.walk(abs_source):
        for fn in filenames:
            if fn.endswith(".cfg"):
                abs_f = os.path.join(root, fn)
                files_to_snapshot.append(os.path.relpath(abs_f, config_path))
    rel_source = os.path.relpath(abs_source, config_path)
    sm.snapshot_files(files_to_snapshot, f"move folder {rel_source}")

    os.makedirs(abs_target_folder, exist_ok=True)
    shutil.move(abs_source, target_path)

    get_service().reload()

    return jsonify({
        "success": True,
        "newPath": target_path,
        "message": "Folder moved in shadow copy.",
    })


@bp.route("/api/files/<path:file_path>", methods=["DELETE"])
def api_delete_file(file_path):
    """Delete a file from the shadow copy directory."""
    session_id = request.headers.get("X-Session-Id")
    success, error = ensure_shadow_lock(session_id)
    if not success:
        return error

    sm = get_shadow_manager()
    config_path = sm._config_dir
    abs_path = os.path.abspath(os.path.join(config_path, file_path))

    if not abs_path.startswith(os.path.abspath(config_path)):
        return jsonify({"error": "Path must be within config directory"}), 400

    if not os.path.isfile(abs_path):
        return jsonify({"error": "File does not exist"}), 404

    rel_path = os.path.relpath(abs_path, config_path)
    sm.snapshot_files([rel_path], f"delete file {rel_path}")

    os.remove(abs_path)

    get_service().reload()

    return jsonify({
        "success": True,
        "message": "File deleted from shadow copy.",
    })


@bp.route("/api/folders/<path:folder_path>", methods=["DELETE"])
def api_delete_folder(folder_path):
    """Delete a folder from the shadow copy directory."""
    session_id = request.headers.get("X-Session-Id")
    success, error = ensure_shadow_lock(session_id)
    if not success:
        return error

    sm = get_shadow_manager()
    config_path = sm._config_dir
    abs_path = os.path.abspath(os.path.join(config_path, folder_path))

    if not abs_path.startswith(os.path.abspath(config_path)):
        return jsonify({"error": "Path must be within config directory"}), 400

    if abs_path == os.path.abspath(config_path):
        return jsonify({"error": "Cannot delete config root directory"}), 400

    if not os.path.isdir(abs_path):
        return jsonify({"error": "Folder does not exist"}), 404

    # Snapshot all .cfg files in the folder
    files_to_snapshot = []
    for root, _dirs, filenames in os.walk(abs_path):
        for fn in filenames:
            if fn.endswith(".cfg"):
                abs_f = os.path.join(root, fn)
                files_to_snapshot.append(os.path.relpath(abs_f, config_path))
    rel_path = os.path.relpath(abs_path, config_path)
    sm.snapshot_files(files_to_snapshot, f"delete folder {rel_path}")

    shutil.rmtree(abs_path)

    get_service().reload()

    return jsonify({
        "success": True,
        "message": "Folder deleted from shadow copy.",
    })
