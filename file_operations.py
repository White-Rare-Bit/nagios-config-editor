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

    # Find character position of target line
    char_pos = sum(len(lines[i]) + 1 for i in range(target_line - 1))

    # Check if 'define' is at the start of this line
    line_content = lines[target_line - 1] if target_line <= len(lines) else ''
    define_on_line = line_content.strip().startswith('define')

    if define_on_line:
        # Find 'define' on this line
        define_pos = content.find('define', char_pos)
        if define_pos >= 0:
            define_line = content[:define_pos].count('\n') + 1
            if define_line != target_line:
                define_pos = -1
    else:
        # Search backward for the containing block
        define_pos = content.rfind('define', 0, char_pos)

    if define_pos < 0:
        # Last resort: search forward
        define_pos = content.find('define', char_pos)
        if define_pos < 0:
            return None

    # Verify this looks like a define block
    remaining = content[define_pos:]
    match = re.match(r'define\s+\w+\s*\{', remaining)
    if not match:
        return None

    # Find opening brace
    brace_open = define_pos + remaining.index('{')

    # Find matching closing brace, respecting quotes
    brace_count = 1
    pos = brace_open + 1
    in_double_quote = False
    in_single_quote = False
    while pos < len(content) and brace_count > 0:
        char = content[pos]
        prev_char = content[pos - 1] if pos > 0 else ''

        # Handle escape sequences
        if prev_char == '\\':
            pos += 1
            continue

        # Track quote state
        if char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
        elif char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        # Only count braces outside quotes
        elif not in_double_quote and not in_single_quote:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
        pos += 1

    if brace_count != 0:
        return None

    return (define_pos, pos)


def find_block_line_range(content: str, target_line: int) -> Optional[Tuple[int, int]]:
    """Find the line range (1-based, inclusive) of a define block.

    Args:
        content: The file content
        target_line: 1-based line number pointing to or within the block

    Returns:
        Tuple of (start_line, end_line) or None if not found
    """
    char_range = find_block_range(content, target_line)
    if not char_range:
        return None

    start_char, end_char = char_range
    start_line = content[:start_char].count('\n') + 1
    end_line = content[:end_char].count('\n') + 1

    return (start_line, end_line)


def edit_object_in_file(file_path: str, line_number: int, new_attrs: Dict[str, str],
                        obj_type: str) -> OperationResult:
    """Edit an object in place in its file."""
    if _op_logger:
        _op_logger.debug('file_op', 'edit_object_in_file', params={'file_path': file_path, 'line_number': line_number, 'obj_type': obj_type})
    path = Path(file_path)
    if not path.exists():
        return OperationResult(False, f"File not found: {file_path}")

    try:
        content = path.read_text()
    except (IOError, OSError) as e:
        return OperationResult(False, f"Read error: {e}")

    block_range = find_block_range(content, line_number)
    if not block_range:
        return OperationResult(False, f"Could not find define block at line {line_number} in {file_path}")

    start_char, end_char = block_range
    new_block = format_object_block(obj_type, new_attrs)
    new_content = content[:start_char] + new_block + content[end_char:]

    try:
        path.write_text(new_content)
    except (IOError, OSError) as e:
        return OperationResult(False, f"Write error: {e}")

    return OperationResult(True)


def delete_object_from_file(file_path: str, line_number: int) -> OperationResult:
    """Delete an object from its file."""
    if _op_logger:
        _op_logger.debug('file_op', 'delete_object_from_file', params={'file_path': file_path, 'line_number': line_number})
    path = Path(file_path)
    if not path.exists():
        return OperationResult(False, f"File not found: {file_path}")

    try:
        content = path.read_text()
    except (IOError, OSError) as e:
        return OperationResult(False, f"Read error: {e}")

    block_range = find_block_range(content, line_number)
    if not block_range:
        return OperationResult(False, f"Could not find define block at line {line_number} in {file_path}")

    start_char, end_char = block_range

    before = content[:start_char].rstrip('\n')
    after = content[end_char:].lstrip('\n')

    if before and after:
        new_content = before + '\n\n' + after
    elif before:
        new_content = before + '\n'
    elif after:
        new_content = after
    else:
        new_content = ''

    try:
        path.write_text(new_content)
    except (IOError, OSError) as e:
        return OperationResult(False, f"Write error: {e}")

    return OperationResult(True)


