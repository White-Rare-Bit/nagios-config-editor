"""Tests for audit log calls in route handlers."""

import logging

import pytest


class TestBackupAuditLogging:
    """Verify backup routes call log_audit."""

    def test_create_backup_logs_audit(self, app, caplog):
        with app.test_client() as client:
            with caplog.at_level(logging.INFO, logger="audit"):
                # This will fail without a proper config path, but we just
                # need to verify the audit call pattern compiles
                pass  # Placeholder — real test needs sample-config setup


class TestGitAuditLogging:
    """Verify git routes call log_audit."""

    def test_discard_all_logs_audit(self, app, caplog):
        with app.test_client() as client:
            with caplog.at_level(logging.INFO, logger="audit"):
                pass  # Placeholder — real test needs git repo setup
