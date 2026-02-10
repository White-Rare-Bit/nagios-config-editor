"""Staging Manager for Nagios Bulk Editor

Handles staging state, lock management, and multi-session coordination.
Uses a file-based approach with atomic writes for thread safety.

TRUE STAGING ARCHITECTURE:
- All operations (object edits, moves, creations, deletions AND file/folder operations)
  are stored in staging.json without writing to disk
- Changes are only written to disk when user clicks "Apply"
- Supports undo via undo stack
- Detects conflicts via file checksums
"""

import contextlib
import hashlib
import json
import logging
import multiprocessing
import os
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from nagios_model import OperationResult

# Schema version
STAGING_SCHEMA_VERSION = 3

# Set up structured logging
logger = logging.getLogger("nagios_bulk_editor.staging")


# =============================================================================
# Typed Staging Data Structures
# =============================================================================

class OperationType(Enum):
    EDIT = "edit"
    MOVE = "move"
    CREATE = "create"
    DELETE = "delete"
    CREATION = "creation"
    DELETION = "deletion"
    NEW_FILE = "new_file"
    FILE_CREATE = "file_create"
    FILE_DELETE = "file_delete"
    FILE_MOVE = "file_move"
    FOLDER_CREATE = "folder_create"
    FOLDER_DELETE = "folder_delete"
    FOLDER_MOVE = "folder_move"
    # Bulk operation types - undo reverses all items at once
    BULK_MOVE = "bulk_move"
    BULK_EDIT = "bulk_edit"
    BULK_CREATION = "bulk_creation"
    BULK_DELETION = "bulk_deletion"


class StagingStatus(Enum):
    EMPTY = "empty"
    ACTIVE = "active"
    RESTORE_PENDING = "restore_pending"


@dataclass
class PendingEdit:
    key: str  # stable_key
    object_type: str
    new_attributes: dict[str, str]
    original_attributes: dict[str, str] | None = None
    op_id: str | None = None


@dataclass
class StagedMove:
    key: str
    source_file: str
    target_file: str
    object_type: str
    op_id: str | None = None


@dataclass
class StagedCreation:
    object_type: str
    attributes: dict[str, str]
    target_file: str
    op_id: str | None = None


@dataclass
class StagedDeletion:
    key: str
    object_type: str
    source_file: str
    op_id: str | None = None


@dataclass
class StagedFileOp:
    path: str
    target_path: str | None = None  # for moves
    op_id: str | None = None


@dataclass
class UndoEntry:
    action_type: OperationType
    data: dict[str, Any]
    description: str
    op_id: str
    timestamp: str | None = None


