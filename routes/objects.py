"""Object CRUD routes — shadow copy architecture.

All mutations operate on the shadow copy (or original if no shadow).
"""

import os

from flask import Blueprint, jsonify, request

from .helpers import get_service, get_shadow_manager, operation_response
from .files import ensure_shadow_lock


def _resolve_stable_key(stable_key: str) -> str:
    """Remap the source_file in a stable key to the active config directory."""
    parts = stable_key.split("|")
    if len(parts) >= 3:
        parts[0] = _resolve_target_file(parts[0])
        return "|".join(parts)
    return stable_key


def _resolve_target_file(target_file: str) -> str:
    """Resolve target_file to be within the active config directory.

    On the first mutation, ensure_shadow_lock() creates the shadow and switches
    the service to it. But the frontend's request was built with the old path.
    This translates that path to the shadow directory.
    """
    from .helpers import get_server_config

    service = get_service()
    active_dir = os.path.abspath(service.config_path)

    abs_target = os.path.abspath(target_file)
    # Already within the active config dir — return as-is (preserve relative/absolute form)
    if abs_target.startswith(active_dir + os.sep) or abs_target == active_dir:
        return target_file

    # Remap: strip old config root prefix, join with active dir
    original_dir = os.path.abspath(get_server_config().nagios_config_path)
    if abs_target.startswith(original_dir + os.sep):
        rel = abs_target[len(original_dir) + 1:]
        return os.path.join(service.config_path, rel)

    return target_file

bp = Blueprint("objects", __name__)


@bp.route("/api/objects")
def api_objects():
    """Get objects, optionally filtered by type."""
    service = get_service()
    object_type = request.args.get("type")
    search = request.args.get("search", "")

    # Build list with global indices
    results = []
    for global_idx, obj in enumerate(service.get_objects()):
        if object_type and obj.object_type != object_type:
            continue
        if search and search.lower() not in obj.get_display_name().lower():
            continue
        obj_dict = obj.to_dict()
        obj_dict["global_index"] = global_idx
        results.append(obj_dict)

    return jsonify(results)


@bp.route("/api/objects/update", methods=["POST"])
def api_update_object():
    """Update an object's attributes in the shadow copy.

    Expects JSON:
    - stable_key: Object's stable key
    - attributes: New complete attributes dict
    """
    data = request.get_json() or {}
    stable_key = data.get("stable_key")
    new_attrs = data.get("attributes")

    if not stable_key:
        return jsonify({"error": "stable_key required"}), 400
    if not new_attrs:
        return jsonify({"error": "attributes required"}), 400

    session_id = request.headers.get("X-Session-Id")
    success, error = ensure_shadow_lock(session_id)
    if not success:
        return error

    service = get_service()
    sm = get_shadow_manager()
    stable_key = _resolve_stable_key(stable_key)

    # Snapshot the file before modifying
    found = service.find_object_by_stable_key(stable_key)
    if not found:
        return jsonify({"error": f"Object not found: {stable_key}"}), 404

    _, obj = found
    rel_path = os.path.relpath(obj.source_file, sm._config_dir)
    sm.snapshot_files([rel_path], f"edit {obj.object_type} {obj.get_display_name()}")

    result = service.update_object(
        obj.source_file, obj.line_number, new_attrs, obj.object_type,
    )
    return operation_response(result)


@bp.route("/api/objects/create", methods=["POST"])
def api_create_object():
    """Create a new object in the shadow copy.

    Expects JSON:
    - target_file: Path to the target file
    - object_type: Nagios object type
    - attributes: Attributes dict
    - after_line: (optional) Line number to insert after
    """
    data = request.get_json() or {}
    target_file = data.get("target_file")
    obj_type = data.get("object_type")
    attrs = data.get("attributes")
    after_line = data.get("after_line")

    if not target_file:
        return jsonify({"error": "target_file required"}), 400
    if not obj_type:
        return jsonify({"error": "object_type required"}), 400
    if not attrs:
        return jsonify({"error": "attributes required"}), 400

    session_id = request.headers.get("X-Session-Id")
    success, error = ensure_shadow_lock(session_id)
    if not success:
        return error

    sm = get_shadow_manager()
    service = get_service()

    # Remap target_file into shadow directory if needed
    target_file = _resolve_target_file(target_file)

    rel_path = os.path.relpath(target_file, sm._config_dir)
    sm.snapshot_files([rel_path], f"create {obj_type}")

    result = service.create_object(target_file, obj_type, attrs, after_block_line=after_line)
    return operation_response(result)


