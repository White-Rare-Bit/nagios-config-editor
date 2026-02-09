"""Staging API routes - Shared staging for multi-user collaboration."""

import os
import time
import uuid
import logging
import multiprocessing
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from nagios_model import NAME_FIELDS
from staging_manager import (
    OperationType,
    UNDO_HANDLERS,
    UndoKeyError
)
from audit_service import write_audit_log
import file_operations
from .helpers import (
    get_config,
    get_config_path,
    get_service,
    get_staging_manager,
    get_backup_manager,
    get_git_service,
    get_op_logger
)

bp = Blueprint('staging', __name__)
logger = logging.getLogger('nagios_bulk_editor')

# Serialize staging operations to prevent race conditions
# Uses multiprocessing.Lock because WSGI servers may use multiple processes
staging_operation_lock = multiprocessing.Lock()



def _create_undo_entry(
    operation_type: str,
    key: str,
    op_data: dict,
    description: str
) -> dict:
    """Create an undo entry dict.

    Args:
        operation_type: Type of operation ('edit', 'move', 'creation', 'deletion', 'new_file')
        key: Unique key for this entry
        op_data: Operation-specific data for undo
        description: Human-readable description

    Returns:
        Undo entry dict with id, type, data, description, and timestamp
    """
    return {
        'id': str(uuid.uuid4())[:8],
        'type': operation_type,
        'data': op_data,
        'description': description,
        'timestamp': time.time()
    }


def _create_bulk_undo_entry(
    operation_type: str,
    individual_entries: list,
    description: str
) -> dict:
    """Create a bulk undo entry that groups multiple operations.

    Args:
        operation_type: Type of bulk operation ('bulk_edit', 'bulk_move', 'bulk_creation', 'bulk_deletion')
        individual_entries: List of individual undo entries to group
        description: Human-readable description

    Returns:
        Bulk undo entry dict with items array containing data for each operation
    """
    # Extract the data from each individual entry to create the items array
    items = [entry['data'] for entry in individual_entries]
    return {
        'id': str(uuid.uuid4())[:8],
        'type': operation_type,
        'data': {'items': items, 'count': len(items)},
        'description': description,
        'timestamp': time.time()
    }


def _create_undo_entries_for_edits(
    pending_edits: dict,
    existing_keys: set,
    log: logging.Logger
) -> list:
    """Create undo entries for new pending edits.

    Args:
        pending_edits: Dict {globalIndex: entry} from staging data
        existing_keys: Set of keys that already have undo entries
        log: Logger instance

    Returns:
        List of undo entry dicts for new edits
    """
    entries = []
    for key, edit_data in pending_edits.items():
        key = str(key)
        if not isinstance(edit_data, dict):
            continue

        if key and key not in existing_keys:
            obj = edit_data.get('object', {})
            op_id = str(uuid.uuid4())[:8]
            obj_name = obj.get('name', obj.get('display_name', 'Unknown'))
            obj_type = obj.get('object_type', 'object')

            op_data = {
                'key': key,
                'globalIndex': edit_data.get('globalIndex', key),
                'op_id': op_id,
                'originalAttributes': edit_data.get('originalAttributes', {}),
                'object': obj
            }
            entry = _create_undo_entry('edit', key, op_data, f"Edit {obj_type} '{obj_name}'")
            entries.append(entry)
            log.debug(f"Created undo entry for edit: {obj_name}")

    return entries


def _create_undo_entries_for_moves(
    staged_moves: dict,
    existing_keys: set,
    log: logging.Logger
) -> list:
    """Create undo entries for new staged moves.

    Args:
        staged_moves: Dict {stableKey: entry} from staging data
        existing_keys: Set of keys that already have undo entries
        log: Logger instance

    Returns:
        List of undo entry dicts for new moves
    """
    entries = []
    for key, move_data in staged_moves.items():
        key = str(key)
        if not isinstance(move_data, dict):
            continue

        if key and key not in existing_keys:
            obj = move_data.get('object', {})
            op_id = str(uuid.uuid4())[:8]
            obj_name = obj.get('name', obj.get('display_name', 'Unknown'))
            obj_type = obj.get('object_type', 'object')
            target_file = move_data.get('targetFile', 'unknown')

            op_data = {
                'key': key,
                'globalIndex': move_data.get('globalIndex'),
                'op_id': op_id,
                'originalFile': move_data.get('originalFile'),
                'targetFile': target_file,
                'object': obj
            }
            entry = _create_undo_entry(
                'move', key, op_data,
                f"Move {obj_type} '{obj_name}' to {os.path.basename(target_file)}"
            )
            entries.append(entry)
            log.debug(f"Created undo entry for move: {obj_name}")

    return entries


def _create_undo_entries_for_creations(
    staged_creations: list,
    existing_ids: set,
    log: logging.Logger
) -> list:
    """Create undo entries for new staged creations.

    Args:
        staged_creations: List of creation entries from staging data
        existing_ids: Set of creation IDs that already have undo entries
        log: Logger instance

    Returns:
        List of undo entry dicts for new creations
    """
    entries = []
    for creation in staged_creations:
        if not isinstance(creation, dict):
            continue
        creation_id = str(creation.get('id', ''))
        if creation_id and creation_id not in existing_ids:
            obj_type = creation.get('object_type', 'object')
            op_id = str(uuid.uuid4())[:8]
            obj_name = creation.get('name', creation.get('display_name', 'New Object'))

            op_data = {
                'op_id': op_id,
                'creationId': creation_id,
                'object_type': obj_type,
                'name': obj_name,
                'targetFile': creation.get('targetFile')
            }
            entry = _create_undo_entry(
                'creation', creation_id, op_data,
                f"Create {obj_type} '{obj_name}'"
            )
            entries.append(entry)
            log.debug(f"Created undo entry for creation: {obj_name}")

    return entries


