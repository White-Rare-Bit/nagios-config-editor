"""Bulk operations routes for Nagios configuration editing."""

import logging
import os
import uuid

from flask import Blueprint, jsonify, request

from ..stable_keys import (
    changed_keys,
    generate_stable_key,
    generate_stable_key_for_object,
    stable_key_after_edit,
)
from .mutation import ApiError, staged_mutation
from .objects import _name_from_attrs, audit_attribute_changes

bp = Blueprint("bulk_ops", __name__)
logger = logging.getLogger(__name__)


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
        raise ApiError("stable_keys required")
    if not target_file:
        raise ApiError("target_file required")

    with staged_mutation() as m:
        service = m.service
        target_file = m.logical(m.resolve(target_file))

        # Find all objects to move
        to_move = []
        not_found = []
        skipped = 0
        for key in stable_keys:
            obj = m.find(key)
            if obj is None:
                not_found.append(key)
                continue
            # Skip same-file objects only when no position specified (no reorder)
            if not after_line and os.path.normpath(obj.source_file) == target_file:
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
        moved_keys = [
            generate_stable_key(target_file, obj.object_type, obj.get_display_name())
            for obj in to_move
        ]
        m.snapshot(
            {target_file, *(obj.source_file for obj in to_move)},
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
            key = generate_stable_key_for_object(obj)
            current_obj = m.find(key)
            if current_obj is None:
                errors.append(f"Lost object after reload: {key}")
                continue
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
                    placed = m.find(generate_stable_key(
                        target_file, current_obj.object_type, current_obj.get_display_name(),
                    ))
                    insert_pos = placed.line_number if placed else None
            else:
                errors.append(result.error)

        if moved > 0:
            txn = uuid.uuid4().hex[:8]
            for obj_type, obj_name, source_file in obj_metadata[:moved]:
                m.audit(
                    "object_move", txn=txn,
                    type=obj_type, name=obj_name,
                    from_file=m.display(source_file),
                    to_file=m.display(target_file),
                )

        if errors:
            raise ApiError(
                f"Moved {moved}/{len(to_move)}. Errors: {'; '.join(errors)}",
                500, moved=moved, skipped=skipped,
            )

    return jsonify({
        "success": True,
        "moved": moved,
        "skipped": skipped,
        "not_found": len(not_found),
        "target_file": target_file,
    })


def _validate_operations(operations) -> None:
    """Refuse a malformed batch (400) before anything is staged.

    Every operation must be applied: dropping one would shift ``keys``
    against the request order. The error names the operation's index.
    """
    if not isinstance(operations, list) or not operations:
        raise ApiError("operations required")
    for i, op in enumerate(operations):
        if not isinstance(op, dict):
            raise ApiError(f"operation {i}: must be an object")
        action = op.get("action")
        if action not in ("update", "create"):
            raise ApiError(f"operation {i}: unknown action {action!r}")
        if not isinstance(op.get("attributes"), dict):
            raise ApiError(f"operation {i}: attributes required")
        if action == "update" and not op.get("stable_key"):
            raise ApiError(f"operation {i}: update needs a stable_key")
        if action == "create" and not (op.get("target_file") and op.get("object_type")):
            raise ApiError(f"operation {i}: create needs target_file and object_type")


@bp.route("/api/batch-mutations", methods=["POST"])
def api_batch_mutations():
    """Execute multiple create/update mutations atomically (single undo).

    Expects JSON:
    - description: Human-readable description for undo history
    - operations: Array of operation objects:
        - {action: "update", stable_key: "...", attributes: {...}}
        - {action: "create", target_file: "...", object_type: "...", attributes: {...}}

    A malformed operation is refused (400, naming its index). Returns keys
    (each object's stable key after the batch, in request order) and
    key_changes ({old_key: new_key} for each updated object whose key changed).
    """
    data = request.get_json() or {}
    description = data.get("description", "batch operation")
    operations = data.get("operations", [])
    _validate_operations(operations)

    with staged_mutation() as m:
        service = m.service

        # Pre-resolve all operations and collect files to snapshot
        files_to_snapshot = set()
        resolved_ops = []
        for op in operations:
            action = op.get("action")
            if action == "update":
                stable_key = op.get("stable_key", "")
                obj = m.find(stable_key)
                if obj is None:
                    raise ApiError(f"Object not found: {stable_key}", 409)
                files_to_snapshot.add(obj.source_file)
                resolved_ops.append({
                    "action": "update", "stable_key": stable_key, "attributes": op["attributes"],
                    "old_attrs": dict(obj.attributes),
                    "obj_type": obj.object_type,
                    "obj_name": obj.get_display_name(),
                    "obj_file": obj.source_file,
                })
            else:
                target_file = m.logical(m.resolve(op.get("target_file", "")))
                files_to_snapshot.add(target_file)
                resolved_ops.append({
                    "action": "create",
                    "target_file": target_file,
                    "object_type": op["object_type"],
                    "attributes": op["attributes"],
                    "name": _name_from_attrs(op["attributes"]),
                })

        # Single snapshot for all operations
        m.snapshot(files_to_snapshot, description)

        # Execute each operation sequentially
        completed = 0
        errors = []
        succeeded = []
        keys = []
        key_changes = {}
        for op in resolved_ops:
            if op["action"] == "update":
                obj = m.find(op["stable_key"])
                if obj is None:
                    errors.append(f"Object not found: {op['stable_key']}")
                    continue
                result = service.update_object(
                    obj.source_file, obj.line_number, op["attributes"], obj.object_type,
                    inline_comments=obj.inline_comments,
                )
                key_file, key_type = obj.source_file, obj.object_type
            else:
                result = service.create_object(
                    op["target_file"], op["object_type"], op["attributes"],
                )
                key_file, key_type = op["target_file"], op["object_type"]

            if result.success:
                completed += 1
                succeeded.append(op)
                keys.append(stable_key_after_edit(key_file, key_type, op["attributes"]))
                if op["action"] == "update":
                    # An edit of host_name/hostgroup_name changes a service's key.
                    key_changes.update(changed_keys([(obj, keys[-1])]))
            else:
                errors.append(result.error)

        # All-or-nothing: one failure undoes the whole batch (and removes a
        # shadow this request created), so the client never sees a half-applied
        # batch. 409: the batch conflicts with the current config state.
        if errors:
            outcome = {
                "description": description,
                "failed": len(errors), "total": len(resolved_ops),
            }
            try:
                m.rollback()
            except ApiError as exc:
                # Undo failed: the shadow may be half-written. Audit that too.
                m.audit("batch_rollback", rollback_failed=exc.message, **outcome)
                raise
            m.audit("batch_rollback", **outcome)
            raise ApiError(
                f"{len(errors)} of {len(resolved_ops)} operations failed: {'; '.join(errors)}",
                409, errors=errors,
            )

        # Audit all succeeded operations
        txn = uuid.uuid4().hex[:8]
        for op in succeeded:
            if op["action"] == "update":
                audit_attribute_changes(
                    m, op["obj_type"], op["obj_name"], op["obj_file"],
                    op["old_attrs"], op["attributes"], txn,
                )
            else:
                m.audit(
                    "object_create", txn=txn,
                    type=op["object_type"], name=op.get("name", ""),
                    file=m.display(op["target_file"]),
                )

    return jsonify({
        "success": True,
        "completed": completed,
        "errors": None,
        "keys": keys,
        "key_changes": key_changes,
    })
