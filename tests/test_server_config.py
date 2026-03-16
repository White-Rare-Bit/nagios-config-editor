from server_config import PathsConfig, ServerConfig, load_config, save_config


class TestPathsConfig:
    def test_new_fields_have_defaults(self):
        p = PathsConfig()
        assert p.nagios_cfg == ""
        assert p.nagios_bin == "/usr/local/nagios/bin/nagios"
        assert p.backup_path is None
        assert p.shadow_path is None
        assert p.resource_cfg == ""
        assert p.extra_cfg_dirs == []
        assert p.primary_dir == ""

    def test_nagios_config_path_removed(self):
        """nagios_config_path field no longer exists."""
        p = PathsConfig()
        assert not hasattr(p, "nagios_config_path")

    def test_round_trip_serialization(self):
        config = ServerConfig()
        config.paths.nagios_cfg = "/etc/nagios/nagios.cfg"
        config.paths.extra_cfg_dirs = ["/opt/custom"]
        config.paths.primary_dir = "/etc/nagios/servers"
        config.paths.resource_cfg = "/etc/nagios/resources.cfg"
        d = config.to_dict()
        restored = ServerConfig.from_dict(d)
        assert restored.paths.nagios_cfg == "/etc/nagios/nagios.cfg"
        assert restored.paths.extra_cfg_dirs == ["/opt/custom"]
        assert restored.paths.primary_dir == "/etc/nagios/servers"
        assert restored.paths.resource_cfg == "/etc/nagios/resources.cfg"

    def test_from_dict_with_missing_new_fields(self):
        """Old settings.json without new fields should use defaults."""
        d = {"paths": {"nagios_bin": "/usr/bin/nagios"}}
        config = ServerConfig.from_dict(d)
        assert config.paths.extra_cfg_dirs == []
        assert config.paths.primary_dir == ""
