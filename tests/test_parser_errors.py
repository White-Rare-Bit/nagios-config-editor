"""Tests for nagios_parser error handling and edge cases."""

from pathlib import Path

import pytest

from app.nagios_parser import NagiosConfigParser


class TestMalformedDefineBlocks:
    """Parser should handle malformed configs gracefully."""

    def test_unclosed_brace(self, tmp_path):
        cfg = tmp_path / "bad.cfg"
        cfg.write_text("define host {\n    host_name web-01\n")
        parser = NagiosConfigParser(str(tmp_path))
        # Should not raise — logs warning and skips
        objects = parser.parse_all()
        # May or may not parse partial content, but must not crash
        assert isinstance(objects, list)

    def test_nested_define(self, tmp_path):
        cfg = tmp_path / "nested.cfg"
        cfg.write_text(
            "define host {\n"
            "    host_name outer\n"
            "    define service {\n"
            "        service_description inner\n"
            "    }\n"
            "}\n"
        )
        parser = NagiosConfigParser(str(tmp_path))
        objects = parser.parse_all()
        # Should parse at least the outer object
        assert len(objects) >= 1
        types = [o.object_type for o in objects]
        assert "host" in types

    def test_empty_define_block(self, tmp_path):
        cfg = tmp_path / "empty.cfg"
        cfg.write_text("define host {\n}\n")
        parser = NagiosConfigParser(str(tmp_path))
        objects = parser.parse_all()
        assert len(objects) == 1
        assert objects[0].object_type == "host"
        assert objects[0].attributes == {}


class TestEncodingFallback:
    """Parser should fall back to latin-1 for non-UTF-8 files."""

    def test_latin1_file_parsed(self, tmp_path):
        cfg = tmp_path / "latin1.cfg"
        # Write with latin-1 encoding (contains a non-UTF-8 char: ü = 0xFC)
        content = "define host {\n    host_name web-\xfc\n    alias M\xfcnchen\n}\n"
        cfg.write_bytes(content.encode("latin-1"))

        parser = NagiosConfigParser(str(tmp_path))
        objects = parser.parse_all()
        assert len(objects) == 1
        assert "nchen" in objects[0].attributes.get("alias", "")


class TestMissingConfigDirectory:
    """Parser should handle missing directories gracefully."""

    def test_nonexistent_dir_returns_empty(self, tmp_path):
        parser = NagiosConfigParser(str(tmp_path / "nonexistent"))
        objects = parser.parse_all()
        assert objects == []


class TestInlineComments:
    """Parser should strip inline comments while preserving content."""

    def test_semicolon_outside_quotes_stripped(self, tmp_path):
        cfg = tmp_path / "comments.cfg"
        cfg.write_text(
            'define host {\n'
            '    host_name web-01 ; this is a comment\n'
            '}\n'
        )
        parser = NagiosConfigParser(str(tmp_path))
        objects = parser.parse_all()
        assert objects[0].attributes["host_name"] == "web-01"

    def test_semicolon_inside_quotes_preserved(self, tmp_path):
        cfg = tmp_path / "quoted.cfg"
        cfg.write_text(
            'define command {\n'
            '    command_name notify\n'
            '    command_line /usr/bin/printf "Alert; check now"\n'
            '}\n'
        )
        parser = NagiosConfigParser(str(tmp_path))
        objects = parser.parse_all()
        assert "Alert; check now" in objects[0].attributes["command_line"]

    def test_inline_comment_text_captured(self, tmp_path):
        cfg = tmp_path / "capture.cfg"
        cfg.write_text(
            'define host {\n'
            '    host_name web-01 ; primary web server\n'
            '}\n'
        )
        parser = NagiosConfigParser(str(tmp_path))
        objects = parser.parse_all()
        assert objects[0].inline_comments.get("host_name") == "primary web server"


class TestLineContinuation:
    """Parser should handle backslash line continuations."""

    def test_backslash_joins_lines(self, tmp_path):
        cfg = tmp_path / "continuation.cfg"
        cfg.write_text(
            'define host {\n'
            '    host_name \\\n'
            '        web-01\n'
            '}\n'
        )
        parser = NagiosConfigParser(str(tmp_path))
        objects = parser.parse_all()
        assert objects[0].attributes["host_name"] == "web-01"
