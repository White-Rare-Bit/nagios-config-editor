"""
Nagios Service Layer

Provides business logic and unified CRUD operations with automatic parser reload.
Eliminates temporal coupling: callers no longer need to remember to call reload_config().
"""

import re
import multiprocessing
from contextlib import contextmanager
from typing import Dict, List, Optional

from nagios_model import NagiosObject, NAME_FIELDS, OperationResult, format_object_block, get_object_name
from nagios_parser import NagiosConfigParser
from file_operations import (
    edit_object_in_file, delete_object_from_file,
    add_object_to_file, move_object_between_files,
    find_block_range
)
from staging_manager import (
    parse_stable_key,
    StagingState,
    StagingManager,
    _ensure_dict_format
)
from pathlib import Path
import os
import shutil


def _iterate_entries(data):
    """Iterate over staging entries regardless of dict or list format.

    Handles both formats:
    - Dict format {key: entry_data, ...}: adds key/globalIndex to entry_data
    - List format [{entry_data}, ...]: returns entries directly

    Args:
        data: Dict or list of staging entries

    Returns:
        Iterable of entry dicts with key/globalIndex populated
    """
    if isinstance(data, dict):
        for key, entry in data.items():
            if isinstance(entry, dict):
                if 'globalIndex' not in entry and 'key' not in entry:
                    entry['globalIndex'] = key
                    entry['key'] = key
                yield entry
            else:
                yield entry
    elif isinstance(data, list):
        for entry in data:
            yield entry


