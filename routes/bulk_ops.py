"""Bulk operations routes for Nagios configuration editing."""

import os
import copy
from flask import Blueprint, request, jsonify
from typing import List

from .helpers import (
    get_service,
    get_parser_for_modification,
    get_backup_manager,
    get_op_logger,
    get_config_path
)
from nagios_model import NAME_FIELDS
from nagios_writer import NagiosConfigWriter
import file_operations

bp = Blueprint('bulk_ops', __name__)


@bp.route('/api/search', methods=['POST'])
def api_search():
    """Search for objects."""
    p = get_service().parser
    data = request.get_json() or {}

    # Validate input is a dictionary
    if not isinstance(data, dict):
        return jsonify({'error': 'Request body must be a JSON object'}), 400

    search_term = data.get('search', '')
    object_type = data.get('type')
    field = data.get('field')
    use_regex = data.get('regex', False)

    results = p.find_objects(search_term, object_type, field, use_regex)
    return jsonify([o.to_dict() for o in results])


@bp.route('/api/preview-rename', methods=['POST'])
def api_preview_rename():
    """Preview bulk rename operation."""
    p = get_service().parser
    data = request.get_json() or {}

    object_type = data.get('type')
    find_pattern = data.get('find', '')
    replace_with = data.get('replace', '')
    use_regex = data.get('regex', False)
    add_prefix = data.get('prefix', '')
    add_suffix = data.get('suffix', '')

    if not object_type:
        return jsonify({'error': 'Object type required'}), 400

    objs = p.get_objects_by_type(object_type)
    changes = []

    for obj in objs:
        old_name = obj.get_name()
        if not old_name:
            continue

        new_name = get_service().transform_name(old_name, find_pattern, replace_with,
                                  add_prefix, add_suffix, use_regex)
        if new_name is None:
            return jsonify({'error': 'Invalid regex pattern'}), 400

        if new_name != old_name:
            # Find references that will be updated
            refs = p.find_references(object_type, old_name)
            changes.append({
                'object': obj.to_dict(),
                'old_name': old_name,
                'new_name': new_name,
                'references': len(refs)
            })

    return jsonify({
        'changes': changes,
        'total': len(changes)
    })


@bp.route('/api/apply-rename', methods=['POST'])
def api_apply_rename():
    """Apply bulk rename operation."""
    op_log = get_op_logger()
    bm = get_backup_manager()
    data = request.get_json() or {}

    object_type = data.get('type')
    if op_log:
        op_log.info('app', 'apply_rename', params={'object_type': object_type})
    find_pattern = data.get('find', '')
    replace_with = data.get('replace', '')
    use_regex = data.get('regex', False)
    add_prefix = data.get('prefix', '')
    add_suffix = data.get('suffix', '')
    # Accept both camelCase and snake_case for compatibility
    should_update_refs = data.get('updateReferences', data.get('update_references', False))

    if not object_type:
        return jsonify({'error': 'Object type required'}), 400

    with get_parser_for_modification() as p:
        # Create backup before changes
        backup_path = bm.create_backup(f"rename_{object_type}")

        name_field = NAME_FIELDS.get(object_type, 'name')
        renamed_count = 0
        references_updated = 0

        for obj in p.objects:
            if obj.object_type == object_type and name_field in obj.attributes:
                old_name = obj.attributes[name_field]
                new_name = get_service().transform_name(old_name, find_pattern, replace_with,
                                          add_prefix, add_suffix, use_regex)
                if new_name is None:
                    continue  # Skip invalid regex

                if new_name != old_name:
                    obj.attributes[name_field] = new_name
                    renamed_count += 1
                    # Only update references if user opted in
                    if should_update_refs:
                        references_updated += get_service().update_references(p.objects, old_name, new_name)

        # Write changes to files
        writer = NagiosConfigWriter()
        writer.write_objects_to_original_files(p.objects)

    # Reload config
    get_service().reload()

    return jsonify({
        'success': True,
        'renamed': renamed_count,
        'references_updated': references_updated,
        'backup': backup_path
    })


