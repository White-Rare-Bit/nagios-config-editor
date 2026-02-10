"""Bulk operations routes for Nagios configuration editing."""

import copy
import logging
import os

from flask import Blueprint, jsonify, request

import file_operations
from nagios_model import NAME_FIELDS, REFERENCE_FIELDS
from nagios_writer import NagiosConfigWriter
from staging_manager import generate_stable_key_for_object

from .helpers import (
    get_config_path,
    get_op_logger,
    get_service,
    get_staging_manager,
)

bp = Blueprint("bulk_ops", __name__)
logger = logging.getLogger("nagios_bulk_editor.bulk_ops")


# ─────────────────────────────────────────────────────────────────────
# api_move_objects helpers
# ─────────────────────────────────────────────────────────────────────

def _validate_move_objects_input(data):
    """Validate move-objects request data. Returns (object_data, target_file, create_new, error_response)."""
    object_data = data.get("objects", [])
    target_file = data.get("target_file", "")
    create_new = data.get("create_new", False)

    if not isinstance(object_data, list):
        return None, None, None, (jsonify({"error": "Objects must be a list"}), 400)
    if not object_data or not target_file:
        return None, None, None, (jsonify({"error": "Objects and target file required"}), 400)

    return object_data, target_file, create_new, None


def _resolve_and_validate_target(target_file, config_path):
    """Resolve target file path and validate it's within config directory. Returns (resolved_path, error_response)."""
    if not os.path.isabs(target_file):
        target_file = os.path.join(config_path, target_file)
    target_file = os.path.realpath(target_file)

    try:
        common = os.path.commonpath([config_path, target_file])
        if common != config_path:
            return None, (jsonify({"error": "Target file must be within config directory"}), 400)
    except ValueError:
        return None, (jsonify({"error": "Target file must be within config directory"}), 400)

    return target_file, None


def _create_target_file_if_needed(target_file, create_new):
    """Create target file if it doesn't exist and create_new is True. Returns (file_created, error_response)."""
    if not create_new or os.path.exists(target_file):
        return False, None
    try:
        parent_dir = os.path.dirname(target_file)
        if not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)
        with open(target_file, "w") as f:
            f.write("# Nagios configuration file\n")
            f.write("# Created by Nagios Bulk Editor\n\n")
        return True, None
    except OSError as e:
        return False, (jsonify({"error": f"Could not create file: {e}"}), 400)


def _move_objects_in_parser(object_data, p_objects, target_file):
    """Move objects to target file. Returns (moved_count, skipped)."""
    moved_count = 0
    skipped = []
    for item in object_data:
        idx, position = _parse_move_item(item)
        if idx is None:
            skipped.append(str(item))
            continue

        if 0 <= idx < len(p_objects):
            old_file = p_objects[idx].source_file
            p_objects[idx].source_file = target_file
            if position is not None:
                p_objects[idx].line_number = position
            moved_count += 1
            logger.debug("Moved object %s from %s to %s at position %s", idx, old_file, target_file, position)
        else:
            skipped.append(idx)
            logger.warning("Invalid index %s, max is %s", idx, len(p_objects)-1)
    return moved_count, skipped


def _parse_move_item(item):
    """Parse a move item (int or dict) into (index, position). Returns (None, None) on error."""
    if isinstance(item, dict):
        idx = item.get("index")
        position = item.get("position")
    else:
        idx = item
        position = None
    try:
        idx = int(idx)
    except (ValueError, TypeError):
        return None, None
    return idx, position


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

@bp.route("/api/search", methods=["POST"])
def api_search():
    """Search for objects."""
    p = get_service().parser
    data = request.get_json() or {}

    # Validate input is a dictionary
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    search_term = data.get("search", "")
    object_type = data.get("type")
    field = data.get("field")
    use_regex = data.get("regex", False)

    results = p.find_objects(search_term, object_type, field, use_regex)
    return jsonify([o.to_dict() for o in results])


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


