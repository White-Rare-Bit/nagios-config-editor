"""Template-specific routes for inheritance and validation."""

import base64

from flask import Blueprint, jsonify, request

from .helpers import get_service

bp = Blueprint("templates", __name__)


@bp.route("/api/templates")
def list_templates():
    """List all templates grouped by object type."""
    service = get_service()
    templates_by_type = {}

    for obj in service.get_objects():
        if obj.attributes.get("register", "1") == "0":
            obj_type = obj.object_type
            if obj_type not in templates_by_type:
                templates_by_type[obj_type] = []
            templates_by_type[obj_type].append(obj.to_dict())

    return jsonify(templates_by_type)


@bp.route("/api/templates/inheritance/<stable_key>")
def get_inheritance(stable_key):
    """Get inheritance chain for an object by stable key.

    The stable_key is base64-encoded "source_file|object_type|name" to handle
    special characters (pipes, slashes) in file paths and object names.
    """
    service = get_service()

    target_obj, obj_type, error = _decode_and_find_object(service, stable_key)
    if error:
        return error

    template_lookup = _build_template_lookup(service, obj_type)
    chain, inherited, errors = _resolve_chain(target_obj, obj_type, template_lookup)

    return jsonify({"chain": chain, "inherited": inherited, "errors": errors})


def _decode_and_find_object(service, stable_key):
    """Decode a base64 stable key and find the matching object.

    Returns:
        Tuple of (target_obj, obj_type, error_response).
        If error_response is not None, target_obj and obj_type are None.

    """
    if not stable_key:
        return None, None, (jsonify({"error": "stable_key parameter required"}), 400)

    try:
        decoded_key = base64.b64decode(stable_key).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None, None, (jsonify({"error": "Invalid stable key encoding"}), 400)

    try:
        source_file, obj_type, obj_name = decoded_key.split("|", 2)
    except ValueError:
        return None, None, (jsonify({"error": "Invalid stable key format"}), 400)

    for obj in service.get_objects():
        if (obj.source_file == source_file and
            obj.object_type == obj_type and
            obj.get_name() == obj_name):
            return obj, obj_type, None

    return None, None, (jsonify({"error": "Object not found"}), 404)


def _build_template_lookup(service, obj_type):
    """Build a name-to-object lookup for templates of a given type."""
    lookup = {}
    for obj in service.get_objects():
        if obj.object_type == obj_type and obj.attributes.get("name"):
            lookup[obj.attributes["name"]] = obj
    return lookup


def _resolve_chain(obj, obj_type, template_lookup, visited=None):
    """Recursively resolve template inheritance chain.

    Nagios inheritance: comma-separated templates apply left-to-right,
    with later templates overriding earlier ones.

    Returns:
        Tuple of (chain, inherited, errors).

    """
    if visited is None:
        visited = set()

    chain = []
    inherited = {}
    errors = []

    use_value = obj.attributes.get("use", "")
    if use_value:
        ctx = {"obj_type": obj_type, "lookup": template_lookup, "visited": visited}
        _resolve_use_templates(use_value, ctx, chain, inherited, errors)

    # Object's own attributes override inherited
    obj_name = obj.get_name() or obj.attributes.get("name", "(unknown)")
    for key, value in obj.attributes.items():
        if key not in ["use", "name", "register"]:
            inherited[key] = {"value": value, "source": obj_name}

    return chain, inherited, errors


def _resolve_use_templates(use_value, ctx, chain, inherited, errors):
    """Process 'use' directive templates and merge into chain/inherited/errors.

    Args:
        use_value: Comma-separated template names string
        ctx: Dict with 'obj_type', 'lookup' (template_lookup), 'visited' set
        chain, inherited, errors: Accumulator lists/dicts (modified in place)

    """
    obj_type = ctx["obj_type"]
    template_lookup = ctx["lookup"]
    visited = ctx["visited"]
    template_names = [t.strip() for t in use_value.split(",") if t.strip()]

    for tmpl_name in template_names:
        if tmpl_name not in template_lookup:
            errors.append(f"Template '{tmpl_name}' not found for type '{obj_type}'")
            continue
        if tmpl_name in visited:
            errors.append(f"Circular dependency: {' -> '.join(visited)} -> {tmpl_name}")
            continue

        visited.add(tmpl_name)
        tmpl_obj = template_lookup[tmpl_name]
        tmpl_chain, tmpl_inherited, tmpl_errors = _resolve_chain(
            tmpl_obj, obj_type, template_lookup, visited,
        )

        for key, entry in tmpl_inherited.items():
            if key not in ["use", "name", "register"]:
                inherited[key] = entry

        chain.append({"name": tmpl_name, "type": obj_type, "attributes": tmpl_obj.attributes})
        chain.extend(tmpl_chain)
        errors.extend(tmpl_errors)

        # Allow reuse in sibling branches (A uses B,C where both use D)
        visited.discard(tmpl_name)


@bp.route("/api/templates/validate-use")
def validate_use():
    """Check if use references exist for given object type."""
    obj_type = request.args.get("object_type", "")
    use_string = request.args.get("use", "")

    if not obj_type or not use_string:
        return jsonify({"error": "object_type and use parameters required"}), 400

    service = get_service()

    # Build template lookup for this object type
    template_names = set()
    for obj in service.get_objects():
        if obj.object_type == obj_type and obj.attributes.get("register", "1") == "0":
            name = obj.attributes.get("name")
            if name:
                template_names.add(name)

    # Check each template in use string
    errors = []
    use_list = [t.strip() for t in use_string.split(",") if t.strip()]

    for tmpl_name in use_list:
        if tmpl_name not in template_names:
            errors.append(f"Template '{tmpl_name}' not found for type '{obj_type}'")

    return jsonify({
        "valid": len(errors) == 0,
        "errors": errors,
    })
