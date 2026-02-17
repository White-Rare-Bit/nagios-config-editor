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


@pytest.fixture
def git_repo(tmp_path):
    """Create a temp directory with git init and an initial commit."""
    subprocess.run(["git", "init", str(tmp_path)], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@t.com"],
                   check=True, capture_output=True)
    # Create initial file and commit
    (tmp_path / "hosts.cfg").write_text("define host { host_name web-01 }\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", "Initial"],
                   check=True, capture_output=True)
    return tmp_path


class TestGitServiceIntegration:
    """Integration tests using real git repositories."""

    def test_is_repo_true(self, git_repo):
        gs = GitService(str(git_repo))
        result = gs.is_repo()
        assert result.success
        assert result.data is True

    def test_is_repo_false(self, tmp_path):
        gs = GitService(str(tmp_path))
        result = gs.is_repo()
        assert result.success
        assert result.data is False

    def test_init_repo(self, tmp_path):
        gs = GitService(str(tmp_path))
        result = gs.init_repo()
        assert result.success
        assert (tmp_path / ".git").is_dir()
        assert (tmp_path / ".gitignore").exists()
        gitignore = (tmp_path / ".gitignore").read_text()
        assert ".staging/" in gitignore

    def test_commit_success(self, git_repo):
        gs = GitService(str(git_repo))
        (git_repo / "new.cfg").write_text("define host { host_name web-02 }\n")
        result = gs.commit("Add web-02", user_name="Test", user_email="t@t.com")
        assert result.success
        assert result.data["commit_hash"]
        assert result.data["message"] == "Add web-02"

    def test_commit_rejects_missing_identity(self, git_repo):
        gs = GitService(str(git_repo))
        (git_repo / "new.cfg").write_text("new content")
        result = gs.commit("msg", user_name="", user_email="")
        assert not result.success
        assert "identity" in result.error.lower()

    def test_commit_nothing_to_commit(self, git_repo):
        gs = GitService(str(git_repo))
        result = gs.commit("empty", user_name="Test", user_email="t@t.com")
        assert not result.success
        assert "nothing to commit" in result.error.lower()

    def test_get_status_clean(self, git_repo):
        gs = GitService(str(git_repo))
        result = gs.get_status()
        assert result.success
        assert result.data.is_repo is True
        assert result.data.has_changes is False

    def test_get_status_modified(self, git_repo):
        gs = GitService(str(git_repo))
        (git_repo / "hosts.cfg").write_text("modified content\n")
        result = gs.get_status()
        assert result.success
        assert result.data.has_changes is True
        paths = [f.path for f in result.data.files]
        assert "hosts.cfg" in paths

    def test_get_status_excludes_backups(self, git_repo):
        gs = GitService(str(git_repo))
        (git_repo / ".backups").mkdir()
        (git_repo / ".backups" / "old.cfg").write_text("old")
        result = gs.get_status()
        assert result.success
        paths = [f.path for f in result.data.files]
        assert not any(".backups" in p for p in paths)

    def test_get_log(self, git_repo):
        gs = GitService(str(git_repo))
        result = gs.get_log()
        assert result.success
        assert result.data["is_repo"] is True
        assert len(result.data["commits"]) >= 1
        assert result.data["commits"][0].message == "Initial"

    def test_get_log_empty_repo(self, tmp_path):
        subprocess.run(["git", "init", str(tmp_path)], check=True,
                       capture_output=True)
        gs = GitService(str(tmp_path))
        result = gs.get_log()
        assert result.success
        assert result.data["commits"] == []

    def test_get_diff_untracked(self, git_repo):
        gs = GitService(str(git_repo))
        (git_repo / "new.cfg").write_text("new file content\n")
        result = gs.get_diff(filepath="new.cfg")
        assert result.success
        assert "+new file content" in result.data

    def test_discard_tracked_file(self, git_repo):
        gs = GitService(str(git_repo))
        original = (git_repo / "hosts.cfg").read_text()
        (git_repo / "hosts.cfg").write_text("modified content\n")
        result = gs.discard("hosts.cfg")
        assert result.success
        assert result.data["action"] == "restored"
        assert (git_repo / "hosts.cfg").read_text() == original

    def test_discard_untracked_file(self, git_repo):
        gs = GitService(str(git_repo))
        (git_repo / "untracked.cfg").write_text("temp")
        result = gs.discard("untracked.cfg")
        assert result.success
        assert result.data["action"] == "deleted"
        assert not (git_repo / "untracked.cfg").exists()

    def test_restore_to_previous_commit(self, git_repo):
        gs = GitService(str(git_repo))
        # Get initial commit hash
        log1 = gs.get_log()
        initial_hash = log1.data["commits"][0].hash

        # Make a second commit with a new file
        (git_repo / "extra.cfg").write_text("extra")
        gs.commit("Add extra", user_name="Test", user_email="t@t.com")

        # Restore to initial commit
        result = gs.restore(initial_hash)
        assert result.success
        assert result.data["commit"] == initial_hash
        # extra.cfg should be deleted since it didn't exist in initial commit
        assert not (git_repo / "extra.cfg").exists()

    def test_clear_history(self, git_repo):
        gs = GitService(str(git_repo))
        # Make a second commit
        (git_repo / "extra.cfg").write_text("extra")
        gs.commit("Second", user_name="Test", user_email="t@t.com")

        result = gs.clear_history(user_name="Test", user_email="t@t.com")
        assert result.success

        # Should have exactly 1 commit now
        log_result = gs.get_log()
        assert len(log_result.data["commits"]) == 1
        assert log_result.data["commits"][0].message == "Initial commit"
