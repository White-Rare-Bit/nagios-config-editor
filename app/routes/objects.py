"""Object CRUD routes — shadow copy architecture.

All mutations go through staged_mutation() and operate on the shadow copy.
Paths and stable keys in requests and responses are logical (the original
config locations) and do not change when staging starts or ends.
"""

import uuid

from flask import Blueprint, jsonify, request

from ..stable_keys import generate_stable_key, stable_key_after_edit
from .helpers import get_service, operation_response
from .mutation import ApiError, staged_mutation

bp = Blueprint("objects", __name__)


def _name_from_attrs(attrs: dict) -> str:
    """Best-effort object name for audit lines (first attribute with 'name' in it)."""
    return attrs.get(next((k for k in attrs if "name" in k.lower()), ""), "")


def audit_attribute_changes(mutation, obj_type, obj_name, file_path, old_attrs, new_attrs, txn):
    """Write one object_edit audit line per changed attribute."""
    for field_name in old_attrs.keys() | new_attrs.keys():
        old_val = old_attrs.get(field_name, "")
        new_val = new_attrs.get(field_name, "")
        if old_val != new_val:
            mutation.audit(
                "object_edit", txn=txn,
                type=obj_type, name=obj_name,
                file=mutation.display(file_path), field=field_name,
                from_val=old_val, to_val=new_val,
            )


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
        raise ApiError("stable_key required")
    if not new_attrs:
        raise ApiError("attributes required")

    with staged_mutation() as m:
        obj = m.require(stable_key)
        m.snapshot([obj.source_file], f"edit {obj.object_type} {obj.get_display_name()}")

        # Capture old attributes before mutation for audit diffing
        old_attrs = dict(obj.attributes)

        result = m.service.update_object(
            obj.source_file, obj.line_number, new_attrs, obj.object_type,
            inline_comments=obj.inline_comments,
        )

        if result.success:
            audit_attribute_changes(
                m, obj.object_type, obj.get_display_name(), obj.source_file,
                old_attrs, new_attrs, uuid.uuid4().hex[:8],
            )

    if not result.success:
        return operation_response(result)
    # The edit can change the display name (e.g. a service's host), so tell
    # the client the key the object has now.
    return jsonify({
        "success": True,
        "stable_key": stable_key_after_edit(obj.source_file, obj.object_type, new_attrs),
    })


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
        raise ApiError("target_file required")
    if not obj_type:
        raise ApiError("object_type required")
    if not attrs:
        raise ApiError("attributes required")

    with staged_mutation() as m:
        target_file = m.logical(m.resolve(target_file))
        m.snapshot([target_file], f"create {obj_type}")

        result = m.service.create_object(target_file, obj_type, attrs, after_block_line=after_line)

        if result.success:
            m.audit(
                "object_create",
                type=obj_type, name=_name_from_attrs(attrs), file=m.display(target_file),
            )

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
        raise ApiError("stable_key required")

    with staged_mutation() as m:
        obj = m.require(stable_key)
        m.snapshot([obj.source_file], f"delete {obj.object_type} {obj.get_display_name()}")

        result = m.service.delete_object(obj.source_file, obj.line_number)

        if result.success:
            m.audit(
                "object_delete",
                type=obj.object_type, name=obj.get_display_name(),
                file=m.display(obj.source_file),
            )

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
        raise ApiError("stable_key required")
    if not target_file:
        raise ApiError("target_file required")

    with staged_mutation() as m:
        target_file = m.logical(m.resolve(target_file))
        obj = m.require(stable_key)

        # Snapshot all affected files (source and target)
        moved_key = generate_stable_key(target_file, obj.object_type, obj.get_display_name())
        m.snapshot(
            [obj.source_file, target_file],
            f"move {obj.object_type} {obj.get_display_name()}",
            moved_keys=[moved_key],
        )

        result = m.service.move_object(
            obj.source_file, obj.line_number, target_file,
            obj.object_type, dict(obj.attributes),
            insert_line=after_line,
        )

        if result.success:
            m.audit(
                "object_move",
                type=obj.object_type, name=obj.get_display_name(),
                from_file=m.display(obj.source_file),
                to_file=m.display(target_file),
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
        raise ApiError("stable_keys required")

    with staged_mutation() as m:
        # Resolve all objects first, snapshot all affected files
        to_delete = [obj for obj in (m.find(key) for key in stable_keys) if obj is not None]
        if not to_delete:
            raise ApiError("No objects found for given keys", 404)

        m.snapshot({obj.source_file for obj in to_delete}, f"delete {len(to_delete)} objects")

        # Delete in reverse line order within each file to maintain line numbers
        to_delete.sort(key=lambda o: (o.source_file, -o.line_number))

        errors = []
        deleted = []
        for obj in to_delete:
            result = m.service.delete_object(obj.source_file, obj.line_number)
            if result.success:
                deleted.append(obj)
            else:
                errors.append(result.error)

        if errors:
            raise ApiError(
                f"Deleted {len(deleted)}/{len(to_delete)} objects. Errors: {'; '.join(errors)}",
                500, deleted=len(deleted),
            )

        txn = uuid.uuid4().hex[:8]
        for obj in deleted:
            m.audit(
                "object_delete", txn=txn,
                type=obj.object_type, name=obj.get_display_name(),
                file=m.display(obj.source_file),
            )

    return jsonify({"success": True, "deleted": len(deleted)})
