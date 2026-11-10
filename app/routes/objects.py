"""Object CRUD routes — shadow copy architecture.

All mutations go through staged_mutation() and operate on the shadow copy.
Paths and stable keys in requests and responses are logical (the original
config locations) and do not change when staging starts or ends.
"""

import uuid

from flask import Blueprint, jsonify, request

from ..nagios_model import NAME_FIELDS, RENAMEABLE_TYPES, is_template_object
from ..references import name_field, reference_edits, referenced_by
from ..stable_keys import (
    changed_keys,
    generate_stable_key,
    generate_stable_key_for_object,
    stable_key_after_edit,
)
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


def _not_renameable(obj) -> str:
    """Why rename refuses this object (``name_field`` returned None)."""
    if is_template_object(obj):
        return f"{obj.object_type} template has no name to rename"
    if obj.object_type not in RENAMEABLE_TYPES:
        return f"{obj.object_type} objects have no name of their own"
    return (
        f"{obj.object_type} {obj.get_display_name()} has no "
        f"{NAME_FIELDS[obj.object_type]} to rename"
    )


def _parse_renames(data: dict) -> list[tuple[str, str]]:
    """Validate a rename request body into [(stable_key, new_name)]."""
    renames = data.get("renames")
    if not isinstance(renames, list) or not renames:
        raise ApiError("renames required")
    parsed = []
    for entry in renames:
        if not isinstance(entry, dict) or not entry.get("stable_key"):
            raise ApiError("each rename needs a stable_key")
        new_name = str(entry.get("new_name") or "").strip()
        if not new_name:
            raise ApiError("new_name required")
        # A comma would split the name in every list that refers to it, and
        # a line break would end the attribute line in the config file.
        if "," in new_name or any(ord(c) < 32 for c in new_name):  # noqa: PLR2004
            raise ApiError(f"Invalid name: {new_name!r}")
        parsed.append((entry["stable_key"], new_name))
    if len({key for key, _ in parsed}) != len(parsed):
        raise ApiError("Each object can be renamed only once per request")
    return parsed


@bp.route("/api/objects/rename", methods=["POST"])
def api_rename_objects():
    """Rename objects and, optionally, the references to them, as one undo step.

    Expects JSON:
    - renames: [{stable_key, new_name}, ...]
    - update_references: (JSON bool, default true) also rewrite references of
      the same type (see app/references.py). Renamed objects get the
      reference edits of each other's renames too (a host's ``parents``, a
      service's ``host_name``), merged into their one write.

    A template is renamed by its ``name`` (references: ``use`` on objects of
    the same type); a registered object by its NAME_FIELDS field, only for
    RENAMEABLE_TYPES. Others have no name of their own (400).

    Returns keys (each renamed object's stable key after the request, in
    request order), key_changes ({old_key: new_key} for every written object
    whose stable key changed, including objects that only had a reference
    rewritten) and references_updated (number of objects whose references
    were changed). If any write fails, everything this request changed is
    undone (409).
    """
    data = request.get_json() or {}
    requested = _parse_renames(data)
    update_references = data.get("update_references", True)
    if not isinstance(update_references, bool):
        raise ApiError("update_references must be true or false")

    with staged_mutation() as m:
        targets = []  # every requested object, in request order
        renames = []  # (obj, field, old, new) for names that change
        for key, new_name in requested:
            obj = m.require(key)
            field = name_field(obj)
            if field is None:
                raise ApiError(_not_renameable(obj))
            targets.append(obj)
            old_name = obj.attributes[field].strip()
            if new_name != old_name:
                renames.append((obj, field, old_name, new_name))

        if not renames:
            return jsonify({
                "success": True, "references_updated": 0, "key_changes": {},
                "keys": [generate_stable_key_for_object(obj) for obj in targets],
            })

        ref_edits = []
        if update_references:
            ref_edits = reference_edits(
                m.service.get_objects(), [(obj, new) for obj, _, _, new in renames],
            )

        # One write per object: reference edits first, then the rename itself
        # (the object's own name field), merged for an object that has both.
        new_attrs = {id(obj): (obj, attrs) for obj, attrs in ref_edits}
        for obj, field, _, new in renames:
            attrs = new_attrs.get(id(obj), (obj, obj.attributes))[1]
            new_attrs[id(obj)] = (obj, {**attrs, field: new})
        writes = list(new_attrs.values())
        keys = [
            stable_key_after_edit(
                obj.source_file, obj.object_type,
                new_attrs.get(id(obj), (obj, obj.attributes))[1],
            )
            for obj in targets
        ]
        # Every written object whose key changes, not only the renamed ones:
        # a service's key names its hosts/hostgroups, so renaming a hostgroup
        # it refers to changes its key too (UI_REVIEW bug 6).
        key_changes = changed_keys(
            (obj, stable_key_after_edit(obj.source_file, obj.object_type, attrs))
            for obj, attrs in writes
        )

        if len(renames) == 1:
            obj, _, old_name, new_name = renames[0]
            description = f"rename {obj.object_type} {old_name} to {new_name}"
        else:
            description = f"rename {len(renames)} objects"
        m.snapshot({obj.source_file for obj, _ in writes}, description)

        # Bottom-up within each file, so a block that changes length does not
        # move the blocks still to be written (their line numbers are from
        # before the first write).
        writes.sort(key=lambda w: (w[0].source_file, -w[0].line_number))
        errors = []
        for obj, attrs in writes:
            result = m.service.update_object(
                obj.source_file, obj.line_number, attrs, obj.object_type,
                inline_comments=obj.inline_comments,
            )
            if not result.success:
                errors.append(f"{obj.object_type} {obj.get_display_name()}: {result.error}")
                break

        # All-or-nothing, like /api/batch-mutations: undo everything this
        # request wrote. 409: the rename conflicts with the current config.
        if errors:
            outcome = {"description": description, "error": errors[0]}
            try:
                m.rollback()
            except ApiError as exc:
                # Undo failed: the shadow may be half-written. Audit that too.
                m.audit("rename_rollback", rollback_failed=exc.message, **outcome)
                raise
            m.audit("rename_rollback", **outcome)
            raise ApiError(f"Rename failed: {errors[0]}", 409, errors=errors)

        txn = uuid.uuid4().hex[:8]
        for obj, attrs in writes:
            audit_attribute_changes(
                m, obj.object_type, obj.get_display_name(), obj.source_file,
                obj.attributes, attrs, txn,
            )

    return jsonify({
        "success": True, "keys": keys, "key_changes": key_changes,
        "references_updated": len(ref_edits),
    })


@bp.route("/api/objects/referenced-by")
def api_referenced_by():
    """Objects that refer to the object with the given stable key.

    Query: key=<stable_key>. Uses the same type-aware matching as rename
    (app/references.py): for a template, the objects of its type that ``use``
    it; for a registered object, its typed references, plus objects that
    ``use`` it by its ``name`` (field "use"), since deleting it breaks those
    too even though renaming it does not. The object itself is not listed.
    """
    stable_key = request.args.get("key")
    if not stable_key:
        raise ApiError("key required")
    service = get_service()
    found = service.find_object_by_stable_key(stable_key)
    if not found:
        raise ApiError(f"Object not found: {stable_key}", 404)
    target = found[1]
    references = [
        {
            "stable_key": generate_stable_key_for_object(obj),
            "object_type": obj.object_type,
            "display_name": obj.get_display_name(),
            "fields": fields,
        }
        for obj, fields in referenced_by(
            service.get_objects(), target, include_template_uses=True,
        )
    ]
    return jsonify({"success": True, "references": references})


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
