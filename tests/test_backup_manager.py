"""
Tests for backup_manager.py - Backup Manager
"""

import pytest
import os
import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backup_manager import BackupManager


class TestBackupManager:
    """Tests for the BackupManager class."""

    def test_init_default_backup_path(self, temp_config_dir):
        """Test initialization with default backup path."""
        manager = BackupManager(temp_config_dir)
        expected_backup_path = Path(temp_config_dir) / 'backups'
        assert manager.backup_path == expected_backup_path

    def test_init_custom_backup_path(self, temp_config_dir):
        """Test initialization with custom backup path."""
        custom_path = os.path.join(temp_config_dir, 'custom_backups')
        manager = BackupManager(temp_config_dir, backup_path=custom_path)
        assert manager.backup_path == Path(custom_path)

    def test_create_backup(self, temp_config_dir):
        """Test creating a backup."""
        # Create a config file to backup
        config_file = os.path.join(temp_config_dir, 'hosts.cfg')
        with open(config_file, 'w') as f:
            f.write('define host { host_name test-server }')

        manager = BackupManager(temp_config_dir)
        backup_path = manager.create_backup()

        assert os.path.exists(backup_path)
        assert 'backup_' in backup_path
        assert backup_path.endswith('.zip')

        # Check that the config file was backed up inside the zip
        with zipfile.ZipFile(backup_path, 'r') as zf:
            assert 'hosts.cfg' in zf.namelist()

    def test_create_backup_with_description(self, temp_config_dir):
        """Test creating a backup with description."""
        config_file = os.path.join(temp_config_dir, 'hosts.cfg')
        with open(config_file, 'w') as f:
            f.write('define host { host_name test-server }')

        manager = BackupManager(temp_config_dir)
        backup_path = manager.create_backup(description='Before major changes')

        assert 'Before_major_changes' in backup_path or 'before_major_changes' in backup_path.lower()

    def test_create_backup_preserves_directory_structure(self, temp_config_dir):
        """Test that backup preserves subdirectory structure."""
        # Create nested config files
        subdir = os.path.join(temp_config_dir, 'servers')
        os.makedirs(subdir)
        config_file = os.path.join(subdir, 'hosts.cfg')
        with open(config_file, 'w') as f:
            f.write('define host { host_name test-server }')

        manager = BackupManager(temp_config_dir)
        backup_path = manager.create_backup()

        # Check that the subdirectory structure is preserved inside the zip
        with zipfile.ZipFile(backup_path, 'r') as zf:
            assert 'servers/hosts.cfg' in zf.namelist()

    def test_create_backup_metadata(self, temp_config_dir):
        """Test that backup includes metadata file."""
        config_file = os.path.join(temp_config_dir, 'hosts.cfg')
        with open(config_file, 'w') as f:
            f.write('define host { host_name test-server }')

        manager = BackupManager(temp_config_dir)
        backup_path = manager.create_backup(description='Test backup')

        with zipfile.ZipFile(backup_path, 'r') as zf:
            assert '_backup_info.txt' in zf.namelist()
            content = zf.read('_backup_info.txt').decode('utf-8')
            assert 'Test backup' in content
            assert 'Files backed up:' in content

    def test_create_backup_skips_backup_directory(self, temp_config_dir):
        """Test that backup doesn't include previous backups."""
        # Create a config file
        config_file = os.path.join(temp_config_dir, 'hosts.cfg')
        with open(config_file, 'w') as f:
            f.write('define host { host_name test-server }')

        manager = BackupManager(temp_config_dir)

        # Create first backup
        first_backup = manager.create_backup(description='first')

        # Create second backup
        second_backup = manager.create_backup(description='second')

        # The second backup zip should not contain the first backup
        first_backup_name = os.path.basename(first_backup)
        with zipfile.ZipFile(second_backup, 'r') as zf:
            assert first_backup_name not in zf.namelist()
            # Should only contain hosts.cfg and _backup_info.txt
            cfg_files = [n for n in zf.namelist() if n.endswith('.cfg')]
            assert cfg_files == ['hosts.cfg']

    def test_list_backups_empty(self, temp_config_dir):
        """Test listing backups when none exist."""
        manager = BackupManager(temp_config_dir)
        backups = manager.list_backups()
        assert backups == []

    def test_list_backups(self, temp_config_dir):
        """Test listing backups."""
        config_file = os.path.join(temp_config_dir, 'hosts.cfg')
        with open(config_file, 'w') as f:
            f.write('define host { host_name test-server }')

        manager = BackupManager(temp_config_dir)

        # Create multiple backups
        manager.create_backup(description='first')
        time.sleep(0.1)  # Small delay to ensure different timestamps
        manager.create_backup(description='second')

        backups = manager.list_backups()
        assert len(backups) == 2
        # Should be sorted by creation time, most recent first
        assert 'second' in backups[0]['name'] or backups[0]['created'] >= backups[1]['created']

    def test_list_backups_with_metadata(self, temp_config_dir):
        """Test that list_backups includes metadata."""
        config_file = os.path.join(temp_config_dir, 'hosts.cfg')
        with open(config_file, 'w') as f:
            f.write('define host { host_name test-server }')

        manager = BackupManager(temp_config_dir)
        manager.create_backup(description='Test description')

        backups = manager.list_backups()
        assert len(backups) == 1
        assert backups[0]['description'] == 'Test description'
        assert backups[0]['file_count'] == 1
        assert backups[0]['created'] is not None

    def test_restore_backup(self, temp_config_dir):
        """Test restoring from a backup."""
        # Create initial config
        config_file = os.path.join(temp_config_dir, 'hosts.cfg')
        with open(config_file, 'w') as f:
            f.write('define host { host_name original-server }')

        manager = BackupManager(temp_config_dir)

        # Create backup of original
        backup_path = manager.create_backup(description='original')
        backup_name = os.path.basename(backup_path)

        # Modify the config
        with open(config_file, 'w') as f:
            f.write('define host { host_name modified-server }')

        # Restore from backup
        result = manager.restore_backup(backup_name)

        # Verify restoration
        with open(config_file, 'r') as f:
            content = f.read()
            assert 'original-server' in content

        assert result['restored_from'] == backup_name
        assert result['files_restored'] == 1

    def test_restore_backup_creates_safety_backup(self, temp_config_dir):
        """Test that restore creates a safety backup first."""
        config_file = os.path.join(temp_config_dir, 'hosts.cfg')
        with open(config_file, 'w') as f:
            f.write('define host { host_name test-server }')

        manager = BackupManager(temp_config_dir)
        backup_path = manager.create_backup()
        backup_name = os.path.basename(backup_path)

        result = manager.restore_backup(backup_name)

        assert 'safety_backup' in result
        assert os.path.exists(result['safety_backup'])

    def test_restore_backup_nonexistent(self, temp_config_dir):
        """Test restoring from a nonexistent backup."""
        manager = BackupManager(temp_config_dir)

        with pytest.raises(ValueError) as exc_info:
            manager.restore_backup('nonexistent_backup')

        assert 'not found' in str(exc_info.value).lower()

    def test_restore_backup_path_traversal_prevention(self, temp_config_dir):
        """Test that path traversal is prevented."""
        manager = BackupManager(temp_config_dir)

        with pytest.raises(ValueError):
            manager.restore_backup('../../../etc/passwd')

        with pytest.raises(ValueError):
            manager.restore_backup('/absolute/path')

    def test_delete_backup(self, temp_config_dir):
        """Test deleting a backup."""
        config_file = os.path.join(temp_config_dir, 'hosts.cfg')
        with open(config_file, 'w') as f:
            f.write('define host { host_name test-server }')

        manager = BackupManager(temp_config_dir)
        backup_path = manager.create_backup()
        backup_name = os.path.basename(backup_path)

        assert os.path.exists(backup_path)

        result = manager.delete_backup(backup_name)

        assert result is True
        assert not os.path.exists(backup_path)

    def test_delete_backup_nonexistent(self, temp_config_dir):
        """Test deleting a nonexistent backup."""
        manager = BackupManager(temp_config_dir)
        result = manager.delete_backup('nonexistent_backup')
        assert result is False

    def test_cleanup_old_backups(self, temp_config_dir):
        """Test cleaning up old backups."""
        config_file = os.path.join(temp_config_dir, 'hosts.cfg')
        with open(config_file, 'w') as f:
            f.write('define host { host_name test-server }')

        manager = BackupManager(temp_config_dir)

        # Create 5 backups
        for i in range(5):
            manager.create_backup(description=f'backup_{i}')
            time.sleep(0.05)  # Small delay to ensure different timestamps

        assert len(manager.list_backups()) == 5

        # Cleanup, keeping only 2
        deleted = manager.cleanup_old_backups(keep_count=2)

        assert deleted == 3
        assert len(manager.list_backups()) == 2

    def test_cleanup_old_backups_keeps_recent(self, temp_config_dir):
        """Test that cleanup keeps the most recent backups."""
        config_file = os.path.join(temp_config_dir, 'hosts.cfg')
        with open(config_file, 'w') as f:
            f.write('define host { host_name test-server }')

        manager = BackupManager(temp_config_dir)

        # Create backups with known order
        first = manager.create_backup(description='oldest')
        time.sleep(0.05)
        second = manager.create_backup(description='middle')
        time.sleep(0.05)
        third = manager.create_backup(description='newest')

        # Cleanup, keeping only 1
        manager.cleanup_old_backups(keep_count=1)

        backups = manager.list_backups()
        assert len(backups) == 1
        # Should keep the newest
        assert 'newest' in backups[0]['name']

    def test_backup_empty_directory(self, temp_config_dir):
        """Test backing up an empty configuration directory."""
        manager = BackupManager(temp_config_dir)
        backup_path = manager.create_backup()

        # Should still create backup zip with metadata
        assert os.path.exists(backup_path)
        with zipfile.ZipFile(backup_path, 'r') as zf:
            assert '_backup_info.txt' in zf.namelist()

    def test_backup_sanitizes_description(self, temp_config_dir):
        """Test that backup sanitizes special characters in description."""
        config_file = os.path.join(temp_config_dir, 'hosts.cfg')
        with open(config_file, 'w') as f:
            f.write('define host { host_name test-server }')

        manager = BackupManager(temp_config_dir)
        backup_path = manager.create_backup(description='test/backup:with<special>chars')

        # Should not have special characters in path
        assert '/' not in os.path.basename(backup_path).replace('backup_', '')
        assert ':' not in os.path.basename(backup_path)
        assert '<' not in os.path.basename(backup_path)
        assert '>' not in os.path.basename(backup_path)

    def test_backup_truncates_long_description(self, temp_config_dir):
        """Test that backup truncates very long descriptions."""
        config_file = os.path.join(temp_config_dir, 'hosts.cfg')
        with open(config_file, 'w') as f:
            f.write('define host { host_name test-server }')

        manager = BackupManager(temp_config_dir)
        long_description = 'a' * 100
        backup_path = manager.create_backup(description=long_description)

        # Backup name should be reasonable length
        backup_name = os.path.basename(backup_path)
        assert len(backup_name) < 100
