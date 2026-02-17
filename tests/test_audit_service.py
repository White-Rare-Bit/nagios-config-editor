"""Tests for audit_service — key=value log line formatting."""

import logging

from audit_service import format_audit_line, log_audit


class TestFormatAuditLine:
    """Test key=value line formatting."""

    def test_basic_apply_modify(self):
        line = format_audit_line(
            action="apply", txn="abc123", user="admin@example.com",
            type="host", name="web01", field="alias", op="modify",
            from_val="Old Alias", to_val="New Alias",
        )
        assert "AUDIT" in line
        assert 'txn=abc123' in line
        assert 'user="admin@example.com"' in line
        assert "action=apply" in line
        assert "type=host" in line
        assert "name=web01" in line
        assert "field=alias" in line
        assert "op=modify" in line
        assert 'from="Old Alias"' in line
        assert 'to="New Alias"' in line

    def test_create_action(self):
        line = format_audit_line(
            action="apply", txn="abc123", user="admin@example.com",
            type="service", name="web01-http", op="create",
        )
        assert "op=create" in line
        assert "field" not in line

    def test_backup_action(self):
        line = format_audit_line(
            action="backup_restore", txn="def456", user="admin@example.com",
            description="pre_apply",
        )
        assert "action=backup_restore" in line
        assert "description=pre_apply" in line

    def test_git_commit_action(self):
        line = format_audit_line(
            action="git_commit", txn="ghi789", user="admin@example.com",
            message="Updated host configs",
        )
        assert "action=git_commit" in line
        assert 'message="Updated host configs"' in line

    def test_values_with_spaces_get_quoted(self):
        line = format_audit_line(
            action="apply", txn="abc", user="a@b.com",
            name="my host",
        )
        assert 'name="my host"' in line

    def test_values_without_spaces_not_quoted(self):
        line = format_audit_line(
            action="apply", txn="abc", user="a@b.com",
            type="host",
        )
        assert "type=host" in line

    def test_empty_value(self):
        line = format_audit_line(
            action="apply", txn="abc", user="a@b.com",
            description="",
        )
        assert 'description=""' in line

    def test_values_with_quotes_get_escaped(self):
        line = format_audit_line(
            action="apply", txn="abc", user="a@b.com",
            from_val='value with "quotes"',
        )
        # Quotes inside values should be escaped
        assert 'from="value with \\"quotes\\""' in line


class TestLogAudit:
    """Test that log_audit writes to the audit logger."""

    def test_log_audit_writes_to_logger(self, caplog):
        with caplog.at_level(logging.INFO, logger="audit"):
            log_audit(
                action="apply", user="admin@example.com", txn="abc123",
                type="host", name="web01", op="modify",
            )
        assert len(caplog.records) == 1
        assert "AUDIT" in caplog.records[0].message
        assert "txn=abc123" in caplog.records[0].message

    def test_log_audit_generates_txn_if_none(self, caplog):
        with caplog.at_level(logging.INFO, logger="audit"):
            log_audit(action="backup_created", user="admin@example.com")
        assert "txn=" in caplog.records[0].message
        # Should be a non-empty txn value
        msg = caplog.records[0].message
        txn_start = msg.index("txn=") + 4
        txn_end = msg.index(" ", txn_start)
        assert len(msg[txn_start:txn_end]) > 0
