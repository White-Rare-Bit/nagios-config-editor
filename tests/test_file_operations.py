"""
Tests for file_operations.py - File Operations for Direct Editing
"""

import pytest
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from file_operations import (
    find_block_range,
    find_block_line_range,
    edit_object_in_file,
    delete_object_from_file,
    add_object_to_file,
    move_object_between_files,
    is_safe_path,
    generate_diff
)
from nagios_model import OperationResult


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary config directory for testing."""
    config_dir = tmp_path / "nagios"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def sample_config_file(temp_config_dir):
    """Create a sample config file with multiple blocks."""
    config_file = temp_config_dir / "test.cfg"
    content = """define host {
    host_name               server1
    alias                   Test Server 1
    address                 192.168.1.1
}

define host {
    host_name               server2
    alias                   Test Server 2
    address                 192.168.1.2
}

define service {
    host_name               server1
    service_description     HTTP
    check_command           check_http
}
"""
    config_file.write_text(content)
    return str(config_file)


class TestFindBlockRange:
    """Tests for find_block_range function."""

    def test_normal_block_finding(self):
        """Test finding a normal define block."""
        content = """define host {
    host_name    server1
    address      192.168.1.1
}
"""
        char_range = find_block_range(content, 1)
        assert char_range is not None
        start, end = char_range
        assert content[start:end] == content.strip()

    def test_nested_braces_in_quoted_strings(self):
        """Test that braces in quoted strings are ignored."""
        content = """define command {
    command_name    test_command
    command_line    echo "value with {braces}"
}
"""
        char_range = find_block_range(content, 1)
        assert char_range is not None
        start, end = char_range
        extracted = content[start:end]
        assert 'define command' in extracted
        assert extracted.endswith('}')

    def test_block_at_beginning_of_file(self):
        """Test finding block at the very beginning of file."""
        content = """define host {
    host_name    server1
}

define service {
    service_description    HTTP
}
"""
        char_range = find_block_range(content, 1)
        assert char_range is not None
        start, end = char_range
        assert start == 0
        assert 'define host' in content[start:end]

    def test_block_at_end_of_file(self):
        """Test finding block at the end of file."""
        content = """define host {
    host_name    server1
}

define service {
    service_description    HTTP
}"""
        lines = content.split('\n')
        last_define_line = None
        for i, line in enumerate(lines, 1):
            if 'define service' in line:
                last_define_line = i

        char_range = find_block_range(content, last_define_line)
        assert char_range is not None
        start, end = char_range
        assert 'define service' in content[start:end]
        assert end == len(content)

    def test_non_existent_line_numbers(self):
        """Test with invalid line numbers."""
        content = """define host {
    host_name    server1
}
"""
        assert find_block_range(content, 0) is None
        assert find_block_range(content, 999) is None

    def test_multiple_blocks_in_file(self):
        """Test finding different blocks in a multi-block file."""
        content = """define host {
    host_name    server1
}

define host {
    host_name    server2
}

