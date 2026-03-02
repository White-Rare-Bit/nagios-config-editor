"""Staging API routes - Shared staging for multi-user collaboration."""

import logging
import multiprocessing
import os
import time
import uuid

from flask import Blueprint, current_app, jsonify, request

import file_operations
from apply_verification import verify_apply_integrity
from audit_service import log_audit
from nagios_model import NAME_FIELDS
from staging_manager import UNDO_HANDLERS, OperationType, UndoKeyError, parse_stable_key

from .helpers import (
    format_audit_user,
    get_backup_manager,
    get_config,
    get_config_path,
    get_git_service,
    get_service,
    get_staging_manager,
)

bp = Blueprint("staging", __name__)
logger = logging.getLogger("nagios_bulk_editor")

# Known fields in the staging wire format (POST /api/staging body).
# Used to warn on unexpected fields that may indicate a version mismatch.
KNOWN_STAGING_FIELDS = {
    'sessionId', 'userName', 'userEmail',
    'pendingEdits', 'stagedMoves', 'stagedCreations',
    'newFiles', 'stagedObjectDeletions',
    'stagedFileCreations', 'stagedFileDeletions', 'stagedFileMoves',
    'stagedFolderCreations', 'stagedFolderDeletions', 'stagedFolderMoves',
}

# Serialize staging operations to prevent race conditions
# Uses multiprocessing.Lock because WSGI servers may use multiple processes
staging_operation_lock = multiprocessing.Lock()


def _create_undo_entry(
    operation_type: str,
    key: str,
    op_data: dict,
    description: str,
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
        "id": str(uuid.uuid4())[:8],
        "type": operation_type,
        "data": op_data,
        "description": description,
        "timestamp": time.time(),
    }


