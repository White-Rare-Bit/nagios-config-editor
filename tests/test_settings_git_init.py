"""Tests for auto git init on config path change."""

import shutil
import subprocess
import tempfile
from pathlib import Path

from app import create_app


def test_settings_save_initializes_git_when_missing():
    """Saving config paths should auto-init git if no repo exists."""
    test_dir = tempfile.mkdtemp()
    try:
        config_path = Path(test_dir) / "nagios"
        config_path.mkdir()

        (config_path / "hosts.cfg").write_text("""
define host {
    host_name   test-host
    alias       Test
    address     10.0.0.1
}
""")

        app = create_app(config_path=str(config_path))
        app.config["TESTING"] = True
        client = app.test_client()

        # Verify no git repo exists
        assert not (config_path / ".git").exists()

        # Save settings with the config path to trigger rediscovery
        resp = client.post("/api/settings", json={
            "paths": {
                "extra_cfg_dirs": [str(config_path)],
                "primary_dir": str(config_path),
            }
        })
        data = resp.get_json()

        assert data["success"] is True
        assert data.get("git_initialized") is True
        assert (config_path / ".git").exists()
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


def test_settings_save_skips_git_init_when_repo_exists():
    """Should not re-init git if repo already exists."""
    test_dir = tempfile.mkdtemp()
    try:
        config_path = Path(test_dir) / "nagios"
        config_path.mkdir()

        (config_path / "hosts.cfg").write_text("""
define host {
    host_name   test-host
    alias       Test
    address     10.0.0.1
}
""")

        app = create_app(config_path=str(config_path))
        app.config["TESTING"] = True
        client = app.test_client()

        # Pre-create a git repo
        subprocess.run(["git", "init"], cwd=str(config_path), capture_output=True)
        assert (config_path / ".git").exists()

        resp = client.post("/api/settings", json={
            "paths": {
                "extra_cfg_dirs": [str(config_path)],
                "primary_dir": str(config_path),
            }
        })
        data = resp.get_json()

        assert data["success"] is True
        assert data.get("git_initialized") is not True
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