def _create_undo_entries_for_deletions(
    staged_deletions: list,
    existing_keys: set,
    log: logging.Logger
) -> list:
    """Create undo entries for new staged deletions.

    Args:
        staged_deletions: List of int global indices from staging data
        existing_keys: Set of keys that already have undo entries
        log: Logger instance

    Returns:
        List of undo entry dicts for new deletions
    """
    entries = []
    service = get_service()
    for deletion_entry in staged_deletions:
        if not isinstance(deletion_entry, (int, float)):
            continue
        key = str(int(deletion_entry))
        if key in existing_keys:
            continue

        # Look up object info for undo description
        obj = service.find_object_by_index(int(deletion_entry))
        obj_name = f"Object {key}"
        obj_type = 'object'
        if obj:
            obj_name = obj.get_display_name() or obj_name
            obj_type = obj.object_type

        op_data = {
            'op_id': str(uuid.uuid4())[:8],
            'key': key,
            'globalIndex': int(deletion_entry),
        }
        entry = _create_undo_entry(
            'deletion', key, op_data,
            f"Delete {obj_type} '{obj_name}'"
        )
        entries.append(entry)
        log.debug(f"Created undo entry for deletion: {obj_name}")

    return entries


def _create_undo_entries_for_new_files(
    new_files: list,
    existing_files: set,
    log: logging.Logger
) -> list:
    """Create undo entries for new files.

    Args:
        new_files: List of new file paths from staging data
        existing_files: Set of file paths that already have undo entries
        log: Logger instance

    Returns:
        List of undo entry dicts for new files
    """
    entries = []
    for new_file in new_files:
        if new_file and new_file not in existing_files:
            file_name = os.path.basename(new_file)
            op_data = {'path': new_file}
            entry = _create_undo_entry(
                'new_file', new_file, op_data,
                f"Create file '{file_name}'"
            )
            entries.append(entry)
            log.debug(f"Created undo entry for new file: {file_name}")

    return entries


def is_safe_path(path, base_dir=None):
    """Wrapper that provides get_config_path() as default for base_dir.

    Returns:
        OperationResult with success=True if safe, success=False with error if unsafe.
    """
    if base_dir is None:
        base_dir = get_config_path()
    return file_operations.is_safe_path(path, base_dir)


@bp.route('/api/staging', methods=['GET'])
def api_get_staging():
    """
    Get current staged changes.

    Returns the full staging data if it exists, or null if no staging.
    All users see the same staging - it's shared.
    """
    sm = get_staging_manager()
    staging = sm.get_staging()
    return jsonify({
        'staging': staging,
        'hasStaging': staging is not None
    })


@bp.route('/api/staging', methods=['DELETE'])
def api_delete_staging():
    """
    Clear/delete current staging data.

    Releases the staging lock and clears all pending changes.
    """
    sm = get_staging_manager()
    sm.clear_staging()
    return jsonify({'success': True})


@bp.route('/api/staging/info', methods=['GET'])
def api_get_staging_info():
    """
    Get summary info about current staging.

    Lightweight endpoint for polling - just returns counts, not full data.
    """
    sm = get_staging_manager()
    return jsonify(sm.get_staging_info())


@bp.route('/api/staging/lock', methods=['GET'])
def api_get_lock_status():
    """
    Get the current staging lock status.

    Returns lock information including who owns the lock and their identity.
    Used by frontend to show lock banner and disable editing UI.
    """
    sm = get_staging_manager()
    session_id = request.headers.get('X-Session-Id')

    lock_status = sm.get_lock_status(session_id)

    # Add user identity if lock is held
    if lock_status['locked']:
        staging = sm.get_staging()
        if staging:
            lock_status['userName'] = staging.get('userName', '')
            lock_status['userEmail'] = staging.get('userEmail', '')
        else:
            lock_status['userName'] = ''
            lock_status['userEmail'] = ''
    else:
        lock_status['userName'] = None
        lock_status['userEmail'] = None

    return jsonify(lock_status)


@bp.route('/api/staging/lock/break', methods=['POST'])
def api_break_lock():
    """
    Force break the staging lock (admin action).

    Discards the other user's pending changes and releases the lock.
    If there are uncommitted git changes, also discards those.
    """
    sm = get_staging_manager()
    git_svc = get_git_service()
    op_log = get_op_logger()

    session_id = request.headers.get('X-Session-Id')

    # Log the break attempt
    if op_log:
        owner = sm.get_lock_owner()
        op_log.warning('staging', 'break_lock',
                      params={'owner': owner, 'breaker': session_id},
                      result='attempted')

    # Check if there are uncommitted git changes to discard
    git_discarded = False
    if git_svc:
        has_changes = git_svc.has_uncommitted_changes()
        if has_changes.success and has_changes.data:
            # Discard git changes
            discard_result = git_svc.discard_all()
            git_discarded = discard_result.success

    # Clear staging
    sm.clear_staging()

    if op_log:
        op_log.info('staging', 'break_lock',
                   params={'git_discarded': git_discarded},
                   result='success')

    return jsonify({
        'success': True,
        'gitDiscarded': git_discarded
    })


def _validate_staging_format(data):
    """Validate staging data format.

    pendingEdits and stagedMoves must be dicts (not arrays).

    Args:
        data: Staging data from POST request

    Returns:
        None if valid, error message string if invalid
    """
    pending_edits = data.get('pendingEdits')
    if pending_edits is not None and not isinstance(pending_edits, dict):
        return "pendingEdits must be a dict {globalIndex: entry}"

    staged_moves = data.get('stagedMoves')
    if staged_moves is not None and not isinstance(staged_moves, dict):
        return "stagedMoves must be a dict {stableKey: entry}"

    return None


