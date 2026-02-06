"""Tests for inline comment preservation through parse-write cycles (SAFETY-3)."""

import pytest
import tempfile
import shutil
import os
from pathlib import Path
from nagios_parser import NagiosConfigParser
from nagios_writer import NagiosConfigWriter


@pytest.fixture
def config_with_comments():
    """Create config files with inline comments."""
    test_dir = tempfile.mkdtemp()
    test_config_path = Path(test_dir) / 'nagios'
    test_config_path.mkdir()

    (test_config_path / 'hosts.cfg').write_text('''define host {
    host_name               web-01
    alias                   Web Server 01
    address                 10.0.0.1 ; primary interface
    max_check_attempts      5 ; increased from 3
    check_interval          5 ; every 5 minutes
    notification_interval   30
}
''')

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
        assert host.attributes['address'] == '10.0.0.1'
        assert host.inline_comments.get('address') == 'primary interface'
        assert host.inline_comments.get('max_check_attempts') == 'increased from 3'
        assert host.inline_comments.get('check_interval') == 'every 5 minutes'
        # Attributes without comments should not appear in inline_comments
        assert 'notification_interval' not in host.inline_comments

    def test_comments_restored_on_write(self, config_with_comments):
        """Writer restores inline comments when formatting objects."""
        config_path, test_dir = config_with_comments
        parser = NagiosConfigParser(config_path)
        parser.parse_all()

        host = parser.objects[0]

        # Write to a new file
        out_dir = tempfile.mkdtemp()
        try:
            out_path = os.path.join(out_dir, 'out.cfg')
            writer = NagiosConfigWriter()
            writer.write_file(out_path, [host])

            content = Path(out_path).read_text()
            assert '; primary interface' in content
            assert '; increased from 3' in content
            assert '; every 5 minutes' in content
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
            out_path = os.path.join(out_dir, 'out.cfg')
            writer = NagiosConfigWriter()
            writer.write_file(out_path, [host])

            # Re-parse
            parser2 = NagiosConfigParser(out_dir)
            parser2.parse_all()

            host2 = parser2.objects[0]
            assert host2.attributes['address'] == '10.0.0.1'
            assert host2.inline_comments.get('address') == 'primary interface'
            assert host2.inline_comments.get('max_check_attempts') == 'increased from 3'
        finally:
            shutil.rmtree(out_dir, ignore_errors=True)

    def test_new_object_without_comments_works(self, config_with_comments):
        """Objects created without comments still format correctly."""
        from nagios_model import NagiosObject
        obj = NagiosObject(
            object_type='host',
            attributes={'host_name': 'test', 'address': '1.2.3.4'},
            source_file='test.cfg',
            line_number=1
        )
        writer = NagiosConfigWriter()
        output = writer.object_to_string(obj)
        assert 'host_name' in output
        assert 'address' in output
        assert ';' not in output