@dataclass
class StagingState:
    """Typed representation of the staging data.

    Provides structured access to staging fields and serialization
    methods for backward-compatible JSON storage.
    """

    session_id: str | None = None
    schema_version: int = STAGING_SCHEMA_VERSION
    user_name: str = ""
    user_email: str = ""
    pending_edits: dict[str, Any] = field(default_factory=dict)
    staged_moves: dict[str, Any] = field(default_factory=dict)
    staged_creations: list[Any] = field(default_factory=list)
    staged_object_deletions: list[Any] = field(default_factory=list)
    new_files: list[str] = field(default_factory=list)
    staged_file_creations: list[Any] = field(default_factory=list)
    staged_file_deletions: list[Any] = field(default_factory=list)
    staged_file_moves: list[Any] = field(default_factory=list)
    staged_folder_creations: list[Any] = field(default_factory=list)
    staged_folder_deletions: list[Any] = field(default_factory=list)
    staged_folder_moves: list[Any] = field(default_factory=list)
    undo_stack: list[Any] = field(default_factory=list)
    base_file_checksums: dict[str, str] = field(default_factory=dict)
    status: StagingStatus = StagingStatus.EMPTY
    last_modified: float | None = None
    last_modified_iso: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict (camelCase keys for backward compat)."""
        return {
            "schemaVersion": self.schema_version,
            "sessionId": self.session_id,
            "userName": self.user_name,
            "userEmail": self.user_email,
            "pendingEdits": self.pending_edits,
            "stagedMoves": self.staged_moves,
            "stagedCreations": self.staged_creations,
            "stagedObjectDeletions": self.staged_object_deletions,
            "newFiles": self.new_files,
            "stagedFileCreations": self.staged_file_creations,
            "stagedFileDeletions": self.staged_file_deletions,
            "stagedFileMoves": self.staged_file_moves,
            "stagedFolderCreations": self.staged_folder_creations,
            "stagedFolderDeletions": self.staged_folder_deletions,
            "stagedFolderMoves": self.staged_folder_moves,
            "undoStack": self.undo_stack,
            "baseFileChecksums": self.base_file_checksums,
            "status": self.status.value,
            "lastModified": self.last_modified,
            "lastModifiedISO": self.last_modified_iso,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StagingState":
        """Deserialize from JSON dict."""
        if not data:
            return cls()

        # Determine status with migration logic
        status = StagingStatus.EMPTY
        if "status" in data:
            status = StagingStatus(data["status"])
        elif data.get("sessionId"):
            status = StagingStatus.ACTIVE

        return cls(
            session_id=data.get("sessionId"),
            schema_version=data.get("schemaVersion", STAGING_SCHEMA_VERSION),
            user_name=data.get("userName", ""),
            user_email=data.get("userEmail", ""),
            pending_edits=data.get("pendingEdits", {}),
            staged_moves=data.get("stagedMoves", {}),
            staged_creations=data.get("stagedCreations", []),
            staged_object_deletions=data.get("stagedObjectDeletions", []),
            new_files=data.get("newFiles", []),
            staged_file_creations=data.get("stagedFileCreations", []),
            staged_file_deletions=data.get("stagedFileDeletions", []),
            staged_file_moves=data.get("stagedFileMoves", []),
            staged_folder_creations=data.get("stagedFolderCreations", []),
            staged_folder_deletions=data.get("stagedFolderDeletions", []),
            staged_folder_moves=data.get("stagedFolderMoves", []),
            undo_stack=data.get("undoStack", []),
            base_file_checksums=data.get("baseFileChecksums", {}),
            status=status,
            last_modified=data.get("lastModified"),
            last_modified_iso=data.get("lastModifiedISO"),
        )

    @property
    def is_empty(self) -> bool:
        """Check if staging has any operations."""
        return not any([
            self.pending_edits,
            self.staged_moves,
            self.staged_creations,
            self.staged_object_deletions,
            self.staged_file_creations,
            self.staged_file_deletions,
            self.staged_file_moves,
            self.staged_folder_creations,
            self.staged_folder_deletions,
            self.staged_folder_moves,
        ])


# =============================================================================
# Composed Manager Classes
# =============================================================================

class ChecksumManager:
    """Manages file checksums and conflict detection.

    Extracted from StagingManager to reduce class responsibilities.
    Requires a reference to the parent StagingManager for staging data access.
    """

    def __init__(self, staging_manager: "StagingManager"):
        """Initialize with reference to parent staging manager.

        Args:
            staging_manager: Parent StagingManager instance for staging data access

        """
        self._sm = staging_manager

    def compute_file_checksum(self, file_path: str) -> str | None:
        """Compute SHA256 checksum of a file.

        Args:
            file_path: Path to the file

        Returns:
            Hex digest of SHA256 hash, or None if file doesn't exist

        """
        try:
            path = Path(file_path)
            if not path.exists():
                return None
            return hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as e:
            logger.warning("Failed to compute checksum for %s: %s", file_path, e)
            return None

    def compute_base_checksums(self, file_paths: list[str] | None = None) -> dict[str, str]:
        """Compute and store checksums for files that will be modified.

        This should be called when staging first begins to capture the
        "base" state of files before modifications.

        Args:
            file_paths: List of file paths to checksum. If None, checksums
                       all .cfg files in config directory.

        Returns:
            Dictionary of {path: checksum}

        """
        checksums = {}

        if file_paths is None:
            # Checksum all .cfg files in config directory
            for cfg_file in self._sm.config_path.rglob("*.cfg"):
                if ".staging" not in str(cfg_file):
                    checksum = self.compute_file_checksum(str(cfg_file))
                    if checksum:
                        checksums[str(cfg_file)] = checksum
        else:
            for file_path in file_paths:
                checksum = self.compute_file_checksum(file_path)
                if checksum:
                    checksums[file_path] = checksum

        return checksums

    def update_base_checksums(self, file_paths: list[str]) -> OperationResult:
        """Update base checksums for specific files.

        Called when a file is first staged for modification.

        Args:
            file_paths: Paths to update checksums for

        Returns:
            OperationResult with success status

        """
        staging = self._sm.get_staging()
        if not staging:
            return OperationResult(False, "No staging data")

        staging = self._sm.migrate_staging_schema(staging)
        base_checksums = staging.get("baseFileChecksums", {})

        for file_path in file_paths:
            # Only store checksum if we don't already have one for this file
            # (preserve the original base state)
            if file_path not in base_checksums:
                checksum = self.compute_file_checksum(file_path)
                if checksum:
                    base_checksums[file_path] = checksum

        staging["baseFileChecksums"] = base_checksums
        return self._sm.save_staging(staging)

    def detect_conflicts(self) -> list[dict[str, Any]]:
        """Detect files that have been modified externally since staging began.

        Compares current file checksums against stored base checksums.

        Returns:
            List of conflict dictionaries: [{path, baseChecksum, currentChecksum}]

        """
        staging = self._sm.get_staging()
        if not staging:
            return []

        base_checksums = staging.get("baseFileChecksums", {})
        conflicts = []

        for file_path, base_checksum in base_checksums.items():
            current_checksum = self.compute_file_checksum(file_path)

            # File was deleted externally
            if current_checksum is None:
                conflicts.append({
                    "path": file_path,
                    "baseChecksum": base_checksum,
                    "currentChecksum": None,
                    "type": "deleted",
                })
            # File was modified externally
            elif current_checksum != base_checksum:
                conflicts.append({
                    "path": file_path,
                    "baseChecksum": base_checksum,
                    "currentChecksum": current_checksum,
                    "type": "modified",
                })

        return conflicts


class UndoStackManager:
    """Manages the undo stack for staging operations.

    Extracted from StagingManager to reduce class responsibilities.
    Requires a reference to the parent StagingManager for staging data access.
    """

    def __init__(self, staging_manager: "StagingManager"):
        """Initialize with reference to parent staging manager.

        Args:
            staging_manager: Parent StagingManager instance for staging data access

        """
        self._sm = staging_manager

    def add_to_undo_stack(self, action_type: str, data: dict, description: str, staging: dict | None = None) -> str | None:
        """Add an action to the undo stack.

        Args:
            action_type: Type of action (e.g., 'edit', 'move', 'create', 'delete',
                        'file_create', 'file_delete', 'file_move', etc.)
            data: Data needed to reverse the action
            description: Human-readable description of the action
            staging: Optional staging dict to modify (if None, reads fresh and saves)

        Returns:
            The ID of the undo entry, or None if failed

        """
        save_after = False
        if staging is None:
            staging = self._sm.get_staging()
            if not staging:
                return None
            staging = self._sm.migrate_staging_schema(staging)
            save_after = True

        undo_id = str(uuid.uuid4())[:8]
        undo_entry = {
            "id": undo_id,
            "type": action_type,
            "data": data,
            "description": description,
            "timestamp": time.time(),
        }

        staging["undoStack"].append(undo_entry)

        if save_after:
            if self._sm.save_staging(staging).success:
                logger.debug("Added undo entry: %s - %s", action_type, description)
                return undo_id
            return None
        logger.debug("Queued undo entry: %s - %s", action_type, description)
        return undo_id

    def peek_undo_stack(self) -> dict | None:
        """Peek at the last action from the undo stack without removing it.

        C-04 FIX: Used for atomic undo operations - peek first, then remove
        only after successfully applying the reversal and saving.

        Returns:
            The undo entry, or None if stack is empty

        """
        staging = self._sm.get_staging()
        if not staging:
            return None

        staging = self._sm.migrate_staging_schema(staging)
        undo_stack = staging.get("undoStack", [])

        if not undo_stack:
            return None

        return undo_stack[-1]

    def pop_undo_stack(self) -> dict | None:
        """Pop and return the last action from the undo stack.

        NOTE: Prefer using peek_undo_stack() + manual removal in atomic operations
        to avoid data loss if subsequent operations fail.

        Returns:
            The undo entry, or None if stack is empty or failed

        """
        staging = self._sm.get_staging()
        if not staging:
            return None

        staging = self._sm.migrate_staging_schema(staging)
        undo_stack = staging.get("undoStack", [])

        if not undo_stack:
            return None

        undo_entry = undo_stack.pop()
        staging["undoStack"] = undo_stack

        if self._sm.save_staging(staging).success:
            logger.debug("Popped undo entry: %s - %s", undo_entry.get("type"), undo_entry.get("description"))
            return undo_entry
        return None

    def get_undo_stack_count(self) -> int:
        """Get the number of items in the undo stack.

        Returns:
            Count of undoable actions

        """
        staging = self._sm.get_staging()
        if not staging:
            return 0
        return len(staging.get("undoStack", []))

    def clear_undo_stack(self) -> OperationResult:
        """Clear the undo stack.

        Returns:
            OperationResult with success status

        """
        staging = self._sm.get_staging()
        if not staging:
            return OperationResult(True)

        staging["undoStack"] = []
        return self._sm.save_staging(staging)


class FileOperationsStager:
    """Manages staging of file and folder operations.

    Extracted from StagingManager to reduce class responsibilities.
    Requires a reference to the parent StagingManager for staging data access.
    """

    def __init__(self, staging_manager: "StagingManager"):
        """Initialize with reference to parent staging manager.

        Args:
            staging_manager: Parent StagingManager instance for staging data access

        """
        self._sm = staging_manager

    def _stage_operation(
        self,
        op_type: str,
        staging_field: str,
        entry_data: dict[str, Any],
        undo_type: str,
        undo_data: dict[str, Any],
        undo_description: str,
        log_message: str,
        checksum_paths: list[str] | None = None,
    ) -> OperationResult:
        """Common helper for staging file/folder operations.

        Centralizes the 9-step staging pattern:
        1. Log operation
        2. Get staging
        3. Check if staging exists
        4. Migrate schema
        5. (Optional) Update checksums for source files
        6. Generate op_id and build entry
        7. Append to staging array
        8. Add to undo stack
        9. Save staging and return result

        Args:
            op_type: Operation type for logging (e.g., 'stage_file_creation')
            staging_field: Field name in staging dict (e.g., 'stagedFileCreations')
            entry_data: Data for the staging entry (path, sourcePath, targetPath, etc.)
            undo_type: Undo operation type (e.g., 'file_create')
            undo_data: Data needed to reverse the operation
            undo_description: Human-readable description for undo stack
            log_message: Message to log on success
            checksum_paths: Optional list of file paths to capture checksums for

        Returns:
            OperationResult with op_id in data field on success

        """
        if self._sm._op_logger:
            self._sm._op_logger.info("staging", op_type, params=entry_data)  # noqa: PLE1205

        staging = self._sm.get_staging()
        if not staging:
            return OperationResult(False, "No staging data")

        staging = self._sm.migrate_staging_schema(staging)

        # Capture checksums for source files if needed
        if checksum_paths:
            self._sm.checksums.update_base_checksums(checksum_paths)

        # Generate operation ID and build entry
        op_id = str(uuid.uuid4())[:8]
        entry = {
            "id": op_id,
            "timestamp": time.time(),
            **entry_data,
        }
        staging[staging_field].append(entry)

        # Add undo data with op_id
        undo_data_with_id = {**undo_data, "op_id": op_id}
        self._sm.undo.add_to_undo_stack(undo_type, undo_data_with_id, undo_description, staging)

        result = self._sm.save_staging(staging)
        if result.success:
            logger.info(log_message)
            return OperationResult(True, data=op_id)
        return result

    def stage_file_creation(self, file_path: str) -> OperationResult:
        """Stage a file creation (doesn't create on disk yet)."""
        return self._stage_operation(
            op_type="stage_file_creation",
            staging_field="stagedFileCreations",
            entry_data={"path": file_path},
            undo_type="file_create",
            undo_data={"path": file_path},
            undo_description=f"Create file {os.path.basename(file_path)}",
            log_message=f"Staged file creation: {file_path}",
        )

    def stage_file_deletion(self, file_path: str) -> OperationResult:
        """Stage a file deletion (doesn't delete from disk yet)."""
        return self._stage_operation(
            op_type="stage_file_deletion",
            staging_field="stagedFileDeletions",
            entry_data={"path": file_path},
            undo_type="file_delete",
            undo_data={"path": file_path},
            undo_description=f"Delete file {os.path.basename(file_path)}",
            log_message=f"Staged file deletion: {file_path}",
            checksum_paths=[file_path],
        )

    def stage_file_move(self, source_path: str, target_path: str) -> OperationResult:
        """Stage a file move (doesn't move on disk yet)."""
        return self._stage_operation(
            op_type="stage_file_move",
            staging_field="stagedFileMoves",
            entry_data={"sourcePath": source_path, "targetPath": target_path},
            undo_type="file_move",
            undo_data={"sourcePath": source_path, "targetPath": target_path},
            undo_description=f"Move file {os.path.basename(source_path)} to {os.path.dirname(target_path)}",
            log_message=f"Staged file move: {source_path} -> {target_path}",
            checksum_paths=[source_path],
        )

    def stage_folder_creation(self, folder_path: str) -> OperationResult:
        """Stage a folder creation (doesn't create on disk yet)."""
        return self._stage_operation(
            op_type="stage_folder_creation",
            staging_field="stagedFolderCreations",
            entry_data={"path": folder_path},
            undo_type="folder_create",
            undo_data={"path": folder_path},
            undo_description=f"Create folder {os.path.basename(folder_path)}",
            log_message=f"Staged folder creation: {folder_path}",
        )

    def stage_folder_deletion(self, folder_path: str) -> OperationResult:
        """Stage a folder deletion (doesn't delete from disk yet)."""
        # Compute checksum paths for all .cfg files in folder
        folder = Path(folder_path)
        checksum_paths = None
        if folder.is_dir():
            file_paths = [str(f) for f in folder.rglob("*.cfg")]
            if file_paths:
                checksum_paths = file_paths

        return self._stage_operation(
            op_type="stage_folder_deletion",
            staging_field="stagedFolderDeletions",
            entry_data={"path": folder_path},
            undo_type="folder_delete",
            undo_data={"path": folder_path},
            undo_description=f"Delete folder {os.path.basename(folder_path)}",
            log_message=f"Staged folder deletion: {folder_path}",
            checksum_paths=checksum_paths,
        )

    def stage_folder_move(self, source_path: str, target_path: str) -> OperationResult:
        """Stage a folder move (doesn't move on disk yet)."""
        # Compute checksum paths for all .cfg files in folder
        folder = Path(source_path)
        checksum_paths = None
        if folder.is_dir():
            file_paths = [str(f) for f in folder.rglob("*.cfg")]
            if file_paths:
                checksum_paths = file_paths

        return self._stage_operation(
            op_type="stage_folder_move",
            staging_field="stagedFolderMoves",
            entry_data={"sourcePath": source_path, "targetPath": target_path},
            undo_type="folder_move",
            undo_data={"sourcePath": source_path, "targetPath": target_path},
            undo_description=f"Move folder {os.path.basename(source_path)} to {os.path.dirname(target_path)}",
            log_message=f"Staged folder move: {source_path} -> {target_path}",
            checksum_paths=checksum_paths,
        )

    def unstage_operation(self, op_id: str, op_type: str) -> OperationResult:
        """Remove a staged operation by its ID.

        Args:
            op_id: The operation ID to remove
            op_type: Type of operation ('file_create', 'file_delete', etc.)

        Returns:
            OperationResult with success status

        """
        staging = self._sm.get_staging()
        if not staging:
            return OperationResult(False, "No staging data")

        staging = self._sm.migrate_staging_schema(staging)

        type_to_field = {
            "file_create": "stagedFileCreations",
            "file_delete": "stagedFileDeletions",
            "file_move": "stagedFileMoves",
            "folder_create": "stagedFolderCreations",
            "folder_delete": "stagedFolderDeletions",
            "folder_move": "stagedFolderMoves",
        }

        field = type_to_field.get(op_type)
        if not field:
            return OperationResult(False, f"Unknown operation type: {op_type}")

        ops = staging.get(field, [])
        original_len = len(ops)
        staging[field] = [op for op in ops if op.get("id") != op_id]

        if len(staging[field]) < original_len:
            result = self._sm.save_staging(staging)
            if result.success:
                logger.info("Unstaged %s operation: %s", op_type, op_id)
            return result

        return OperationResult(False, f"Operation {op_id} not found")


class StagingManager:
    """Manages staging state and locks for the Nagios Bulk Editor.

    TRUE STAGING SYSTEM:
    The staging system now implements full staging where:
    1. Lock management - ensures only one session can edit at a time
    2. Metadata storage - tracks user info, timestamps for conflict detection
    3. Object operations - stores edits, moves, creations, deletions
    4. File/folder operations - stores file/folder creates, deletes, moves
    5. Undo support - maintains an undo stack for reverting operations
    6. Conflict detection - tracks base file checksums to detect external changes

    NO changes are written to disk until user clicks "Apply".

    This class uses composition to delegate specialized operations:
    - checksums: ChecksumManager for file checksums and conflict detection
    - undo: UndoStackManager for undo stack operations
    - file_ops: FileOperationsStager for file/folder staging operations

    These sub-managers are exposed as public attributes for direct access,
    and common methods are also available directly on StagingManager for
    backward compatibility.
    """

    def __init__(self, config_path: str, op_logger=None):
        """Initialize the staging manager.

        Args:
            config_path: Path to the Nagios configuration directory
            op_logger: Optional OperationLogger instance

        """
        self.config_path = Path(config_path)
        self.staging_dir = self.config_path / ".staging"
        self.staging_file = self.staging_dir / "staging.json"
        self._op_logger = op_logger

        # Initialize composed managers
        self.checksums = ChecksumManager(self)
        self.undo = UndoStackManager(self)
        self.file_ops = FileOperationsStager(self)

        logger.debug("StagingManager initialized for %s", config_path)

    def _ensure_staging_dir(self) -> None:
        """Ensure the staging directory exists with a .gitignore."""
        self.staging_dir.mkdir(parents=True, exist_ok=True)

        gitignore_path = self.staging_dir / ".gitignore"
        if not gitignore_path.exists():
            gitignore_path.write_text("*\n")

    def _is_empty_staging(self, data: dict | None) -> bool:
        """Check if staging data is effectively empty.

        Staging is considered empty if:
        - data is None or empty dict
        - status is EMPTY

        Args:
            data: Staging data dictionary

        Returns:
            True if staging is empty (no lock held)

        """
        if not data:
            return True

        # Check status field (new approach)
        if data.get("status") == StagingStatus.EMPTY.value:
            return True

        # Legacy fallback: files without 'status' field
        return bool(not data.get("status") and not data.get("sessionId"))

    def get_staging(self) -> dict | None:
        """Get the current staging data.

        Returns:
            Staging data dictionary, or None if no staging exists

        """
        if not self.staging_file.exists():
            return None

        try:
            content = self.staging_file.read_text()
            if not content.strip():
                return None
            return json.loads(content)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Failed to read staging file: %s", e)
            return None

    def save_staging(self, data: dict) -> OperationResult:
        """Save staging data with metadata."""
        if self._op_logger:
            self._op_logger.debug("staging", "save_staging", session_id=data.get("sessionId"))  # noqa: PLE1205
        self._ensure_staging_dir()

        # Add metadata
        timestamp = time.time()
        data["lastModified"] = timestamp
        data["lastModifiedISO"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp))

        temp_path = None
        try:
            # Atomic write: write to temp file, then rename
            temp_fd, temp_path = tempfile.mkstemp(
                suffix=".tmp",
                dir=str(self.staging_dir),
            )
            try:
                with open(temp_fd, "w") as f:
                    json.dump(data, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())

                # Atomic rename
                Path(temp_path).replace(self.staging_file)
                logger.debug("Staging saved for session %s", data.get("sessionId"))
                return OperationResult(True)
            except Exception as write_err:
                # Clean up temp file on failure
                try:
                    if temp_path:
                        Path(temp_path).unlink()
                except OSError as cleanup_err:
                    # Log at CRITICAL level with temp file path for manual recovery
                    logger.critical(
                        "DISK_LEAK: Failed to cleanup staging temp file. Manual intervention required. "
                        "temp_file=%s, original_error=%s, cleanup_error=%s",
                        temp_path, write_err, cleanup_err,
                    )
                    # Raise exception instead of continuing silently
                    raise OSError(
                        f"Staging write succeeded but temp file cleanup failed: {temp_path}. "
                        f"Investigate disk space/permissions. Cleanup error: {cleanup_err}",
                    ) from cleanup_err
                raise
        except OSError as e:
            logger.exception("Failed to save staging: %s", e)
            return OperationResult(False, f"Failed to save staging: {e}")

    def save_staging_atomic(self, data: dict, session_id: str, lock: "multiprocessing.Lock") -> OperationResult:
        """Save staging data with atomic lock validation.

        This method ensures the lock check and save operation are atomic,
        preventing race conditions where another session clears staging
        between the lock check and save.

        Args:
            data: Staging data to save
            session_id: Session ID that should own the lock
            lock: Threading lock to serialize operations

        Returns:
            OperationResult with success=True if saved,
            or success=False with error if lock validation failed

        """
        with lock:
            # Re-validate lock ownership inside the critical section
            owner = self.get_lock_owner()
            if owner is not None and owner != session_id:
                return OperationResult(False, "Staging is locked by another user")

            # Now save atomically
            return self.save_staging(data)

    def clear_staging(self) -> OperationResult:
        """Clear all staging data."""
        if self._op_logger:
            self._op_logger.info("staging", "clear_staging")  # noqa: PLE1205
        if not self.staging_file.exists():
            return OperationResult(True)

        try:
            self.staging_file.unlink()
            logger.info("Staging cleared")
            return OperationResult(True)
        except OSError as e:
            logger.exception("Failed to clear staging: %s", e)
            return OperationResult(False, f"Failed to clear staging: {e}")

    def has_staging(self) -> bool:
        """Check if there is active staging (lock held).

        Returns:
            True if staging exists and has a session lock

        """
        data = self.get_staging()
        return not self._is_empty_staging(data)

    # Mapping of staging data fields to their count keys in get_staging_info output
    _STAGING_COUNT_FIELDS = (
        ("pendingEdits", "edits"),
        ("stagedMoves", "moves"),
        ("stagedCreations", "creations"),
        ("stagedObjectDeletions", "objectDeletions"),
        ("newFiles", "newFiles"),
        ("stagedFileCreations", "fileCreations"),
        ("stagedFileDeletions", "fileDeletions"),
        ("stagedFileMoves", "fileMoves"),
        ("stagedFolderCreations", "folderCreations"),
        ("stagedFolderDeletions", "folderDeletions"),
        ("stagedFolderMoves", "folderMoves"),
    )

    def _count_staged_operations(self, data: dict) -> dict[str, int]:
        """Count all staged operations from staging data.

        Returns:
            Dict mapping count keys to their counts (only non-zero entries)

        """
        counts = {}
        for data_field, count_key in self._STAGING_COUNT_FIELDS:
            items = data.get(data_field, {} if data_field in ("pendingEdits", "stagedMoves") else [])
            if items:
                counts[count_key] = len(items)
        return counts

    def get_staging_info(self) -> dict[str, Any]:
        """Get summary info about current staging.

        Returns counts for all staged operations including file/folder ops.

        Returns:
            Dictionary with hasStaging, counts, undoCount, and metadata

        """
        data = self.get_staging()

        if self._is_empty_staging(data):
            return {
                "hasStaging": False,
                "counts": {},
                "undoCount": 0,
            }

        data = self.migrate_staging_schema(data)
        counts = self._count_staged_operations(data)

        result = {
            "hasStaging": True,
            "status": data.get("status", ""),
            "counts": counts,
            "totalCount": sum(counts.values()),
            "undoCount": len(data.get("undoStack", [])),
        }

        if "lastModified" in data:
            result["lastModified"] = data["lastModified"]

        return result

    # =========================================================================
    # Lock Management
    # =========================================================================

    def get_lock_owner(self) -> str | None:
        """Get the session ID that owns the staging lock.

        Returns:
            Session ID string, or None if no lock exists

        """
        data = self.get_staging()
        if not data:
            return None
        return data.get("sessionId")

    def can_modify(self, session_id: str) -> bool:
        """Check if a session can modify staging.

        A session can modify if:
        - No staging exists (no lock held)
        - Session is the lock owner

        Args:
            session_id: Session ID to check

        Returns:
            True if session can modify

        """
        owner = self.get_lock_owner()
        if owner is None:
            return True
        return owner == session_id

    def validate_or_acquire_lock(self, session_id: str) -> bool:
        """Validate session owns lock, or acquire it if available.

        Args:
            session_id: Session ID to validate/acquire for

        Returns:
            True if session has lock, False if locked by another session

        Warning:
            RACE CONDITION: This check is NOT atomic with subsequent operations.
            Between this check returning True and a subsequent save_staging() call,
            another session could clear_staging() and acquire the lock, causing
            the original session to write without holding the lock.

            For atomic lock validation + save, use save_staging_atomic() instead,
            which holds a lock during validation and write.

        Example of UNSAFE usage::

            # BAD: Race condition between check and save
            if sm.validate_or_acquire_lock(session_id):
                # Another session could clear_staging() here!
                sm.save_staging(data)  # May write without lock

        Example of SAFE usage::

            # GOOD: Atomic lock validation + save
            result = sm.save_staging_atomic(data, session_id, lock)
            if not result.success:
                # Handle lock conflict

        """
        owner = self.get_lock_owner()

        # No lock exists - session can acquire
        if owner is None:
            return True

        # Session already owns the lock
        return owner == session_id

    def get_lock_status(self, session_id: str | None) -> dict[str, Any]:
        """Get detailed lock status.

        Args:
            session_id: Session ID to check against

        Returns:
            Dictionary with locked, owner, and isOwner fields

        """
        owner = self.get_lock_owner()

        if owner is None:
            return {
                "locked": False,
                "owner": None,
                "isOwner": False,
            }

        return {
            "locked": True,
            "owner": owner,
            "isOwner": (session_id == owner) if session_id else False,
        }

    # =========================================================================
    # Schema Management
    # =========================================================================

    def get_empty_staging_structure(self) -> dict[str, Any]:
        """Get an empty staging structure with all required fields.

        Returns:
            Dictionary with default empty values for all staging fields

        """
        return StagingState().to_dict()

    def migrate_staging_schema(self, data: dict) -> dict:
        """Ensure staging data has all required fields.

        Args:
            data: Existing staging data

        Returns:
            Staging data with all required fields populated

        """
        if not data:
            return self.get_empty_staging_structure()

        # Ensure all fields exist
        defaults = self.get_empty_staging_structure()
        for key in defaults:
            if key not in data:
                data[key] = defaults[key]
        data["schemaVersion"] = STAGING_SCHEMA_VERSION

        # Determine status from content if not explicitly set by caller
        if data.get("status") == StagingStatus.EMPTY.value and data.get("sessionId"):
            data["status"] = StagingStatus.ACTIVE.value

        return data

    # =========================================================================
    # Undo Stack Management (delegates to UndoStackManager)
    # =========================================================================

    def add_to_undo_stack(self, action_type: str, data: dict, description: str, staging: dict | None = None) -> str | None:
        """Add an action to the undo stack. Delegates to self.undo."""
        return self.undo.add_to_undo_stack(action_type, data, description, staging)

    def peek_undo_stack(self) -> dict | None:
        """Peek at the last action from the undo stack. Delegates to self.undo."""
        return self.undo.peek_undo_stack()

    def pop_undo_stack(self) -> dict | None:
        """Pop and return the last action from the undo stack. Delegates to self.undo."""
        return self.undo.pop_undo_stack()

    def get_undo_stack_count(self) -> int:
        """Get the number of items in the undo stack. Delegates to self.undo."""
        return self.undo.get_undo_stack_count()

    def clear_undo_stack(self) -> OperationResult:
        """Clear the undo stack. Delegates to self.undo."""
        return self.undo.clear_undo_stack()

    # =========================================================================
    # Checksum and Conflict Detection (delegates to ChecksumManager)
    # =========================================================================

    def compute_file_checksum(self, file_path: str) -> str | None:
        """Compute SHA256 checksum of a file. Delegates to self.checksums."""
        return self.checksums.compute_file_checksum(file_path)

    def compute_base_checksums(self, file_paths: list[str] | None = None) -> dict[str, str]:
        """Compute checksums for files. Delegates to self.checksums."""
        return self.checksums.compute_base_checksums(file_paths)

    def update_base_checksums(self, file_paths: list[str]) -> OperationResult:
        """Update base checksums for specific files. Delegates to self.checksums."""
        return self.checksums.update_base_checksums(file_paths)

    def detect_conflicts(self) -> list[dict[str, Any]]:
        """Detect files modified externally since staging began. Delegates to self.checksums."""
        return self.checksums.detect_conflicts()

    # =========================================================================
    # File/Folder Staging Operations (delegates to FileOperationsStager)
    # =========================================================================

    def stage_file_creation(self, file_path: str) -> OperationResult:
        """Stage a file creation. Delegates to self.file_ops."""
        return self.file_ops.stage_file_creation(file_path)

    def stage_file_deletion(self, file_path: str) -> OperationResult:
        """Stage a file deletion. Delegates to self.file_ops."""
        return self.file_ops.stage_file_deletion(file_path)

    def stage_file_move(self, source_path: str, target_path: str) -> OperationResult:
        """Stage a file move. Delegates to self.file_ops."""
        return self.file_ops.stage_file_move(source_path, target_path)

    def stage_folder_creation(self, folder_path: str) -> OperationResult:
        """Stage a folder creation. Delegates to self.file_ops."""
        return self.file_ops.stage_folder_creation(folder_path)

    def stage_folder_deletion(self, folder_path: str) -> OperationResult:
        """Stage a folder deletion. Delegates to self.file_ops."""
        return self.file_ops.stage_folder_deletion(folder_path)

    def stage_folder_move(self, source_path: str, target_path: str) -> OperationResult:
        """Stage a folder move. Delegates to self.file_ops."""
        return self.file_ops.stage_folder_move(source_path, target_path)

    def unstage_operation(self, op_id: str, op_type: str) -> OperationResult:
        """Remove a staged operation by its ID. Delegates to self.file_ops."""
        return self.file_ops.unstage_operation(op_id, op_type)

    def stage_bulk_rename(
        self, session_id: str, renames: list[dict],
    ) -> OperationResult:
        """Stage a bulk rename as individual pendingEdits with a grouped undo entry.

        Args:
            session_id: Session ID for lock validation
            renames: List of dicts with keys:
                - stableKey: stable key for the object
                - globalIndex: global index of the object
                - object: object summary dict (name, object_type, source_file, etc.)
                - originalAttrs: original attributes dict
                - editedAttrs: dict of changed attributes (name field + any ref updates)

        Returns:
            OperationResult with data=count of staged edits on success

        """
        if self._op_logger:
            self._op_logger.info(  # noqa: PLE1205
                "staging", "stage_bulk_rename",
                params={"count": len(renames)},
            )

        staging = self.get_staging()
        if not staging:
            # Initialize fresh staging
            staging = self.get_empty_staging_structure()
            staging["sessionId"] = session_id
            staging["status"] = StagingStatus.ACTIVE.value

        staging = self.migrate_staging_schema(staging)

        pending_edits = staging.get("pendingEdits", {})
        undo_items = []

        for entry in renames:
            key = str(entry["globalIndex"])
            pending_edits[key] = {
                "globalIndex": key,
                "object": entry["object"],
                "original": entry["originalAttrs"],
                "edited": entry["editedAttrs"],
            }
            undo_items.append({"key": key, "object": entry["object"]})

        staging["pendingEdits"] = pending_edits

        # Add a single grouped undo entry
        self.undo.add_to_undo_stack(
            OperationType.BULK_EDIT.value,
            {"items": undo_items},
            f"Bulk rename: {len(renames)} object(s)",
            staging,
        )

        result = self.save_staging(staging)
        if result.success:
            logger.info("Staged bulk rename: %d object(s)", len(renames))
            return OperationResult(True, data=len(renames))
        return result

    def stage_bulk_move(
        self, session_id: str, moves: list[dict],
    ) -> OperationResult:
        """Stage a bulk move as individual stagedMoves with a grouped undo entry.

        Args:
            session_id: Session ID for lock validation
            moves: List of dicts with keys:
                - stableKey: stable key for the object
                - object: object summary dict
                - sourceFile: original source file
                - targetFile: destination file

        Returns:
            OperationResult with data=count of staged moves on success

        """
        if self._op_logger:
            self._op_logger.info(  # noqa: PLE1205
                "staging", "stage_bulk_move",
                params={"count": len(moves)},
            )

        staging = self.get_staging()
        if not staging:
            staging = self.get_empty_staging_structure()
            staging["sessionId"] = session_id
            staging["status"] = StagingStatus.ACTIVE.value

        staging = self.migrate_staging_schema(staging)

        staged_moves = staging.get("stagedMoves", {})
        undo_items = []

        # Capture checksums for source files
        source_files = list({entry["sourceFile"] for entry in moves})
        self.checksums.update_base_checksums(source_files)

        for entry in moves:
            key = entry["stableKey"]
            staged_moves[key] = {
                "stableKey": key,
                "object": entry["object"],
                "sourceFile": entry["sourceFile"],
                "targetFile": entry["targetFile"],
            }
            undo_items.append({"key": key, "object": entry["object"]})

        staging["stagedMoves"] = staged_moves

        self.undo.add_to_undo_stack(
            OperationType.BULK_MOVE.value,
            {"items": undo_items},
            f"Bulk move: {len(moves)} object(s)",
            staging,
        )

        result = self.save_staging(staging)
        if result.success:
            logger.info("Staged bulk move: %d object(s)", len(moves))
            return OperationResult(True, data=len(moves))
        return result

    def get_total_staged_count(self) -> int:
        """Get total count of all staged operations.

        Returns:
            Total number of staged changes

        """
        info = self.get_staging_info()
        counts = info.get("counts", {})
        return sum(counts.values())