@bp.route("/api/objects/delete", methods=["POST"])
def api_delete_object():
    """Delete an object from the shadow copy.

    Expects JSON:
    - stable_key: Object's stable key
    """
    data = request.get_json() or {}
    stable_key = data.get("stable_key")

    if not stable_key:
        return jsonify({"error": "stable_key required"}), 400

    session_id = request.headers.get("X-Session-Id")
    success, error = ensure_shadow_lock(session_id)
    if not success:
        return error

    service = get_service()
    sm = get_shadow_manager()
    stable_key = _resolve_stable_key(stable_key)

    found = service.find_object_by_stable_key(stable_key)
    if not found:
        return jsonify({"error": f"Object not found: {stable_key}"}), 404

    _, obj = found
    rel_path = os.path.relpath(obj.source_file, sm._config_dir)
    sm.snapshot_files([rel_path], f"delete {obj.object_type} {obj.get_display_name()}")

    result = service.delete_object(obj.source_file, obj.line_number)
    return operation_response(result)


@bp.route("/api/objects/move", methods=["POST"])
def api_move_object():
    """Move an object to a new position (same-file reorder or cross-file).

    Expects JSON:
    - stable_key: Source object's stable key
    - target_file: Destination file path
    - after_line: (optional) Line number to insert after
    """
    data = request.get_json() or {}
    stable_key = data.get("stable_key")
    target_file = data.get("target_file")
    after_line = data.get("after_line")

    if not stable_key:
        return jsonify({"error": "stable_key required"}), 400
    if not target_file:
        return jsonify({"error": "target_file required"}), 400

    session_id = request.headers.get("X-Session-Id")
    success, error = ensure_shadow_lock(session_id)
    if not success:
        return error

    service = get_service()
    sm = get_shadow_manager()

    stable_key = _resolve_stable_key(stable_key)
    target_file = _resolve_target_file(target_file)

    found = service.find_object_by_stable_key(stable_key)
    if not found:
        return jsonify({"error": f"Object not found: {stable_key}"}), 404

    _, obj = found

    # Snapshot all affected files (source and target)
    files_to_snapshot = set()
    files_to_snapshot.add(os.path.relpath(obj.source_file, sm._config_dir))
    rel_target = os.path.relpath(target_file, sm._config_dir)
    files_to_snapshot.add(rel_target)
    moved_key = f"{rel_target}|{obj.object_type}|{obj.get_display_name()}"
    sm.snapshot_files(
        list(files_to_snapshot),
        f"move {obj.object_type} {obj.get_display_name()}",
        moved_keys=[moved_key],
    )

    result = service.move_object(
        obj.source_file, obj.line_number, target_file,
        obj.object_type, dict(obj.attributes),
        insert_line=after_line,
    )
    return operation_response(result)


@bp.route("/api/objects/delete-multiple", methods=["POST"])
def api_delete_multiple_objects():
    """Delete multiple objects from the shadow copy.

    Expects JSON:
    - stable_keys: Array of stable keys to delete
    """
    data = request.get_json() or {}
    stable_keys = data.get("stable_keys", [])

    if not stable_keys:
        return jsonify({"error": "stable_keys required"}), 400

    session_id = request.headers.get("X-Session-Id")
    success, error = ensure_shadow_lock(session_id)
    if not success:
        return error

    service = get_service()
    sm = get_shadow_manager()

    # Resolve all objects first, snapshot all affected files
    stable_keys = [_resolve_stable_key(k) for k in stable_keys]
    to_delete = []
    files_to_snapshot = set()
    for key in stable_keys:
        found = service.find_object_by_stable_key(key)
        if found:
            _, obj = found
            to_delete.append(obj)
            rel_path = os.path.relpath(obj.source_file, sm._config_dir)
            files_to_snapshot.add(rel_path)

    if not to_delete:
        return jsonify({"error": "No objects found for given keys"}), 404

    sm.snapshot_files(list(files_to_snapshot), f"delete {len(to_delete)} objects")

    # Delete in reverse line order within each file to maintain line numbers
    to_delete.sort(key=lambda o: (o.source_file, -o.line_number))

    errors = []
    deleted = 0
    for obj in to_delete:
        result = service.delete_object(obj.source_file, obj.line_number)
        if result.success:
            deleted += 1
        else:
            errors.append(result.error)

    if errors:
        return jsonify({
            "success": False,
            "error": f"Deleted {deleted}/{len(to_delete)} objects. Errors: {'; '.join(errors)}",
            "deleted": deleted,
        }), 500

    return jsonify({"success": True, "deleted": deleted})
