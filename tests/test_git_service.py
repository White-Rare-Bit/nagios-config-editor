"""Tests for git_service module."""

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from git_service import (
    GitService,
    _classify_status,
    _parse_log_entries,
)


class TestParseLogEntries:
    """Unit tests for _parse_log_entries (no git needed)."""

    def test_parses_single_commit(self):
        raw = "abc1234567890\x00Alice\x002025-01-15 10:30:00 +0000\x00Fix bug\n"
        commits = _parse_log_entries(raw)
        assert len(commits) == 1
        assert commits[0].hash == "abc1234567890"
        assert commits[0].hash_short == "abc1234"
        assert commits[0].author == "Alice"
        assert commits[0].message == "Fix bug"

    def test_parses_multiple_commits(self):
        raw = (
            "aaa1111111111\x00Alice\x002025-01-15\x00First\n"
            "bbb2222222222\x00Bob\x002025-01-16\x00Second\n"
        )
        commits = _parse_log_entries(raw)
        assert len(commits) == 2
        assert commits[0].message == "First"
        assert commits[1].message == "Second"

    def test_skips_empty_lines(self):
        raw = "\naaa1111111111\x00A\x00D\x00Msg\n\n"
        commits = _parse_log_entries(raw)
        assert len(commits) == 1

    def test_skips_malformed_lines(self):
        raw = "not-enough-fields\x00only-two\n"
        commits = _parse_log_entries(raw)
        assert len(commits) == 0

    def test_empty_input(self):
        assert _parse_log_entries("") == []
        assert _parse_log_entries("\n") == []


class TestClassifyStatus:
    """Unit tests for _classify_status."""

    def test_untracked(self):
        assert _classify_status("?", "?") == ("untracked", "?")

    def test_added(self):
        assert _classify_status("A", " ") == ("added", "A")

    def test_deleted(self):
        assert _classify_status("D", " ") == ("deleted", "D")

    def test_renamed(self):
        assert _classify_status("R", " ") == ("renamed", "R")

    def test_modified_staged(self):
        assert _classify_status("M", " ") == ("modified", "M")

    def test_modified_unstaged(self):
        assert _classify_status(" ", "M") == ("modified", "M")

    def test_fallback(self):
        status, code = _classify_status("C", " ")
        assert status == "changed"
        assert code == "C"


class TestParseSingleStatusLine:
    """Unit tests for GitService._parse_single_status_line."""

    def test_modified_file(self):
        entry = GitService._parse_single_status_line(" M  hosts.cfg", [])
        assert entry is not None
        assert entry.path == "hosts.cfg"
        assert entry.status == "modified"

    def test_excluded_path(self):
        entry = GitService._parse_single_status_line(
            " M  .backups/old.cfg", [".backups/"])
        assert entry is None

    def test_renamed_file(self):
        entry = GitService._parse_single_status_line(
            "R   old.cfg -> new.cfg", [])
        assert entry is not None
        assert entry.path == "new.cfg"

    def test_quoted_path(self):
        entry = GitService._parse_single_status_line(
            '?? "path with spaces.cfg"', [])
        assert entry is not None
        assert entry.path == "path with spaces.cfg"

    def test_staged_flag(self):
        entry = GitService._parse_single_status_line("M   staged.cfg", [])
        assert entry.staged is True
        assert entry.unstaged is False

    def test_unstaged_flag(self):
        entry = GitService._parse_single_status_line(" M  unstaged.cfg", [])
        assert entry.staged is False
        assert entry.unstaged is True