class NagiosService:
    """Service layer for Nagios configuration management.

    Wraps the parser and file operations, providing a unified interface
    with automatic state synchronization (reload after write).
    """

    def __init__(self, config_path: str, staging_manager: Optional[StagingManager] = None, op_logger=None):
        self._config_path = config_path
        self._parser: Optional[NagiosConfigParser] = None
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
                self._op_logger.debug('parser', 'reload', params={'config_path': self._config_path})
            return self._parser

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

    def get_typed_staging(self) -> Optional[StagingState]:
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

    def find_object_by_index(self, idx: int) -> Optional[NagiosObject]:
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
            'total': len(objects),
            'by_type': type_counts,
            'file_count': len(files),
        }

    # =========================================================================
    # Domain Logic (moved from app.py)
    # =========================================================================

    def get_name_field(self, object_type: str) -> str:
        """Get the name field for a given object type."""
        return NAME_FIELDS.get(object_type, 'name')

    def find_object_by_stable_key(self, stable_key: str) -> Optional[tuple]:
        """Find an object by its stable key.

        Args:
            stable_key: Stable key in format "source_file|object_type|name"

        Returns:
            Tuple of (global_index, NagiosObject) or None if not found
        """
        parsed = parse_stable_key(stable_key)
        if not parsed:
            return None

        source_file = parsed['source_file']
        obj_type = parsed['object_type']
        target_name = parsed['name']

        p = self.parser
        for idx, obj in enumerate(p.objects):
            if obj.source_file != source_file:
                continue
            if obj.object_type != obj_type:
                continue
            obj_name = get_object_name(obj.object_type, obj.attributes)
            if obj_name == target_name:
                return (idx, obj)

        return None

    def transform_name(self, name: str, find_pattern: str = '', replace_with: str = '',
                       prefix: str = '', suffix: str = '', use_regex: bool = False) -> Optional[str]:
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

    def update_references(self, objects: List[NagiosObject], old_name: str, new_name: str) -> int:
        """Update all references to an object when it's renamed.

        Returns the count of individual references updated.
        """
        references_updated = 0
        for obj in objects:
            for field_name, value in list(obj.attributes.items()):
                values = [v.strip() for v in value.split(',')]
                if old_name in values:
                    replacement_count = values.count(old_name)
                    new_values = [new_name if v == old_name else v for v in values]
                    obj.attributes[field_name] = ','.join(new_values)
                    references_updated += replacement_count
        return references_updated

    # =========================================================================
    # CRUD Operations (unified file_operations + reload)
    # =========================================================================

    def _reload_parser_safe(self, old_parser: Optional[NagiosConfigParser], file_path: str = None) -> OperationResult:
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
        except Exception as e:
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
                self._op_logger.error('service', 'parser_reload',
                                     params={'file_path': file_path, 'corrupted': True},
                                     error=str(e))
            return OperationResult(False, error_msg)

    def _check_parser_state(self) -> Optional[OperationResult]:
        """Check if parser state is corrupted and return error if so.

        Returns:
            OperationResult with error if corrupted, None if OK to proceed.
        """
        if self._parser_corrupted:
            return OperationResult(
                False,
                "CRITICAL: Parser state is inconsistent with disk state. "
                "All operations are blocked until explicit reload succeeds. "
                "Run POST /api/reload to resync parser."
            )

    def create_object(self, target_file: str, obj_type: str, attrs: Dict[str, str],
                      after_block_line: Optional[int] = None) -> OperationResult:
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
                        self._op_logger.error('service', 'create_object', params={'target_file': target_file, 'obj_type': obj_type}, error=result.error)
                    return result
                # Save old parser for rollback on reload failure
                old_parser = self._parser
                reload_result = self._reload_parser_safe(old_parser, file_path=target_file)
                if not reload_result.success:
                    return reload_result
                if self._op_logger:
                    self._op_logger.info('service', 'create_object', params={'target_file': target_file, 'obj_type': obj_type}, result='success')
                return OperationResult(True)
            except Exception as e:
                if self._op_logger:
                    self._op_logger.error('service', 'create_object', params={'target_file': target_file, 'obj_type': obj_type}, error=str(e))
                return OperationResult(False, f"Create failed: {e}")

    def update_object(self, source_file: str, line_number: int,
                      new_attrs: Dict[str, str], obj_type: str) -> OperationResult:
        """Update an object's attributes in place.

        Args:
            source_file: Path to the config file
            line_number: Line number where object starts
            new_attrs: New attributes dictionary
            obj_type: Object type (for formatting)

        Returns:
            OperationResult with success status
        """
        with self._lock:
            # Check if parser state is corrupted
            corrupted_error = self._check_parser_state()
            if corrupted_error:
                return corrupted_error

            try:
                result = edit_object_in_file(source_file, line_number, new_attrs, obj_type)
                if not result.success:
                    if self._op_logger:
                        self._op_logger.error('service', 'update_object', params={'source_file': source_file, 'line_number': line_number, 'obj_type': obj_type}, error=result.error)
                    return result
                # Save old parser for rollback on reload failure
                old_parser = self._parser
                reload_result = self._reload_parser_safe(old_parser, file_path=source_file)
                if not reload_result.success:
                    return reload_result
                if self._op_logger:
                    self._op_logger.info('service', 'update_object', params={'source_file': source_file, 'line_number': line_number, 'obj_type': obj_type}, result='success')
                return OperationResult(True)
            except Exception as e:
                if self._op_logger:
                    self._op_logger.error('service', 'update_object', params={'source_file': source_file, 'line_number': line_number, 'obj_type': obj_type}, error=str(e))
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
                        self._op_logger.error('service', 'delete_object', params={'source_file': source_file, 'line_number': line_number}, error=result.error)
                    return result
                # Save old parser for rollback on reload failure
                old_parser = self._parser
                reload_result = self._reload_parser_safe(old_parser, file_path=source_file)
                if not reload_result.success:
                    return reload_result
                if self._op_logger:
                    self._op_logger.info('service', 'delete_object', params={'source_file': source_file, 'line_number': line_number}, result='success')
                return OperationResult(True)
            except Exception as e:
                if self._op_logger:
                    self._op_logger.error('service', 'delete_object', params={'source_file': source_file, 'line_number': line_number}, error=str(e))
                return OperationResult(False, f"Delete failed: {e}")

    def move_object(self, source_file: str, source_line: int,
                    target_file: str, obj_type: str, attrs: Dict[str, str],
                    insert_line: Optional[int] = None) -> OperationResult:
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
                        self._op_logger.error('service', 'move_object', params={'source_file': source_file, 'target_file': target_file, 'obj_type': obj_type}, error=result.error)
                    return result
                # Save old parser for rollback on reload failure
                old_parser = self._parser
                reload_result = self._reload_parser_safe(old_parser, file_path=target_file)
                if not reload_result.success:
                    return reload_result
                if self._op_logger:
                    self._op_logger.info('service', 'move_object', params={'source_file': source_file, 'target_file': target_file, 'obj_type': obj_type}, result='success')
                return OperationResult(True)
            except Exception as e:
                if self._op_logger:
                    self._op_logger.error('service', 'move_object', params={'source_file': source_file, 'target_file': target_file, 'obj_type': obj_type}, error=str(e))
                return OperationResult(False, f"Move failed: {e}")

    # =========================================================================
    # Staging Apply Operations
    # =========================================================================

    def _log_apply_result(self, phase: str, count: int, errors: list) -> None:
        """Log the result of an apply phase."""
        if not self._op_logger:
            return
        if errors:
            self._op_logger.warning('service', phase,
                                    params={'count': count, 'error_count': len(errors)},
                                    result='partial' if count > 0 else 'failed')
        elif count > 0:
            self._op_logger.info('service', phase,
                                 params={'count': count}, result='success')
        else:
            self._op_logger.debug('service', phase, params={'count': 0}, result='noop')

    def apply_folder_creations(self, staging_data: dict, is_safe_path_func) -> OperationResult:
        """Create staged folders."""
        if self._op_logger:
            self._op_logger.debug('service', 'apply_folder_creations', result='started')
        folder_creations = staging_data.get('stagedFolderCreations', [])
        folder_creations.sort(key=lambda x: x.get('path', '').count('/'))
        count = 0
        errors = []
        details = []

        for op in folder_creations:
            folder_path = op.get('path')
            if folder_path:
                safe, err = is_safe_path_func(folder_path, self._config_path)
                if not safe:
                    errors.append(f"Unsafe folder path {folder_path}: {err}")
                    continue
                try:
                    os.makedirs(folder_path, exist_ok=True)
                    count += 1
                    details.append({'path': folder_path})
                except Exception as e:
                    errors.append(f"Failed to create folder {folder_path}: {e}")

        self._log_apply_result('apply_folder_creations', count, errors)
        return OperationResult(True, data={'count': count, 'errors': errors, 'details': details})

    def apply_file_creations(self, staging_data: dict, is_safe_path_func) -> OperationResult:
        """Create staged files."""
        if self._op_logger:
            self._op_logger.debug('service', 'apply_file_creations', result='started')
        file_creations = staging_data.get('stagedFileCreations', [])
        count = 0
        errors = []

        for op in file_creations:
            file_path = op.get('path')
            if file_path:
                safe, err = is_safe_path_func(file_path, self._config_path)
                if not safe:
                    errors.append(f"Unsafe file path {file_path}: {err}")
                    continue
                try:
                    parent_dir = os.path.dirname(file_path)
                    if parent_dir:
                        os.makedirs(parent_dir, exist_ok=True)
                    if not os.path.exists(file_path):
                        with open(file_path, 'w') as f:
                            f.write(f"# Nagios configuration file: {os.path.basename(file_path)}\n\n")
                        count += 1
                except Exception as e:
                    errors.append(f"Failed to create file {file_path}: {e}")

        new_files = staging_data.get('newFiles', [])
        for file_path in new_files:
            if not os.path.isabs(file_path):
                file_path = os.path.join(self._config_path, file_path)
            safe, err = is_safe_path_func(file_path, self._config_path)
            if not safe:
                errors.append(f"Unsafe file path {file_path}: {err}")
                continue
            try:
                parent_dir = os.path.dirname(file_path)
                if parent_dir:
                    os.makedirs(parent_dir, exist_ok=True)
                if not os.path.exists(file_path):
                    Path(file_path).touch()
                    count += 1
            except Exception as e:
                errors.append(f"Failed to create file {file_path}: {e}")

        self._log_apply_result('apply_file_creations', count, errors)
        return OperationResult(True, data={'count': count, 'errors': errors})

    def apply_object_deletions(self, staging_data: dict) -> OperationResult:
        """Delete staged objects."""
        if self._op_logger:
            self._op_logger.debug('service', 'apply_object_deletions', result='started')
        staged_deletions = staging_data.get('stagedObjectDeletions', [])
        count = 0
        errors = []
        details = []

        if staged_deletions:
            p = self.parser
            objects_to_delete = []

            for deletion_entry in staged_deletions:
                # Handle integer global_index directly (frontend sends Array.from(Set))
                if isinstance(deletion_entry, int):
                    if 0 <= deletion_entry < len(p.objects):
                        obj = p.objects[deletion_entry]
                        objects_to_delete.append((obj.source_file, obj.line_number, obj.object_type, obj))
                    continue

                normalized = _ensure_dict_format(deletion_entry)
                source_file = normalized.get('source_file')
                line_number = normalized.get('line_number')
                obj_type = normalized.get('object_type')

                if source_file and line_number:
                    for obj in p.objects:
                        if (obj.source_file == source_file and
                            obj.line_number == line_number and
                            obj.object_type == obj_type):
                            objects_to_delete.append((source_file, line_number, obj_type, obj))
                            break
                elif normalized.get('key'):
                    try:
                        global_index = int(normalized['key'])
                        if 0 <= global_index < len(p.objects):
                            obj = p.objects[global_index]
                            objects_to_delete.append((obj.source_file, obj.line_number, obj.object_type, obj))
                    except (ValueError, KeyError):
                        pass

            objects_to_delete.sort(key=lambda x: (x[0], -x[1]))
            for source_file, line_number, obj_type, obj in objects_to_delete:
                name_field = NAME_FIELDS.get(obj_type)
                obj_name = obj.attributes.get(name_field, '') if name_field else ''
                result = self.delete_object(source_file, line_number)
                if result.success:
                    count += 1
                    details.append({
                        'object_type': obj_type,
                        'object_name': obj_name,
                        'file': source_file
                    })
                    p = self.parser
                elif result.error:
                    errors.append(f"Failed to delete object at {source_file}:{line_number}: {result.error}")

        self._log_apply_result('apply_object_deletions', count, errors)
        return OperationResult(True, data={'count': count, 'errors': errors, 'details': details})

    def _group_moves_by_target(self, moves: List[dict]) -> dict:
        """Group moves by target file realpath.

        Args:
            moves: List of normalized move dictionaries

        Returns:
            Dict mapping target realpath to list of moves for that target
        """
        from collections import defaultdict
        by_target = defaultdict(list)
        for move in moves:
            by_target[os.path.realpath(move['target_file'])].append(move)
        return by_target

    def _compute_moved_out_by_file(self, moves: List[dict]) -> dict:
        """Compute which objects are being moved out of each file.

        Args:
            moves: List of normalized move dictionaries

        Returns:
            Dict mapping source realpath to set of (obj_type, attrs_tuple) being moved out
        """
        from collections import defaultdict
        moved_out_by_file = defaultdict(set)
        for move in moves:
            source_real = os.path.realpath(move['source_file'])
            attrs_key = (move['obj_type'], tuple(sorted(move['attrs'].items())))
            # Object is removed from source (whether cross-file move or same-file reorder)
            moved_out_by_file[source_real].add(attrs_key)
        return moved_out_by_file

    def _compute_target_file_order(self, target_moves: List[dict], existing_objects: list,
                                   removed_from_here: set) -> List[dict]:
        """Compute final object order for a target file.

        Args:
            target_moves: Moves targeting this file
            existing_objects: Current objects in file (sorted by line_number)
            removed_from_here: Set of (obj_type, attrs_tuple) being moved out

        Returns:
            Sorted list of item dicts with position, obj_type, attrs, line_number
        """
        items = []

        # Existing objects that stay in place
        for obj in existing_objects:
            attrs_key = (obj.object_type, tuple(sorted(obj.attributes.items())))
            if attrs_key not in removed_from_here:
                items.append({
                    'position': obj.line_number,
                    'obj_type': obj.object_type,
                    'attrs': obj.attributes,
                    'line_number': obj.line_number,
                })

        # Add incoming/reordered objects at their insertPositions
        for move in target_moves:
            pos = float(move['insert_position']) if move['insert_position'] is not None else float('inf')
            items.append({
                'position': pos,
                'obj_type': move['obj_type'],
                'attrs': move['attrs'],
                'line_number': None,  # No existing line (will be formatted fresh)
            })

        # Sort by position to get final order
        items.sort(key=lambda x: x['position'])
        return items

    def _rewrite_target_file(self, target_path: str, items: List[dict],
                             content: str) -> Optional[str]:
        """Rewrite target file with computed object order.

        Args:
            target_path: Path to target file
            items: Sorted list of items to write
            content: Current file content (for extracting existing blocks)

        Returns:
            Error message on failure, None on success
        """
        # Extract blocks: for existing objects, preserve original formatting
        blocks = []
        for item in items:
            if item['line_number'] is not None:
                block_range = find_block_range(content, item['line_number'])
                if block_range:
                    start, end = block_range
                    blocks.append(content[start:end].strip())
                else:
                    blocks.append(format_object_block(item['obj_type'], item['attrs']))
            else:
                blocks.append(format_object_block(item['obj_type'], item['attrs']))

        # Preserve file header (comments/whitespace before first define block)
        first_define = content.find('define ')
        header = content[:first_define].rstrip('\n') if first_define > 0 else ''

        # Build new content
        if blocks:
            if header:
                new_content = header + '\n\n' + '\n\n'.join(blocks) + '\n'
            else:
                new_content = '\n\n'.join(blocks) + '\n'
        else:
            new_content = header + '\n' if header else ''

        try:
            Path(target_path).write_text(new_content)
            return None
        except (IOError, OSError) as e:
            return f"Failed to write {target_path}: {e}"

    def _cleanup_source_only_files(self, source_only_removals: dict, errors: list) -> None:
        """Delete moved-out objects from source-only files.

        Args:
            source_only_removals: Dict mapping source realpath to list of moves
            errors: List to append error messages to
        """
        for source_real, source_moves in source_only_removals.items():
            source_path = source_moves[0]['source_file']
            # Reload parser to get current line numbers
            self._parser = NagiosConfigParser(self._config_path)
            self._parser.parse_all()
            p = self.parser

            # Find objects to delete (process in reverse line order)
            to_delete = []
            for move in source_moves:
                for obj in p.objects:
                    if (os.path.realpath(obj.source_file) == source_real and
                        obj.object_type == move['obj_type'] and
                        obj.attributes == move['attrs']):
                        to_delete.append(obj.line_number)
                        break

            to_delete.sort(reverse=True)
            for line_num in to_delete:
                result = delete_object_from_file(source_path, line_num)
                if not result.success:
                    errors.append(f"Failed to remove from source: {result.error}")

    def _normalize_staged_moves(self, staged_moves: List[dict]) -> List[dict]:
        """Normalize staged move entries into a consistent format.

        Args:
            staged_moves: Raw staged move entries from staging data

        Returns:
            List of normalized move dicts with target_file, source_file,
            obj_type, attrs, and insert_position keys
        """
        moves = []
        for entry in _iterate_entries(staged_moves):
            move_data = _ensure_dict_format(entry)
            target_file = move_data.get('targetFile')
            obj_info = move_data.get('object', {})
            source_file = obj_info.get('source_file')
            obj_type = obj_info.get('object_type')
            attrs = obj_info.get('attributes', {})
            insert_position = move_data.get('insertPosition')
            if all([target_file, source_file, obj_type, attrs]):
                moves.append({
                    'target_file': target_file,
                    'source_file': source_file,
                    'obj_type': obj_type,
                    'attrs': attrs,
                    'insert_position': insert_position,
                })
        return moves

    def _process_target_file_moves(
        self,
        target_real: str,
        target_moves: List[dict],
        moved_out_by_file: dict,
        parser_objects: list,
        errors: list,
        details: list
    ) -> int:
        """Process moves for a single target file.

        Args:
            target_real: Realpath of the target file
            target_moves: List of moves targeting this file
            moved_out_by_file: Dict of objects being moved out by file
            parser_objects: Current parser objects list
            errors: List to append errors to
            details: List to append details to

        Returns:
            Number of successful moves
        """
        target_path = target_moves[0]['target_file']
        count = 0

        # Get existing objects in this file from the parser
        existing_objects = [o for o in parser_objects
                           if os.path.realpath(o.source_file) == target_real]
        existing_objects.sort(key=lambda o: o.line_number)

        # Compute final order
        removed_from_here = moved_out_by_file.get(target_real, set())
        items = self._compute_target_file_order(target_moves, existing_objects, removed_from_here)

        # Read the current file content
        try:
            content = Path(target_path).read_text()
        except (IOError, OSError) as e:
            errors.append(f"Failed to read {target_path}: {e}")
            return 0

        # Rewrite the file
        write_error = self._rewrite_target_file(target_path, items, content)
        if write_error:
            errors.append(write_error)
            return 0

        # Record details for audit log
        for move in target_moves:
            count += 1
            name_field = NAME_FIELDS.get(move['obj_type'])
            obj_name = move['attrs'].get(name_field, '') if name_field else ''
            details.append({
                'object_type': move['obj_type'],
                'object_name': obj_name,
                'from_file': move['source_file'],
                'to_file': move['target_file']
            })

        return count

    def apply_object_moves(self, staging_data: dict) -> OperationResult:
        """Move staged objects by computing final file order and rewriting atomically.

        Instead of processing moves one-by-one with fragile line-number adjustments,
        this computes the desired final order for each target file (mirroring the
        frontend's virtual tree) and rewrites it in one pass.
        """
        if self._op_logger:
            self._op_logger.debug('service', 'apply_object_moves', result='started')
        staged_moves = staging_data.get('stagedMoves', [])
        count = 0
        errors = []
        details = []

        if not staged_moves:
            self._log_apply_result('apply_object_moves', count, errors)
            return OperationResult(True, data={'count': count, 'errors': errors, 'details': details})

        # Normalize all moves
        moves = self._normalize_staged_moves(staged_moves)
        if not moves:
            self._log_apply_result('apply_object_moves', count, errors)
            return OperationResult(True, data={'count': count, 'errors': errors, 'details': details})

        # Group moves by target file and compute what's being moved out
        by_target = self._group_moves_by_target(moves)
        all_target_reals = set(by_target.keys())
        moved_out_by_file = self._compute_moved_out_by_file(moves)
        p = self.parser

        # Process each target file: compute desired order and rewrite
        for target_real, target_moves in by_target.items():
            file_count = self._process_target_file_moves(
                target_real, target_moves, moved_out_by_file,
                p.objects, errors, details
            )
            count += file_count

        # Delete moved-out objects from source-only files (files not rewritten above)
        from collections import defaultdict
        source_only_removals = defaultdict(list)
        for move in moves:
            source_real = os.path.realpath(move['source_file'])
            target_real = os.path.realpath(move['target_file'])
            if source_real != target_real and source_real not in all_target_reals:
                source_only_removals[source_real].append(move)

        self._cleanup_source_only_files(source_only_removals, errors)

        # Final parser reload
        self._parser = NagiosConfigParser(self._config_path)
        self._parser.parse_all()

        self._log_apply_result('apply_object_moves', count, errors)
        return OperationResult(True, data={'count': count, 'errors': errors, 'details': details})

    def apply_object_edits(self, staging_data: dict) -> OperationResult:
        """Edit staged objects."""
        if self._op_logger:
            self._op_logger.debug('service', 'apply_object_edits', result='started')
        pending_edits = staging_data.get('pendingEdits', [])
        count = 0
        errors = []
        details = []

        if pending_edits:
            p = self.parser
            for edit_entry in _iterate_entries(pending_edits):
                edit_data = _ensure_dict_format(edit_entry)
                global_index = edit_data.get('globalIndex')

                edited_attrs = edit_data.get('edited', {})
                if not edited_attrs:
                    continue

                obj_info = edit_data.get('object', {})
                target_obj = None

                if obj_info.get('source_file') and obj_info.get('line_number'):
                    for obj in p.objects:
                        if (obj.source_file == obj_info['source_file'] and
                            obj.line_number == obj_info['line_number']):
                            target_obj = obj
                            break

                if not target_obj and global_index is not None and 0 <= global_index < len(p.objects):
                    target_obj = p.objects[global_index]

                if target_obj:
                    old_attrs = dict(target_obj.attributes)
                    merged_attrs = dict(target_obj.attributes)
                    merged_attrs.update(edited_attrs)
                    result = self.update_object(target_obj.source_file, target_obj.line_number,
                                                merged_attrs, target_obj.object_type)
                    if result.success:
                        count += 1
                        changes = []
                        for key, new_val in edited_attrs.items():
                            old_val = old_attrs.get(key)
                            if old_val is None:
                                changes.append({'type': 'add', 'key': key, 'value': new_val})
                            elif old_val != new_val:
                                changes.append({'type': 'modify', 'key': key, 'from': old_val, 'to': new_val})
                        name_field = NAME_FIELDS.get(target_obj.object_type)
                        obj_name = old_attrs.get(name_field, '') if name_field else ''
                        # C-11: Include both old and new names when name changes for audit trail
                        detail_entry = {
                            'object_type': target_obj.object_type,
                            'object_name': obj_name,
                            'changes': changes
                        }
                        # Check if name field was changed and record new name
                        if name_field and name_field in edited_attrs:
                            new_name = edited_attrs.get(name_field)
                            if new_name and new_name != obj_name:
                                detail_entry['renamed_to'] = new_name
                        details.append(detail_entry)
                        p = self.parser
                    elif result.error:
                        errors.append(f"Failed to edit object: {result.error}")

        self._log_apply_result('apply_object_edits', count, errors)
        return OperationResult(True, data={'count': count, 'errors': errors, 'details': details})

    def apply_object_creations(self, staging_data: dict) -> OperationResult:
        """Create staged objects."""
        if self._op_logger:
            self._op_logger.debug('service', 'apply_object_creations', result='started')
        staged_creations = staging_data.get('stagedCreations', [])
        count = 0
        errors = []
        details = []

        if staged_creations:
            for creation in staged_creations:
                object_type = creation.get('object_type')
                attributes = creation.get('attributes', {})
                target_file = creation.get('targetFile')

                if object_type and target_file:
                    if not os.path.isabs(target_file):
                        target_file = os.path.join(self._config_path, target_file)

                    result = self.create_object(target_file, object_type, attributes)
                    if result.success:
                        count += 1
                        name_field = NAME_FIELDS.get(object_type)
                        obj_name = attributes.get(name_field, '') if name_field else ''
                        details.append({
                            'object_type': object_type,
                            'object_name': obj_name,
                            'file': target_file
                        })
                    elif result.error:
                        errors.append(f"Failed to create object: {result.error}")

        self._log_apply_result('apply_object_creations', count, errors)
        return OperationResult(True, data={'count': count, 'errors': errors, 'details': details})

    def apply_file_moves(self, staging_data: dict, is_safe_path_func) -> OperationResult:
        """Move staged files."""
        if self._op_logger:
            self._op_logger.debug('service', 'apply_file_moves', result='started')
        file_moves = staging_data.get('stagedFileMoves', [])
        count = 0
        errors = []
        details = []

        for op in file_moves:
            source_path = op.get('sourcePath')
            target_path = op.get('targetPath')
            if source_path and target_path:
                safe_src, err_src = is_safe_path_func(source_path, self._config_path)
                safe_tgt, err_tgt = is_safe_path_func(target_path, self._config_path)
                if not safe_src:
                    errors.append(f"Unsafe source path {source_path}: {err_src}")
                    continue
                if not safe_tgt:
                    errors.append(f"Unsafe target path {target_path}: {err_tgt}")
                    continue
                try:
                    target_dir = os.path.dirname(target_path)
                    if target_dir:
                        os.makedirs(target_dir, exist_ok=True)
                    if os.path.exists(source_path):
                        shutil.move(source_path, target_path)
                        count += 1
                        details.append({'from': source_path, 'to': target_path})
                except Exception as e:
                    errors.append(f"Failed to move file {source_path}: {e}")

        self._log_apply_result('apply_file_moves', count, errors)
        return OperationResult(True, data={'count': count, 'errors': errors, 'details': details})

    def apply_folder_moves(self, staging_data: dict, is_safe_path_func) -> OperationResult:
        """Move staged folders."""
        if self._op_logger:
            self._op_logger.debug('service', 'apply_folder_moves', result='started')
        folder_moves = staging_data.get('stagedFolderMoves', [])
        count = 0
        errors = []
        details = []

        for op in folder_moves:
            source_path = op.get('sourcePath')
            target_path = op.get('targetPath')
            if source_path and target_path:
                safe_src, err_src = is_safe_path_func(source_path, self._config_path)
                safe_tgt, err_tgt = is_safe_path_func(target_path, self._config_path)
                if not safe_src:
                    errors.append(f"Unsafe source path {source_path}: {err_src}")
                    continue
                if not safe_tgt:
                    errors.append(f"Unsafe target path {target_path}: {err_tgt}")
                    continue
                try:
                    target_parent = os.path.dirname(target_path)
                    if target_parent:
                        os.makedirs(target_parent, exist_ok=True)
                    if os.path.isdir(source_path):
                        shutil.move(source_path, target_path)
                        count += 1
                        details.append({'from': source_path, 'to': target_path})
                except Exception as e:
                    errors.append(f"Failed to move folder {source_path}: {e}")

        self._log_apply_result('apply_folder_moves', count, errors)
        return OperationResult(True, data={'count': count, 'errors': errors, 'details': details})

    def apply_file_deletions(self, staging_data: dict, is_safe_path_func) -> OperationResult:
        """Delete staged files."""
        if self._op_logger:
            self._op_logger.debug('service', 'apply_file_deletions', result='started')
        file_deletions = staging_data.get('stagedFileDeletions', [])
        count = 0
        errors = []
        details = []

        for op in file_deletions:
            file_path = op.get('path')
            if file_path and os.path.isfile(file_path):
                safe, err = is_safe_path_func(file_path, self._config_path)
                if not safe:
                    errors.append(f"Unsafe file path {file_path}: {err}")
                    continue
                try:
                    os.remove(file_path)
                    count += 1
                    details.append({'path': file_path, 'type': 'file'})
                except Exception as e:
                    errors.append(f"Failed to delete file {file_path}: {e}")

        self._log_apply_result('apply_file_deletions', count, errors)
        return OperationResult(True, data={'count': count, 'errors': errors, 'details': details})

    def apply_folder_deletions(self, staging_data: dict, is_safe_path_func) -> OperationResult:
        """Delete staged folders."""
        if self._op_logger:
            self._op_logger.debug('service', 'apply_folder_deletions', result='started')
        folder_deletions = staging_data.get('stagedFolderDeletions', [])
        folder_deletions.sort(key=lambda x: -x.get('path', '').count('/'))
        count = 0
        errors = []
        details = []

        for op in folder_deletions:
            folder_path = op.get('path')
            if folder_path and os.path.isdir(folder_path):
                safe, err = is_safe_path_func(folder_path, self._config_path)
                if not safe:
                    errors.append(f"Unsafe folder path {folder_path}: {err}")
                    continue
                try:
                    shutil.rmtree(folder_path)
                    count += 1
                    details.append({'path': folder_path, 'type': 'folder'})
                except Exception as e:
                    errors.append(f"Failed to delete folder {folder_path}: {e}")

        self._log_apply_result('apply_folder_deletions', count, errors)
        return OperationResult(True, data={'count': count, 'errors': errors, 'details': details})
