"""Bulk operations routes for Nagios configuration editing."""

import copy
import logging
import os

from flask import Blueprint, jsonify, request

import file_operations
from nagios_model import NAME_FIELDS
from nagios_writer import NagiosConfigWriter

from .helpers import get_service

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
