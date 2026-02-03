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
from file_operations import is_safe_path

bp = Blueprint('objects', __name__)


def validate_template_references(object_type: str, attributes: dict) -> tuple[bool, str]:
    """
    Validate that all templates referenced in 'use' attribute exist and match the object type.

    Nagios templates are type-scoped: a host template can only be used by hosts,
    a service template can only be used by services, etc.

    Returns:
        (True, None) if valid or no 'use' attribute
        (False, error_message) if invalid template reference found
    """
    use_value = attributes.get('use', '')
    if not use_value:
        return True, None

    service = get_service()

    # Build lookup of templates by type
    templates_by_type = {}
    for obj in service.get_objects():
        if obj.attributes.get('register', '1') == '0':
            name = obj.attributes.get('name')
            if name:
                if obj.object_type not in templates_by_type:
                    templates_by_type[obj.object_type] = set()
                templates_by_type[obj.object_type].add(name)

    # Check each template reference
    template_names = [t.strip() for t in use_value.split(',') if t.strip()]
    valid_templates = templates_by_type.get(object_type, set())

    for tmpl_name in template_names:
        if tmpl_name not in valid_templates:
            # Check if it exists as a different type
            found_type = None
            for tmpl_type, names in templates_by_type.items():
                if tmpl_name in names:
                    found_type = tmpl_type
                    break

            if found_type:
                return False, f"Template '{tmpl_name}' is a {found_type} template, cannot be used by {object_type}"
            else:
                return False, f"Template '{tmpl_name}' not found for type '{object_type}'"

    return True, None


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


@bp.route('/api/objects/by-key/<path:stable_key>', methods=['GET'])
def api_get_object_by_key(stable_key: str):
    """
    Get an object by its stable key.

    The stable key is URL-encoded and passed as a path parameter.
    Format: "source_file|object_type|name"

    Returns the object data including its current global_index (for compatibility).
    """
    found = get_service().find_object_by_stable_key(stable_key)

    if not found:
        return jsonify({'error': f'Object not found: {stable_key}'}), 404

    idx, obj = found
    obj_dict = obj.to_dict()
    obj_dict['global_index'] = idx
    obj_dict['stable_key'] = stable_key

    return jsonify(obj_dict)


@bp.route('/api/object/update', methods=['POST'])
def api_update_object():
    """Update a single object's attributes."""
    bm = get_backup_manager()
    data = request.get_json() or {}

    source_file = data.get('source_file')
    line_number = data.get('line_number')
    object_type = data.get('object_type')
    original_attrs = data.get('original_attributes', {})
    new_attrs = data.get('new_attributes', {})

    # Validate that required name field exists (unless it's a template)
    if 'register' not in new_attrs or new_attrs.get('register') != '0':
        name_field = NAME_FIELDS.get(object_type, 'name')
        if name_field not in new_attrs or not new_attrs[name_field].strip():
            return jsonify({'error': f'Required field "{name_field}" is missing or empty'}), 400

    # Validate template references match object type
    is_valid, error_msg = validate_template_references(object_type, new_attrs)
    if not is_valid:
        return jsonify({'error': error_msg}), 400

    with get_parser_for_modification() as p:
        # Find the matching object
        target_obj = None
        for obj in p.objects:
            if (obj.source_file == source_file and
                obj.line_number == line_number and
                obj.object_type == object_type):
                target_obj = obj
                break

        if not target_obj:
            return jsonify({'error': 'Object not found'}), 404

        # Create backup
        backup_path = bm.create_backup("inline_edit")

        # Update attributes
        target_obj.attributes = new_attrs

        # Write changes
        writer = NagiosConfigWriter()
        writer.write_objects_to_original_files(p.objects)

        # Get updated display name
        display_name = target_obj.get_display_name()

    # Reload config
    get_service().reload()

    return jsonify({
        'success': True,
        'display_name': display_name,
        'backup': backup_path
    })


