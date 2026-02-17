# Test Suite Overhaul — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prune low-value tests and fill critical coverage gaps, focusing on code paths where bugs cause data loss or corruption.

**Architecture:** Delete the convention-enforcement tests (now covered by ESLint/Stylelint), fix existing anti-patterns (implementation-detail mocking, brittle assertions), add a shared fixture factory, then write new test files for the four untested critical modules: git_service, backup_manager, validator, and nagios_parser error paths.

**Tech Stack:** pytest, tempfile, zipfile, subprocess (mocked for validator binary tests), real git repos for git_service integration tests

---

### Task 1: Delete test_conventions.py

**Files:**
- Delete: `tests/test_conventions.py`

**Step 1: Delete the file**

Delete `tests/test_conventions.py` (486 lines). ESLint and Stylelint now handle JS/CSS naming enforcement. Python naming can be enforced by Ruff if needed later.

**Step 2: Run tests to verify nothing breaks**

Run: `python3 -m pytest tests/ -v`
Expected: All remaining tests pass. Test count drops by the number of tests in test_conventions.py.

**Step 3: Commit**

```bash
git add -u tests/test_conventions.py
git commit -m "test: remove test_conventions.py, now covered by ESLint/Stylelint"
```

---

### Task 2: Fix test_atomic_writes.py — behavioral tests

**Files:**
- Modify: `tests/test_atomic_writes.py`

Replace the `TestStagingSaveAtomic` class (lines 12-41) that mocks `os.fsync` with a behavioral test that verifies the save/load round-trip works correctly.

**Step 1: Rewrite TestStagingSaveAtomic**

Replace the existing class with:

```python
class TestStagingSaveAtomic:
    """Verify staging_manager.save_staging() produces a readable file."""

    def test_staging_save_round_trip(self, app):
        """save_staging() must produce a file that get_staging() can read back."""
        from staging_manager import StagingManager

        with tempfile.TemporaryDirectory() as tmpdir:
            sm = StagingManager(tmpdir)
            sm.staging_dir = Path(tmpdir)
            sm.staging_file = Path(tmpdir) / "staging.json"

            data = {
                "sessionId": "test-session",
                "pendingEdits": {
                    "file.cfg|host|web-01": {
                        "address": "10.0.0.1",
                    },
                },
            }

            result = sm.save_staging(data)
            assert result.success, f"save_staging failed: {result.error}"

            loaded = sm.get_staging()
            assert loaded is not None, "get_staging returned None after save"
            assert loaded["sessionId"] == "test-session"
            assert "file.cfg|host|web-01" in loaded["pendingEdits"]
            assert loaded["pendingEdits"]["file.cfg|host|web-01"]["address"] == "10.0.0.1"
```

Leave `TestAuditWriteAtomic` and `TestServerConfigSaveAtomic` unchanged — those test audit/config infrastructure where verifying the atomic write mechanism itself is the point.

**Step 2: Run tests**

Run: `python3 -m pytest tests/test_atomic_writes.py -v`
Expected: All tests pass.

**Step 3: Commit**

```bash
git add tests/test_atomic_writes.py
git commit -m "test: rewrite staging atomic test as behavioral round-trip"
```

---

### Task 3: Fix brittle assertion in test_health_check.py

**Files:**
- Modify: `tests/test_health_check.py:132`

**Step 1: Replace exact string match with substring check**

Change line 132 from:
```python
    assert oncall_cmd_issues[0]["message"] == "References non-existent command: nonexistent-cmd", \
        f"Expected precise error for 'nonexistent-cmd', got: {oncall_cmd_issues[0]['message']}"
```
To:
```python
    assert "nonexistent-cmd" in oncall_cmd_issues[0]["message"], \
        f"Expected 'nonexistent-cmd' in message, got: {oncall_cmd_issues[0]['message']}"
```

**Step 2: Run tests**

Run: `python3 -m pytest tests/test_health_check.py::test_health_check_detects_missing_cmd_in_comma_separated_list -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_health_check.py
git commit -m "test: replace brittle exact-match assertion with substring check"
```

---

### Task 4: Add shared fixture factory to conftest.py

**Files:**
- Modify: `tests/conftest.py`

**Step 1: Add make_app fixture**

Add this fixture after the existing `service` fixture in `tests/conftest.py`:

```python
@pytest.fixture
def make_app(tmp_path):
    """Factory fixture: write config files to tmp_path, return (app, client).

    Usage:
        def test_something(make_app):
            app, client = make_app({
                "hosts.cfg": "define host { host_name web-01 ... }",
                "commands.cfg": "define command { ... }",
            })
            resp = client.get("/api/health-check")
    """
    def _make(config_files: dict):
        for name, content in config_files.items():
            filepath = tmp_path / name
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content)
        application = create_app(config_path=str(tmp_path))
        application.config["TESTING"] = True
        return application, application.test_client()
    return _make
```

