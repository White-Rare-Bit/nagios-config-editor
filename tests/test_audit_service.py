"""Tests for audit_service — key=value log line formatting."""

import logging
import logging.handlers

import pytest

from app.audit_service import format_audit_line, log_audit


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

    def test_log_audit_writes_to_logger(self):
        audit = logging.getLogger("audit")
        handler = logging.handlers.MemoryHandler(capacity=100)
        handler.setLevel(logging.INFO)
        audit.addHandler(handler)
        try:
            log_audit(
                action="apply", user="admin@example.com", txn="abc123",
                type="host", name="web01", op="modify",
            )
            assert len(handler.buffer) == 1
            assert "AUDIT" in handler.buffer[0].getMessage()
            assert "txn=abc123" in handler.buffer[0].getMessage()
        finally:
            audit.removeHandler(handler)

    def test_log_audit_generates_txn_if_none(self):
        audit = logging.getLogger("audit")
        handler = logging.handlers.MemoryHandler(capacity=100)
        handler.setLevel(logging.INFO)
        audit.addHandler(handler)
        try:
            log_audit(action="backup_created", user="admin@example.com")
            assert len(handler.buffer) == 1
            msg = handler.buffer[0].getMessage()
            assert "txn=" in msg
            txn_start = msg.index("txn=") + 4
            txn_end = msg.index(" ", txn_start)
            assert len(msg[txn_start:txn_end]) > 0
        finally:
            audit.removeHandler(handler)


class TestMakeRelativePath:
    """Test make_relative_path helper."""

    def test_strips_config_parent(self):
        from app.routes.helpers import make_relative_path
        result = make_relative_path("/etc/nagios/objects/hosts.cfg", "/etc/nagios/objects")
        assert result == "objects/hosts.cfg"

    def test_non_config_path_unchanged(self):
        from app.routes.helpers import make_relative_path
        result = make_relative_path("/tmp/other/file.cfg", "/etc/nagios/objects")
        assert result == "/tmp/other/file.cfg"

    def test_none_path_passthrough(self):
        from app.routes.helpers import make_relative_path
        result = make_relative_path(None, "/etc/nagios/objects")
        assert result is None


class TestAuditLineRoundTrip:
    """The log viewer (routes/logs.parse_audit_line) must read back exactly what
    format_audit_line wrote. Breaks caught: values that split a log line or
    confuse the quoting, including forged entries via an embedded newline."""

    @pytest.mark.parametrize("value", [
        "plain",
        "with spaces",
        'say "hi"',
        "",
        "x=y; z",
        r"C:\path\x",
        "ends with backslash\\",
        'backslash then quote \\"',
    ])
    def test_value_round_trips(self, value):
        from app.routes.logs import parse_audit_line
        line = format_audit_line(action="apply", txn="t1", user="u@x", from_val=value)
        parsed = parse_audit_line("Nov 04 10:00:00 " + line)
        assert parsed["from"] == value
        assert parsed["action"] == "apply"

    def test_newline_cannot_forge_a_second_entry(self):
        from app.routes.logs import parse_audit_line
        forged = 'x\nNov 04 10:00:00 AUDIT txn=evil user="admin" action=git_commit'
        line = format_audit_line(action="object_edit", txn="t1", user="mallory", to_val=forged)
        assert "\n" not in line and "\r" not in line
        assert parse_audit_line("Nov 04 10:00:00 " + line)["to"] == forged

    def test_user_with_quote_round_trips(self):
        from app.routes.logs import parse_audit_line
        line = format_audit_line(action="apply", txn="t1", user='Bob "the admin"')
        assert parse_audit_line("Nov 04 10:00:00 " + line)["user"] == 'Bob "the admin"'
