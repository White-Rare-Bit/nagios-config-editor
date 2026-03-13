"""Bulk operations routes for Nagios configuration editing."""

import copy
import logging
import os

from flask import Blueprint, jsonify, request

import file_operations
from nagios_model import NAME_FIELDS, REFERENCE_FIELDS
from nagios_writer import NagiosConfigWriter

from .files import ensure_shadow_lock
from .helpers import get_service, get_shadow_manager

bp = Blueprint("bulk_ops", __name__)
logger = logging.getLogger("nagios_bulk_editor.bulk_ops")


# ─────────────────────────────────────────────────────────────────────
# api_diff_rename helpers
# ─────────────────────────────────────────────────────────────────────

def _group_objects_by_file(objects):
    """Group a list of objects by source_file. Returns {filepath: [objects]}."""
    by_file = {}
    for obj in objects:
        if obj.source_file not in by_file:
            by_file[obj.source_file] = []
        by_file[obj.source_file].append(obj)
    return by_file


def _apply_renames_to_objects(objects, object_type, rename_params):
    """Apply rename transforms to a list of objects in-place."""
    name_field = NAME_FIELDS.get(object_type, "name")
    find_pattern, replace_with, add_prefix, add_suffix, use_regex = rename_params
    for obj in objects:
        if obj.object_type == object_type and name_field in obj.attributes:
            old_name = obj.attributes[name_field]
            new_name = get_service().transform_name(
                old_name, find_pattern, replace_with,
                add_prefix, add_suffix, use_regex,
            )
            if new_name is not None and new_name != old_name:
                obj.attributes[name_field] = new_name
                get_service().update_references(objects, old_name, new_name)


def _generate_file_diffs(original_by_file, original_content, modified_by_file, writer):
    """Generate diff output for files that changed."""
    diffs = []
    all_files = set(list(original_by_file.keys()) + list(modified_by_file.keys()))
    for filepath in all_files:
        orig = original_content.get(filepath, "")
        mod_objs = modified_by_file.get(filepath, [])
        mod = writer.objects_to_string(mod_objs) if mod_objs else ""
        if orig != mod:
            diff_lines = file_operations.generate_diff(orig, mod, os.path.basename(filepath))
            diffs.append({"file": filepath, "diff": "".join(diff_lines)})
    return diffs


# ═══════════════════════════════════════════════════════════════════════
# Route handlers
# ═══════════════════════════════════════════════════════════════════════

@bp.route("/api/preview-rename", methods=["POST"])
def api_preview_rename():
    """Preview bulk rename operation."""
    p = get_service().parser
    data = request.get_json() or {}

    object_type = data.get("type")
    find_pattern = data.get("find", "")
    replace_with = data.get("replace", "")
    use_regex = data.get("regex", False)
    add_prefix = data.get("prefix", "")
    add_suffix = data.get("suffix", "")

    if not object_type:
        return jsonify({"error": "Object type required"}), 400

    objs = p.get_objects_by_type(object_type)
    changes = []

    for obj in objs:
        old_name = obj.get_name()
        if not old_name:
            continue

        new_name = get_service().transform_name(old_name, find_pattern, replace_with,
                                  add_prefix, add_suffix, use_regex)
        if new_name is None:
            return jsonify({"error": "Invalid regex pattern"}), 400

        if new_name != old_name:
            # Find references that will be updated
            refs = p.find_references(object_type, old_name)
            changes.append({
                "object": obj.to_dict(),
                "old_name": old_name,
                "new_name": new_name,
                "references": len(refs),
            })

    return jsonify({
        "changes": changes,
        "total": len(changes),
    })


@bp.route("/api/diff/rename", methods=["POST"])
def api_diff_rename():
    """Generate diff preview for bulk rename operation."""
    service = get_service()
    data = request.get_json() or {}

    object_type = data.get("type")
    if not object_type:
        return jsonify({"error": "Object type required"}), 400

    rename_params = (
        data.get("find", ""),
        data.get("replace", ""),
        data.get("prefix", ""),
        data.get("suffix", ""),
        data.get("regex", False),
    )

    writer = NagiosConfigWriter()

    # Generate original content by file
    original_objects = copy.deepcopy(service.get_objects())
    original_by_file = _group_objects_by_file(original_objects)
    original_content = {fp: writer.objects_to_string(objs) for fp, objs in original_by_file.items()}

    # Apply changes to copy
    modified_objects = copy.deepcopy(service.get_objects())
    _apply_renames_to_objects(modified_objects, object_type, rename_params)
    modified_by_file = _group_objects_by_file(modified_objects)

    # Generate diffs
    diffs = _generate_file_diffs(original_by_file, original_content, modified_by_file, writer)

    return jsonify({"diffs": diffs})