# =============================================================================
# Stable Key Utilities
# =============================================================================

def generate_stable_key(source_file: str, object_type: str, name: str) -> str:
    """Generate a stable key for an object.

    The stable key format is: "source_file|object_type|name"
    This key remains stable across parser reloads and index changes.

    Args:
        source_file: Path to the source file
        object_type: Type of the object (host, service, etc.)
        name: The object's name (varies by type)

    Returns:
        Stable key string

    """
    return f"{source_file}|{object_type}|{name}"


def parse_stable_key(key: str) -> dict[str, str] | None:
    """Parse a stable key back into its components.

    Args:
        key: Stable key string

    Returns:
        Dictionary with source_file, object_type, name keys, or None if invalid

    """
    parts = key.split("|")
    if len(parts) != 3:  # noqa: PLR2004
        return None

    return {
        "source_file": parts[0],
        "object_type": parts[1],
        "name": parts[2],
    }


def generate_stable_key_for_object(obj: Any) -> str:
    """Generate a stable key for a NagiosObject.

    Args:
        obj: NagiosObject instance

    Returns:
        Stable key string

    """
    from nagios_model import get_object_name
    name = get_object_name(obj.object_type, obj.attributes)
    return generate_stable_key(obj.source_file, obj.object_type, name)


# =============================================================================
# Undo Helper Functions
# =============================================================================

