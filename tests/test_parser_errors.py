"""Tests for nagios_parser error handling and edge cases."""

import logging

import pytest

from app.nagios_parser import NagiosConfigParser


class TestMalformedDefineBlocks:
    """Parser should handle malformed configs gracefully."""

    def test_unclosed_brace(self, tmp_path, caplog):
        """An unterminated block is skipped (not half-parsed) and a warning logged."""
        cfg = tmp_path / "bad.cfg"
        cfg.write_text("define host {\n    host_name web-01\n")
        parser = NagiosConfigParser(str(tmp_path))
        with caplog.at_level(logging.WARNING):
            objects = parser.parse_all()
        assert objects == []
        assert any("Unmatched brace" in r.getMessage() for r in caplog.records)

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
        # Outer and inner become separate objects; "define service {" must not
        # leak into the host as an attribute
        assert [(o.object_type, o.attributes) for o in objects] == [
            ("host", {"host_name": "outer"}),
            ("service", {"service_description": "inner"}),
        ]

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


class TestLineNumbers:
    """Edits locate objects by line number, so a wrong count edits the wrong object."""

    @pytest.mark.parametrize("nl", ["\n", "\r\n"])
    def test_line_numbers_across_many_blocks(self, tmp_path, nl):
        text = nl.join([
            "# header comment",                  # 1
            "",                                  # 2
            "define host {",                     # 3  <- h1
            "    host_name h1",                  # 4
            "}",                                 # 5
            "# a comment between blocks",        # 6
            "define host {",                     # 7  <- h2
            "    host_name h2",                  # 8
            "} define host {",                   # 9  <- h3 (same line as h2's close)
            "    host_name h3",                  # 10
            "}",                                 # 11
            "",                                  # 12
            "",                                  # 13
            "define command{",                   # 14 <- c1
            '    command_line /bin/echo "{ }"',  # 15
            "    command_name c1",               # 16
            "}",                                 # 17
        ]) + nl
        (tmp_path / "x.cfg").write_bytes(text.encode())
        objects = NagiosConfigParser(str(tmp_path)).parse_all()
        found = [(o.get_name(), o.line_number) for o in objects]
        assert found == [("h1", 3), ("h2", 7), ("h3", 9), ("c1", 14)]

    def test_line_numbers_after_unclosed_block(self, tmp_path):
        (tmp_path / "x.cfg").write_text(
            "define host {\n    host_name broken\n\n"   # 1-3, never closed
            "define host {\n    host_name h2\n}\n"      # 4-6
        )
        objects = NagiosConfigParser(str(tmp_path)).parse_all()
        assert [o.line_number for o in objects if o.get_name() == "h2"] == [4]
