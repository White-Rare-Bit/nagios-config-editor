"""Git integration routes."""

from datetime import datetime
from flask import Blueprint, request, jsonify
from file_operations import is_safe_path
from staging_manager import StagingStatus
from audit_service import write_audit_log
from .helpers import (
    get_git_service,
    get_staging_manager,
    get_backup_manager,
    get_op_logger,
    get_config_path,
    get_service,
    get_audit_user_identity
)

bp = Blueprint('git', __name__)


def _check_staging_lock(session_id, op_log=None, operation='git'):
    """Check if staging is locked by another session.

    Returns:
        Error response tuple (jsonify, status_code) if locked, or None if OK.
    """
    if not session_id:
        return None
    staging_mgr = get_staging_manager()
    lock_owner = staging_mgr.get_lock_owner()
    if lock_owner and lock_owner != session_id:
        if op_log:
            op_log.warning('git', operation, session_id=session_id, result='lock_conflict')
        return jsonify({
            'error': 'Another user has pending changes. Wait for them to commit or discard.',
            'locked': True,
            'lockOwner': staging_mgr.get_lock_status(session_id)
        }), 423
    return None


def _resolve_user_identity(data):
    """Resolve user identity from request body, falling back to staging data.

    Returns:
        Tuple of (user_name, user_email) - either may be None.
    """
    user_name = data.get('user_name', '').strip() if data.get('user_name') else None
    user_email = data.get('user_email', '').strip() if data.get('user_email') else None

    if not user_name or not user_email:
        staging_mgr = get_staging_manager()
        staging = staging_mgr.get_staging()
        if staging:
            user_name = user_name or staging.get('userName')
            user_email = user_email or staging.get('userEmail')

    return user_name, user_email


def _validate_commit_files(files, config_path, op_log):
    """Validate file paths for a commit.

    Returns:
        Error response tuple if invalid, or None if all valid.
    """
    for filepath in files:
        safe_result = is_safe_path(filepath, config_path)
        if not safe_result.success:
            if op_log:
                op_log.warning('git', 'commit', params={'file': filepath},
                               error=f'path_validation_failed: {safe_result.error}')
            return jsonify({'error': f'Invalid file path: {safe_result.error}'}), 400
    return None


def _create_pre_commit_backup(git_svc, user_name, user_email, op_log):
    """Create backup before commit if there are changes. Non-fatal on failure."""
    try:
        status_result = git_svc.get_status()
        if status_result.success and status_result.data.has_changes:
            bm = get_backup_manager()
            bm.create_backup('pre-commit', user_name, user_email)
    except Exception as backup_err:
        if op_log:
            op_log.warning('git', 'commit', error=f'backup failed: {backup_err}')


def _write_commit_audit_log(commit_hash, message, user_name, user_email, initialized):
    """Write audit log entry for a git commit."""
    if initialized:
        write_audit_log({
            'timestamp': datetime.now().isoformat(),
            'action': 'git_initialized',
            'commit_hash': commit_hash,
            'message': message,
            'userName': user_name,
            'userEmail': user_email
        })
        return

    staging_mgr = get_staging_manager()
    staging = staging_mgr.get_staging()
    restore_info = {}
    if staging and staging.get('status') == StagingStatus.RESTORE_PENDING.value:
        restore_info = {
            'restoreType': staging.get('restoreType', ''),
            'restoreFrom': staging.get('restoreFrom', '')
        }

    write_audit_log({
        'timestamp': datetime.now().isoformat(),
        'action': 'git_commit',
        'commit_hash': commit_hash,
        'message': message,
        'userName': user_name,
        'userEmail': user_email,
        **restore_info
    })


