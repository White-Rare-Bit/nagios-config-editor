"""Tests for backup_manager module."""

import os
import time
import zipfile

import pytest

from app.backup_manager import BackupManager


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


class TestBackupCreationTriggersCleanup:
    """Verify the /api/backups POST route auto-cleans old backups."""

    def test_old_backups_cleaned_after_create(self, client, app):
        """Creating a backup via API should trigger cleanup_old_backups."""
        from unittest.mock import patch

        with app.app_context():
            bm = app.extensions["backup"]

        with patch.object(bm, "cleanup_old_backups", wraps=bm.cleanup_old_backups) as mock_cleanup:
            resp = client.post("/api/backups", json={"description": "trigger cleanup"})
            assert resp.status_code == 200
            mock_cleanup.assert_called_once_with(keep_count=20)


class TestMultiRootBackup:
    """A backup covers every config root and restores each file where it came from."""

    def _roots(self, tmp_path):
        a = tmp_path / "servers"
        b = tmp_path / "switches"
        a.mkdir()
        b.mkdir()
        (a / "hosts.cfg").write_text("A-ORIGINAL")
        (b / "hosts.cfg").write_text("B-ORIGINAL")
        (b / "sub").mkdir()
        (b / "sub" / "more.cfg").write_text("B-SUB")
        return a, b

    def test_round_trip_two_roots(self, tmp_path):
        a, b = self._roots(tmp_path)
        bm = BackupManager(str(a), str(tmp_path / "backups"), cfg_dirs=[str(a), str(b)])
        name = os.path.basename(bm.create_backup("both"))
        assert bm.list_backups()[0]["file_count"] == 3

        (a / "hosts.cfg").write_text("A-CHANGED")
        (b / "hosts.cfg").write_text("B-CHANGED")
        (b / "sub" / "more.cfg").unlink()
        (b / "new.cfg").write_text("B-NEW")

        result = bm.restore_backup(name)

        assert result["files_restored"] == 3
        assert (a / "hosts.cfg").read_text() == "A-ORIGINAL"
        assert (b / "hosts.cfg").read_text() == "B-ORIGINAL"
        assert (b / "sub" / "more.cfg").read_text() == "B-SUB"
        assert not (b / "new.cfg").exists()

    def test_same_file_name_in_two_roots_does_not_collide(self, tmp_path):
        a, b = self._roots(tmp_path)
        bm = BackupManager(str(a), str(tmp_path / "backups"), cfg_dirs=[str(a), str(b)])
        with zipfile.ZipFile(bm.create_backup("both")) as zf:
            names = sorted(n for n in zf.namelist() if n.endswith(".cfg"))
        assert names == ["root_0/hosts.cfg", "root_1/hosts.cfg", "root_1/sub/more.cfg"]

    def test_nested_root_is_backed_up_once(self, tmp_path):
        a, _b = self._roots(tmp_path)
        (a / "inner").mkdir()
        (a / "inner" / "x.cfg").write_text("X")
        bm = BackupManager(str(a), str(tmp_path / "backups"), cfg_dirs=[str(a), str(a / "inner")])
        bm.create_backup("nested")
        assert bm.list_backups()[0]["file_count"] == 2

    def test_restore_never_writes_to_a_directory_that_is_not_a_root(self, tmp_path):
        a, b = self._roots(tmp_path)
        both = BackupManager(str(a), str(tmp_path / "backups"), cfg_dirs=[str(a), str(b)])
        name = os.path.basename(both.create_backup("both"))
        (b / "hosts.cfg").write_text("B-CHANGED")

        only_a = BackupManager(str(a), str(tmp_path / "backups"))
        result = only_a.restore_backup(name)

        assert (b / "hosts.cfg").read_text() == "B-CHANGED"
        assert result["files_restored"] == 1
        assert result["files_skipped"] == 2

    def test_single_root_backup_made_before_multi_root_still_restores(self, tmp_path):
        """Old backups hold files relative to the primary directory, no root table."""
        a, b = self._roots(tmp_path)
        old = BackupManager(str(a), str(tmp_path / "backups"))
        name = os.path.basename(old.create_backup("old"))
        with zipfile.ZipFile(tmp_path / "backups" / name) as zf:
            assert "hosts.cfg" in zf.namelist()
        (a / "hosts.cfg").write_text("A-CHANGED")
        (b / "hosts.cfg").write_text("B-CHANGED")

        now = BackupManager(str(a), str(tmp_path / "backups"), cfg_dirs=[str(a), str(b)])
        now.restore_backup(name)

        assert (a / "hosts.cfg").read_text() == "A-ORIGINAL"
        assert (b / "hosts.cfg").read_text() == "B-CHANGED", "an old backup knows nothing about other roots"

    def test_primary_dir_inside_a_larger_root(self, tmp_path):
        """primary_dir may be a subdirectory of a config root; files must go back
        to where they were, not one level off."""
        outer = tmp_path / "etc"
        primary = outer / "objects"
        primary.mkdir(parents=True)
        (outer / "top.cfg").write_text("TOP")
        (primary / "hosts.cfg").write_text("HOSTS")
        bm = BackupManager(str(primary), str(tmp_path / "backups"), cfg_dirs=[str(outer)])
        name = os.path.basename(bm.create_backup("nested-primary"))
        (outer / "top.cfg").write_text("CHANGED")
        (primary / "hosts.cfg").write_text("CHANGED")

        bm.restore_backup(name)

        assert (outer / "top.cfg").read_text() == "TOP"
        assert (primary / "hosts.cfg").read_text() == "HOSTS"
        assert not (outer / "hosts.cfg").exists()

    def test_old_backup_restores_into_primary_dir_even_inside_a_larger_root(self, tmp_path):
        outer = tmp_path / "etc"
        primary = outer / "objects"
        primary.mkdir(parents=True)
        (outer / "top.cfg").write_text("TOP")
        (primary / "hosts.cfg").write_text("HOSTS")
        old = BackupManager(str(primary), str(tmp_path / "backups"))
        name = os.path.basename(old.create_backup("old"))
        (primary / "hosts.cfg").write_text("CHANGED")

        now = BackupManager(str(primary), str(tmp_path / "backups"), cfg_dirs=[str(outer)])
        now.restore_backup(name)

        assert (primary / "hosts.cfg").read_text() == "HOSTS"
        assert (outer / "top.cfg").read_text() == "TOP", "files outside the old backup's directory are left alone"
        assert not (outer / "hosts.cfg").exists()
