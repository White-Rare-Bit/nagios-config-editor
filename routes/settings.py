"""Settings and logging management routes."""

import os
import json
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app, send_file

from .helpers import (
    get_config,
    get_server_config,
    get_op_logger,
    get_staging_manager,
    get_service,
    get_backup_manager,
)
from operation_logger import LogConfig
from logging_config import save_config as save_logging_config
from server_config import save_config as save_server_config, update_config as update_server_config
from audit_service import (
    get_audit_log_dir,
    get_audit_log_path,
    rotate_audit_log,
)

bp = Blueprint('settings', __name__)


@bp.route('/api/settings', methods=['GET'])
def api_get_settings():
    """Get current settings."""
    server_config = get_server_config()
    if not server_config:
        return jsonify({})

    return jsonify({
        'nagios_config_path': server_config.nagios_config_path,
        'backup_path': server_config.backup_path,
        'nagios_bin': server_config.nagios_bin,
        'nagios_cfg': server_config.nagios_cfg,
    })


@bp.route('/api/settings', methods=['POST'])
def api_update_settings():
    """Update settings and persist to config/settings.json."""
    server_config = get_server_config()
    if not server_config:
        return jsonify({'error': 'Server config not initialized'}), 500

    data = request.get_json() or {}

    updated = []
    errors = []

    # Update config path
    if 'nagios_config_path' in data:
        path = data['nagios_config_path']
        if os.path.isdir(path):
            # F-05: Create all services BEFORE updating config to prevent inconsistent state
            # If any service fails to initialize, roll back entirely
            op_logger = get_op_logger()
            from staging_manager import StagingManager
            from nagios_service import NagiosService
            from backup_manager import BackupManager
            from git_service import GitService
            import file_operations

            normalized_path = os.path.abspath(path)
            old_config_path = server_config.paths.nagios_config_path

            try:
                # Create all services with new path (may fail if config is invalid)
                new_staging = StagingManager(normalized_path, op_logger=op_logger)
                new_service = NagiosService(normalized_path, new_staging, op_logger=op_logger)
                # Force parser initialization to catch config errors early
                _ = new_service.parser
                new_backup = BackupManager(normalized_path, server_config.backup_path, op_logger=op_logger)
                new_git = GitService(normalized_path, op_logger=op_logger)

                # All services created successfully - now safe to update config and extensions
                server_config.paths.nagios_config_path = normalized_path
                file_operations.set_logger(op_logger)
                current_app.extensions['service'] = new_service
                current_app.extensions['staging'] = new_staging
                current_app.extensions['backup'] = new_backup
                current_app.extensions['git'] = new_git

                updated.append('nagios_config_path')
            except Exception as e:
                # Service initialization failed - config remains unchanged
                errors.append(f'Failed to initialize services for path: {e}')
        else:
            errors.append(f'Invalid directory: {path}')

    # Update backup path
    if 'backup_path' in data:
        path = data['backup_path']
        if path and not os.path.isdir(path):
            try:
                os.makedirs(path, exist_ok=True)
            except OSError as e:
                errors.append(f'Cannot create backup directory: {e}')
        if not errors or 'backup' not in str(errors[-1]):
            server_config.paths.backup_path = path or None

            # Reinitialize backup manager with new path
            op_logger = get_op_logger()
            from backup_manager import BackupManager
            backup_manager = BackupManager(server_config.nagios_config_path, server_config.backup_path, op_logger=op_logger)
            current_app.extensions['backup'] = backup_manager

            updated.append('backup_path')

    # Update Nagios binary path
    if 'nagios_bin' in data:
        path = data['nagios_bin']
        server_config.paths.nagios_bin = path
        updated.append('nagios_bin')

    # Update Nagios config file path
    if 'nagios_cfg' in data:
        path = data['nagios_cfg']
        server_config.paths.nagios_cfg = path
        updated.append('nagios_cfg')

    # Persist changes to config/settings.json
    if updated and not errors:
        try:
            save_server_config(server_config)
        except Exception as e:
            errors.append(f'Failed to save config: {e}')

    return jsonify({
        'success': len(errors) == 0,
        'updated': updated,
        'errors': errors,
        'config': {
            'nagios_config_path': server_config.nagios_config_path,
            'backup_path': server_config.backup_path,
            'nagios_bin': server_config.nagios_bin,
            'nagios_cfg': server_config.nagios_cfg,
        }
    })


