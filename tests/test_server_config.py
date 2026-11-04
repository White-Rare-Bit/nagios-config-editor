from app.server_config import ServerConfig


class TestPathsConfig:

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
