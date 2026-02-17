"""Tests for app-level logging configuration."""

import logging
import os
import tempfile

import pytest

from app import create_app


class TestLoggingSetup:
    """Verify that create_app configures both log handlers."""

    @pytest.fixture(autouse=True)
    def _clean_handlers(self):
        """Remove file handlers added during tests to avoid cross-test pollution."""
        yield
        # Clean up any file handlers we added
        for logger_name in ("", "audit"):
            lgr = logging.getLogger(logger_name)
            for h in lgr.handlers[:]:
                if hasattr(h, "baseFilename"):
                    h.close()
                    lgr.removeHandler(h)

    def test_app_logger_has_file_handler(self, sample_config_path):
        """App logger should write to logs/app.log."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "logs")
            app = create_app(config_path=sample_config_path, log_dir_override=log_dir)
            root = logging.getLogger()
            file_handlers = [
                h for h in root.handlers
                if hasattr(h, "baseFilename") and "app.log" in h.baseFilename
            ]
            assert len(file_handlers) >= 1

    def test_audit_logger_has_file_handler(self, sample_config_path):
        """Audit logger should write to logs/audit.log."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "logs")
            app = create_app(config_path=sample_config_path, log_dir_override=log_dir)
            audit = logging.getLogger("audit")
            file_handlers = [
                h for h in audit.handlers
                if hasattr(h, "baseFilename") and "audit.log" in h.baseFilename
            ]
            assert len(file_handlers) >= 1

    def test_app_log_format_is_syslog_style(self, sample_config_path):
        """App log lines should match syslog-style format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "logs")
            app = create_app(config_path=sample_config_path, log_dir_override=log_dir)

            test_logger = logging.getLogger("test_module")
            test_logger.info("Test message")

            log_path = os.path.join(log_dir, "app.log")
            with open(log_path) as f:
                line = f.readline()
            assert "nagios-editor" in line
            assert "[INFO]" in line
            assert "Test message" in line

    def test_audit_log_format_is_passthrough(self, sample_config_path):
        """Audit log lines should pass through the message unmodified (formatter adds only timestamp)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "logs")
            app = create_app(config_path=sample_config_path, log_dir_override=log_dir)

            audit = logging.getLogger("audit")
            audit.info('AUDIT txn=abc123 user="admin@example.com" action=apply')

            log_path = os.path.join(log_dir, "audit.log")
            with open(log_path) as f:
                line = f.readline()
            # Should have timestamp prefix + the raw AUDIT line
            assert "AUDIT txn=abc123" in line
            assert 'user="admin@example.com"' in line
