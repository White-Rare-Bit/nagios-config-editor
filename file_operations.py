"""
File Operations for Direct Editing

Provides atomic file operations for editing, creating, deleting, and moving
Nagios configuration objects directly in files (no shadow copies).
"""

import os
import re
import difflib
from pathlib import Path
from typing import Dict, Tuple, Optional, List
from nagios_model import format_object_block, OperationResult

# Module-level operation logger (set via set_logger)
_op_logger = None


def set_logger(logger):
    """Set the module-level operation logger."""
    global _op_logger
    _op_logger = logger


def _compute_checksum(content: str) -> str:
    """Compute SHA256 checksum of content string."""
    import hashlib
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def _atomic_write(file_path: str, content: str) -> None:
    """Write content to file atomically using temp file + rename.

    Creates a temp file in the same directory, writes content, then
    renames to target path. This ensures the file is never in a
    partially-written state.
    """
    import tempfile
    dir_name = os.path.dirname(os.path.abspath(file_path))
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, file_path)
    except:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _read_file_content(file_path: str, expected_checksum: Optional[str] = None) -> OperationResult:
    """Read file content with standard error handling and optional checksum validation.

    Args:
        file_path: Path to the file to read
        expected_checksum: If provided, validates file hasn't changed since staging began.
                          Returns conflict error if checksum doesn't match.

    Returns:
        OperationResult with success=True and data=content on success,
        or success=False with error details on failure
    """
    path = Path(file_path)
    if not path.exists():
        return OperationResult(False, f"File not found: {file_path}")
    try:
        content = path.read_text()
        if expected_checksum is not None:
            actual_checksum = _compute_checksum(content)
            if actual_checksum != expected_checksum:
                return OperationResult(False,
                    f"Conflict: {file_path} was modified externally. Aborting to prevent data loss.")
        return OperationResult(True, data=content)
    except (IOError, OSError) as e:
        return OperationResult(False, f"Read error: {e}")


def _normalize_block_spacing(before: str, middle: str, after: str) -> str:
    """Join content sections with normalized spacing between define blocks.

    Rules:
    - 2 blank lines between blocks
    - 1 trailing newline at EOF
    - Strip excess whitespace from section boundaries

    Args:
        before: Content before the insertion/deletion point
        middle: New block content (empty string for deletions)
        after: Content after the insertion/deletion point

    Returns:
        Normalized content with proper spacing
    """
    before = before.rstrip('\n')
    after = after.lstrip('\n')
    parts = [s for s in (before, middle, after) if s]
    if not parts:
        return ''
    result = '\n\n'.join(parts)
    # Add trailing newline when content ends with our sections (not raw after content)
    if before or middle:
        if not after:
            result += '\n'
    return result


def _find_matching_brace(content: str, brace_open: int) -> Optional[int]:
    """Find the position after the matching closing brace, respecting quotes.

    Args:
        content: Full file content
        brace_open: Position of the opening brace

    Returns:
        Position after closing brace, or None if unmatched
    """
    brace_count = 1
    pos = brace_open + 1
    in_double_quote = False
    in_single_quote = False
    while pos < len(content) and brace_count > 0:
        char = content[pos]
        prev_char = content[pos - 1] if pos > 0 else ''

        if prev_char == '\\':
            pos += 1
            continue

        if char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
        elif char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif not in_double_quote and not in_single_quote:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
        pos += 1

    return pos if brace_count == 0 else None


def _locate_define_pos(content: str, char_pos: int, target_line: int, lines: list) -> int:
    """Locate the character position of the 'define' keyword for a block.

    Tries: exact line match, backward search, then forward search.

    Args:
        content: Full file content
        char_pos: Character position of target_line start
        target_line: 1-based target line number
        lines: Pre-split lines of content

    Returns:
        Character position of 'define', or -1 if not found
    """
    line_content = lines[target_line - 1] if target_line <= len(lines) else ''
    define_on_line = line_content.strip().startswith('define')

    if define_on_line:
        define_pos = content.find('define', char_pos)
        if define_pos >= 0:
            define_line = content[:define_pos].count('\n') + 1
            if define_line != target_line:
                define_pos = -1
        if define_pos >= 0:
            return define_pos
    else:
        define_pos = content.rfind('define', 0, char_pos)
        if define_pos >= 0:
            return define_pos

    # Last resort: search forward
    return content.find('define', char_pos)


