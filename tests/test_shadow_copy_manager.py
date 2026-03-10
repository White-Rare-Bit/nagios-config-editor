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
