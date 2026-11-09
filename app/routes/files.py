"""File and folder management routes — shadow copy architecture.

All mutations go through staged_mutation() and operate on the shadow copy.
Read routes list the shadow when one exists, otherwise the original config.
Either way every path in a request or response is a logical path (the
original config location), so paths do not change when staging starts.
"""

import logging
import os
import re
import shutil

from flask import Blueprint, jsonify, request

from ..config_discovery import PROTECTED_FILENAMES
from .helpers import get_service
from .mutation import ApiError, staged_mutation

bp = Blueprint("files", __name__)
logger = logging.getLogger("nagios_bulk_editor.files")

_SKIPPED_DIRS = ("backups", "backup")


def _walk_roots(skip_hidden_dirs=False):
    """Walk every config root where it currently lives.

    Yields (logical_dir, dirnames, filenames): the directory's logical path
    with the names found in its physical location.
    """
    for physical_root, logical_root in get_service().active_dirs:
        if not os.path.exists(physical_root):
            continue
        for current, dirs, filenames in os.walk(physical_root):
            dirs[:] = [
                d for d in dirs
                if d not in _SKIPPED_DIRS and not (skip_hidden_dirs and d.startswith("."))
            ]
            rel = os.path.relpath(current, physical_root)
            logical_dir = logical_root if rel == "." else os.path.join(logical_root, rel)
            yield logical_dir, dirs, filenames


def _cfg_files_under(physical_dir):
    """Physical paths of all .cfg files below a directory."""
    return [
        os.path.join(current, name)
        for current, _dirs, filenames in os.walk(physical_dir)
        for name in filenames if name.endswith(".cfg")
    ]


def _move_paths(m, data):
    """Validate sourcePath and targetFolder. Returns their logical paths."""
    source_path = data.get("sourcePath")
    target_folder = data.get("targetFolder")

    if not source_path:
        raise ApiError("sourcePath required")
    if not target_folder:
        raise ApiError("targetFolder required")

    if m.sm.composite_path(m.resolve(source_path)) is None:
        raise ApiError("Source path must be within config directory")
    if m.sm.composite_path(m.resolve(target_folder)) is None:
        raise ApiError("Target folder must be within config directory")

    return m.logical(m.resolve(source_path)), m.logical(m.resolve(target_folder))


# ═══════════════════════════════════════════════════════════════════════
# Read routes — list the shadow when active, report logical paths
# ═══════════════════════════════════════════════════════════════════════


@bp.route("/api/files")
def api_files():
    """Get list of all .cfg files across all config roots.

    Lists the active config (shadow when staging, original otherwise) and
    reports logical paths, along with the list of config roots.
    """
    files = [
        os.path.join(logical_dir, filename)
        for logical_dir, _dirs, filenames in _walk_roots()
        for filename in filenames
        if filename.endswith(".cfg") and filename not in PROTECTED_FILENAMES
    ]

    return jsonify({
        "files": sorted(files),
        "roots": get_service().cfg_dirs,
    })


@bp.route("/api/folders", methods=["GET"])
def api_list_folders():
    """List all folders across all config roots."""
    folders = [
        os.path.join(logical_dir, d)
        for logical_dir, dirs, _filenames in _walk_roots(skip_hidden_dirs=True)
        for d in dirs
    ]

    return jsonify({
        "folders": sorted(folders),
        "roots": get_service().cfg_dirs,
    })


# ═══════════════════════════════════════════════════════════════════════
# Mutation routes — operate on shadow copy
# ═══════════════════════════════════════════════════════════════════════


@bp.route("/api/files/create", methods=["POST"])
def api_create_file():
    """Create a file in the shadow copy directory.

    ``path`` is absolute, or relative to the primary config root.
    """
    data = request.get_json() or {}
    file_path = data.get("path")

    if not file_path:
        raise ApiError("path is required")

    if not file_path.endswith(".cfg"):
        file_path += ".cfg"

    filename = os.path.basename(file_path)
    if re.search(r'[/\\:*?"<>|]', filename):
        raise ApiError('Filename cannot contain / \\ : * ? " < > |')

    with staged_mutation() as m:
        logical = m.logical(m.resolve(file_path))
        physical = m.physical(logical)

        if os.path.exists(physical):
            raise ApiError("File already exists")

        # Snapshot, then create the file directly
        m.snapshot([logical], f"create file {m.display(logical)}")

        os.makedirs(os.path.dirname(physical), exist_ok=True)
        with open(physical, "w") as f:
            f.write("")

        # Reload parser to pick up new file
        m.files_changed()
        m.audit("file_create", file=m.display(logical))

    return jsonify({
        "success": True,
        "path": logical,
        "message": "File created in shadow copy.",
    })


