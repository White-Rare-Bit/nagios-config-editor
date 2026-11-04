"""Tests for inline comment preservation through parse-write cycles (SAFETY-3)."""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from app.nagios_parser import NagiosConfigParser


@pytest.fixture
def config_with_comments():
    """Create config files with inline comments."""
    test_dir = tempfile.mkdtemp()
    test_config_path = Path(test_dir) / "nagios"
    test_config_path.mkdir()

    (test_config_path / "hosts.cfg").write_text("""define host {
    host_name               web-01
    alias                   Web Server 01
    address                 10.0.0.1 ; primary interface
    max_check_attempts      5 ; increased from 3
    check_interval          5 ; every 5 minutes
    notification_interval   30
}
""")

    yield str(test_config_path), test_dir

    shutil.rmtree(test_dir, ignore_errors=True)


class TestInlineCommentPreservation:
    """Test that inline comments survive parse-write cycles."""

    def test_comments_captured_during_parse(self, config_with_comments):
        """Parser stores inline comments separately from values."""
        config_path, _ = config_with_comments
        parser = NagiosConfigParser(config_path)
        parser.parse_all()

        host = parser.objects[0]
        assert host.attributes["address"] == "10.0.0.1"
        assert host.inline_comments.get("address") == "primary interface"
        assert host.inline_comments.get("max_check_attempts") == "increased from 3"
        assert host.inline_comments.get("check_interval") == "every 5 minutes"
        # Attributes without comments should not appear in inline_comments
        assert "notification_interval" not in host.inline_comments


    def test_edit_object_in_file_preserves_comments(self, config_with_comments):
        """edit_object_in_file preserves inline comments when passed."""
        from app.file_operations import edit_object_in_file
        config_path, _ = config_with_comments
        host_file = os.path.join(config_path, "hosts.cfg")

        # Parse to get inline comments
        parser = NagiosConfigParser(config_path)
        parser.parse_all()
        host = parser.objects[0]
        assert host.inline_comments.get("address") == "primary interface"

        # Edit: change check_interval but keep inline comments
        new_attrs = dict(host.attributes)
        new_attrs["check_interval"] = "10"
        result = edit_object_in_file(
            host_file, host.line_number, new_attrs, "host",
            inline_comments=host.inline_comments,
        )
        assert result.success

        content = Path(host_file).read_text()
        assert "check_interval" in content
        assert "; primary interface" in content
        assert "; increased from 3" in content
        assert "; every 5 minutes" in content

        # Re-parse to confirm values
        parser2 = NagiosConfigParser(config_path)
        parser2.parse_all()
        host2 = parser2.objects[0]
        assert host2.attributes["check_interval"] == "10"
        assert host2.inline_comments.get("address") == "primary interface"

    def test_new_object_without_comments_works(self):
        """Objects created without comments format with no stray ';'."""
        from app.nagios_model import format_object_block
        output = format_object_block("host", {"host_name": "test", "address": "1.2.3.4"})
        assert "host_name" in output
        assert "address" in output
        assert ";" not in output


# ---------------------------------------------------------------------------
# Edits made through the API (the path the UI uses) must keep inline comments.
# Breaks caught: a route calling service.update_object() without passing the
# object's inline_comments, which silently deletes every comment on the object.
# ---------------------------------------------------------------------------

HOSTS_WITH_COMMENTS = """define host {
    host_name               web-01
    alias                   Web Server 01
    address                 10.0.0.1 ; primary interface
    max_check_attempts      5 ; increased from 3
}
"""


@pytest.fixture
def commented_app(tmp_path):
    config_dir = tmp_path / "nagios"
    config_dir.mkdir()
    (config_dir / "hosts.cfg").write_text(HOSTS_WITH_COMMENTS)
    from app import create_app
    app = create_app(config_path=str(config_dir))
    app.config["TESTING"] = True
    return app, app.test_client(), config_dir / "hosts.cfg"


def _web01(client):
    obj = next(o for o in client.get("/api/objects").json
               if o["attributes"].get("host_name") == "web-01")
    key = f"{obj['source_file']}|{obj['object_type']}|{obj['display_name']}"
    return obj, key


class TestCommentsSurviveApiEdits:

    def test_update_route_keeps_comments_on_untouched_fields(self, commented_app):
        _, client, hosts_cfg = commented_app
        obj, key = _web01(client)

        resp = client.post("/api/objects/update", json={
            "stable_key": key,
            "attributes": {**obj["attributes"], "alias": "Renamed"},
        }, headers={"X-Session-Id": "s1"})
        assert resp.status_code == 200
        assert client.post("/api/staging/apply").json["success"] is True

        content = hosts_cfg.read_text()
        assert "Renamed" in content
        assert "10.0.0.1 ; primary interface" in content
        assert "5 ; increased from 3" in content

    def test_update_route_drops_comment_of_deleted_field(self, commented_app):
        _, client, hosts_cfg = commented_app
        obj, key = _web01(client)
        attrs = {k: v for k, v in obj["attributes"].items() if k != "address"}

        resp = client.post("/api/objects/update", json={"stable_key": key, "attributes": attrs},
                           headers={"X-Session-Id": "s1"})
        assert resp.status_code == 200
        client.post("/api/staging/apply")

        content = hosts_cfg.read_text()
        assert "primary interface" not in content
        assert "5 ; increased from 3" in content

    def test_batch_update_keeps_comments(self, commented_app):
        _, client, hosts_cfg = commented_app
        obj, key = _web01(client)

        resp = client.post("/api/batch-mutations", json={
            "description": "batch",
            "operations": [{"action": "update", "stable_key": key,
                            "attributes": {**obj["attributes"], "alias": "Batch"}}],
        }, headers={"X-Session-Id": "s1"})
        assert resp.status_code == 200
        client.post("/api/staging/apply")

        content = hosts_cfg.read_text()
        assert "Batch" in content
        assert "10.0.0.1 ; primary interface" in content
