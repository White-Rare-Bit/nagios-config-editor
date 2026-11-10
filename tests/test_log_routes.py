"""Tests for log API endpoints and log file parsing."""

import pytest

from app import create_app
from app.routes.logs import parse_audit_line, parse_app_line


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


ISO = "2026-11-04T12:43:45.123+00:00"


class TestIsoTimestamps:
    """Lines written since the switch to ISO 8601 timestamps; old lines still parse."""

    def test_audit_line_with_iso_timestamp(self):
        result = parse_audit_line(f'{ISO} AUDIT txn=abc user="a@b.com" action=file_create file=x.cfg')
        assert result["timestamp"] == ISO
        assert result["action"] == "file_create"

    def test_app_line_with_iso_timestamp(self):
        result = parse_app_line(f"{ISO} nagios-editor [INFO] app.git_service: Committed")
        assert result["timestamp"] == ISO
        assert result["source"] == "app.git_service"
        assert result["message"] == "Committed"

    def test_negative_utc_offset(self):
        result = parse_app_line("2026-11-04T07:43:45.123-05:00 nagios-editor [INFO] app: x")
        assert result["timestamp"] == "2026-11-04T07:43:45.123-05:00"


@pytest.fixture
def log_client(sample_config_path, tmp_path):
    log_dir = tmp_path / "logs"
    application = create_app(config_path=sample_config_path, log_dir_override=str(log_dir))
    application.config["TESTING"] = True
    # Start from empty files: create_app itself may have logged startup lines.
    for name in ("app.log", "audit.log"):
        (log_dir / name).write_text("")
    return application.test_client(), log_dir


def _audit(n):
    return f'{ISO} AUDIT txn=t{n} user="u" action=file_create file=f{n}.cfg\n'


class TestLogViewerReading:
    def test_audit_view_includes_rotated_files_newest_first(self, log_client):
        client, log_dir = log_client
        (log_dir / "audit.log.2").write_text(_audit(1) + _audit(2))
        (log_dir / "audit.log.1").write_text(_audit(3))
        (log_dir / "audit.log").write_text(_audit(4) + _audit(5))

        data = client.get("/api/logs/audit").get_json()["data"]

        assert [e["txn"] for e in data["entries"]] == ["t5", "t4", "t3", "t2", "t1"]
        assert data["truncated"] is False

    def test_app_view_includes_rotated_files(self, log_client):
        client, log_dir = log_client
        (log_dir / "app.log.1").write_text(f"{ISO} nagios-editor [INFO] app: older\n")
        (log_dir / "app.log").write_text(f"{ISO} nagios-editor [INFO] app: newer\n")

        entries = client.get("/api/logs/app").get_json()["data"]["entries"]

        assert [e["message"] for e in entries] == ["newer", "older"]

    def test_limit_returns_newest_entries_and_flags_truncation(self, log_client):
        client, log_dir = log_client
        (log_dir / "audit.log.1").write_text("".join(_audit(i) for i in range(100)))
        (log_dir / "audit.log").write_text("".join(_audit(i) for i in range(100, 200)))

        data = client.get("/api/logs/audit?limit=150").get_json()["data"]

        assert len(data["entries"]) == 150
        assert data["entries"][0]["txn"] == "t199"
        assert data["entries"][-1]["txn"] == "t50"
        assert data["truncated"] is True

    def test_reads_large_file_backwards_without_splitting_lines(self, log_client):
        client, log_dir = log_client
        # Far bigger than one read block, with lines straddling block edges.
        (log_dir / "audit.log").write_text("".join(_audit(i) for i in range(5000)))

        entries = client.get("/api/logs/audit?limit=10000").get_json()["data"]["entries"]

        assert [e["txn"] for e in entries] == [f"t{i}" for i in reversed(range(5000))]


class TestLogClearAndDownload:
    def test_audit_log_cannot_be_cleared(self, log_client):
        client, log_dir = log_client
        (log_dir / "audit.log").write_text(_audit(1))

        response = client.post("/api/logs/audit/clear")

        assert response.status_code in (404, 405)
        assert "txn=t1" in (log_dir / "audit.log").read_text()

    def test_clearing_app_log_is_audited(self, log_client):
        client, log_dir = log_client
        (log_dir / "app.log").write_text(f"{ISO} nagios-editor [INFO] app: old\n")

        response = client.post("/api/logs/app/clear",
                               headers={"X-User-Name": "Ann", "X-User-Email": "ann@x"})

        assert response.status_code == 200
        assert "old" not in (log_dir / "app.log").read_text()
        audit = (log_dir / "audit.log").read_text()
        assert "action=log_clear" in audit
        assert "log=app" in audit
        assert 'user="Ann <ann@x>"' in audit

    def test_download_includes_rotated_files_oldest_first(self, log_client):
        client, log_dir = log_client
        (log_dir / "audit.log.2").write_text(_audit(1))
        (log_dir / "audit.log.1").write_text(_audit(2))
        (log_dir / "audit.log").write_text(_audit(3))

        body = client.get("/api/logs/audit/download").get_data(as_text=True)

        assert body == _audit(1) + _audit(2) + _audit(3)


class TestFrontendLogEndpoint:
    """POST /api/logs/frontend writes browser-supplied text into app.log."""

    def _app_entries(self, client):
        return client.get("/api/logs/app").get_json()["data"]["entries"]

    def test_newline_in_message_cannot_forge_an_entry(self, log_client):
        client, _ = log_client
        forged = f"hi\n{ISO} nagios-editor [ERROR] app.git_service: Force-pushed main\rmore"

        client.post("/api/logs/frontend", json={"level": "error", "message": forged})

        entries = self._app_entries(client)
        assert len(entries) == 1
        assert entries[0]["source"].endswith("frontend")
        assert "\\n" in entries[0]["message"] and "\\r" in entries[0]["message"]

    def test_long_message_is_truncated(self, log_client):
        client, log_dir = log_client

        client.post("/api/logs/frontend", json={"level": "error", "message": "x" * 100_000})

        line = (log_dir / "app.log").read_text().splitlines()[0]
        assert len(line) < 3000
        assert "[truncated]" in line

    def test_batch_size_is_capped(self, log_client):
        from app.routes.settings import MAX_FRONTEND_BATCH

        client, _ = log_client
        batch = [{"level": "error", "message": f"m{i}"} for i in range(MAX_FRONTEND_BATCH + 50)]

        client.post("/api/logs/frontend", json=batch)

        entries = self._app_entries(client)
        frontend = [e for e in entries if e["message"].startswith("[frontend] m")]
        assert len(frontend) == MAX_FRONTEND_BATCH
        assert any("dropped 50" in e["message"] for e in entries)

    def test_unicode_line_separators_are_escaped(self, log_client):
        client, log_dir = log_client

        client.post("/api/logs/frontend", json={"level": "error", "message": "a b\x0cc\x85d"})

        assert len((log_dir / "app.log").read_text().splitlines()) == 1