def _create_bulk_undo_entry(
    operation_type: str,
    individual_entries: list,
    description: str,
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
    items = [entry["data"] for entry in individual_entries]
    return {
        "id": str(uuid.uuid4())[:8],
        "type": operation_type,
        "data": {"items": items, "count": len(items)},
        "description": description,
        "timestamp": time.time(),
    }


def _create_undo_entries_for_edits(
    pending_edits: dict,
    existing_keys: set,
    log: logging.Logger,
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
            obj = edit_data.get("object", {})
            op_id = str(uuid.uuid4())[:8]
            obj_type = obj.get("object_type") or "object"
            # Resolve name: try object metadata, then extract from attributes
            obj_name = obj.get("name") or obj.get("display_name")
            if not obj_name:
                name_field = NAME_FIELDS.get(obj_type)
                attrs = edit_data.get("edited") or edit_data.get("original") or {}
                obj_name = attrs.get(name_field) if name_field else None
            if not obj_name:
                obj_name = "Unknown"

            op_data = {
                "key": key,
                "globalIndex": edit_data.get("globalIndex", key),
                "op_id": op_id,
                "originalAttributes": edit_data.get("originalAttributes", {}),
                "object": obj,
            }
            entry = _create_undo_entry(
                "edit", key, op_data, f"Edit {obj_type} '{obj_name}'"
            )
            entries.append(entry)
            log.debug("Created undo entry for edit: %s", obj_name)

    return entries


def _create_undo_entries_for_moves(
    staged_moves: dict,
    existing_keys: set,
    log: logging.Logger,
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
            obj = move_data.get("object", {})
            op_id = str(uuid.uuid4())[:8]
            obj_type = obj.get("object_type") or "object"
            obj_name = obj.get("name") or obj.get("display_name")
            if not obj_name:
                obj_name = "Unknown"
            target_file = move_data.get("targetFile", "unknown")

            op_data = {
                "key": key,
                "globalIndex": move_data.get("globalIndex"),
                "op_id": op_id,
                "originalFile": move_data.get("originalFile"),
                "targetFile": target_file,
                "object": obj,
            }
            entry = _create_undo_entry(
                "move",
                key,
                op_data,
                f"Move {obj_type} '{obj_name}' to {os.path.basename(target_file)}",
            )
            entries.append(entry)
            log.debug("Created undo entry for move: %s", obj_name)

    return entries


def _create_undo_entries_for_creations(
    staged_creations: list,
    existing_ids: set,
    log: logging.Logger,
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
        creation_id = str(creation.get("id", ""))
        if creation_id and creation_id not in existing_ids:
            obj_type = creation.get("object_type", "object")
            op_id = str(uuid.uuid4())[:8]
            obj_name = creation.get("name", creation.get("display_name", "New Object"))

            op_data = {
                "op_id": op_id,
                "creationId": creation_id,
                "object_type": obj_type,
                "name": obj_name,
                "targetFile": creation.get("targetFile"),
            }
            entry = _create_undo_entry(
                "creation",
                creation_id,
                op_data,
                f"Create {obj_type} '{obj_name}'",
            )
            entries.append(entry)
            log.debug("Created undo entry for creation: %s", obj_name)

    return entries


def _create_undo_entries_for_deletions(
    staged_deletions: list,
    existing_keys: set,
    log: logging.Logger,
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
        obj_type = "object"
        if obj:
            obj_name = obj.get_display_name() or obj_name
            obj_type = obj.object_type

        op_data = {
            "op_id": str(uuid.uuid4())[:8],
            "key": key,
            "globalIndex": int(deletion_entry),
        }
        entry = _create_undo_entry(
            "deletion",
            key,
            op_data,
            f"Delete {obj_type} '{obj_name}'",
        )
        entries.append(entry)
        log.debug("Created undo entry for deletion: %s", obj_name)

    return entries


def _create_undo_entries_for_new_files(
    new_files: list,
    existing_files: set,
    log: logging.Logger,
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
            op_data = {"path": new_file}
            entry = _create_undo_entry(
                "new_file",
                new_file,
                op_data,
                f"Create file '{file_name}'",
            )
            entries.append(entry)
            log.debug("Created undo entry for new file: %s", file_name)

    return entries


def _preserve_existing_session_data(existing, data, session_id):
    """Preserve user identity and file/folder ops from existing staging if same session.

    When a session saves new staging data, we preserve fields that weren't
    explicitly provided in the new request (user identity, file/folder operations,
    undo stack, base checksums).

    Args:
        existing: Existing staging data (may be None)
        data: New staging data dict from POST request (modified in place)
        session_id: Current session ID

    """
    if not existing or existing.get("sessionId") != session_id:
        return

    # Preserve existing identity if not provided
    if "userName" not in data and existing.get("userName"):
        data["userName"] = existing.get("userName")
    if "userEmail" not in data and existing.get("userEmail"):
        data["userEmail"] = existing.get("userEmail")

    # Preserve existing file/folder staging operations
    for field in [
        "stagedFileCreations",
        "stagedFileDeletions",
        "stagedFileMoves",
        "stagedFolderCreations",
        "stagedFolderDeletions",
        "stagedFolderMoves",
        "undoStack",
        "baseFileChecksums",
        "_deletionIdentities",
    ]:
        if field not in data and existing.get(field):
            data[field] = existing.get(field)


def _collect_affected_files(data, config_path):
    """Collect set of files affected by all staging operations.

    Scans pending edits, moves, creations, and deletions to find all files
    that will be affected when staging is applied.

    Args:
        data: Staging data dict
        config_path: Base configuration path for resolving relative paths

    Returns:
        Set of absolute file paths that will be affected

    """
    files = set()
    _collect_files_from_edits(files, data.get("pendingEdits", {}))
    _collect_files_from_moves(files, data.get("stagedMoves", {}))
    _collect_files_from_creations(files, data.get("stagedCreations", []), config_path)
    _collect_files_from_deletions(files, data.get("stagedObjectDeletions", []))
    return files


def _collect_files_from_edits(files, pending_edits):
    """Add source files from pending edits to the tracking set."""
    for entry in pending_edits.values():
        if isinstance(entry, dict):
            source = entry.get("object", {}).get("source_file")
            if source:
                files.add(source)


def _collect_files_from_moves(files, staged_moves):
    """Add source and target files from staged moves to the tracking set."""
    for move_data in staged_moves.values():
        if not isinstance(move_data, dict):
            continue
        source = move_data.get("object", {}).get("source_file")
        if source:
            files.add(source)
        target = move_data.get("targetFile")
        if target:
            files.add(target)


def _collect_files_from_creations(files, staged_creations, config_path):
    """Add target files from staged creations to the tracking set (if they exist)."""
    for creation in staged_creations:
        target_file = creation.get("targetFile")
        if not target_file:
            continue
        if not os.path.isabs(target_file):
            target_file = os.path.join(config_path, target_file)
        if os.path.exists(target_file):
            files.add(target_file)


def _collect_files_from_deletions(files, staged_deletions):
    """Add source files from staged object deletions to the tracking set."""
    service = get_service()
    for deletion_entry in staged_deletions:
        if isinstance(deletion_entry, (int, float)):
            obj = service.find_object_by_index(int(deletion_entry))
            if obj:
                files.add(obj.source_file)


def _get_existing_operation_keys(existing):
    """Extract sets of keys for operations already in existing staging data.

    Used to determine which operations are new (and need undo entries) vs
    already present from a previous save.

    Args:
        existing: Existing staging data (may be None)

    Returns:
        Tuple of (edit_keys, move_keys, creation_ids, deletion_keys) as sets of strings

    """
    if not existing:
        return set(), set(), set(), set()

    edit_keys = set(str(k) for k in existing.get("pendingEdits", {}))
    move_keys = set(str(k) for k in existing.get("stagedMoves", {}))

    creation_ids = set()
    for creation in existing.get("stagedCreations", []):
        if isinstance(creation, dict) and creation.get("id"):
            creation_ids.add(str(creation["id"]))

    deletion_keys = set(str(d) for d in existing.get("stagedObjectDeletions", []))

    return edit_keys, move_keys, creation_ids, deletion_keys


def _filter_orphaned_undo_entries(undo_stack, current_edit_keys, current_move_keys):
    """Remove undo entries for operations no longer present in staging data.

    When a user manually reverts an edit (editing back to original value),
    the pending edit is removed but the undo entry persists. This cleans
    up those orphaned entries so the undo stack reflects actual changes.

    Args:
        undo_stack: List of undo entry dicts
        current_edit_keys: Set of string keys currently in pendingEdits
        current_move_keys: Set of string keys currently in stagedMoves

    Returns:
        Filtered list of undo entries

    """
    result = []
    for entry in undo_stack:
        etype = entry.get("type", "")
        edata = entry.get("data", {})

        if etype == "edit":
            if str(edata.get("key", "")) not in current_edit_keys:
                continue
        elif etype == "move":
            if str(edata.get("key", "")) not in current_move_keys:
                continue
        elif etype in ("bulk_edit", "bulk_move"):
            keys = current_edit_keys if etype == "bulk_edit" else current_move_keys
            items = [i for i in edata.get("items", []) if str(i.get("key", "")) in keys]
            if not items:
                continue
            entry = {**entry, "data": {**edata, "items": items, "count": len(items)}}
        elif etype == "compound":
            subs = _filter_orphaned_undo_entries(
                edata.get("entries", []),
                current_edit_keys,
                current_move_keys,
            )
            if not subs:
                continue
            entry = {**entry, "data": {**edata, "entries": subs}}

        result.append(entry)
    return result


def _build_undo_entries(data, existing, log):
    """Build the complete undo stack including new entries for new operations.

    Creates undo entries for new edits, moves, creations, deletions, and new files.
    Groups multiple operations of the same type into bulk undo entries.
    Removes orphaned entries for operations that have been manually reverted.

    Args:
        data: New staging data dict
        existing: Existing staging data (may be None)
        log: Logger instance

    Returns:
        List of undo entries (the complete undo stack)

    """
    (
        existing_edit_keys,
        existing_move_keys,
        existing_creation_ids,
        existing_deletion_keys,
    ) = _get_existing_operation_keys(existing)

    # Initialize undo stack from existing data
    undo_stack = list(existing.get("undoStack", [])) if existing else []

    # Remove undo entries for operations that were manually reverted
    current_edit_keys = set(str(k) for k in data.get("pendingEdits", {}))
    current_move_keys = set(str(k) for k in data.get("stagedMoves", {}))
    undo_stack = _filter_orphaned_undo_entries(
        undo_stack,
        current_edit_keys,
        current_move_keys,
    )

    # Create undo entries for new operations
    new_edits = _create_undo_entries_for_edits(
        data.get("pendingEdits", {}),
        existing_edit_keys,
        log,
    )
    new_moves = _create_undo_entries_for_moves(
        data.get("stagedMoves", {}),
        existing_move_keys,
        log,
    )
    new_creations = _create_undo_entries_for_creations(
        data.get("stagedCreations", []),
        existing_creation_ids,
        log,
    )
    new_deletions = _create_undo_entries_for_deletions(
        data.get("stagedObjectDeletions", []),
        existing_deletion_keys,
        log,
    )

    # Create undo entries for NEW files (newFiles set)
    existing_new_files = set(existing.get("newFiles", [])) if existing else set()
    new_files = _create_undo_entries_for_new_files(
        data.get("newFiles", []),
        existing_new_files,
        log,
    )

    # Group entries: first group same-type operations, then check for cross-type
    grouped_entries = []
    _collect_undo_group(grouped_entries, new_edits, "bulk_edit", "edit")
    _collect_undo_group(grouped_entries, new_moves, "bulk_move", "move")
    _collect_undo_group(grouped_entries, new_creations, "bulk_creation", "create")
    _collect_undo_group(grouped_entries, new_deletions, "bulk_deletion", "delete")
    grouped_entries.extend(new_files)

    # H-020: If a single POST creates operations of multiple types, group into
    # one compound entry so Ctrl+Z reverses the entire user action at once
    if len(grouped_entries) > 1:
        descriptions = [e.get("description", "") for e in grouped_entries]
        undo_stack.append(
            {
                "id": str(uuid.uuid4())[:8],
                "type": "compound",
                "data": {"entries": grouped_entries},
                "description": " + ".join(descriptions),
                "timestamp": time.time(),
            }
        )
    else:
        undo_stack.extend(grouped_entries)

    return undo_stack


def _collect_undo_group(collector, new_entries, bulk_type, verb):
    """Collect undo entries, grouping multiple same-type entries into a bulk entry.

    If there are more than 1 entries, creates a single bulk undo entry.
    Otherwise, adds individual entries directly.

    Args:
        collector: List to collect entries into (modified in place)
        new_entries: List of individual undo entries
        bulk_type: Bulk operation type string (e.g. 'bulk_edit')
        verb: Verb for description (e.g. 'edit')

    """
    if len(new_entries) > 1:
        collector.append(
            _create_bulk_undo_entry(
                bulk_type,
                new_entries,
                f"Bulk {verb} {len(new_entries)} object(s)",
            )
        )
    else:
        collector.extend(new_entries)


def _build_staging_data(sm, data):
    """Build the final staging data structure with schema version.

    Args:
        sm: StagingManager instance
        data: Staging data dict with all fields populated

    Returns:
        Staging data dict with schema version applied

    """
    result = sm.migrate_staging_schema(
        {
            "sessionId": data["sessionId"],
            "userName": data.get("userName", ""),
            "userEmail": data.get("userEmail", ""),
            "pendingEdits": data.get("pendingEdits", {}),
            "stagedMoves": data.get("stagedMoves", {}),
            "stagedCreations": data.get("stagedCreations", []),
            "stagedObjectDeletions": data.get("stagedObjectDeletions", []),
            "newFiles": data.get("newFiles", []),
            "stagedFileCreations": data.get("stagedFileCreations", []),
            "stagedFileDeletions": data.get("stagedFileDeletions", []),
            "stagedFileMoves": data.get("stagedFileMoves", []),
            "stagedFolderCreations": data.get("stagedFolderCreations", []),
            "stagedFolderDeletions": data.get("stagedFolderDeletions", []),
            "stagedFolderMoves": data.get("stagedFolderMoves", []),
            "undoStack": data.get("undoStack", []),
            "baseFileChecksums": data.get("baseFileChecksums", {}),
        }
    )
    # Sidecar field — not part of schema, preserved as extra key
    if data.get("_deletionIdentities"):
        result["_deletionIdentities"] = data["_deletionIdentities"]
    return result


def is_safe_path(path, base_dir=None):
    """Wrapper that provides get_config_path() as default for base_dir.

    Returns:
        OperationResult with success=True if safe, success=False with error if unsafe.

    """
    if base_dir is None:
        base_dir = get_config_path()
    return file_operations.is_safe_path(path, base_dir)


@bp.route("/api/staging", methods=["GET"])
def api_get_staging():
    """Get current staged changes.

    Returns the full staging data if it exists, or null if no staging.
    All users see the same staging - it's shared.
    """
    sm = get_staging_manager()
    staging = sm.get_staging()
    return jsonify(
        {
            "staging": staging,
            "hasStaging": staging is not None,
        }
    )


@bp.route("/api/staging", methods=["DELETE"])
def api_delete_staging():
    """Clear/delete current staging data.

    Releases the staging lock and clears all pending changes.
    """
    sm = get_staging_manager()
    sm.clear_staging()
    return jsonify({"success": True})


@bp.route("/api/staging/info", methods=["GET"])
def api_get_staging_info():
    """Get summary info about current staging.

    Lightweight endpoint for polling - just returns counts, not full data.
    """
    sm = get_staging_manager()
    return jsonify(sm.get_staging_info())


@bp.route("/api/staging/lock", methods=["GET"])
def api_get_lock_status():
    """Get the current staging lock status.

    Returns lock information including who owns the lock and their identity.
    Used by frontend to show lock banner and disable editing UI.
    """
    sm = get_staging_manager()
    session_id = request.headers.get("X-Session-Id")

    lock_status = sm.get_lock_status(session_id)

    # Add user identity if lock is held
    if lock_status["locked"]:
        staging = sm.get_staging()
        if staging:
            lock_status["userName"] = staging.get("userName", "")
            lock_status["userEmail"] = staging.get("userEmail", "")
        else:
            lock_status["userName"] = ""
            lock_status["userEmail"] = ""
    else:
        lock_status["userName"] = None
        lock_status["userEmail"] = None

    return jsonify(lock_status)


@bp.route("/api/staging/lock/break", methods=["POST"])
def api_break_lock():
    """Force break the staging lock (admin action).

    Discards the other user's pending changes and releases the lock.
    If there are uncommitted git changes, also discards those.
    """
    sm = get_staging_manager()
    git_svc = get_git_service()

    session_id = request.headers.get("X-Session-Id")

    # Log the break attempt
    owner = sm.get_lock_owner()
    logger.warning("Break lock attempted: owner=%s, breaker=%s", owner, session_id)

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

    logger.info("Break lock succeeded: git_discarded=%s", git_discarded)

    return jsonify(
        {
            "success": True,
            "gitDiscarded": git_discarded,
        }
    )


def _validate_staging_format(data):
    """Validate staging data format.

    pendingEdits and stagedMoves must be dicts (not arrays).

    Args:
        data: Staging data from POST request

    Returns:
        None if valid, error message string if invalid

    """
    pending_edits = data.get("pendingEdits")
    if pending_edits is not None and not isinstance(pending_edits, dict):
        return "pendingEdits must be a dict {stableKey: entry}"

    staged_moves = data.get("stagedMoves")
    if staged_moves is not None and not isinstance(staged_moves, dict):
        return "stagedMoves must be a dict {stableKey: entry}"

    return None


@bp.route("/api/staging", methods=["POST"])
def api_save_staging():
    """Save staged changes WITHOUT applying them to files.

    TRUE STAGING APPROACH:
    This endpoint ONLY stores staging data in staging.json.
    NO changes are written to disk until user calls POST /api/staging/apply.

    Requires X-Session-Id header. Rejects if staging is locked by another session.
    Accepts userName and userEmail in request body for user identification.
    """
    # Staging state wire format (shared with frontend data-loading.js:saveStaging).
    # Field names use camelCase to match frontend conventions.
    # Changes to these field names MUST be coordinated with the frontend.
    #
    # Required fields:
    #   sessionId: str
    #   pendingEdits: dict[str, object]   — key is stable key (source_file|type|name)
    #   stagedMoves: dict[str, object]    — key is stable key
    #   stagedCreations: list[object]
    #   stagedObjectDeletions: list[str]  — stable key values
    #   newFiles: list[str]               — file paths
    #   stagedFileCreations: list[object]
    #   stagedFileDeletions: list[object]
    #   stagedFileMoves: list[object]
    #   stagedFolderCreations: list[object]
    #   stagedFolderDeletions: list[object]
    #   stagedFolderMoves: list[object]
    import logging

    log = logging.getLogger("nagios_bulk_editor.staging")

    sm = get_staging_manager()
    data = request.get_json() or {}

    # Warn on unknown fields (possible frontend/backend version mismatch)
    unknown = set(data.keys()) - KNOWN_STAGING_FIELDS
    if unknown:
        log.warning("Unknown staging fields (possible frontend/backend mismatch): %s", unknown)

    # Validate format before processing
    format_error = _validate_staging_format(data)
    if format_error:
        return jsonify({"error": f"Invalid staging format: {format_error}"}), 400

    session_id = request.headers.get("X-Session-Id")
    log.debug(
        "POST /api/staging: %s moves, session=%s",
        len(data.get("stagedMoves", {})),
        session_id,
    )

    # Require session ID for modifications
    if not session_id:
        return jsonify({"error": "X-Session-Id header required"}), 400

    # Check if locked by another session
    if not sm.validate_or_acquire_lock(session_id):
        return jsonify(
            {"error": "Staging is locked by another user", "locked": True}
        ), 423

    data["sessionId"] = session_id

    # Preserve user identity and file/folder ops from existing staging
    existing = sm.get_staging()
    _preserve_existing_session_data(existing, data, session_id)

    # Collect and track files affected by all staging operations.
    # Compute checksums directly into data (not via sm.update_base_checksums,
    # which would be overwritten by the subsequent save_staging_atomic call).
    files_to_track = _collect_affected_files(data, get_config_path())
    if files_to_track:
        base_checksums = data.get("baseFileChecksums", {})
        checksum_mgr = sm.checksums
        for file_path in files_to_track:
            if file_path not in base_checksums:
                checksum = checksum_mgr.compute_file_checksum(file_path)
                if checksum:
                    base_checksums[file_path] = checksum
        data["baseFileChecksums"] = base_checksums

    # Build undo stack with entries for new operations
    data["undoStack"] = _build_undo_entries(data, existing, log)

    # Build final staging data structure and save atomically
    staging_data = _build_staging_data(sm, data)
    save_result = sm.save_staging_atomic(
        staging_data, session_id, staging_operation_lock
    )

    if save_result.success:
        return jsonify(
            {
                "success": True,
                "message": "Staging saved. Use POST /api/staging/apply to write changes to disk.",
            }
        )
    if "locked" in (save_result.error or "").lower():
        return jsonify({"error": save_result.error, "locked": True}), 423
    return jsonify({"error": save_result.error or "Failed to save staging"}), 500


def _validate_apply_preconditions(sm, session_id):
    """Validate preconditions for staging apply.

    Args:
        sm: StagingManager instance
        session_id: Session ID from request

    Returns:
        Tuple of (error_response, staging_data) - error_response is None if valid

    """
    if not session_id:
        return (jsonify({"error": "X-Session-Id header required"}), 400), None

    if not sm.can_modify(session_id):
        logger.warning("Staging apply lock conflict: session_id=%s", session_id)
        return (
            jsonify({"error": "Staging is locked by another user", "locked": True}),
            423,
        ), None

    staging_data = sm.get_staging()
    if not staging_data:
        return (jsonify({"error": "No staging data found"}), 400), None

    conflicts = sm.detect_conflicts()
    if conflicts:
        logger.warning("Staging apply conflicts detected: session_id=%s", session_id)
        return (
            jsonify(
                {
                    "error": "Conflicts detected - files have been modified externally",
                    "conflicts": conflicts,
                    "requiresResolution": True,
                }
            ),
            409,
        ), None

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
        ("folderCreations", lambda: service.apply_folder_creations(staging_data)),
        ("fileCreations", lambda: service.apply_file_creations(staging_data)),
        ("objectComposite", lambda: service.apply_object_composite(staging_data)),
        ("fileMoves", lambda: service.apply_file_moves(staging_data)),
        ("folderMoves", lambda: service.apply_folder_moves(staging_data)),
        ("fileDeletions", lambda: service.apply_file_deletions(staging_data)),
        ("folderDeletions", lambda: service.apply_folder_deletions(staging_data)),
    ]

    applied_summary = {}
    all_details = {}
    phase_errors = []

    for key, apply_fn in phases:
        result = apply_fn()

        if key == "objectComposite":
            # Flatten composite counts into summary
            composite_counts = result.data.get("counts", {})
            applied_summary["objectDeletions"] = composite_counts.get("deletes", 0)
            applied_summary["objectMoves"] = composite_counts.get("moves", 0)
            applied_summary["objectEdits"] = composite_counts.get("edits", 0)
            applied_summary["objectMoveEdits"] = composite_counts.get("move_edits", 0)
            applied_summary["objectCreations"] = composite_counts.get("creates", 0)
        else:
            applied_summary[key] = result.data.get("count", 0)

        errors = result.data.get("errors", [])
        details = result.data.get("details", [])

        if details:
            all_details[key] = details

        if errors:
            phase_errors.extend(errors)
            # Halt on first error - don't continue with subsequent phases
            return applied_summary, all_details, phase_errors, key

    return applied_summary, all_details, phase_errors, None


_PHASE_TO_AUDIT_KEY = {
    "objectComposite": "object_composite",
    "folderCreations": "folder_creations",
    "fileCreations": "file_creations",
    "fileMoves": "file_moves",
    "folderMoves": "folder_moves",
    "fileDeletions": "file_deletions",
    "folderDeletions": "folder_deletions",
}

_OP_SUFFIX_TO_VERB = {
    "creation": "create",
    "deletion": "delete",
    "move": "move",
}


def _make_relative_path(path):
    """Convert an absolute path to a path relative to the config directory's parent.

    For config_path=/etc/nagios/objects and path=/etc/nagios/objects/hosts.cfg,
    returns "objects/hosts.cfg". This preserves the config dir name while
    stripping server filesystem structure from audit logs.
    """
    if not path:
        return path
    config_path = get_config_path()
    if config_path and path.startswith(config_path):
        return os.path.relpath(path, os.path.dirname(config_path))
    return path


def _write_apply_audit_log(staging_data, session_id, all_details, errors, log):
    """Write audit log entries for an apply operation.

    Emits one log_audit() call per individual change, all sharing the same txn ID.

    Args:
        staging_data: Staging data dict
        session_id: Session ID
        all_details: Details from each phase
        errors: List of errors encountered
        log: Logger instance

    Returns:
        Tuple of (success: bool, error_message: Optional[str])

    """
    txn = uuid.uuid4().hex[:8]
    user = format_audit_user(
        name=staging_data.get("userName", ""),
        email=staging_data.get("userEmail", ""),
    )

    try:
        for phase_key, audit_key in _PHASE_TO_AUDIT_KEY.items():
            details = all_details.get(phase_key, [])
            for detail in details:
                if audit_key == "object_composite":
                    action_type = detail.get("action", "")
                    obj_type = detail.get("object_type", "")
                    obj_name = detail.get("object_name", "")

                    if action_type in ("edit", "move_edit"):
                        for change in detail.get("changes", []):
                            log_audit(
                                action="edit",
                                user=user,
                                txn=txn,
                                type=obj_type,
                                name=obj_name,
                                field=change.get("key", ""),
                                op=change.get("type", "modify"),
                                from_val=change.get("from", ""),
                                to_val=change.get("to", change.get("value", "")),
                            )
                    if action_type in ("move", "move_edit"):
                        log_audit(
                            action="move",
                            user=user,
                            txn=txn,
                            type=obj_type,
                            name=obj_name,
                            op="move",
                            from_val=_make_relative_path(detail.get("from_file", "")),
                            to_val=_make_relative_path(detail.get("to_file", "")),
                        )
                    if action_type == "create":
                        log_audit(
                            action="create",
                            user=user,
                            txn=txn,
                            type=obj_type,
                            name=obj_name,
                            op="create",
                        )
                    if action_type == "delete":
                        log_audit(
                            action="delete",
                            user=user,
                            txn=txn,
                            type=obj_type,
                            name=obj_name,
                            op="delete",
                        )
                elif audit_key in (
                    "file_creations",
                    "file_deletions",
                    "file_moves",
                    "folder_creations",
                    "folder_deletions",
                    "folder_moves",
                ):
                    raw_suffix = audit_key.rstrip("s").split("_")[-1]
                    op_verb = _OP_SUFFIX_TO_VERB.get(raw_suffix, raw_suffix)
                    prefix = "file" if "file" in audit_key else "folder"
                    log_audit(
                        action=op_verb,
                        user=user,
                        txn=txn,
                        op=f"{prefix}_{op_verb}",
                        path=detail.get("path", detail.get("from", "")),
                    )

        if errors:
            for error in errors:
                log_audit(action="apply_error", user=user, txn=txn, error=str(error))

        return True, None
    except Exception as e:
        error_msg = f"Failed to write audit log: {e}"
        log.exception(error_msg)
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
    pending_edits = staging_data.get("pendingEdits", {})

    for edit_data in pending_edits.values():
        if not isinstance(edit_data, dict):
            continue
        obj_info = edit_data.get("object", {})
        obj_type = obj_info.get("object_type")
        if not obj_type:
            continue

        name_field = NAME_FIELDS.get(obj_type)
        if not name_field:
            continue

        original = edit_data.get("original", {})
        edited = edit_data.get("edited", {})

        # Check if name field was modified
        if name_field in edited:
            old_name = original.get(name_field)
            new_name = edited.get(name_field)
            if old_name and new_name and old_name != new_name:
                name_changes.append(
                    {
                        "oldName": old_name,
                        "newName": new_name,
                        "objectType": obj_type,
                    }
                )

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
        old_name = change["oldName"]
        new_name = change["newName"]
        refs_updated = service.update_references(objects, old_name, new_name)
        total_refs_updated += refs_updated
        if refs_updated > 0:
            log.info(
                "Updated %s references: %s -> %s", refs_updated, old_name, new_name
            )

    if total_refs_updated > 0:
        # Write modified objects back to their files
        writer = NagiosConfigWriter()
        writer.write_objects_to_original_files(objects)
        # Reload parser to reflect reference changes
        service.reload()

    return total_refs_updated


def _create_pre_apply_backup(staging_data, log):
    """Create a backup before applying staged changes.

    Non-fatal: logs a warning if backup creation fails.

    Args:
        staging_data: Staging data dict (for user identity)
        log: Logger instance

    """
    bm = get_backup_manager()
    if bm:
        try:
            bm.create_backup(
                "pre-apply",
                user_name=staging_data.get("userName", ""),
                user_email=staging_data.get("userEmail", ""),
            )
        except Exception as e:  # noqa: BLE001
            log.warning("Failed to create pre-apply backup: %s", e)


def _capture_git_file_list():
    """Capture current git status file list for verification.

    Returns list of dicts with 'path' and 'status_code', or None if git
    is unavailable.
    """
    try:
        git_svc = get_git_service()
        result = git_svc.get_status()
        if result.success and result.data and result.data.is_repo:
            return [
                {"path": f.path, "status_code": f.status_code}
                for f in result.data.files
            ]
        return None
    except Exception:  # noqa: BLE001
        return None


def _handle_apply_failure(service, failed_phase, apply_ctx):
    """Handle a failed apply phase: log, reload parser, return error response.

    Args:
        service: NagiosService instance
        failed_phase: Name of the phase that failed
        apply_ctx: Dict with 'applied_summary', 'errors', 'session_id', 'log'

    Returns:
        Flask response tuple (jsonify, status_code)

    """
    errors = apply_ctx["errors"]
    session_id = apply_ctx["session_id"]
    log = apply_ctx["log"]

    log.error(
        "Staging apply failed at phase '%s': session_id=%s, errors=%s",
        failed_phase,
        session_id,
        errors,
    )

    # Still reload parser to reflect partial changes
    service.reload()

    return jsonify(
        {
            "success": False,
            "error": f"Apply failed during {failed_phase} phase. Staging preserved for retry.",
            "failedPhase": failed_phase,
            "applied": apply_ctx["applied_summary"],
            "errors": errors,
            "stagingPreserved": True,
        }
    ), 500


def _apply_post_phase_reference_updates(
    service, name_changes, all_details, errors, log
):
    """Apply reference updates after successful apply phases.

    C-06: Updates references in other objects when objects are renamed.
    Non-fatal: logs a warning and appends to errors on failure.

    Args:
        service: NagiosService instance (freshly reloaded)
        name_changes: List of {oldName, newName, objectType} dicts
        all_details: Phase details dict (modified in place to add referenceUpdates)
        errors: Error list (may be appended to on failure)
        log: Logger instance

    Returns:
        Number of references updated

    """
    if not name_changes:
        return 0
    try:
        refs_updated = _apply_reference_updates(service, name_changes, log)
        if refs_updated > 0:
            all_details["referenceUpdates"] = {
                "count": refs_updated,
                "renames": name_changes,
            }
        return refs_updated
    except Exception as ref_err:  # noqa: BLE001
        # Reference update failure is non-fatal - objects were already renamed
        log.warning("Reference update failed (non-fatal): %s", ref_err)
        errors.append(f"Reference update warning: {ref_err}")
        return 0


def _run_post_apply_validation():
    """Run nagios -v validation after a successful apply.

    Returns:
        Validation result dict, or None if validation was not requested/possible

    """
    try:
        config = get_config()
        nagios_bin = config.get("nagios_bin", "")
        nagios_cfg = config.get("nagios_cfg", "")
        if nagios_bin and nagios_cfg:
            from validator import NagiosValidator

            validator = NagiosValidator(nagios_bin, nagios_cfg)
            val_result = validator.validate()
            return val_result.to_dict()
        return {
            "success": None,
            "skipped": True,
            "message": "Nagios binary or config path not configured",
        }
    except Exception as e:  # noqa: BLE001
        return {
            "success": None,
            "skipped": True,
            "message": f"Validation failed to run: {e!s}",
        }


def _build_apply_success_response(result_ctx, audit_ctx):
    """Build the success response for a completed apply operation.

    Handles audit logging, optional validation, and response construction.

    Args:
        result_ctx: Dict with 'applied_summary', 'all_details', 'errors',
                    'refs_updated', 'staging_cleared', 'defer_clear', 'validate_after'
        audit_ctx: Dict with 'staging_data', 'session_id', 'log'

    Returns:
        Flask jsonify response

    """
    applied_summary = result_ctx["applied_summary"]
    errors = result_ctx["errors"]
    total_changes = sum(applied_summary.values())

    # C-10: Track audit log write result and include failure in response
    audit_failed = False
    if total_changes > 0:
        audit_success, audit_error = _write_apply_audit_log(
            audit_ctx["staging_data"],
            audit_ctx["session_id"],
            result_ctx["all_details"],
            errors,
            audit_ctx["log"],
        )
        if not audit_success:
            audit_failed = True
            errors.append(audit_error)

    response_data = {
        "success": True,
        "applied": applied_summary,
        "totalChanges": total_changes,
        "errors": errors or None,
        "referencesUpdated": result_ctx["refs_updated"],
        "stagingCleared": result_ctx["staging_cleared"],
        "stagingDeferred": result_ctx["defer_clear"],
    }
    if audit_failed:
        response_data["warnings"] = [
            "Audit log write failed - changes applied but not logged"
        ]

    verification = result_ctx.get("verification")
    if verification:
        response_data["verification"] = verification

    if result_ctx["validate_after"]:
        response_data["validation"] = _run_post_apply_validation()

    return jsonify(response_data)


@bp.route("/api/staging/apply", methods=["POST"])
def api_apply_staging():
    """Apply all staged changes to disk.

    TRUE STAGING: This endpoint writes all staged changes to the filesystem.
    Changes are applied in the correct order to avoid conflicts:
    1. Create folders (parent -> child)
    2. Create files
    3. Object composite (per-entity merged: deletes, moves/edits/move_edits, creates)
    4. Move files
    5. Move folders
    6. Delete files
    7. Delete folders (child -> parent)

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
    log = logging.getLogger("nagios_bulk_editor.staging")
    sm = get_staging_manager()
    session_id = request.headers.get("X-Session-Id")

    # C-06: Read updateReferences flag from request body (use silent=True to handle missing body)
    # C-10: Read deferClear flag - if true, don't clear staging on success (for atomic apply+commit)
    request_data = request.get_json(silent=True) or {}
    update_references_flag = request_data.get("updateReferences", False)
    defer_clear = request_data.get("deferClear", False)
    validate_after = request_data.get("validate", False)

    # Validate preconditions
    error_response, staging_data = _validate_apply_preconditions(sm, session_id)
    if error_response:
        return error_response

    # C-06: Extract name changes BEFORE applying phases (needed for reference updates)
    name_changes = _extract_name_changes(staging_data) if update_references_flag else []

    log.info(
        "Staging apply: session_id=%s, user=%s, update_references=%s, name_changes=%d",
        session_id,
        staging_data.get("userName", ""),
        update_references_flag,
        len(name_changes),
    )

    service = get_service()
    _create_pre_apply_backup(staging_data, log)

    # Capture pre-apply state for verification
    pre_git_files = _capture_git_file_list()
    pre_parser_objects = [obj.to_dict() for obj in service.parser.objects]

    try:
        applied_summary, all_details, errors, failed_phase = _execute_apply_phases(
            service,
            staging_data,
        )

        if failed_phase:
            apply_ctx = {
                "applied_summary": applied_summary,
                "errors": errors,
                "session_id": session_id,
                "log": log,
            }
            return _handle_apply_failure(service, failed_phase, apply_ctx)

        # All phases succeeded - reload parser, apply reference updates, then clear staging
        service.reload()

        refs_updated = (
            _apply_post_phase_reference_updates(
                service,
                name_changes,
                all_details,
                errors,
                log,
            )
            if update_references_flag
            else 0
        )

        # Post-apply verification
        post_git_files = _capture_git_file_list()
        parsed_objects = [obj.to_dict() for obj in service.parser.objects]
        verification = verify_apply_integrity(
            staging_data=staging_data,
            parsed_objects=parsed_objects,
            pre_git_files=pre_git_files,
            post_git_files=post_git_files,
            config_path=get_config_path(),
            pre_parser_objects=pre_parser_objects,
        )

        # Log verification result to audit trail
        if verification:
            v_status = "passed" if verification["passed"] else "warnings"
            ol = verification.get("objectLevel", {})
            log_audit(
                action="verify",
                user=staging_data.get("userEmail"),
                txn=None,
                status=v_status,
                edits_ok=ol.get("editsVerified", 0),
                edits_fail=ol.get("editsFailed", 0),
                creates_ok=ol.get("creationsVerified", 0),
                creates_fail=ol.get("creationsFailed", 0),
                deletes_ok=ol.get("deletionsVerified", 0),
                deletes_fail=ol.get("deletionsFailed", 0),
                moves_ok=ol.get("movesVerified", 0),
                moves_fail=ol.get("movesFailed", 0),
            )
            if not verification["passed"]:
                for failure in ol.get("failures", []):
                    log_audit(
                        action="verify_warning",
                        user=staging_data.get("userEmail"),
                        detail=failure,
                    )

        # C-10: Only clear staging if deferClear is not requested
        staging_cleared = not defer_clear
        if staging_cleared:
            sm.clear_staging()

        result_ctx = {
            "applied_summary": applied_summary,
            "all_details": all_details,
            "errors": errors,
            "refs_updated": refs_updated,
            "staging_cleared": staging_cleared,
            "defer_clear": defer_clear,
            "validate_after": validate_after,
            "verification": verification,
        }
        audit_ctx = {"staging_data": staging_data, "session_id": session_id, "log": log}
        return _build_apply_success_response(result_ctx, audit_ctx)

    except Exception as e:  # noqa: BLE001
        # Unexpected exception - do NOT clear staging
        log.exception("Error applying staging: %s", e)
        return jsonify(
            {
                "error": f"Failed to apply staging: {e}",
                "stagingPreserved": True,
            }
        ), 500


def _build_stable_key_index(virtual_objects):
    """Build a stable_key -> list_index map from virtual object dicts.

    Uses the same name resolution as StableKey.build() in JS:
    display_name ?? name ?? "idx:{global_index}"
    """
    index_map = {}
    for i, obj in enumerate(virtual_objects):
        name = obj.get("display_name") or obj.get("name") or f"idx:{obj.get('global_index', i)}"
        key = f"{obj['source_file']}|{obj['object_type']}|{name}"
        index_map[key] = i
    return index_map


def _apply_staged_edits_to_virtual(virtual_objects, pending_edits):
    """Apply pending edits to virtual objects in place.

    Args:
        virtual_objects: List of virtual object dicts (modified in place)
        pending_edits: Dict {stableKey: edit_data} from staging

    Returns:
        Set of edited global indices

    """
    key_index = _build_stable_key_index(virtual_objects)
    edited_indices = set()
    for stable_key, edit_data in pending_edits.items():
        if not isinstance(edit_data, dict):
            continue
        idx = key_index.get(stable_key)
        if idx is not None:
            edited_attrs = edit_data.get("edited", {})
            if edited_attrs:
                virtual_objects[idx]["attributes"].update(edited_attrs)
                virtual_objects[idx]["_staged_status"] = "edited"
                edited_indices.add(idx)
    return edited_indices


def _apply_staged_deletions_to_virtual(virtual_objects, staged_deletions):
    """Mark objects for deletion in virtual objects list.

    Args:
        virtual_objects: List of virtual object dicts (modified in place)
        staged_deletions: List of stable key strings from staging

    Returns:
        Set of deleted global indices

    """
    key_index = _build_stable_key_index(virtual_objects)
    deleted_indices = set()
    for stable_key in staged_deletions:
        if not isinstance(stable_key, str):
            continue
        idx = key_index.get(stable_key)
        if idx is not None:
            virtual_objects[idx]["_staged_status"] = "deleted"
            deleted_indices.add(idx)
    return deleted_indices


def _apply_staged_moves_to_virtual(virtual_objects, staged_moves):
    """Mark objects for move in virtual objects list.

    Args:
        virtual_objects: List of virtual object dicts (modified in place)
        staged_moves: Dict {stableKey: move_data} from staging

    """
    key_index = _build_stable_key_index(virtual_objects)
    for stable_key, move_data in staged_moves.items():
        if not isinstance(move_data, dict):
            continue
        target_file = move_data.get("targetFile")
        idx = key_index.get(stable_key)
        if idx is not None:
            virtual_objects[idx]["_staged_status"] = "moved"
            virtual_objects[idx]["_staged_target_file"] = target_file


def _add_staged_creations_to_virtual(virtual_objects, staged_creations):
    """Add staged object creations to virtual objects list.

    Args:
        virtual_objects: List of virtual object dicts (modified in place)
        staged_creations: List of creation dicts from staging

    """
    for creation in staged_creations:
        virtual_objects.append(
            {
                "object_type": creation.get("object_type"),
                "attributes": creation.get("attributes", {}),
                "source_file": creation.get("targetFile"),
                "line_number": -1,  # Doesn't exist yet
                "global_index": -1,
                "_staged_status": "created",
            }
        )


def _collect_virtual_files(virtual_objects, staging_data):
    """Collect the set of files for the virtual tree view.

    Includes files from virtual objects, new files, file creations,
    and removes file deletions.

    Args:
        virtual_objects: List of virtual object dicts
        staging_data: Full staging data dict

    Returns:
        Set of file paths

    """
    files = set(obj["source_file"] for obj in virtual_objects if obj.get("source_file"))

    # Add staged new files
    config_path = get_config_path()
    for file_path in staging_data.get("newFiles", []):
        if not os.path.isabs(file_path):
            file_path = os.path.join(config_path, file_path)
        files.add(file_path)

    # Add staged file creations
    for op in staging_data.get("stagedFileCreations", []):
        if op.get("path"):
            files.add(op["path"])

    # Remove staged file deletions
    for op in staging_data.get("stagedFileDeletions", []):
        files.discard(op.get("path"))

    return files


def _count_staged_operations(staging_data):
    """Count all staged operations for the virtual tree summary.

    Args:
        staging_data: Full staging data dict

    Returns:
        Dict of operation type -> count

    """
    pending_edits = staging_data.get("pendingEdits", {})
    staged_moves = staging_data.get("stagedMoves", {})
    staged_creations = staging_data.get("stagedCreations", [])
    staged_deletions = staging_data.get("stagedObjectDeletions", [])
    new_files = staging_data.get("newFiles", [])

    return {
        "edits": len(pending_edits),
        "moves": len(staged_moves),
        "creations": len(staged_creations),
        "deletions": len(staged_deletions),
        "newFiles": len(new_files) + len(staging_data.get("stagedFileCreations", [])),
        "fileDeletes": len(staging_data.get("stagedFileDeletions", [])),
        "fileMoves": len(staging_data.get("stagedFileMoves", [])),
        "folderCreates": len(staging_data.get("stagedFolderCreations", [])),
        "folderDeletes": len(staging_data.get("stagedFolderDeletions", [])),
        "folderMoves": len(staging_data.get("stagedFolderMoves", [])),
    }


@bp.route("/api/staging/virtual-tree", methods=["GET"])
def api_get_virtual_tree():
    """Get a merged virtual view of objects with staged changes applied.

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
        obj_dict["global_index"] = i
        obj_dict["_staged_status"] = None  # Not staged
        virtual_objects.append(obj_dict)

    if not staging_data:
        # No staging - return current state
        return jsonify(
            {
                "objects": virtual_objects,
                "files": sorted(set(obj["source_file"] for obj in virtual_objects)),
                "stagedCounts": {},
            }
        )

    # Apply staged changes to virtual objects
    _apply_staged_edits_to_virtual(
        virtual_objects, staging_data.get("pendingEdits", {})
    )
    _apply_staged_deletions_to_virtual(
        virtual_objects, staging_data.get("stagedObjectDeletions", [])
    )
    _apply_staged_moves_to_virtual(virtual_objects, staging_data.get("stagedMoves", {}))
    _add_staged_creations_to_virtual(
        virtual_objects, staging_data.get("stagedCreations", [])
    )

    files = _collect_virtual_files(virtual_objects, staging_data)
    staged_counts = _count_staged_operations(staging_data)

    return jsonify(
        {
            "objects": virtual_objects,
            "files": sorted(files),
            "stagedCounts": staged_counts,
            "undoCount": len(staging_data.get("undoStack", [])),
        }
    )


@bp.route("/api/staging/undo", methods=["POST"])
def api_staging_undo():
    """Undo the last staged operation.

    C-04 FIX: Uses atomic undo pattern - peeks at entry first, applies reversal,
    removes from stack, then saves all changes atomically. This prevents data
    loss if save fails after popping.
    """
    sm = get_staging_manager()
    session_id = request.headers.get("X-Session-Id")

    error_response, undo_entry, staging = _validate_undo_preconditions(sm, session_id)
    if error_response:
        return error_response

    action_type = undo_entry.get("type")
    action_data = undo_entry.get("data", {})

    try:
        reversed_action = _execute_undo_action(staging, action_type, action_data)
    except UndoKeyError as e:
        logger.exception("Undo failed due to invalid key: %s", e)
        return jsonify({"error": f"Undo failed: {e}"}), 400

    # C-04 FIX: Now remove from stack (in memory) after successful reversal
    undo_stack = staging.get("undoStack", [])
    if undo_stack:
        undo_stack.pop()
        staging["undoStack"] = undo_stack

    # Save updated staging atomically (reversal + stack removal together)
    if sm.save_staging(staging).success:
        return jsonify(
            {
                "success": True,
                "undone": undo_entry.get("description"),
                "action": reversed_action,
                "undoCount": len(staging.get("undoStack", [])),
            }
        )
    return jsonify({"error": "Failed to save staging"}), 500


def _validate_undo_preconditions(sm, session_id):
    """Validate preconditions for an undo operation.

    Returns:
        Tuple of (error_response, undo_entry, staging).
        error_response is None if all preconditions are met.

    """
    if not session_id:
        return (jsonify({"error": "X-Session-Id header required"}), 400), None, None
    if not sm.can_modify(session_id):
        return (
            (jsonify({"error": "Staging is locked by another user"}), 423),
            None,
            None,
        )

    undo_entry = sm.peek_undo_stack()
    if not undo_entry:
        return (jsonify({"error": "Nothing to undo"}), 404), None, None

    staging = sm.get_staging()
    if not staging:
        return (jsonify({"error": "No staging data"}), 400), None, None

    return None, undo_entry, staging


def _execute_undo_action(staging, action_type, action_data):
    """Execute a single undo action by dispatching to the appropriate handler.

    Returns:
        Description of the reversed action.

    Raises:
        UndoKeyError: If undo data has invalid keys.

    """
    try:
        op_type = OperationType(action_type)
    except ValueError:
        logger.warning("Invalid undo action_type: %s, skipping", action_type)
        return f"Skipped invalid action: {action_type}"

    handler = UNDO_HANDLERS.get(op_type)
    if handler:
        return handler(staging, action_data)

    logger.warning("Unknown undo action_type: %s, skipping", action_type)
    return f"Skipped unknown action: {action_type}"


@bp.route("/api/staging/conflicts", methods=["GET"])
def api_staging_conflicts():
    """Check for conflicts between staged changes and current file state.

    Compares base file checksums (stored when staging began) against
    current file checksums to detect external modifications.
    """
    sm = get_staging_manager()

    conflicts = sm.detect_conflicts()

    return jsonify(
        {
            "hasConflicts": len(conflicts) > 0,
            "conflicts": conflicts,
        }
    )


def _build_staged_changes_summary(staging):
    """Build a summary of staged changes for the commit dialog.

    Counts each type of staged operation and builds a list of
    {type, count, label} dicts for non-zero operation types.

    Args:
        staging: Staging data dict (or empty dict)

    Returns:
        Tuple of (staged_changes list, total_staged_count int)

    """
    # Define operation types: (staging_key, type_name, label_template)
    _OPERATION_TYPES = [
        ("pendingEdits", "edits", "object edit(s)"),
        ("stagedMoves", "moves", "object move(s)"),
        ("stagedCreations", "creations", "new object(s)"),
        ("stagedObjectDeletions", "deletions", "object deletion(s)"),
        ("newFiles", "newFiles", "new file(s)"),
        ("stagedFileCreations", "fileCreations", "file creation(s)"),
        ("stagedFileDeletions", "fileDeletions", "file deletion(s)"),
        ("stagedFileMoves", "fileMoves", "file move(s)"),
        ("stagedFolderCreations", "folderCreations", "folder creation(s)"),
        ("stagedFolderDeletions", "folderDeletions", "folder deletion(s)"),
        ("stagedFolderMoves", "folderMoves", "folder move(s)"),
    ]

    staged_changes = []
    total_staged_count = 0
    for staging_key, type_name, label_template in _OPERATION_TYPES:
        data = staging.get(staging_key)
        count = len(data) if data else 0
        total_staged_count += count
        if count > 0:
            staged_changes.append(
                {
                    "type": type_name,
                    "count": count,
                    "label": f"{count} {label_template}",
                }
            )

    return staged_changes, total_staged_count


def _get_existing_folders(config_path):
    """Get list of existing non-hidden subdirectories under config_path.

    Args:
        config_path: Base configuration directory path

    Returns:
        List of absolute folder paths

    """
    existing_folders = []
    try:
        for root, dirs, _files in os.walk(config_path):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            rel_path = os.path.relpath(root, config_path)
            if rel_path != ".":
                existing_folders.append(os.path.join(config_path, rel_path))
    except OSError:
        pass
    return existing_folders


@bp.route("/api/staging/diff", methods=["GET"])
def api_staging_diff():
    """Get diff of uncommitted changes using git diff.

    Changes are now applied directly to files, so this endpoint returns
    git diff information along with staging metadata for file/folder operations.

    Returns data compatible with both the git page (simple diff view) and
    the commit dialog (which needs staging info for file/folder operations).
    """
    config_path = get_config_path()
    sm = get_staging_manager()
    staging = sm.get_staging() or {}

    # Paths to exclude from diff (backups, staging metadata, git internals)
    excluded_paths = [".backups/", ".staging/", ".git/"]
    existing_folders = _get_existing_folders(config_path)

    try:
        git_svc = get_git_service()
        diff_result = git_svc.get_workspace_diff(excluded_paths)
        if not diff_result.success:
            return jsonify({"error": diff_result.error}), 500

        diffs = diff_result.data["diffs"]
        git_changes = diff_result.data["git_changes"]
        has_git_changes = len(diffs) > 0

        staged_changes, total_staged_count = _build_staged_changes_summary(staging)
        has_staged_changes = total_staged_count > 0

        # Get all objects from parser for context display in commit dialog
        service = get_service()
        all_objects = [
            {
                "global_index": i,
                "object_type": obj.object_type,
                "name": obj.get_name(),
                "display_name": obj.get_display_name(),
                "source_file": obj.source_file,
                "line_number": obj.line_number,
                "attributes": dict(obj.attributes),
            }
            for i, obj in enumerate(service.get_objects())
        ]

        return jsonify(
            {
                # For git page (simple diff view)
                "hasDiffs": has_git_changes,
                "diffs": diffs,
                "count": len(diffs) + total_staged_count,
                # For commit dialog
                "hasChanges": has_git_changes or has_staged_changes,
                "hasGitChanges": has_git_changes,
                "hasStagedChanges": has_staged_changes,
                "gitChanges": git_changes,
                "stagedChanges": staged_changes,
                "totalStagedCount": total_staged_count,
                "staging": staging,
                "configPath": config_path,
                "existingFolders": existing_folders,
                # All objects from parser for context display
                "objects": all_objects,
            }
        )

    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"Failed to get diff: {e!s}"}), 500


@bp.route("/api/staging/analyze-references", methods=["GET"])
def api_staging_analyze_references():
    """Analyze pending name changes and count affected references.

    Returns information about objects whose names are being changed,
    and how many references to those objects exist in the configuration.
    Uses the same broad scan as update_references() to ensure the count
    matches what will actually be updated at apply time.
    """
    sm = get_staging_manager()
    staging = sm.get_staging()

    if not staging:
        return jsonify({"nameChanges": [], "totalReferences": 0})

    service = get_service()
    objects = service.get_objects()
    pending_edits = staging.get("pendingEdits", {})
    name_changes = []
    total_references = 0

    for stable_key, edit_data in pending_edits.items():
        if not isinstance(edit_data, dict):
            continue
        parsed = parse_stable_key(stable_key)
        if not parsed:
            continue

        obj = service._find_by_identity(
            parsed["source_file"], parsed["object_type"], parsed["name"]
        )
        if obj is None:
            continue
        original = edit_data.get("original", {})
        edited = edit_data.get("edited", {})

        # Check if name field changed
        name_field = NAME_FIELDS.get(obj.object_type, "name")
        if not name_field:
            continue

        old_name = original.get(name_field) or obj.attributes.get(name_field)
        new_name = edited.get(name_field)

        if old_name and new_name and old_name != new_name:
            # Scan all attributes of all objects (same logic as update_references)
            # Skip the renamed object itself — its name change is the primary edit,
            # not a reference.
            refs = []
            for ref_obj in objects:
                if ref_obj is obj:
                    continue
                for field_name, value in ref_obj.attributes.items():
                    values = [v.strip() for v in value.split(",")]
                    if old_name in values:
                        new_values = [new_name if v == old_name else v for v in values]
                        refs.append(
                            {
                                "objectType": ref_obj.object_type,
                                "objectName": ref_obj.get_display_name(),
                                "field": field_name,
                                "sourceFile": ref_obj.source_file,
                                "oldValue": value,
                                "newValue": ",".join(new_values),
                            }
                        )

            ref_count = len(refs)
            total_references += ref_count

            name_changes.append(
                {
                    "stableKey": stable_key,
                    "objectType": obj.object_type,
                    "oldName": old_name,
                    "newName": new_name,
                    "referenceCount": ref_count,
                    "references": refs,
                }
            )

    return jsonify(
        {
            "nameChanges": name_changes,
            "totalReferences": total_references,
            "hasNameChanges": len(name_changes) > 0,
        }
    )


@bp.route("/api/staging/commit", methods=["POST"])
def api_staging_commit():
    """Apply all staged changes and release the lock.

    This endpoint:
    1. Applies all staged moves (object moves between files)
    2. Creates a backup
    3. Clears the staging lock
    4. Reloads the parser

    Moves are applied here (not on every save) to keep global_index stable during editing.

    Requires X-Session-Id header matching the lock owner.
    """
    sm = get_staging_manager()
    session_id = request.headers.get("X-Session-Id")

    # Check lock ownership before committing
    if not session_id:
        return jsonify({"error": "X-Session-Id header required"}), 400

    if not sm.validate_or_acquire_lock(session_id):
        return jsonify(
            {
                "error": "Cannot commit: staging is locked by another user",
                "locked": True,
            }
        ), 423  # 423 Locked

    staging = sm.get_staging()
    current_app.extensions.get("app_config", {})

    # Apply staged changes to disk before committing
    if staging:
        # Pass through request JSON data (e.g., updateReferences flag)
        request_data = request.get_json(silent=True) or {}
        with current_app.test_client() as client:
            apply_resp = client.post(
                "/api/staging/apply",
                json=request_data,
                headers={
                    "X-Session-Id": session_id,
                    "Content-Type": "application/json",
                },
            )
            if apply_resp.status_code >= 400:  # noqa: PLR2004
                apply_data = apply_resp.get_json()
                error_msg = (
                    apply_data.get("error", "Failed to apply staged changes")
                    if apply_data
                    else "Failed to apply staged changes"
                )
                return jsonify(
                    {
                        "success": False,
                        "error": error_msg,
                    }
                ), apply_resp.status_code

    # Check if there are uncommitted git changes (the real indicator of pending work)
    try:
        git_svc = get_git_service()
        changes_result = git_svc.has_uncommitted_changes()
        has_changes = changes_result.success and changes_result.data
    except Exception:  # noqa: BLE001
        has_changes = False

    if not has_changes:
        return jsonify({"success": False, "error": "No changes to commit"})

    # Get user identity from staging data or empty
    user_name = staging.get("userName", "") if staging else ""
    user_email = staging.get("userEmail", "") if staging else ""

    # Note: Backup is created in /api/staging/apply BEFORE changes are written to disk

    try:
        # Clear staging (releases lock)
        sm.clear_staging()

        # Reload configuration
        get_service().reload()

        # Log to audit file
        log_audit(
            action="staging_commit",
            user=format_audit_user(name=user_name, email=user_email),
        )

        return jsonify({"success": True})

    except Exception as e:  # noqa: BLE001
        logger.exception("Commit failed: %s", e)
        return jsonify(
            {
                "success": False,
                "error": str(e),
            }
        ), 500