class UndoKeyError(ValueError):
    """Raised when undo operation has invalid/empty key."""



def _filter_staged_entries(entries, target_key):
    """Remove an entry from a staged dict by key.

    Raises UndoKeyError if target_key is empty/None (prevents silent no-op).

    Args:
        entries: Dict {key: data, ...} of staged entries
        target_key: Key to match for removal

    Returns:
        New dict with target_key removed

    Raises:
        UndoKeyError: If target_key is None or empty string

    """
    if not entries:
        return {}

    if target_key is None or target_key == "":
        raise UndoKeyError(
            "Cannot filter staged entries with empty target_key. "
            "This indicates corrupted undo data or a bug in undo entry creation.",
        )

    result = dict(entries)
    str_key = str(target_key)
    result.pop(str_key, None)
    return result


def _remove_by_op_id(staging: dict, field: str, op_id: str) -> int:
    """Remove staged entry by operation ID.

    Common helper for undo operations that filter by op_id.

    Args:
        staging: Staging data dict to modify
        field: Field name containing the operation list (e.g., 'stagedFileCreations')
        op_id: Operation ID to match for removal

    Returns:
        Number of entries removed

    """
    ops = staging.get(field, [])
    original_len = len(ops)
    staging[field] = [op for op in ops if op.get("id") != op_id]
    return original_len - len(staging[field])