def add_object_to_file(file_path: str, obj_type: str, attrs: Dict[str, str],
                       after_block_line: Optional[int] = None) -> OperationResult:
    """Add a new object to a file, inserting after a specific block."""
    if _op_logger:
        _op_logger.debug('file_op', 'add_object_to_file', params={'file_path': file_path, 'obj_type': obj_type})
    path = Path(file_path)
    new_block = format_object_block(obj_type, attrs)

    if not path.exists():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(new_block + '\n')
            return OperationResult(True)
        except (IOError, OSError) as e:
            return OperationResult(False, f"Failed to create file {file_path}: {e}")

    try:
        content = path.read_text()
    except (IOError, OSError) as e:
        return OperationResult(False, f"Read error: {e}")

    if after_block_line == 0:
        after = content.lstrip('\n')
        if after:
            new_content = new_block + '\n\n' + after
        else:
            new_content = new_block + '\n'
    elif after_block_line is not None and after_block_line > 0:
        block_range = find_block_range(content, after_block_line)

        if block_range:
            start_char, end_char = block_range
            before = content[:end_char]
            after = content[end_char:]

            before = before.rstrip('\n')
            after = after.lstrip('\n')

            if after:
                new_content = before + '\n\n' + new_block + '\n\n' + after
            else:
                new_content = before + '\n\n' + new_block + '\n'
        else:
            content = content.rstrip('\n')
            if content:
                new_content = content + '\n\n' + new_block + '\n'
            else:
                new_content = new_block + '\n'
    else:
        content = content.rstrip('\n')
        if content:
            new_content = content + '\n\n' + new_block + '\n'
        else:
            new_content = new_block + '\n'

    try:
        path.write_text(new_content)
    except (IOError, OSError) as e:
        return OperationResult(False, f"Write error: {e}")

    return OperationResult(True)


def move_object_between_files(source_file: str, source_line: int,
                              target_file: str, obj_type: str, attrs: Dict[str, str],
                              insert_line: Optional[int] = None) -> OperationResult:
    """Move an object from one file to another."""
    if _op_logger:
        _op_logger.debug('file_op', 'move_object_between_files', params={'source_file': source_file, 'target_file': target_file, 'obj_type': obj_type})

    source_real = os.path.realpath(source_file)
    target_real = os.path.realpath(target_file)

    if source_real == target_real:
        # Same file reorder - delete first, then add
        try:
            content = Path(source_file).read_text()
        except (IOError, OSError) as e:
            return OperationResult(False, f"Read error on source: {e}")

        source_line_range = find_block_line_range(content, source_line)
        if not source_line_range:
            return OperationResult(False, f"Could not find source block at line {source_line}")

        source_start, source_end = source_line_range

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
            new_total_lines = len(new_content.split('\n'))
            old_total_lines = len(content.split('\n'))
            actual_shift = old_total_lines - new_total_lines
            adjusted_insert_line = insert_line - actual_shift
            if adjusted_insert_line < 1:
                adjusted_insert_line = None

        add_result = add_object_to_file(target_file, obj_type, attrs, adjusted_insert_line)
        if not add_result.success:
            # Try to re-add at original position (best effort recovery)
            add_object_to_file(source_file, obj_type, attrs, source_line)
            return OperationResult(False, f"Failed to re-add after delete: {add_result.error}")
    else:
        # Different files - add first to prevent data loss
        add_result = add_object_to_file(target_file, obj_type, attrs, insert_line)
        if not add_result.success:
            return add_result

        # Delete from source
        del_result = delete_object_from_file(source_file, source_line)
        if not del_result.success:
            # Rollback: remove the object we just added to target
            try:
                target_content = Path(target_file).read_text()
                target_block = format_object_block(obj_type, attrs)
                if target_block in target_content:
                    rollback_content = target_content.replace(target_block, '', 1)
                    rollback_content = re.sub(r'\n{3,}', '\n\n', rollback_content)
                    Path(target_file).write_text(rollback_content)
            except (IOError, OSError):
                pass
            return OperationResult(False, f"Failed to delete from source after add: {del_result.error}")

    return OperationResult(True)


def is_safe_path(path: str, base_dir: Optional[str] = None) -> tuple[bool, str]:
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
        Tuple of (is_safe, error_message). If safe, error_message is empty.
    """
    if base_dir is None:
        return False, "base_dir parameter is required"

    # Check for null bytes
    if '\x00' in path:
        return False, "Path contains null bytes"

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
            return False, "Path must be within config directory"
    except ValueError:
        # Different drives on Windows
        return False, "Path must be within config directory"

    return True, ""


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
