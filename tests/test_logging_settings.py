"""Logging settings: saved changes take effect without a restart, in every worker."""

import logging
import os

import pytest

from app import create_app
from app import server_config as sc
from app.log_handlers import MultiProcessRotatingFileHandler


@pytest.fixture
def client_and_logs(sample_config_path, tmp_path):
    log_dir = tmp_path / "logs"
    application = create_app(config_path=sample_config_path, log_dir_override=str(log_dir))
    application.config["TESTING"] = True
    yield application.test_client(), log_dir
    logging.getLogger().setLevel(logging.INFO)


def _our_handler(logger_name):
    return next(h for h in logging.getLogger(logger_name).handlers
                if isinstance(h, MultiProcessRotatingFileHandler))


def _app_handler():
    return _our_handler("")


def test_log_level_change_applies_immediately(client_and_logs):
    client, log_dir = client_and_logs

    resp = client.post("/api/settings/logging", json={"log_level": "DEBUG"})

    assert resp.status_code == 200
    logging.getLogger("app.some_module").debug("debug now visible")
    assert "debug now visible" in (log_dir / "app.log").read_text()


def test_rotation_settings_apply_immediately(client_and_logs):
    client, _ = client_and_logs

    client.post("/api/settings/logging", json={"max_file_size_mb": 1, "max_backup_files": 2})

    for name in ("", "audit"):
        handler = _our_handler(name)
        assert handler.maxBytes == 1024 * 1024
        assert handler.backupCount == 2


def test_change_saved_by_another_worker_is_picked_up(client_and_logs):
    """Each gunicorn worker has its own loggers; a save in one must reach the others."""
    client, _ = client_and_logs
    cfg = sc.load_config()
    cfg.logging.log_level = "WARNING"
    sc.save_config(cfg)  # as if another worker handled the POST
    st = os.stat(sc.CONFIG_FILE)
    os.utime(sc.CONFIG_FILE, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))

    client.get("/api/settings/logging")

    assert logging.getLogger().level == logging.WARNING
    assert _app_handler().level == logging.WARNING


def test_invalid_log_level_is_rejected(client_and_logs):
    client, _ = client_and_logs

    resp = client.post("/api/settings/logging", json={"log_level": "LOUD"})

    assert resp.status_code == 400
    assert sc.load_config().logging.log_level == "INFO"


@pytest.mark.parametrize("payload", [
    {"max_file_size_mb": 0},
    {"max_backup_files": -1},
    {"max_file_size_mb": "ten"},
])
def test_invalid_rotation_values_are_rejected(client_and_logs, payload):
    client, _ = client_and_logs
    assert client.post("/api/settings/logging", json=payload).status_code == 400


def test_log_dir_cannot_be_changed_over_http(client_and_logs):
    """Where the app writes files is set in config/settings.json, not by any web user."""
    client, _ = client_and_logs
    assert client.post("/api/settings/logging", json={"log_dir": "/etc"}).status_code == 400


def test_get_reports_live_log_file_and_no_dead_settings(client_and_logs):
    client, log_dir = client_and_logs
    (log_dir / "app.log").write_text("x" * 123)

    data = client.get("/api/settings/logging").get_json()

    assert data["log_file_path"] == str(log_dir / "app.log")
    assert data["log_file_size"] == 123
    assert "enabled" not in data
    assert "log_filename" not in data


@pytest.mark.parametrize("url", ["/api/logs/operations", "/api/logs/operations/download"])
def test_obsolete_operations_log_endpoints_are_gone(client_and_logs, url):
    client, _ = client_and_logs
    assert client.get(url).status_code == 404


def test_old_settings_file_with_dead_keys_still_loads():
    sc.CONFIG_FILE.write_text(
        '{"version": 1, "logging": {"enabled": false, "log_filename": "operations.jsonl",'
        ' "log_level": "ERROR"}}'
    )
    cfg = sc.load_config()
    assert cfg.logging.log_level == "ERROR"
    assert "enabled" not in cfg.to_dict()["logging"]
    assert "log_filename" not in cfg.to_dict()["logging"]
