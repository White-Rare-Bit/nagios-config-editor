"""Tests for deterministic move ordering in the apply path."""

import os
import shutil
import tempfile

import pytest

from file_operations import extract_all_blocks, assemble_file_from_blocks
from nagios_service import NagiosService


class TestExtractAllBlocks:
    def test_extract_two_blocks(self):
        content = (
            "# File header comment\n\n"
            "define host {\n    host_name    a\n}\n\n"
            "define host {\n    host_name    b\n}\n"
        )
        blocks = extract_all_blocks(content)
        assert len(blocks) == 2
        assert "host_name    a" in blocks[0][2]
        assert "host_name    b" in blocks[1][2]

    def test_extract_preserves_order(self):
        content = (
            "define host {\n    host_name    first\n}\n\n"
            "define service {\n    service_description    svc1\n    host_name    first\n}\n\n"
            "define host {\n    host_name    second\n}\n"
        )
        blocks = extract_all_blocks(content)
        assert len(blocks) == 3
        assert blocks[0][0] < blocks[1][0] < blocks[2][0]

    def test_extract_empty_file(self):
        blocks = extract_all_blocks("")
        assert blocks == []

    def test_extract_preamble_only(self):
        content = "# Just a comment\n# No define blocks\n"
        blocks = extract_all_blocks(content)
        assert blocks == []

    def test_start_end_positions(self):
        content = "define host {\n    host_name    x\n}\n"
        blocks = extract_all_blocks(content)
        assert len(blocks) == 1
        start, end, text = blocks[0]
        assert content[start:end] == text


class TestAssembleFileFromBlocks:
    def test_preserves_preamble(self):
        preamble = "# My hosts file\n# Auto-generated\n"
        blocks = [
            "define host {\n    host_name    c\n}",
            "define host {\n    host_name    a\n}",
        ]
        result = assemble_file_from_blocks(preamble, blocks)
        assert result.startswith("# My hosts file\n")
        assert result.index("host_name    c") < result.index("host_name    a")

    def test_empty_preamble(self):
        blocks = ["define host {\n    host_name    x\n}"]
        result = assemble_file_from_blocks("", blocks)
        assert result.startswith("define host")
        assert result.endswith("\n")

    def test_trailing_newline(self):
        result = assemble_file_from_blocks("", ["define host {\n    host_name    a\n}"])
        assert result.endswith("\n")
        assert not result.endswith("\n\n")

    def test_two_blank_lines_between_blocks(self):
        blocks = [
            "define host {\n    host_name    a\n}",
            "define host {\n    host_name    b\n}",
        ]
        result = assemble_file_from_blocks("", blocks)
        assert "\n\n\n" not in result  # no triple newlines
        # Two blocks separated by exactly 2 blank lines = \n\n between them
        parts = result.split("\n\n")
        assert len(parts) == 2

    def test_empty_blocks(self):
        result = assemble_file_from_blocks("# header\n", [])
        assert result == "# header\n"

    def test_preamble_with_trailing_whitespace(self):
        preamble = "# header\n\n\n"
        blocks = ["define host {\n    host_name    a\n}"]
        result = assemble_file_from_blocks(preamble, blocks)
        # Should not have excessive blank lines between preamble and first block
        assert "\n\n\n\n" not in result
