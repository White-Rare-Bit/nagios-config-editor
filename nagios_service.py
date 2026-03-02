"""Nagios Service Layer

Provides business logic and unified CRUD operations with automatic parser reload.
Eliminates temporal coupling: callers no longer need to remember to call reload_config().
"""

import logging
import multiprocessing
import os
import re
import shutil
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from file_operations import (
    _atomic_write,
    _find_matching_brace,
    add_object_to_file,
    assemble_file_from_blocks,
    delete_object_from_file,
    edit_object_in_file,
    extract_all_blocks,
    find_block_range,
    is_safe_path,
    move_object_between_files,
)
from nagios_model import NAME_FIELDS, NagiosObject, OperationResult, get_object_name
from nagios_parser import NagiosConfigParser
from staging_manager import (
    StagingManager,
    StagingState,
    parse_stable_key,
)

logger = logging.getLogger(__name__)


@dataclass
class CompositeAction:
    """A merged per-entity action for the apply phase.

    Collapses separate staging operations (edit, move, delete, create) on the
    same object into a single composite action. This eliminates phase-ordering
    bugs where the same object appears in multiple phases.
    """

    action_type: str  # "delete" | "edit" | "move" | "move_edit" | "create"
    stable_key: str  # "source_file|object_type|name"
    object_type: str
    object_name: str
    source_file: str | None = None
    original_attrs: dict | None = None
    final_attrs: dict | None = None
    target_file: str | None = None
    insert_position: float | None = None
    inline_comments: dict | None = None
    global_index: int | None = None


