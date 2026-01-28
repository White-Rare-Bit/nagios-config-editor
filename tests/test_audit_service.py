"""
Tests for audit_service.py - Audit Log Service
"""

import pytest
import os
import sys
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import audit_service


class TestAuditService:
    """Tests for the audit service functions."""

    def setup_method(self):
        """Reset global state before each test."""
        audit_service.AUDIT_LOG_DIR = None
        audit_service.AUDIT_LOG_FILE = None

    def teardown_method(self):
        """Reset global state after each test to avoid polluting other tests."""
        audit_service.AUDIT_LOG_DIR = None
        audit_service.AUDIT_LOG_FILE = None

    def test_get_audit_log_dir_default(self, temp_config_dir):
        """Test get_audit_log_dir returns expected directory path."""
        log_dir = audit_service.get_audit_log_dir(temp_config_dir)
        expected_dir = os.path.join(temp_config_dir, 'logs')
        assert log_dir == expected_dir

    def test_get_audit_log_dir_creates_directory(self, temp_config_dir):
        """Test get_audit_log_dir creates directory if it doesn't exist."""
        log_dir = audit_service.get_audit_log_dir(temp_config_dir)
        assert os.path.exists(log_dir)
        assert os.path.isdir(log_dir)

    def test_get_audit_log_dir_caches_result(self, temp_config_dir):
        """Test get_audit_log_dir caches the directory path."""
        first_call = audit_service.get_audit_log_dir(temp_config_dir)
        second_call = audit_service.get_audit_log_dir(temp_config_dir)
        assert first_call == second_call
        assert audit_service.AUDIT_LOG_DIR == first_call

    def test_get_audit_log_path_returns_correct_path(self, temp_config_dir):
        """Test get_audit_log_path returns correct log file path."""
        log_path = audit_service.get_audit_log_path(temp_config_dir)
        expected_path = os.path.join(temp_config_dir, 'logs', 'audit_log.json')
        assert log_path == expected_path

    def test_get_audit_log_path_caches_result(self, temp_config_dir):
        """Test get_audit_log_path caches the file path."""
        first_call = audit_service.get_audit_log_path(temp_config_dir)
        second_call = audit_service.get_audit_log_path(temp_config_dir)
        assert first_call == second_call
        assert audit_service.AUDIT_LOG_FILE == first_call

    def test_write_audit_log_creates_new_file(self, temp_config_dir):
        """Test write_audit_log creates a new file when none exists."""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'action': 'test_action',
            'user': 'test_user'
        }

        audit_service.write_audit_log(entry, temp_config_dir)

        log_path = audit_service.get_audit_log_path(temp_config_dir)
        assert os.path.exists(log_path)

    def test_write_audit_log_entry_format(self, temp_config_dir):
        """Test write_audit_log creates properly formatted entries."""
        entry = {
            'timestamp': '2025-01-24T10:00:00',
            'action': 'create_host',
            'user': 'admin',
            'details': {'host_name': 'test-server'}
        }

        audit_service.write_audit_log(entry, temp_config_dir)

        log_path = audit_service.get_audit_log_path(temp_config_dir)
        with open(log_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        assert 'entries' in data
        assert len(data['entries']) == 1
        assert data['entries'][0] == entry

    def test_write_audit_log_appends_multiple_entries(self, temp_config_dir):
        """Test write_audit_log appends multiple entries correctly."""
        entry1 = {
            'timestamp': '2025-01-24T10:00:00',
            'action': 'action1',
            'user': 'user1'
        }
        entry2 = {
            'timestamp': '2025-01-24T11:00:00',
            'action': 'action2',
            'user': 'user2'
        }
        entry3 = {
            'timestamp': '2025-01-24T12:00:00',
            'action': 'action3',
            'user': 'user3'
        }

        audit_service.write_audit_log(entry1, temp_config_dir)
        audit_service.write_audit_log(entry2, temp_config_dir)
        audit_service.write_audit_log(entry3, temp_config_dir)

        log_path = audit_service.get_audit_log_path(temp_config_dir)
        with open(log_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        assert len(data['entries']) == 3
        assert data['entries'][0] == entry1
        assert data['entries'][1] == entry2
        assert data['entries'][2] == entry3

    def test_write_audit_log_handles_corrupted_file(self, temp_config_dir):
        """Test write_audit_log handles corrupted JSON gracefully."""
        log_path = audit_service.get_audit_log_path(temp_config_dir)

        # Write corrupted JSON
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write("corrupted json {")

        # Should still be able to write new entry
        entry = {
            'timestamp': '2025-01-24T10:00:00',
            'action': 'test_action',
            'user': 'test_user'
        }

        audit_service.write_audit_log(entry, temp_config_dir)

        # Verify the file was overwritten with valid JSON
        with open(log_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        assert 'entries' in data
        assert len(data['entries']) == 1
        assert data['entries'][0] == entry

    def test_rotate_audit_log_no_rotation_under_limit(self, temp_config_dir):
        """Test rotate_audit_log does not rotate when under limit."""
        entries = [{'action': f'action_{i}'} for i in range(100)]

        result = audit_service.rotate_audit_log(entries)

        assert result == entries
        assert len(result) == 100

    def test_rotate_audit_log_rotates_at_max_entries(self, temp_config_dir):
        """Test rotate_audit_log rotates when exceeding max entries."""
        # Set up entries at the max limit
        entries = [{'action': f'action_{i}'} for i in range(audit_service.AUDIT_LOG_MAX_ENTRIES)]

        # Initialize log dir
        audit_service.get_audit_log_dir(temp_config_dir)

        result = audit_service.rotate_audit_log(entries)

        # Should return empty list after rotation
        assert result == []

    def test_rotate_audit_log_creates_archive_file(self, temp_config_dir):
        """Test rotate_audit_log creates an archive file."""
        entries = [{'action': f'action_{i}'} for i in range(audit_service.AUDIT_LOG_MAX_ENTRIES)]

        # Initialize log dir
        log_dir = audit_service.get_audit_log_dir(temp_config_dir)

        audit_service.rotate_audit_log(entries)

        # Check that an archive file was created
        archive_files = [f for f in os.listdir(log_dir) if f.startswith('audit_log_') and f.endswith('.json')]
        assert len(archive_files) == 1

    def test_rotate_audit_log_archive_format(self, temp_config_dir):
        """Test rotate_audit_log creates properly formatted archive."""
        entries = [
            {'action': 'action_1', 'timestamp': '2025-01-24T10:00:00'},
            {'action': 'action_2', 'timestamp': '2025-01-24T11:00:00'}
        ]

        # Pad to max entries
        while len(entries) < audit_service.AUDIT_LOG_MAX_ENTRIES:
            entries.append({'action': f'action_{len(entries)}'})

        log_dir = audit_service.get_audit_log_dir(temp_config_dir)

        audit_service.rotate_audit_log(entries)

        # Find and read the archive file
        archive_files = [f for f in os.listdir(log_dir) if f.startswith('audit_log_') and f.endswith('.json')]
        assert len(archive_files) == 1

        archive_path = os.path.join(log_dir, archive_files[0])
        with open(archive_path, 'r', encoding='utf-8') as f:
            archive_data = json.load(f)

        assert 'entries' in archive_data
        assert 'archived_at' in archive_data
        assert len(archive_data['entries']) == audit_service.AUDIT_LOG_MAX_ENTRIES
        assert archive_data['entries'][0] == entries[0]
        assert archive_data['entries'][1] == entries[1]

    def test_rotate_audit_log_archive_filename_format(self, temp_config_dir):
        """Test rotate_audit_log creates archive with timestamp in filename."""
        entries = [{'action': f'action_{i}'} for i in range(audit_service.AUDIT_LOG_MAX_ENTRIES)]

        log_dir = audit_service.get_audit_log_dir(temp_config_dir)

        audit_service.rotate_audit_log(entries)

        # Check archive filename format
        archive_files = [f for f in os.listdir(log_dir) if f.startswith('audit_log_') and f.endswith('.json')]
        assert len(archive_files) == 1

        # Filename should be audit_log_YYYYMMDD_HHMMSS.json
        filename = archive_files[0]
        assert filename.startswith('audit_log_')
        assert filename.endswith('.json')

        # Extract timestamp portion
        timestamp_part = filename.replace('audit_log_', '').replace('.json', '')
        assert len(timestamp_part) == 15  # YYYYMMDD_HHMMSS
        assert '_' in timestamp_part

    def test_write_audit_log_triggers_rotation(self, temp_config_dir):
        """Test write_audit_log triggers rotation at max entries."""
        # Write entries up to the limit
        for i in range(audit_service.AUDIT_LOG_MAX_ENTRIES - 1):
            entry = {'action': f'action_{i}', 'timestamp': f'2025-01-24T{i:02d}:00:00'}
            audit_service.write_audit_log(entry, temp_config_dir)

        log_path = audit_service.get_audit_log_path(temp_config_dir)
        with open(log_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert len(data['entries']) == audit_service.AUDIT_LOG_MAX_ENTRIES - 1

        # Write one more entry to trigger rotation
        entry = {'action': 'action_final', 'timestamp': '2025-01-24T23:00:00'}
        audit_service.write_audit_log(entry, temp_config_dir)

        # Check that log was rotated (entries list becomes empty after rotation)
        with open(log_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert len(data['entries']) == 0

        # Check that archive was created with all entries including the final one
        log_dir = audit_service.get_audit_log_dir(temp_config_dir)
        archive_files = [f for f in os.listdir(log_dir) if f.startswith('audit_log_') and f.endswith('.json')]
        assert len(archive_files) == 1

        # Verify archive contains all max entries
        archive_path = os.path.join(log_dir, archive_files[0])
        with open(archive_path, 'r', encoding='utf-8') as f:
            archive_data = json.load(f)
        assert len(archive_data['entries']) == audit_service.AUDIT_LOG_MAX_ENTRIES

    def test_multiple_rotations_create_multiple_archives(self, temp_config_dir):
        """Test that multiple rotations create separate archive files."""
        # First rotation
        for i in range(audit_service.AUDIT_LOG_MAX_ENTRIES):
            entry = {'action': f'batch1_action_{i}'}
            audit_service.write_audit_log(entry, temp_config_dir)

        log_dir = audit_service.get_audit_log_dir(temp_config_dir)
        archive_files = [f for f in os.listdir(log_dir) if f.startswith('audit_log_') and f.endswith('.json')]
        assert len(archive_files) == 1

        # Second rotation (need to write MAX_ENTRIES more)
        for i in range(audit_service.AUDIT_LOG_MAX_ENTRIES):
            entry = {'action': f'batch2_action_{i}'}
            audit_service.write_audit_log(entry, temp_config_dir)

        archive_files = [f for f in os.listdir(log_dir) if f.startswith('audit_log_') and f.endswith('.json')]
        assert len(archive_files) == 2
