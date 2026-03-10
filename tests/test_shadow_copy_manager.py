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
