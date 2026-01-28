"""
Tests for staging conflict detection in StagingManager.

These tests verify that the staging system correctly detects when files
have been modified externally (by another process or user) after staging began.
"""

import os
import sys
import pytest
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from staging_manager import StagingManager


class TestStagingConflictDetection:
    """Tests for staging conflict detection via file checksums."""

    def test_detect_conflict_when_file_modified_externally(self, temp_config_dir):
        """Test that conflict is detected when file is modified after staging begins.

        Scenario:
        1. Create a config file
        2. Start staging session and capture base checksum
        3. Modify the file externally (simulating another user/process)
        4. Verify detect_conflicts() reports the modification
        """
        manager = StagingManager(temp_config_dir)

        # Create a config file
        config_file = os.path.join(temp_config_dir, 'hosts.cfg')
        original_content = '''define host {
    host_name    webserver01
    address      192.168.1.1
}
'''
        Path(config_file).write_text(original_content)

        # Start staging session
        staging_data = {
            'sessionId': 'test-session',
            'pendingEdits': [],
            'stagedMoves': [],
            'stagedCreations': [],
            'baseFileChecksums': {}
        }
        manager.save_staging(staging_data)

        # Capture base checksum for the file
        manager.update_base_checksums([config_file])

        # Verify base checksum was captured
        staging = manager.get_staging()
        assert config_file in staging['baseFileChecksums']
        original_checksum = staging['baseFileChecksums'][config_file]

        # Simulate external modification
        modified_content = '''define host {
    host_name    webserver01
    address      192.168.1.100
}
'''
        Path(config_file).write_text(modified_content)

        # Detect conflicts
        conflicts = manager.detect_conflicts()

        # Should detect one conflict
        assert len(conflicts) == 1
        conflict = conflicts[0]
        assert conflict['path'] == config_file
        assert conflict['type'] == 'modified'
        assert conflict['baseChecksum'] == original_checksum
        assert conflict['currentChecksum'] is not None
        assert conflict['currentChecksum'] != original_checksum

    def test_detect_conflict_when_file_deleted_externally(self, temp_config_dir):
        """Test that conflict is detected when file is deleted after staging begins.

        Scenario:
        1. Create a config file
        2. Start staging session and capture base checksum
        3. Delete the file externally
        4. Verify detect_conflicts() reports type='deleted'
        """
        manager = StagingManager(temp_config_dir)

        # Create a config file
        config_file = os.path.join(temp_config_dir, 'services.cfg')
        content = '''define service {
    host_name            webserver01
    service_description  HTTP
    check_command        check_http
}
'''
        Path(config_file).write_text(content)

        # Start staging session
        staging_data = {
            'sessionId': 'test-session',
            'pendingEdits': [],
            'stagedMoves': [],
            'stagedCreations': [],
            'baseFileChecksums': {}
        }
        manager.save_staging(staging_data)

        # Capture base checksum
        manager.update_base_checksums([config_file])

        # Verify base checksum was captured
        staging = manager.get_staging()
        assert config_file in staging['baseFileChecksums']
        original_checksum = staging['baseFileChecksums'][config_file]

        # Delete the file externally
        os.remove(config_file)
        assert not Path(config_file).exists()

        # Detect conflicts
        conflicts = manager.detect_conflicts()

        # Should detect one conflict with type='deleted'
        assert len(conflicts) == 1
        conflict = conflicts[0]
        assert conflict['path'] == config_file
        assert conflict['type'] == 'deleted'
        assert conflict['baseChecksum'] == original_checksum
        assert conflict['currentChecksum'] is None

    def test_no_conflict_when_file_unchanged(self, temp_config_dir):
        """Test that no conflict is detected when file remains unchanged.

        Scenario:
        1. Create a config file
        2. Start staging session and capture base checksum
        3. Do NOT modify the file
        4. Verify detect_conflicts() returns empty list
        """
        manager = StagingManager(temp_config_dir)

        # Create a config file
        config_file = os.path.join(temp_config_dir, 'commands.cfg')
        content = '''define command {
    command_name    check_ping
    command_line    /usr/lib/nagios/plugins/check_ping -H $HOSTADDRESS$
}
'''
        Path(config_file).write_text(content)

        # Start staging session
        staging_data = {
            'sessionId': 'test-session',
            'pendingEdits': [],
            'stagedMoves': [],
            'stagedCreations': [],
            'baseFileChecksums': {}
        }
        manager.save_staging(staging_data)

        # Capture base checksum
        manager.update_base_checksums([config_file])

        # Verify base checksum was captured
        staging = manager.get_staging()
        assert config_file in staging['baseFileChecksums']

        # Do NOT modify the file

        # Detect conflicts
        conflicts = manager.detect_conflicts()

        # Should have no conflicts
        assert len(conflicts) == 0

    def test_base_checksum_captured_on_first_stage(self, temp_config_dir):
        """Test that base checksums are only captured once per file.

        Scenario:
        1. Create a config file
        2. Start staging session and capture base checksum
        3. Modify the file
        4. Call update_base_checksums again
        5. Verify the original checksum is preserved (not updated to new value)

        This ensures we compare against the state when staging FIRST began,
        not some intermediate state.
        """
        manager = StagingManager(temp_config_dir)

        # Create a config file
        config_file = os.path.join(temp_config_dir, 'timeperiods.cfg')
        original_content = '''define timeperiod {
    timeperiod_name    24x7
    alias              24 Hours A Day
}
'''
        Path(config_file).write_text(original_content)

        # Start staging session
        staging_data = {
            'sessionId': 'test-session',
            'pendingEdits': [],
            'stagedMoves': [],
            'stagedCreations': [],
            'baseFileChecksums': {}
        }
        manager.save_staging(staging_data)

        # First capture of base checksum
        manager.update_base_checksums([config_file])

        staging = manager.get_staging()
        original_checksum = staging['baseFileChecksums'][config_file]

        # Modify the file (simulating internal application write)
        modified_content = '''define timeperiod {
    timeperiod_name    24x7
    alias              24 Hours A Day, 7 Days A Week
}
'''
        Path(config_file).write_text(modified_content)

        # Try to update base checksums again
        manager.update_base_checksums([config_file])

        # Verify the original checksum is PRESERVED
        staging = manager.get_staging()
        preserved_checksum = staging['baseFileChecksums'][config_file]

        assert preserved_checksum == original_checksum, \
            "Base checksum should not be updated once captured"

        # Compute current checksum to prove file was actually modified
        current_checksum = manager.compute_file_checksum(config_file)
        assert current_checksum != original_checksum, \
            "File should have different checksum after modification"