def _undo_file_create(staging, action_data):
    """Remove staged file creation."""
    _remove_by_op_id(staging, "stagedFileCreations", action_data.get("op_id"))
    return f"Unstaged file creation: {action_data.get('path')}"


def _undo_file_delete(staging, action_data):
    """Remove staged file deletion."""
    _remove_by_op_id(staging, "stagedFileDeletions", action_data.get("op_id"))
    return f"Unstaged file deletion: {action_data.get('path')}"


def _undo_file_move(staging, action_data):
    """Remove staged file move."""
    _remove_by_op_id(staging, "stagedFileMoves", action_data.get("op_id"))
    return f"Unstaged file move: {action_data.get('sourcePath')}"


def _undo_folder_create(staging, action_data):
    """Remove staged folder creation."""
    _remove_by_op_id(staging, "stagedFolderCreations", action_data.get("op_id"))
    return f"Unstaged folder creation: {action_data.get('path')}"


def _undo_folder_delete(staging, action_data):
    """Remove staged folder deletion."""
    _remove_by_op_id(staging, "stagedFolderDeletions", action_data.get("op_id"))
    return f"Unstaged folder deletion: {action_data.get('path')}"


def _undo_folder_move(staging, action_data):
    """Remove staged folder move."""
    _remove_by_op_id(staging, "stagedFolderMoves", action_data.get("op_id"))
    return f"Unstaged folder move: {action_data.get('sourcePath')}"