@bp.route("/api/folders", methods=["POST"])
def api_create_folder():
    """Create a folder in the shadow copy directory.

    ``path`` is absolute, or relative to the primary config root.
    """
    data = request.get_json() or {}
    folder_path = data.get("path")

    if not folder_path:
        raise ApiError("path required")

    folder_name = os.path.basename(folder_path.rstrip("/"))
    if re.search(r'[\\:*?"<>|]', folder_name):
        raise ApiError('Folder name cannot contain \\ : * ? " < > |')

    with staged_mutation() as m:
        logical = m.logical(m.resolve(folder_path))
        physical = m.physical(logical)

        if os.path.isdir(physical):
            raise ApiError("Folder already exists")

        # Snapshot before creation so undo can remove it
        m.snapshot([], f"create folder {m.display(logical)}", dirs=[logical])

        os.makedirs(physical, exist_ok=True)

        m.files_changed()
        m.audit("folder_create", folder=m.display(logical))

    return jsonify({
        "success": True,
        "path": logical,
        "message": "Folder created in shadow copy.",
    })


@bp.route("/api/files/move", methods=["POST"])
def api_move_file():
    """Move a file within the shadow copy directory."""
    data = request.get_json() or {}

    with staged_mutation() as m:
        source, target_folder = _move_paths(m, data)
        physical_source = m.physical(source)

        if not os.path.isfile(physical_source):
            raise ApiError("Source file does not exist", 404)

        target = os.path.join(target_folder, os.path.basename(source))
        physical_target = m.physical(target)

        # Snapshot affected files before move
        m.snapshot([source, target], f"move file {m.display(source)}")

        os.makedirs(os.path.dirname(physical_target), exist_ok=True)
        shutil.move(physical_source, physical_target)

        m.files_changed()
        m.audit("file_move", from_file=m.display(source), to_file=m.display(target))

    return jsonify({
        "success": True,
        "newPath": target,
        "message": "File moved in shadow copy.",
    })


@bp.route("/api/folders/move", methods=["POST"])
def api_move_folder():
    """Move a folder within the shadow copy directory."""
    data = request.get_json() or {}

    with staged_mutation() as m:
        source, target_folder = _move_paths(m, data)
        physical_source = m.physical(source)

        if not os.path.isdir(physical_source):
            raise ApiError("Source folder does not exist", 404)

        if target_folder == source or target_folder.startswith(source + os.sep):
            raise ApiError("Cannot move folder into itself or a descendant")

        target = os.path.join(target_folder, os.path.basename(source))
        physical_target = m.physical(target)

        # Snapshot every .cfg file at both its old and its new location, and
        # every directory the move will create, so undo puts the files back
        # AND removes the moved copies.
        files_to_snapshot = []
        for physical_file in _cfg_files_under(physical_source):
            rel = os.path.relpath(physical_file, physical_source)
            files_to_snapshot.append(os.path.join(source, rel))
            files_to_snapshot.append(os.path.join(target, rel))
        new_dirs = [
            os.path.join(target, os.path.relpath(os.path.join(current, d), physical_source))
            for current, dirs, _filenames in os.walk(physical_source)
            for d in dirs
        ]
        # Deepest first: undo removes directories in this order, and can only
        # remove empty ones.
        new_dirs.sort(key=lambda d: d.count(os.sep), reverse=True)
        m.snapshot(files_to_snapshot, f"move folder {m.display(source)}", dirs=[*new_dirs, target])

        os.makedirs(os.path.dirname(physical_target), exist_ok=True)
        shutil.move(physical_source, physical_target)

        m.files_changed()
        m.audit("folder_move", from_folder=m.display(source), to_folder=m.display(target))

    return jsonify({
        "success": True,
        "newPath": target,
        "message": "Folder moved in shadow copy.",
    })


@bp.route("/api/files/<path:file_path>", methods=["DELETE"])
def api_delete_file(file_path):
    """Delete a file from the shadow copy directory.

    The path is relative to the primary config root, or an absolute path
    (whose leading slash the URL cannot carry) inside any config root.
    """
    with staged_mutation() as m:
        logical = m.logical(m.resolve(file_path))
        physical = m.physical(logical)

        if not os.path.isfile(physical):
            raise ApiError("File does not exist", 404)

        m.snapshot([logical], f"delete file {m.display(logical)}")

        os.remove(physical)

        m.files_changed()
        m.audit("file_delete", file=m.display(logical))

    return jsonify({
        "success": True,
        "message": "File deleted from shadow copy.",
    })


@bp.route("/api/folders/<path:folder_path>", methods=["DELETE"])
def api_delete_folder(folder_path):
    """Delete a folder from the shadow copy directory.

    The path is relative to the primary config root, or an absolute path
    (whose leading slash the URL cannot carry) inside any config root.
    """
    with staged_mutation() as m:
        logical = m.logical(m.resolve(folder_path))
        physical = m.physical(logical)

        if logical in m.service.cfg_dirs:
            raise ApiError("Cannot delete config root directory")

        if not os.path.isdir(physical):
            raise ApiError("Folder does not exist", 404)

        # Snapshot all .cfg files in the folder
        files_to_snapshot = [
            os.path.join(logical, os.path.relpath(physical_file, physical))
            for physical_file in _cfg_files_under(physical)
        ]
        m.snapshot(files_to_snapshot, f"delete folder {m.display(logical)}")

        shutil.rmtree(physical)

        m.files_changed()
        m.audit("folder_delete", folder=m.display(logical))

    return jsonify({
        "success": True,
        "message": "Folder deleted from shadow copy.",
    })