class TestStagingConflictDetectionMultipleFiles:
    """Tests for conflict detection with multiple files."""

    def test_detect_conflicts_multiple_files_mixed_states(self, temp_config_dir):
        """Test conflict detection with multiple files in different states.

        Scenario:
        - file1: modified externally (should conflict)
        - file2: deleted externally (should conflict)
        - file3: unchanged (no conflict)
        """
        manager = StagingManager(temp_config_dir)

        # Create three config files
        file1 = os.path.join(temp_config_dir, 'hosts.cfg')
        file2 = os.path.join(temp_config_dir, 'services.cfg')
        file3 = os.path.join(temp_config_dir, 'commands.cfg')

        Path(file1).write_text('define host { host_name host1 }')
        Path(file2).write_text('define service { service_description svc1 }')
        Path(file3).write_text('define command { command_name cmd1 }')

        # Start staging session
        staging_data = {
            'sessionId': 'test-session',
            'pendingEdits': [],
            'stagedMoves': [],
            'stagedCreations': [],
            'baseFileChecksums': {}
        }
        manager.save_staging(staging_data)

        # Capture base checksums for all files
        manager.update_base_checksums([file1, file2, file3])

        # Modify file1
        Path(file1).write_text('define host { host_name host1-modified }')

        # Delete file2
        os.remove(file2)

        # Leave file3 unchanged

        # Detect conflicts
        conflicts = manager.detect_conflicts()

        # Should have 2 conflicts
        assert len(conflicts) == 2

        # Verify conflict types
        conflict_map = {c['path']: c for c in conflicts}

        assert file1 in conflict_map
        assert conflict_map[file1]['type'] == 'modified'

        assert file2 in conflict_map
        assert conflict_map[file2]['type'] == 'deleted'

        # file3 should NOT be in conflicts
        assert file3 not in conflict_map

    def test_detect_conflicts_no_staging(self, temp_config_dir):
        """Test that detect_conflicts returns empty list when no staging exists."""
        manager = StagingManager(temp_config_dir)

        # Create a file but don't start staging
        config_file = os.path.join(temp_config_dir, 'hosts.cfg')
        Path(config_file).write_text('define host { host_name host1 }')

        # Should return empty list
        conflicts = manager.detect_conflicts()
        assert conflicts == []

    def test_detect_conflicts_empty_base_checksums(self, temp_config_dir):
        """Test that detect_conflicts works when no base checksums exist."""
        manager = StagingManager(temp_config_dir)

        # Create a file
        config_file = os.path.join(temp_config_dir, 'hosts.cfg')
        Path(config_file).write_text('define host { host_name host1 }')

        # Start staging without capturing checksums
        staging_data = {
            'sessionId': 'test-session',
            'pendingEdits': [],
            'stagedMoves': [],
            'stagedCreations': [],
            'baseFileChecksums': {}  # Empty
        }
        manager.save_staging(staging_data)

        # Modify the file
        Path(config_file).write_text('define host { host_name host1-modified }')

        # Should return empty list (no base checksums to compare against)
        conflicts = manager.detect_conflicts()
        assert conflicts == []


