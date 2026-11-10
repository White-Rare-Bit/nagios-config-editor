"""Shared helper functions for route blueprints."""

import os

from flask import current_app, jsonify, request

from ..nagios_model import OperationResult
from ..server_config import ServerConfig


def operation_response(result: OperationResult, success_data: dict = None, error_code: int = 500):
    """Convert OperationResult to Flask JSON response.

    Args:
        result: OperationResult from service method
        success_data: Additional data to include on success (merged with {'success': True})
        error_code: HTTP status code on error (default 500)

    Returns:
        Flask Response tuple (jsonify, status_code)

    Example:
        result = service.create_object(...)
        return operation_response(result, {'path': file_path, 'staged': True})

    """
    if result.success:
        response = {"success": True}
        if success_data:
            response.update(success_data)
        if result.data is not None and "data" not in response:
            response["data"] = result.data
        return jsonify(response)
    return jsonify({"success": False, "error": result.error or "Operation failed"}), error_code


def get_config_roots() -> list[str]:
    """Get list of active config directory paths."""
    service = current_app.extensions.get("service")
    if service:
        return service.cfg_dirs
    return []


def get_config_path() -> str:
    """Get primary config path (first cfg_dir, backward compat)."""
    service = current_app.extensions.get("service")
    if service:
        return service.config_path
    return ""


def make_relative_path(path, config_path):
    """Convert an absolute path to a path relative to the config directory's parent.

    For config_path=/etc/nagios/objects and path=/etc/nagios/objects/hosts.cfg,
    returns "objects/hosts.cfg". This preserves the config dir name while
    stripping server filesystem structure from audit logs.
    """
    if not path:
        return path
    if config_path and (path == config_path or path.startswith(config_path + os.sep)):
        return os.path.relpath(path, os.path.dirname(config_path))
    return path


def audit_file_path(source_file):
    """Convert a config file path to a display path for audit logs.

    Makes the path relative to the parent of the config root it is in
    (e.g. "objects/hosts.cfg"), whichever root that is. Shadow paths are
    accepted too and reported as the original file they stand for.
    """
    if not source_file:
        return source_file
    logical = get_shadow_manager().logical_path(source_file)
    for root in sorted(get_config_roots(), key=len, reverse=True):
        relative = make_relative_path(logical, root)
        if relative != logical:
            return relative
    return logical


def get_server_config() -> ServerConfig:
    """Get the server configuration object."""
    return current_app.extensions.get("server_config")


def get_config() -> dict:
    """Get the app config as a dict (backward compatibility).

    Returns a dict with the same keys as the old config dict format.
    """
    server_config = get_server_config()
    if not server_config:
        return {}
    return {
        "backup_path": server_config.backup_path,
        "nagios_bin": server_config.nagios_bin,
        "nagios_cfg": server_config.nagios_cfg,
    }


def get_service():
    """Get the NagiosService instance."""
    return current_app.extensions["service"]


def get_shadow_manager():
    """Get the shadow copy manager."""
    return current_app.extensions["shadow"]


def get_backup_manager():
    """Get the backup manager."""
    return current_app.extensions["backup"]


def get_git_service():
    """Get the git service."""
    return current_app.extensions["git"]



# Env var naming a request header that a trusted reverse proxy sets to the
# authenticated user (e.g. Apache: RequestHeader set X-Remote-User %{REMOTE_USER}s).
# Read from the environment only, so it can't be switched on or off from the
# settings page by the users it is meant to identify.
TRUSTED_USER_HEADER_ENV = "NBE_TRUSTED_USER_HEADER"


def get_audit_user_identity():
    """Get user identity for audit log entries.

    Checks request headers first (X-User-Name, X-User-Email),
    then falls back to JSON body for backward compatibility.
    Returns dict with userName and userEmail keys. Those are whatever the
    browser claims; when NBE_TRUSTED_USER_HEADER is set, the dict also has
    verifiedUser (the proxy's header value, "" if absent), which
    format_audit_user prefers.
    """
    # Prefer headers (sent automatically by getStagingHeaders)
    user_name = request.headers.get("X-User-Name")
    user_email = request.headers.get("X-User-Email")

    # Fall back to request body
    if not user_name or not user_email:
        data = request.get_json(silent=True) or {}
        user_name = user_name or data.get("user_name") or data.get("userName")
        user_email = user_email or data.get("user_email") or data.get("userEmail")

    identity = {
        "userName": user_name,
        "userEmail": user_email,
    }
    trusted_header = os.environ.get(TRUSTED_USER_HEADER_ENV, "").strip()
    if trusted_header:
        identity["verifiedUser"] = request.headers.get(trusted_header, "").strip()
    return identity


def format_audit_user(identity=None, *, name=None, email=None):
    """Format user identity for audit log entries as 'Name <email>'.

    Accepts either an identity dict (from get_audit_user_identity) or
    explicit name/email kwargs.
    """
    if identity:
        if identity.get("verifiedUser"):
            return identity["verifiedUser"]
        name = name or identity.get("userName")
        email = email or identity.get("userEmail")
    claimed = f"{name} <{email}>" if name and email else (email or name or "")
    if identity and "verifiedUser" in identity:
        # Trusted header configured but missing: the request didn't come
        # through the authenticating proxy, so the claim can't be relied on.
        return f"unverified: {claimed}"
    return claimed
