import json
import os
import shutil
import tempfile
import pytest
from shadow_copy_manager import ShadowCopyManager


@pytest.fixture
def setup_dirs():
    """Create temp config and shadow directories."""
    config_dir = tempfile.mkdtemp()
    shadow_base = tempfile.mkdtemp()
    # Create a sample config file
    os.makedirs(os.path.join(config_dir, "subdir"))
    with open(os.path.join(config_dir, "hosts.cfg"), "w") as f:
        f.write("define host {\n    host_name webserver1\n}\n")
    with open(os.path.join(config_dir, "subdir", "services.cfg"), "w") as f:
        f.write("define service {\n    service_description HTTP\n}\n")
    yield config_dir, shadow_base
    shutil.rmtree(config_dir, ignore_errors=True)
    shutil.rmtree(shadow_base, ignore_errors=True)


class TestShadowLifecycle:
    def test_has_shadow_initially_false(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        assert scm.has_shadow() is False

    def test_create_shadow_copies_all_cfg_files(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        result = scm.create_shadow("session-1", "user", "user@test.com")
        assert result.success
        assert scm.has_shadow()
        # Verify files copied
        shadow_hosts = os.path.join(shadow_base, "config", "hosts.cfg")
        shadow_services = os.path.join(shadow_base, "config", "subdir", "services.cfg")
        assert os.path.exists(shadow_hosts)
        assert os.path.exists(shadow_services)

    def test_create_shadow_when_already_exists_fails(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("session-1", "user", "user@test.com")
        result = scm.create_shadow("session-2", "user2", "user2@test.com")
        assert not result.success

    def test_destroy_shadow(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("session-1", "user", "user@test.com")
        result = scm.destroy_shadow()
        assert result.success
        assert scm.has_shadow() is False

    def test_destroy_when_no_shadow_succeeds(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        result = scm.destroy_shadow()
        assert result.success

    def test_create_shadow_stores_checksums(self, setup_dirs):
        """create_shadow should hash all .cfg files and write checksums.json."""
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")

        checksums_path = os.path.join(shadow_base, "checksums.json")
        assert os.path.isfile(checksums_path), "checksums.json not created"

        with open(checksums_path) as f:
            checksums = json.load(f)

        # Should have an entry for each .cfg file in config_dir
        cfg_files = []
        for root, _dirs, files in os.walk(config_dir):
            for fn in files:
                if fn.endswith(".cfg"):
                    cfg_files.append(os.path.relpath(os.path.join(root, fn), config_dir))

        assert set(checksums.keys()) == set(cfg_files)
        # Each value should be a 64-char hex string (SHA-256)
        for path, digest in checksums.items():
            assert len(digest) == 64, f"Bad checksum for {path}: {digest}"


class TestLockManagement:
    def test_lock_created_with_shadow(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("session-1", "Alice", "alice@test.com")
        status = scm.get_lock_status()
        assert status["locked"] is True
        assert status["session_id"] == "session-1"
        assert status["user_name"] == "Alice"

    def test_can_modify_correct_session(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("session-1", "Alice", "alice@test.com")
        assert scm.can_modify("session-1") is True
        assert scm.can_modify("session-2") is False

    def test_can_modify_when_no_shadow(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        assert scm.can_modify("any-session") is True

    def test_break_lock_destroys_shadow(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("session-1", "Alice", "alice@test.com")
        result = scm.break_lock()
        assert result.success
        assert scm.has_shadow() is False

    def test_get_lock_status_when_unlocked(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        status = scm.get_lock_status()
        assert status["locked"] is False


class TestUndoSnapshots:
    def test_snapshot_files_creates_copy(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        snapshot_id = scm.snapshot_files(["hosts.cfg"], "edit host")
        assert snapshot_id is not None
        assert scm.get_undo_count() == 1

    def test_undo_restores_file(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        # Read original content
        shadow_file = scm.shadow_path("hosts.cfg")
        with open(shadow_file) as f:
            original = f.read()
        # Snapshot before mutation
        scm.snapshot_files(["hosts.cfg"], "edit host")
        # Mutate
        with open(shadow_file, "w") as f:
            f.write("modified content")
        # Undo
        result = scm.undo()
        assert result.success
        with open(shadow_file) as f:
            assert f.read() == original
        assert scm.get_undo_count() == 0

    def test_multiple_undos_in_order(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        shadow_file = scm.shadow_path("hosts.cfg")
        with open(shadow_file) as f:
            v1 = f.read()
        # First edit
        scm.snapshot_files(["hosts.cfg"], "edit 1")
        with open(shadow_file, "w") as f:
            f.write("v2")
        # Second edit
        scm.snapshot_files(["hosts.cfg"], "edit 2")
        with open(shadow_file, "w") as f:
            f.write("v3")
        assert scm.get_undo_count() == 2
        # Undo second
        scm.undo()
        with open(shadow_file) as f:
            assert f.read() == "v2"
        # Undo first
        scm.undo()
        with open(shadow_file) as f:
            assert f.read() == v1

    def test_undo_when_empty_fails(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        result = scm.undo()
        assert not result.success

    def test_snapshot_multiple_files(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        scm.snapshot_files(["hosts.cfg", "subdir/services.cfg"], "bulk edit")
        assert scm.get_undo_count() == 1

    def test_snapshot_nonexistent_file_for_creation_undo(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        # Snapshot a file that doesn't exist yet (for undoing creation)
        scm.snapshot_files(["new_file.cfg"], "create file")
        # Create the file
        new_path = scm.shadow_path("new_file.cfg")
        with open(new_path, "w") as f:
            f.write("new content")
        # Undo should delete the file
        result = scm.undo()
        assert result.success
        assert not os.path.exists(new_path)


class TestDiffComputation:
    def test_no_changes_empty_diff(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        changed = scm.get_changed_files()
        assert changed == []

    def test_modified_file_detected(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        # Modify a file in shadow
        shadow_file = scm.shadow_path("hosts.cfg")
        with open(shadow_file, "w") as f:
            f.write("modified content\n")
        changed = scm.get_changed_files()
        assert len(changed) == 1
        assert changed[0]["path"] == "hosts.cfg"
        assert changed[0]["status"] == "modified"

    def test_new_file_detected(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        # Create new file in shadow
        new_path = scm.shadow_path("new.cfg")
        with open(new_path, "w") as f:
            f.write("define host {\n    host_name new\n}\n")
        changed = scm.get_changed_files()
        assert len(changed) == 1
        assert changed[0]["path"] == "new.cfg"
        assert changed[0]["status"] == "added"

    def test_deleted_file_detected(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        # Delete file from shadow
        os.remove(scm.shadow_path("hosts.cfg"))
        changed = scm.get_changed_files()
        assert len(changed) == 1
        assert changed[0]["path"] == "hosts.cfg"
        assert changed[0]["status"] == "deleted"

    def test_get_file_diff_returns_unified_diff(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        shadow_file = scm.shadow_path("hosts.cfg")
        with open(shadow_file, "w") as f:
            f.write("define host {\n    host_name webserver1\n    alias Modified\n}\n")
        diff = scm.get_file_diff("hosts.cfg")
        assert "alias" in diff["diff_text"]

    def test_object_aware_diff_keeps_blocks_atomic(self, setup_dirs):
        """Removing middle object should not split surrounding objects' boundaries.

        Real Nagios services share many identical lines (use, host_name, contacts).
        Line-level diff cross-matches these shared lines across object boundaries,
        making the Memory block appear partially removed. Object-aware chunking
        treats each define block as an atom, preventing this.
        """
        config_dir, shadow_base = setup_dirs
        original_content = (
            "define service {\n"
            "    use                    generic-service\n"
            "    host_name              webserver1\n"
            "    service_description    CPU Load\n"
            "    check_command          check_nrpe!check_cpu\n"
            "    contacts               admin\n"
            "}\n"
            "\n"
            "define service {\n"
            "    use                    generic-service\n"
            "    host_name              webserver1\n"
            "    service_description    Disk Usage\n"
            "    check_command          check_nrpe!check_disk\n"
            "    contacts               admin\n"
            "}\n"
            "\n"
            "define service {\n"
            "    use                    generic-service\n"
            "    host_name              webserver1\n"
            "    service_description    Memory\n"
            "    check_command          check_nrpe!check_mem\n"
            "    contacts               admin\n"
            "}\n"
        )
        with open(os.path.join(config_dir, "services.cfg"), "w") as f:
            f.write(original_content)

        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")

        # Shadow: middle object (Disk Usage) removed
        shadow_content = (
            "define service {\n"
            "    use                    generic-service\n"
            "    host_name              webserver1\n"
            "    service_description    CPU Load\n"
            "    check_command          check_nrpe!check_cpu\n"
            "    contacts               admin\n"
            "}\n"
            "\n"
            "define service {\n"
            "    use                    generic-service\n"
            "    host_name              webserver1\n"
            "    service_description    Memory\n"
            "    check_command          check_nrpe!check_mem\n"
            "    contacts               admin\n"
            "}\n"
        )
        with open(scm.shadow_path("services.cfg"), "w") as f:
            f.write(shadow_content)

        diff = scm.get_file_diff("services.cfg")
        diff_text = diff["diff_text"]

        # With object-aware diff, the entire Disk block is removed atomically:
        # 'define service {' appears BEFORE 'Disk Usage' in removed lines.
        # With line-level diff, 'define service {' is cross-matched as context
        # and 'Disk Usage' appears BEFORE 'define service {' in removed lines
        # (the 'define service {' that IS removed belongs to the Memory block).
        removed = [l for l in diff_text.splitlines()
                   if l.startswith("-") and not l.startswith("---")]
        define_idx = next((i for i, l in enumerate(removed) if "define service" in l), None)
        disk_idx = next((i for i, l in enumerate(removed) if "Disk Usage" in l), None)
        assert define_idx is not None and disk_idx is not None, (
            f"Expected both 'define service' and 'Disk Usage' in removed lines: {removed}"
        )
        assert define_idx < disk_idx, (
            "Object-aware diff should remove the whole Disk block atomically "
            "(define service { before Disk Usage), but got split boundaries"
        )

    def test_reorder_objects_shows_atomic_moves(self, setup_dirs):
        """Reordering objects should show whole blocks as added/removed, not interleaved."""
        config_dir, shadow_base = setup_dirs

        original = (
            "define host {\n"
            "    host_name    alpha\n"
            "    alias        Alpha Server\n"
            "}\n"
            "\n"
            "define host {\n"
            "    host_name    beta\n"
            "    alias        Beta Server\n"
            "}\n"
        )
        # Shadow: reversed order
        shadow = (
            "define host {\n"
            "    host_name    beta\n"
            "    alias        Beta Server\n"
            "}\n"
            "\n"
            "define host {\n"
            "    host_name    alpha\n"
            "    alias        Alpha Server\n"
            "}\n"
        )

        os.makedirs(config_dir, exist_ok=True)
        with open(os.path.join(config_dir, "hosts.cfg"), "w") as f:
            f.write(original)

        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")

        with open(scm.shadow_path("hosts.cfg"), "w") as f:
            f.write(shadow)

        diff = scm.get_file_diff("hosts.cfg")
        diff_text = diff["diff_text"]

        # Every line containing "alpha" should have the same prefix (all + or all -)
        # i.e., the alpha block was not split
        alpha_prefixes = set()
        for line in diff_text.split("\n"):
            if "alpha" in line.lower() and (line.startswith("+") or line.startswith("-")):
                alpha_prefixes.add(line[0])
        # If the block is atomic, all alpha lines have the same prefix
        assert len(alpha_prefixes) <= 1, f"Alpha block was split across +/-: {alpha_prefixes}"

    def test_get_changed_object_count(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        # Modify shadow file
        shadow_file = scm.shadow_path("hosts.cfg")
        with open(shadow_file, "w") as f:
            f.write("define host {\n    host_name webserver1\n    alias Modified\n}\n")
        count = scm.get_changed_object_count()
        assert count >= 1


class TestApply:
    def test_apply_copies_modified_files(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        # Modify shadow
        with open(scm.shadow_path("hosts.cfg"), "w") as f:
            f.write("modified\n")
        result = scm.apply()
        assert result.success
        # Original should now have modified content
        with open(os.path.join(config_dir, "hosts.cfg")) as f:
            assert f.read() == "modified\n"
        # Shadow should be destroyed
        assert not scm.has_shadow()

    def test_apply_handles_new_files(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        with open(scm.shadow_path("new.cfg"), "w") as f:
            f.write("new content\n")
        result = scm.apply()
        assert result.success
        assert os.path.exists(os.path.join(config_dir, "new.cfg"))

    def test_apply_handles_deleted_files(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        os.remove(scm.shadow_path("hosts.cfg"))
        result = scm.apply()
        assert result.success
        assert not os.path.exists(os.path.join(config_dir, "hosts.cfg"))

    def test_apply_handles_new_subdirectory(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        new_dir = os.path.join(scm.shadow_path(""), "newdir")
        os.makedirs(new_dir)
        with open(os.path.join(new_dir, "test.cfg"), "w") as f:
            f.write("content\n")
        result = scm.apply()
        assert result.success
        assert os.path.exists(os.path.join(config_dir, "newdir", "test.cfg"))

    def test_apply_with_no_changes(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        result = scm.apply()
        assert result.success
        assert not scm.has_shadow()

    def test_apply_creates_backup_when_manager_provided(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        from backup_manager import BackupManager
        backup_path = tempfile.mkdtemp()
        bm = BackupManager(config_dir, backup_path)
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        with open(scm.shadow_path("hosts.cfg"), "w") as f:
            f.write("modified\n")
        result = scm.apply(backup_manager=bm)
        assert result.success
        backups = bm.list_backups()
        assert len(backups) >= 1
        shutil.rmtree(backup_path, ignore_errors=True)