def _undo_edit(staging, action_data):
    """Remove pending edit."""
    edit_key = str(action_data["key"]) if "key" in action_data else str(action_data.get("globalIndex", ""))
    pending_edits = staging.get("pendingEdits", {})
    staging["pendingEdits"] = _filter_staged_entries(pending_edits, edit_key)
    return f"Unstaged edit: {action_data.get('object', {}).get('name', 'unknown')}"


def _undo_move(staging, action_data):
    """Remove staged move."""
    move_key = str(action_data["key"]) if "key" in action_data else str(action_data.get("globalIndex", ""))
    staged_moves = staging.get("stagedMoves", {})
    staging["stagedMoves"] = _filter_staged_entries(staged_moves, move_key)
    return f"Unstaged move: {action_data.get('object', {}).get('name', 'unknown')}"


def _undo_creation(staging, action_data):
    """Remove staged creation."""
    creation_id = action_data.get("creationId")
    staged_creations = staging.get("stagedCreations", [])
    staging["stagedCreations"] = [
        c for c in staged_creations
        if str(c.get("id", "")) != str(creation_id)
    ]
    return f"Unstaged creation: {action_data.get('name', 'unknown')}"


def _undo_deletion(staging, action_data):
    """Remove staged deletion."""
    deletion_key = str(action_data["key"]) if "key" in action_data else str(action_data.get("globalIndex", ""))
    staged_deletions = staging.get("stagedObjectDeletions", [])
    # stagedObjectDeletions is an array of ints — filter by int comparison
    try:
        target_int = int(deletion_key)
        staging["stagedObjectDeletions"] = [d for d in staged_deletions if d != target_int]
    except (ValueError, TypeError):
        pass
    return f"Unstaged deletion: {action_data.get('deletion', {}).get('name', 'unknown')}"