@bp.route("/api/apply-rename", methods=["POST"])
def api_apply_rename():
    """Stage bulk rename operation (changes applied via staging Apply)."""
    op_log = get_op_logger()
    sm = get_staging_manager()
    data = request.get_json() or {}

    object_type = data.get("type")
    if op_log:
        op_log.info("app", "apply_rename", params={"object_type": object_type})
    find_pattern = data.get("find", "")
    replace_with = data.get("replace", "")
    use_regex = data.get("regex", False)
    add_prefix = data.get("prefix", "")
    add_suffix = data.get("suffix", "")
    should_update_refs = data.get("updateReferences", data.get("update_references", False))

    if not object_type:
        return jsonify({"error": "Object type required"}), 400

    session_id = request.headers.get("X-Session-Id")
    if not session_id:
        return jsonify({"error": "X-Session-Id header required"}), 400
    if not sm.can_modify(session_id):
        return jsonify({"error": "Locked by another user", "locked": True}), 423

    service = get_service()
    p = service.parser
    name_field = NAME_FIELDS.get(object_type, "name")
    renames = []

    # Compute renames and reference updates
    # Work on copies to avoid mutating live parser state
    all_objects = list(p.objects)
    ref_updates = {}  # {old_name: new_name} for reference tracking

    for idx, obj in enumerate(all_objects):
        if obj.object_type != object_type or name_field not in obj.attributes:
            continue
        old_name = obj.attributes[name_field]
        new_name = service.transform_name(old_name, find_pattern, replace_with,
                                          add_prefix, add_suffix, use_regex)
        if new_name is None or new_name == old_name:
            continue
        ref_updates[old_name] = new_name
        renames.append({
            "globalIndex": idx,
            "object": obj.to_dict(),
            "originalAttrs": {name_field: old_name},
            "editedAttrs": {name_field: new_name},
        })

    if not renames:
        return jsonify({"success": True, "staged": 0, "references_staged": 0})

    # Stage reference updates if requested
    references_staged = 0
    if should_update_refs and ref_updates:
        for idx, obj in enumerate(all_objects):
            ref_edits = {}
            for field in REFERENCE_FIELDS:
                val = obj.attributes.get(field)
                if not val:
                    continue
                parts = [v.strip() for v in val.split(",")]
                changed = False
                new_parts = []
                for part in parts:
                    if part in ref_updates:
                        new_parts.append(ref_updates[part])
                        changed = True
                    else:
                        new_parts.append(part)
                if changed:
                    ref_edits[field] = ",".join(new_parts)
            if ref_edits:
                # Check if this object already has a rename entry
                existing = next((r for r in renames if r["globalIndex"] == idx), None)
                if existing:
                    existing["editedAttrs"].update(ref_edits)
                    existing["originalAttrs"].update(
                        {f: obj.attributes[f] for f in ref_edits},
                    )
                else:
                    renames.append({
                        "globalIndex": idx,
                        "object": obj.to_dict(),
                        "originalAttrs": {f: obj.attributes[f] for f in ref_edits},
                        "editedAttrs": ref_edits,
                    })
                    references_staged += 1

    result = sm.stage_bulk_rename(session_id, renames)
    if not result.success:
        return jsonify({"error": result.error}), 500

    return jsonify({
        "success": True,
        "staged": result.data,
        "references_staged": references_staged,
    })


@bp.route("/api/move-objects", methods=["POST"])
def api_move_objects():
    """Stage bulk move operation (changes applied via staging Apply)."""
    op_log = get_op_logger()
    sm = get_staging_manager()
    data = request.get_json() or {}

    if op_log:
        op_log.info("app", "move_objects", params={
            "object_count": len(data.get("objects", [])),
            "target_file": data.get("target_file", ""),
        })

    session_id = request.headers.get("X-Session-Id")
    if not session_id:
        return jsonify({"error": "X-Session-Id header required"}), 400
    if not sm.can_modify(session_id):
        return jsonify({"error": "Locked by another user", "locked": True}), 423

    object_data, target_file, create_new, err = _validate_move_objects_input(data)
    if err:
        return err

    config_path = os.path.realpath(get_config_path())
    target_file, err = _resolve_and_validate_target(target_file, config_path)
    if err:
        return err

    # If creating a new file, stage the file creation
    if create_new and not os.path.exists(target_file):
        sm.file_ops.stage_file_creation(target_file)

    service = get_service()
    p = service.parser
    all_objects = list(p.objects)
    moves = []
    skipped = []

    for item in object_data:
        idx, _position = _parse_move_item(item)
        if idx is None:
            skipped.append(str(item))
            continue
        if 0 <= idx < len(all_objects):
            obj = all_objects[idx]
            if obj.source_file == target_file:
                continue  # Already in target file
            moves.append({
                "stableKey": generate_stable_key_for_object(obj),
                "object": obj.to_dict(),
                "sourceFile": obj.source_file,
                "targetFile": target_file,
            })
        else:
            skipped.append(str(idx))

    if not moves:
        return jsonify({
            "success": True,
            "staged": 0,
            "skipped": skipped,
            "requested": len(object_data),
        })

    result = sm.stage_bulk_move(session_id, moves)
    if not result.success:
        return jsonify({"error": result.error}), 500

    return jsonify({
        "success": True,
        "staged": result.data,
        "skipped": skipped,
        "requested": len(object_data),
        "target_file": target_file,
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