define service {
    service_description    HTTP
}
"""
        # Find first block
        range1 = find_block_range(content, 1)
        assert range1 is not None
        assert 'server1' in content[range1[0]:range1[1]]

        # Find second block
        range2 = find_block_range(content, 5)
        assert range2 is not None
        assert 'server2' in content[range2[0]:range2[1]]

        # Find third block
        range3 = find_block_range(content, 9)
        assert range3 is not None
        assert 'service_description' in content[range3[0]:range3[1]]

    def test_backward_search_from_within_block(self):
        """Test finding block when target line is inside the block."""
        content = """define host {
    host_name    server1
    address      192.168.1.1
    alias        Test Server
}
"""
        # Target line 3 (inside the block)
        char_range = find_block_range(content, 3)
        assert char_range is not None
        start, end = char_range
        assert 'define host' in content[start:end]
        assert 'server1' in content[start:end]
        assert 'Test Server' in content[start:end]

    def test_escaped_quotes(self):
        """Test handling of escaped quotes in strings."""
        content = """define command {
    command_name    test
    command_line    echo "value with \\"escaped\\" quotes"
}
"""
        char_range = find_block_range(content, 1)
        assert char_range is not None
        start, end = char_range
        assert content[start:end].endswith('}')

    def test_single_quotes(self):
        """Test handling of single quotes with braces."""
        content = """define command {
    command_name    test
    command_line    echo 'value with {braces}'
}
"""
        char_range = find_block_range(content, 1)
        assert char_range is not None
        start, end = char_range
        assert content[start:end].endswith('}')

    def test_unmatched_braces(self):
        """Test that unmatched braces return None."""
        content = """define host {
    host_name    server1
    address      192.168.1.1
"""
        char_range = find_block_range(content, 1)
        assert char_range is None

    def test_no_define_block(self):
        """Test content without define blocks."""
        content = """# Just a comment
# No define blocks here
"""
        char_range = find_block_range(content, 1)
        assert char_range is None


class TestFindBlockLineRange:
    """Tests for find_block_line_range function."""

    def test_returns_line_numbers(self):
        """Test that it returns line numbers instead of char positions."""
        content = """define host {
    host_name    server1
    address      192.168.1.1
}
"""
        line_range = find_block_line_range(content, 1)
        assert line_range is not None
        start_line, end_line = line_range
        assert start_line == 1
        assert end_line == 4

    def test_multi_block_file(self):
        """Test line ranges in multi-block file."""
        content = """define host {
    host_name    server1
}

define service {
    service_description    HTTP
}
"""
        # First block
        line_range1 = find_block_line_range(content, 1)
        assert line_range1 == (1, 3)

        # Second block
        line_range2 = find_block_line_range(content, 5)
        assert line_range2 == (5, 7)

    def test_invalid_target_line(self):
        """Test with invalid target line."""
        content = """define host {
    host_name    server1
}
"""
        assert find_block_line_range(content, 999) is None


class TestEditObjectInFile:
    """Tests for edit_object_in_file function."""

    def test_basic_edit(self, temp_config_dir):
        """Test basic editing of an object."""
        config_file = temp_config_dir / "test.cfg"
        content = """define host {
    host_name               server1
    alias                   Old Alias
    address                 192.168.1.1
}
"""
        config_file.write_text(content)

        result = edit_object_in_file(
            str(config_file),
            1,
            {'host_name': 'server1', 'alias': 'New Alias', 'address': '192.168.1.100'},
            'host'
        )

        assert result.success is True
        new_content = config_file.read_text()
        assert 'New Alias' in new_content
        assert '192.168.1.100' in new_content
        assert 'Old Alias' not in new_content

    def test_file_not_found(self):
        """Test editing non-existent file."""
        result = edit_object_in_file(
            '/nonexistent/file.cfg',
            1,
            {'host_name': 'server1'},
            'host'
        )
        assert result.success is False
        assert 'File not found' in result.error

    def test_block_not_found(self, temp_config_dir):
        """Test editing when block not found at given line."""
        config_file = temp_config_dir / "test.cfg"
        config_file.write_text("# Just a comment\n")

        result = edit_object_in_file(
            str(config_file),
            1,
            {'host_name': 'server1'},
            'host'
        )
        assert result.success is False
        assert 'Could not find define block' in result.error

    def test_edit_preserves_other_blocks(self, sample_config_file):
        """Test that editing one block doesn't affect others."""
        original_content = Path(sample_config_file).read_text()

        result = edit_object_in_file(
            sample_config_file,
            1,
            {'host_name': 'server1', 'alias': 'Modified', 'address': '192.168.1.1'},
            'host'
        )

        assert result.success is True
        new_content = Path(sample_config_file).read_text()
        assert 'Modified' in new_content
        assert 'server2' in new_content
        assert 'Test Server 2' in new_content


class TestDeleteObjectFromFile:
    """Tests for delete_object_from_file function."""

    def test_delete_single_object(self, temp_config_dir):
        """Test deleting the only object in a file."""
        config_file = temp_config_dir / "test.cfg"
        content = """define host {
    host_name               server1
    address                 192.168.1.1
}
"""
        config_file.write_text(content)

        result = delete_object_from_file(str(config_file), 1)
        assert result.success is True

        new_content = config_file.read_text()
        assert 'server1' not in new_content

    def test_delete_from_multi_object_file(self, sample_config_file):
        """Test deleting one object from a multi-object file."""
        original_content = Path(sample_config_file).read_text()

        result = delete_object_from_file(sample_config_file, 1)
        assert result.success is True

        new_content = Path(sample_config_file).read_text()
        assert 'Test Server 1' not in new_content
        assert '192.168.1.1' not in new_content
        assert 'server2' in new_content
        assert 'Test Server 2' in new_content
        assert 'HTTP' in new_content

    def test_delete_file_not_found(self):
        """Test deleting from non-existent file."""
        result = delete_object_from_file('/nonexistent/file.cfg', 1)
        assert result.success is False
        assert 'File not found' in result.error

    def test_delete_block_not_found(self, temp_config_dir):
        """Test deleting when block not found."""
        config_file = temp_config_dir / "test.cfg"
        config_file.write_text("# Just a comment\n")

        result = delete_object_from_file(str(config_file), 1)
        assert result.success is False
        assert 'Could not find define block' in result.error

    def test_delete_middle_object(self, temp_config_dir):
        """Test deleting middle object preserves proper spacing."""
        config_file = temp_config_dir / "test.cfg"
        content = """define host {
    host_name    server1
}

define host {
    host_name    server2
}

define host {
    host_name    server3
}
"""
        config_file.write_text(content)

        result = delete_object_from_file(str(config_file), 5)
        assert result.success is True

        new_content = config_file.read_text()
        assert 'server1' in new_content
        assert 'server2' not in new_content
        assert 'server3' in new_content


class TestAddObjectToFile:
    """Tests for add_object_to_file function."""

    def test_add_to_existing_file(self, temp_config_dir):
        """Test adding to existing file at the end."""
        config_file = temp_config_dir / "test.cfg"
        content = """define host {
    host_name    server1
}
"""
        config_file.write_text(content)

        result = add_object_to_file(
            str(config_file),
            'host',
            {'host_name': 'server2', 'address': '192.168.1.2'}
        )

        assert result.success is True
        new_content = config_file.read_text()
        assert 'server1' in new_content
        assert 'server2' in new_content

    def test_add_after_specific_block(self, temp_config_dir):
        """Test adding after a specific block."""
        config_file = temp_config_dir / "test.cfg"
        content = """define host {
    host_name    server1
}

define host {
    host_name    server3
}
"""
        config_file.write_text(content)

        result = add_object_to_file(
            str(config_file),
            'host',
            {'host_name': 'server2', 'address': '192.168.1.2'},
            after_block_line=1
        )

        assert result.success is True
        new_content = config_file.read_text()
        lines = new_content.split('\n')

        # Find positions of servers
        server1_idx = None
        server2_idx = None
        server3_idx = None
        for i, line in enumerate(lines):
            if 'server1' in line:
                server1_idx = i
            if 'server2' in line:
                server2_idx = i
            if 'server3' in line:
                server3_idx = i

        # server2 should be between server1 and server3
        assert server1_idx < server2_idx < server3_idx

    def test_add_to_non_existent_file(self, temp_config_dir):
        """Test adding to non-existent file creates it."""
        config_file = temp_config_dir / "new_file.cfg"

        result = add_object_to_file(
            str(config_file),
            'host',
            {'host_name': 'server1', 'address': '192.168.1.1'}
        )

        assert result.success is True
        assert config_file.exists()
        content = config_file.read_text()
        assert 'server1' in content

    def test_add_at_position_zero(self, temp_config_dir):
        """Test adding at beginning of file."""
        config_file = temp_config_dir / "test.cfg"
        content = """define host {
    host_name    server2
}
"""
        config_file.write_text(content)

        result = add_object_to_file(
            str(config_file),
            'host',
            {'host_name': 'server1', 'address': '192.168.1.1'},
            after_block_line=0
        )

        assert result.success is True
        new_content = config_file.read_text()
        lines = new_content.split('\n')

        # server1 should appear before server2
        server1_idx = None
        server2_idx = None
        for i, line in enumerate(lines):
            if 'server1' in line:
                server1_idx = i
            if 'server2' in line:
                server2_idx = i

        assert server1_idx < server2_idx

    def test_add_creates_parent_directories(self, temp_config_dir):
        """Test that adding creates parent directories if needed."""
        nested_file = temp_config_dir / "subdir" / "test.cfg"

        result = add_object_to_file(
            str(nested_file),
            'host',
            {'host_name': 'server1', 'address': '192.168.1.1'}
        )

        assert result.success is True
        assert nested_file.exists()
        assert nested_file.parent.exists()


class TestMoveObjectBetweenFiles:
    """Tests for move_object_between_files function."""

    def test_move_between_different_files(self, temp_config_dir):
        """Test moving object between different files."""
        source_file = temp_config_dir / "source.cfg"
        target_file = temp_config_dir / "target.cfg"

        source_content = """define host {
    host_name    server1
    address      192.168.1.1
}

define host {
    host_name    server2
}
"""
        source_file.write_text(source_content)

        target_content = """define host {
    host_name    server3
}
"""
        target_file.write_text(target_content)

        result = move_object_between_files(
            str(source_file),
            1,
            str(target_file),
            'host',
            {'host_name': 'server1', 'address': '192.168.1.1'}
        )

        assert result.success is True

        source_new = source_file.read_text()
        target_new = target_file.read_text()

        assert 'server1' not in source_new
        assert 'server2' in source_new
        assert 'server1' in target_new
        assert 'server3' in target_new

    def test_same_file_reorder(self, temp_config_dir):
        """Test reordering within the same file."""
        config_file = temp_config_dir / "test.cfg"
        content = """define host {
    host_name    server1
}

define host {
    host_name    server2
}

define host {
    host_name    server3
}
"""
        config_file.write_text(content)

        # Move server3 to after server1
        result = move_object_between_files(
            str(config_file),
            9,  # Line where server3 is
            str(config_file),
            'host',
            {'host_name': 'server3'},
            insert_line=1
        )

        assert result.success is True
        new_content = config_file.read_text()
        lines = new_content.split('\n')

        # Find positions
        positions = {}
        for i, line in enumerate(lines):
            for server in ['server1', 'server2', 'server3']:
                if server in line:
                    positions[server] = i

        # server3 should now be between server1 and server2
        assert positions['server1'] < positions['server3'] < positions['server2']

    def test_move_to_non_existent_target(self, temp_config_dir):
        """Test moving to a non-existent target file."""
        source_file = temp_config_dir / "source.cfg"
        target_file = temp_config_dir / "target.cfg"

        source_content = """define host {
    host_name    server1
}
"""
        source_file.write_text(source_content)

        result = move_object_between_files(
            str(source_file),
            1,
            str(target_file),
            'host',
            {'host_name': 'server1'}
        )

        assert result.success is True
        assert not source_file.read_text().strip() or 'server1' not in source_file.read_text()
        assert target_file.exists()
        assert 'server1' in target_file.read_text()

    def test_move_source_not_found(self):
        """Test moving from non-existent source file."""
        result = move_object_between_files(
            '/nonexistent/source.cfg',
            1,
            '/tmp/target.cfg',
            'host',
            {'host_name': 'server1'}
        )
        assert result.success is False


class TestIsSafePath:
    """Tests for is_safe_path function."""

    def test_valid_path_within_base(self, temp_config_dir):
        """Test valid path within base directory."""
        base_dir = str(temp_config_dir)
        test_path = os.path.join(base_dir, "test.cfg")

        is_safe, error = is_safe_path(test_path, base_dir)
        assert is_safe is True
        assert error == ""

    def test_path_traversal_attempt(self, temp_config_dir):
        """Test path traversal with ../."""
        base_dir = str(temp_config_dir)
        test_path = os.path.join(base_dir, "..", "etc", "passwd")

        is_safe, error = is_safe_path(test_path, base_dir)
        assert is_safe is False
        assert "must be within config directory" in error

    def test_null_byte_injection(self, temp_config_dir):
        """Test null byte injection."""
        base_dir = str(temp_config_dir)
        test_path = os.path.join(base_dir, "test\x00.cfg")

        is_safe, error = is_safe_path(test_path, base_dir)
        assert is_safe is False
        assert "null bytes" in error.lower()

    def test_absolute_path_outside_config(self, temp_config_dir):
        """Test absolute path outside config directory."""
        base_dir = str(temp_config_dir)
        test_path = "/etc/passwd"

        is_safe, error = is_safe_path(test_path, base_dir)
        assert is_safe is False
        assert "must be within config directory" in error

    def test_relative_path_within_config(self, temp_config_dir):
        """Test relative path that stays within config directory."""
        base_dir = str(temp_config_dir)
        test_path = "subdir/test.cfg"

        is_safe, error = is_safe_path(test_path, base_dir)
        assert is_safe is True
        assert error == ""

    def test_symlink_traversal(self, temp_config_dir, tmp_path):
        """Test symlink pointing outside config directory."""
        base_dir = str(temp_config_dir)
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        outside_file = outside_dir / "secret.cfg"
        outside_file.write_text("secret data")

        # Create symlink inside config dir pointing outside
        symlink_path = temp_config_dir / "link_to_outside"
        try:
            symlink_path.symlink_to(outside_dir)
            test_path = str(symlink_path / "secret.cfg")

            is_safe, error = is_safe_path(test_path, base_dir)
            assert is_safe is False
            assert "must be within config directory" in error
        except OSError:
            # Symlinks may not be supported on all platforms
            pytest.skip("Symlinks not supported on this platform")

    def test_no_base_dir(self):
        """Test that base_dir is required."""
        is_safe, error = is_safe_path("/some/path", None)
        assert is_safe is False
        assert "base_dir parameter is required" in error

    def test_symlinked_base_directory(self, tmp_path):
        """Test with symlinked base directory."""
        real_dir = tmp_path / "real_config"
        real_dir.mkdir()

        link_dir = tmp_path / "link_config"
        try:
            link_dir.symlink_to(real_dir)

            test_file = "test.cfg"
            is_safe, error = is_safe_path(test_file, str(link_dir))
            assert is_safe is True
            assert error == ""
        except OSError:
            pytest.skip("Symlinks not supported on this platform")


class TestGenerateDiff:
    """Tests for generate_diff function."""

    def test_simple_diff_with_changes(self):
        """Test generating diff with changes."""
        old_content = """define host {
    host_name    server1
    alias        Old Alias
}
"""
        new_content = """define host {
    host_name    server1
    alias        New Alias
}
"""
        diff = generate_diff(old_content, new_content, "test.cfg")
        diff_text = ''.join(diff)

        assert len(diff) > 0
        assert 'test.cfg' in diff_text
        assert '-' in diff_text or '+' in diff_text

    def test_no_changes_empty_diff(self):
        """Test that identical content produces minimal diff output."""
        content = """define host {
    host_name    server1
}
"""
        diff = generate_diff(content, content, "test.cfg")
        diff_list = list(diff)

        # Unified diff with no changes should produce no output or minimal header
        assert len(diff_list) == 0 or all(
            line.startswith('---') or line.startswith('+++') or line.startswith('@@')
            for line in diff_list
        )

    def test_diff_without_filename(self):
        """Test generating diff without filename."""
        old_content = "old\n"
        new_content = "new\n"

        diff = generate_diff(old_content, new_content)
        diff_text = ''.join(diff)

        assert 'before' in diff_text or 'after' in diff_text

    def test_diff_addition(self):
        """Test diff showing addition."""
        old_content = "line1\n"
        new_content = "line1\nline2\n"

        diff = generate_diff(old_content, new_content, "test.txt")
        diff_text = ''.join(diff)

        assert '+line2' in diff_text or '+ line2' in diff_text

    def test_diff_deletion(self):
        """Test diff showing deletion."""
        old_content = "line1\nline2\n"
        new_content = "line1\n"

        diff = generate_diff(old_content, new_content, "test.txt")
        diff_text = ''.join(diff)

        assert '-line2' in diff_text or '- line2' in diff_text