def find_block_range(content: str, target_line: int) -> Optional[Tuple[int, int]]:
    """Find the character range of a define block at or containing target_line.

    Args:
        content: The file content
        target_line: 1-based line number pointing to or within the block

    Returns:
        Tuple of (start_char, end_char) or None if not found
    """
    lines = content.split('\n')
    if target_line < 1 or target_line > len(lines):
        return None

    char_pos = sum(len(lines[i]) + 1 for i in range(target_line - 1))
    define_pos = _locate_define_pos(content, char_pos, target_line, lines)
    if define_pos < 0:
        return None

    remaining = content[define_pos:]
    match = re.match(r'define\s+\w+\s*\{', remaining)
    if not match:
        return None

    brace_open = define_pos + remaining.index('{')
    end_pos = _find_matching_brace(content, brace_open)
    if end_pos is None:
        return None

    return (define_pos, end_pos)


def edit_object_in_file(file_path: str, line_number: int, new_attrs: Dict[str, str],
                        obj_type: str, expected_checksum: Optional[str] = None) -> OperationResult:
    """Edit an object in place in its file.

    Args:
        file_path: Path to the file containing the object
        line_number: Line number of the object to edit
        new_attrs: New attributes for the object
        obj_type: Type of the object (e.g., 'host', 'service')
        expected_checksum: If provided, validates file hasn't changed since staging began.
                          Returns conflict error if checksum doesn't match.

    Returns:
        OperationResult with success=True on success, or error details on failure
    """
    if _op_logger:
        _op_logger.debug('file_op', 'edit_object_in_file', params={'file_path': file_path, 'line_number': line_number, 'obj_type': obj_type})

    read_result = _read_file_content(file_path, expected_checksum)
    if not read_result.success:
        return read_result
    content = read_result.data

    block_range = find_block_range(content, line_number)
    if not block_range:
        return OperationResult(False, f"Could not find define block at line {line_number} in {file_path}")

    start_char, end_char = block_range
    new_block = format_object_block(obj_type, new_attrs)
    new_content = content[:start_char] + new_block + content[end_char:]

    try:
        _atomic_write(file_path, new_content)
    except (IOError, OSError) as e:
        return OperationResult(False, f"Write error: {e}")

    return OperationResult(True)


def delete_object_from_file(file_path: str, line_number: int,
                            expected_checksum: Optional[str] = None) -> OperationResult:
    """Delete an object from its file.

    Args:
        file_path: Path to the file containing the object
        line_number: Line number of the object to delete
        expected_checksum: If provided, validates file hasn't changed since staging began.
                          Returns conflict error if checksum doesn't match.

    Returns:
        OperationResult with success=True on success, or error details on failure
    """
    if _op_logger:
        _op_logger.debug('file_op', 'delete_object_from_file', params={'file_path': file_path, 'line_number': line_number})

    read_result = _read_file_content(file_path, expected_checksum)
    if not read_result.success:
        return read_result
    content = read_result.data

    block_range = find_block_range(content, line_number)
    if not block_range:
        return OperationResult(False, f"Could not find define block at line {line_number} in {file_path}")

    start_char, end_char = block_range
    new_content = _normalize_block_spacing(content[:start_char], '', content[end_char:])

    try:
        _atomic_write(file_path, new_content)
    except (IOError, OSError) as e:
        return OperationResult(False, f"Write error: {e}")

    return OperationResult(True)


