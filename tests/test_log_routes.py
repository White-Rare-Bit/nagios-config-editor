"""Tests for log API endpoints and log file parsing."""

import os

import pytest

from routes.logs import parse_audit_line, parse_app_line


class TestParseAuditLine:
    """Test parsing key=value audit log lines."""

    def test_basic_modify(self):
        line = 'Feb 17 14:23:01 AUDIT txn=abc123 user="admin@example.com" action=apply type=host name=web01 field=alias op=modify from="Old" to="New"'
        result = parse_audit_line(line)
        assert result["timestamp"] == "Feb 17 14:23:01"
        assert result["txn"] == "abc123"
        assert result["user"] == "admin@example.com"
        assert result["action"] == "apply"
        assert result["type"] == "host"
        assert result["name"] == "web01"
        assert result["op"] == "modify"
        assert result["from"] == "Old"
        assert result["to"] == "New"

    def test_unquoted_values(self):
        line = "Feb 17 14:23:01 AUDIT txn=abc user=a@b.com action=apply type=host name=web01 op=create"
        result = parse_audit_line(line)
        assert result["user"] == "a@b.com"
        assert result["op"] == "create"

    def test_quoted_value_with_spaces(self):
        line = 'Feb 17 14:23:01 AUDIT txn=abc user="a@b.com" action=apply name="my host"'
        result = parse_audit_line(line)
        assert result["name"] == "my host"

    def test_empty_quoted_value(self):
        line = 'Feb 17 14:23:01 AUDIT txn=abc user="a@b.com" action=apply description=""'
        result = parse_audit_line(line)
        assert result["description"] == ""

    def test_malformed_line_returns_none(self):
        result = parse_audit_line("not a valid log line")
        assert result is None

    def test_escaped_quotes_in_value(self):
        line = 'Feb 17 14:23:01 AUDIT txn=abc user="a@b.com" action=apply from="value with \\"quotes\\""'
        result = parse_audit_line(line)
        assert result["from"] == 'value with "quotes"'


class TestParseAppLine:
    """Test parsing syslog-style app log lines."""

    def test_basic_info(self):
        line = "Feb 17 14:23:01 nagios-editor [INFO] backup_manager: Created backup pre_apply"
        result = parse_app_line(line)
        assert result["timestamp"] == "Feb 17 14:23:01"
        assert result["level"] == "INFO"
        assert result["source"] == "backup_manager"
        assert result["message"] == "Created backup pre_apply"

    def test_warning_level(self):
        line = "Feb 17 14:23:01 nagios-editor [WARNING] nagios_parser: Syntax issue in hosts.cfg"
        result = parse_app_line(line)
        assert result["level"] == "WARNING"

    def test_error_level(self):
        line = "Feb 17 14:23:01 nagios-editor [ERROR] git_service: Failed to commit"
        result = parse_app_line(line)
        assert result["level"] == "ERROR"

    def test_malformed_line_returns_none(self):
        result = parse_app_line("garbage")
        assert result is None
