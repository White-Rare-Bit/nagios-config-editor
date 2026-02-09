"""Template-specific routes for inheritance and validation."""

import base64
from flask import Blueprint, request, jsonify
from .helpers import get_service

bp = Blueprint('templates', __name__)


@bp.route('/api/templates')
def list_templates():
    """List all templates grouped by object type."""
    service = get_service()
    templates_by_type = {}

    for obj in service.get_objects():
        if obj.attributes.get('register', '1') == '0':
            obj_type = obj.object_type
            if obj_type not in templates_by_type:
                templates_by_type[obj_type] = []
            templates_by_type[obj_type].append(obj.to_dict())

    return jsonify(templates_by_type)


@bp.route('/api/templates/inheritance/<stable_key>')
def get_inheritance(stable_key):
    """Get inheritance chain for an object by stable key.

    The stable_key is base64-encoded "source_file|object_type|name" to handle
    special characters (pipes, slashes) in file paths and object names.
    """
    service = get_service()

    # Validate stable_key parameter
    if not stable_key:
        return jsonify({'error': 'stable_key parameter required'}), 400

    # Decode base64 stable key to handle special characters in paths
    try:
        decoded_key = base64.b64decode(stable_key).decode('utf-8')
    except Exception:
        return jsonify({'error': 'Invalid stable key encoding'}), 400

    # Parse stable key: "source_file|object_type|name"
    try:
        source_file, obj_type, obj_name = decoded_key.split('|', 2)
    except ValueError:
        return jsonify({'error': 'Invalid stable key format'}), 400

    # Find target object
    target_obj = None
    for obj in service.get_objects():
        if (obj.source_file == source_file and
            obj.object_type == obj_type and
            obj.get_name() == obj_name):
            target_obj = obj
            break

    if not target_obj:
        return jsonify({'error': 'Object not found'}), 404

    # Build template lookup for this object type
    template_lookup = {}
    for obj in service.get_objects():
        if obj.object_type == obj_type and obj.attributes.get('name'):
            template_lookup[obj.attributes['name']] = obj

    def get_obj_display_name(obj):
        """Get display name for source attribution."""
        return obj.get_name() or obj.attributes.get('name', '(unknown)')

    def resolve_chain(obj, visited=None):
        """Recursively resolve template inheritance chain.

        Uses shared visited set to detect circular dependencies.
        Nagios inheritance: comma-separated templates apply left-to-right,
        with later templates overriding earlier ones.

        Returns inherited as {attr: {value, source}} for source tracking.
        """
        if visited is None:
            visited = set()

        chain = []
        inherited = {}
        errors = []
        obj_name = get_obj_display_name(obj)

        use_value = obj.attributes.get('use', '')
        if use_value:
            template_names = [t.strip() for t in use_value.split(',') if t.strip()]

            for tmpl_name in template_names:
                # Check for missing template
                if tmpl_name not in template_lookup:
                    errors.append(f"Template '{tmpl_name}' not found for type '{obj_type}'")
                    continue

                # Check for circular dependency
                if tmpl_name in visited:
                    errors.append(f"Circular dependency: {' -> '.join(visited)} -> {tmpl_name}")
                    continue

                # Add to visited set before recursion to detect cycles
                visited.add(tmpl_name)
                tmpl_obj = template_lookup[tmpl_name]

                # Recursively resolve template's chain
                tmpl_chain, tmpl_inherited, tmpl_errors = resolve_chain(tmpl_obj, visited)

                # Merge inherited attributes (later templates override earlier)
                for key, entry in tmpl_inherited.items():
                    if key not in ['use', 'name', 'register']:
                        inherited[key] = entry

                # Add template to chain
                chain.append({
                    'name': tmpl_name,
                    'type': obj_type,
                    'attributes': tmpl_obj.attributes
                })

                # Merge template's chain
                chain.extend(tmpl_chain)
                errors.extend(tmpl_errors)

                # Remove from visited after processing to allow reuse in sibling branches
                # Example: A uses B,C where both B and C use D - D should be processable twice
                visited.discard(tmpl_name)

        # Object's own attributes override inherited
        for key, value in obj.attributes.items():
            if key not in ['use', 'name', 'register']:
                inherited[key] = {'value': value, 'source': obj_name}

        return chain, inherited, errors

    chain, inherited, errors = resolve_chain(target_obj)

    return jsonify({
        'chain': chain,
        'inherited': inherited,
        'errors': errors
    })


@bp.route('/api/templates/validate-use')
def validate_use():
    """Check if use references exist for given object type."""
    obj_type = request.args.get('object_type', '')
    use_string = request.args.get('use', '')

    if not obj_type or not use_string:
        return jsonify({'error': 'object_type and use parameters required'}), 400

    service = get_service()

    # Build template lookup for this object type
    template_names = set()
    for obj in service.get_objects():
        if obj.object_type == obj_type and obj.attributes.get('register', '1') == '0':
            name = obj.attributes.get('name')
            if name:
                template_names.add(name)

    # Check each template in use string
    errors = []
    use_list = [t.strip() for t in use_string.split(',') if t.strip()]

    for tmpl_name in use_list:
        if tmpl_name not in template_names:
            errors.append(f"Template '{tmpl_name}' not found for type '{obj_type}'")

    return jsonify({
        'valid': len(errors) == 0,
        'errors': errors
    })