@bp.route('/api/git/identity', methods=['GET'])
def api_git_identity_get():
    """Get the identity of the current lock owner from staging data.

    Returns the userName and userEmail stored in staging data.
    This is the identity of whoever currently has pending changes.
    Each user's own identity is stored in their browser's localStorage.
    """
    try:
        staging_mgr = get_staging_manager()
        staging = staging_mgr.get_staging()

        if not staging:
            return jsonify({
                'user_name': '',
                'user_email': '',
                'is_configured': False,
                'has_lock': False
            })

        user_name = staging.get('userName', '')
        user_email = staging.get('userEmail', '')

        return jsonify({
            'user_name': user_name,
            'user_email': user_email,
            'is_configured': bool(user_name and user_email),
            'has_lock': True
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/api/git/identity', methods=['POST'])
def api_git_identity_set():
    """Update user identity in staging data.

    Requires X-Session-Id header. Only the lock owner can update identity.
    If no staging exists, creates minimal staging with just the identity.
    Identity is stored per-session (each browser stores own identity in localStorage).
    """
    session_id = request.headers.get('X-Session-Id')
    if not session_id:
        return jsonify({'error': 'X-Session-Id header required'}), 400

    lock_error = _check_staging_lock(session_id)
    if lock_error:
        return lock_error

    data = request.get_json() or {}
    error = _validate_identity_input(data)
    if error:
        return error

    user_name = data.get('user_name', '').strip()
    user_email = data.get('user_email', '').strip()

    try:
        staging_mgr = get_staging_manager()
        staging = staging_mgr.get_staging() or {}
        staging['sessionId'] = session_id
        staging['userName'] = user_name
        staging['userEmail'] = user_email

        if staging_mgr.save_staging(staging).success:
            return jsonify({'success': True, 'user_name': user_name, 'user_email': user_email})
        return jsonify({'error': 'Failed to save identity'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _validate_identity_input(data):
    """Validate user identity fields from request data.

    Returns:
        Error response tuple if invalid, or None if valid.
    """
    user_name = data.get('user_name', '').strip()
    user_email = data.get('user_email', '').strip()

    if not user_name or not user_email:
        return jsonify({'error': 'Both user_name and user_email are required'}), 400
    if '@' not in user_email or '.' not in user_email:
        return jsonify({'error': 'Invalid email format'}), 400
    return None


@bp.route('/api/git/status', methods=['GET'])
def api_git_status():
    """Get git status of config directory."""
    try:
        git_svc = get_git_service()
        result = git_svc.get_status()
        if not result.success:
            return jsonify({'error': result.error}), 500

        status = result.data
        return jsonify({
            'is_repo': status.is_repo,
            'branch': status.branch,
            'files': [{'path': f.path, 'status': f.status, 'status_code': f.status_code,
                        'staged': f.staged, 'unstaged': f.unstaged}
                       for f in status.files],
            'has_changes': status.has_changes,
            **(({'error': status.error} if status.error else {}))
        })
    except Exception as e:
        return jsonify({'error': f'Failed to get git status: {str(e)}'}), 500


@bp.route('/api/git/diff', methods=['POST'])
def api_git_diff():
    """Get git diff for a file or all changes."""
    config_path = get_config_path()
    data = request.get_json() or {}

    filepath = data.get('file')
    staged = data.get('staged', False)
    full_file = data.get('fullFile', True)
    context_lines = data.get('contextLines')

    if filepath:
        safe_result = is_safe_path(filepath, config_path)
        if not safe_result.success:
            return jsonify({'error': safe_result.error}), 400

    try:
        git_svc = get_git_service()
        result = git_svc.get_diff(filepath=filepath, staged=staged, full_file=full_file,
                                  context_lines=context_lines)
        if not result.success:
            return jsonify({'error': result.error}), 500

        return jsonify({
            'success': True,
            'diff': result.data,
            'file': filepath
        })
    except Exception as e:
        return jsonify({'error': f'Failed to get diff: {str(e)}'}), 500


@bp.route('/api/git/commit', methods=['POST'])
def api_git_commit():
    """Commit changes to git."""
    op_log = get_op_logger()
    data = request.get_json() or {}
    if op_log:
        op_log.info('git', 'commit', params={'message': data.get('message', '')[:100]})

    message = data.get('message', '').strip()
    if not message:
        return jsonify({'error': 'Commit message is required'}), 400

    session_id = request.headers.get('X-Session-Id')
    lock_error = _check_staging_lock(session_id, op_log, 'commit')
    if lock_error:
        return lock_error

    precondition_error = _validate_commit_preconditions(data, op_log)
    if precondition_error:
        return precondition_error

    try:
        return _execute_commit(data, message, session_id, op_log)
    except Exception as e:
        if op_log:
            op_log.error('git', 'commit', error=str(e))
        return jsonify({'error': f'Failed to commit: {str(e)}'}), 500


def _validate_commit_preconditions(data, op_log):
    """Validate identity and file paths for a commit.

    Returns:
        Error response tuple if invalid, or None if all valid.
    """
    user_name, user_email = _resolve_user_identity(data)
    if not user_name or not user_email:
        return jsonify({
            'error': 'Please set your name and email in Settings before committing.',
            'needsConfig': True
        }), 400

    files = data.get('files', [])
    if files:
        return _validate_commit_files(files, get_config_path(), op_log)
    return None


def _execute_commit(data, message, session_id, op_log):
    """Execute the git commit after preconditions are validated.

    Returns:
        Flask response.
    """
    user_name, user_email = _resolve_user_identity(data)
    files = data.get('files', [])
    auto_init = data.get('auto_init', False)

    git_svc = get_git_service()
    _create_pre_commit_backup(git_svc, user_name, user_email, op_log)

    result = git_svc.commit(
        message=message, files=files or None,
        user_name=user_name, user_email=user_email, auto_init=auto_init
    )

    if not result.success:
        return _handle_commit_failure(result)

    commit_hash = result.data['commit_hash']
    initialized = result.data['initialized']
    _write_commit_audit_log(commit_hash, message, user_name, user_email, initialized)

    if session_id:
        get_staging_manager().clear_staging()

    return jsonify({
        'success': True, 'commit_hash': commit_hash, 'message': message,
        'output': result.data['output'], 'initialized': initialized
    })


def _handle_commit_failure(result):
    """Handle a failed git commit result.

    Returns:
        Flask response tuple.
    """
    if 'nothing to commit' in (result.error or '').lower():
        return jsonify({
            'success': False, 'error': 'Nothing to commit',
            'message': 'Working directory is clean'
        })
    return jsonify({'error': result.error}), 400


@bp.route('/api/git/discard', methods=['POST'])
def api_git_discard():
    """Discard changes to a file."""
    op_log = get_op_logger()
    config_path = get_config_path()
    data = request.get_json() or {}

    filepath = data.get('file')
    if op_log:
        op_log.info('git', 'discard_file', params={'file': filepath})

    if not filepath:
        return jsonify({'error': 'File path is required'}), 400

    session_id = request.headers.get('X-Session-Id')
    lock_error = _check_staging_lock(session_id, op_log, 'discard_file')
    if lock_error:
        return lock_error

    safe_result = is_safe_path(filepath, config_path)
    if not safe_result.success:
        if op_log:
            op_log.warning('git', 'discard_file', params={'file': filepath},
                           error=f'path_validation_failed: {safe_result.error}')
        return jsonify({'error': safe_result.error}), 400

    try:
        git_svc = get_git_service()
        result = git_svc.discard(filepath)
        if not result.success:
            return jsonify({'error': result.error}), 400

        if result.data['action'] == 'restored':
            get_service().reload()

        return jsonify({'success': True, 'action': result.data['action']})

    except Exception as e:
        if op_log:
            op_log.error('git', 'discard_file', params={'file': filepath}, error=str(e))
        return jsonify({'error': f'Failed to discard changes: {str(e)}'}), 500


@bp.route('/api/git/discard-all', methods=['POST'])
def api_git_discard_all():
    """Discard all uncommitted changes."""
    op_log = get_op_logger()
    if op_log:
        op_log.info('git', 'discard_all')

    session_id = request.headers.get('X-Session-Id')
    lock_error = _check_staging_lock(session_id, op_log, 'discard_all')
    if lock_error:
        return lock_error

    try:
        git_svc = get_git_service()
        result = git_svc.discard_all()

        if not result.success:
            return jsonify({
                'error': result.error,
                'commands': result.data.get('commands', []) if result.data else []
            }), 400

        # Reload config to reflect changes
        get_service().reload()

        # Write audit log entry for discard
        write_audit_log({
            'timestamp': datetime.now().isoformat(),
            'action': 'git_discarded',
            'description': 'Discarded all uncommitted changes',
            **get_audit_user_identity()
        })

        return jsonify({
            'success': True,
            'commands': result.data['commands']
        })

    except Exception as e:
        if op_log:
            op_log.error('git', 'discard_all', error=str(e))
        return jsonify({'error': f'Failed to discard changes: {str(e)}'}), 500


@bp.route('/api/git/clear-history', methods=['POST'])
def api_git_clear_history():
    """Clear all git history and reinitialize with a fresh commit."""
    op_log = get_op_logger()
    if op_log:
        op_log.warning('git', 'clear_history')

    session_id = request.headers.get('X-Session-Id')
    lock_error = _check_staging_lock(session_id, op_log, 'clear_history')
    if lock_error:
        return lock_error

    try:
        # Get user identity from request body
        data = request.get_json() or {}
        user_name = data.get('user_name', '').strip() if data.get('user_name') else None
        user_email = data.get('user_email', '').strip() if data.get('user_email') else None

        # Require identity
        if not user_name or not user_email:
            return jsonify({
                'error': 'Please set your name and email in Settings before clearing history.',
                'needsConfig': True
            }), 400

        git_svc = get_git_service()
        result = git_svc.clear_history(user_name=user_name, user_email=user_email)
        if not result.success:
            return jsonify({'error': result.error}), 400

        # Write audit log entry for clear history
        write_audit_log({
            'timestamp': datetime.now().isoformat(),
            'action': 'git_clear_history',
            'description': 'Cleared all git history and reinitialized repository',
            'userName': user_name,
            'userEmail': user_email
        })

        return jsonify({'success': True, 'message': result.data['message']})

    except Exception as e:
        if op_log:
            op_log.error('git', 'clear_history', error=str(e))
        return jsonify({'error': f'Failed to clear history: {str(e)}'}), 500


@bp.route('/api/git/log', methods=['GET'])
def api_git_log():
    """Get git commit history."""
    # Get optional limit parameter (default 50)
    limit = request.args.get('limit', 50, type=int)

    try:
        git_svc = get_git_service()
        result = git_svc.get_log(limit=limit)
        if not result.success:
            return jsonify({'error': result.error}), 400

        data = result.data
        # Serialize GitCommit dataclasses to dicts
        commits = [{'hash': c.hash, 'hash_short': c.hash_short, 'author': c.author,
                    'date': c.date, 'message': c.message,
                    'matches_working_dir': c.matches_working_dir}
                   for c in data.get('commits', [])]

        response = {
            'is_repo': data.get('is_repo', False),
            'commits': commits,
        }
        if 'matching_commit' in data:
            response['matching_commit'] = data['matching_commit']
        if 'error' in data:
            response['error'] = data['error']
        if 'message' in data:
            response['message'] = data['message']
        return jsonify(response)

    except Exception as e:
        return jsonify({'error': f'Failed to get log: {str(e)}'}), 500


@bp.route('/api/git/restore', methods=['POST'])
def api_git_restore():
    """Restore working directory to a specific commit.

    Requires X-Session-Id header. Rejects if staging is locked by another session.
    Clears all pending GUI changes on successful restore.
    """
    data = request.get_json() or {}

    commit_hash = data.get('commit')

    if not commit_hash:
        return jsonify({'error': 'Commit hash is required'}), 400

    # Check staging lock - git operations require lock ownership
    session_id = request.headers.get('X-Session-Id')
    if session_id:
        staging_mgr = get_staging_manager()
        lock_owner = staging_mgr.get_lock_owner()
        if lock_owner and lock_owner != session_id:
            return jsonify({
                'error': 'Another user has pending changes. Wait for them to commit or discard.',
                'locked': True
            }), 423

    # Validate commit hash format (prevent injection)
    if not commit_hash.replace('-', '').isalnum():
        return jsonify({'error': 'Invalid commit hash format'}), 400

    try:
        git_svc = get_git_service()
        result = git_svc.restore(commit_hash)

        if not result.success:
            status_code = 404 if 'not found' in (result.error or '').lower() else 400
            return jsonify({'error': result.error}), status_code

        # Reload config to reflect changes
        get_service().reload()

        # Write audit log entry for git restore
        audit_identity = get_audit_user_identity()
        write_audit_log({
            'timestamp': datetime.now().isoformat(),
            'action': 'git_restored',
            'userName': audit_identity.get('userName'),
            'userEmail': audit_identity.get('userEmail'),
            'commit_hash': commit_hash,
            'commit_message': result.data['message'],
            'deleted_files_count': len(result.data['deleted_files'])
        })

        # Create staging lock so other sessions see the pending restore changes
        sm = get_staging_manager()
        if session_id:
            sm.save_staging({
                'sessionId': session_id,
                'userName': audit_identity.get('userName', ''),
                'userEmail': audit_identity.get('userEmail', ''),
                'status': StagingStatus.RESTORE_PENDING.value,
                'restoreType': 'git',
                'restoreFrom': commit_hash
            })
        else:
            sm.clear_staging()

        return jsonify({
            'success': True,
            'commit': result.data['commit'],
            'message': result.data['message'],
            'had_uncommitted_changes': result.data['had_uncommitted_changes'],
            'stashed': result.data['stashed'],
            'deleted_files': result.data['deleted_files']
        })

    except Exception as e:
        return jsonify({'error': f'Failed to restore: {str(e)}'}), 500