@bp.route('/api/staging', methods=['POST'])
def api_save_staging():
    """
    Save staged changes WITHOUT applying them to files.

    TRUE STAGING APPROACH:
    This endpoint ONLY stores staging data in staging.json.
    NO changes are written to disk until user calls POST /api/staging/apply.

    Requires X-Session-Id header. Rejects if staging is locked by another session.
    Accepts userName and userEmail in request body for user identification.
    """
    import logging
    logger = logging.getLogger('nagios_bulk_editor.staging')

    sm = get_staging_manager()
    data = request.get_json() or {}

    # Validate format before processing
    format_error = _validate_staging_format(data)
    if format_error:
        return jsonify({'error': f'Invalid staging format: {format_error}'}), 400
    session_id = request.headers.get('X-Session-Id')

    # Log staging request
    staged_moves = data.get('stagedMoves', {})
    logger.debug(f"POST /api/staging: {len(staged_moves)} moves, session={session_id}")

    # Require session ID for modifications
    if not session_id:
        return jsonify({'error': 'X-Session-Id header required'}), 400

    # Check if locked by another session
    if not sm.validate_or_acquire_lock(session_id):
        return jsonify({
            'error': 'Staging is locked by another user',
            'locked': True
        }), 423  # 423 Locked

    # Ensure session ID is stored with the staging data
    data['sessionId'] = session_id

    # User identity comes from the request (stored in browser localStorage)
    # Keep existing identity if not provided in this request
    existing = sm.get_staging()
    if existing and existing.get('sessionId') == session_id:
        # Preserve existing identity if not provided
        if 'userName' not in data and existing.get('userName'):
            data['userName'] = existing.get('userName')
        if 'userEmail' not in data and existing.get('userEmail'):
            data['userEmail'] = existing.get('userEmail')
        # Preserve existing file/folder staging operations
        for field in ['stagedFileCreations', 'stagedFileDeletions', 'stagedFileMoves',
                      'stagedFolderCreations', 'stagedFolderDeletions', 'stagedFolderMoves',
                      'undoStack', 'baseFileChecksums']:
            if field not in data and existing.get(field):
                data[field] = existing.get(field)

    # TRUE STAGING: Collect files that will be affected to track base checksums
    # NO changes are written to disk here - only staging data is saved
    files_to_track = set()

    # Track files affected by object edits
    pending_edits = data.get('pendingEdits', {})
    for entry in pending_edits.values():
        if isinstance(entry, dict):
            obj_info = entry.get('object', {})
            if obj_info.get('source_file'):
                files_to_track.add(obj_info['source_file'])

    # Track files affected by object moves
    for move_data in data.get('stagedMoves', {}).values():
        if isinstance(move_data, dict):
            obj_info = move_data.get('object', {})
            if obj_info.get('source_file'):
                files_to_track.add(obj_info['source_file'])
            if move_data.get('targetFile'):
                files_to_track.add(move_data['targetFile'])

    # Track files affected by object creations
    for creation in data.get('stagedCreations', []):
        if creation.get('targetFile'):
            target_file = creation['targetFile']
            config_path = get_config_path()
            if not os.path.isabs(target_file):
                target_file = os.path.join(config_path, target_file)
            if os.path.exists(target_file):
                files_to_track.add(target_file)

    # Track files affected by object deletions (array of ints)
    service = get_service()
    for deletion_entry in data.get('stagedObjectDeletions', []):
        if isinstance(deletion_entry, (int, float)):
            obj = service.find_object_by_index(int(deletion_entry))
            if obj:
                files_to_track.add(obj.source_file)

    # Update base checksums for files we're about to modify
    if files_to_track:
        sm.update_base_checksums(list(files_to_track))

    # Create undo entries for new object operations
    # Get existing operations to compare
    existing_pending_edit_keys = set()
    existing_staged_move_keys = set()
    existing_staged_creation_ids = set()
    existing_staged_deletion_keys = set()

    if existing:
        # Dict keys are the globalIndex/stableKey directly
        existing_pending_edit_keys = set(str(k) for k in existing.get('pendingEdits', {}).keys())
        existing_staged_move_keys = set(str(k) for k in existing.get('stagedMoves', {}).keys())

        # Extract IDs from existing staged creations
        for creation in existing.get('stagedCreations', []):
            if isinstance(creation, dict) and creation.get('id'):
                existing_staged_creation_ids.add(str(creation['id']))

        # Extract keys from existing staged deletions (array of ints)
        existing_staged_deletion_keys = set(str(int(d)) for d in existing.get('stagedObjectDeletions', [])
                                            if isinstance(d, (int, float)))

    # Initialize undo stack from existing data
    undo_stack = list(existing.get('undoStack', [])) if existing else []

    # Create undo entries for new operations
    # If multiple items of the same type are new, create a single bulk undo entry
    new_edits = _create_undo_entries_for_edits(
        pending_edits, existing_pending_edit_keys, logger
    )
    new_moves = _create_undo_entries_for_moves(
        data.get('stagedMoves', {}), existing_staged_move_keys, logger
    )
    new_creations = _create_undo_entries_for_creations(
        data.get('stagedCreations', []), existing_staged_creation_ids, logger
    )
    new_deletions = _create_undo_entries_for_deletions(
        data.get('stagedObjectDeletions', []), existing_staged_deletion_keys, logger
    )

    # Group multiple operations into single bulk undo entries
    # D-05: Threshold is >1 (not >5 or >10) because:
    # - User expectation: Multiple objects selected and edited together should undo together
    # - UI simplicity: Bulk operations appear as single "Bulk edit N objects" in undo stack
    # - Single operation stays atomic to allow granular undo when user edits one object at a time
    if len(new_edits) > 1:
        # Create single bulk edit undo entry
        undo_stack.append(_create_bulk_undo_entry('bulk_edit', new_edits, f"Bulk edit {len(new_edits)} object(s)"))
    else:
        undo_stack.extend(new_edits)

    if len(new_moves) > 1:
        # Create single bulk move undo entry
        target_file = new_moves[0]['data'].get('object', {}).get('targetFile', 'target')
        undo_stack.append(_create_bulk_undo_entry('bulk_move', new_moves, f"Bulk move {len(new_moves)} object(s)"))
    else:
        undo_stack.extend(new_moves)

    if len(new_creations) > 1:
        # Create single bulk creation undo entry
        undo_stack.append(_create_bulk_undo_entry('bulk_creation', new_creations, f"Bulk create {len(new_creations)} object(s)"))
    else:
        undo_stack.extend(new_creations)

    if len(new_deletions) > 1:
        # Create single bulk deletion undo entry
        undo_stack.append(_create_bulk_undo_entry('bulk_deletion', new_deletions, f"Bulk delete {len(new_deletions)} object(s)"))
    else:
        undo_stack.extend(new_deletions)

    # Create undo entries for NEW files (newFiles set) - these remain individual
    existing_new_files = set(existing.get('newFiles', [])) if existing else set()
    undo_stack.extend(_create_undo_entries_for_new_files(
        data.get('newFiles', []), existing_new_files, logger
    ))

    # Update the data with the new undo stack
    data['undoStack'] = undo_stack

    # Build staging data structure (with schema version)
    staging_data = sm.migrate_staging_schema({
        'sessionId': data['sessionId'],
        'userName': data.get('userName', ''),
        'userEmail': data.get('userEmail', ''),
        'pendingEdits': data.get('pendingEdits', {}),
        'stagedMoves': data.get('stagedMoves', {}),
        'stagedCreations': data.get('stagedCreations', []),
        'stagedObjectDeletions': data.get('stagedObjectDeletions', []),
        'newFiles': data.get('newFiles', []),
        'stagedFileCreations': data.get('stagedFileCreations', []),
        'stagedFileDeletions': data.get('stagedFileDeletions', []),
        'stagedFileMoves': data.get('stagedFileMoves', []),
        'stagedFolderCreations': data.get('stagedFolderCreations', []),
        'stagedFolderDeletions': data.get('stagedFolderDeletions', []),
        'stagedFolderMoves': data.get('stagedFolderMoves', []),
        'undoStack': data.get('undoStack', []),
        'baseFileChecksums': data.get('baseFileChecksums', {}),
    })

    # Use atomic save to prevent race condition with lock validation
    save_result = sm.save_staging_atomic(staging_data, session_id, staging_operation_lock)
    if save_result.success:
        return jsonify({
            'success': True,
            'message': 'Staging saved. Use POST /api/staging/apply to write changes to disk.'
        })
    elif 'locked' in (save_result.error or '').lower():
        return jsonify({'error': save_result.error, 'locked': True}), 423
    else:
        return jsonify({'error': save_result.error or 'Failed to save staging'}), 500


