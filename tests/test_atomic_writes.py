"""Tests for atomic write patterns across the codebase (Issue #13)."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


class TestStagingSaveAtomic:
    """Verify staging_manager.save_staging() calls fsync before rename."""

    def test_staging_save_calls_fsync(self, app):
        """save_staging() must flush+fsync before the atomic rename."""
        from staging_manager import StagingManager

        with tempfile.TemporaryDirectory() as tmpdir:
            sm = StagingManager(tmpdir)
            sm.staging_dir = Path(tmpdir)
            sm.staging_file = Path(tmpdir) / "staging.json"

            data = {
                "sessionId": "test-session",
                "pendingEdits": {},
            }

            fsync_calls = []
            original_fsync = os.fsync

            def tracking_fsync(fd):
                fsync_calls.append(fd)
                return original_fsync(fd)

            with patch("os.fsync", side_effect=tracking_fsync):
                result = sm.save_staging(data)

            assert result.success, f"save_staging failed: {result.error}"
            assert len(fsync_calls) > 0, "os.fsync was not called during save_staging()"
            assert sm.staging_file.exists(), "Staging file was not written"


class TestAuditWriteAtomic:
    """Verify audit_service uses atomic write pattern."""

    def test_audit_write_uses_atomic_replace(self, app):
        """write_audit_log() must use os.replace for atomic writes."""
        from audit_service import write_audit_log

        replace_calls = []
        original_replace = os.replace

        def tracking_replace(src, dst):
            replace_calls.append((src, dst))
            return original_replace(src, dst)

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("audit_service.get_audit_log_path", return_value=os.path.join(tmpdir, "audit.json")):
                with patch("audit_service.get_audit_log_dir", return_value=tmpdir):
                    with patch("os.replace", side_effect=tracking_replace):
                        write_audit_log({"action": "test", "timestamp": "2025-01-01"}, tmpdir)

            assert len(replace_calls) > 0, "os.replace was not called (no atomic write)"

    def test_audit_rotate_uses_atomic_replace(self, app):
        """rotate_audit_log() must use os.replace for atomic writes."""
        from audit_service import AUDIT_LOG_MAX_ENTRIES, rotate_audit_log

        replace_calls = []
        original_replace = os.replace

        def tracking_replace(src, dst):
            replace_calls.append((src, dst))
            return original_replace(src, dst)

        entries = [{"action": f"test-{i}"} for i in range(AUDIT_LOG_MAX_ENTRIES + 1)]

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("audit_service.get_audit_log_dir", return_value=tmpdir):
                with patch("os.replace", side_effect=tracking_replace):
                    result = rotate_audit_log(entries)

            assert result == [], "rotate_audit_log should return empty list"
            assert len(replace_calls) > 0, "os.replace was not called during rotation"


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
