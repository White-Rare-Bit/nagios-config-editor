"""
Tests for staging_manager.py - Staging Manager
"""

import pytest
import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from staging_manager import StagingManager


class TestStagingManager:
    """Tests for the StagingManager class."""

    def test_init(self, temp_config_dir):
        """Test initialization."""
        manager = StagingManager(temp_config_dir)
        assert manager.config_path.exists()
        assert manager.staging_dir == manager.config_path / '.staging'

    def test_get_staging_none(self, temp_config_dir):
        """Test getting staging when none exists."""
        manager = StagingManager(temp_config_dir)
        result = manager.get_staging()
        assert result is None

    def test_save_and_get_staging(self, temp_config_dir):
        """Test saving and retrieving staging data."""
        manager = StagingManager(temp_config_dir)

        data = {
            'sessionId': 'test-session',
            'pendingEdits': [[1, {'original': {}, 'edited': {'host_name': 'test'}}]],
            'stagedMoves': [],
            'stagedCreations': []
        }

        result = manager.save_staging(data)
        assert result.success

        retrieved = manager.get_staging()
        assert retrieved is not None
        assert len(retrieved['pendingEdits']) == 1

    def test_save_staging_adds_metadata(self, temp_config_dir):
        """Test that save_staging adds metadata."""
        manager = StagingManager(temp_config_dir)

        data = {
            'sessionId': 'test-session',
            'pendingEdits': [[1, {}]],
            'stagedMoves': [],
            'stagedCreations': []
        }

        manager.save_staging(data)
        retrieved = manager.get_staging()

        assert 'lastModified' in retrieved
        assert 'lastModifiedISO' in retrieved

    def test_clear_staging(self, temp_config_dir):
        """Test clearing staging data."""
        manager = StagingManager(temp_config_dir)

        # Save some data
        data = {
            'sessionId': 'test-session',
            'pendingEdits': [[1, {}]],
            'stagedMoves': [],
            'stagedCreations': []
        }
        manager.save_staging(data)
        assert manager.get_staging() is not None

        # Clear it
        result = manager.clear_staging()
        assert result.success
        assert manager.get_staging() is None

    def test_clear_staging_when_empty(self, temp_config_dir):
        """Test clearing staging when it's already empty."""
        manager = StagingManager(temp_config_dir)
        result = manager.clear_staging()
        assert result.success

    def test_has_staging_false(self, temp_config_dir):
        """Test has_staging when no staging exists."""
        manager = StagingManager(temp_config_dir)
        assert manager.has_staging() is False

    def test_has_staging_true(self, temp_config_dir):
        """Test has_staging when staging exists (has sessionId)."""
        manager = StagingManager(temp_config_dir)

        data = {
            'sessionId': 'test-session',
            'pendingEdits': [[1, {}]],
            'stagedMoves': [],
            'stagedCreations': []
        }
        manager.save_staging(data)

        assert manager.has_staging() is True

    def test_has_staging_empty_data(self, temp_config_dir):
        """Test has_staging with empty staging data."""
        manager = StagingManager(temp_config_dir)

        # Save empty data
        # Note: stagedFileMoves, stagedFolderMoves, newFolders, stagedDeletions removed
        # - these operations now happen immediately via API
        data = {
            'pendingEdits': [],
            'stagedMoves': [],
            'stagedCreations': [],
            'stagedObjectDeletions': [],
            'newFiles': []
        }
        manager.save_staging(data)

        # Should return False because staging is effectively empty
        assert manager.has_staging() is False

    def test_get_staging_info_none(self, temp_config_dir):
        """Test get_staging_info when no staging exists."""
        manager = StagingManager(temp_config_dir)
        info = manager.get_staging_info()

        assert info['hasStaging'] is False
        assert info['counts'] == {}

    def test_get_staging_info_with_data(self, temp_config_dir):
        """Test get_staging_info with staging data."""
        manager = StagingManager(temp_config_dir)

        # Note: stagedFileMoves, stagedFolderMoves, newFolders, stagedDeletions removed
        data = {
            'sessionId': 'test-session',
            'pendingEdits': [[1, {}], [2, {}]],
            'stagedMoves': [[3, {}]],
            'stagedCreations': [{'object_type': 'host'}],
            'stagedObjectDeletions': [5],
            'newFiles': ['test.cfg']
        }
        manager.save_staging(data)

        info = manager.get_staging_info()

        assert info['hasStaging'] is True
        assert info['counts']['edits'] == 2
        assert info['counts']['moves'] == 1
        assert info['counts']['creations'] == 1
        assert info['counts']['objectDeletions'] == 1
        assert info['counts']['newFiles'] == 1
        assert 'lastModified' in info

    def test_staging_creates_gitignore(self, temp_config_dir):
        """Test that staging directory includes .gitignore."""
        manager = StagingManager(temp_config_dir)

        data = {'pendingEdits': [[1, {}]], 'stagedMoves': [], 'stagedCreations': []}
        manager.save_staging(data)

        gitignore_path = manager.staging_dir / '.gitignore'
        assert gitignore_path.exists()
        assert '*' in gitignore_path.read_text()

    def test_staging_atomic_write(self, temp_config_dir):
        """Test that staging writes are atomic."""
        manager = StagingManager(temp_config_dir)

        data = {'pendingEdits': [[1, {}]], 'stagedMoves': [], 'stagedCreations': []}
        manager.save_staging(data)

        # Check no temp files left behind
        staging_files = list(manager.staging_dir.glob('*'))
        assert not any(f.suffix == '.tmp' for f in staging_files)

    def test_staging_handles_corrupt_json(self, temp_config_dir):
        """Test that get_staging handles corrupt JSON gracefully."""
        manager = StagingManager(temp_config_dir)

        # Create corrupt staging file
        manager._ensure_staging_dir()
        manager.staging_file.write_text('not valid json {{{')

        result = manager.get_staging()
        assert result is None

    def test_staging_handles_empty_file(self, temp_config_dir):
        """Test that get_staging handles empty file gracefully."""
        manager = StagingManager(temp_config_dir)

        # Create empty staging file
        manager._ensure_staging_dir()
        manager.staging_file.write_text('')

        result = manager.get_staging()
        assert result is None

    def test_is_empty_staging(self, temp_config_dir):
        """Test _is_empty_staging helper.

        With the direct-file approach, staging is now just a lock mechanism.
        Staging is "empty" if there's no session holding the lock.
        """
        manager = StagingManager(temp_config_dir)

        # Empty data
        assert manager._is_empty_staging({}) is True
        assert manager._is_empty_staging(None) is True

        # No sessionId means empty
        no_session_data = {
            'pendingEdits': [[1, {}]],
            'stagedMoves': [],
            'stagedCreations': []
        }
        assert manager._is_empty_staging(no_session_data) is True

        # With sessionId means not empty (lock is held)
        with_session_data = {
            'sessionId': 'test-session',
            'pendingEdits': [],
            'stagedMoves': [],
            'stagedCreations': []
        }
        assert manager._is_empty_staging(with_session_data) is False

        # restorePending also means not empty
        restore_pending_data = {
            'restorePending': True,
            'pendingEdits': [],
            'stagedMoves': [],
            'stagedCreations': []
        }
        assert manager._is_empty_staging(restore_pending_data) is False

    def test_staging_preserves_session_id(self, temp_config_dir):
        """Test that staging preserves session ID."""
        manager = StagingManager(temp_config_dir)

        data = {
            'sessionId': 'test-session-123',
            'pendingEdits': [[1, {}]],
            'stagedMoves': [],
            'stagedCreations': []
        }
        manager.save_staging(data)

        retrieved = manager.get_staging()
        assert retrieved['sessionId'] == 'test-session-123'

    def test_staging_multiple_updates(self, temp_config_dir):
        """Test multiple updates to staging."""
        manager = StagingManager(temp_config_dir)

        # First update
        data1 = {
            'sessionId': 'test-session',
            'pendingEdits': [[1, {}]],
            'stagedMoves': [],
            'stagedCreations': []
        }
        manager.save_staging(data1)

        # Second update
        data2 = {
            'sessionId': 'test-session',
            'pendingEdits': [[1, {}], [2, {}]],
            'stagedMoves': [[3, {}]],
            'stagedCreations': []
        }
        manager.save_staging(data2)

        retrieved = manager.get_staging()
        assert len(retrieved['pendingEdits']) == 2
        assert len(retrieved['stagedMoves']) == 1

    def test_staging_complex_data(self, temp_config_dir):
        """Test staging with complex nested data."""
        manager = StagingManager(temp_config_dir)

        data = {
            'sessionId': 'test-session',
            'pendingEdits': [
                [1, {
                    'original': {'host_name': 'old-name', 'address': '192.168.1.1'},
                    'edited': {'host_name': 'new-name', 'address': '192.168.1.1'},
                    'object': {
                        'source_file': '/etc/nagios/hosts.cfg',
                        'line_number': 10,
                        'object_type': 'host',
                        'display_name': 'new-name'
                    }
                }]
            ],
            'stagedMoves': [
                [2, {
                    'originalFile': '/etc/nagios/old.cfg',
                    'targetFile': '/etc/nagios/new.cfg'
                }]
            ],
            'stagedCreations': [
                {
                    'object_type': 'host',
                    'attributes': {'host_name': 'created-host'},
                    'targetFile': '/etc/nagios/hosts.cfg'
                }
            ],
            # Note: stagedFileMoves, stagedFolderMoves, newFolders, stagedDeletions removed
            'stagedObjectDeletions': [],
            'newFiles': []
        }
        manager.save_staging(data)

        retrieved = manager.get_staging()
        assert retrieved['pendingEdits'][0][1]['edited']['host_name'] == 'new-name'
        assert retrieved['stagedMoves'][0][1]['targetFile'] == '/etc/nagios/new.cfg'
        assert retrieved['stagedCreations'][0]['attributes']['host_name'] == 'created-host'


