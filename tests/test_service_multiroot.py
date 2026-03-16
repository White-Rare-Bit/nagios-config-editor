from nagios_service import NagiosService


class TestNagiosServiceMultiRoot:
    def test_init_with_cfg_dirs(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "hosts.cfg").write_text('define host {\n    host_name h1\n}\n')
        (dir_b / "hosts.cfg").write_text('define host {\n    host_name h2\n}\n')

        svc = NagiosService(cfg_dirs=[str(dir_a), str(dir_b)])
        objects = svc.get_objects()
        names = {o.attributes.get("host_name") for o in objects}
        assert names == {"h1", "h2"}

    def test_init_with_cfg_files(self, tmp_path):
        f = tmp_path / "commands.cfg"
        f.write_text('define command {\n    command_name check_ping\n}\n')

        svc = NagiosService(cfg_files=[str(f)])
        objects = svc.get_objects()
        assert len(objects) == 1

    def test_backward_compat_single_path(self, tmp_path):
        (tmp_path / "hosts.cfg").write_text('define host {\n    host_name h1\n}\n')
        svc = NagiosService(config_path=str(tmp_path))
        assert len(svc.get_objects()) == 1

    def test_reload_preserves_multi_root(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        (dir_a / "hosts.cfg").write_text('define host {\n    host_name h1\n}\n')

        svc = NagiosService(cfg_dirs=[str(dir_a)])
        svc.get_objects()  # trigger initial parse
        # Add a new file
        (dir_a / "services.cfg").write_text('define service {\n    service_description svc1\n    host_name h1\n    check_command check_ping\n}\n')
        svc.reload()
        assert len(svc.get_objects()) == 2

    def test_config_path_returns_first_dir(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()

        svc = NagiosService(cfg_dirs=[str(dir_a), str(dir_b)])
        assert svc.config_path == str(dir_a.resolve())
