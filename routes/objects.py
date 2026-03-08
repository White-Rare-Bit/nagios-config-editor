"""Object CRUD routes."""

from flask import Blueprint, jsonify, request

from .helpers import get_service

bp = Blueprint("objects", __name__)


@bp.route("/api/objects")
def api_objects():
    """Get objects, optionally filtered by type."""
    service = get_service()
    object_type = request.args.get("type")
    search = request.args.get("search", "")

    # Build list with global indices
    results = []
    for global_idx, obj in enumerate(service.get_objects()):
        if object_type and obj.object_type != object_type:
            continue
        if search and search.lower() not in obj.get_display_name().lower():
            continue
        obj_dict = obj.to_dict()
        obj_dict["global_index"] = global_idx
        results.append(obj_dict)

    return jsonify(results)


