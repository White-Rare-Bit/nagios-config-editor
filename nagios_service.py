"""Nagios Service Layer

Provides business logic and unified CRUD operations with automatic parser reload.
Eliminates temporal coupling: callers no longer need to remember to call reload_config().
"""

import logging
import multiprocessing
import os
import re
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
from stable_keys import parse_stable_key

logger = logging.getLogger(__name__)


class NagiosService:
    """Service layer for Nagios configuration management.

    Wraps the parser and file operations, providing a unified interface
    with automatic state synchronization (reload after write).
    """

    def __init__(self, config_path=None, *, cfg_dirs=None, cfg_files=None):
        if config_path is not None:
            self._cfg_dirs = [config_path]
            self._cfg_files = []
        else:
            self._cfg_dirs = list(cfg_dirs or [])
            self._cfg_files = list(cfg_files or [])
        self._parser: NagiosConfigParser | None = None
        self._lock = multiprocessing.Lock()
        # Flag to indicate parser state is inconsistent with disk state.
        # When True, all CRUD operations are blocked until explicit reload succeeds.
        self._parser_corrupted = False

    @property
    def config_path(self) -> str:
        """First cfg_dir for backward compat. Returns empty string if none."""
        if self._cfg_dirs:
            return str(Path(self._cfg_dirs[0]).resolve())
        return ""

    @config_path.setter
    def config_path(self, path: str) -> None:
        """Set single config path (backward compat, replaces all dirs)."""
        with self._lock:
            self._cfg_dirs = [path]
            self._cfg_files = []
            self._parser = None

    @property
    def cfg_dirs(self) -> list[str]:
        return list(self._cfg_dirs)

    @property
    def cfg_files(self) -> list[str]:
        return list(self._cfg_files)

    def set_roots(self, cfg_dirs, cfg_files):
        """Update config roots and clear parser cache."""
        with self._lock:
            self._cfg_dirs = list(cfg_dirs)
            self._cfg_files = list(cfg_files)
            self._parser = None

    @property
    def parser(self) -> NagiosConfigParser:
        """Get or create the parser (thread-safe)."""
        with self._lock:
            if self._parser is None:
                self._parser = NagiosConfigParser(
                    cfg_dirs=self._cfg_dirs,
                    cfg_files=self._cfg_files,
                )
                self._parser.parse_all()
            return self._parser

    def reload(self) -> NagiosConfigParser:
        """Force reload of configuration (thread-safe).

        Also clears the _parser_corrupted flag on success, allowing
        CRUD operations to resume after a reload.
        """
        with self._lock:
            self._parser = NagiosConfigParser(
                cfg_dirs=self._cfg_dirs,
                cfg_files=self._cfg_files,
            )
            self._parser.parse_all()
            self._parser_corrupted = False
            logger.debug("Parser reload: cfg_dirs=%s", self._cfg_dirs)
            return self._parser

    def _validate_path_safety(
        self, path: str, path_type: str
    ) -> tuple[bool, str | None]:
        """Path validation wrapper preventing path traversal attacks.

        Args:
            path: Path to validate
            path_type: Type of path ("file" or "folder") for error messages

        Returns:
            Tuple of (is_safe, error_message). error_message is None if safe.

        """
        safe_result = is_safe_path(path, self.config_path)
        if not safe_result.success:
            return (False, f"Unsafe {path_type} path {path}: {safe_result.error}")
        return (True, None)

    def _find_by_identity(
        self, source_file: str, obj_type: str, obj_name: str
    ) -> NagiosObject | None:
        """Find object by stable identity: source_file + type + name."""
        source_real = os.path.realpath(source_file)
        name_field = NAME_FIELDS.get(obj_type)
        for obj in self.parser.objects:
            if (
                os.path.realpath(obj.source_file) == source_real
                and obj.object_type == obj_type
            ):
                if name_field and obj.attributes.get(name_field) == obj_name:
                    return obj
                if not name_field and obj.get_name() == obj_name:
                    return obj
        return None

    def _find_by_attrs(
        self, source_file: str, obj_type: str, attrs: dict
    ) -> NagiosObject | None:
        """Find object by exact attribute match (for moves)."""
        source_real = os.path.realpath(source_file)
        for obj in self.parser.objects:
            if (
                os.path.realpath(obj.source_file) == source_real
                and obj.object_type == obj_type
                and obj.attributes == attrs
            ):
                return obj
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
                self._parser = NagiosConfigParser(
                    cfg_dirs=self._cfg_dirs,
                    cfg_files=self._cfg_files,
                )
                self._parser.parse_all()
            yield self._parser

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

    # =========================================================================
    # Domain Logic (moved from app.py)
    # =========================================================================

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

    def transform_name(
        self,
        name: str,
        find_pattern: str = "",
        replace_with: str = "",
        prefix: str = "",
        suffix: str = "",
        use_regex: bool = False,
    ) -> str | None:
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

    def update_references(
        self, objects: list[NagiosObject], old_name: str, new_name: str
    ) -> int:
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

    def _reload_parser_safe(
        self, old_parser: NagiosConfigParser | None, file_path: str = None
    ) -> OperationResult:
        """Safely reload parser, setting corrupted flag on failure.

        Args:
            old_parser: Previous parser instance to restore on failure
            file_path: Optional path of file that was modified (for error message)

        Returns:
            OperationResult with success status. On failure, _parser_corrupted flag is set
            to block subsequent operations until explicit reload succeeds.

        """
        try:
            new_parser = NagiosConfigParser(
                cfg_dirs=self._cfg_dirs,
                cfg_files=self._cfg_files,
            )
            new_parser.parse_all()
            self._parser = new_parser
            self._parser_corrupted = False
            return OperationResult(True)
        except Exception as e:  # noqa: BLE001
            # Set corrupted flag to block subsequent operations
            self._parser_corrupted = True
            # Restore old parser for read operations (queries still work)
            self._parser = old_parser
            file_info = (
                f" File {file_path} was modified but"
                if file_path
                else " File was modified but"
            )
            error_msg = (
                f"CRITICAL:{file_info} parser state is inconsistent. "
                f"All operations are blocked. Run POST /api/reload to resync parser. "
                f"If reload fails, manual inspection of config files required. "
                f"Original error: {e}"
            )
            logger.exception(
                "Parser reload failed: file_path=%s corrupted=True", file_path
            )
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

    def create_object(
        self,
        target_file: str,
        obj_type: str,
        attrs: dict[str, str],
        after_block_line: int | None = None,
        inline_comments: dict | None = None,
    ) -> OperationResult:
        """Create a new object in a file.

        Args:
            target_file: Path to the target config file
            obj_type: Object type (host, service, etc.)
            attrs: Attribute key-value pairs
            after_block_line: Line number to insert after (None = end)
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
                result = add_object_to_file(
                    target_file,
                    obj_type,
                    attrs,
                    after_block_line,
                    inline_comments=inline_comments,
                )
                if not result.success:
                    logger.error(
                        "create_object failed: target_file=%s obj_type=%s error=%s",
                        target_file,
                        obj_type,
                        result.error,
                    )
                    return result
                # Save old parser for rollback on reload failure
                old_parser = self._parser
                reload_result = self._reload_parser_safe(
                    old_parser, file_path=target_file
                )
                if not reload_result.success:
                    return reload_result
                logger.info(
                    "create_object: target_file=%s obj_type=%s result=success",
                    target_file,
                    obj_type,
                )
                return OperationResult(True)
            except Exception as e:  # noqa: BLE001
                logger.exception(
                    "create_object failed: target_file=%s obj_type=%s",
                    target_file,
                    obj_type,
                )
                return OperationResult(False, f"Create failed: {e}")

    def update_object(
        self,
        source_file: str,
        line_number: int,
        new_attrs: dict[str, str],
        obj_type: str,
        inline_comments: dict | None = None,
    ) -> OperationResult:
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
                    source_file,
                    line_number,
                    new_attrs,
                    obj_type,
                    inline_comments=inline_comments,
                )
                if not result.success:
                    logger.error(
                        "update_object failed: source_file=%s line_number=%s obj_type=%s error=%s",
                        source_file,
                        line_number,
                        obj_type,
                        result.error,
                    )
                    return result
                # Save old parser for rollback on reload failure
                old_parser = self._parser
                reload_result = self._reload_parser_safe(
                    old_parser, file_path=source_file
                )
                if not reload_result.success:
                    return reload_result
                logger.info(
                    "update_object: source_file=%s line_number=%s obj_type=%s result=success",
                    source_file,
                    line_number,
                    obj_type,
                )
                return OperationResult(True)
            except Exception as e:  # noqa: BLE001
                logger.exception(
                    "update_object failed: source_file=%s line_number=%s obj_type=%s",
                    source_file,
                    line_number,
                    obj_type,
                )
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
                    logger.error(
                        "delete_object failed: source_file=%s line_number=%s error=%s",
                        source_file,
                        line_number,
                        result.error,
                    )
                    return result
                # Save old parser for rollback on reload failure
                old_parser = self._parser
                reload_result = self._reload_parser_safe(
                    old_parser, file_path=source_file
                )
                if not reload_result.success:
                    return reload_result
                logger.info(
                    "delete_object: source_file=%s line_number=%s result=success",
                    source_file,
                    line_number,
                )
                return OperationResult(True)
            except Exception as e:  # noqa: BLE001
                logger.exception(
                    "delete_object failed: source_file=%s line_number=%s",
                    source_file,
                    line_number,
                )
                return OperationResult(False, f"Delete failed: {e}")

    def move_object(
        self,
        source_file: str,
        source_line: int,
        target_file: str,
        obj_type: str,
        attrs: dict[str, str],
        insert_line: int | None = None,
    ) -> OperationResult:
        """Move an object from one file to another (or reorder within same file).

        Args:
            source_file: Path to the file containing the object
            source_line: Line number where object starts
            target_file: Path to the destination file
            obj_type: Object type (for formatting fallback)
            attrs: Object attributes (for formatting fallback)
            insert_line: Line number to insert after in target (None = end)

        Returns:
            OperationResult with success status

        """
        with self._lock:
            corrupted_error = self._check_parser_state()
            if corrupted_error:
                return corrupted_error

            try:
                result = move_object_between_files(
                    source_file, source_line, target_file,
                    obj_type, attrs, insert_line,
                )
                if not result.success:
                    logger.error(
                        "move_object failed: %s:%s -> %s error=%s",
                        source_file, source_line, target_file, result.error,
                    )
                    return result
                old_parser = self._parser
                reload_result = self._reload_parser_safe(
                    old_parser, file_path=source_file,
                )
                if not reload_result.success:
                    return reload_result
                logger.info(
                    "move_object: %s:%s -> %s result=success",
                    source_file, source_line, target_file,
                )
                return OperationResult(True)
            except Exception as e:  # noqa: BLE001
                logger.exception(
                    "move_object failed: %s:%s -> %s",
                    source_file, source_line, target_file,
                )
                return OperationResult(False, f"Move failed: {e}")
