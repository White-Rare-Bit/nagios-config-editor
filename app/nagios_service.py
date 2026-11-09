"""Nagios Service Layer

Provides business logic and unified CRUD operations with automatic parser reload.
Eliminates temporal coupling: callers no longer need to remember to call reload_config().

Which files the service reads and writes is decided per call from what is on
disk, never from a flag in memory: while a shadow copy exists the service
works on it, otherwise on the original config. Callers always pass and
receive *logical* paths (original config locations); see shadow_copy_manager.
"""

import logging
import os
import re
from contextlib import contextmanager
from pathlib import Path
from .file_operations import (
    add_object_to_file,
    delete_object_from_file,
    edit_object_in_file,
    is_safe_path,
    move_object_between_files,
)
from .nagios_model import NAME_FIELDS, NagiosObject, OperationResult
from .nagios_parser import NagiosConfigParser
from .process_lock import ProcessLock
from .stable_keys import parse_stable_key

logger = logging.getLogger(__name__)

_NOT_STAGED_ERROR = (
    "No staging session is active. Changes must go through the shadow copy, "
    "never directly to the live configuration."
)


class NagiosService:
    """Service layer for Nagios configuration management.

    Wraps the parser and file operations, providing a unified interface
    with automatic state synchronization (reload after write).

    Args:
        config_path: Single config directory (shorthand for cfg_dirs=[...]).
        cfg_dirs: Config root directories.
        cfg_files: Individual config files outside the roots (read-only:
            they are not part of the shadow copy and are not listed while
            staging is active).
        shadow_manager: When given, the service is staging-aware: it reads
            the shadow copy whenever one exists, refuses to write outside
            one, and notices changes made by other worker processes. Without
            it the service reads and writes the given directories directly
            (unit tests, scripts).
    """

    def __init__(self, config_path=None, *, cfg_dirs=None, cfg_files=None, shadow_manager=None):
        if config_path is not None:
            self._cfg_dirs = [config_path]
            self._cfg_files = []
        else:
            self._cfg_dirs = list(cfg_dirs or [])
            self._cfg_files = list(cfg_files or [])
        self._shadow = shadow_manager
        self._parser: NagiosConfigParser | None = None
        # Generation the cached parser was built at (see _current_token).
        self._parser_token: str | None = None
        # A file lock when workers share a shadow manager, so writes and
        # parses exclude other worker processes too.
        self._lock = ProcessLock(shadow_manager.lock_file("service") if shadow_manager else None)
        # Flag to indicate parser state is inconsistent with disk state.
        # When True, all CRUD operations are blocked until explicit reload succeeds.
        self._parser_corrupted = False

    @property
    def config_path(self) -> str:
        """First config root (logical). Returns empty string if none."""
        if self._cfg_dirs:
            return str(Path(self._cfg_dirs[0]).resolve())
        return ""

    @property
    def cfg_dirs(self) -> list[str]:
        """Config roots as logical paths (the original directories)."""
        return list(self._cfg_dirs)

    @property
    def cfg_files(self) -> list[str]:
        return list(self._cfg_files)

    # =========================================================================
    # Staging awareness
    # =========================================================================

    def staging_active(self) -> bool:
        """True while a shadow copy exists (checked on disk every time)."""
        return self._shadow is not None and self._shadow.has_shadow()

    @property
    def active_dirs(self) -> list[tuple[str, str]]:
        """(physical_dir, logical_dir) for each root: where to read it now, and its name."""
        shadow = self._shadow
        if shadow is not None and shadow.has_shadow():
            return [(physical, logical) for _name, physical, logical
                    in shadow.ordered_root_pairs()]
        return [(d, d) for d in self._cfg_dirs]

    def physical_path(self, path: str) -> str | None:
        """Where a logical path must be read or written right now.

        Returns None when the path may not be written: staging is required
        but not active, or the path is outside every config root.
        """
        if self._shadow is None:
            return path
        if not self._shadow.has_shadow():
            return None
        return self._shadow.physical_path(path)

    def _unwritable(self, path: str) -> OperationResult:
        """Explain why physical_path() returned None for a path."""
        if self._shadow is not None and not self._shadow.has_shadow():
            return OperationResult(False, _NOT_STAGED_ERROR)
        return OperationResult(
            False, f"Path is outside the configuration directories: {path}",
        )

    def _current_token(self) -> str:
        return self._shadow.generation() if self._shadow is not None else ""

    def _mark_changed(self) -> None:
        """Tell every worker (including this one) that the config changed."""
        if self._shadow is not None:
            self._shadow.bump_generation()

    def _build_parser(self) -> NagiosConfigParser:
        """Parse whatever is current on disk; objects get logical source_file paths."""
        shadow = self._shadow
        if shadow is not None and shadow.has_shadow():
            pairs = shadow.ordered_root_pairs()
            parser = NagiosConfigParser(
                cfg_dirs=[physical for _name, physical, _logical in pairs],
            )
            parser.parse_all()
            self._relabel_logical(parser, pairs)
            return parser
        parser = NagiosConfigParser(cfg_dirs=self._cfg_dirs, cfg_files=self._cfg_files)
        parser.parse_all()
        return parser

    @staticmethod
    def _relabel_logical(parser: NagiosConfigParser, pairs) -> None:
        """Rewrite shadow paths on parsed objects to their logical paths."""
        prefixes = [(physical + os.sep, logical + os.sep) for _name, physical, logical in pairs]

        def to_logical(path: str) -> str:
            for physical_prefix, logical_prefix in prefixes:
                if path.startswith(physical_prefix):
                    return logical_prefix + path[len(physical_prefix):]
            return path

        for obj in parser.objects:
            obj.source_file = to_logical(obj.source_file)
        parser.files_parsed = [to_logical(f) for f in parser.files_parsed]

    def _ensure_parser(self) -> NagiosConfigParser:
        """Return an up-to-date parser. Caller holds self._lock."""
        # Read the token before parsing: if another worker changes things
        # mid-parse the stored token is already old and the next call reparses.
        token = self._current_token()
        if self._parser is None or token != self._parser_token:
            self._parser = self._build_parser()
            self._parser_token = token
        return self._parser

    @property
    def parser(self) -> NagiosConfigParser:
        """Get the parser, rebuilding it if the config changed on disk (thread-safe)."""
        with self._lock:
            return self._ensure_parser()

    def reload(self) -> NagiosConfigParser:
        """Force reload of configuration (thread-safe).

        Also clears the _parser_corrupted flag on success, allowing
        CRUD operations to resume after a reload, and invalidates the
        cached parser of every other worker.
        """
        with self._lock:
            self._mark_changed()
            token = self._current_token()
            self._parser = self._build_parser()
            self._parser_token = token
            self._parser_corrupted = False
            logger.debug("Parser reload: cfg_dirs=%s staging=%s", self._cfg_dirs, self.staging_active())
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
            yield self._ensure_parser()

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
        # The file is already written, so other workers must reparse even if
        # our own reparse below fails.
        self._mark_changed()
        try:
            token = self._current_token()
            self._parser = self._build_parser()
            self._parser_token = token
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
            target_file: Logical path of the target config file
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

            physical_file = self.physical_path(target_file)
            if physical_file is None:
                return self._unwritable(target_file)

            try:
                result = add_object_to_file(
                    physical_file,
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
            source_file: Logical path of the config file
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

            physical_file = self.physical_path(source_file)
            if physical_file is None:
                return self._unwritable(source_file)

            try:
                result = edit_object_in_file(
                    physical_file,
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
            source_file: Logical path of the config file
            line_number: Line number where object starts

        Returns:
            OperationResult with success status

        """
        with self._lock:
            # Check if parser state is corrupted
            corrupted_error = self._check_parser_state()
            if corrupted_error:
                return corrupted_error

            physical_file = self.physical_path(source_file)
            if physical_file is None:
                return self._unwritable(source_file)

            try:
                result = delete_object_from_file(physical_file, line_number)
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

            physical_source = self.physical_path(source_file)
            if physical_source is None:
                return self._unwritable(source_file)
            physical_target = self.physical_path(target_file)
            if physical_target is None:
                return self._unwritable(target_file)

            try:
                result = move_object_between_files(
                    physical_source, source_line, physical_target,
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
