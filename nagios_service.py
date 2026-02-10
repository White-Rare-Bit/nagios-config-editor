"""Nagios Service Layer

Provides business logic and unified CRUD operations with automatic parser reload.
Eliminates temporal coupling: callers no longer need to remember to call reload_config().
"""

import multiprocessing
import os
import re
import shutil
from contextlib import contextmanager
from pathlib import Path

from file_operations import (
    add_object_to_file,
    delete_object_from_file,
    edit_object_in_file,
    is_safe_path,
    move_object_between_files,
)
from nagios_model import NAME_FIELDS, NagiosObject, OperationResult
from nagios_parser import NagiosConfigParser
from staging_manager import (
    StagingManager,
    StagingState,
    parse_stable_key,
)


class NagiosService:
    """Service layer for Nagios configuration management.

    Wraps the parser and file operations, providing a unified interface
    with automatic state synchronization (reload after write).
    """

    def __init__(self, config_path: str, staging_manager: StagingManager | None = None, op_logger=None):
        self._config_path = config_path
        self._parser: NagiosConfigParser | None = None
        self._lock = multiprocessing.Lock()
        self._staging_manager = staging_manager
        self._op_logger = op_logger
        # Flag to indicate parser state is inconsistent with disk state.
        # When True, all CRUD operations are blocked until explicit reload succeeds.
        self._parser_corrupted = False

    @property
    def config_path(self) -> str:
        return self._config_path

    @config_path.setter
    def config_path(self, path: str) -> None:
        with self._lock:
            self._config_path = path
            self._parser = None

    @property
    def parser(self) -> NagiosConfigParser:
        """Get or create the parser (thread-safe)."""
        with self._lock:
            if self._parser is None:
                self._parser = NagiosConfigParser(self._config_path)
                self._parser.parse_all()
            return self._parser

    def reload(self) -> NagiosConfigParser:
        """Force reload of configuration (thread-safe).

        Also clears the _parser_corrupted flag on success, allowing
        CRUD operations to resume after a reload.
        """
        with self._lock:
            self._parser = NagiosConfigParser(self._config_path)
            self._parser.parse_all()
            self._parser_corrupted = False  # Clear corrupted flag on successful reload
            if self._op_logger:
                self._op_logger.debug("parser", "reload", params={"config_path": self._config_path})  # noqa: PLE1205
            return self._parser

    def _validate_path_safety(self, path: str, path_type: str) -> tuple[bool, str | None]:
        """Path validation wrapper preventing path traversal attacks.

        Used by 7 apply methods (folder/file creations, deletions, moves)
        to ensure consistent path safety validation.

        Args:
            path: Path to validate
            path_type: Type of path ("file" or "folder") for error messages

        Returns:
            Tuple of (is_safe, error_message). error_message is None if safe.

        """
        safe_result = is_safe_path(path, self._config_path)
        if not safe_result.success:
            return (False, f"Unsafe {path_type} path {path}: {safe_result.error}")
        return (True, None)

    def _build_apply_result(self, operation: str, count: int, errors: list, details: list = None) -> dict:
        """Construct result dict with consistent structure for apply operations.

        op_logger provides structured logging for error tracking.

        Args:
            operation: Operation name (e.g., "folder_creations", "object_deletions")
            count: Number of items successfully processed
            errors: List of error messages
            details: Optional list of detail dicts about processed items

        Returns:
            Dict with success=True, count, errors, and optional details

        """
        result = {"success": True, "count": count, "errors": errors}
        if details is not None:
            result["details"] = details
        return result

    def _find_object_by_entry(self, entry: dict, lookup_type: str) -> NagiosObject | None:
        """Find object by globalIndex from entry dict.

        Frontend sends globalIndex for edits (validated: Object.fromEntries
        produces dict with globalIndex as key).

        Args:
            entry: Entry dict with globalIndex field
            lookup_type: Operation type ("edit") for logging

        Returns:
            Found NagiosObject or None

        Note:
            Caller must hold self._lock to prevent race conditions during iteration.

        """
        p = self.parser
        raw_index = entry.get("globalIndex")
        if raw_index is not None:
            global_index = int(raw_index)
            if 0 <= global_index < len(p.objects):
                return p.objects[global_index]

        if self._op_logger:
            self._op_logger.warning("service", f"find_object_for_{lookup_type}",  # noqa: PLE1205
                                    params={"entry": str(entry)}, result="not_found")
        return None

    @contextmanager
    def modification_context(self):
        """Context manager for parser modification with lock held.

        Usage:
            with service.modification_context() as p:
                # modify p.objects
                # write changes
        """
        with self._lock:
            if self._parser is None:
                self._parser = NagiosConfigParser(self._config_path)
                self._parser.parse_all()
            yield self._parser

    def get_typed_staging(self) -> StagingState | None:
        """Get typed staging state.

        Returns:
            StagingState instance, or None if no staging manager or no staging data

        """
        if not self._staging_manager:
            return None
        staging_data = self._staging_manager.get_staging()
        if not staging_data:
            return None
        return StagingState.from_dict(staging_data)

    # =========================================================================
    # Query Methods
    # =========================================================================

    def get_objects(self) -> list:
        """Get all parsed objects.

        Returns:
            List of NagiosObject instances

        """
        return self.parser.objects

    def find_object_by_index(self, idx: int) -> NagiosObject | None:
        """Find object by global index.

        Args:
            idx: Index in parser.objects list

        Returns:
            NagiosObject if index is valid, None otherwise

        """
        objects = self.parser.objects
        if 0 <= idx < len(objects):
            return objects[idx]
        return None

    def search_objects(self, query: str, object_type: str = None,
                       field: str = None, use_regex: bool = False) -> list:
        """Search objects using the parser's find_objects method.

        Args:
            query: Search term or regex pattern
            object_type: Optional filter by object type
            field: Optional filter by specific field
            use_regex: Whether to treat query as regex

        Returns:
            List of matching NagiosObject instances

        """
        return self.parser.find_objects(query, object_type, field, use_regex)

    def get_object_stats(self) -> dict:
        """Get statistics about parsed objects.

        Returns:
            Dict with counts by type, total count, and file count

        """
        objects = self.parser.objects
        type_counts = {}
        files = set()
        for obj in objects:
            type_counts[obj.object_type] = type_counts.get(obj.object_type, 0) + 1
            if obj.source_file:
                files.add(obj.source_file)
        return {
            "total": len(objects),
            "by_type": type_counts,
            "file_count": len(files),
        }

    # =========================================================================
    # Domain Logic (moved from app.py)
    # =========================================================================

    def get_name_field(self, object_type: str) -> str:
        """Get the name field for a given object type."""
        return NAME_FIELDS.get(object_type, "name")

    def find_object_by_stable_key(self, stable_key: str) -> tuple | None:
        """Find an object by its stable key.

        Args:
            stable_key: Stable key in format "source_file|object_type|display_name"

        Returns:
            Tuple of (global_index, NagiosObject) or None if not found

        """
        parsed = parse_stable_key(stable_key)
        if not parsed:
            return None

        source_file = parsed["source_file"]
        obj_type = parsed["object_type"]
        target_name = parsed["name"]

        p = self.parser
        for idx, obj in enumerate(p.objects):
            if obj.source_file != source_file:
                continue
            if obj.object_type != obj_type:
                continue
            if obj.get_display_name() == target_name:
                return (idx, obj)

        return None

    def transform_name(self, name: str, find_pattern: str = "", replace_with: str = "",
                       prefix: str = "", suffix: str = "", use_regex: bool = False) -> str | None:
        """Transform a name using find/replace and prefix/suffix operations.

        Returns the transformed name, or None if regex is invalid.
        """
        new_name = name

        if find_pattern:
            if use_regex:
                try:
                    new_name = re.sub(find_pattern, replace_with, new_name)
                except re.error:
                    return None
            else:
                new_name = new_name.replace(find_pattern, replace_with)

        if prefix:
            new_name = prefix + new_name
        if suffix:
            new_name = new_name + suffix

        return new_name

    def update_references(self, objects: list[NagiosObject], old_name: str, new_name: str) -> int:
        """Update all references to an object when it's renamed.

        Returns the count of individual references updated.
        """
        references_updated = 0
        for obj in objects:
            for field_name, value in list(obj.attributes.items()):
                values = [v.strip() for v in value.split(",")]
                if old_name in values:
                    replacement_count = values.count(old_name)
                    new_values = [new_name if v == old_name else v for v in values]
                    obj.attributes[field_name] = ",".join(new_values)
                    references_updated += replacement_count
        return references_updated

    # =========================================================================
    # CRUD Operations (unified file_operations + reload)
    # =========================================================================

    def _reload_parser_safe(self, old_parser: NagiosConfigParser | None, file_path: str = None) -> OperationResult:
        """Safely reload parser, setting corrupted flag on failure.

        Args:
            old_parser: Previous parser instance to restore on failure
            file_path: Optional path of file that was modified (for error message)

        Returns:
            OperationResult with success status. On failure, _parser_corrupted flag is set
            to block subsequent operations until explicit reload succeeds.

        """
        try:
            new_parser = NagiosConfigParser(self._config_path)
            new_parser.parse_all()
            self._parser = new_parser
            self._parser_corrupted = False
            return OperationResult(True)
        except Exception as e:  # noqa: BLE001
            # Set corrupted flag to block subsequent operations
            self._parser_corrupted = True
            # Restore old parser for read operations (queries still work)
            self._parser = old_parser
            file_info = f" File {file_path} was modified but" if file_path else " File was modified but"
            error_msg = (
                f"CRITICAL:{file_info} parser state is inconsistent. "
                f"All operations are blocked. Run POST /api/reload to resync parser. "
                f"If reload fails, manual inspection of config files required. "
                f"Original error: {e}"
            )
            if self._op_logger:
                self._op_logger.exception("service", "parser_reload",  # noqa: PLE1205
                                     params={"file_path": file_path, "corrupted": True},
                                     error=str(e))
            return OperationResult(False, error_msg)

    def _check_parser_state(self) -> OperationResult | None:
        """Check if parser state is corrupted and return error if so.

        Returns:
            OperationResult with error if corrupted, None if OK to proceed.

        """
        if self._parser_corrupted:
            return OperationResult(
                False,
                "CRITICAL: Parser state is inconsistent with disk state. "
                "All operations are blocked until explicit reload succeeds. "
                "Run POST /api/reload to resync parser.",
            )
        return None

    def create_object(self, target_file: str, obj_type: str, attrs: dict[str, str],
                      after_block_line: int | None = None) -> OperationResult:
        """Create a new object in a file.

        Args:
            target_file: Path to the target config file
            obj_type: Object type (host, service, etc.)
            attrs: Attribute key-value pairs
            after_block_line: Line number to insert after (None = end)

        Returns:
            OperationResult with success status

        """
        with self._lock:
            # Check if parser state is corrupted
            corrupted_error = self._check_parser_state()
            if corrupted_error:
                return corrupted_error

            try:
                result = add_object_to_file(target_file, obj_type, attrs, after_block_line)
                if not result.success:
                    if self._op_logger:
                        self._op_logger.error("service", "create_object", params={"target_file": target_file, "obj_type": obj_type}, error=result.error)  # noqa: PLE1205
                    return result
                # Save old parser for rollback on reload failure
                old_parser = self._parser
                reload_result = self._reload_parser_safe(old_parser, file_path=target_file)
                if not reload_result.success:
                    return reload_result
                if self._op_logger:
                    self._op_logger.info("service", "create_object", params={"target_file": target_file, "obj_type": obj_type}, result="success")  # noqa: PLE1205
                return OperationResult(True)
            except Exception as e:  # noqa: BLE001
                if self._op_logger:
                    self._op_logger.exception("service", "create_object", params={"target_file": target_file, "obj_type": obj_type}, error=str(e))  # noqa: PLE1205
                return OperationResult(False, f"Create failed: {e}")

    def update_object(self, source_file: str, line_number: int,
                      new_attrs: dict[str, str], obj_type: str,
                      inline_comments: dict | None = None) -> OperationResult:
        """Update an object's attributes in place.

        Args:
            source_file: Path to the config file
            line_number: Line number where object starts
            new_attrs: New attributes dictionary
            obj_type: Object type (for formatting)
            inline_comments: If provided, preserves inline comments on attributes.

        Returns:
            OperationResult with success status

        """
        with self._lock:
            # Check if parser state is corrupted
            corrupted_error = self._check_parser_state()
            if corrupted_error:
                return corrupted_error

            try:
                result = edit_object_in_file(
                    source_file, line_number, new_attrs, obj_type,
                    inline_comments=inline_comments,
                )
                if not result.success:
                    if self._op_logger:
                        self._op_logger.error("service", "update_object", params={"source_file": source_file, "line_number": line_number, "obj_type": obj_type}, error=result.error)  # noqa: PLE1205
                    return result
                # Save old parser for rollback on reload failure
                old_parser = self._parser
                reload_result = self._reload_parser_safe(old_parser, file_path=source_file)
                if not reload_result.success:
                    return reload_result
                if self._op_logger:
                    self._op_logger.info("service", "update_object", params={"source_file": source_file, "line_number": line_number, "obj_type": obj_type}, result="success")  # noqa: PLE1205
                return OperationResult(True)
            except Exception as e:  # noqa: BLE001
                if self._op_logger:
                    self._op_logger.exception("service", "update_object", params={"source_file": source_file, "line_number": line_number, "obj_type": obj_type}, error=str(e))  # noqa: PLE1205
                return OperationResult(False, f"Update failed: {e}")

    def delete_object(self, source_file: str, line_number: int) -> OperationResult:
        """Delete an object from its file.

        Args:
            source_file: Path to the config file
            line_number: Line number where object starts

        Returns:
            OperationResult with success status

        """
        with self._lock:
            # Check if parser state is corrupted
            corrupted_error = self._check_parser_state()
            if corrupted_error:
                return corrupted_error

            try:
                result = delete_object_from_file(source_file, line_number)
                if not result.success:
                    if self._op_logger:
                        self._op_logger.error("service", "delete_object", params={"source_file": source_file, "line_number": line_number}, error=result.error)  # noqa: PLE1205
                    return result
                # Save old parser for rollback on reload failure
                old_parser = self._parser
                reload_result = self._reload_parser_safe(old_parser, file_path=source_file)
                if not reload_result.success:
                    return reload_result
                if self._op_logger:
                    self._op_logger.info("service", "delete_object", params={"source_file": source_file, "line_number": line_number}, result="success")  # noqa: PLE1205
                return OperationResult(True)
            except Exception as e:  # noqa: BLE001
                if self._op_logger:
                    self._op_logger.exception("service", "delete_object", params={"source_file": source_file, "line_number": line_number}, error=str(e))  # noqa: PLE1205
                return OperationResult(False, f"Delete failed: {e}")

    def move_object(self, source_file: str, source_line: int,
                    target_file: str, obj_type: str, attrs: dict[str, str],
                    insert_line: int | None = None) -> OperationResult:
        """Move an object from one file to another.

        Args:
            source_file: Path to source config file
            source_line: Line number of object in source file
            target_file: Path to target config file
            obj_type: Object type
            attrs: Object attributes
            insert_line: Optional line to insert at in target

        Returns:
            OperationResult with success status

        """
        with self._lock:
            # Check if parser state is corrupted
            corrupted_error = self._check_parser_state()
            if corrupted_error:
                return corrupted_error

            try:
                result = move_object_between_files(source_file, source_line,
                                                   target_file, obj_type, attrs, insert_line)
                if not result.success:
                    if self._op_logger:
                        self._op_logger.error("service", "move_object", params={"source_file": source_file, "target_file": target_file, "obj_type": obj_type}, error=result.error)  # noqa: PLE1205
                    return result
                # Save old parser for rollback on reload failure
                old_parser = self._parser
                reload_result = self._reload_parser_safe(old_parser, file_path=target_file)
                if not reload_result.success:
                    return reload_result
                if self._op_logger:
                    self._op_logger.info("service", "move_object", params={"source_file": source_file, "target_file": target_file, "obj_type": obj_type}, result="success")  # noqa: PLE1205
                return OperationResult(True)
            except Exception as e:  # noqa: BLE001
                if self._op_logger:
                    self._op_logger.exception("service", "move_object", params={"source_file": source_file, "target_file": target_file, "obj_type": obj_type}, error=str(e))  # noqa: PLE1205
                return OperationResult(False, f"Move failed: {e}")

    # =========================================================================
    # Staging Apply Operations
    # =========================================================================

    def _log_apply_result(self, phase: str, count: int, errors: list) -> None:
        """Log the result of an apply phase."""
        if not self._op_logger:
            return
        if errors:
            self._op_logger.warning("service", phase,  # noqa: PLE1205
                                    params={"count": count, "error_count": len(errors)},
                                    result="partial" if count > 0 else "failed")
        elif count > 0:
            self._op_logger.info("service", phase,  # noqa: PLE1205
                                 params={"count": count}, result="success")
        else:
            self._op_logger.debug("service", phase, params={"count": 0}, result="noop")  # noqa: PLE1205

    def apply_folder_creations(self, staging_data: dict) -> OperationResult:
        """Create staged folders."""
        if self._op_logger:
            self._op_logger.debug("service", "apply_folder_creations", result="started")  # noqa: PLE1205
        folder_creations = staging_data.get("stagedFolderCreations", [])
        folder_creations.sort(key=lambda x: x.get("path", "").count("/"))
        count = 0
        errors = []
        details = []

        for op in folder_creations:
            folder_path = op.get("path")
            if folder_path:
                is_safe, error_msg = self._validate_path_safety(folder_path, "folder")
                if not is_safe:
                    errors.append(error_msg)
                    continue
                try:
                    os.makedirs(folder_path, exist_ok=True)
                    count += 1
                    details.append({"path": folder_path})
                except OSError as e:
                    errors.append(f"Failed to create folder {folder_path}: {e}")

        result = self._build_apply_result("folder_creations", count, errors, details)
        self._log_apply_result("apply_folder_creations", count, errors)
        return OperationResult(True, data=result)

    def _create_staged_file(self, file_path: str) -> tuple[bool, str]:
        """Create a single staged file with header content.

        Returns:
            Tuple of (success, error_message). error_message is empty on success.

        """
        try:
            parent_dir = os.path.dirname(file_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            if not os.path.exists(file_path):
                with open(file_path, "w") as f:
                    f.write(f"# Nagios configuration file: {os.path.basename(file_path)}\n\n")
                return (True, "")
            return (False, "")  # Already exists, not an error but no count
        except OSError as e:
            return (False, f"Failed to create file {file_path}: {e}")

    def _create_new_file(self, file_path: str) -> tuple[bool, str]:
        """Create a new empty file, resolving relative paths.

        Returns:
            Tuple of (success, error_message). error_message is empty on success.

        """
        try:
            parent_dir = os.path.dirname(file_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            if not os.path.exists(file_path):
                Path(file_path).touch()
                return (True, "")
            return (False, "")  # Already exists
        except OSError as e:
            return (False, f"Failed to create file {file_path}: {e}")

    def _apply_staged_file_creations(self, file_creations: list, errors: list) -> int:
        """Process stagedFileCreations entries, returning count of files created."""
        count = 0
        for op in file_creations:
            file_path = op.get("path")
            if not file_path:
                continue
            is_safe, error_msg = self._validate_path_safety(file_path, "file")
            if not is_safe:
                errors.append(error_msg)
                continue
            success, error = self._create_staged_file(file_path)
            if success:
                count += 1
            elif error:
                errors.append(error)
        return count

    def _apply_new_files(self, new_files: list, errors: list) -> int:
        """Process newFiles entries, resolving relative paths. Returns count created."""
        count = 0
        for file_path in new_files:
            if not os.path.isabs(file_path):
                file_path = os.path.join(self._config_path, file_path)
            is_safe, error_msg = self._validate_path_safety(file_path, "file")
            if not is_safe:
                errors.append(error_msg)
                continue
            success, error = self._create_new_file(file_path)
            if success:
                count += 1
            elif error:
                errors.append(error)
        return count

    def apply_file_creations(self, staging_data: dict) -> OperationResult:
        """Create staged files."""
        if self._op_logger:
            self._op_logger.debug("service", "apply_file_creations", result="started")  # noqa: PLE1205
        errors = []
        count = self._apply_staged_file_creations(
            staging_data.get("stagedFileCreations", []), errors,
        )
        count += self._apply_new_files(
            staging_data.get("newFiles", []), errors,
        )
        result = self._build_apply_result("file_creations", count, errors)
        self._log_apply_result("apply_file_creations", count, errors)
        return OperationResult(True, data=result)

    def apply_object_deletions(self, staging_data: dict) -> OperationResult:
        """Delete staged objects."""
        if self._op_logger:
            self._op_logger.debug("service", "apply_object_deletions", result="started")  # noqa: PLE1205
        staged_deletions = staging_data.get("stagedObjectDeletions", [])
        count = 0
        errors = []
        details = []

        if not staged_deletions:
            result = self._build_apply_result("object_deletions", count, errors, details)
            self._log_apply_result("apply_object_deletions", count, errors)
            return OperationResult(True, data=result)

        p = self.parser
        objects_to_delete = []

        for deletion_entry in staged_deletions:
            # Frontend sends Array.from(Set) which produces integer array
            if isinstance(deletion_entry, int) and 0 <= deletion_entry < len(p.objects):
                obj = p.objects[deletion_entry]
                objects_to_delete.append((obj.source_file, obj.line_number, obj.object_type, obj))

        objects_to_delete.sort(key=lambda x: (x[0], -x[1]))
        for source_file, line_number, obj_type, obj in objects_to_delete:
            name_field = NAME_FIELDS.get(obj_type)
            obj_name = obj.attributes.get(name_field, "") if name_field else ""
            result = self.delete_object(source_file, line_number)
            if result.success:
                count += 1
                details.append({
                    "object_type": obj_type,
                    "object_name": obj_name,
                    "file": source_file,
                })
                p = self.parser
            elif result.error:
                errors.append(f"Failed to delete object at {source_file}:{line_number}: {result.error}")

        result = self._build_apply_result("object_deletions", count, errors, details)
        self._log_apply_result("apply_object_deletions", count, errors)
        return OperationResult(True, data=result)

    def _normalize_staged_moves(self, staging_data: dict) -> list[dict]:
        """Normalize staged move entries into a consistent format.

        Args:
            staging_data: Staging data dict containing stagedMoves

        Returns:
            List of normalized move dicts sorted by insertPosition

        """
        staged_moves = staging_data.get("stagedMoves", {})
        move_list = list(staged_moves.values()) if isinstance(staged_moves, dict) else staged_moves
        move_list.sort(key=lambda e: (e.get("insertPosition") or 0) if isinstance(e, dict) else 0)

        moves = []
        for move_data in move_list:
            if not isinstance(move_data, dict):
                continue
            target_file = move_data.get("targetFile")
            obj_info = move_data.get("object", {})
            source_file = obj_info.get("source_file")
            obj_type = obj_info.get("object_type")
            attrs = obj_info.get("attributes", {})
            insert_position = move_data.get("insertPosition")
            if all([target_file, source_file, obj_type, attrs]):
                moves.append({
                    "target_file": target_file,
                    "source_file": source_file,
                    "obj_type": obj_type,
                    "attrs": attrs,
                    "insert_position": insert_position,
                })
        return moves

    def _resolve_insert_position(self, target_file: str, insert_position,
                                  parser_objects: list, exclude_obj=None) -> int | None:
        """Convert virtual insertPosition to actual line number to insert after.

        The frontend uses insertPosition as a virtual ordering value that's compared
        against existing objects' line numbers. This finds the object whose line_number
        is highest but still <= insert_position, and returns that line number.

        Args:
            target_file: Target file path
            insert_position: Virtual position (compared against line numbers) or None
            parser_objects: Current parser objects list
            exclude_obj: Object to exclude (the one being moved, for same-file moves)

        Returns:
            Line number to insert after, or None for end of file, or 0 for beginning

        """
        if insert_position is None:
            return None  # Append to end

        target_real = os.path.realpath(target_file)

        # Get objects in target file, sorted by line number
        target_objects = [o for o in parser_objects
                         if os.path.realpath(o.source_file) == target_real]

        # Exclude the object being moved (for same-file reordering)
        if exclude_obj is not None:
            target_objects = [o for o in target_objects
                             if not (o.line_number == exclude_obj.line_number and
                                    o.object_type == exclude_obj.object_type)]

        target_objects.sort(key=lambda o: o.line_number)

        if not target_objects:
            return None  # Empty file or only contains the moved object

        # Find the object whose line_number is highest but still <= insert_position
        insert_after_obj = None
        for obj in target_objects:
            if obj.line_number <= insert_position:
                insert_after_obj = obj
            else:
                break

        if insert_after_obj is None:
            return 0  # Insert at beginning (before first object)

        return insert_after_obj.line_number

    def _find_object_by_attrs(self, source_file: str, obj_type: str,
                              attrs: dict, objects: list) -> NagiosObject | None:
        """Find an object by source file, type, and full attribute match.

        Attribute matching is required for same-file reordering: line numbers
        shift as objects are moved, making line-number lookup unreliable.

        Args:
            source_file: Source file path (resolved for comparison)
            obj_type: Object type to match
            attrs: Full attribute dict to match
            objects: Parser objects list to search

        Returns:
            Matching NagiosObject or None

        """
        source_real = os.path.realpath(source_file)
        for obj in objects:
            if (os.path.realpath(obj.source_file) == source_real and
                obj.object_type == obj_type and
                obj.attributes == attrs):
                return obj
        return None

    def _determine_insert_line(self, move: dict, target_file_real: str,
                                last_insert_line: dict, target_obj, p) -> int | None:
        """Determine the insert line for a move operation.

        Uses tracked position if we've already inserted to this file,
        otherwise resolves from insertPosition.

        Returns:
            Line number to insert after, or None for end of file

        """
        if target_file_real in last_insert_line:
            return last_insert_line[target_file_real]
        return self._resolve_insert_position(
            move["target_file"], move["insert_position"],
            p.objects, exclude_obj=target_obj,
        )

    def _track_inserted_position(self, move: dict, target_file_real: str,
                                  last_insert_line: dict) -> None:
        """Track where an object was inserted for subsequent moves.

        Reloads parser and finds the moved object to get its new line number.
        """
        self._parser = NagiosConfigParser(self._config_path)
        self._parser.parse_all()
        found = self._find_object_by_attrs(
            move["target_file"], move["obj_type"], move["attrs"], self._parser.objects,
        )
        if found:
            last_insert_line[target_file_real] = found.line_number

    def apply_object_moves(self, staging_data: dict) -> OperationResult:
        """Move staged objects using surgical file operations.

        Uses move_object_between_files() for each move, which preserves
        comments and formatting in both source and target files.
        """
        if self._op_logger:
            self._op_logger.debug("service", "apply_object_moves", result="started")  # noqa: PLE1205
        count = 0
        errors = []
        details = []

        staged_moves = staging_data.get("stagedMoves", {})
        if not staged_moves:
            self._log_apply_result("apply_object_moves", count, errors)
            return OperationResult(True, data={"count": count, "errors": errors, "details": details})

        moves = self._normalize_staged_moves(staging_data)
        if not moves:
            self._log_apply_result("apply_object_moves", count, errors)
            return OperationResult(True, data={"count": count, "errors": errors, "details": details})

        last_insert_line = {}

        for move in moves:
            self._parser = NagiosConfigParser(self._config_path)
            self._parser.parse_all()
            p = self.parser

            target_obj = self._find_object_by_attrs(
                move["source_file"], move["obj_type"], move["attrs"], p.objects,
            )
            if not target_obj:
                errors.append(f"Could not find object to move: {move['obj_type']} in {move['source_file']}")
                continue

            target_file_real = os.path.realpath(move["target_file"])
            insert_line = self._determine_insert_line(move, target_file_real, last_insert_line, target_obj, p)

            result = move_object_between_files(
                target_obj.source_file, target_obj.line_number,
                move["target_file"], move["obj_type"], move["attrs"], insert_line,
            )

            if result.success:
                count += 1
                name_field = NAME_FIELDS.get(move["obj_type"])
                obj_name = move["attrs"].get(name_field, "") if name_field else ""
                details.append({
                    "object_type": move["obj_type"], "object_name": obj_name,
                    "from_file": move["source_file"], "to_file": move["target_file"],
                })
                self._track_inserted_position(move, target_file_real, last_insert_line)
            else:
                errors.append(f"Move failed: {result.error}")

        # Final parser reload
        self._parser = NagiosConfigParser(self._config_path)
        self._parser.parse_all()

        result = self._build_apply_result("object_moves", count, errors, details)
        self._log_apply_result("apply_object_moves", count, errors)
        return OperationResult(True, data=result)

    def _build_edit_detail(self, target_obj, old_attrs: dict, edited_attrs: dict) -> dict:
        """Build detail entry for an applied edit, tracking individual attribute changes.

        Args:
            target_obj: The NagiosObject being edited
            old_attrs: Original attributes before edit
            edited_attrs: Only the changed attributes

        Returns:
            Detail dict with object_type, object_name, changes, and optional renamed_to

        """
        changes = []
        for key, new_val in edited_attrs.items():
            old_val = old_attrs.get(key)
            if old_val is None:
                changes.append({"type": "add", "key": key, "value": new_val})
            elif old_val != new_val:
                changes.append({"type": "modify", "key": key, "from": old_val, "to": new_val})

        name_field = NAME_FIELDS.get(target_obj.object_type)
        obj_name = old_attrs.get(name_field, "") if name_field else ""
        detail_entry = {
            "object_type": target_obj.object_type,
            "object_name": obj_name,
            "changes": changes,
        }
        if name_field and name_field in edited_attrs:
            new_name = edited_attrs.get(name_field)
            if new_name and new_name != obj_name:
                detail_entry["renamed_to"] = new_name
        return detail_entry

    def apply_object_edits(self, staging_data: dict) -> OperationResult:
        """Edit staged objects."""
        if self._op_logger:
            self._op_logger.debug("service", "apply_object_edits", result="started")  # noqa: PLE1205
        pending_edits = staging_data.get("pendingEdits", {})
        count = 0
        errors = []
        details = []

        if not pending_edits:
            result = self._build_apply_result("object_edits", count, errors, details)
            self._log_apply_result("apply_object_edits", count, errors)
            return OperationResult(True, data=result)

        # pendingEdits is a dict {globalIndex: entry}
        for gi_str, entry in pending_edits.items():
            if not isinstance(entry, dict):
                continue
            if "globalIndex" not in entry:
                entry["globalIndex"] = gi_str

            edited_attrs = entry.get("edited", {})
            if not edited_attrs:
                continue

            target_obj = self._find_object_by_entry(entry, "edit")
            if not target_obj:
                continue

            old_attrs = dict(target_obj.attributes)
            merged_attrs = dict(target_obj.attributes)
            merged_attrs.update(edited_attrs)
            result = self.update_object(target_obj.source_file, target_obj.line_number,
                                        merged_attrs, target_obj.object_type,
                                        inline_comments=target_obj.inline_comments)
            if result.success:
                count += 1
                details.append(self._build_edit_detail(target_obj, old_attrs, edited_attrs))
            elif result.error:
                errors.append(f"Failed to edit object: {result.error}")

        result = self._build_apply_result("object_edits", count, errors, details)
        self._log_apply_result("apply_object_edits", count, errors)
        return OperationResult(True, data=result)

    def apply_object_creations(self, staging_data: dict) -> OperationResult:
        """Create staged objects."""
        if self._op_logger:
            self._op_logger.debug("service", "apply_object_creations", result="started")  # noqa: PLE1205
        staged_creations = staging_data.get("stagedCreations", [])
        count = 0
        errors = []
        details = []

        if not staged_creations:
            result = self._build_apply_result("object_creations", count, errors, details)
            self._log_apply_result("apply_object_creations", count, errors)
            return OperationResult(True, data=result)

        for creation in staged_creations:
            object_type = creation.get("object_type")
            attributes = creation.get("attributes", {})
            target_file = creation.get("targetFile")

            if object_type and target_file:
                if not os.path.isabs(target_file):
                    target_file = os.path.join(self._config_path, target_file)

                result = self.create_object(target_file, object_type, attributes)
                if result.success:
                    count += 1
                    name_field = NAME_FIELDS.get(object_type)
                    obj_name = attributes.get(name_field, "") if name_field else ""
                    details.append({
                        "object_type": object_type,
                        "object_name": obj_name,
                        "file": target_file,
                    })
                elif result.error:
                    errors.append(f"Failed to create object: {result.error}")

        result = self._build_apply_result("object_creations", count, errors, details)
        self._log_apply_result("apply_object_creations", count, errors)
        return OperationResult(True, data=result)

    def apply_file_moves(self, staging_data: dict) -> OperationResult:
        """Move staged files."""
        if self._op_logger:
            self._op_logger.debug("service", "apply_file_moves", result="started")  # noqa: PLE1205
        file_moves = staging_data.get("stagedFileMoves", [])
        count = 0
        errors = []
        details = []

        for op in file_moves:
            source_path = op.get("sourcePath")
            target_path = op.get("targetPath")
            if source_path and target_path:
                is_safe_src, error_src = self._validate_path_safety(source_path, "file")
                is_safe_tgt, error_tgt = self._validate_path_safety(target_path, "file")
                if not is_safe_src:
                    errors.append(error_src)
                    continue
                if not is_safe_tgt:
                    errors.append(error_tgt)
                    continue
                try:
                    target_dir = os.path.dirname(target_path)
                    if target_dir:
                        os.makedirs(target_dir, exist_ok=True)
                    if os.path.exists(source_path):
                        shutil.move(source_path, target_path)
                        count += 1
                        details.append({"from": source_path, "to": target_path})
                except OSError as e:
                    errors.append(f"Failed to move file {source_path}: {e}")

        result = self._build_apply_result("file_moves", count, errors, details)
        self._log_apply_result("apply_file_moves", count, errors)
        return OperationResult(True, data=result)

    def apply_folder_moves(self, staging_data: dict) -> OperationResult:
        """Move staged folders."""
        if self._op_logger:
            self._op_logger.debug("service", "apply_folder_moves", result="started")  # noqa: PLE1205
        folder_moves = staging_data.get("stagedFolderMoves", [])
        count = 0
        errors = []
        details = []

        for op in folder_moves:
            source_path = op.get("sourcePath")
            target_path = op.get("targetPath")
            if source_path and target_path:
                is_safe_src, error_src = self._validate_path_safety(source_path, "folder")
                is_safe_tgt, error_tgt = self._validate_path_safety(target_path, "folder")
                if not is_safe_src:
                    errors.append(error_src)
                    continue
                if not is_safe_tgt:
                    errors.append(error_tgt)
                    continue
                try:
                    target_parent = os.path.dirname(target_path)
                    if target_parent:
                        os.makedirs(target_parent, exist_ok=True)
                    if os.path.isdir(source_path):
                        shutil.move(source_path, target_path)
                        count += 1
                        details.append({"from": source_path, "to": target_path})
                except OSError as e:
                    errors.append(f"Failed to move folder {source_path}: {e}")

        result = self._build_apply_result("folder_moves", count, errors, details)
        self._log_apply_result("apply_folder_moves", count, errors)
        return OperationResult(True, data=result)

    def apply_file_deletions(self, staging_data: dict) -> OperationResult:
        """Delete staged files."""
        if self._op_logger:
            self._op_logger.debug("service", "apply_file_deletions", result="started")  # noqa: PLE1205
        file_deletions = staging_data.get("stagedFileDeletions", [])
        count = 0
        errors = []
        details = []

        for op in file_deletions:
            file_path = op.get("path")
            if file_path and os.path.isfile(file_path):
                is_safe, error_msg = self._validate_path_safety(file_path, "file")
                if not is_safe:
                    errors.append(error_msg)
                    continue
                try:
                    os.remove(file_path)
                    count += 1
                    details.append({"path": file_path, "type": "file"})
                except OSError as e:
                    errors.append(f"Failed to delete file {file_path}: {e}")

        result = self._build_apply_result("file_deletions", count, errors, details)
        self._log_apply_result("apply_file_deletions", count, errors)
        return OperationResult(True, data=result)

    def apply_folder_deletions(self, staging_data: dict) -> OperationResult:
        """Delete staged folders."""
        if self._op_logger:
            self._op_logger.debug("service", "apply_folder_deletions", result="started")  # noqa: PLE1205
        folder_deletions = staging_data.get("stagedFolderDeletions", [])
        folder_deletions.sort(key=lambda x: -x.get("path", "").count("/"))
        count = 0
        errors = []
        details = []

        for op in folder_deletions:
            folder_path = op.get("path")
            if folder_path and os.path.isdir(folder_path):
                is_safe, error_msg = self._validate_path_safety(folder_path, "folder")
                if not is_safe:
                    errors.append(error_msg)
                    continue
                try:
                    shutil.rmtree(folder_path)
                    count += 1
                    details.append({"path": folder_path, "type": "folder"})
                except OSError as e:
                    errors.append(f"Failed to delete folder {folder_path}: {e}")

        result = self._build_apply_result("folder_deletions", count, errors, details)
        self._log_apply_result("apply_folder_deletions", count, errors)
        return OperationResult(True, data=result)
