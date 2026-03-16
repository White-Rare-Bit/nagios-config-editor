from nagios_parser import NagiosConfigParser


class TestMultiRootParser:
    def test_parses_multiple_cfg_dirs(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "hosts.cfg").write_text('define host {\n    host_name server1\n}\n')
        (dir_b / "hosts.cfg").write_text('define host {\n    host_name server2\n}\n')

        parser = NagiosConfigParser(cfg_dirs=[str(dir_a), str(dir_b)])
        parser.parse_all()
        names = {o.attributes.get("host_name") for o in parser.objects}
        assert names == {"server1", "server2"}

    def test_parses_individual_cfg_files(self, tmp_path):
        f = tmp_path / "commands.cfg"
        f.write_text('define command {\n    command_name check_ping\n}\n')

        parser = NagiosConfigParser(cfg_files=[str(f)])
        parser.parse_all()
        assert len(parser.objects) == 1
        assert parser.objects[0].attributes["command_name"] == "check_ping"

    def test_deduplicates_files(self, tmp_path):
        """File listed in both cfg_file and cfg_dir should be parsed once."""
        (tmp_path / "hosts.cfg").write_text('define host {\n    host_name server1\n}\n')

        parser = NagiosConfigParser(cfg_dirs=[str(tmp_path)], cfg_files=[str(tmp_path / "hosts.cfg")])
        parser.parse_all()
        assert len(parser.objects) == 1

    def test_skips_nonexistent_dirs(self, tmp_path):
        parser = NagiosConfigParser(cfg_dirs=[str(tmp_path / "nonexistent")])
        parser.parse_all()
        assert parser.objects == []

    def test_skips_nonexistent_files(self, tmp_path):
        parser = NagiosConfigParser(cfg_files=[str(tmp_path / "missing.cfg")])
        parser.parse_all()
        assert parser.objects == []

    def test_backward_compat_single_dir(self, tmp_path):
        """Single positional arg still works as config_path."""
        (tmp_path / "hosts.cfg").write_text('define host {\n    host_name server1\n}\n')

        parser = NagiosConfigParser(str(tmp_path))
        parser.parse_all()
        assert len(parser.objects) == 1

    def test_preserves_skip_logic(self, tmp_path):
        """Backup and staging files still skipped."""
        d = tmp_path / "configs"
        d.mkdir()
        (d / "hosts.cfg").write_text('define host {\n    host_name server1\n}\n')
        bak = d / "backups"
        bak.mkdir()
        (bak / "old.cfg").write_text('define host {\n    host_name old\n}\n')

        parser = NagiosConfigParser(cfg_dirs=[str(d)])
        parser.parse_all()
        names = {o.attributes.get("host_name") for o in parser.objects}
        assert "old" not in names