def add_object_to_file(file_path: str, obj_type: str, attrs: Dict[str, str],
                       after_block_line: Optional[int] = None,
                       expected_checksum: Optional[str] = None,
                       raw_block: Optional[str] = None) -> OperationResult:
    """Add a new object to a file, inserting after a specific block.

    Args:
        file_path: Path to the file to add the object to
        obj_type: Type of the object (e.g., 'host', 'service')
        attrs: Attributes for the new object
        after_block_line: Line number of the block to insert after (0 = beginning, None = end)
        expected_checksum: If provided, validates file hasn't changed since staging began.
                          Returns conflict error if checksum doesn't match.
                          Only applies to existing files.
        raw_block: If provided, use this exact block text instead of formatting from attrs.
                   This preserves original formatting, indentation, and inline comments.

    Returns:
        OperationResult with success=True on success, or error details on failure
    """
    if _op_logger:
        _op_logger.debug('file_op', 'add_object_to_file', params={'file_path': file_path, 'obj_type': obj_type})
    path = Path(file_path)
    new_block = raw_block if raw_block else format_object_block(obj_type, attrs)

    if not path.exists():
        # New file - no checksum validation needed
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(file_path, new_block + '\n')
            return OperationResult(True)
        except (IOError, OSError) as e:
            return OperationResult(False, f"Failed to create file {file_path}: {e}")

    read_result = _read_file_content(file_path, expected_checksum)
    if not read_result.success:
        return read_result
    content = read_result.data

    if after_block_line == 0:
        # Insert at beginning
        new_content = _normalize_block_spacing('', new_block, content)
    elif after_block_line is not None and after_block_line > 0:
        block_range = find_block_range(content, after_block_line)

        if block_range:
            start_char, end_char = block_range
            before = content[:end_char]
            after = content[end_char:]
            # Insert after the found block
            new_content = _normalize_block_spacing(before, new_block, after)
        else:
            # Block not found, append to end
            new_content = _normalize_block_spacing(content, new_block, '')
    else:
        # Append to end
        new_content = _normalize_block_spacing(content, new_block, '')

    try:
        _atomic_write(file_path, new_content)
    except (IOError, OSError) as e:
        return OperationResult(False, f"Write error: {e}")

    return OperationResult(True)


def _move_same_file(source_file: str, source_line: int, source_content: str,
                    start_char: int, raw_block: str, obj_type: str,
                    attrs: Dict[str, str], insert_line: Optional[int]) -> OperationResult:
    """Handle same-file reorder: delete first, then re-add at new position.

    Args:
        source_file: Path to the file
        source_line: Line number of object to move
        source_content: Original file content (for line shift calculation)
        start_char: Character position of block start
        raw_block: Raw block text to preserve formatting
        obj_type: Object type
        attrs: Object attributes (fallback)
        insert_line: Target insert position

    Returns:
        OperationResult
    """
    source_start = source_content[:start_char].count('\n') + 1

    del_result = delete_object_from_file(source_file, source_line)
    if not del_result.success:
        return del_result

    # Recalculate insert position after deletion
    adjusted_insert_line = insert_line
    if insert_line is not None and insert_line > source_start:
        try:
            new_content = Path(source_file).read_text()
        except (IOError, OSError) as e:
            return OperationResult(False, f"Read error after delete: {e}")
        actual_shift = len(source_content.split('\n')) - len(new_content.split('\n'))
        adjusted_insert_line = insert_line - actual_shift
        if adjusted_insert_line < 1:
            adjusted_insert_line = None

    add_result = add_object_to_file(source_file, obj_type, attrs, adjusted_insert_line, raw_block=raw_block)
    if not add_result.success:
        add_object_to_file(source_file, obj_type, attrs, source_line, raw_block=raw_block)
        return OperationResult(False, f"Failed to re-add after delete: {add_result.error}")

    return OperationResult(True)


def _rollback_target_add(target_file: str, raw_block: str, del_error: str) -> OperationResult:
    """Roll back a failed move by removing the block added to target.

    Args:
        target_file: File where block was added
        raw_block: Block text to remove
        del_error: Original deletion error message

    Returns:
        OperationResult with appropriate error message
    """
    try:
        target_content = Path(target_file).read_text()
        if raw_block in target_content:
            rollback_content = target_content.replace(raw_block, '', 1)
            rollback_content = re.sub(r'\n{3,}', '\n\n', rollback_content)
            _atomic_write(target_file, rollback_content)
        if _op_logger:
            _op_logger.info('file_op', 'move_rollback',
                           params={'target': target_file}, result='success')
        return OperationResult(False, f"Failed to delete from source after add: {del_error}")
    except (IOError, OSError) as e:
        if _op_logger:
            _op_logger.error('file_op', 'move_rollback',
                            params={'target': target_file}, error=str(e))
        return OperationResult(False,
            f"Failed to delete from source: {del_error}. "
            f"CRITICAL: Rollback failed, object may be duplicated in both files: {e}")


