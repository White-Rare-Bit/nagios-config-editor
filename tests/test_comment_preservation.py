"""Tests for inline comment preservation through parse-write cycles (SAFETY-3)."""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from nagios_parser import NagiosConfigParser
from nagios_writer import NagiosConfigWriter


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

    def test_comments_restored_on_write(self, config_with_comments):
        """Writer restores inline comments when formatting objects."""
        config_path, test_dir = config_with_comments
        parser = NagiosConfigParser(config_path)
        parser.parse_all()

        host = parser.objects[0]

        # Write to a new file
        out_dir = tempfile.mkdtemp()
        try:
            out_path = os.path.join(out_dir, "out.cfg")
            writer = NagiosConfigWriter()
            writer.write_file(out_path, [host])

            content = Path(out_path).read_text()
            assert "; primary interface" in content
            assert "; increased from 3" in content
            assert "; every 5 minutes" in content
        finally:
            shutil.rmtree(out_dir, ignore_errors=True)

    def test_round_trip_preserves_comments(self, config_with_comments):
        """Full round-trip: parse -> write -> re-parse preserves comments."""
        config_path, test_dir = config_with_comments
        parser = NagiosConfigParser(config_path)
        parser.parse_all()

        host = parser.objects[0]

        out_dir = tempfile.mkdtemp()
        try:
            out_path = os.path.join(out_dir, "out.cfg")
            writer = NagiosConfigWriter()
            writer.write_file(out_path, [host])

            # Re-parse
            parser2 = NagiosConfigParser(out_dir)
            parser2.parse_all()

            host2 = parser2.objects[0]
            assert host2.attributes["address"] == "10.0.0.1"
            assert host2.inline_comments.get("address") == "primary interface"
            assert host2.inline_comments.get("max_check_attempts") == "increased from 3"
        finally:
            shutil.rmtree(out_dir, ignore_errors=True)

    def test_edit_object_in_file_preserves_comments(self, config_with_comments):
        """edit_object_in_file preserves inline comments when passed."""
        from file_operations import edit_object_in_file
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

    def test_edit_object_in_file_without_comments(self, config_with_comments):
        """edit_object_in_file without inline_comments strips comments (old behavior)."""
        from file_operations import edit_object_in_file
        config_path, _ = config_with_comments
        host_file = os.path.join(config_path, "hosts.cfg")

        parser = NagiosConfigParser(config_path)
        parser.parse_all()
        host = parser.objects[0]

        new_attrs = dict(host.attributes)
        result = edit_object_in_file(host_file, host.line_number, new_attrs, "host")
        assert result.success

        content = Path(host_file).read_text()
        # Without passing inline_comments, comments are stripped
        assert "; primary interface" not in content

    def test_new_object_without_comments_works(self, config_with_comments):
        """Objects created without comments still format correctly."""
        from nagios_model import NagiosObject
        obj = NagiosObject(
            object_type="host",
            attributes={"host_name": "test", "address": "1.2.3.4"},
            source_file="test.cfg",
            line_number=1,
        )
        writer = NagiosConfigWriter()
        output = writer.object_to_string(obj)
        assert "host_name" in output
        assert "address" in output
        assert ";" not in output
