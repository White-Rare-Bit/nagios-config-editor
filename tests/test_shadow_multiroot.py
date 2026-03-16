import json
import os

from shadow_copy_manager import ShadowCopyManager


class TestMultiRootShadow:
    def test_create_shadow_copies_all_roots(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "hosts.cfg").write_text("define host { host_name h1 }\n")
        (dir_b / "services.cfg").write_text("define service { service_description s1 }\n")
        shadow_base = tmp_path / "shadow"

        sm = ShadowCopyManager(
            cfg_dirs=[str(dir_a), str(dir_b)],
            shadow_base_path=str(shadow_base),
        )
        result = sm.create_shadow("sess1", "user", "user@test.com")
        assert result.success
        assert sm.has_shadow()

        # Both files should exist in shadow
        root_map = sm.get_root_map()
        assert len(root_map) == 2

    def test_root_map_json_created(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        (dir_a / "hosts.cfg").write_text("define host {}\n")
        shadow_base = tmp_path / "shadow"

        sm = ShadowCopyManager(cfg_dirs=[str(dir_a)], shadow_base_path=str(shadow_base))
        sm.create_shadow("sess1", "user", "user@test.com")

        root_map_path = os.path.join(str(shadow_base), "root_map.json")
        assert os.path.exists(root_map_path)
        with open(root_map_path) as f:
            root_map = json.load(f)
        assert len(root_map) == 1
        assert str(dir_a.resolve()) in root_map.values()

    def test_shadow_path_resolves_correctly(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        (dir_a / "hosts.cfg").write_text("define host {}\n")
        shadow_base = tmp_path / "shadow"

        sm = ShadowCopyManager(cfg_dirs=[str(dir_a)], shadow_base_path=str(shadow_base))
        sm.create_shadow("sess1", "user", "user@test.com")

        # shadow_path should return path within the shadow config dir
        sp = sm.shadow_path_for(str(dir_a.resolve() / "hosts.cfg"))
        assert os.path.exists(sp)

    def test_original_path_resolves_correctly(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        (dir_a / "hosts.cfg").write_text("define host {}\n")
        shadow_base = tmp_path / "shadow"

        sm = ShadowCopyManager(cfg_dirs=[str(dir_a)], shadow_base_path=str(shadow_base))
        sm.create_shadow("sess1", "user", "user@test.com")

        sp = sm.shadow_path_for(str(dir_a.resolve() / "hosts.cfg"))
        op = sm.original_path_for(sp)
        assert op == str(dir_a.resolve() / "hosts.cfg")

    def test_apply_writes_to_correct_roots(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        (dir_a / "hosts.cfg").write_text("original\n")
        shadow_base = tmp_path / "shadow"

        sm = ShadowCopyManager(cfg_dirs=[str(dir_a)], shadow_base_path=str(shadow_base))
        sm.create_shadow("sess1", "user", "user@test.com")

        # Modify file in shadow
        sp = sm.shadow_path_for(str(dir_a.resolve() / "hosts.cfg"))
        with open(sp, "w") as f:
            f.write("modified\n")

        result = sm.apply(force=True)
        assert result.success

        # Original should now be modified
        assert (dir_a / "hosts.cfg").read_text() == "modified\n"

    def test_protected_files_excluded(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        (dir_a / "hosts.cfg").write_text("define host {}\n")
        (dir_a / "nagios.cfg").write_text("cfg_dir=.\n")
        (dir_a / "cgi.cfg").write_text("some=setting\n")
        shadow_base = tmp_path / "shadow"

        sm = ShadowCopyManager(cfg_dirs=[str(dir_a)], shadow_base_path=str(shadow_base))
        sm.create_shadow("sess1", "user", "user@test.com")

        # Protected files should not be in shadow
        sp_nagios = sm.shadow_path_for(str(dir_a.resolve() / "nagios.cfg"))
        sp_cgi = sm.shadow_path_for(str(dir_a.resolve() / "cgi.cfg"))
        assert not os.path.exists(sp_nagios)
        assert not os.path.exists(sp_cgi)

    def test_backward_compat_single_config_path(self, tmp_path):
        (tmp_path / "hosts.cfg").write_text("define host {}\n")
        shadow_base = tmp_path / "shadow"

        sm = ShadowCopyManager(config_path=str(tmp_path), shadow_base_path=str(shadow_base))
        result = sm.create_shadow("sess1", "user", "user@test.com")
        assert result.success