def _validate_apply_preconditions(sm, session_id, op_log):
    """Validate preconditions for staging apply.

    Args:
        sm: StagingManager instance
        session_id: Session ID from request
        op_log: Operation logger

    Returns:
        Tuple of (error_response, staging_data) - error_response is None if valid
    """
    if not session_id:
        return (jsonify({'error': 'X-Session-Id header required'}), 400), None

    if not sm.can_modify(session_id):
        if op_log:
            op_log.warning('app', 'staging_apply', session_id=session_id, result='lock_conflict')
        return (jsonify({'error': 'Staging is locked by another user', 'locked': True}), 423), None

    staging_data = sm.get_staging()
    if not staging_data:
        return (jsonify({'error': 'No staging data found'}), 400), None

    conflicts = sm.detect_conflicts()
    if conflicts:
        if op_log:
            op_log.warning('app', 'staging_apply', session_id=session_id, result='conflicts_detected')
        return (jsonify({
            'error': 'Conflicts detected - files have been modified externally',
            'conflicts': conflicts, 'requiresResolution': True
        }), 409), None

    return None, staging_data


def _execute_apply_phases(service, staging_data):
    """Execute all apply phases, halting on first error.

    Args:
        service: NagiosService instance
        staging_data: Staging data dict

    Returns:
        Tuple of (applied_summary, all_details, phase_errors, failed_phase)
        failed_phase is None if all phases succeeded
    """
    phases = [
        ('folderCreations', lambda: service.apply_folder_creations(staging_data)),
        ('fileCreations', lambda: service.apply_file_creations(staging_data)),
        ('objectDeletions', lambda: service.apply_object_deletions(staging_data)),
        ('objectMoves', lambda: service.apply_object_moves(staging_data)),
        ('objectEdits', lambda: service.apply_object_edits(staging_data)),
        ('objectCreations', lambda: service.apply_object_creations(staging_data)),
        ('fileMoves', lambda: service.apply_file_moves(staging_data)),
        ('folderMoves', lambda: service.apply_folder_moves(staging_data)),
        ('fileDeletions', lambda: service.apply_file_deletions(staging_data)),
        ('folderDeletions', lambda: service.apply_folder_deletions(staging_data)),
    ]

    applied_summary = {}
    all_details = {}
    phase_errors = []

    for key, apply_fn in phases:
        result = apply_fn()
        applied_summary[key] = result.data.get('count', 0)
        errors = result.data.get('errors', [])
        details = result.data.get('details', [])

        if details:
            all_details[key] = details

        if errors:
            phase_errors.extend(errors)
            # Halt on first error - don't continue with subsequent phases
            return applied_summary, all_details, phase_errors, key

    return applied_summary, all_details, phase_errors, None