@bp.route('/api/move-objects', methods=['POST'])
def api_move_objects():
    """Move objects to a different file."""
    op_log = get_op_logger()
    bm = get_backup_manager()
    data = request.get_json() or {}

    object_data = data.get('objects', [])
    if op_log:
        op_log.info('app', 'move_objects', params={'object_count': len(data.get('objects', [])), 'target_file': data.get('target_file', '')})
    target_file = data.get('target_file', '')
    create_new = data.get('create_new', False)

    # Validate types
    if not isinstance(object_data, list):
        return jsonify({'error': 'Objects must be a list'}), 400
    if not object_data or not target_file:
        return jsonify({'error': 'Objects and target file required'}), 400

    config_path = os.path.realpath(get_config_path())

    # Resolve target path - if relative, make it relative to config_path
    if not os.path.isabs(target_file):
        target_file = os.path.join(config_path, target_file)
    target_file = os.path.realpath(target_file)

    # Security check: ensure target is within config directory
    try:
        # Use commonpath to verify target is under config_path
        common = os.path.commonpath([config_path, target_file])
        if common != config_path:
            return jsonify({'error': 'Target file must be within config directory'}), 400
    except ValueError:
        # commonpath raises ValueError if paths are on different drives (Windows)
        return jsonify({'error': 'Target file must be within config directory'}), 400

    with get_parser_for_modification() as p:
        # Create backup
        backup_path = bm.create_backup("move_objects")

        file_created = False
        # Create new file if it doesn't exist
        if create_new and not os.path.exists(target_file):
            try:
                # Ensure parent directory exists
                parent_dir = os.path.dirname(target_file)
                if not os.path.exists(parent_dir):
                    os.makedirs(parent_dir, exist_ok=True)
                # Create empty file with header comment
                with open(target_file, 'w') as f:
                    f.write(f"# Nagios configuration file\n")
                    f.write(f"# Created by Nagios Bulk Editor\n\n")
                file_created = True
            except OSError as e:
                return jsonify({'error': f'Could not create file: {e}'}), 400

        # Move objects - handle both old format (list of ints) and new format (list of {index, position})
        moved_count = 0
        skipped = []
        for item in object_data:
            # Handle both formats: plain int or object with index/position
            if isinstance(item, dict):
                idx = item.get('index')
                position = item.get('position')
            else:
                idx = item
                position = None

            try:
                idx = int(idx)  # Ensure integer
            except (ValueError, TypeError):
                skipped.append(str(idx))
                continue

            if 0 <= idx < len(p.objects):
                old_file = p.objects[idx].source_file
                p.objects[idx].source_file = target_file
                # Update line_number to control position in new file
                if position is not None:
                    p.objects[idx].line_number = position
                moved_count += 1
                print(f"Moved object {idx} from {old_file} to {target_file} at position {position}")
            else:
                skipped.append(idx)
                print(f"Invalid index {idx}, max is {len(p.objects)-1}")

        # Write changes
        try:
            writer = NagiosConfigWriter()
            writer.write_objects_to_original_files(p.objects)
        except (IOError, OSError, PermissionError) as e:
            return jsonify({'error': f'Failed to write changes: {str(e)}'}), 500

    # Reload config
    try:
        get_service().reload()
    except (IOError, OSError) as e:
        return jsonify({'error': f'Failed to reload config: {str(e)}'}), 500

    return jsonify({
        'success': True,
        'moved': moved_count,
        'skipped': skipped,
        'requested': len(object_data),
        'backup': backup_path,
        'file_created': file_created,
        'target_file': target_file
    })


@bp.route('/api/diff/rename', methods=['POST'])
def api_diff_rename():
    """Generate diff preview for bulk rename operation."""
    service = get_service()
    data = request.get_json() or {}

    object_type = data.get('type')
    find_pattern = data.get('find', '')
    replace_with = data.get('replace', '')
    use_regex = data.get('regex', False)
    add_prefix = data.get('prefix', '')
    add_suffix = data.get('suffix', '')

    if not object_type:
        return jsonify({'error': 'Object type required'}), 400

    # Create deep copy of objects
    original_objects = copy.deepcopy(service.get_objects())
    writer = NagiosConfigWriter()

    # Generate original content by file
    original_by_file = {}
    for obj in original_objects:
        if obj.source_file not in original_by_file:
            original_by_file[obj.source_file] = []
        original_by_file[obj.source_file].append(obj)

    original_content = {}
    for filepath, objs in original_by_file.items():
        original_content[filepath] = writer.objects_to_string(objs)

    # Apply changes to copy
    name_field = NAME_FIELDS.get(object_type, 'name')
    modified_objects = copy.deepcopy(service.get_objects())

    for obj in modified_objects:
        if obj.object_type == object_type and name_field in obj.attributes:
            old_name = obj.attributes[name_field]
            new_name = get_service().transform_name(old_name, find_pattern, replace_with,
                                      add_prefix, add_suffix, use_regex)
            if new_name is None:
                continue  # Skip invalid regex

            if new_name != old_name:
                obj.attributes[name_field] = new_name
                get_service().update_references(modified_objects, old_name, new_name)

    # Generate modified content
    modified_by_file = {}
    for obj in modified_objects:
        if obj.source_file not in modified_by_file:
            modified_by_file[obj.source_file] = []
        modified_by_file[obj.source_file].append(obj)

    # Generate diffs
    diffs = []
    for filepath in set(list(original_by_file.keys()) + list(modified_by_file.keys())):
        orig = original_content.get(filepath, '')
        mod_objs = modified_by_file.get(filepath, [])
        mod = writer.objects_to_string(mod_objs) if mod_objs else ''

        if orig != mod:
            diff_lines = file_operations.generate_diff(orig, mod, os.path.basename(filepath))
            diffs.append({
                'file': filepath,
                'diff': ''.join(diff_lines)
            })

    return jsonify({'diffs': diffs})