def _undo_new_file(staging, action_data):
    """Remove new file tracking."""
    file_path = action_data.get("path")
    new_files = staging.get("newFiles", [])
    staging["newFiles"] = [f for f in new_files if f != file_path]
    return f"Unstaged new file: {os.path.basename(file_path or '')}"


def _undo_bulk_move(staging, action_data):
    """Remove all staged moves from a bulk operation."""
    items = action_data.get("items", [])
    count = 0
    for item in items:
        move_key = str(item["key"]) if "key" in item else str(item.get("globalIndex", ""))
        staged_moves = staging.get("stagedMoves", {})
        before_len = len(staged_moves)
        staging["stagedMoves"] = _filter_staged_entries(staged_moves, move_key)
        if len(staging["stagedMoves"]) < before_len:
            count += 1
    return f"Unstaged bulk move: {count} object(s)"


def _undo_bulk_edit(staging, action_data):
    """Remove all pending edits from a bulk operation."""
    items = action_data.get("items", [])
    count = 0
    for item in items:
        edit_key = str(item["key"]) if "key" in item else str(item.get("globalIndex", ""))
        pending_edits = staging.get("pendingEdits", {})
        before_len = len(pending_edits)
        staging["pendingEdits"] = _filter_staged_entries(pending_edits, edit_key)
        if len(staging["pendingEdits"]) < before_len:
            count += 1
    return f"Unstaged bulk edit: {count} object(s)"