class TestComputeFileChecksum:
    """Tests for the compute_file_checksum method."""

    def test_compute_checksum_existing_file(self, temp_config_dir):
        """Test computing checksum for an existing file."""
        manager = StagingManager(temp_config_dir)

        config_file = os.path.join(temp_config_dir, 'test.cfg')
        content = 'define host { host_name test }'
        Path(config_file).write_text(content)

        checksum = manager.compute_file_checksum(config_file)

        assert checksum is not None
        assert len(checksum) == 64  # SHA256 hex digest is 64 chars

    def test_compute_checksum_nonexistent_file(self, temp_config_dir):
        """Test computing checksum for a file that doesn't exist."""
        manager = StagingManager(temp_config_dir)

        nonexistent = os.path.join(temp_config_dir, 'nonexistent.cfg')

        checksum = manager.compute_file_checksum(nonexistent)

        assert checksum is None

    def test_compute_checksum_deterministic(self, temp_config_dir):
        """Test that checksum is deterministic for same content."""
        manager = StagingManager(temp_config_dir)

        config_file = os.path.join(temp_config_dir, 'test.cfg')
        content = 'define host { host_name test }'
        Path(config_file).write_text(content)

        checksum1 = manager.compute_file_checksum(config_file)
        checksum2 = manager.compute_file_checksum(config_file)

        assert checksum1 == checksum2

    def test_compute_checksum_changes_with_content(self, temp_config_dir):
        """Test that checksum changes when file content changes."""
        manager = StagingManager(temp_config_dir)

        config_file = os.path.join(temp_config_dir, 'test.cfg')

        Path(config_file).write_text('content1')
        checksum1 = manager.compute_file_checksum(config_file)

        Path(config_file).write_text('content2')
        checksum2 = manager.compute_file_checksum(config_file)

        assert checksum1 != checksum2


class TestComputeBaseChecksums:
    """Tests for the compute_base_checksums method."""

    def test_compute_base_checksums_all_cfg_files(self, temp_config_dir):
        """Test computing checksums for all .cfg files in directory."""
        manager = StagingManager(temp_config_dir)

        # Create multiple .cfg files
        Path(os.path.join(temp_config_dir, 'hosts.cfg')).write_text('host content')
        Path(os.path.join(temp_config_dir, 'services.cfg')).write_text('service content')
        Path(os.path.join(temp_config_dir, 'other.txt')).write_text('other content')

        checksums = manager.compute_base_checksums()

        # Should only include .cfg files
        assert len(checksums) == 2
        assert any('hosts.cfg' in path for path in checksums.keys())
        assert any('services.cfg' in path for path in checksums.keys())
        assert not any('other.txt' in path for path in checksums.keys())

    def test_compute_base_checksums_specific_files(self, temp_config_dir):
        """Test computing checksums for specific files only."""
        manager = StagingManager(temp_config_dir)

        file1 = os.path.join(temp_config_dir, 'hosts.cfg')
        file2 = os.path.join(temp_config_dir, 'services.cfg')
        Path(file1).write_text('host content')
        Path(file2).write_text('service content')

        checksums = manager.compute_base_checksums([file1])

        # Should only include the specified file
        assert len(checksums) == 1
        assert file1 in checksums
        assert file2 not in checksums

    def test_compute_base_checksums_excludes_staging_dir(self, temp_config_dir):
        """Test that .staging directory is excluded from checksums."""
        manager = StagingManager(temp_config_dir)

        # Create a .cfg file in main dir
        Path(os.path.join(temp_config_dir, 'hosts.cfg')).write_text('host content')

        # Create staging dir with a .cfg file (should be excluded)
        staging_dir = os.path.join(temp_config_dir, '.staging')
        os.makedirs(staging_dir, exist_ok=True)
        Path(os.path.join(staging_dir, 'staging.cfg')).write_text('staging content')

        checksums = manager.compute_base_checksums()

        # Should only include the main hosts.cfg
        assert len(checksums) == 1
        assert not any('.staging' in path for path in checksums.keys())