@bp.route('/api/settings/browse', methods=['POST'])
def api_browse_directory():
    """List contents of a directory for browsing."""
    data = request.get_json() or {}
    path = data.get('path', '/')

    if not os.path.isabs(path):
        path = os.path.abspath(path)

    path = os.path.normpath(path)

    if '..' in path.split(os.sep):
        return jsonify({'error': 'Invalid path'}), 400

    if not os.path.isdir(path):
        return jsonify({'error': 'Not a valid directory'}), 400

    try:
        entries = []
        for entry in os.scandir(path):
            try:
                entries.append({
                    'name': entry.name,
                    'path': entry.path,
                    'is_dir': entry.is_dir(),
                    'is_file': entry.is_file()
                })
            except PermissionError:
                continue

        entries.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))

        return jsonify({
            'path': path,
            'parent': os.path.dirname(path) if path != '/' else None,
            'entries': entries
        })
    except PermissionError:
        return jsonify({'error': 'Permission denied'}), 403


@bp.route('/api/settings/logging', methods=['GET'])
def api_get_logging_settings():
    """Get logging configuration and file info."""
    op_logger = get_op_logger()
    if not op_logger:
        return jsonify({'error': 'Logger not initialized'}), 500

    cfg = op_logger.config
    return jsonify({
        'enabled': cfg.enabled,
        'log_level': cfg.level,
        'log_dir': cfg.log_dir,
        'log_filename': cfg.filename,
        'max_file_size_mb': cfg.max_size_mb,
        'max_backup_files': cfg.max_backup_files,
        'log_file_path': str(op_logger.get_log_file_path()),
        'log_file_size': op_logger.get_log_file_size(),
        'rotated_files': [str(f) for f in op_logger.get_rotated_files()]
    })


@bp.route('/api/settings/logging', methods=['POST'])
def api_update_logging_settings():
    """Update logging configuration, persist, and reconfigure."""
    op_logger = get_op_logger()
    if not op_logger:
        return jsonify({'error': 'Logger not initialized'}), 500

    data = request.get_json() or {}
    new_config = LogConfig(
        level=data.get('log_level', op_logger.config.level),
        log_dir=data.get('log_dir', op_logger.config.log_dir),
        filename=data.get('log_filename', op_logger.config.filename),
        max_size_mb=data.get('max_file_size_mb', op_logger.config.max_size_mb),
        max_backup_files=data.get('max_backup_files', op_logger.config.max_backup_files),
        enabled=data.get('enabled', op_logger.config.enabled),
    )

    # Update in-memory server config
    server_config = get_server_config()
    if server_config:
        server_config.logging.enabled = new_config.enabled
        server_config.logging.log_level = new_config.level
        server_config.logging.log_dir = new_config.log_dir
        server_config.logging.log_filename = new_config.filename
        server_config.logging.max_file_size_mb = new_config.max_size_mb
        server_config.logging.max_backup_files = new_config.max_backup_files

    # Persist to config/settings.json
    save_logging_config(new_config)
    op_logger.reconfigure(new_config)

    return jsonify({'success': True, 'config': {
        'enabled': new_config.enabled,
        'log_level': new_config.level,
        'log_dir': new_config.log_dir,
        'log_filename': new_config.filename,
        'max_file_size_mb': new_config.max_size_mb,
        'max_backup_files': new_config.max_backup_files,
    }})


@bp.route('/api/logs/operations', methods=['GET'])
def api_get_operation_logs():
    """Read recent log entries with optional filtering."""
    op_logger = get_op_logger()
    if not op_logger:
        return jsonify({'error': 'Logger not initialized'}), 500

    limit = request.args.get('limit', 100, type=int)
    level_filter = request.args.get('level', '').upper()

    log_path = op_logger.get_log_file_path()
    if not log_path.exists():
        return jsonify({'entries': [], 'total': 0})

    entries = []
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if level_filter and entry.get('level') != level_filter:
                    continue
                entries.append(entry)
                if len(entries) >= limit:
                    break
            except json.JSONDecodeError:
                continue
    except OSError:
        pass

    return jsonify({'entries': entries, 'total': len(lines) if 'lines' in dir() else 0})


