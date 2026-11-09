"""Paths and keys the API hands out stay the same before, during and after staging."""

from app import create_app

H = {"X-Session-Id": "s1"}


def _hosts(client):
    return {o["attributes"]["host_name"]: o for o in client.get("/api/objects?type=host").json
            if "host_name" in o["attributes"]}


def _multiroot(tmp_path):
    dir_a = tmp_path / "servers"
    dir_b = tmp_path / "switches"
    dir_a.mkdir()
    dir_b.mkdir()
    (dir_a / "hosts.cfg").write_text("define host {\n    host_name web1\n    address 10.0.0.1\n}\n")
    (dir_b / "hosts.cfg").write_text("define host {\n    host_name switch1\n    address 10.0.1.1\n}\n")
    nagios_cfg = tmp_path / "nagios.cfg"
    nagios_cfg.write_text(f"cfg_dir={dir_a}\ncfg_dir={dir_b}\n")

    from app.server_config import ServerConfig, save_config
    config = ServerConfig()
    config.paths.nagios_cfg = str(nagios_cfg)
    save_config(config)
    application = create_app()
    application.config["TESTING"] = True
    return application.test_client(), dir_a, dir_b


class TestPathsDoNotChangeWhenStagingStarts:
    def test_source_file_is_unchanged_after_first_edit(self, client):
        before = _hosts(client)
        name, host = next(iter(before.items()))
        resp = client.post("/api/objects/update", headers=H, json={
            "stable_key": f"{host['source_file']}|host|{name}",
            "attributes": dict(host["attributes"], alias="X"),
        })
        assert resp.status_code == 200

        after = _hosts(client)
        assert after[name]["source_file"] == host["source_file"]
        assert {o["source_file"] for o in after.values()} == {o["source_file"] for o in before.values()}

    def test_file_and_folder_listing_is_unchanged_after_first_edit(self, client):
        files_before = client.get("/api/files").json
        folders_before = client.get("/api/folders").json
        assert client.post("/api/files/create", headers=H, json={"path": "extra.cfg"}).status_code == 200

        files_after = client.get("/api/files").json
        assert files_after["roots"] == files_before["roots"]
        assert set(files_before["files"]) < set(files_after["files"])
        created = set(files_after["files"]) - set(files_before["files"])
        assert created == {files_before["roots"][0] + "/extra.cfg"}
        assert client.get("/api/folders").json == folders_before

    def test_same_key_keeps_working_for_every_edit(self, client):
        name, host = next(iter(_hosts(client).items()))
        key = f"{host['source_file']}|host|{name}"
        for alias in ("one", "two", "three"):
            resp = client.post("/api/objects/update", headers=H, json={
                "stable_key": key, "attributes": dict(host["attributes"], alias=alias),
            })
            assert resp.status_code == 200
        assert _hosts(client)[name]["attributes"]["alias"] == "three"

    def test_changed_object_keys_match_object_keys(self, client):
        name, host = next(iter(_hosts(client).items()))
        key = f"{host['source_file']}|host|{host['display_name']}"
        client.post("/api/objects/update", headers=H, json={
            "stable_key": key, "attributes": dict(host["attributes"], alias="X"),
        })
        assert client.get("/api/staging/info").json["data"]["changedObjectKeys"] == [key]

    def test_staging_diff_reports_the_file_path_clients_already_know(self, client):
        name, host = next(iter(_hosts(client).items()))
        client.post("/api/objects/update", headers=H, json={
            "stable_key": f"{host['source_file']}|host|{name}",
            "attributes": dict(host["attributes"], alias="X"),
        })
        files = client.get("/api/staging/diff").json["data"]["files"]
        assert [f["abs_path"] for f in files] == [host["source_file"]]