Add `from app import create_app` to the imports if not already present (it is — line 7).

**Step 2: Run tests**

Run: `python3 -m pytest tests/ -v`
Expected: All pass. Fixture is available but not yet used by existing tests.

**Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add make_app factory fixture to conftest.py"
```

---

### Task 5: Write test_git_service.py — Pure function unit tests

**Files:**
- Create: `tests/test_git_service.py`

**Step 1: Write pure function tests**

```python
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
```

**Step 2: Run tests**

Run: `python3 -m pytest tests/test_git_service.py -v`
Expected: All pass.

**Step 3: Commit**

```bash
git add tests/test_git_service.py
git commit -m "test: add git_service pure function unit tests"
```

---

### Task 6: Write test_git_service.py — Integration tests with real repos

**Files:**
- Modify: `tests/test_git_service.py` (append to existing file)

**Step 1: Add git_repo fixture and integration tests**

Append to `tests/test_git_service.py`:

```python
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
```

**Step 2: Run tests**

Run: `python3 -m pytest tests/test_git_service.py -v`
Expected: All pass (pure + integration).

**Step 3: Commit**

```bash
git add tests/test_git_service.py
git commit -m "test: add git_service integration tests with real temp repos"
```

---

### Task 7: Write test_backup_manager.py

**Files:**
- Create: `tests/test_backup_manager.py`

**Step 1: Write tests**

```python
"""Tests for backup_manager module."""

import os
import time
import zipfile
from pathlib import Path

import pytest

from backup_manager import BackupManager