class NagiosService:
    """Service layer for Nagios configuration management.

    Wraps the parser and file operations, providing a unified interface
    with automatic state synchronization (reload after write).
    """

    def __init__(self, config_path: str, staging_manager: StagingManager | None = None):
        self._config_path = config_path
        self._parser: NagiosConfigParser | None = None
        self._lock = multiprocessing.Lock()
        self._staging_manager = staging_manager
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
            logger.debug("Parser reload: config_path=%s", self._config_path)
            return self._parser

    def _validate_path_safety(
        self, path: str, path_type: str
    ) -> tuple[bool, str | None]:
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

    def _build_apply_result(
        self, operation: str, count: int, errors: list, details: list = None
    ) -> dict:
        """Construct result dict with consistent structure for apply operations.

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

    def _resolve_on_disk_attrs(
        self, source_file: str, obj_type: str, obj_name: str
    ) -> dict | None:
        """Look up the on-disk attributes for an object by identity.

        Args:
            source_file: Source file path
            obj_type: Object type
            obj_name: Object name

        Returns:
            Attribute dict from parser, or None if not found.

        """
        source_real = os.path.realpath(source_file)
        name_field = NAME_FIELDS.get(obj_type)
        for obj in self.parser.objects:
            if (
                os.path.realpath(obj.source_file) == source_real
                and obj.object_type == obj_type
            ):
                if name_field and obj.attributes.get(name_field) == obj_name:
                    return dict(obj.attributes)
                if not name_field and obj.get_name() == obj_name:
                    return dict(obj.attributes)
        return None

    def _build_composite_actions(self, staging_data: dict) -> list[CompositeAction]:
        """Merge staging operations into per-entity composite actions.

        Indexes pendingEdits, stagedMoves, stagedObjectDeletions, and
        stagedCreations by stable key, then merges overlapping operations
        into a single CompositeAction per entity.

        Args:
            staging_data: Full staging data dict from staging manager.

        Returns:
            List of CompositeAction sorted: deletes first, then moves/edits, then creates.

        """
        p = self.parser
        edits_by_key = {}
        moves_by_key = {}
        deletes_by_key = {}

        # Index pendingEdits by normalized stable key
        for stable_key, entry in staging_data.get("pendingEdits", {}).items():
            if not isinstance(entry, dict):
                continue
            parsed = parse_stable_key(stable_key)
            if parsed:
                norm_key = f"{os.path.realpath(parsed['source_file'])}|{parsed['object_type']}|{parsed['name']}"
                edits_by_key[norm_key] = {"entry": entry}

        # Index stagedMoves by stable key (normalize path portion)
        for key, move_entry in staging_data.get("stagedMoves", {}).items():
            if isinstance(move_entry, dict):
                parsed_key = parse_stable_key(key)
                if parsed_key:
                    norm_key = f"{os.path.realpath(parsed_key['source_file'])}|{parsed_key['object_type']}|{parsed_key['name']}"
                else:
                    norm_key = key
                moves_by_key[norm_key] = move_entry

        # Index stagedObjectDeletions by normalized stable key
        for deletion_key in staging_data.get("stagedObjectDeletions", []):
            if not isinstance(deletion_key, str):
                continue
            parsed = parse_stable_key(deletion_key)
            if not parsed:
                continue
            norm_key = f"{os.path.realpath(parsed['source_file'])}|{parsed['object_type']}|{parsed['name']}"
            deletes_by_key[norm_key] = {}

        # Collect creation actions (no merging needed)
        create_actions = []
        for creation in staging_data.get("stagedCreations", []):
            obj_type = creation.get("object_type")
            attrs = creation.get("attributes", {})
            target_file = creation.get("targetFile")
            if not (obj_type and target_file):
                continue
            name_field = NAME_FIELDS.get(obj_type)
            obj_name = attrs.get(name_field, "") if name_field else ""
            if not os.path.isabs(target_file):
                target_file = os.path.join(self._config_path, target_file)
            create_actions.append(
                CompositeAction(
                    action_type="create",
                    stable_key=f"{target_file}|{obj_type}|{obj_name}",
                    object_type=obj_type,
                    object_name=obj_name,
                    target_file=target_file,
                    final_attrs=attrs,
                    inline_comments=creation.get("inline_comments"),
                )
            )

        # Merge edits, moves, deletes by stable key
        all_keys = set(edits_by_key) | set(moves_by_key) | set(deletes_by_key)
        delete_actions = []
        modify_actions = []

        for key in all_keys:
            has_edit = key in edits_by_key
            has_move = key in moves_by_key
            has_delete = key in deletes_by_key
            parsed = parse_stable_key(key)
            if not parsed:
                continue
            obj_type = parsed["object_type"]
            obj_name = parsed["name"]
            source_file = parsed["source_file"]

            if has_delete:
                delete_actions.append(
                    CompositeAction(
                        action_type="delete",
                        stable_key=key,
                        object_type=obj_type,
                        object_name=obj_name,
                        source_file=source_file,
                    )
                )

            elif has_edit and has_move:
                edit_info = edits_by_key[key]
                move_info = moves_by_key[key]
                original_attrs = edit_info["entry"].get("original", {})
                final_attrs = edit_info["entry"].get("edited", {})
                target_file = move_info.get("targetFile")
                insert_position = move_info.get("insertPosition")
                modify_actions.append(
                    CompositeAction(
                        action_type="move_edit",
                        stable_key=key,
                        object_type=obj_type,
                        object_name=obj_name,
                        source_file=source_file,
                        original_attrs=original_attrs,
                        final_attrs=final_attrs,
                        target_file=target_file,
                        insert_position=insert_position,
                    )
                )

            elif has_move:
                move_info = moves_by_key[key]
                target_file = move_info.get("targetFile")
                insert_position = move_info.get("insertPosition")
                # Resolve original attrs from parser (on-disk truth)
                original_attrs = self._resolve_on_disk_attrs(
                    source_file, obj_type, obj_name
                )
                if original_attrs is None:
                    # Fallback to snapshot
                    obj_meta = move_info.get("object", {})
                    original_attrs = obj_meta.get("attributes", {})
                modify_actions.append(
                    CompositeAction(
                        action_type="move",
                        stable_key=key,
                        object_type=obj_type,
                        object_name=obj_name,
                        source_file=source_file,
                        original_attrs=original_attrs,
                        target_file=target_file,
                        insert_position=insert_position,
                    )
                )

            elif has_edit:
                edit_info = edits_by_key[key]
                final_attrs = edit_info["entry"].get("edited", {})
                modify_actions.append(
                    CompositeAction(
                        action_type="edit",
                        stable_key=key,
                        object_type=obj_type,
                        object_name=obj_name,
                        source_file=source_file,
                        final_attrs=final_attrs,
                    )
                )

        # Sort deletes by reverse line order within same file
        def _delete_sort_key(action):
            obj = self._find_by_identity(action.source_file, action.object_type, action.object_name)
            line = obj.line_number if obj else 0
            return (action.source_file or "", -line)
        delete_actions.sort(key=_delete_sort_key)

        return delete_actions + modify_actions + create_actions

    def apply_object_composite(self, staging_data: dict) -> OperationResult:
        """Apply all object operations as per-entity composite actions.

        Replaces the separate apply_object_deletions, apply_object_moves,
        apply_object_edits, and apply_object_creations methods. Merges
        operations on the same entity into a single action before executing.

        Returns:
            OperationResult with data containing per-type counts, errors, details.

        """
        logger.debug("apply_object_composite: result=started")
        actions = self._build_composite_actions(staging_data)

        # Partition actions by type
        delete_actions = [a for a in actions if a.action_type == "delete"]
        move_actions = [a for a in actions if a.action_type in ("move", "move_edit")]
        edit_actions = [a for a in actions if a.action_type == "edit"]
        create_actions = [a for a in actions if a.action_type == "create"]

        counts = {"deletes": 0, "moves": 0, "edits": 0, "move_edits": 0, "creates": 0}
        errors = []
        details = []

        def _record(result, detail, action):
            if result.success:
                count_key = (
                    action.action_type + "s"
                    if action.action_type != "move_edit"
                    else "move_edits"
                )
                counts[count_key] = counts.get(count_key, 0) + 1
                if detail:
                    details.append(detail)
            else:
                errors.append(
                    result.error
                    or f"Failed {action.action_type} on {action.stable_key}"
                )

        # Phase 1: Deletes (unchanged — sequential, reverse line order)
        for action in delete_actions:
            result, detail = self._exec_delete(action)
            _record(result, detail, action)

        # Phase 2: Batched moves (deterministic per-file ordering)
        if move_actions:
            move_results = self._exec_moves_batched(move_actions, staging_data)
            for (result, detail), action in zip(move_results, move_actions):
                _record(result, detail, action)

        # Phase 3: Edits (unchanged — sequential)
        for action in edit_actions:
            result, detail = self._exec_edit(action)
            _record(result, detail, action)

        # Phase 4: Creates (unchanged — sequential)
        for action in create_actions:
            result, detail = self._exec_create(action)
            _record(result, detail, action)

        total = sum(counts.values())
        if errors:
            result_str = "partial" if total > 0 else "failed"
            logger.warning(
                "apply_object_composite: %s errors=%d result=%s",
                " ".join(f"{k}={v}" for k, v in counts.items()),
                len(errors),
                result_str,
            )
        elif total > 0:
            logger.info(
                "apply_object_composite: %s result=success",
                " ".join(f"{k}={v}" for k, v in counts.items()),
            )
        else:
            logger.debug("apply_object_composite: total=0 result=noop")

        return OperationResult(
            True,
            data={
                "count": total,
                "errors": errors,
                "details": details,
                "counts": counts,
            },
        )

    def _execute_composite_action(
        self, action: CompositeAction
    ) -> tuple[OperationResult, dict | None]:
        """Execute a single composite action and return result + detail entry.

        Each action triggers a parser reload after modifying files so
        subsequent actions see the updated state.

        Args:
            action: The CompositeAction to execute.

        Returns:
            Tuple of (OperationResult, detail_dict or None).

        """
        if action.action_type == "delete":
            return self._exec_delete(action)
        if action.action_type == "edit":
            return self._exec_edit(action)
        if action.action_type == "move":
            return self._exec_move(action)
        if action.action_type == "move_edit":
            return self._exec_move_edit(action)
        if action.action_type == "create":
            return self._exec_create(action)
        return OperationResult(
            False, f"Unknown action type: {action.action_type}"
        ), None

    def _exec_delete(
        self, action: CompositeAction
    ) -> tuple[OperationResult, dict | None]:
        """Execute a delete composite action."""
        self._parser = NagiosConfigParser(self._config_path)
        self._parser.parse_all()
        target_obj = self._find_by_identity(
            action.source_file, action.object_type, action.object_name
        )
        if not target_obj:
            return OperationResult(
                False, f"Delete: object not found: {action.stable_key}"
            ), None
        result = self.delete_object(target_obj.source_file, target_obj.line_number)
        if result.success:
            detail = {
                "action": "delete",
                "object_type": action.object_type,
                "object_name": action.object_name,
                "file": target_obj.source_file,
            }
            return result, detail
        return result, None

    def _exec_edit(
        self, action: CompositeAction
    ) -> tuple[OperationResult, dict | None]:
        """Execute an edit composite action."""
        self._parser = NagiosConfigParser(self._config_path)
        self._parser.parse_all()
        target_obj = self._find_by_identity(
            action.source_file, action.object_type, action.object_name
        )
        if not target_obj:
            return OperationResult(
                False, f"Edit: object not found: {action.stable_key}"
            ), None
        old_attrs = dict(target_obj.attributes)
        merged_attrs = dict(target_obj.attributes)
        merged_attrs.update(action.final_attrs)
        result = self.update_object(
            target_obj.source_file,
            target_obj.line_number,
            merged_attrs,
            target_obj.object_type,
            inline_comments=target_obj.inline_comments,
        )
        if result.success:
            detail = self._build_edit_detail(target_obj, old_attrs, action.final_attrs)
            detail["action"] = "edit"
            return result, detail
        return result, None

    def _exec_move(
        self, action: CompositeAction
    ) -> tuple[OperationResult, dict | None]:
        """Execute a move composite action."""
        self._parser = NagiosConfigParser(self._config_path)
        self._parser.parse_all()
        target_obj = self._find_by_attrs(
            action.source_file, action.object_type, action.original_attrs
        )
        if not target_obj:
            return OperationResult(
                False, f"Move: object not found: {action.stable_key}"
            ), None
        insert_line = self._resolve_insert_position(
            action.target_file,
            action.insert_position,
            self._parser.objects,
            exclude_obj=target_obj,
        )
        result = move_object_between_files(
            target_obj.source_file,
            target_obj.line_number,
            action.target_file,
            action.object_type,
            action.original_attrs,
            insert_line,
        )
        if result.success:
            detail = {
                "action": "move",
                "object_type": action.object_type,
                "object_name": action.object_name,
                "from_file": action.source_file,
                "to_file": action.target_file,
            }
            return result, detail
        return result, None

    def _exec_move_edit(
        self, action: CompositeAction
    ) -> tuple[OperationResult, dict | None]:
        """Execute a move+edit composite action.

        Step 1: Move using original on-disk attrs for matching.
        Step 2: Edit in new location with final attrs.
        """
        # Move phase
        self._parser = NagiosConfigParser(self._config_path)
        self._parser.parse_all()
        target_obj = self._find_by_attrs(
            action.source_file, action.object_type, action.original_attrs
        )
        if not target_obj:
            return OperationResult(
                False, f"MoveEdit move: object not found: {action.stable_key}"
            ), None
        insert_line = self._resolve_insert_position(
            action.target_file,
            action.insert_position,
            self._parser.objects,
            exclude_obj=target_obj,
        )
        move_result = move_object_between_files(
            target_obj.source_file,
            target_obj.line_number,
            action.target_file,
            action.object_type,
            action.original_attrs,
            insert_line,
        )
        if not move_result.success:
            return move_result, None

        # Edit phase — find the moved object in target file
        self._parser = NagiosConfigParser(self._config_path)
        self._parser.parse_all()
        moved_obj = self._find_by_identity(
            action.target_file, action.object_type, action.object_name
        )
        if not moved_obj:
            return OperationResult(
                False,
                f"MoveEdit edit: object not found after move: {action.stable_key}",
            ), None
        old_attrs = dict(moved_obj.attributes)
        merged_attrs = dict(moved_obj.attributes)
        merged_attrs.update(action.final_attrs)
        edit_result = self.update_object(
            moved_obj.source_file,
            moved_obj.line_number,
            merged_attrs,
            moved_obj.object_type,
            inline_comments=moved_obj.inline_comments,
        )
        if edit_result.success:
            detail = {
                "action": "move_edit",
                "object_type": action.object_type,
                "object_name": action.object_name,
                "from_file": action.source_file,
                "to_file": action.target_file,
                "changes": self._build_edit_detail(
                    moved_obj, old_attrs, action.final_attrs
                ).get("changes", []),
            }
            return edit_result, detail
        return edit_result, None

    def _exec_create(
        self, action: CompositeAction
    ) -> tuple[OperationResult, dict | None]:
        """Execute a create composite action."""
        result = self.create_object(
            action.target_file,
            action.object_type,
            action.final_attrs,
            inline_comments=action.inline_comments,
        )
        if result.success:
            detail = {
                "action": "create",
                "object_type": action.object_type,
                "object_name": action.object_name,
                "file": action.target_file,
            }
            return result, detail
        return result, None

    def _extract_raw_blocks_for_actions(
        self, move_actions: list[CompositeAction],
    ) -> dict[str, str]:
        """Extract raw block text for each move action's source object.

        Must be called BEFORE any file mutations. Reads each source file,
        finds the object by identity, extracts the raw define block.

        Returns dict mapping stable_key -> raw_block_text.
        """
        blocks = {}
        # Cache file contents to avoid re-reading
        file_cache: dict[str, str] = {}

        for action in move_actions:
            source_real = os.path.realpath(action.source_file)
            if source_real not in file_cache:
                try:
                    file_cache[source_real] = Path(action.source_file).read_text()
                except OSError as e:
                    logger.warning("move_batch extract: read error file=%s: %s", action.source_file, e)
                    continue

            content = file_cache[source_real]
            # Find the object in parser
            obj = self._find_by_attrs(
                action.source_file, action.object_type, action.original_attrs,
            )
            if not obj:
                logger.warning("move_batch extract: object not found key=%s", action.stable_key)
                continue

            block_range = find_block_range(content, obj.line_number)
            if not block_range:
                logger.warning("move_batch extract: block not found key=%s line=%d", action.stable_key, obj.line_number)
                continue

            start_char, end_char = block_range
            raw_block = content[start_char:end_char].strip()
            blocks[action.stable_key] = raw_block
            logger.debug("move_batch extract: key=%s line=%d len=%d", action.stable_key, obj.line_number, len(raw_block))

        return blocks

    def _exec_moves_batched(
        self, move_actions: list[CompositeAction], staging_data: dict,
    ) -> list[tuple[OperationResult, dict | None]]:
        """Execute all moves with deterministic per-file ordering.

        1. Parse once (pre-mutation snapshot)
        2. Extract all raw blocks from source files
        3. For each affected target file:
           a. Compute expected order via _compute_expected_file_order
           b. For existing objects staying in file: extract raw blocks
           c. Assemble file from preamble + ordered blocks
           d. Atomic write
        4. For source files not already rewritten: remove moved objects
        5. For move_edit actions: re-parse and apply edits
        """
        results = []

        # Step 1: Parse once
        self._parser = NagiosConfigParser(self._config_path)
        self._parser.parse_all()

        # Step 2: Extract raw blocks for all move actions BEFORE mutations
        raw_blocks = self._extract_raw_blocks_for_actions(move_actions)

        # Actions that failed to extract a raw block → report error immediately
        failed_keys: set[str] = set()
        for action in move_actions:
            if action.stable_key not in raw_blocks:
                failed_keys.add(action.stable_key)
                results.append((
                    OperationResult(False, f"Move: object not found at source: {action.stable_key}"),
                    None,
                ))

        # Filter to only actions with extracted blocks
        move_actions = [a for a in move_actions if a.stable_key not in failed_keys]
        if not move_actions:
            return results

        # Build helper sets
        all_move_keys = {a.stable_key for a in move_actions}
        delete_keys = set()  # Deletions handled in separate phase

        # Identify all affected target files
        target_files = set()
        for action in move_actions:
            target_files.add(os.path.realpath(action.target_file))
        # Also include source files that have objects being moved out (for cleanup)
        source_files = set()
        for action in move_actions:
            source_files.add(os.path.realpath(action.source_file))

        # Cache current file contents for existing block extraction
        file_contents: dict[str, str] = {}
        for fpath in target_files | source_files:
            # Find the actual path (not necessarily realpath) for reading
            try:
                content = Path(fpath).read_text()
                file_contents[fpath] = content
            except OSError:
                pass

        # Track which files we've rewritten (to avoid double-processing)
        rewritten_files: set[str] = set()

        # Step 3: For each target file, compute order and write
        for target_real in target_files:
            # Find the actual file path from an action
            target_path = None
            for a in move_actions:
                if os.path.realpath(a.target_file) == target_real:
                    target_path = a.target_file
                    break
            if not target_path:
                continue

            # Get incoming actions for this target
            incoming = [
                a for a in move_actions
                if os.path.realpath(a.target_file) == target_real
            ]

            # Compute expected order
            order = self._compute_expected_file_order(
                target_path, incoming, move_actions, delete_keys,
            )

            existing_count = sum(1 for item in order if item["source"] == "existing")
            incoming_count = sum(1 for item in order if item["source"] == "incoming")
            logger.debug(
                "move_batch plan: file=%s existing=%d incoming=%d final=%d",
                target_path, existing_count, incoming_count, len(order),
            )
            for i, item in enumerate(order):
                logger.debug(
                    "move_batch plan[%d]: %s %s pos=%.1f",
                    i, item["source"], item["name"], item["position"],
                )

            # Extract preamble from current file content
            current_content = file_contents.get(target_real, "")
            all_blocks = extract_all_blocks(current_content)
            if all_blocks:
                preamble = current_content[:all_blocks[0][0]]
            else:
                preamble = current_content

            # Build ordered block list
            ordered_blocks = []
            for item in order:
                if item["source"] == "existing":
                    # Extract raw block from current file content
                    obj = item["obj"]
                    block_range = find_block_range(current_content, obj.line_number)
                    if block_range:
                        start, end = block_range
                        ordered_blocks.append(current_content[start:end].strip())
                    else:
                        logger.warning("move_batch write: existing block not found name=%s", item["name"])
                elif item["source"] == "incoming":
                    action = item["action"]
                    if action.stable_key in raw_blocks:
                        ordered_blocks.append(raw_blocks[action.stable_key])
                    else:
                        logger.warning("move_batch write: raw block missing key=%s", action.stable_key)

            # Assemble and write
            if not ordered_blocks and not preamble.strip():
                # File would be empty — write empty content
                new_content = ""
            else:
                new_content = assemble_file_from_blocks(preamble, ordered_blocks)

            logger.debug("move_batch write: file=%s blocks=%d", target_path, len(ordered_blocks))
            try:
                # Ensure parent directory exists (for new files)
                Path(target_path).parent.mkdir(parents=True, exist_ok=True)
                _atomic_write(target_path, new_content)
                rewritten_files.add(target_real)
            except OSError as e:
                for a in incoming:
                    results.append((
                        OperationResult(False, f"Write error for {target_path}: {e}"),
                        None,
                    ))
                continue

            # Record success for each incoming move action
            for a in incoming:
                detail = {
                    "action": "move" if a.action_type == "move" else "move_edit",
                    "object_type": a.object_type,
                    "object_name": a.object_name,
                    "from_file": a.source_file,
                    "to_file": a.target_file,
                }
                results.append((OperationResult(True), detail))

        # Step 4: Clean up source files (remove moved-out objects)
        # Group moves by source file
        source_groups: dict[str, list[CompositeAction]] = {}
        for action in move_actions:
            src_real = os.path.realpath(action.source_file)
            # Skip if source was already rewritten as a target (same-file reorder)
            if src_real in rewritten_files:
                continue
            source_groups.setdefault(src_real, []).append(action)

        for src_real, actions_in_file in source_groups.items():
            # Re-read and rebuild the source file without the moved objects
            src_path = actions_in_file[0].source_file
            try:
                src_content = Path(src_path).read_text()
            except OSError:
                continue

            src_blocks = extract_all_blocks(src_content)
            if not src_blocks:
                continue

            # Determine which blocks to keep
            # Re-parse to find current objects
            self._parser = NagiosConfigParser(self._config_path)
            self._parser.parse_all()
            src_objs = [
                o for o in self._parser.objects
                if os.path.realpath(o.source_file) == src_real
            ]
            src_objs.sort(key=lambda o: o.line_number)

            moved_keys = {a.stable_key for a in actions_in_file}
            keep_blocks = []
            for obj in src_objs:
                obj_name = get_object_name(obj.object_type, obj.attributes)
                obj_key = f"{os.path.realpath(obj.source_file)}|{obj.object_type}|{obj_name}"
                if obj_key in moved_keys:
                    logger.debug("move_batch source_delete: file=%s key=%s", src_path, obj_key)
                    continue
                block_range = find_block_range(src_content, obj.line_number)
                if block_range:
                    start, end = block_range
                    keep_blocks.append(src_content[start:end].strip())

            # Extract preamble
            if src_blocks:
                preamble = src_content[:src_blocks[0][0]]
            else:
                preamble = ""

            new_content = assemble_file_from_blocks(preamble, keep_blocks)
            try:
                _atomic_write(src_path, new_content)
            except OSError as e:
                logger.warning("move_batch source_delete: write error file=%s: %s", src_path, e)

        # Step 5: For move_edit actions, re-parse and apply edits
        move_edit_actions = [a for a in move_actions if a.action_type == "move_edit"]
        if move_edit_actions:
            self._parser = NagiosConfigParser(self._config_path)
            self._parser.parse_all()
            for action in move_edit_actions:
                moved_obj = self._find_by_identity(
                    action.target_file, action.object_type, action.object_name,
                )
                if not moved_obj:
                    # Update the result for this action
                    for i, (r, d) in enumerate(results):
                        if d and d.get("object_name") == action.object_name and d.get("action") == "move_edit":
                            results[i] = (
                                OperationResult(False, f"MoveEdit edit: object not found after move: {action.stable_key}"),
                                None,
                            )
                            break
                    continue

                old_attrs = dict(moved_obj.attributes)
                merged_attrs = dict(moved_obj.attributes)
                merged_attrs.update(action.final_attrs)
                edit_result = self.update_object(
                    moved_obj.source_file,
                    moved_obj.line_number,
                    merged_attrs,
                    moved_obj.object_type,
                    inline_comments=moved_obj.inline_comments,
                )
                if not edit_result.success:
                    for i, (r, d) in enumerate(results):
                        if d and d.get("object_name") == action.object_name and d.get("action") == "move_edit":
                            results[i] = (edit_result, None)
                            break
                else:
                    # Update detail with changes info
                    for i, (r, d) in enumerate(results):
                        if d and d.get("object_name") == action.object_name and d.get("action") == "move_edit":
                            d["changes"] = self._build_edit_detail(
                                moved_obj, old_attrs, action.final_attrs,
                            ).get("changes", [])
                            break
                    # Re-parse for next edit
                    self._parser = NagiosConfigParser(self._config_path)
                    self._parser.parse_all()

        # Step 6: Verify ordering
        expected_orders: dict[str, list[str]] = {}
        for target_real in target_files:
            target_path = None
            for a in move_actions:
                if os.path.realpath(a.target_file) == target_real:
                    target_path = a.target_file
                    break
            if target_path:
                incoming = [
                    a for a in move_actions
                    if os.path.realpath(a.target_file) == target_real
                ]
                order = self._compute_expected_file_order(
                    target_path, incoming, move_actions, delete_keys,
                )
                expected_orders[target_path] = [item["name"] for item in order]

        warnings = self._verify_move_ordering(expected_orders)
        for w in warnings:
            logger.warning("move_batch verify: %s", w)

        return results

    def _verify_move_ordering(self, expected_orders: dict[str, list[str]]) -> list[str]:
        """Re-parse affected files, compare object order against expected.

        Returns list of warning messages (empty = all match).
        """
        self._parser = NagiosConfigParser(self._config_path)
        self._parser.parse_all()
        warnings = []
        for file_path, expected_names in expected_orders.items():
            actual = [
                get_object_name(o.object_type, o.attributes)
                for o in self.parser.objects
                if os.path.realpath(o.source_file) == os.path.realpath(file_path)
            ]
            if actual != expected_names:
                warnings.append(
                    f"Order mismatch in {file_path}: expected={expected_names} actual={actual}"
                )
        return warnings

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

    def _compute_expected_file_order(
        self,
        target_file: str,
        incoming_actions: list[CompositeAction],
        all_move_actions: list[CompositeAction],
        delete_keys: set[str],
    ) -> list[dict]:
        """Compute expected object order for a target file after all moves.

        Mirrors frontend buildFileItemsList logic:
        1. Existing objects in file sorted by line_number
        2. Remove objects being moved OUT or deleted
        3. Add incoming objects at their insertPosition
        4. Sort by position

        Returns list of dicts with: source, stable_key, name, position, action (if incoming).
        """
        target_real = os.path.realpath(target_file)

        # Build set of keys being moved (any direction) for quick lookup
        move_keys = {a.stable_key for a in all_move_actions}

        # Get existing objects in target file, sorted by line_number
        existing = [
            o for o in self.parser.objects
            if os.path.realpath(o.source_file) == target_real
        ]
        existing.sort(key=lambda o: o.line_number)

        order = []
        for obj in existing:
            obj_name = get_object_name(obj.object_type, obj.attributes)
            obj_key = f"{os.path.realpath(obj.source_file)}|{obj.object_type}|{obj_name}"

            # Skip objects staged for deletion
            if obj_key in delete_keys:
                continue

            # Skip objects being moved (they'll be re-added at new position if
            # targeting this same file, or removed if targeting another file)
            if obj_key in move_keys:
                continue

            order.append({
                "source": "existing",
                "stable_key": obj_key,
                "name": obj_name,
                "position": float(obj.line_number),
                "obj": obj,
            })

        # Add incoming move actions
        for action in incoming_actions:
            pos = float(action.insert_position) if action.insert_position is not None else float("inf")
            order.append({
                "source": "incoming",
                "stable_key": action.stable_key,
                "name": action.object_name,
                "position": pos,
                "action": action,
            })

        order.sort(key=lambda item: item["position"])
        return order

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

    def search_objects(
        self,
        query: str,
        object_type: str = None,
        field: str = None,
        use_regex: bool = False,
    ) -> list:
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
                result = move_object_between_files(
                    source_file, source_line, target_file, obj_type, attrs, insert_line
                )
                if not result.success:
                    logger.error(
                        "move_object failed: source_file=%s target_file=%s obj_type=%s error=%s",
                        source_file,
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
                    "move_object: source_file=%s target_file=%s obj_type=%s result=success",
                    source_file,
                    target_file,
                    obj_type,
                )
                return OperationResult(True)
            except Exception as e:  # noqa: BLE001
                logger.exception(
                    "move_object failed: source_file=%s target_file=%s obj_type=%s",
                    source_file,
                    target_file,
                    obj_type,
                )
                return OperationResult(False, f"Move failed: {e}")

    # =========================================================================
    # Staging Apply Operations
    # =========================================================================

    def _log_apply_result(self, phase: str, count: int, errors: list) -> None:
        """Log the result of an apply phase."""
        if errors:
            result = "partial" if count > 0 else "failed"
            logger.warning(
                "%s: count=%d error_count=%d result=%s",
                phase,
                count,
                len(errors),
                result,
            )
        elif count > 0:
            logger.info("%s: count=%d result=success", phase, count)
        else:
            logger.debug("%s: count=0 result=noop", phase)

    def apply_folder_creations(self, staging_data: dict) -> OperationResult:
        """Create staged folders."""
        logger.debug("apply_folder_creations: result=started")
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
                    f.write(
                        f"# Nagios configuration file: {os.path.basename(file_path)}\n\n"
                    )
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
        logger.debug("apply_file_creations: result=started")
        errors = []
        count = self._apply_staged_file_creations(
            staging_data.get("stagedFileCreations", []),
            errors,
        )
        count += self._apply_new_files(
            staging_data.get("newFiles", []),
            errors,
        )
        result = self._build_apply_result("file_creations", count, errors)
        self._log_apply_result("apply_file_creations", count, errors)
        return OperationResult(True, data=result)

    def _resolve_insert_position(
        self, target_file: str, insert_position, parser_objects: list, exclude_obj=None
    ) -> int | None:
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
        target_objects = [
            o for o in parser_objects if os.path.realpath(o.source_file) == target_real
        ]

        # Exclude the object being moved (for same-file reordering)
        if exclude_obj is not None:
            target_objects = [
                o
                for o in target_objects
                if not (
                    o.line_number == exclude_obj.line_number
                    and o.object_type == exclude_obj.object_type
                )
            ]

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

    def _build_edit_detail(
        self, target_obj, old_attrs: dict, edited_attrs: dict
    ) -> dict:
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
                changes.append(
                    {"type": "modify", "key": key, "from": old_val, "to": new_val}
                )

        obj_name = get_object_name(target_obj.object_type, old_attrs)
        name_field = NAME_FIELDS.get(target_obj.object_type)
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

    def apply_file_moves(self, staging_data: dict) -> OperationResult:
        """Move staged files."""
        logger.debug("apply_file_moves: result=started")
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
        logger.debug("apply_folder_moves: result=started")
        folder_moves = staging_data.get("stagedFolderMoves", [])
        count = 0
        errors = []
        details = []

        for op in folder_moves:
            source_path = op.get("sourcePath")
            target_path = op.get("targetPath")
            if source_path and target_path:
                is_safe_src, error_src = self._validate_path_safety(
                    source_path, "folder"
                )
                is_safe_tgt, error_tgt = self._validate_path_safety(
                    target_path, "folder"
                )
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
        logger.debug("apply_file_deletions: result=started")
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
        logger.debug("apply_folder_deletions: result=started")
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
