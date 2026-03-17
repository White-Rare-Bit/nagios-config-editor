"""Bulk operations routes for Nagios configuration editing."""

import logging
import os
import uuid

from flask import Blueprint, jsonify, request

from audit_service import log_audit
from .files import ensure_shadow_lock
from .helpers import get_audit_user_identity, format_audit_user, audit_file_path, get_service, get_shadow_manager

bp = Blueprint("bulk_ops", __name__)
logger = logging.getLogger("nagios_bulk_editor.bulk_ops")


@bp.route("/api/move-objects", methods=["POST"])
def api_move_objects():
    """Move multiple objects to a target file via shadow copy.

    Expects JSON:
    - stable_keys: Array of stable keys to move
    - target_file: Destination file path
    - after_line: (optional) Line number to insert after in target file
    """
    data = request.get_json() or {}
    stable_keys = data.get("stable_keys", [])
    target_file = data.get("target_file", "")
    after_line = data.get("after_line")

    if not stable_keys:
        return jsonify({"error": "stable_keys required"}), 400
    if not target_file:
        return jsonify({"error": "target_file required"}), 400

    session_id = request.headers.get("X-Session-Id")
    success, error = ensure_shadow_lock(session_id)
    if not success:
        return error

    service = get_service()
    sm = get_shadow_manager()

    # Resolve target file path into shadow directory
    from .objects import _resolve_target_file, _resolve_stable_key
    target_file = _resolve_target_file(target_file)

    # Find all objects to move
    to_move = []
    not_found = []
    skipped = 0
    for key in stable_keys:
        key = _resolve_stable_key(key)
        found = service.find_object_by_stable_key(key)
        if not found:
            not_found.append(key)
            continue
        _, obj = found
        # Skip same-file objects only when no position specified (no reorder)
        if not after_line and os.path.realpath(obj.source_file) == os.path.realpath(target_file):
            skipped += 1
            continue
        to_move.append(obj)

    if not to_move:
        return jsonify({
            "success": True,
            "moved": 0,
            "skipped": skipped,
            "not_found": len(not_found),
        })

    # Snapshot all affected files
    affected_files = set()
    rel_target = os.path.relpath(target_file, sm._config_dir)
    affected_files.add(rel_target)
    for obj in to_move:
        affected_files.add(os.path.relpath(obj.source_file, sm._config_dir))
    moved_keys = [
        f"{rel_target}|{obj.object_type}|{obj.get_display_name()}"
        for obj in to_move
    ]
    sm.snapshot_files(
        list(affected_files),
        f"bulk move {len(to_move)} objects",
        moved_keys=moved_keys,
    )

    # Capture source files before moves for audit (obj.source_file changes after move)
    obj_metadata = [(obj.object_type, obj.get_display_name(), obj.source_file) for obj in to_move]

    # Move each object using service.move_object (reloads after each)
    moved = 0
    errors = []
    insert_pos = after_line
    for obj in to_move:
        # Re-find by stable key since reloads may shift state
        from stable_keys import generate_stable_key_for_object
        key = generate_stable_key_for_object(obj)
        refound = service.find_object_by_stable_key(key)
        if not refound:
            errors.append(f"Lost object after reload: {key}")
            continue
        _, current_obj = refound
        result = service.move_object(
            current_obj.source_file, current_obj.line_number,
            target_file, current_obj.object_type,
            dict(current_obj.attributes),
            insert_line=insert_pos,
        )
        if result.success:
            moved += 1
            # Find the just-moved object so the next insert goes after it
            if insert_pos is not None:
                new_key = f"{target_file}|{current_obj.object_type}|{current_obj.get_display_name()}"
                placed = service.find_object_by_stable_key(new_key)
                insert_pos = placed[1].line_number if placed else None
        else:
            errors.append(result.error)

    if moved > 0:
        identity = get_audit_user_identity()
        user = format_audit_user(identity)
        txn = uuid.uuid4().hex[:8]
        for obj_type, obj_name, source_file in obj_metadata[:moved]:
            log_audit(
                action="object_move", user=user, txn=txn,
                type=obj_type, name=obj_name,
                from_file=audit_file_path(source_file),
                to_file=audit_file_path(target_file),
            )

    if errors:
        return jsonify({
            "success": False,
            "error": f"Moved {moved}/{len(to_move)}. Errors: {'; '.join(errors)}",
            "moved": moved,
            "skipped": skipped,
        }), 500

    return jsonify({
        "success": True,
        "moved": moved,
        "skipped": skipped,
        "not_found": len(not_found),
        "target_file": target_file,
    })


@bp.route("/api/batch-mutations", methods=["POST"])
def api_batch_mutations():
    """Execute multiple create/update mutations atomically (single undo).

    Expects JSON:
    - description: Human-readable description for undo history
    - operations: Array of operation objects:
        - {action: "update", stable_key: "...", attributes: {...}}
        - {action: "create", target_file: "...", object_type: "...", attributes: {...}}
    """
    data = request.get_json() or {}
    description = data.get("description", "batch operation")
    operations = data.get("operations", [])

    if not operations:
        return jsonify({"error": "operations required"}), 400

    session_id = request.headers.get("X-Session-Id")
    success, error = ensure_shadow_lock(session_id)
    if not success:
        return error

    service = get_service()
    sm = get_shadow_manager()

    from .objects import _resolve_stable_key, _resolve_target_file

    # Pre-resolve all operations and collect files to snapshot
    files_to_snapshot = set()
    resolved_ops = []
    for op in operations:
        action = op.get("action")
        if action == "update":
            stable_key = _resolve_stable_key(op.get("stable_key", ""))
            found = service.find_object_by_stable_key(stable_key)
            if not found:
                continue
            _, obj = found
            files_to_snapshot.add(os.path.relpath(obj.source_file, sm._config_dir))
            resolved_ops.append({"action": "update", "stable_key": stable_key, "attributes": op["attributes"]})
        elif action == "create":
            target_file = _resolve_target_file(op.get("target_file", ""))
            files_to_snapshot.add(os.path.relpath(target_file, sm._config_dir))
            resolved_ops.append({
                "action": "create",
                "target_file": target_file,
                "object_type": op["object_type"],
                "attributes": op["attributes"],
            })

    if not resolved_ops:
        return jsonify({"success": True, "completed": 0, "errors": []})

    # Single snapshot for all operations
    sm.snapshot_files(list(files_to_snapshot), description)

    # Execute each operation sequentially
    completed = 0
    errors = []
    for op in resolved_ops:
        if op["action"] == "update":
            found = service.find_object_by_stable_key(op["stable_key"])
            if not found:
                errors.append(f"Object not found: {op['stable_key']}")
                continue
            _, obj = found
            result = service.update_object(
                obj.source_file, obj.line_number, op["attributes"], obj.object_type,
            )
        elif op["action"] == "create":
            result = service.create_object(
                op["target_file"], op["object_type"], op["attributes"],
            )
        else:
            continue

        if result.success:
            completed += 1
        else:
            errors.append(result.error)

    return jsonify({
        "success": True,
        "completed": completed,
        "errors": errors if errors else None,
    })