@bp.route("/api/apply-rename", methods=["POST"])
def api_apply_rename():
    """Apply bulk rename to shadow copy.

    Expects same params as preview-rename plus optional updateReferences.
    """
    data = request.get_json() or {}
    object_type = data.get("type")
    find_pattern = data.get("find", "")
    replace_with = data.get("replace", "")
    use_regex = data.get("regex", False)
    add_prefix = data.get("prefix", "")
    add_suffix = data.get("suffix", "")
    should_update_refs = data.get("updateReferences", data.get("update_references", False))

    if not object_type:
        return jsonify({"error": "Object type required"}), 400

    session_id = request.headers.get("X-Session-Id")
    success, error = ensure_shadow_lock(session_id)
    if not success:
        return error

    service = get_service()
    sm = get_shadow_manager()
    p = service.parser
    name_field = NAME_FIELDS.get(object_type, "name")

    # Compute renames
    renames = []  # (obj, old_name, new_name)
    for obj in p.objects:
        if obj.object_type != object_type or name_field not in obj.attributes:
            continue
        old_name = obj.attributes[name_field]
        new_name = service.transform_name(
            old_name, find_pattern, replace_with,
            add_prefix, add_suffix, use_regex,
        )
        if new_name is not None and new_name != old_name:
            renames.append((obj, old_name, new_name))

    if not renames:
        return jsonify({"success": True, "renamed": 0, "references_updated": 0})

    # Compute reference updates
    ref_updates = []  # (obj, new_attrs)
    if should_update_refs:
        rename_map = {old: new for _, old, new in renames}
        for obj in p.objects:
            new_attrs = None
            for field_name in REFERENCE_FIELDS:
                val = obj.attributes.get(field_name)
                if not val:
                    continue
                parts = [v.strip() for v in val.split(",")]
                new_parts = [rename_map.get(part, part) for part in parts]
                if new_parts != parts:
                    if new_attrs is None:
                        new_attrs = dict(obj.attributes)
                    new_attrs[field_name] = ",".join(new_parts)
            if new_attrs is not None:
                ref_updates.append((obj, new_attrs))

    # Snapshot all affected files
    affected_files = set()
    for obj, _, _ in renames:
        affected_files.add(os.path.relpath(obj.source_file, sm._config_dir))
    for obj, _ in ref_updates:
        affected_files.add(os.path.relpath(obj.source_file, sm._config_dir))
    sm.snapshot_files(list(affected_files), f"bulk rename {object_type}")

    # Build complete edits: merge renames and reference updates per object
    edits = {}  # source_file -> [(line_number, new_attrs, obj_type)]
    for obj, _old_name, new_name in renames:
        attrs = dict(obj.attributes)
        attrs[name_field] = new_name
        # Check if this object also has reference updates
        ref_match = next((na for o, na in ref_updates if o is obj), None)
        if ref_match:
            attrs.update(ref_match)
        edits.setdefault(obj.source_file, []).append(
            (obj.line_number, attrs, obj.object_type)
        )

    for obj, new_attrs in ref_updates:
        # Skip objects already covered by renames
        if any(o is obj for o, _, _ in renames):
            continue
        edits.setdefault(obj.source_file, []).append(
            (obj.line_number, new_attrs, obj.object_type)
        )

    # Apply edits: reverse line order within each file
    errors = []
    for source_file, file_edits in edits.items():
        for line_number, new_attrs, obj_type in sorted(file_edits, key=lambda e: -e[0]):
            result = file_operations.edit_object_in_file(
                source_file, line_number, new_attrs, obj_type,
            )
            if not result.success:
                errors.append(result.error)

    if errors:
        service.reload()
        return jsonify({
            "success": False,
            "error": f"Some edits failed: {'; '.join(errors)}",
        }), 500

    service.reload()

    # Count individual reference field updates
    references_updated = 0
    if should_update_refs:
        rename_map = {old: new for _, old, new in renames}
        for obj, new_attrs in ref_updates:
            for field_name in REFERENCE_FIELDS:
                old_val = obj.attributes.get(field_name)
                new_val = new_attrs.get(field_name)
                if old_val and new_val and old_val != new_val:
                    old_parts = [v.strip() for v in old_val.split(",")]
                    references_updated += sum(1 for p in old_parts if p in rename_map)

    return jsonify({
        "success": True,
        "renamed": len(renames),
        "references_updated": references_updated,
    })


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