def move_object_between_files(source_file: str, source_line: int,
                              target_file: str, obj_type: str, attrs: Dict[str, str],
                              insert_line: Optional[int] = None) -> OperationResult:
    """Move an object from one file to another, preserving original formatting.

    This uses surgical operations: extract block from source, delete from source,
    insert into target. Comments and formatting in both files are preserved.

    Args:
        source_file: Path to the file containing the object
        source_line: Line number of the object to move
        target_file: Path to the destination file
        obj_type: Type of the object (e.g., 'host', 'service')
        attrs: Attributes of the object (used as fallback if block extraction fails)
        insert_line: Line number to insert after in target (None = end of file)

    Returns:
        OperationResult with success=True on success, or error details on failure
    """
    if _op_logger:
        _op_logger.debug('file_op', 'move_object_between_files',
                        params={'source_file': source_file, 'target_file': target_file, 'obj_type': obj_type})

    try:
        source_content = Path(source_file).read_text()
    except (IOError, OSError) as e:
        return OperationResult(False, f"Read error on source: {e}")

    block_range = find_block_range(source_content, source_line)
    if not block_range:
        return OperationResult(False, f"Could not find source block at line {source_line}")

    start_char, end_char = block_range
    raw_block = source_content[start_char:end_char].strip()

    if os.path.realpath(source_file) == os.path.realpath(target_file):
        return _move_same_file(source_file, source_line, source_content,
                               start_char, raw_block, obj_type, attrs, insert_line)

    # Different files - add first to prevent data loss
    add_result = add_object_to_file(target_file, obj_type, attrs, insert_line, raw_block=raw_block)
    if not add_result.success:
        return add_result

    del_result = delete_object_from_file(source_file, source_line)
    if not del_result.success:
        return _rollback_target_add(target_file, raw_block, del_result.error)

    return OperationResult(True)


def is_safe_path(path: str, base_dir: Optional[str] = None) -> OperationResult:
    """
    Validate that a path is safe and within the allowed directory.

    Security checks performed:
    - Null byte injection
    - Path traversal (../)
    - Symlink traversal (for paths pointing outside config directory)
    - Absolute path escaping

    Args:
        path: The path to validate
        base_dir: The base directory paths must be within (required when called from file_operations)

    Returns:
        OperationResult with success=True if safe, success=False with error if unsafe.
    """
    if base_dir is None:
        return OperationResult(False, "base_dir parameter is required")

    # Check for null bytes
    if '\x00' in path:
        return OperationResult(False, "Path contains null bytes")

    # Resolve the base directory to handle symlinked config directories (e.g., /tmp -> /private/tmp)
    base_dir_resolved = os.path.realpath(os.path.abspath(os.path.normpath(base_dir)))

    # Normalize the path
    normalized = os.path.normpath(path)

    # If path is relative, join with base_dir
    if not os.path.isabs(normalized):
        normalized = os.path.normpath(os.path.join(base_dir_resolved, normalized))

    # Make sure the normalized path is absolute
    normalized = os.path.abspath(normalized)

    # Resolve any symlinks in the path for comparison
    # For non-existent paths, resolve what exists and check the rest
    resolved_normalized = normalized
    check_path = normalized
    while check_path and check_path != os.path.dirname(check_path):
        if os.path.exists(check_path):
            # Resolve symlinks for existing portion
            resolved_normalized = os.path.realpath(check_path)
            # Add back any non-existent suffix
            if check_path != normalized:
                suffix = normalized[len(check_path):]
                resolved_normalized = os.path.normpath(resolved_normalized + suffix)
            break
        check_path = os.path.dirname(check_path)

    # Check if resolved path is within resolved base directory
    try:
        common = os.path.commonpath([base_dir_resolved, resolved_normalized])
        if common != base_dir_resolved:
            return OperationResult(False, "Path must be within config directory")
    except ValueError:
        # Different drives on Windows
        return OperationResult(False, "Path must be within config directory")

    return OperationResult(True)


def generate_diff(old_content: str, new_content: str, filename: str = '') -> List[str]:
    """Generate a unified diff between two strings."""
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f'a/{filename}' if filename else 'before',
        tofile=f'b/{filename}' if filename else 'after'
    )
    return list(diff)
