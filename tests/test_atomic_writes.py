"""Tests for atomic write patterns across the codebase (Issue #13)."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


class TestStagingSaveAtomic:
    """Verify staging_manager.save_staging() produces a readable file."""

    def test_staging_save_round_trip(self, app):
        """save_staging() must produce a file that get_staging() can read back."""
        from staging_manager import StagingManager

        with tempfile.TemporaryDirectory() as tmpdir:
            sm = StagingManager(tmpdir)
            sm.staging_dir = Path(tmpdir)
            sm.staging_file = Path(tmpdir) / "staging.json"

            data = {
                "sessionId": "test-session",
                "pendingEdits": {
                    "file.cfg|host|web-01": {
                        "address": "10.0.0.1",
                    },
                },
            }

            result = sm.save_staging(data)
            assert result.success, f"save_staging failed: {result.error}"

            loaded = sm.get_staging()
            assert loaded is not None, "get_staging returned None after save"
            assert loaded["sessionId"] == "test-session"
            assert "file.cfg|host|web-01" in loaded["pendingEdits"]
            assert loaded["pendingEdits"]["file.cfg|host|web-01"]["address"] == "10.0.0.1"



class TestServerConfigSaveAtomic:
    """Verify server_config.save_config() uses atomic write pattern."""

    def test_server_config_save_uses_atomic_pattern(self, app):
        """save_config() must use temp file + fsync + os.replace."""
        from server_config import CONFIG_DIR, CONFIG_FILE, ServerConfig, save_config

        fsync_calls = []
        replace_calls = []
        original_fsync = os.fsync
        original_replace = os.replace

        def tracking_fsync(fd):
            fsync_calls.append(fd)
            return original_fsync(fd)

        def tracking_replace(src, dst):
            replace_calls.append((src, dst))
            return original_replace(src, dst)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_config_dir = Path(tmpdir) / "config"
            tmp_config_dir.mkdir()
            tmp_config_file = tmp_config_dir / "settings.json"

            config = ServerConfig()

            with patch("server_config.CONFIG_DIR", tmp_config_dir), \
                 patch("server_config.CONFIG_FILE", tmp_config_file), \
                 patch("os.fsync", side_effect=tracking_fsync), \
                 patch("os.replace", side_effect=tracking_replace):
                save_config(config)

            assert len(fsync_calls) > 0, "os.fsync was not called"
            assert len(replace_calls) > 0, "os.replace was not called"
            assert tmp_config_file.exists(), "Config file was not written"
