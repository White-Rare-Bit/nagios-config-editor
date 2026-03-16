"""Shared test fixtures for Nagios Bulk Editor tests."""

import glob
import os
import shutil

import pytest

from app import create_app


@pytest.fixture
def sample_config_path():
    """Path to the sample-config directory shipped with the repo."""
    path = os.path.join(os.path.dirname(__file__), "..", "sample-config")
    path = os.path.abspath(path)
    assert os.path.isdir(path), f"sample-config not found at {path}"
    return path


def _cleanup_test_artifacts():
    """Remove shadow copies, backups, and log files created during tests."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    shadow_dir = os.path.join(project_root, ".shadow")
    if os.path.isdir(shadow_dir):
        shutil.rmtree(shadow_dir, ignore_errors=True)
    sample_config = os.path.join(project_root, "sample-config")
    backup_dir = os.path.join(sample_config, "backups")
    if os.path.isdir(backup_dir):
        shutil.rmtree(backup_dir, ignore_errors=True)
    log_dir = os.path.join(project_root, "logs")
    for f in glob.glob(os.path.join(log_dir, "*.log*")):
        os.remove(f)


@pytest.fixture(autouse=True)
def _cleanup_after_test():
    """Auto-cleanup test artifacts after every test."""
    yield
    _cleanup_test_artifacts()


@pytest.fixture
def app(sample_config_path):
    """Create Flask app pointed at the sample-config directory."""
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