@bp.route('/api/objects/batch-update', methods=['POST'])
def api_batch_update_objects():
    """Update multiple objects at once (commit operation)."""
    bm = get_backup_manager()
    data = request.get_json() or {}

    updates = data.get('updates', [])
    if not updates:
        return jsonify({'error': 'No updates provided'}), 400

    with get_parser_for_modification() as p:
        # Create a single backup for all changes
        backup_path = bm.create_backup("batch_commit")

        updated_count = 0
        errors = []

        for update in updates:
            source_file = update.get('source_file')
            line_number = update.get('line_number')
            object_type = update.get('object_type')
            new_attrs = update.get('new_attributes', {})

            # Find the matching object
            target_obj = None
            for obj in p.objects:
                if (obj.source_file == source_file and
                    obj.line_number == line_number and
                    obj.object_type == object_type):
                    target_obj = obj
                    break

            if target_obj:
                # Validate that required name field exists (unless it's a template)
                if 'register' not in new_attrs or new_attrs.get('register') != '0':
                    name_field = NAME_FIELDS.get(object_type, 'name')
                    if name_field not in new_attrs or not new_attrs[name_field].strip():
                        errors.append(f"Required field '{name_field}' missing for {object_type} at {source_file}:{line_number}")
                        continue

                # Validate template references match object type
                is_valid, tmpl_error = validate_template_references(object_type, new_attrs)
                if not is_valid:
                    errors.append(f"{tmpl_error} (at {source_file}:{line_number})")
                    continue

                target_obj.attributes = new_attrs
                updated_count += 1
            else:
                errors.append(f"Object not found: {object_type} at {source_file}:{line_number}")

        # Write all changes at once
        writer = NagiosConfigWriter()
        writer.write_objects_to_original_files(p.objects)

    # Reload config
    get_service().reload()

    return jsonify({
        'success': True,
        'updated_count': updated_count,
        'errors': errors,
        'backup': backup_path
    })


@bp.route('/api/objects/create', methods=['POST'])
def api_create_object():
    """Create a new Nagios object in a target file."""
    bm = get_backup_manager()
    data = request.get_json() or {}

    object_type = data.get('object_type')
    attributes = data.get('attributes', {})
    target_file = data.get('target_file')

    if not object_type:
        return jsonify({'error': 'object_type is required'}), 400
    if not attributes:
        return jsonify({'error': 'attributes are required'}), 400
    if not target_file:
        return jsonify({'error': 'target_file is required'}), 400

    # Security check - validate target_file is within config directory
    config_path = get_config_path()
    safe_result = is_safe_path(target_file, config_path)
    if not safe_result.success:
        return jsonify({'error': safe_result.error}), 400

    # Validate template references match object type
    is_valid, tmpl_error = validate_template_references(object_type, attributes)
    if not is_valid:
        return jsonify({'error': tmpl_error}), 400

    # Check for duplicate object names
    name_field = NAME_FIELDS.get(object_type, 'name')
    object_name = attributes.get(name_field, '').strip()
    if object_name:
        service = get_service()
        for obj in service.get_objects():
            if obj.object_type == object_type and obj.get_name() == object_name:
                return jsonify({
                    'error': f'{object_type.capitalize()} "{object_name}" already exists in {obj.source_file}',
                    'duplicate': True
                }), 409

    # Normalize the target_file path
    if not os.path.isabs(target_file):
        target_file = os.path.normpath(os.path.join(config_path, target_file))
    else:
        target_file = os.path.normpath(target_file)

    with get_parser_for_modification() as p:
        # Create backup
        backup_path = bm.create_backup("create_object")

        # Create the new object
        new_obj = NagiosObject(
            object_type=object_type,
            attributes=attributes,
            source_file=target_file,
            line_number=999999  # Will be placed at end of file
        )

        # Add to parser's objects
        p.objects.append(new_obj)

        # Write all objects back to their files
        try:
            writer = NagiosConfigWriter()
            writer.write_objects_to_original_files(p.objects)
        except (IOError, OSError, PermissionError) as e:
            # Remove the object we just added since write failed
            p.objects.remove(new_obj)
            return jsonify({'error': f'Failed to write: {str(e)}'}), 500

    # Reload config
    get_service().reload()

    return jsonify({
        'success': True,
        'object_type': object_type,
        'file': target_file,
        'backup': backup_path
    })


@bp.route('/api/objects/update-references', methods=['POST'])
def api_update_references():
    """
    Update references to renamed objects across all configuration files.

    Expects JSON body with:
    - renames: Array of {oldName: string, newName: string} objects
    """
    data = request.get_json() or {}

    renames = data.get('renames', [])
    if not renames:
        return jsonify({'success': True, 'references_updated': 0})

    with get_parser_for_modification() as p:
        total_refs_updated = 0

        for rename in renames:
            old_name = rename.get('oldName')
            new_name = rename.get('newName')
            if old_name and new_name and old_name != new_name:
                refs_updated = get_service().update_references(p.objects, old_name, new_name)
                total_refs_updated += refs_updated

        if total_refs_updated > 0:
            writer = NagiosConfigWriter()
            writer.write_objects_to_original_files(p.objects)

    # Reload config
    get_service().reload()

    return jsonify({
        'success': True,
        'references_updated': total_refs_updated
    })


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
