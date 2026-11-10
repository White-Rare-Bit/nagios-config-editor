"""Template-specific routes for inheritance and validation."""

import base64

from flask import Blueprint, jsonify, request

from ..inheritance import build_type_template_lookup, resolve_chain
from ..nagios_model import is_template_object

from .helpers import get_service
from .mutation import ApiError

bp = Blueprint("templates", __name__)


@bp.route("/api/templates")
def list_templates():
    """List all templates grouped by object type."""
    service = get_service()
    templates_by_type = {}

    for obj in service.get_objects():
        if is_template_object(obj):
            obj_type = obj.object_type
            if obj_type not in templates_by_type:
                templates_by_type[obj_type] = []
            templates_by_type[obj_type].append(obj.to_dict())

    return jsonify(templates_by_type)


@bp.route("/api/templates/inheritance")
@bp.route("/api/templates/inheritance/<stable_key>")
def get_inheritance(stable_key=None):
    """Get inheritance chain for an object by stable key.

    The stable_key is "source_file|object_type|name", either as is or
    base64-encoded. The client sends the plain key as ``?key=``: a path
    segment cannot carry it (an absolute file path starts with a slash, which
    Flask's routing would reject or merge). The base64 path form stays for
    older callers.
    """
    service = get_service()
    if stable_key is None:
        stable_key = request.args.get("key", "")

    target_obj, obj_type = _decode_and_find_object(service, stable_key)

    template_lookup = build_type_template_lookup(service.get_objects(), obj_type)
    chain, inherited, errors = resolve_chain(target_obj, obj_type, template_lookup)

    return jsonify({"chain": chain, "inherited": inherited, "errors": errors})


def _decode_and_find_object(service, stable_key):
    """Find the object for a plain or base64-encoded stable key.

    Returns:
        Tuple of (target_obj, obj_type).

    Raises:
        ApiError: 400 for a missing or undecodable key, 404 for no such object.

    """
    if not stable_key:
        raise ApiError("stable_key parameter required", 400)

    # A plain key always contains "|"; the base64 alphabet has none.
    decoded_key = stable_key
    if "|" not in stable_key:
        try:
            decoded_key = base64.b64decode(stable_key).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            raise ApiError("Invalid stable key encoding", 400) from None

    result = service.find_object_by_stable_key(decoded_key)
    if result is None:
        raise ApiError("Object not found", 404)

    _, obj = result
    return obj, obj.object_type