def _undo_bulk_creation(staging, action_data):
    """Remove all staged creations from a bulk operation."""
    items = action_data.get("items", [])
    creation_ids = {str(item.get("creationId", "")) for item in items}
    staged_creations = staging.get("stagedCreations", [])
    before_len = len(staged_creations)
    staging["stagedCreations"] = [
        c for c in staged_creations
        if str(c.get("id", "")) not in creation_ids
    ]
    count = before_len - len(staging["stagedCreations"])
    return f"Unstaged bulk creation: {count} object(s)"


def _undo_bulk_deletion(staging, action_data):
    """Remove all staged deletions from a bulk operation."""
    items = action_data.get("items", [])
    # Collect all int keys to remove
    keys_to_remove = set()
    for item in items:
        deletion_key = str(item["key"]) if "key" in item else str(item.get("globalIndex", ""))
        with contextlib.suppress(ValueError, TypeError):
            keys_to_remove.add(int(deletion_key))
    staged_deletions = staging.get("stagedObjectDeletions", [])
    before_len = len(staged_deletions)
    staging["stagedObjectDeletions"] = [d for d in staged_deletions if d not in keys_to_remove]
    count = before_len - len(staging["stagedObjectDeletions"])
    return f"Unstaged bulk deletion: {count} object(s)"


UNDO_HANDLERS = {
    OperationType.FILE_CREATE: _undo_file_create,
    OperationType.FILE_DELETE: _undo_file_delete,
    OperationType.FILE_MOVE: _undo_file_move,
    OperationType.FOLDER_CREATE: _undo_folder_create,
    OperationType.FOLDER_DELETE: _undo_folder_delete,
    OperationType.FOLDER_MOVE: _undo_folder_move,
    OperationType.EDIT: _undo_edit,
    OperationType.MOVE: _undo_move,
    OperationType.CREATION: _undo_creation,
    OperationType.DELETION: _undo_deletion,
    OperationType.NEW_FILE: _undo_new_file,
    # Bulk operation handlers
    OperationType.BULK_MOVE: _undo_bulk_move,
    OperationType.BULK_EDIT: _undo_bulk_edit,
    OperationType.BULK_CREATION: _undo_bulk_creation,
    OperationType.BULK_DELETION: _undo_bulk_deletion,
}
