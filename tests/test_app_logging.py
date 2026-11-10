"""Tests for app-level logging configuration."""

import logging
import os
import re
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


    def test_app_log_format_is_syslog_style(self, sample_config_path):
        """App log lines should match syslog-style format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "logs")
            create_app(config_path=sample_config_path, log_dir_override=log_dir)

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
            create_app(config_path=sample_config_path, log_dir_override=log_dir)

            audit = logging.getLogger("audit")
            audit.info('AUDIT txn=abc123 user="admin@example.com" action=apply')

            log_path = os.path.join(log_dir, "audit.log")
            with open(log_path) as f:
                line = f.readline()
            # Should have timestamp prefix + the raw AUDIT line
            assert "AUDIT txn=abc123" in line
            assert 'user="admin@example.com"' in line

    def test_create_app_twice_writes_each_line_once(self, sample_config_path, tmp_path):
        """Re-running the factory must replace its handlers, not stack more."""
        log_dir = str(tmp_path / "logs")
        create_app(config_path=sample_config_path, log_dir_override=log_dir)
        create_app(config_path=sample_config_path, log_dir_override=log_dir)

        logging.getLogger("test_module").warning("only once please")
        logging.getLogger("audit").info("AUDIT txn=x action=once")

        assert (tmp_path / "logs" / "app.log").read_text().count("only once please") == 1
        assert (tmp_path / "logs" / "audit.log").read_text().count("action=once") == 1

    @pytest.mark.parametrize("filename,logger_name,message", [
        ("app.log", "test_module", "ts check"),
        ("audit.log", "audit", "AUDIT txn=x action=ts"),
    ])
    def test_timestamps_are_iso8601_with_timezone(self, sample_config_path, tmp_path,
                                                  filename, logger_name, message):
        """Timestamps carry the year, milliseconds and UTC offset."""
        log_dir = str(tmp_path / "logs")
        create_app(config_path=sample_config_path, log_dir_override=log_dir)
        logging.getLogger(logger_name).warning(message)

        last = (tmp_path / "logs" / filename).read_text().splitlines()[-1]
        assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{2}:\d{2} ", last), last

    def test_file_handlers_are_multiprocess_safe(self, sample_config_path, tmp_path):
        from app.log_handlers import MultiProcessRotatingFileHandler

        create_app(config_path=sample_config_path, log_dir_override=str(tmp_path / "logs"))

        for name in ("", "audit"):
            file_handlers = [h for h in logging.getLogger(name).handlers if hasattr(h, "baseFilename")]
            assert file_handlers
            assert all(isinstance(h, MultiProcessRotatingFileHandler) for h in file_handlers)

    def test_audit_still_written_when_log_level_is_warning(self, sample_config_path, tmp_path):
        """log_level controls app.log only; it must never switch off auditing."""
        from app import server_config as sc

        cfg = sc.load_config()
        cfg.logging.log_level = "WARNING"
        sc.save_config(cfg)
        create_app(config_path=sample_config_path, log_dir_override=str(tmp_path / "logs"))

        from app.audit_service import log_audit
        log_audit("file_create", user="a", file="x.cfg")

        assert "action=file_create" in (tmp_path / "logs" / "audit.log").read_text()


def test_every_module_logger_lives_under_the_app_package():
    """One hierarchy ("app.*"), so setting the "app" logger's level covers all code."""
    import importlib
    import pkgutil

    import app as app_pkg

    wrong = {}
    for info in pkgutil.walk_packages(app_pkg.__path__, "app."):
        module = importlib.import_module(info.name)
        module_logger = getattr(module, "logger", None)
        if isinstance(module_logger, logging.Logger) and module_logger.name != info.name:
            wrong[info.name] = module_logger.name
    assert wrong == {}


def test_error_responses_are_logged_with_their_message(sample_config_path, tmp_path):
    """Routes often turn a failure into a 500 JSON body without logging it;
    operators must still find it in app.log."""
    log_dir = tmp_path / "logs"
    application = create_app(config_path=sample_config_path, log_dir_override=str(log_dir))
    client = application.test_client()

    # A 500 a route returns itself, without raising, the way routes report
    # a failed OperationResult: {"error": ...}, 500.
    from flask import jsonify
    with application.test_request_context("/api/x", method="POST"):
        response = jsonify({"error": "disk on fire"})
        response.status_code = 500
        application.process_response(response)

    text = (log_dir / "app.log").read_text()
    assert "POST /api/x -> 500" in text
    assert "disk on fire" in text
    assert client  # app still serves requests


def test_client_errors_are_not_logged_as_errors(sample_config_path, tmp_path):
    log_dir = tmp_path / "logs"
    application = create_app(config_path=sample_config_path, log_dir_override=str(log_dir))

    application.test_client().post("/api/files/create", json={})  # 400: path is required

    assert "-> 400" not in (log_dir / "app.log").read_text()