def _write_apply_audit_log(staging_data, session_id, all_details, errors, log):
    """Write audit log entry for apply operation.

    C-10: Returns success status and error message if write fails.
    Caller should include audit failure in response warnings.

    Args:
        staging_data: Staging data dict
        session_id: Session ID
        all_details: Details from each phase
        errors: List of errors encountered
        log: Logger instance

    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    try:
        audit_entry = {
            'timestamp': datetime.now().isoformat(),
            'userName': staging_data.get('userName', ''),
            'userEmail': staging_data.get('userEmail', ''),
            'sessionId': session_id,
        }
        if all_details.get('objectEdits'):
            audit_entry['object_edits'] = all_details['objectEdits']
        if all_details.get('objectMoves'):
            audit_entry['object_moves'] = all_details['objectMoves']
        if all_details.get('objectCreations'):
            audit_entry['object_creations'] = all_details['objectCreations']
        if all_details.get('objectDeletions'):
            audit_entry['object_deletions'] = all_details['objectDeletions']
        if all_details.get('folderCreations'):
            audit_entry['folder_creations'] = all_details['folderCreations']
        if all_details.get('fileMoves'):
            audit_entry['file_moves'] = all_details['fileMoves']
        if all_details.get('folderMoves'):
            audit_entry['folder_moves'] = all_details['folderMoves']
        file_deletions = all_details.get('fileDeletions', []) + all_details.get('folderDeletions', [])
        if file_deletions:
            audit_entry['file_deletions'] = file_deletions
        if errors:
            audit_entry['errors'] = errors
        write_audit_log(audit_entry)
        return True, None
    except Exception as e:
        error_msg = f"Failed to write audit log: {e}"
        log.error(error_msg)  # C-10: Elevated from warning to error
        return False, error_msg


def _extract_name_changes(staging_data):
    """Extract name changes from pendingEdits for reference updates.

    C-06: Identifies objects whose name field was modified.

    Args:
        staging_data: Staging data dict containing pendingEdits

    Returns:
        List of dicts with {oldName, newName, objectType} for each name change
    """
    name_changes = []
    pending_edits = staging_data.get('pendingEdits', {})

    for edit_data in pending_edits.values():
        if not isinstance(edit_data, dict):
            continue
        obj_info = edit_data.get('object', {})
        obj_type = obj_info.get('object_type')
        if not obj_type:
            continue

        name_field = NAME_FIELDS.get(obj_type)
        if not name_field:
            continue

        original = edit_data.get('original', {})
        edited = edit_data.get('edited', {})

        # Check if name field was modified
        if name_field in edited:
            old_name = original.get(name_field)
            new_name = edited.get(name_field)
            if old_name and new_name and old_name != new_name:
                name_changes.append({
                    'oldName': old_name,
                    'newName': new_name,
                    'objectType': obj_type
                })

    return name_changes


def _apply_reference_updates(service, name_changes, log):
    """Apply reference updates for name changes.

    C-06: Updates references in other objects when objects are renamed.

    Args:
        service: NagiosService instance (must have fresh parser after apply)
        name_changes: List of {oldName, newName, objectType} from _extract_name_changes
        log: Logger instance

    Returns:
        Total count of references updated
    """
    from nagios_writer import NagiosConfigWriter

    if not name_changes:
        return 0

    total_refs_updated = 0
    objects = service.get_objects()

    for change in name_changes:
        old_name = change['oldName']
        new_name = change['newName']
        refs_updated = service.update_references(objects, old_name, new_name)
        total_refs_updated += refs_updated
        if refs_updated > 0:
            log.info(f"Updated {refs_updated} references: {old_name} -> {new_name}")

    if total_refs_updated > 0:
        # Write modified objects back to their files
        writer = NagiosConfigWriter()
        writer.write_objects_to_original_files(objects)
        # Reload parser to reflect reference changes
        service.reload()

    return total_refs_updated


@bp.route('/api/staging/apply', methods=['POST'])
def api_apply_staging():
    """
    Apply all staged changes to disk.

    TRUE STAGING: This endpoint writes all staged changes to the filesystem.
    Changes are applied in the correct order to avoid conflicts:
    1. Create folders (parent → child)
    2. Create files
    3. Delete objects (surgical)
    4. Move objects (sorted by line desc)
    5. Edit objects (surgical)
    6. Create objects
    7. Move files
    8. Move folders
    9. Delete files
    10. Delete folders (child → parent)

    ATOMIC BEHAVIOR:
    - Phases execute sequentially
    - If any phase encounters errors, execution halts immediately
    - On error, staging is NOT cleared (allows retry after fixing issues)
    - On success, staging is cleared UNLESS deferClear=true

    Request body options:
    - updateReferences: bool - Update references when objects are renamed
    - deferClear: bool - If true, don't clear staging on success (C-10 fix).
                         Use this when git commit will follow; clear staging
                         manually after git commit succeeds.

    Returns summary of applied changes and optionally prompts for git commit.
    """
    log = logging.getLogger('nagios_bulk_editor.staging')
    sm = get_staging_manager()
    session_id = request.headers.get('X-Session-Id')
    op_log = get_op_logger()

    # C-06: Read updateReferences flag from request body (use silent=True to handle missing body)
    # C-10: Read deferClear flag - if true, don't clear staging on success (for atomic apply+commit)
    request_data = request.get_json(silent=True) or {}
    update_references_flag = request_data.get('updateReferences', False)
    defer_clear = request_data.get('deferClear', False)
    validate_after = request_data.get('validate', False)

    # Validate preconditions
    error_response, staging_data = _validate_apply_preconditions(sm, session_id, op_log)
    if error_response:
        return error_response

    # C-06: Extract name changes BEFORE applying phases (needed for reference updates)
    name_changes = _extract_name_changes(staging_data) if update_references_flag else []

    if op_log:
        op_log.info('app', 'staging_apply', session_id=session_id,
                    user_name=staging_data.get('userName', ''),
                    user_email=staging_data.get('userEmail', ''),
                    update_references=update_references_flag,
                    name_changes_count=len(name_changes))

    service = get_service()

    # Create backup BEFORE applying any changes
    bm = get_backup_manager()
    if bm:
        try:
            user_name = staging_data.get('userName', '')
            user_email = staging_data.get('userEmail', '')
            bm.create_backup('pre-apply', user_name=user_name, user_email=user_email)
        except Exception as e:
            log.warning(f"Failed to create pre-apply backup: {e}")

    try:
        # Execute all phases, halting on first error
        applied_summary, all_details, errors, failed_phase = _execute_apply_phases(
            service, staging_data
        )

        if failed_phase:
            # Phase failed - do NOT clear staging, allow user to retry
            log.error(f"Staging apply failed at phase '{failed_phase}': {errors}")
            if op_log:
                op_log.error('app', 'staging_apply', session_id=session_id,
                             error=f"Failed at phase {failed_phase}: {errors}")

            # Still reload parser to reflect partial changes
            service.reload()

            return jsonify({
                'success': False,
                'error': f"Apply failed during {failed_phase} phase. Staging preserved for retry.",
                'failedPhase': failed_phase,
                'applied': applied_summary,
                'errors': errors,
                'stagingPreserved': True
            }), 500

        # All phases succeeded - reload parser, apply reference updates, then clear staging
        service.reload()

        # C-06: Apply reference updates if requested and there are name changes
        refs_updated = 0
        if update_references_flag and name_changes:
            try:
                refs_updated = _apply_reference_updates(service, name_changes, log)
                if refs_updated > 0:
                    all_details['referenceUpdates'] = {
                        'count': refs_updated,
                        'renames': name_changes
                    }
            except Exception as ref_err:
                # Reference update failure is non-fatal - objects were already renamed
                log.warning(f"Reference update failed (non-fatal): {ref_err}")
                errors.append(f"Reference update warning: {ref_err}")

        # C-10: Only clear staging if deferClear is not requested
        # When deferClear=true, caller will clear staging after git commit succeeds
        staging_cleared = False
        if not defer_clear:
            sm.clear_staging()
            staging_cleared = True

        total_changes = sum(applied_summary.values())

        # C-10: Track audit log write result and include failure in response
        audit_failed = False
        if total_changes > 0:
            audit_success, audit_error = _write_apply_audit_log(staging_data, session_id, all_details, errors, log)
            if not audit_success:
                audit_failed = True
                errors.append(audit_error)

        response_data = {
            'success': True, 'applied': applied_summary,
            'totalChanges': total_changes, 'errors': errors if errors else None,
            'referencesUpdated': refs_updated,
            'stagingCleared': staging_cleared,
            'stagingDeferred': defer_clear
        }
        if audit_failed:
            response_data['warnings'] = ['Audit log write failed - changes applied but not logged']

        # Optional: Run nagios -v validation after successful apply
        if validate_after:
            try:
                config = get_config()
                nagios_bin = config.get('nagios_bin', '')
                nagios_cfg = config.get('nagios_cfg', '')
                if nagios_bin and nagios_cfg:
                    from validator import NagiosValidator
                    validator = NagiosValidator(nagios_bin, nagios_cfg)
                    val_result = validator.validate()
                    response_data['validation'] = val_result.to_dict()
                else:
                    response_data['validation'] = {
                        'success': None,
                        'skipped': True,
                        'message': 'Nagios binary or config path not configured'
                    }
            except Exception as e:
                response_data['validation'] = {
                    'success': None,
                    'skipped': True,
                    'message': f'Validation failed to run: {str(e)}'
                }

        return jsonify(response_data)

    except Exception as e:
        # Unexpected exception - do NOT clear staging
        log.error(f"Error applying staging: {e}")
        if op_log:
            op_log.error('app', 'staging_apply', session_id=session_id, error=str(e))
        return jsonify({
            'error': f'Failed to apply staging: {e}',
            'stagingPreserved': True
        }), 500


@bp.route('/api/staging/virtual-tree', methods=['GET'])
def api_get_virtual_tree():
    """
    Get a merged virtual view of objects with staged changes applied.

    This endpoint returns what the file tree and objects would look like
    AFTER all staged changes are applied, without actually writing to disk.

    Used by the frontend to display the "preview" of changes.
    """
    sm = get_staging_manager()
    staging_data = sm.get_staging()
    service = get_service()

    # Start with current objects
    virtual_objects = []
    for i, obj in enumerate(service.get_objects()):
        obj_dict = obj.to_dict()
        obj_dict['global_index'] = i
        obj_dict['_staged_status'] = None  # Not staged
        virtual_objects.append(obj_dict)

    if not staging_data:
        # No staging - return current state
        return jsonify({
            'objects': virtual_objects,
            'files': sorted(set(obj['source_file'] for obj in virtual_objects)),
            'stagedCounts': {}
        })

    # Apply pending edits virtually
    pending_edits = staging_data.get('pendingEdits', {})
    edited_indices = set()
    for gi_str, edit_data in pending_edits.items():
        if not isinstance(edit_data, dict):
            continue
        global_index = int(gi_str) if gi_str is not None else None

        if global_index is not None and 0 <= global_index < len(virtual_objects):
            edited_attrs = edit_data.get('edited', {})
            if edited_attrs:
                virtual_objects[global_index]['attributes'].update(edited_attrs)
                virtual_objects[global_index]['_staged_status'] = 'edited'
                edited_indices.add(global_index)

    # Mark objects for deletion (array of ints)
    staged_deletions = staging_data.get('stagedObjectDeletions', [])
    deleted_indices = set()
    for deletion_entry in staged_deletions:
        if isinstance(deletion_entry, (int, float)):
            global_index = int(deletion_entry)
            if 0 <= global_index < len(virtual_objects):
                virtual_objects[global_index]['_staged_status'] = 'deleted'
                deleted_indices.add(global_index)

    # Mark objects for move
    staged_moves = staging_data.get('stagedMoves', {})
    for move_data in staged_moves.values():
        if not isinstance(move_data, dict):
            continue

        obj_info = move_data.get('object', {})
        target_file = move_data.get('targetFile')

        for i, obj in enumerate(virtual_objects):
            if (obj['source_file'] == obj_info.get('source_file') and
                obj['object_type'] == obj_info.get('object_type') and
                obj['attributes'] == obj_info.get('attributes')):
                obj['_staged_status'] = 'moved'
                obj['_staged_target_file'] = target_file
                break

    # Add staged creations
    staged_creations = staging_data.get('stagedCreations', [])
    for creation in staged_creations:
        virtual_objects.append({
            'object_type': creation.get('object_type'),
            'attributes': creation.get('attributes', {}),
            'source_file': creation.get('targetFile'),
            'line_number': -1,  # Doesn't exist yet
            'global_index': -1,
            '_staged_status': 'created'
        })

    # Collect files (including new files)
    files = set(obj['source_file'] for obj in virtual_objects if obj.get('source_file'))

    # Add staged new files
    new_files = staging_data.get('newFiles', [])
    config_path = get_config_path()
    for file_path in new_files:
        if not os.path.isabs(file_path):
            file_path = os.path.join(config_path, file_path)
        files.add(file_path)

    # Add staged file creations
    for op in staging_data.get('stagedFileCreations', []):
        if op.get('path'):
            files.add(op['path'])

    # Remove staged file deletions from file list
    for op in staging_data.get('stagedFileDeletions', []):
        if op.get('path') in files:
            files.discard(op['path'])

    # Calculate staged counts
    staged_counts = {
        'edits': len(pending_edits),
        'moves': len(staged_moves),
        'creations': len(staged_creations),
        'deletions': len(staged_deletions),
        'newFiles': len(new_files) + len(staging_data.get('stagedFileCreations', [])),
        'fileDeletes': len(staging_data.get('stagedFileDeletions', [])),
        'fileMoves': len(staging_data.get('stagedFileMoves', [])),
        'folderCreates': len(staging_data.get('stagedFolderCreations', [])),
        'folderDeletes': len(staging_data.get('stagedFolderDeletions', [])),
        'folderMoves': len(staging_data.get('stagedFolderMoves', [])),
    }

    return jsonify({
        'objects': virtual_objects,
        'files': sorted(files),
        'stagedCounts': staged_counts,
        'undoCount': len(staging_data.get('undoStack', []))
    })


@bp.route('/api/staging/undo', methods=['POST'])
def api_staging_undo():
    """
    Undo the last staged operation.

    C-04 FIX: Uses atomic undo pattern - peeks at entry first, applies reversal,
    removes from stack, then saves all changes atomically. This prevents data
    loss if save fails after popping.
    """
    sm = get_staging_manager()
    session_id = request.headers.get('X-Session-Id')

    if not session_id:
        return jsonify({'error': 'X-Session-Id header required'}), 400

    if not sm.can_modify(session_id):
        return jsonify({'error': 'Staging is locked by another user'}), 423

    # C-04 FIX: Peek first, don't pop yet
    undo_entry = sm.peek_undo_stack()
    if not undo_entry:
        return jsonify({'error': 'Nothing to undo'}), 404

    # Get staging for modification
    staging = sm.get_staging()
    if not staging:
        return jsonify({'error': 'No staging data'}), 400

    action_type = undo_entry.get('type')
    action_data = undo_entry.get('data', {})

    try:
        op_type = OperationType(action_type)
        handler = UNDO_HANDLERS.get(op_type)
        if handler:
            reversed_action = handler(staging, action_data)
        else:
            logger.warning(f"Unknown undo action_type: {action_type}, skipping")
            reversed_action = f"Skipped unknown action: {action_type}"
    except UndoKeyError as e:
        # C-05 FIX: Catch empty key errors and report to user instead of silent failure
        logger.error(f"Undo failed due to invalid key: {e}")
        return jsonify({'error': f'Undo failed: {e}'}), 400
    except ValueError:
        logger.warning(f"Invalid undo action_type: {action_type}, skipping")
        reversed_action = f"Skipped invalid action: {action_type}"

    # C-04 FIX: Now remove from stack (in memory) after successful reversal
    undo_stack = staging.get('undoStack', [])
    if undo_stack:
        undo_stack.pop()
        staging['undoStack'] = undo_stack

    # Save updated staging atomically (reversal + stack removal together)
    if sm.save_staging(staging).success:
        return jsonify({
            'success': True,
            'undone': undo_entry.get('description'),
            'action': reversed_action,
            'undoCount': len(staging.get('undoStack', []))
        })
    else:
        # If save fails, nothing was changed - entry still in stack, no data loss
        return jsonify({'error': 'Failed to save staging'}), 500


@bp.route('/api/staging/conflicts', methods=['GET'])
def api_staging_conflicts():
    """
    Check for conflicts between staged changes and current file state.

    Compares base file checksums (stored when staging began) against
    current file checksums to detect external modifications.
    """
    sm = get_staging_manager()

    conflicts = sm.detect_conflicts()

    return jsonify({
        'hasConflicts': len(conflicts) > 0,
        'conflicts': conflicts
    })


@bp.route('/api/staging/diff', methods=['GET'])
def api_staging_diff():
    """
    Get diff of uncommitted changes using git diff.

    Changes are now applied directly to files, so this endpoint returns
    git diff information along with staging metadata for file/folder operations.

    Returns data compatible with both the git page (simple diff view) and
    the commit dialog (which needs staging info for file/folder operations).
    """
    config_path = get_config_path()
    sm = get_staging_manager()
    staging = sm.get_staging() or {}

    # Paths to exclude from diff (backups, staging metadata, git internals)
    excluded_paths = ['.backups/', '.staging/', '.git/']

    # Get existing folders for the commit dialog
    existing_folders = []
    try:
        for root, dirs, files in os.walk(config_path):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            rel_path = os.path.relpath(root, config_path)
            if rel_path != '.':
                existing_folders.append(os.path.join(config_path, rel_path))
    except Exception:
        pass

    try:
        git_svc = get_git_service()
        diff_result = git_svc.get_workspace_diff(excluded_paths)
        if not diff_result.success:
            return jsonify({'error': diff_result.error}), 500

        diffs = diff_result.data['diffs']
        git_changes = diff_result.data['git_changes']

        # With TRUE STAGING, changes are NOT on disk yet
        # Count staged operations separately from git changes
        has_git_changes = len(diffs) > 0

        # Count staged changes (not yet on disk)
        staged_edits_count = len(staging.get('pendingEdits', {}))
        staged_moves_count = len(staging.get('stagedMoves', {}))
        staged_creations_count = len(staging.get('stagedCreations', []))
        staged_deletions_count = len(staging.get('stagedObjectDeletions', []))
        staged_file_creates = len(staging.get('stagedFileCreations', []))
        staged_file_deletes = len(staging.get('stagedFileDeletions', []))
        staged_file_moves = len(staging.get('stagedFileMoves', []))
        staged_folder_creates = len(staging.get('stagedFolderCreations', []))
        staged_folder_deletes = len(staging.get('stagedFolderDeletions', []))
        staged_folder_moves = len(staging.get('stagedFolderMoves', []))
        new_files_count = len(staging.get('newFiles', []))

        total_staged_count = (staged_edits_count + staged_moves_count + staged_creations_count +
                              staged_deletions_count + staged_file_creates + staged_file_deletes +
                              staged_file_moves + staged_folder_creates + staged_folder_deletes +
                              staged_folder_moves + new_files_count)

        has_staged_changes = total_staged_count > 0
        has_changes = has_git_changes or has_staged_changes

        # Build staged changes summary for commit dialog
        staged_changes = []
        if staged_edits_count > 0:
            staged_changes.append({'type': 'edits', 'count': staged_edits_count, 'label': f'{staged_edits_count} object edit(s)'})
        if staged_moves_count > 0:
            staged_changes.append({'type': 'moves', 'count': staged_moves_count, 'label': f'{staged_moves_count} object move(s)'})
        if staged_creations_count > 0:
            staged_changes.append({'type': 'creations', 'count': staged_creations_count, 'label': f'{staged_creations_count} new object(s)'})
        if staged_deletions_count > 0:
            staged_changes.append({'type': 'deletions', 'count': staged_deletions_count, 'label': f'{staged_deletions_count} object deletion(s)'})
        if new_files_count > 0:
            staged_changes.append({'type': 'newFiles', 'count': new_files_count, 'label': f'{new_files_count} new file(s)'})
        if staged_file_creates > 0:
            staged_changes.append({'type': 'fileCreations', 'count': staged_file_creates, 'label': f'{staged_file_creates} file creation(s)'})
        if staged_file_deletes > 0:
            staged_changes.append({'type': 'fileDeletions', 'count': staged_file_deletes, 'label': f'{staged_file_deletes} file deletion(s)'})
        if staged_file_moves > 0:
            staged_changes.append({'type': 'fileMoves', 'count': staged_file_moves, 'label': f'{staged_file_moves} file move(s)'})
        if staged_folder_creates > 0:
            staged_changes.append({'type': 'folderCreations', 'count': staged_folder_creates, 'label': f'{staged_folder_creates} folder creation(s)'})
        if staged_folder_deletes > 0:
            staged_changes.append({'type': 'folderDeletions', 'count': staged_folder_deletes, 'label': f'{staged_folder_deletes} folder deletion(s)'})
        if staged_folder_moves > 0:
            staged_changes.append({'type': 'folderMoves', 'count': staged_folder_moves, 'label': f'{staged_folder_moves} folder move(s)'})

        # Get all objects from parser for context display in commit dialog
        service = get_service()
        all_objects = [{
            'global_index': i,
            'object_type': obj.object_type,
            'name': obj.get_name(),
            'display_name': obj.get_display_name(),
            'source_file': obj.source_file,
            'line_number': obj.line_number,
            'attributes': dict(obj.attributes)
        } for i, obj in enumerate(service.get_objects())]

        return jsonify({
            # For git page (simple diff view)
            'hasDiffs': has_git_changes,
            'diffs': diffs,
            'count': len(diffs) + total_staged_count,

            # For commit dialog
            'hasChanges': has_changes,
            'hasGitChanges': has_git_changes,
            'hasStagedChanges': has_staged_changes,
            'gitChanges': git_changes,
            'stagedChanges': staged_changes,
            'totalStagedCount': total_staged_count,
            'staging': staging,
            'configPath': config_path,
            'existingFolders': existing_folders,

            # All objects from parser for context display
            'objects': all_objects
        })

    except Exception as e:
        return jsonify({'error': f'Failed to get diff: {str(e)}'}), 500


@bp.route('/api/staging/analyze-references', methods=['GET'])
def api_staging_analyze_references():
    """
    Analyze pending name changes and count affected references.

    Returns information about objects whose names are being changed,
    and how many references to those objects exist in the configuration.
    """
    sm = get_staging_manager()
    staging = sm.get_staging()

    if not staging:
        return jsonify({'nameChanges': [], 'totalReferences': 0})

    service = get_service()
    p = service.parser
    pending_edits = staging.get('pendingEdits', {})
    name_changes = []
    total_references = 0

    for gi_str, edit_data in pending_edits.items():
        if not isinstance(edit_data, dict):
            continue
        try:
            global_index = int(gi_str)
        except (ValueError, TypeError):
            continue

        obj = service.find_object_by_index(global_index)
        if obj is None:
            continue
        original = edit_data.get('original', {})
        edited = edit_data.get('edited', {})

        # Check if name field changed
        name_field = NAME_FIELDS.get(obj.object_type, 'name')
        if not name_field:
            continue

        old_name = original.get(name_field) or obj.attributes.get(name_field)
        new_name = edited.get(name_field)

        if old_name and new_name and old_name != new_name:
            # Count references
            refs = p.find_references(obj.object_type, old_name)
            ref_count = len(refs)
            total_references += ref_count

            name_changes.append({
                'globalIndex': global_index,
                'objectType': obj.object_type,
                'oldName': old_name,
                'newName': new_name,
                'referenceCount': ref_count,
                'references': [
                    {
                        'objectType': ref_obj.object_type,
                        'objectName': ref_obj.get_display_name(),
                        'field': ref_field
                    }
                    for ref_obj, ref_field in refs[:10]  # Limit to 10 for display
                ]
            })

    return jsonify({
        'nameChanges': name_changes,
        'totalReferences': total_references,
        'hasNameChanges': len(name_changes) > 0
    })


@bp.route('/api/staging/commit', methods=['POST'])
def api_staging_commit():
    """
    Apply all staged changes and release the lock.

    This endpoint:
    1. Applies all staged moves (object moves between files)
    2. Creates a backup
    3. Clears the staging lock
    4. Reloads the parser

    Moves are applied here (not on every save) to keep global_index stable during editing.

    Requires X-Session-Id header matching the lock owner.
    """
    sm = get_staging_manager()
    session_id = request.headers.get('X-Session-Id')

    # Check lock ownership before committing
    if not session_id:
        return jsonify({'error': 'X-Session-Id header required'}), 400

    if not sm.validate_or_acquire_lock(session_id):
        return jsonify({
            'error': 'Cannot commit: staging is locked by another user',
            'locked': True
        }), 423  # 423 Locked

    staging = sm.get_staging()
    config = current_app.extensions.get('app_config', {})
    config_path = config.get('nagios_config_path', '')

    # Apply staged changes to disk before committing
    if staging:
        # Pass through request JSON data (e.g., updateReferences flag)
        request_data = request.get_json(silent=True) or {}
        with current_app.test_client() as client:
            apply_resp = client.post('/api/staging/apply',
                                     json=request_data,
                                     headers={'X-Session-Id': session_id,
                                              'Content-Type': 'application/json'})
            if apply_resp.status_code >= 400:
                apply_data = apply_resp.get_json()
                error_msg = apply_data.get('error', 'Failed to apply staged changes') if apply_data else 'Failed to apply staged changes'
                return jsonify({
                    'success': False,
                    'error': error_msg
                }), apply_resp.status_code

    # Check if there are uncommitted git changes (the real indicator of pending work)
    try:
        git_svc = get_git_service()
        changes_result = git_svc.has_uncommitted_changes()
        has_changes = changes_result.success and changes_result.data
    except Exception:
        has_changes = False

    if not has_changes:
        return jsonify({'success': False, 'error': 'No changes to commit'})

    # Get user identity from staging data or empty
    user_name = staging.get('userName', '') if staging else ''
    user_email = staging.get('userEmail', '') if staging else ''

    # Note: Backup is created in /api/staging/apply BEFORE changes are written to disk

    audit_log = {
        'timestamp': datetime.now().isoformat(),
        'userName': user_name,
        'userEmail': user_email
    }

    try:
        # Clear staging (releases lock)
        sm.clear_staging()

        # Reload configuration
        parser = None
        get_service().reload()

        # Log to audit file
        try:
            write_audit_log(audit_log)
        except Exception as e:
            print(f"Warning: Failed to write audit log: {e}")

        return jsonify({
            'success': True,
            'auditLog': audit_log
        })

    except Exception as e:
        print(f"Error: Commit failed: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'auditLog': audit_log
        }), 500
