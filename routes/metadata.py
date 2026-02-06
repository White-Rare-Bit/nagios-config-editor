"""Metadata API - serves Nagios domain constants to the frontend."""

from flask import Blueprint, jsonify
from nagios_model import (
    NAME_FIELDS, REQUIRED_FIELDS, REFERENCE_FIELDS,
    VALID_ATTRIBUTES, OBJECT_TYPE_LABELS, DEFAULT_ATTRIBUTES,
    NOTIFICATION_OPTIONS, GROUP_STRUCTURE, SPECIAL_DIRECTIVES,
    ATTRIBUTE_SORT_ORDER
)

bp = Blueprint('metadata', __name__)


@bp.route('/api/metadata')
def api_metadata():
    """Serve all Nagios domain metadata as a single JSON payload.

    Called once at frontend startup. Eliminates the need for
    hardcoded domain constants in JavaScript.
    """
    return jsonify({
        'success': True,
        'data': {
            'name_fields': NAME_FIELDS,
            'required_fields': {
                obj_type: [
                    list(req) if isinstance(req, tuple) else req
                    for req in reqs
                ]
                for obj_type, reqs in REQUIRED_FIELDS.items()
            },
            'reference_fields': REFERENCE_FIELDS,
            'valid_attributes': VALID_ATTRIBUTES,
            'object_type_labels': OBJECT_TYPE_LABELS,
            'default_attributes': DEFAULT_ATTRIBUTES,
            'notification_options': NOTIFICATION_OPTIONS,
            'group_structure': GROUP_STRUCTURE,
            'special_directives': SPECIAL_DIRECTIVES,
            'attribute_sort_order': ATTRIBUTE_SORT_ORDER,
        }
    })