class TestStagingManagerThreadSafety:
    """Tests for thread safety of StagingManager."""

    def test_concurrent_reads(self, temp_config_dir):
        """Test concurrent reads don't cause issues."""
        import threading

        manager = StagingManager(temp_config_dir)
        data = {
            'sessionId': 'test-session',
            'pendingEdits': [[1, {}]],
            'stagedMoves': [],
            'stagedCreations': []
        }
        manager.save_staging(data)

        results = []
        errors = []

        def read_staging():
            try:
                result = manager.get_staging()
                results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=read_staging) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 10
        assert all(r is not None for r in results)

    def test_concurrent_writes(self, temp_config_dir):
        """Test concurrent writes don't corrupt data."""
        import threading

        manager = StagingManager(temp_config_dir)
        errors = []

        def write_staging(i):
            try:
                data = {
                    'sessionId': f'test-session-{i}',
                    'pendingEdits': [[i, {}]],
                    'stagedMoves': [],
                    'stagedCreations': []
                }
                manager.save_staging(data)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=write_staging, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # Final staging should be valid JSON
        result = manager.get_staging()
        assert result is not None


class TestStagingLock:
    """Tests for lock management in StagingManager."""

    def test_get_lock_owner_no_staging(self, temp_config_dir):
        """Test get_lock_owner returns None when no staging exists."""
        manager = StagingManager(temp_config_dir)
        assert manager.get_lock_owner() is None

    def test_get_lock_owner_with_session(self, temp_config_dir):
        """Test get_lock_owner returns session ID from staging."""
        manager = StagingManager(temp_config_dir)
        data = {
            'sessionId': 'session-abc-123',
            'pendingEdits': [[1, {}]],
            'stagedMoves': [],
            'stagedCreations': []
        }
        manager.save_staging(data)

        assert manager.get_lock_owner() == 'session-abc-123'

    def test_can_modify_no_staging(self, temp_config_dir):
        """Test can_modify returns True when no staging exists."""
        manager = StagingManager(temp_config_dir)
        assert manager.can_modify('any-session') is True

    def test_can_modify_same_session(self, temp_config_dir):
        """Test can_modify returns True for the lock owner."""
        manager = StagingManager(temp_config_dir)
        data = {
            'sessionId': 'my-session',
            'pendingEdits': [[1, {}]],
            'stagedMoves': [],
            'stagedCreations': []
        }
        manager.save_staging(data)

        assert manager.can_modify('my-session') is True

    def test_can_modify_different_session(self, temp_config_dir):
        """Test can_modify returns False for different session."""
        manager = StagingManager(temp_config_dir)
        data = {
            'sessionId': 'owner-session',
            'pendingEdits': [[1, {}]],
            'stagedMoves': [],
            'stagedCreations': []
        }
        manager.save_staging(data)

        assert manager.can_modify('other-session') is False

    def test_validate_or_acquire_lock_no_staging(self, temp_config_dir):
        """Test validate_or_acquire_lock returns True when no staging."""
        manager = StagingManager(temp_config_dir)
        assert manager.validate_or_acquire_lock('new-session') is True

    def test_validate_or_acquire_lock_owner(self, temp_config_dir):
        """Test validate_or_acquire_lock returns True for owner."""
        manager = StagingManager(temp_config_dir)
        data = {
            'sessionId': 'owner-session',
            'pendingEdits': [[1, {}]],
            'stagedMoves': [],
            'stagedCreations': []
        }
        manager.save_staging(data)

        assert manager.validate_or_acquire_lock('owner-session') is True

    def test_validate_or_acquire_lock_other(self, temp_config_dir):
        """Test validate_or_acquire_lock returns False for non-owner."""
        manager = StagingManager(temp_config_dir)
        data = {
            'sessionId': 'owner-session',
            'pendingEdits': [[1, {}]],
            'stagedMoves': [],
            'stagedCreations': []
        }
        manager.save_staging(data)

        assert manager.validate_or_acquire_lock('other-session') is False

    def test_get_lock_status_no_staging(self, temp_config_dir):
        """Test get_lock_status when no staging exists."""
        manager = StagingManager(temp_config_dir)
        status = manager.get_lock_status('any-session')

        assert status['locked'] is False
        assert status['owner'] is None
        assert status['isOwner'] is False

    def test_get_lock_status_is_owner(self, temp_config_dir):
        """Test get_lock_status when requesting session is owner."""
        manager = StagingManager(temp_config_dir)
        data = {
            'sessionId': 'my-session',
            'pendingEdits': [[1, {}]],
            'stagedMoves': [],
            'stagedCreations': []
        }
        manager.save_staging(data)

        status = manager.get_lock_status('my-session')

        assert status['locked'] is True
        assert status['owner'] == 'my-session'
        assert status['isOwner'] is True

    def test_get_lock_status_not_owner(self, temp_config_dir):
        """Test get_lock_status when requesting session is not owner."""
        manager = StagingManager(temp_config_dir)
        data = {
            'sessionId': 'owner-session',
            'pendingEdits': [[1, {}]],
            'stagedMoves': [],
            'stagedCreations': []
        }
        manager.save_staging(data)

        status = manager.get_lock_status('other-session')

        assert status['locked'] is True
        assert status['owner'] == 'owner-session'
        assert status['isOwner'] is False


