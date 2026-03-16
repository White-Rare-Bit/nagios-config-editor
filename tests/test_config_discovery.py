import os
import tempfile

from config_discovery import PROTECTED_FILENAMES, discover_config_roots
from nagios_cfg import parse_nagios_cfg


class TestParseNagiosCfg:
    def test_extracts_resource_file(self):
        """parse_nagios_cfg should also extract resource_file directive."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False) as f:
            f.write("cfg_dir=/etc/nagios/servers\n")
            f.write("resource_file=/etc/nagios/resources.cfg\n")
            f.name
        try:
            result = parse_nagios_cfg(f.name)
            assert result["cfg_dirs"] == ["/etc/nagios/servers"]
            assert result["resource_file"] == "/etc/nagios/resources.cfg"
        finally:
            os.unlink(f.name)

    def test_resource_file_defaults_empty(self):
        """Missing resource_file returns empty string."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False) as f:
            f.write("cfg_dir=/etc/nagios/servers\n")
            f.name
        try:
            result = parse_nagios_cfg(f.name)
            assert result["resource_file"] == ""
        finally:
            os.unlink(f.name)


class TestDiscoverConfigRoots:
    def test_discovers_cfg_dirs(self, tmp_path):
        servers = tmp_path / "servers"
        servers.mkdir()
        (servers / "hosts.cfg").write_text("define host {}\n")

        nagios_cfg = tmp_path / "nagios.cfg"
        nagios_cfg.write_text(f"cfg_dir={servers}\n")

        result = discover_config_roots(str(nagios_cfg))
        accessible = [d for d in result["directories"] if d["accessible"]]
        assert len(accessible) == 1
        assert accessible[0]["path"] == str(servers)

    def test_derives_dirs_from_cfg_files(self, tmp_path):
        """cfg_file entries grouped by parent directory."""
        (tmp_path / "hosts.cfg").write_text("define host {}\n")
        (tmp_path / "services.cfg").write_text("define service {}\n")

        nagios_cfg = tmp_path / "nagios.cfg"
        nagios_cfg.write_text(
            f"cfg_file={tmp_path}/hosts.cfg\n"
            f"cfg_file={tmp_path}/services.cfg\n"
        )

        result = discover_config_roots(str(nagios_cfg))
        accessible = [d for d in result["directories"] if d["accessible"]]
        assert len(accessible) == 1
        assert accessible[0]["path"] == str(tmp_path)

    def test_deduplicates_cfg_dir_and_cfg_file_parents(self, tmp_path):
        servers = tmp_path / "servers"
        servers.mkdir()
        (servers / "hosts.cfg").write_text("define host {}\n")

        nagios_cfg = tmp_path / "nagios.cfg"
        nagios_cfg.write_text(
            f"cfg_dir={servers}\n"
            f"cfg_file={servers}/hosts.cfg\n"
        )

        result = discover_config_roots(str(nagios_cfg))
        accessible = [d for d in result["directories"] if d["accessible"]]
        assert len(accessible) == 1

    def test_merges_extra_dirs(self, tmp_path):
        custom = tmp_path / "custom"
        custom.mkdir()

        nagios_cfg = tmp_path / "nagios.cfg"
        nagios_cfg.write_text("")

        result = discover_config_roots(str(nagios_cfg), extra_cfg_dirs=[str(custom)])
        accessible = [d for d in result["directories"] if d["accessible"]]
        assert any(d["path"] == str(custom) for d in accessible)

    def test_flags_inaccessible_dirs(self, tmp_path):
        nagios_cfg = tmp_path / "nagios.cfg"
        nagios_cfg.write_text("cfg_dir=/nonexistent/path\n")

        result = discover_config_roots(str(nagios_cfg))
        assert len(result["directories"]) == 1
        assert result["directories"][0]["accessible"] is False
        assert result["directories"][0]["error"] is not None

    def test_extracts_resource_file(self, tmp_path):
        nagios_cfg = tmp_path / "nagios.cfg"
        res_file = tmp_path / "resources.cfg"
        res_file.write_text("$USER1$=/usr/lib/nagios/plugins\n")
        nagios_cfg.write_text(f"resource_file={res_file}\n")

        result = discover_config_roots(str(nagios_cfg))
        assert result["resource_file"] == str(res_file)

    def test_protected_filenames(self):
        assert "nagios.cfg" in PROTECTED_FILENAMES
        assert "resource.cfg" in PROTECTED_FILENAMES
        assert "cgi.cfg" in PROTECTED_FILENAMES

    def test_returns_cfg_files_list(self, tmp_path):
        """Individual cfg_file paths are returned for the parser."""
        (tmp_path / "hosts.cfg").write_text("define host {}\n")
        nagios_cfg = tmp_path / "nagios.cfg"
        nagios_cfg.write_text(f"cfg_file={tmp_path}/hosts.cfg\n")

        result = discover_config_roots(str(nagios_cfg))
        assert str(tmp_path / "hosts.cfg") in result["cfg_files"]

    def test_empty_nagios_cfg_path(self):
        result = discover_config_roots("")
        assert result["directories"] == []
        assert result["cfg_files"] == []
        assert result["resource_file"] == ""