@bp.route('/api/logs/operations/download', methods=['GET'])
def api_download_operation_logs():
    """Download the full log file."""
    op_logger = get_op_logger()
    if not op_logger:
        return jsonify({'error': 'Logger not initialized'}), 500

    log_path = op_logger.get_log_file_path()
    if not log_path.exists():
        return jsonify({'error': 'Log file not found'}), 404

    return send_file(str(log_path), mimetype='application/x-ndjson',
                     as_attachment=True, download_name=log_path.name)


@bp.route('/api/logs/frontend', methods=['POST'])
def api_frontend_log():
    """Receive debug logs from frontend and write to file."""
    import logging
    logger = logging.getLogger('nagios_bulk_editor.frontend')

    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # Handle both single log entry (dict) and batch entries (list)
    entries = data if isinstance(data, list) else [data]

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        level = entry.get('level', 'debug').lower()
        message = entry.get('message', '')
        context = entry.get('context', {})

        log_message = f"[frontend] {message}"
        if context:
            log_message += f" | context: {json.dumps(context)}"

        if level == 'error':
            logger.error(log_message)
        elif level == 'warning':
            logger.warning(log_message)
        elif level == 'info':
            logger.info(log_message)
        else:
            logger.debug(log_message)

    return jsonify({'success': True})


@bp.route('/api/audit-log', methods=['GET'])
def api_get_audit_log():
    """Get the audit log."""
    config_dir = current_app.config.get('CONFIG_DIR', os.path.dirname(os.path.abspath(__file__)))
    audit_path = get_audit_log_path(config_dir)
    if not os.path.exists(audit_path):
        return jsonify({'entries': []})

    try:
        with open(audit_path, 'r') as f:
            data = json.load(f)
        return jsonify(data)
    except (IOError, OSError, json.JSONDecodeError) as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/api/audit-log', methods=['POST'])
def api_save_audit_log():
    """Save an audit log entry."""
    config_dir = current_app.config.get('CONFIG_DIR', os.path.dirname(os.path.abspath(__file__)))
    audit_path = get_audit_log_path(config_dir)

    try:
        entries = []
        if os.path.exists(audit_path):
            with open(audit_path, 'r') as f:
                data = json.load(f)
                entries = data.get('entries', [])

        new_entry = request.json
        entries.append(new_entry)

        entries = rotate_audit_log(entries)

        with open(audit_path, 'w') as f:
            json.dump({'entries': entries}, f, indent=2)

        return jsonify({'success': True})
    except (IOError, OSError, json.JSONDecodeError) as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/api/audit-log/clear', methods=['POST'])
def api_clear_audit_log():
    """Clear the audit log."""
    config_dir = current_app.config.get('CONFIG_DIR', os.path.dirname(os.path.abspath(__file__)))
    audit_path = get_audit_log_path(config_dir)

    try:
        with open(audit_path, 'w') as f:
            json.dump({'entries': []}, f)
        return jsonify({'success': True})
    except (IOError, OSError) as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/api/audit-log/archives', methods=['GET'])
def api_list_audit_archives():
    """List all archived audit log files."""
    config_dir = current_app.config.get('CONFIG_DIR', os.path.dirname(os.path.abspath(__file__)))
    log_dir = get_audit_log_dir(config_dir)

    archives = []
    try:
        for filename in os.listdir(log_dir):
            if filename.startswith('audit_log_') and filename.endswith('.json'):
                filepath = os.path.join(log_dir, filename)
                stat = os.stat(filepath)
                archives.append({
                    'filename': filename,
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat()
                })

        archives.sort(key=lambda x: x['filename'], reverse=True)

        return jsonify({'archives': archives})
    except (IOError, OSError) as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/api/audit-log/archives/<filename>', methods=['GET'])
def api_get_audit_archive(filename):
    """Get a specific archived audit log."""
    if not filename.startswith('audit_log_') or not filename.endswith('.json'):
        return jsonify({'error': 'Invalid archive filename'}), 400
    if '/' in filename or '\\' in filename or '..' in filename:
        return jsonify({'error': 'Invalid archive filename'}), 400

    log_dir = get_audit_log_dir()
    filepath = os.path.join(log_dir, filename)

    if not os.path.exists(filepath):
        return jsonify({'error': 'Archive not found'}), 404

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify(data)
    except (IOError, OSError, json.JSONDecodeError) as e:
        return jsonify({'error': str(e)}), 500
