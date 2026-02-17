"""Tests for backup_manager module."""

import os
import time
import zipfile
from pathlib import Path

import pytest

from backup_manager import BackupManager


@pytest.fixture
def backup_env(tmp_path):
    """Create a config dir with .cfg files and a separate backup dir."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    (config_dir / "hosts.cfg").write_text(
        "define host { host_name web-01\n address 10.0.0.1 }\n")
    (config_dir / "commands.cfg").write_text(
        "define command { command_name check_ping\n"
        " command_line /usr/lib/nagios/plugins/check_ping }\n")

    bm = BackupManager(str(config_dir), str(backup_dir))
    return bm, config_dir, backup_dir


class TestCreateBackup:
    """Tests for BackupManager.create_backup."""

    def test_creates_zip_with_cfg_files(self, backup_env):
        bm, config_dir, backup_dir = backup_env
        zip_path = bm.create_backup("test backup")
        assert os.path.exists(zip_path)
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            cfg_files = [n for n in names if n.endswith(".cfg")]
            assert len(cfg_files) == 2
            assert any("hosts.cfg" in n for n in cfg_files)
            assert any("commands.cfg" in n for n in cfg_files)

    def test_includes_metadata(self, backup_env):
        bm, _, _ = backup_env
        zip_path = bm.create_backup("my description")
        with zipfile.ZipFile(zip_path, "r") as zf:
            assert "_backup_info.txt" in zf.namelist()
            metadata = zf.read("_backup_info.txt").decode("utf-8")
            assert "my description" in metadata
            assert "Files backed up: 2" in metadata

    def test_skips_symlinks(self, backup_env):
        bm, config_dir, _ = backup_env
        # Create a symlink to a .cfg file
        target = config_dir / "hosts.cfg"
        link = config_dir / "link.cfg"
        link.symlink_to(target)

        zip_path = bm.create_backup("symlink test")
        with zipfile.ZipFile(zip_path, "r") as zf:
            cfg_names = [n for n in zf.namelist() if n.endswith(".cfg")]
            assert not any("link.cfg" in n for n in cfg_names)

    def test_backup_path_equals_config_path_raises(self, tmp_path):
        with pytest.raises(ValueError, match="must not equal"):
            BackupManager(str(tmp_path), str(tmp_path))


class TestListBackups:
    """Tests for BackupManager.list_backups."""

    def test_empty_directory(self, backup_env):
        bm, _, _ = backup_env
        backups = bm.list_backups()
        assert backups == []

    def test_lists_multiple_sorted_by_date(self, backup_env):
        bm, _, _ = backup_env
        bm.create_backup("first")
        time.sleep(0.05)  # Ensure different timestamps
        bm.create_backup("second")
        backups = bm.list_backups()
        assert len(backups) == 2
        # Most recent first
        assert "second" in backups[0]["name"]
        assert "first" in backups[1]["name"]


class TestRestoreBackup:
    """Tests for BackupManager.restore_backup."""

    def test_round_trip(self, backup_env):
        bm, config_dir, _ = backup_env
        original_hosts = (config_dir / "hosts.cfg").read_text()
        original_commands = (config_dir / "commands.cfg").read_text()

        zip_path = bm.create_backup("before change")
        backup_name = os.path.basename(zip_path)

        # Modify config files
        (config_dir / "hosts.cfg").write_text("MODIFIED CONTENT")
        (config_dir / "commands.cfg").write_text("ALSO MODIFIED")

        result = bm.restore_backup(backup_name)
        assert result["files_restored"] == 2

        # Verify files are restored to originals
        assert (config_dir / "hosts.cfg").read_text() == original_hosts
        assert (config_dir / "commands.cfg").read_text() == original_commands

    def test_path_traversal_in_backup_name_blocked(self, backup_env):
        bm, _, _ = backup_env
        with pytest.raises(ValueError, match="Invalid backup name"):
            bm.restore_backup("../../etc/passwd")

    def test_nonexistent_backup_raises(self, backup_env):
        bm, _, _ = backup_env
        with pytest.raises(ValueError, match="Backup not found"):
            bm.restore_backup("nonexistent.zip")


class TestDeleteBackup:
    """Tests for BackupManager.delete_backup."""

    def test_delete_existing(self, backup_env):
        bm, _, _ = backup_env
        zip_path = bm.create_backup("to delete")
        name = os.path.basename(zip_path)
        assert bm.delete_backup(name) is True
        assert not os.path.exists(zip_path)

    def test_delete_nonexistent_returns_false(self, backup_env):
        bm, _, _ = backup_env
        assert bm.delete_backup("nonexistent.zip") is False

    def test_path_traversal_blocked(self, backup_env):
        bm, _, _ = backup_env
        with pytest.raises(ValueError, match="Invalid backup name"):
            bm.delete_backup("../../../etc/passwd")


class TestCleanupOldBackups:
    """Tests for BackupManager.cleanup_old_backups."""

    def test_keeps_recent_deletes_old(self, backup_env):
        bm, _, _ = backup_env
        for i in range(5):
            bm.create_backup(f"backup-{i}")
            time.sleep(0.02)  # Ensure different timestamps

        deleted = bm.cleanup_old_backups(keep_count=3)
        assert deleted == 2
        assert len(bm.list_backups()) == 3