@pytest.fixture
def backup_env(tmp_path):
    """Create a config dir with .cfg files and a separate backup dir."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    (config_dir / "hosts.cfg").write_text(
        "define host { host_name web-01\n address 10.0.0.1 }\n")
    (config_dir / "commands.cfg").write_text(
        "define command { command_name check_ping\n"
        " command_line /usr/lib/nagios/plugins/check_ping }\n")

    bm = BackupManager(str(config_dir), str(backup_dir))
    return bm, config_dir, backup_dir


class TestCreateBackup:
    """Tests for BackupManager.create_backup."""

    def test_creates_zip_with_cfg_files(self, backup_env):
        bm, config_dir, backup_dir = backup_env
        zip_path = bm.create_backup("test backup")
        assert os.path.exists(zip_path)
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            cfg_files = [n for n in names if n.endswith(".cfg")]
            assert len(cfg_files) == 2
            assert any("hosts.cfg" in n for n in cfg_files)
            assert any("commands.cfg" in n for n in cfg_files)

    def test_includes_metadata(self, backup_env):
        bm, _, _ = backup_env
        zip_path = bm.create_backup("my description")
        with zipfile.ZipFile(zip_path, "r") as zf:
            assert "_backup_info.txt" in zf.namelist()
            metadata = zf.read("_backup_info.txt").decode("utf-8")
            assert "my description" in metadata
            assert "Files backed up: 2" in metadata

    def test_skips_symlinks(self, backup_env):
        bm, config_dir, _ = backup_env
        # Create a symlink to a .cfg file
        target = config_dir / "hosts.cfg"
        link = config_dir / "link.cfg"
        link.symlink_to(target)

        zip_path = bm.create_backup("symlink test")
        with zipfile.ZipFile(zip_path, "r") as zf:
            cfg_names = [n for n in zf.namelist() if n.endswith(".cfg")]
            assert not any("link.cfg" in n for n in cfg_names)

    def test_backup_path_equals_config_path_raises(self, tmp_path):
        with pytest.raises(ValueError, match="must not equal"):
            BackupManager(str(tmp_path), str(tmp_path))


class TestListBackups:
    """Tests for BackupManager.list_backups."""

    def test_empty_directory(self, backup_env):
        bm, _, _ = backup_env
        # No backups created yet — but fixture dir exists
        # Remove any auto-created files
        backups = bm.list_backups()
        assert backups == []

    def test_lists_multiple_sorted_by_date(self, backup_env):
        bm, _, _ = backup_env
        bm.create_backup("first")
        time.sleep(0.05)  # Ensure different timestamps
        bm.create_backup("second")
        backups = bm.list_backups()
        assert len(backups) == 2
        # Most recent first
        assert "second" in backups[0]["name"]
        assert "first" in backups[1]["name"]


class TestRestoreBackup:
    """Tests for BackupManager.restore_backup."""

    def test_round_trip(self, backup_env):
        bm, config_dir, _ = backup_env
        original_hosts = (config_dir / "hosts.cfg").read_text()
        original_commands = (config_dir / "commands.cfg").read_text()

        zip_path = bm.create_backup("before change")
        backup_name = os.path.basename(zip_path)

        # Modify config files
        (config_dir / "hosts.cfg").write_text("MODIFIED CONTENT")
        (config_dir / "commands.cfg").write_text("ALSO MODIFIED")

        result = bm.restore_backup(backup_name)
        assert result["files_restored"] == 2

        # Verify files are restored to originals
        assert (config_dir / "hosts.cfg").read_text() == original_hosts
        assert (config_dir / "commands.cfg").read_text() == original_commands

    def test_path_traversal_in_backup_name_blocked(self, backup_env):
        bm, _, _ = backup_env
        with pytest.raises(ValueError, match="Invalid backup name"):
            bm.restore_backup("../../etc/passwd")

    def test_nonexistent_backup_raises(self, backup_env):
        bm, _, _ = backup_env
        with pytest.raises(ValueError, match="Backup not found"):
            bm.restore_backup("nonexistent.zip")


class TestDeleteBackup:
    """Tests for BackupManager.delete_backup."""

    def test_delete_existing(self, backup_env):
        bm, _, _ = backup_env
        zip_path = bm.create_backup("to delete")
        name = os.path.basename(zip_path)
        assert bm.delete_backup(name) is True
        assert not os.path.exists(zip_path)

    def test_delete_nonexistent_returns_false(self, backup_env):
        bm, _, _ = backup_env
        assert bm.delete_backup("nonexistent.zip") is False

    def test_path_traversal_blocked(self, backup_env):
        bm, _, _ = backup_env
        with pytest.raises(ValueError, match="Invalid backup name"):
            bm.delete_backup("../../../etc/passwd")


class TestCleanupOldBackups:
    """Tests for BackupManager.cleanup_old_backups."""

    def test_keeps_recent_deletes_old(self, backup_env):
        bm, _, _ = backup_env
        for i in range(5):
            bm.create_backup(f"backup-{i}")
            time.sleep(0.02)  # Ensure different timestamps

        deleted = bm.cleanup_old_backups(keep_count=3)
        assert deleted == 2
        assert len(bm.list_backups()) == 3
```

**Step 2: Run tests**

Run: `python3 -m pytest tests/test_backup_manager.py -v`
Expected: All pass.

**Step 3: Commit**

```bash
git add tests/test_backup_manager.py
git commit -m "test: add backup_manager tests (create, restore, delete, cleanup)"
```

---

### Task 8: Write test_validator.py

**Files:**
- Create: `tests/test_validator.py`

**Step 1: Write tests**

```python
"""Tests for validator module — output parsing and binary verification."""

import os
import stat
import subprocess
from unittest.mock import patch

import pytest

from validator import NagiosValidator


class TestParseOutput:
    """Unit tests for NagiosValidator._parse_output (pure function)."""

    def setup_method(self):
        self.v = NagiosValidator()

    def test_clean_output(self):
        output = (
            "Nagios Core 4.4.6\n"
            "Total Warnings: 0\n"
            "Total Errors:   0\n"
            "Things look okay - No serious problems were detected\n"
        )
        result = self.v._parse_output(output, exit_success=True)
        assert result.success is True
        assert result.total_errors == 0
        assert result.total_warnings == 0

    def test_single_error(self):
        output = (
            "Error: Could not find host 'web-99'\n"
            "Total Warnings: 0\n"
            "Total Errors:   1\n"
        )
        result = self.v._parse_output(output, exit_success=False)
        assert result.success is False
        assert result.total_errors == 1
        assert "web-99" in result.errors[0]["message"]

    def test_error_with_file_and_line(self):
        output = (
            "Error in file '/etc/nagios/hosts.cfg' on line 42: "
            "Could not find host 'missing-host'\n"
            "Total Errors:   1\n"
        )
        result = self.v._parse_output(output, exit_success=False)
        assert result.total_errors == 1
        assert result.errors[0]["file"] == "/etc/nagios/hosts.cfg"
        assert result.errors[0]["line"] == 42

    def test_config_error_prefix(self):
        output = "CONFIG ERROR: Invalid directive 'foo'\nTotal Errors: 1\n"
        result = self.v._parse_output(output, exit_success=False)
        assert result.total_errors == 1

    def test_warnings(self):
        output = (
            "Warning: Host 'web-01' has no services\n"
            "Warning: Unused command 'old-check'\n"
            "Total Warnings: 2\n"
            "Total Errors:   0\n"
        )
        result = self.v._parse_output(output, exit_success=True)
        assert result.success is True
        assert result.total_warnings == 2
        assert len(result.warnings) == 2

    def test_mixed_errors_and_warnings(self):
        output = (
            "Warning: Something minor\n"
            "Error: Something critical\n"
            "Total Warnings: 1\n"
            "Total Errors:   1\n"
        )
        result = self.v._parse_output(output, exit_success=False)
        assert result.success is False
        assert result.total_errors == 1
        assert result.total_warnings == 1

    def test_summary_line_overrides_counted(self):
        # If summary says 3 errors but we only parsed 1, use max
        output = (
            "Error: One detected error\n"
            "Total Errors:   3\n"
        )
        result = self.v._parse_output(output, exit_success=False)
        assert result.total_errors == 3

    def test_exit_failure_with_zero_parsed_errors(self):
        # Exit code failed but no parseable errors — still not success
        output = "Some unexpected output\nTotal Errors: 0\n"
        result = self.v._parse_output(output, exit_success=False)
        assert result.success is False


class TestCheckBinaryExists:
    """Tests for NagiosValidator.check_binary_exists."""

    def test_nonexistent_binary(self, tmp_path):
        v = NagiosValidator(nagios_bin=str(tmp_path / "nonexistent"))
        exists, msg = v.check_binary_exists()
        assert exists is False
        assert "not found" in msg

    def test_existing_non_executable(self, tmp_path):
        binary = tmp_path / "nagios"
        binary.write_text("not a real binary")
        binary.chmod(stat.S_IRUSR)
        v = NagiosValidator(nagios_bin=str(binary))
        exists, msg = v.check_binary_exists()
        assert exists is False
        assert "not executable" in msg

    def test_existing_executable(self, tmp_path):
        binary = tmp_path / "nagios"
        binary.write_text("#!/bin/sh\necho hi")
        binary.chmod(stat.S_IRWXU)
        v = NagiosValidator(nagios_bin=str(binary))
        exists, msg = v.check_binary_exists()
        assert exists is True


class TestVerifyBinary:
    """Tests for NagiosValidator.verify_binary with mocked subprocess."""

    def test_valid_nagios_binary(self, tmp_path):
        binary = tmp_path / "nagios"
        binary.write_text("#!/bin/sh")
        binary.chmod(stat.S_IRWXU)
        v = NagiosValidator(nagios_bin=str(binary))

        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="Nagios Core 4.4.6\nCopyright...\n", stderr="")
        with patch("subprocess.run", return_value=mock_result):
            result = v.verify_binary()
        assert result.success is True
        assert "4.4.6" in result.data

    def test_non_nagios_binary(self, tmp_path):
        binary = tmp_path / "nagios"
        binary.write_text("#!/bin/sh")
        binary.chmod(stat.S_IRWXU)
        v = NagiosValidator(nagios_bin=str(binary))

        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="Apache HTTP Server\n", stderr="")
        with patch("subprocess.run", return_value=mock_result):
            result = v.verify_binary()
        assert result.success is False
        assert "does not appear to be Nagios" in result.error

    def test_timeout(self, tmp_path):
        binary = tmp_path / "nagios"
        binary.write_text("#!/bin/sh")
        binary.chmod(stat.S_IRWXU)
        v = NagiosValidator(nagios_bin=str(binary))

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 5)):
            result = v.verify_binary()
        assert result.success is False
        assert "timed out" in result.error
```

**Step 2: Run tests**

Run: `python3 -m pytest tests/test_validator.py -v`
Expected: All pass.

**Step 3: Commit**

```bash
git add tests/test_validator.py
git commit -m "test: add validator tests (output parsing, binary verification)"
```

---

### Task 9: Write test_parser_errors.py

**Files:**
- Create: `tests/test_parser_errors.py`

**Step 1: Write tests**

```python
"""Tests for nagios_parser error handling and edge cases."""

from pathlib import Path

import pytest

from nagios_parser import NagiosConfigParser


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
```

**Step 2: Run tests**

Run: `python3 -m pytest tests/test_parser_errors.py -v`
Expected: All pass.

**Step 3: Commit**

```bash
git add tests/test_parser_errors.py
git commit -m "test: add parser error handling and edge case tests"
```

---

### Task 10: Run full test suite and verify

**Step 1: Run all tests**

Run: `python3 -m pytest tests/ -v`
Expected: All tests pass. No regressions from pruning. New tests all green.

**Step 2: Check test count summary**

Verify:
- `test_conventions.py` gone (test count decreased)
- `test_atomic_writes.py` still has 3 test methods (1 rewritten, 2 unchanged)
- `test_health_check.py` unchanged count, no failures
- 4 new test files present: `test_git_service.py`, `test_backup_manager.py`, `test_validator.py`, `test_parser_errors.py`
