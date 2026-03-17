"""Validation and health-check routes."""

from flask import Blueprint, jsonify

from ..validator import NagiosValidator

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


@bp.route("/api/health-check")
def api_health_check():
    """Analyze configuration for potential issues."""
    from ..inheritance import build_template_lookup
    from .health_checks import run_all_checks
    from .helpers import get_server_config

    service = get_service()
    p = service.parser
    objects = p.objects

    obj_to_index = {id(obj): idx for idx, obj in enumerate(objects)}
    template_lookup = build_template_lookup(objects)

    server_config = get_server_config()
    config_paths = {}
    if server_config:
        config_paths["nagios_cfg"] = server_config.nagios_cfg
        if hasattr(server_config.paths, "resource_cfg"):
            config_paths["resource_cfg"] = server_config.paths.resource_cfg

    issues = run_all_checks(objects, obj_to_index, template_lookup, config_paths=config_paths)

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


