"""Shared test fixtures for Nagios Bulk Editor tests."""

import logging
import shutil
from pathlib import Path

import pytest

from app import create_app
from app import server_config

# Importing `app` runs create_app() at module level (app/__init__.py, for
# wsgi.py), before any fixture can isolate it. That attaches file handlers
# writing to the repo's real logs/app.log and logs/audit.log. Detach them so no
# test can write there; per-test handlers are cleaned up in _isolate_environment.
for _logger in (logging.getLogger(), logging.getLogger("audit")):
    for _handler in [h for h in _logger.handlers if isinstance(h, logging.FileHandler)]:
        _logger.removeHandler(_handler)
        _handler.close()

_REPO_SAMPLE_CONFIG = Path(__file__).resolve().parent.parent / "sample-config"

# Environment variables that override config/settings.json (see
# server_config._apply_env_overrides). Cleared so a developer's shell
# environment can't change test behaviour.
_SERVER_CONFIG_ENV_VARS = ("NAGIOS_CFG", "NAGIOS_BIN", "BACKUP_PATH", "NBE_SHADOW_PATH")


@pytest.fixture(autouse=True)
def _isolate_environment(tmp_path_factory, monkeypatch):
    """Keep every test away from the developer's real files.

    - config/settings.json: redirected to an empty per-test directory, so
      tests start from default settings and any save (e.g. POST /api/settings)
      can't overwrite the real file.
    - Working directory: changed to a per-test temp dir, so relative defaults
      (the "logs" log_dir, "./sample-config") never resolve inside the repo.
      Without this, tests appended to and rotated the real logs/audit.log.
    - Log handlers: create_app() adds file handlers to the global root and
      "audit" loggers and never removes them. Removed after each test so
      handlers don't pile up and later tests don't write into earlier tests'
      log files.
    """
    config_dir = tmp_path_factory.mktemp("server_config")
    monkeypatch.setattr(server_config, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(server_config, "CONFIG_FILE", config_dir / "settings.json")
    for var in _SERVER_CONFIG_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path_factory.mktemp("cwd"))

    loggers = [logging.getLogger(), logging.getLogger("audit")]
    handlers_before = [list(lg.handlers) for lg in loggers]
    yield
    for lg, before in zip(loggers, handlers_before):
        for handler in [h for h in lg.handlers if h not in before]:
            lg.removeHandler(handler)
            handler.close()


@pytest.fixture
def sample_config_path(tmp_path):
    """Path to a per-test copy of the repo's sample-config directory.

    A copy, not the original: the app writes shadow copies next to the config
    dir and backups inside it, which for the real sample-config are the dev
    app's live .shadow/ and sample-config/backups/.
    """
    assert _REPO_SAMPLE_CONFIG.is_dir(), f"sample-config not found at {_REPO_SAMPLE_CONFIG}"
    dest = tmp_path / "sample-config"
    shutil.copytree(_REPO_SAMPLE_CONFIG, dest, ignore=shutil.ignore_patterns("backups", ".git"))
    return str(dest)


@pytest.fixture
def app(sample_config_path):
    """Create Flask app pointed at a copy of the sample-config directory."""
    application = create_app(config_path=sample_config_path)
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def service(app):
    """NagiosService instance from the app."""
    with app.app_context():
        yield app.extensions["service"]


@pytest.fixture
def make_app(tmp_path):
    """Factory fixture: write config files to tmp_path, return (app, client).

    Usage:
        def test_something(make_app):
            app, client = make_app({
                "hosts.cfg": "define host { host_name web-01 ... }",
                "commands.cfg": "define command { ... }",
            })
            resp = client.get("/api/health-check")
    """
    def _make(config_files: dict):
        for name, content in config_files.items():
            filepath = tmp_path / name
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content)
        application = create_app(config_path=str(tmp_path))
        application.config["TESTING"] = True
        return application, application.test_client()
    return _make
