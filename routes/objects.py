"""Object CRUD routes."""

import os
import copy
from flask import Blueprint, request, jsonify

from .helpers import (
    get_service,
    get_parser_for_modification,
    get_backup_manager,
    get_config_path
)
from nagios_model import NagiosObject, NAME_FIELDS
from nagios_writer import NagiosConfigWriter

bp = Blueprint('objects', __name__)


@bp.route('/api/objects')
def api_objects():
    """Get objects, optionally filtered by type."""
    service = get_service()
    object_type = request.args.get('type')
    search = request.args.get('search', '')

    # Build list with global indices
    results = []
    for global_idx, obj in enumerate(service.get_objects()):
        if object_type and obj.object_type != object_type:
            continue
        if search and search.lower() not in obj.get_display_name().lower():
            continue
        obj_dict = obj.to_dict()
        obj_dict['global_index'] = global_idx
        results.append(obj_dict)

    return jsonify(results)


@bp.route('/api/delete-objects', methods=['POST'])
def api_delete_objects():
    """Delete multiple objects."""
    bm = get_backup_manager()
    data = request.get_json() or {}

    # Validate input is a dictionary
    if not isinstance(data, dict):
        return jsonify({'error': 'Request body must be a JSON object'}), 400

    object_indices = data.get('objects', [])
    update_references_flag = data.get('update_references', True)

    if not object_indices:
        return jsonify({'error': 'No objects specified'}), 400

    # Validate all indices are integers
    if not isinstance(object_indices, list):
        return jsonify({'error': 'objects must be an array'}), 400

    validated_indices = []
    for idx in object_indices:
        if isinstance(idx, bool) or not isinstance(idx, (int, float)):
            return jsonify({'error': 'All object indices must be integers'}), 400
        if isinstance(idx, float) and not idx.is_integer():
            return jsonify({'error': 'All object indices must be integers'}), 400
        validated_indices.append(int(idx))
    object_indices = validated_indices

    # Use lock for entire modification operation
    with get_parser_for_modification() as p:
        # Create backup
        backup_path = bm.create_backup("bulk_delete")

        # Get objects to delete and their names for reference cleanup
        objects_to_delete = []
        for idx in sorted(object_indices, reverse=True):
            if 0 <= idx < len(p.objects):
                obj = p.objects[idx]
                objects_to_delete.append({
                    'type': obj.object_type,
                    'name': obj.get_name()
                })

        # Remove objects (in reverse order to maintain indices)
        deleted_count = 0
        for idx in sorted(object_indices, reverse=True):
            if 0 <= idx < len(p.objects):
                del p.objects[idx]
                deleted_count += 1

        # Clean up references if requested
        references_cleaned = 0
        if update_references_flag:
            for deleted in objects_to_delete:
                if not deleted['name']:
                    continue
                for obj in p.objects:
                    for field_name, value in list(obj.attributes.items()):
                        values = [v.strip() for v in value.split(',')]
                        if deleted['name'] in values:
                            new_values = [v for v in values if v != deleted['name']]
                            if new_values:
                                obj.attributes[field_name] = ','.join(new_values)
                            else:
                                del obj.attributes[field_name]
                            references_cleaned += 1

        # Write changes
        writer = NagiosConfigWriter()
        writer.write_objects_to_original_files(p.objects)

        # Reset parser to force reload on next access
        parser = None

    return jsonify({
        'success': True,
        'deleted': deleted_count,
        'references_cleaned': references_cleaned,
        'backup': backup_path
    })


@bp.route('/api/clone-objects', methods=['POST'])
def api_clone_objects():
    """Clone/duplicate objects with modifications."""
    bm = get_backup_manager()
    data = request.get_json() or {}

    object_indices = data.get('objects', [])
    find_pattern = data.get('find', '')
    replace_with = data.get('replace', '')
    add_prefix = data.get('prefix', '')
    add_suffix = data.get('suffix', '')
    target_file = data.get('target_file', '')

    if not object_indices:
        return jsonify({'error': 'No objects specified'}), 400

    with get_parser_for_modification() as p:
        # Create backup
        backup_path = bm.create_backup("clone_objects")

        cloned_count = 0

        for idx in object_indices:
            if 0 <= idx < len(p.objects):
                original = p.objects[idx]
                cloned = NagiosObject(
                    object_type=original.object_type,
                    attributes=copy.deepcopy(original.attributes),
                    source_file=target_file if target_file else original.source_file,
                    line_number=0
                )

                # Modify the name
                name_field = NAME_FIELDS.get(original.object_type, 'name')
                if name_field in cloned.attributes:
                    old_name = cloned.attributes[name_field]
                    new_name = get_service().transform_name(old_name, find_pattern, replace_with,
                                              add_prefix, add_suffix)
                    if new_name is None:
                        new_name = old_name  # Shouldn't happen since no regex, but be safe

                    # Ensure name is different
                    if new_name == old_name:
                        new_name = old_name + '_copy'

                    cloned.attributes[name_field] = new_name

                # Ensure target file has full path
                if cloned.source_file and not os.path.isabs(cloned.source_file):
                    cloned.source_file = os.path.join(get_config_path(), cloned.source_file)

                p.objects.append(cloned)
                cloned_count += 1

        # Write changes
        writer = NagiosConfigWriter()
        writer.write_objects_to_original_files(p.objects)

    # Reload config
    get_service().reload()

    return jsonify({
        'success': True,
        'cloned': cloned_count,
        'backup': backup_path
    })
