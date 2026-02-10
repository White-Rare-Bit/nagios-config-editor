"""Template-specific routes for inheritance and validation."""

import base64

from flask import Blueprint, jsonify, request

from inheritance import build_type_template_lookup, resolve_chain

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

    template_lookup = build_type_template_lookup(service.get_objects(), obj_type)
    chain, inherited, errors = resolve_chain(target_obj, obj_type, template_lookup)

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
            obj.get_display_name() == obj_name):
            return obj, obj_type, None

    return None, None, (jsonify({"error": "Object not found"}), 404)


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
