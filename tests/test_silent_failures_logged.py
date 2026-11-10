"""Failures that used to be swallowed without a trace now reach app.log.

Each one changes what the app does (falls back to defaults, treats a lock as
free, discovers no config) while the operator had no way to find out why.
"""

import logging

from app import server_config as sc
from app.nagios_cfg import parse_nagios_cfg, parse_resource_cfg
from app.shadow_copy_manager import ShadowCopyManager


def _warnings(caplog):
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]


def test_corrupt_settings_file_is_logged(caplog):
    sc.CONFIG_FILE.write_text("{not json")

    with caplog.at_level(logging.WARNING):
        sc.load_config()

    assert any("settings.json" in m and "defaults" in m for m in _warnings(caplog))


def test_unreadable_nagios_cfg_is_logged(caplog, tmp_path):
    with caplog.at_level(logging.WARNING):
        parse_nagios_cfg(str(tmp_path / "missing" / "nagios.cfg"))

    assert any("nagios.cfg" in m for m in _warnings(caplog))


def test_undecodable_nagios_cfg_is_logged(caplog, tmp_path):
    bad = tmp_path / "nagios.cfg"
    bad.write_bytes(b"cfg_dir=\xff\xfe\n")

    with caplog.at_level(logging.WARNING):
        parse_nagios_cfg(str(bad))

    assert any("Cannot read nagios.cfg" in m for m in _warnings(caplog))


def test_unreadable_resource_cfg_is_logged(caplog, tmp_path):
    with caplog.at_level(logging.WARNING):
        parse_resource_cfg(str(tmp_path / "missing" / "resource.cfg"))

    assert any("resource.cfg" in m for m in _warnings(caplog))


def test_corrupt_lock_file_is_logged(caplog, tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "a.cfg").write_text("")
    sm = ShadowCopyManager(cfg_dirs=[str(cfg)], shadow_base_path=str(tmp_path / ".shadow"))
    assert sm.create_shadow("s1", "A", "a@x").success
    with open(sm._lock_file, "w") as f:
        f.write("{broken")

    with caplog.at_level(logging.WARNING):
        status = sm.get_lock_status()

    assert status == {"locked": False}
    assert any("lock" in m.lower() for m in _warnings(caplog))


def test_failed_settings_save_is_logged(caplog, sample_config_path, tmp_path, monkeypatch):
    from app import create_app
    from app.routes import settings as settings_routes

    application = create_app(config_path=sample_config_path, log_dir_override=str(tmp_path / "logs"))

    def boom(_cfg):
        raise OSError("read-only file system")
    monkeypatch.setattr(settings_routes, "save_server_config", boom)

    with caplog.at_level(logging.WARNING):
        resp = application.test_client().post("/api/settings", json={"paths": {"primary_dir": "/x"}})

    assert resp.get_json()["success"] is False
    assert any("read-only file system" in m for m in _warnings(caplog))
