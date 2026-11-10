"""An empty primary_dir means "Auto"; startup must not turn it into a fixed path."""

import json

import pytest

from app import create_app, server_config


@pytest.fixture
def auto_app(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    for d in (first, second):
        d.mkdir()
        (d / "hosts.cfg").write_text("define host {\n host_name h\n}\n")
    nagios_cfg = tmp_path / "nagios.cfg"
    nagios_cfg.write_text(f"cfg_dir={first}\ncfg_dir={second}\n")
    server_config.CONFIG_FILE.write_text(json.dumps({"paths": {"nagios_cfg": str(nagios_cfg)}}))
    app = create_app()
    app.config["TESTING"] = True
    return app, str(first.resolve())


def test_auto_primary_dir_is_not_reported_as_fixed(auto_app):
    app, first = auto_app
    resp = app.test_client().get("/api/settings")
    assert resp.get_json()["paths"]["primary_dir"] == ""
    assert app.extensions["primary_dir"] == first


def test_saving_unchanged_settings_keeps_auto(auto_app):
    app, _ = auto_app
    client = app.test_client()
    paths = client.get("/api/settings").get_json()["paths"]
    resp = client.post("/api/settings", json={"paths": paths})
    assert resp.get_json()["success"] is True
    saved = json.loads(server_config.CONFIG_FILE.read_text())
    assert saved["paths"]["primary_dir"] == ""


def test_auto_survives_a_save_that_changes_another_setting(auto_app, tmp_path):
    app, first = auto_app
    client = app.test_client()
    extra = tmp_path / "extra"
    extra.mkdir()
    paths = client.get("/api/settings").get_json()["paths"]
    paths["extra_cfg_dirs"] = [str(extra)]
    resp = client.post("/api/settings", json={"paths": paths})
    assert resp.get_json()["success"] is True
    saved = json.loads(server_config.CONFIG_FILE.read_text())
    assert saved["paths"]["primary_dir"] == ""
    assert app.extensions["primary_dir"] == first
