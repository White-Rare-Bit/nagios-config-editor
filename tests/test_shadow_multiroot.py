import json
import os

from app.shadow_copy_manager import ShadowCopyManager


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

        # Each root is mapped, and each root's file was actually copied
        root_map = sm.get_root_map()
        assert sorted(root_map.values()) == sorted([str(dir_a.resolve()), str(dir_b.resolve())])
        assert os.path.isfile(sm.physical_path(str(dir_a.resolve() / "hosts.cfg")))
        assert os.path.isfile(sm.physical_path(str(dir_b.resolve() / "services.cfg")))

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
        sp = sm.physical_path(str(dir_a.resolve() / "hosts.cfg"))
        assert os.path.exists(sp)

    def test_original_path_resolves_correctly(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        (dir_a / "hosts.cfg").write_text("define host {}\n")
        shadow_base = tmp_path / "shadow"

        sm = ShadowCopyManager(cfg_dirs=[str(dir_a)], shadow_base_path=str(shadow_base))
        sm.create_shadow("sess1", "user", "user@test.com")

        sp = sm.physical_path(str(dir_a.resolve() / "hosts.cfg"))
        op = sm.logical_path(sp)
        assert op == str(dir_a.resolve() / "hosts.cfg")

    def test_apply_writes_to_correct_roots(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        (dir_a / "hosts.cfg").write_text("original\n")
        shadow_base = tmp_path / "shadow"

        sm = ShadowCopyManager(cfg_dirs=[str(dir_a)], shadow_base_path=str(shadow_base))
        sm.create_shadow("sess1", "user", "user@test.com")

        # Modify file in shadow
        sp = sm.physical_path(str(dir_a.resolve() / "hosts.cfg"))
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
        sp_nagios = sm.physical_path(str(dir_a.resolve() / "nagios.cfg"))
        sp_cgi = sm.physical_path(str(dir_a.resolve() / "cgi.cfg"))
        assert not os.path.exists(sp_nagios)
        assert not os.path.exists(sp_cgi)

    def test_backward_compat_single_config_path(self, tmp_path):
        (tmp_path / "hosts.cfg").write_text("define host {}\n")
        shadow_base = tmp_path / "shadow"

        sm = ShadowCopyManager(config_path=str(tmp_path), shadow_base_path=str(shadow_base))
        result = sm.create_shadow("sess1", "user", "user@test.com")
        assert result.success
        shadow_file = sm.physical_path(str(tmp_path.resolve() / "hosts.cfg"))
        assert open(shadow_file).read() == "define host {}\n"


class TestPathMapping:
    """Logical (original) <-> physical (shadow) path conversion."""

    def _two_roots(self, tmp_path, shadow_base=None):
        # The first root has the longer path, so it is the one tried first.
        dir_a = tmp_path / "etc-main-config"
        dir_b = tmp_path / "extra"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "hosts.cfg").write_text("define host {\n    host_name a\n}\n")
        (dir_b / "hosts.cfg").write_text("define host {\n    host_name b\n}\n")
        sm = ShadowCopyManager(
            cfg_dirs=[str(dir_a), str(dir_b)],
            shadow_base_path=str(shadow_base or tmp_path / "shadow"),
        )
        assert sm.create_shadow("s1", "User", "u@test.com").success
        return sm, dir_a.resolve(), dir_b.resolve()

    def test_round_trip_in_every_root(self, tmp_path):
        sm, dir_a, dir_b = self._two_roots(tmp_path)
        for root in (dir_a, dir_b):
            logical = str(root / "hosts.cfg")
            physical = sm.physical_path(logical)
            assert physical != logical and os.path.isfile(physical)
            assert sm.logical_path(physical) == logical

    def test_path_outside_every_root_has_no_physical_path(self, tmp_path):
        sm, _dir_a, _dir_b = self._two_roots(tmp_path)
        assert sm.physical_path(str(tmp_path / "elsewhere.cfg")) is None
        assert sm.composite_path(str(tmp_path / "elsewhere.cfg")) is None

    def test_shadow_nested_inside_first_root_maps_second_root_correctly(self, tmp_path):
        """The shadow base may live inside a config root; a shadow path of the
        second root must not be mistaken for a file of the first root."""
        sm, _dir_a, dir_b = self._two_roots(tmp_path, shadow_base=tmp_path / "etc-main-config" / ".shadow")
        physical_b = sm.physical_path(str(dir_b / "hosts.cfg"))
        assert sm.logical_path(physical_b) == str(dir_b / "hosts.cfg")
        assert sm.composite_path(physical_b) == "root_1/hosts.cfg"
        assert sm.physical_path(physical_b) == physical_b

    def test_eleventh_root_keeps_its_place(self, tmp_path):
        dirs = []
        for i in range(11):
            d = tmp_path / f"r{i}"
            d.mkdir()
            dirs.append(str(d))
        sm = ShadowCopyManager(cfg_dirs=dirs, shadow_base_path=str(tmp_path / "shadow"))
        assert sm.create_shadow("s1", "User", "u@test.com").success
        names = [os.path.basename(p) for p in sm.shadow_cfg_dirs]
        assert names == [f"root_{i}" for i in range(11)]
