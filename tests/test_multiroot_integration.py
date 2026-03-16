"""Integration test: multi-root config discovery through full stack."""

import os

from app import create_app


class TestMultiRootIntegration:
    def test_full_workflow(self, tmp_path):
        """Test: nagios.cfg -> discovery -> parse -> shadow -> apply."""
        # Setup: two config directories
        dir_a = tmp_path / "servers"
        dir_b = tmp_path / "switches"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "hosts.cfg").write_text(
            "define host {\n    host_name web1\n    address 10.0.0.1\n}\n"
        )
        (dir_b / "hosts.cfg").write_text(
            "define host {\n    host_name switch1\n    address 10.0.1.1\n}\n"
        )

        # Create nagios.cfg
        nagios_cfg = tmp_path / "nagios.cfg"
        nagios_cfg.write_text(
            f"cfg_dir={dir_a}\n"
            f"cfg_dir={dir_b}\n"
            f"resource_file={tmp_path}/resources.cfg\n"
        )
        (tmp_path / "resources.cfg").write_text("$USER1$=/usr/lib/nagios/plugins\n")

        # Create app with this nagios.cfg via server config override
        from server_config import ServerConfig, save_config
        config = ServerConfig()
        config.paths.nagios_cfg = str(nagios_cfg)
        save_config(config)

        application = create_app()
        application.config["TESTING"] = True
        client = application.test_client()

        with application.app_context():
            # Verify objects from both dirs are loaded
            resp = client.get("/api/objects")
            assert resp.status_code == 200
            objects = resp.json
            names = {o["attributes"].get("host_name") for o in objects}
            assert "web1" in names
            assert "switch1" in names

            # Verify files API returns roots
            resp = client.get("/api/files")
            assert resp.status_code == 200
            data = resp.json
            assert "roots" in data
            assert len(data["roots"]) == 2

            # Verify settings API shows discovered dirs
            resp = client.get("/api/settings")
            assert resp.status_code == 200
            settings = resp.json
            assert "discovered" in settings
            discovered_dirs = settings["discovered"]["cfg_dirs"]
            accessible = [d for d in discovered_dirs if d["accessible"]]
            assert len(accessible) == 2

    def test_shadow_edit_across_roots(self, tmp_path):
        """Edit objects from different roots via shadow, then apply."""
        dir_a = tmp_path / "servers"
        dir_a.mkdir()
        (dir_a / "hosts.cfg").write_text(
            "define host {\n    host_name web1\n    address 10.0.0.1\n}\n"
        )

        application = create_app(config_path=str(dir_a))
        application.config["TESTING"] = True
        client = application.test_client()

        with application.app_context():
            # First mutation triggers shadow creation; afterwards objects have shadow paths.
            # Get the host object's stable key using API source_file (absolute path).
            resp = client.get("/api/objects")
            objects = resp.json
            host = next(o for o in objects if o["attributes"].get("host_name") == "web1")
            key = f"{host['source_file']}|{host['object_type']}|web1"

            # Edit via API (creates shadow automatically)
            resp = client.post("/api/objects/update", json={
                "stable_key": key,
                "attributes": {**host["attributes"], "alias": "Web Server 1"},
            }, headers={"X-Session-Id": "test-session"})
            assert resp.status_code == 200

            # Verify staging shows changes
            resp = client.get("/api/staging/info")
            assert resp.json["data"]["totalCount"] >= 1

            # Apply changes
            resp = client.post("/api/staging/apply?force=true")
            assert resp.status_code == 200
            assert resp.json["success"]

            # Verify changes persisted to original file
            content = (dir_a / "hosts.cfg").read_text()
            assert "Web Server 1" in content

    def test_cfg_file_directive(self, tmp_path):
        """Individual cfg_file directives are parsed correctly."""
        (tmp_path / "commands.cfg").write_text(
            "define command {\n    command_name check_ping\n    command_line /usr/lib/nagios/plugins/check_ping\n}\n"
        )

        nagios_cfg = tmp_path / "nagios.cfg"
        nagios_cfg.write_text(f"cfg_file={tmp_path}/commands.cfg\n")

        from server_config import ServerConfig, save_config
        config = ServerConfig()
        config.paths.nagios_cfg = str(nagios_cfg)
        save_config(config)

        application = create_app()
        application.config["TESTING"] = True
        client = application.test_client()

        with application.app_context():
            resp = client.get("/api/objects")
            objects = resp.json
            names = {o["attributes"].get("command_name") for o in objects}
            assert "check_ping" in names

    def test_inaccessible_dir_handled_gracefully(self, tmp_path):
        """Inaccessible directories don't crash the app."""
        nagios_cfg = tmp_path / "nagios.cfg"
        nagios_cfg.write_text("cfg_dir=/nonexistent/path\n")

        from server_config import ServerConfig, save_config
        config = ServerConfig()
        config.paths.nagios_cfg = str(nagios_cfg)
        save_config(config)

        application = create_app()
        application.config["TESTING"] = True
        client = application.test_client()

        with application.app_context():
            resp = client.get("/api/settings")
            assert resp.status_code == 200
            discovered = resp.json["discovered"]["cfg_dirs"]
            assert len(discovered) == 1
            assert discovered[0]["accessible"] is False