class TestSecondRoot:
    def test_edit_in_second_root_is_staged(self, tmp_path):
        client, _dir_a, dir_b = _multiroot(tmp_path)
        live = dir_b / "hosts.cfg"
        before = live.read_text()
        host = _hosts(client)["switch1"]

        resp = client.post("/api/objects/update", headers=H, json={
            "stable_key": f"{host['source_file']}|host|switch1",
            "attributes": {"host_name": "switch1", "address": "9.9.9.9"},
        })

        assert resp.status_code == 200, resp.json
        assert live.read_text() == before
        assert _hosts(client)["switch1"]["attributes"]["address"] == "9.9.9.9"

    def test_create_in_second_root_is_staged_then_applied(self, tmp_path):
        client, _dir_a, dir_b = _multiroot(tmp_path)
        live = dir_b / "hosts.cfg"
        before = live.read_text()
        target = _hosts(client)["switch1"]["source_file"]

        resp = client.post("/api/objects/create", headers=H, json={
            "target_file": target, "object_type": "host",
            "attributes": {"host_name": "switch2", "address": "10.0.1.2"},
        })

        assert resp.status_code == 200, resp.json
        assert live.read_text() == before, "create must not touch live config before Apply"
        assert _hosts(client)["switch2"]["source_file"] == target

        assert client.post("/api/staging/apply", headers=H).status_code == 200
        assert "switch2" in live.read_text()

    def test_file_delete_in_second_root(self, tmp_path):
        client, dir_a, dir_b = _multiroot(tmp_path)
        target = _hosts(client)["switch1"]["source_file"]

        resp = client.delete("/api/files/" + target.lstrip("/"), headers=H)

        assert resp.status_code == 200, resp.json
        assert "switch1" not in _hosts(client)
        assert "web1" in _hosts(client)
        assert (dir_b / "hosts.cfg").exists(), "live file stays until Apply"
        assert (dir_a / "hosts.cfg").exists()

    def test_write_outside_every_root_is_refused(self, tmp_path):
        client, _dir_a, _dir_b = _multiroot(tmp_path)
        outside = tmp_path / "elsewhere.cfg"
        outside.write_text("")

        resp = client.post("/api/objects/create", headers=H, json={
            "target_file": str(outside), "object_type": "host",
            "attributes": {"host_name": "evil"},
        })

        assert resp.status_code == 400
        assert outside.read_text() == ""
        assert client.get("/api/staging/lock").json["data"]["locked"] is False, \
            "a refused first request must not leave a lock behind"

    def test_backup_and_restore_cover_every_root(self, tmp_path):
        client, dir_a, dir_b = _multiroot(tmp_path)
        resp = client.post("/api/backups", json={"description": "both"})
        assert resp.status_code == 200
        name = client.get("/api/backups").json[0]["name"]
        assert client.get("/api/backups").json[0]["file_count"] == 2

        (dir_a / "hosts.cfg").write_text("define host {\n    host_name changed-a\n}\n")
        (dir_b / "hosts.cfg").write_text("define host {\n    host_name changed-b\n}\n")
        (dir_b / "added.cfg").write_text("define host {\n    host_name added\n}\n")

        resp = client.post(f"/api/backups/{name}/restore", headers=H, json={})
        assert resp.status_code == 200, resp.json
        assert "web1" in (dir_a / "hosts.cfg").read_text()
        assert "switch1" in (dir_b / "hosts.cfg").read_text()
        assert not (dir_b / "added.cfg").exists()

    def test_git_status_names_roots_it_does_not_track(self, tmp_path):
        client, _dir_a, dir_b = _multiroot(tmp_path)
        status = client.get("/api/git/status").json
        assert status["untracked_roots"] == [str(dir_b)]


class TestFolderMoveUndo:
    def test_undo_of_folder_move_leaves_no_copy_behind(self, make_app):
        _app, client = make_app({
            "team/web/hosts.cfg": "define host {\n    host_name web1\n}\n",
            "archive/keep.cfg": "define host {\n    host_name old1\n}\n",
        })
        root = client.get("/api/files").json["roots"][0]
        before = client.get("/api/files").json["files"]

        resp = client.post("/api/folders/move", headers=H, json={
            "sourcePath": f"{root}/team", "targetFolder": f"{root}/archive",
        })
        assert resp.status_code == 200, resp.json
        assert f"{root}/archive/team/web/hosts.cfg" in client.get("/api/files").json["files"]

        assert client.post("/api/staging/undo", headers=H).status_code == 200

        assert client.get("/api/files").json["files"] == before
        assert f"{root}/archive/team" not in client.get("/api/folders").json["folders"]
        assert client.get("/api/staging/info").json["data"]["changedFiles"] == 0