class TestStableKeyOperations:
    """Tests for stable key utility functions."""

    def test_generate_stable_key(self):
        """Test generating stable keys."""
        from staging_manager import generate_stable_key

        key = generate_stable_key('/etc/nagios/hosts.cfg', 'host', 'webserver01')
        assert key == '/etc/nagios/hosts.cfg|host|webserver01'

    def test_generate_stable_key_with_special_chars(self):
        """Test stable keys with special characters in name."""
        from staging_manager import generate_stable_key

        key = generate_stable_key('/etc/nagios/services.cfg', 'service', 'HTTP Check - Port 80')
        assert key == '/etc/nagios/services.cfg|service|HTTP Check - Port 80'

    def test_parse_stable_key(self):
        """Test parsing stable keys."""
        from staging_manager import parse_stable_key

        result = parse_stable_key('/etc/nagios/hosts.cfg|host|webserver01')
        assert result == {
            'source_file': '/etc/nagios/hosts.cfg',
            'object_type': 'host',
            'name': 'webserver01'
        }

    def test_parse_stable_key_invalid(self):
        """Test parsing invalid stable keys."""
        from staging_manager import parse_stable_key

        # Too few parts
        assert parse_stable_key('invalid') is None
        assert parse_stable_key('only|two') is None

        # Too many parts (pipes in filename)
        result = parse_stable_key('a|b|c|d')
        assert result is None

    def test_get_object_name_host(self):
        """Test getting object name for hosts."""
        from staging_manager import get_object_name

        attrs = {'host_name': 'webserver01', 'address': '192.168.1.1'}
        assert get_object_name('host', attrs) == 'webserver01'

    def test_get_object_name_service(self):
        """Test getting object name for services."""
        from staging_manager import get_object_name

        attrs = {'service_description': 'HTTP Check', 'host_name': 'webserver01'}
        assert get_object_name('service', attrs) == 'HTTP Check'

    def test_get_object_name_command(self):
        """Test getting object name for commands."""
        from staging_manager import get_object_name

        attrs = {'command_name': 'check_http', 'command_line': '/usr/lib/nagios/plugins/check_http'}
        assert get_object_name('command', attrs) == 'check_http'

    def test_get_object_name_template(self):
        """Test getting object name for templates (uses 'name' field)."""
        from staging_manager import get_object_name

        attrs = {'name': 'generic-host', 'register': '0'}
        assert get_object_name('host', attrs) == 'generic-host'

    def test_get_object_name_missing(self):
        """Test getting object name when not found."""
        from staging_manager import get_object_name

        attrs = {'address': '192.168.1.1'}
        assert get_object_name('host', attrs) == ''

    def test_get_object_name_all_types(self):
        """Test getting object name for all standard types."""
        from staging_manager import get_object_name

        test_cases = [
            ('host', {'host_name': 'test-host'}),
            ('hostgroup', {'hostgroup_name': 'test-hg'}),
            ('service', {'service_description': 'test-svc'}),
            ('servicegroup', {'servicegroup_name': 'test-sg'}),
            ('contact', {'contact_name': 'test-contact'}),
            ('contactgroup', {'contactgroup_name': 'test-cg'}),
            ('command', {'command_name': 'test-cmd'}),
            ('timeperiod', {'timeperiod_name': 'test-tp'}),
        ]

        for obj_type, attrs in test_cases:
            name = get_object_name(obj_type, attrs)
            assert name.startswith('test-'), f"Failed for {obj_type}"
