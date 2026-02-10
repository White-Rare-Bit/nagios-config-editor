"""Validation and health-check routes."""

from flask import Blueprint, jsonify

from nagios_model import NAME_FIELDS, REFERENCE_FIELDS, REQUIRED_FIELDS
from validator import NagiosValidator

from .helpers import get_config, get_service

bp = Blueprint("validation", __name__)


@bp.route("/api/reload", methods=["POST"])
def api_reload():
    """Reload configuration from disk."""
    service = get_service()
    p = service.reload()
    return jsonify({
        "success": True,
        "objects": len(service.get_objects()),
        "files": len(p.files_parsed),
    })


@bp.route("/api/summary")
def api_summary():
    """Get configuration summary."""
    service = get_service()
    p = service.parser
    return jsonify({
        "summary": p.get_summary(),
        "files": p.get_files(),
        "total_objects": len(service.get_objects()),
    })


@bp.route("/api/validate", methods=["POST"])
def api_validate():
    """Validate Nagios configuration."""
    config = get_config()
    validator = NagiosValidator(config["nagios_bin"], config["nagios_cfg"])
    result = validator.validate()
    return jsonify(result.to_dict())


@bp.route("/api/validate/check", methods=["GET"])
def api_validate_check():
    """Check if Nagios binary is available and valid.

    Returns verification status including:
    - Whether binary exists and is executable
    - Whether binary is actually Nagios (verified via version check)
    - Version string if verification succeeded
    """
    config = get_config()
    validator = NagiosValidator(config["nagios_bin"], config["nagios_cfg"])

    # First check existence
    exists, exists_message = validator.check_binary_exists()

    # If binary exists, verify it's actually Nagios
    verified = False
    version = None
    verify_message = exists_message

    if exists:
        result = validator.verify_binary()
        verified = result.success
        version = result.data
        verify_message = result.error or "Valid Nagios binary"

    return jsonify({
        "available": exists,
        "verified": verified,
        "version": version,
        "message": verify_message,
        "nagios_bin": config["nagios_bin"],
        "nagios_cfg": config["nagios_cfg"],
    })


@bp.route("/api/constants")
def api_constants():
    """Return domain metadata constants (single source of truth)."""
    # Convert REQUIRED_FIELDS tuples to lists for JSON serialization
    required_fields_json = {}
    for obj_type, reqs in REQUIRED_FIELDS.items():
        converted = []
        for req in reqs:
            if isinstance(req, tuple):
                converted.append(list(req))  # OR condition
            else:
                converted.append(req)
        required_fields_json[obj_type] = converted

    return jsonify({
        "name_fields": NAME_FIELDS,
        "required_fields": required_fields_json,
        "reference_fields": REFERENCE_FIELDS,
    })


@bp.route("/api/health-check")
def api_health_check():
    """Analyze configuration for potential issues."""
    from .health_checks import build_template_lookup, run_all_checks

    service = get_service()
    p = service.parser
    objects = p.objects

    obj_to_index = {id(obj): idx for idx, obj in enumerate(objects)}
    template_lookup = build_template_lookup(objects)

    issues = run_all_checks(objects, obj_to_index, template_lookup)

    summary = {
        "total_issues": len(issues),
        "errors": len([i for i in issues if i["severity"] == "error"]),
        "warnings": len([i for i in issues if i["severity"] == "warning"]),
        "info": len([i for i in issues if i["severity"] == "info"]),
    }

    return jsonify({
        "issues": issues,
        "summary": summary,
    })


@bp.route("/api/analysis/orphans")
def api_analysis_orphans():
    """Detect orphan objects - objects not referenced by any other object.

    An orphan is a non-template object whose name does not appear in any
    reference field of any other object. Special cases:
    - Hosts with 'hostgroups' attr (direct or inherited) are considered in-use
    - Services with 'host_name' or 'hostgroup_name' (direct or inherited) are in-use
    - Services with 'servicegroups' attr (direct or inherited) are in-use
    - Templates (register=0) are excluded from analysis entirely
    """
    from .health_checks import build_template_lookup, detect_orphans

    service = get_service()
    objects = service.get_objects()
    template_lookup = build_template_lookup(objects)

    orphan_indices, by_type, _ = detect_orphans(objects, template_lookup)

    return jsonify({
        "orphan_indices": orphan_indices,
        "summary": {
            "total_orphans": len(orphan_indices),
            "by_type": by_type,
        },
    })


@bp.route("/api/analysis/template-suggestions")
def api_analysis_template_suggestions():
    """Suggest template consolidation opportunities.

    Finds groups of 3+ objects of the same type that share identical
    non-identity attributes and don't already use a template.
    """
    service = get_service()
    objects = service.get_objects()

    identity_fields = {
        "host_name", "service_description", "name", "contact_name",
        "alias", "address", "hostgroup_name", "servicegroup_name",
        "contactgroup_name", "command_name", "timeperiod_name",
    }

    objects_by_type = {}
    for idx, obj in enumerate(objects):
        objects_by_type.setdefault(obj.object_type, []).append((idx, obj))

    suggestions = []
    for obj_type, type_entries in objects_by_type.items():
        if len(type_entries) < 3 or obj_type in ("timeperiod", "command"):  # noqa: PLR2004
            continue
        signatures = _build_type_signatures(type_entries, identity_fields)
        _collect_suggestions(obj_type, signatures, suggestions)

    suggestions.sort(key=lambda s: s["count"] * s["attr_count"], reverse=True)
    return jsonify({"suggestions": suggestions})


def _build_type_signatures(type_entries, identity_fields):
    """Build attribute signatures for objects that could share a template."""
    signatures = {}
    for idx, obj in type_entries:
        if obj.attributes.get("use") or obj.attributes.get("register") == "0":
            continue
        attr_pairs = []
        for key, value in sorted(obj.attributes.items()):
            if key not in identity_fields and key != "register":
                attr_pairs.append(f"{key}={value}")
        if not attr_pairs:
            continue
        signature = "|".join(attr_pairs)
        signatures.setdefault(signature, []).append((idx, obj))
    return signatures


def _collect_suggestions(obj_type, signatures, suggestions):
    """Convert matching signature groups into template suggestions."""
    for signature, matching_entries in signatures.items():
        if len(matching_entries) < 3:  # noqa: PLR2004
            continue
        attrs = _parse_signature(signature)
        matching_objects = [obj for _, obj in matching_entries]
        suggested_name = _generate_template_name(obj_type, matching_objects, attrs)
        suggestions.append({
            "type": obj_type,
            "suggested_name": suggested_name,
            "attributes": attrs,
            "object_indices": [idx for idx, _ in matching_entries],
            "count": len(matching_entries),
            "attr_count": len(attrs),
        })


def _parse_signature(signature):
    """Parse a pipe-delimited key=value signature back to a dict."""
    attrs = {}
    for pair in signature.split("|"):
        eq_idx = pair.index("=")
        attrs[pair[:eq_idx]] = pair[eq_idx + 1:]
    return attrs


def _generate_template_name(obj_type, objects, attrs):
    """Generate a suggested template name from object patterns.

    Delegates to the canonical implementation in health_checks to avoid duplication.
    Kept as a module-level function for backward compatibility.
    """
    from .health_checks import _generate_template_name as _impl
    return _impl(obj_type, objects, attrs)
