"""Shared helper functions for route blueprints."""

from flask import current_app, request, jsonify
from server_config import ServerConfig
from nagios_model import OperationResult


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
        response = {'success': True}
        if success_data:
            response.update(success_data)
        if result.data is not None and 'data' not in response:
            response['data'] = result.data
        return jsonify(response)
    else:
        return jsonify({'error': result.error or 'Operation failed'}), error_code


def get_config_path() -> str:
    """Get current Nagios config path."""
    server_config = get_server_config()
    if server_config:
        return server_config.nagios_config_path
    return ''


def get_server_config() -> ServerConfig:
    """Get the server configuration object."""
    return current_app.extensions.get('server_config')


def get_config() -> dict:
    """Get the app config as a dict (backward compatibility).

    Returns a dict with the same keys as the old config dict format.
    """
    server_config = get_server_config()
    if not server_config:
        return {}
    return {
        'nagios_config_path': server_config.nagios_config_path,
        'backup_path': server_config.backup_path,
        'nagios_bin': server_config.nagios_bin,
        'nagios_cfg': server_config.nagios_cfg,
    }


def get_service():
    """Get the NagiosService instance."""
    return current_app.extensions['service']


def get_parser():
    """Get the config parser (read-only access)."""
    return get_service().parser


def get_parser_for_modification():
    """Get parser with lock held for modification operations."""
    return get_service().modification_context()


def get_staging_manager():
    """Get the staging manager."""
    return current_app.extensions['staging']


def get_backup_manager():
    """Get the backup manager."""
    return current_app.extensions['backup']


def get_git_service():
    """Get the git service."""
    return current_app.extensions['git']


def get_op_logger():
    """Get the operation logger."""
    return current_app.extensions.get('op_logger')


def get_audit_user_identity():
    """Get user identity for audit log entries.

    Checks request JSON body first, then staging data.
    Returns dict with userName and userEmail keys.
    """
    data = request.get_json(silent=True) or {}
    user_name = data.get('user_name') or data.get('userName')
    user_email = data.get('user_email') or data.get('userEmail')

    if not user_name or not user_email:
        try:
            sm = get_staging_manager()
            staging = sm.get_staging()
            if staging:
                user_name = user_name or staging.get('userName')
                user_email = user_email or staging.get('userEmail')
        except Exception:
            pass

    return {
        'userName': user_name,
        'userEmail': user_email
    }
