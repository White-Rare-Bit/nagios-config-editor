"""Shared helper functions for route blueprints."""

from flask import current_app, jsonify, request

from nagios_model import OperationResult
from server_config import ServerConfig


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
    return jsonify({"error": result.error or "Operation failed"}), error_code


def get_config_path() -> str:
    """Get current config path (shadow dir when active, original otherwise)."""
    service = current_app.extensions.get("service")
    if service:
        return service.config_path
    server_config = get_server_config()
    if server_config:
        return server_config.nagios_config_path
    return ""


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
        "nagios_config_path": server_config.nagios_config_path,
        "backup_path": server_config.backup_path,
        "nagios_bin": server_config.nagios_bin,
        "nagios_cfg": server_config.nagios_cfg,
    }


def get_service():
    """Get the NagiosService instance."""
    return current_app.extensions["service"]


def get_parser_for_modification():
    """Get parser with lock held for modification operations."""
    return get_service().modification_context()


def get_shadow_manager():
    """Get the shadow copy manager."""
    return current_app.extensions["shadow"]


def get_backup_manager():
    """Get the backup manager."""
    return current_app.extensions["backup"]


def get_git_service():
    """Get the git service."""
    return current_app.extensions["git"]



def get_audit_user_identity():
    """Get user identity for audit log entries.

    Checks request headers first (X-User-Name, X-User-Email),
    then falls back to JSON body for backward compatibility.
    Returns dict with userName and userEmail keys.
    """
    # Prefer headers (sent automatically by getStagingHeaders)
    user_name = request.headers.get("X-User-Name")
    user_email = request.headers.get("X-User-Email")

    # Fall back to request body
    if not user_name or not user_email:
        data = request.get_json(silent=True) or {}
        user_name = user_name or data.get("user_name") or data.get("userName")
        user_email = user_email or data.get("user_email") or data.get("userEmail")

    return {
        "userName": user_name,
        "userEmail": user_email,
    }


def format_audit_user(identity=None, *, name=None, email=None):
    """Format user identity for audit log entries as 'Name <email>'.

    Accepts either an identity dict (from get_audit_user_identity) or
    explicit name/email kwargs.
    """
    if identity:
        name = name or identity.get("userName")
        email = email or identity.get("userEmail")
    if name and email:
        return f"{name} <{email}>"
    return email or name or ""
