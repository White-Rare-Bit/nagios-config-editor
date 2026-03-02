# L01: tests/test_candidate_manager.py — CREATE

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Layer:** 1 — Backend Core
**Action:** CREATE
**Path:** `tests/test_candidate_manager.py`
**Dependencies:** L01-candidate-manager.md must be implemented first
**Goal:** Comprehensive test suite for CandidateManager (~62 tests across 17 test classes)

---

## Architecture

TDD approach: write tests first in logical groups, implement CandidateManager to make them pass. Tests use a shared `config_dir` fixture that creates a temp directory with sample Nagios config files.

## Imports

```python
import json
import os
import shutil
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from backup_manager import BackupManager
from candidate_manager import CandidateManager
```

> **Commandment 10 (Linting):** All test code must pass `ruff check` and `ruff format --check` before committing. The verification section includes the lint check command.

## Fixtures

### `config_dir` (function-scoped)

Creates a temp directory with:

**`hosts.cfg`:**
```
define host {
    host_name                      web-01
    alias                          Web Server
    address                        10.0.0.1
}

define host {
    host_name                      web-02
    alias                          Backup Server
    address                        10.0.0.2
}
```

**`services.cfg`:**
```
define service {
    host_name                      web-01
    service_description            HTTP
    check_command                  check_http
}
```

Yields directory path. Cleanup via `shutil.rmtree` in teardown.

### `cm(config_dir)` (function-scoped)

Returns `CandidateManager(config_dir)`.

### `config_dir_with_nagios_cfg(tmp_path)` (function-scoped, inside TestNagiosCfgRewrite)

Creates a directory with:
- `hosts.cfg` (one host)
- `conf.d/services.cfg` (one service)
- `resource.cfg` (one line: `$USER1$=/usr/local/nagios/libexec`)
- `nagios.cfg` with absolute path directives:
  ```
  # Nagios config
  cfg_file=<dir>/hosts.cfg
  cfg_dir=<dir>/conf.d
  resource_file=<dir>/resource.cfg
  log_file=<dir>/var/nagios.log
  object_cache_file=<dir>/var/objects.cache
  status_file=<dir>/var/status.dat
  ```

## Test Classes and Methods

### TestSessionLifecycle (8 tests)

```python
def test_no_session_initially(cm):
    assert cm.has_session() is False
    assert cm.get_session_info() is None

def test_init_session_creates_candidate_dir(cm):
    result = cm.init_session("sess-1", "Test User", "test@example.com")
    assert result.success
    assert cm.has_session()
    assert os.path.isdir(cm.candidate_path)

def test_init_session_copies_config_files(cm):
    cm.init_session("sess-1")
    assert os.path.exists(os.path.join(cm.candidate_path, "hosts.cfg"))
    assert os.path.exists(os.path.join(cm.candidate_path, "services.cfg"))

def test_init_session_creates_git_repo(cm):
    cm.init_session("sess-1")
    assert os.path.isdir(os.path.join(cm.candidate_path, ".git"))

def test_session_info_returns_details(cm):
    cm.init_session("sess-1", "Test User")
    info = cm.get_session_info()
    assert info["session_id"] == "sess-1"
    assert info["user_name"] == "Test User"
    assert info["undo_count"] == 0

def test_can_modify_with_correct_session(cm):
    cm.init_session("sess-1")
    assert cm.can_modify("sess-1") is True
    assert cm.can_modify("sess-2") is False

def test_can_modify_when_no_session(cm):
    assert cm.can_modify("any-session") is True

def test_discard_removes_candidate_dir(cm):
    cm.init_session("sess-1")
    result = cm.discard()
    assert result.success
    assert cm.has_session() is False
    assert not os.path.exists(cm.candidate_path)

def test_double_init_fails(cm):
    cm.init_session("sess-1")
    result = cm.init_session("sess-2")
    assert not result.success
```

### TestLiveConfigImmutability (4 tests)

> **Commandment 1 enforcement.** These tests verify the core invariant: the running (live) config is NEVER modified until `apply()` is called. Each test performs a mutation, then asserts the running directory is byte-for-byte identical to its pre-mutation state.

```python
def _snapshot_dir(path):
    """Return dict of {relative_path: content} for all files under path."""
    result = {}
    for root, _dirs, files in os.walk(path):
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, path)
            result[rel] = Path(full).read_bytes()
    return result

def test_edit_does_not_touch_running(cm):
    cm.init_session("sess-1")
    before = _snapshot_dir(cm.running_path)
    hosts_path = os.path.join(cm.candidate_path, "hosts.cfg")
    cm.edit_object(hosts_path, 1, {"host_name": "web-01", "alias": "Changed", "address": "10.0.0.1"}, "host")
    after = _snapshot_dir(cm.running_path)
    assert before == after

def test_delete_does_not_touch_running(cm):
    cm.init_session("sess-1")
    before = _snapshot_dir(cm.running_path)
    hosts_path = os.path.join(cm.candidate_path, "hosts.cfg")
    cm.delete_object(hosts_path, 7)
    after = _snapshot_dir(cm.running_path)
    assert before == after

def test_create_does_not_touch_running(cm):
    cm.init_session("sess-1")
    before = _snapshot_dir(cm.running_path)
    hosts_path = os.path.join(cm.candidate_path, "hosts.cfg")
    cm.create_object(hosts_path, "host", {"host_name": "web-99", "alias": "Test", "address": "10.0.0.99"})
    after = _snapshot_dir(cm.running_path)
    assert before == after

def test_file_ops_do_not_touch_running(cm):
    cm.init_session("sess-1")
    before = _snapshot_dir(cm.running_path)
    new_file = os.path.join(cm.candidate_path, "new.cfg")
    cm.create_file(new_file)
    target = os.path.join(cm.candidate_path, "services-moved.cfg")
    cm.move_file(os.path.join(cm.candidate_path, "services.cfg"), target)
    cm.delete_file(new_file)
    after = _snapshot_dir(cm.running_path)
    assert before == after
```

### TestAuditLogging (4 tests)

> **Commandment 3 enforcement.** All CandidateManager operations must produce audit log entries via `audit_service.log_audit()`. These tests use `unittest.mock.patch` to verify the audit function is called with the correct action type.

```python
def test_init_session_logs_audit(cm):
    with patch("candidate_manager.log_audit") as mock_audit:
        cm.init_session("sess-1", "Test User", "test@example.com")
        mock_audit.assert_called()
        call_args = mock_audit.call_args
        assert call_args.kwargs.get("action") == "candidate_init" or call_args[0][0] == "candidate_init"

def test_apply_logs_audit(cm):
    cm.init_session("sess-1")
    with patch("candidate_manager.log_audit") as mock_audit:
        cm.apply()
        actions = [c[0][0] if c[0] else c[1].get("action") for c in mock_audit.call_args_list]
        assert "candidate_apply" in actions

def test_discard_logs_audit(cm):
    cm.init_session("sess-1")
    with patch("candidate_manager.log_audit") as mock_audit:
        cm.discard()
        mock_audit.assert_called()
        call_args = mock_audit.call_args
        assert call_args.kwargs.get("action") == "candidate_discard" or call_args[0][0] == "candidate_discard"

def test_edit_logs_audit(cm):
    cm.init_session("sess-1")
    hosts_path = os.path.join(cm.candidate_path, "hosts.cfg")
    with patch("candidate_manager.log_audit") as mock_audit:
        cm.edit_object(hosts_path, 1, {"host_name": "web-01", "alias": "Changed", "address": "10.0.0.1"}, "host")
        mock_audit.assert_called()
```

### TestNagiosCfgRewrite (5 tests)

Uses `config_dir_with_nagios_cfg` fixture. Creates CandidateManager with `nagios_cfg` param.

```python
def test_cfg_file_directives_rewritten(config_dir_with_nagios_cfg):
    # .validation-nagios.cfg exists and contains .candidate/ paths
    # Original absolute paths are NOT present

def test_cfg_dir_directives_rewritten(config_dir_with_nagios_cfg):
    # Original cfg_dir path absent; .candidate/conf.d present

def test_resource_file_rewritten(config_dir_with_nagios_cfg):
    # .candidate/resource.cfg present in rewritten config

def test_var_directories_created(config_dir_with_nagios_cfg):
    # var/ directory exists under candidate

def test_comments_pass_through(config_dir_with_nagios_cfg):
    # "# Nagios config" comment preserved in output
```

### TestBackupExclusion (1 test)

```python
def test_backup_excludes_candidate_dir(config_dir):
    bm = BackupManager(config_dir)
    cm = CandidateManager(config_dir)
    cm.init_session("sess-1")
    backup_path = bm.create_backup("test")
    with zipfile.ZipFile(backup_path) as zf:
        assert not any(".candidate/" in name for name in zf.namelist())
```

### TestCopyExcludes (2 tests)

```python
def test_bak_files_excluded(config_dir):
    # Create a .bak file in running config before init
    Path(config_dir, "hosts.cfg.bak").write_text("backup")
    cm = CandidateManager(config_dir)
    cm.init_session("sess-1")
    assert not os.path.exists(os.path.join(cm.candidate_path, "hosts.cfg.bak"))

def test_backup_dir_excluded(config_dir):
    # Create a backup/ directory in running config before init
    os.makedirs(os.path.join(config_dir, "backup"))
    Path(config_dir, "backup", "old.cfg").write_text("old")
    cm = CandidateManager(config_dir)
    cm.init_session("sess-1")
    assert not os.path.exists(os.path.join(cm.candidate_path, "backup"))
```

### TestConcurrency (1 test)

```python
def test_file_lock_prevents_double_init(config_dir):
    cm1 = CandidateManager(config_dir)
    cm2 = CandidateManager(config_dir)
    result1 = cm1.init_session("sess-1")
    assert result1.success
    result2 = cm2.init_session("sess-2")
    assert not result2.success
```

### TestRestorePendingState (3 tests)

```python
def test_session_starts_active(cm):
    cm.init_session("sess-1")
    assert cm.get_session_state() == "active"

def test_set_restore_pending(cm):
    cm.init_session("sess-1")
    cm.set_restore_pending()
    assert cm.get_session_state() == "restore_pending"

def test_session_info_includes_state(cm):
    cm.init_session("sess-1")
    info = cm.get_session_info()
    assert info["state"] == "active"
```

### TestObjectOperations (6 tests)

All tests call `cm.init_session("sess-1")` first.

```python
def test_edit_object(cm):
    cm.init_session("sess-1")
    hosts_path = os.path.join(cm.candidate_path, "hosts.cfg")
    result = cm.edit_object(hosts_path, 1, {"host_name": "web-01", "alias": "Updated Web", "address": "10.0.0.1"}, "host")
    assert result.success
    # Verify candidate file changed
    content = Path(hosts_path).read_text()
    assert "Updated Web" in content
    # Verify running file unchanged
    running = Path(cm.running_path, "hosts.cfg").read_text()
    assert "Web Server" in running

def test_delete_object(cm):
    cm.init_session("sess-1")
    hosts_path = os.path.join(cm.candidate_path, "hosts.cfg")
    # Delete web-02 (starts at line 7 in the fixture)
    result = cm.delete_object(hosts_path, 7)
    assert result.success
    content = Path(hosts_path).read_text()
    assert "web-02" not in content
    assert "web-01" in content

def test_create_object(cm):
    cm.init_session("sess-1")
    hosts_path = os.path.join(cm.candidate_path, "hosts.cfg")
    result = cm.create_object(hosts_path, "host", {"host_name": "web-03", "alias": "New", "address": "10.0.0.3"})
    assert result.success
    content = Path(hosts_path).read_text()
    assert "web-03" in content

def test_move_object(cm):
    cm.init_session("sess-1")
    hosts_path = os.path.join(cm.candidate_path, "hosts.cfg")
    services_path = os.path.join(cm.candidate_path, "services.cfg")
    # Parse to get line number
    from nagios_parser import NagiosConfigParser
    parser = NagiosConfigParser(cm.candidate_path)
    parser.parse_all()
    host_obj = [o for o in parser.objects if o.attributes.get("host_name") == "web-01" and o.object_type == "host"][0]
    result = cm.move_object(hosts_path, host_obj.line_number, services_path, "host", dict(host_obj.attributes))
    assert result.success

def test_edit_creates_undo_entry(cm):
    cm.init_session("sess-1")
    hosts_path = os.path.join(cm.candidate_path, "hosts.cfg")
    cm.edit_object(hosts_path, 1, {"host_name": "web-01", "alias": "Changed", "address": "10.0.0.1"}, "host")
    info = cm.get_session_info()
    assert info["undo_count"] == 1

def test_multi_file_delete_correct_objects(cm):
    cm.init_session("sess-1")
    hosts_path = os.path.join(cm.candidate_path, "hosts.cfg")
    services_path = os.path.join(cm.candidate_path, "services.cfg")
    # Parse to find line numbers
    from nagios_parser import NagiosConfigParser
    parser = NagiosConfigParser(cm.candidate_path)
    parser.parse_all()
    web02 = [o for o in parser.objects if o.attributes.get("host_name") == "web-02" and o.object_type == "host"][0]
    http_svc = [o for o in parser.objects if o.object_type == "service"][0]
    # Delete web-02 first, then service
    cm.delete_object(hosts_path, web02.line_number)
    # Re-parse to get updated line number for service
    parser2 = NagiosConfigParser(cm.candidate_path)
    parser2.parse_all()
    http_svc2 = [o for o in parser2.objects if o.object_type == "service"][0]
    cm.delete_object(services_path, http_svc2.line_number)
    # Verify: only web-01 host remains, no services
    parser3 = NagiosConfigParser(cm.candidate_path)
    parser3.parse_all()
    hosts = [o for o in parser3.objects if o.object_type == "host"]
    services = [o for o in parser3.objects if o.object_type == "service"]
    assert len(hosts) == 1
    assert hosts[0].attributes["host_name"] == "web-01"
    assert len(services) == 0
```

### TestReferenceAnalysis (3 tests)

References are deferred to apply time. `edit_object()` never updates cross-references.
`analyze_references()` detects pending name changes. `apply(update_references=True)` updates them.

```python
def test_edit_does_not_update_references(cm):
    cm.init_session("sess-1")
    hosts_path = os.path.join(cm.candidate_path, "hosts.cfg")
    result = cm.edit_object(hosts_path, 1, {"host_name": "web-server-01", "alias": "Web Server", "address": "10.0.0.1"}, "host")
    assert result.success
    # Service should still reference old name — references are deferred
    services_content = Path(os.path.join(cm.candidate_path, "services.cfg")).read_text()
    assert "web-01" in services_content

def test_analyze_references_detects_name_change(cm):
    cm.init_session("sess-1")
    hosts_path = os.path.join(cm.candidate_path, "hosts.cfg")
    cm.edit_object(hosts_path, 1, {"host_name": "web-server-01", "alias": "Web Server", "address": "10.0.0.1"}, "host")
    result = cm.analyze_references()
    assert result.success
    assert result.data["totalReferences"] > 0
    assert result.data["nameChanges"][0]["oldName"] == "web-01"
    assert result.data["nameChanges"][0]["newName"] == "web-server-01"

def test_apply_with_reference_update(cm):
    cm.init_session("sess-1")
    hosts_path = os.path.join(cm.candidate_path, "hosts.cfg")
    cm.edit_object(hosts_path, 1, {"host_name": "web-server-01", "alias": "Web Server", "address": "10.0.0.1"}, "host")
    result = cm.apply(update_references=True)
    assert result.success
    # After apply, running config should have updated references
    services_content = Path(os.path.join(cm._running_path, "services.cfg")).read_text()
    assert "web-server-01" in services_content
```

### TestPathSafety (4 tests)

```python
def test_edit_rejects_path_traversal(cm):
    cm.init_session("sess-1")
    result = cm.edit_object("../etc/passwd", 1, {}, "host")
    assert not result.success

def test_create_file_rejects_null_byte(cm):
    cm.init_session("sess-1")
    result = cm.create_file(os.path.join(cm.candidate_path, "evil\x00.cfg"))
    assert not result.success

def test_move_file_rejects_escape(cm):
    cm.init_session("sess-1")
    source = os.path.join(cm.candidate_path, "hosts.cfg")
    result = cm.move_file(source, "/tmp/stolen.cfg")
    assert not result.success

def test_delete_folder_rejects_traversal(cm):
    cm.init_session("sess-1")
    result = cm.delete_folder(os.path.join(cm.candidate_path, ".."))
    assert not result.success
```

### TestParserCorruptionGuard (1 test)

```python
def test_edit_reverts_on_corrupt_output(cm, monkeypatch):
    cm.init_session("sess-1")
    hosts_path = os.path.join(cm.candidate_path, "hosts.cfg")
    original_content = Path(hosts_path).read_text()

    # Monkeypatch edit_object_in_file to append garbage after write
    from file_operations import edit_object_in_file as real_edit
    def corrupt_edit(*args, **kwargs):
        result = real_edit(*args, **kwargs)
        if result.success:
            with open(args[0], "a") as f:
                f.write("\nUNCLOSED GARBAGE {{{")
        return result

    monkeypatch.setattr("candidate_manager.edit_object_in_file", corrupt_edit)
    result = cm.edit_object(hosts_path, 1, {"host_name": "web-01", "alias": "Bad", "address": "10.0.0.1"}, "host")
    assert not result.success
    # File should be reverted
    assert "UNCLOSED GARBAGE" not in Path(hosts_path).read_text()
```

### TestUndo (6 tests)

```python
def test_undo_reverts_edit(cm):
    cm.init_session("sess-1")
    hosts_path = os.path.join(cm.candidate_path, "hosts.cfg")
    cm.edit_object(hosts_path, 1, {"host_name": "web-01", "alias": "Changed", "address": "10.0.0.1"}, "host")
    cm.undo()
    content = Path(hosts_path).read_text()
    assert "Web Server" in content

def test_undo_reverts_delete(cm):
    cm.init_session("sess-1")
    hosts_path = os.path.join(cm.candidate_path, "hosts.cfg")
    cm.delete_object(hosts_path, 7)  # delete web-02
    cm.undo()
    content = Path(hosts_path).read_text()
    assert "web-02" in content

def test_undo_count_decrements(cm):
    cm.init_session("sess-1")
    hosts_path = os.path.join(cm.candidate_path, "hosts.cfg")
    cm.edit_object(hosts_path, 1, {"host_name": "web-01", "alias": "A", "address": "10.0.0.1"}, "host")
    cm.edit_object(hosts_path, 1, {"host_name": "web-01", "alias": "B", "address": "10.0.0.1"}, "host")
    assert cm.get_session_info()["undo_count"] == 2
    cm.undo()
    assert cm.get_session_info()["undo_count"] == 1
    cm.undo()
    assert cm.get_session_info()["undo_count"] == 0

def test_undo_at_baseline_fails(cm):
    cm.init_session("sess-1")
    result = cm.undo()
    assert not result.success

def test_undo_returns_description(cm):
    cm.init_session("sess-1")
    hosts_path = os.path.join(cm.candidate_path, "hosts.cfg")
    cm.edit_object(hosts_path, 1, {"host_name": "web-01", "alias": "Changed", "address": "10.0.0.1"}, "host", description="Edit web-01")
    result = cm.undo()
    assert "Edit web-01" in result.data["description"]

def test_undo_cleans_empty_dirs(cm):
    cm.init_session("sess-1")
    folder_path = os.path.join(cm.candidate_path, "subdir")
    cm.create_folder(folder_path)
    assert os.path.isdir(folder_path)
    cm.undo()
    assert not os.path.exists(folder_path)
```

### TestFileOperations (7 tests)

```python
def test_create_file(cm):
    cm.init_session("sess-1")
    new_file = os.path.join(cm.candidate_path, "new.cfg")
    result = cm.create_file(new_file)
    assert result.success
    assert os.path.exists(new_file)

def test_delete_file(cm):
    cm.init_session("sess-1")
    target = os.path.join(cm.candidate_path, "services.cfg")
    result = cm.delete_file(target)
    assert result.success
    assert not os.path.exists(target)

def test_move_file(cm):
    cm.init_session("sess-1")
    source = os.path.join(cm.candidate_path, "services.cfg")
    target = os.path.join(cm.candidate_path, "moved-services.cfg")
    result = cm.move_file(source, target)
    assert result.success
    assert not os.path.exists(source)
    assert os.path.exists(target)

def test_create_folder(cm):
    cm.init_session("sess-1")
    folder = os.path.join(cm.candidate_path, "new-folder")
    result = cm.create_folder(folder)
    assert result.success
    assert os.path.isdir(folder)

def test_delete_folder(cm):
    cm.init_session("sess-1")
    folder = os.path.join(cm.candidate_path, "new-folder")
    cm.create_folder(folder)
    result = cm.delete_folder(folder)
    assert result.success
    assert not os.path.exists(folder)

def test_move_folder(cm):
    cm.init_session("sess-1")
    source = os.path.join(cm.candidate_path, "folder-a")
    target = os.path.join(cm.candidate_path, "folder-b")
    cm.create_folder(source)
    result = cm.move_folder(source, target)
    assert result.success
    assert not os.path.exists(source)
    assert os.path.isdir(target)

def test_file_ops_are_undoable(cm):
    cm.init_session("sess-1")
    new_file = os.path.join(cm.candidate_path, "undo-test.cfg")
    cm.create_file(new_file)
    assert os.path.exists(new_file)
    cm.undo()
    assert not os.path.exists(new_file)
```

### TestDiffAndApply (9+ tests)

```python
def test_get_diff_shows_changes(cm):
    cm.init_session("sess-1")
    hosts_path = os.path.join(cm.candidate_path, "hosts.cfg")
    cm.edit_object(hosts_path, 1, {"host_name": "web-01", "alias": "Changed", "address": "10.0.0.1"}, "host")
    result = cm.get_diff()
    assert result.success
    assert len(result.data["changed_files"]) > 0
    assert "unified_diff" in result.data

def test_get_diff_empty_when_no_changes(cm):
    cm.init_session("sess-1")
    result = cm.get_diff()
    assert result.success
    assert len(result.data["changed_files"]) == 0

def test_get_diff_includes_undo_count(cm):
    cm.init_session("sess-1")
    hosts_path = os.path.join(cm.candidate_path, "hosts.cfg")
    cm.edit_object(hosts_path, 1, {"host_name": "web-01", "alias": "Changed", "address": "10.0.0.1"}, "host")
    result = cm.get_diff()
    assert result.data["undo_count"] == 1

def test_get_file_diff_returns_unified(cm):
    cm.init_session("sess-1")
    hosts_path = os.path.join(cm.candidate_path, "hosts.cfg")
    cm.edit_object(hosts_path, 1, {"host_name": "web-01", "alias": "Changed", "address": "10.0.0.1"}, "host")
    result = cm.get_file_diff("hosts.cfg")
    assert result.success
    assert "diff" in result.data

def test_detect_conflicts_none_initially(cm):
    cm.init_session("sess-1")
    conflicts = cm.detect_conflicts()
    assert conflicts == []

def test_detect_conflicts_after_external_change(cm):
    cm.init_session("sess-1")
    # Modify running file externally
    running_hosts = os.path.join(cm.running_path, "hosts.cfg")
    Path(running_hosts).write_text("# externally modified\n")
    conflicts = cm.detect_conflicts()
    assert len(conflicts) >= 1

def test_apply_copies_to_running(cm):
    cm.init_session("sess-1")
    hosts_path = os.path.join(cm.candidate_path, "hosts.cfg")
    cm.edit_object(hosts_path, 1, {"host_name": "web-01", "alias": "Applied", "address": "10.0.0.1"}, "host")
    result = cm.apply()
    assert result.success
    running_content = Path(os.path.join(cm.running_path, "hosts.cfg")).read_text()
    assert "Applied" in running_content

def test_apply_cleans_up_candidate(cm):
    cm.init_session("sess-1")
    cm.apply()
    assert cm.has_session() is False

def test_apply_removes_empty_dirs(cm):
    cm.init_session("sess-1")
    # Create a subdirectory with a file, then delete the file
    subdir = os.path.join(cm.candidate_path, "subdir")
    os.makedirs(subdir, exist_ok=True)
    sub_file = os.path.join(subdir, "test.cfg")
    Path(sub_file).write_text("define host {\n    host_name test\n}\n")
    cm._git_commit("add subdir")
    os.remove(sub_file)
    cm._git_commit("remove file")
    # Corresponding running dir should exist
    running_subdir = os.path.join(cm.running_path, "subdir")
    os.makedirs(running_subdir, exist_ok=True)
    Path(os.path.join(running_subdir, "test.cfg")).write_text("old")
    cm.apply()
    # Empty subdir should be cleaned up in running
    assert not os.path.exists(running_subdir)
```

### TestApplyBackup (1 test)

```python
def test_apply_creates_backup(config_dir):
    backup_dir = os.path.join(config_dir, "backups")
    bm = BackupManager(config_dir, backup_dir)
    cm = CandidateManager(config_dir, backup_manager=bm)
    cm.init_session("sess-1")
    cm.apply()
    zips = [f for f in os.listdir(backup_dir) if f.endswith(".zip")]
    assert len(zips) >= 1
    assert any("pre_candidate_apply" in z for z in zips)
```

### TestValidation (1 test)

```python
def test_validate_returns_result(cm):
    cm.init_session("sess-1")
    result = cm.validate()
    # Either success or "not configured" since nagios binary likely not available in test
    assert result.success or "not configured" in result.error.lower()
```

### TestBulkOperations (5 tests)

```python
def test_bulk_edit(cm):
    cm.init_session("sess-1")
    from nagios_parser import NagiosConfigParser
    parser = NagiosConfigParser(cm.candidate_path)
    parser.parse_all()
    hosts = [o for o in parser.objects if o.object_type == "host"]
    edits = [{"file_path": os.path.join(cm.candidate_path, "hosts.cfg"), "line_number": h.line_number, "new_attrs": {**h.attributes, "alias": f"Bulk-{h.attributes['host_name']}"}, "obj_type": "host"} for h in hosts]
    result = cm.bulk_edit(edits, "Bulk rename")
    assert result.success
    assert result.data["count"] == len(hosts)
    assert cm.get_session_info()["undo_count"] == 1

def test_bulk_edit_two_objects_same_file(cm):
    cm.init_session("sess-1")
    from nagios_parser import NagiosConfigParser
    parser = NagiosConfigParser(cm.candidate_path)
    parser.parse_all()
    hosts = [o for o in parser.objects if o.object_type == "host"]
    edits = [{"file_path": os.path.join(cm.candidate_path, "hosts.cfg"), "line_number": h.line_number, "new_attrs": {**h.attributes, "alias": f"Bulk-{h.attributes['host_name']}"}, "obj_type": "host"} for h in hosts]
    result = cm.bulk_edit(edits, "Bulk same file")
    assert result.success
    content = Path(os.path.join(cm.candidate_path, "hosts.cfg")).read_text()
    assert "Bulk-web-01" in content
    assert "Bulk-web-02" in content

def test_bulk_move(cm):
    cm.init_session("sess-1")
    from nagios_parser import NagiosConfigParser
    parser = NagiosConfigParser(cm.candidate_path)
    parser.parse_all()
    hosts = [o for o in parser.objects if o.object_type == "host"]
    target = os.path.join(cm.candidate_path, "bulk-target.cfg")
    Path(target).touch()
    cm._git_commit("add target")
    moves = [{"source_file": os.path.join(cm.candidate_path, "hosts.cfg"), "source_line": h.line_number, "target_file": target, "obj_type": "host", "attrs": dict(h.attributes)} for h in hosts]
    result = cm.bulk_move(moves, "Bulk move")
    assert result.success
    parser2 = NagiosConfigParser(cm.candidate_path)
    parser2.parse_all()
    target_hosts = [o for o in parser2.objects if o.source_file == target and o.object_type == "host"]
    assert len(target_hosts) == len(hosts)

def test_bulk_delete(cm):
    cm.init_session("sess-1")
    from nagios_parser import NagiosConfigParser
    parser = NagiosConfigParser(cm.candidate_path)
    parser.parse_all()
    web02 = [o for o in parser.objects if o.attributes.get("host_name") == "web-02"][0]
    svc = [o for o in parser.objects if o.object_type == "service"][0]
    deletes = [
        {"file_path": os.path.join(cm.candidate_path, "hosts.cfg"), "line_number": web02.line_number},
        {"file_path": os.path.join(cm.candidate_path, "services.cfg"), "line_number": svc.line_number},
    ]
    result = cm.bulk_delete(deletes, "Bulk delete")
    assert result.success
    assert result.data["count"] == 2
    assert cm.get_session_info()["undo_count"] == 1

def test_bulk_delete_same_file(cm):
    cm.init_session("sess-1")
    from nagios_parser import NagiosConfigParser
    parser = NagiosConfigParser(cm.candidate_path)
    parser.parse_all()
    hosts = [o for o in parser.objects if o.object_type == "host"]
    deletes = [{"file_path": os.path.join(cm.candidate_path, "hosts.cfg"), "line_number": h.line_number} for h in hosts]
    result = cm.bulk_delete(deletes, "Delete all hosts")
    assert result.success
    parser2 = NagiosConfigParser(cm.candidate_path)
    parser2.parse_all()
    remaining = [o for o in parser2.objects if o.object_type == "host"]
    assert len(remaining) == 0
```

### TestBulkMoveInsertLine (1 test)

```python
def test_bulk_move_two_objects_to_same_target(cm):
    cm.init_session("sess-1")
    from nagios_parser import NagiosConfigParser
    parser = NagiosConfigParser(cm.candidate_path)
    parser.parse_all()
    hosts = [o for o in parser.objects if o.object_type == "host"]
    # Create target with one existing host
    target = os.path.join(cm.candidate_path, "target.cfg")
    Path(target).write_text('define host {\n    host_name                      existing\n    address                        1.1.1.1\n}\n')
    cm._git_commit("add target")
    moves = [{"source_file": os.path.join(cm.candidate_path, "hosts.cfg"), "source_line": h.line_number, "target_file": target, "obj_type": "host", "attrs": dict(h.attributes)} for h in hosts]
    result = cm.bulk_move(moves, "Move to target")
    assert result.success
    parser2 = NagiosConfigParser(cm.candidate_path)
    parser2.parse_all()
    target_hosts = [o for o in parser2.objects if o.source_file == target]
    assert len(target_hosts) == 3  # existing + 2 moved
```

---

## Error Handling Coverage (Commandment 4)

The following test classes verify proper error handling — no silent failures, no swallowed exceptions:

| Test Class | What It Verifies |
|------------|-----------------|
| `TestSessionLifecycle.test_double_init_fails` | Duplicate session init returns `OperationResult(False, ...)` |
| `TestPathSafety` (4 tests) | Path traversal, null bytes, and escape attempts all return `OperationResult(False, ...)` |
| `TestParserCorruptionGuard` | Corrupt output is caught, reverted, and returns `OperationResult(False, ...)` |
| `TestUndo.test_undo_at_baseline_fails` | Undo with nothing to undo returns `OperationResult(False, ...)` |
| `TestValidation.test_validate_returns_result` | Validation without nagios binary returns a meaningful error |

## Dead Code & Functionality Migration (Commandments 5 & 6)

This is a **new test file** — no dead code to delete. Once the candidate system fully replaces the staging system:

- `tests/test_staging_manager.py` (if it exists) becomes dead code and must be removed
- Tests that exercise staging-specific code paths in other test files must be updated or removed

These cleanup tasks are tracked in later layer plans.

## Verification

```bash
# Lint checks (Commandment 10)
ruff check tests/test_candidate_manager.py
ruff format --check tests/test_candidate_manager.py

# Run the full test suite
python3 -m pytest tests/test_candidate_manager.py -v

# Expected: 54 tests, all passing
# If CandidateManager not yet implemented, all tests should FAIL (TDD: red phase)
```

---

## Change Tracking (Commandment 8)

All implementation tasks for this test file. Tick off as completed.

- [ ] Create `tests/test_candidate_manager.py` with imports
- [ ] Implement `config_dir` fixture
- [ ] Implement `cm` fixture
- [ ] Implement `TestSessionLifecycle` (8 tests)
- [ ] Implement `TestLiveConfigImmutability` (4 tests) — C1 enforcement
- [ ] Implement `TestAuditLogging` (4 tests) — C3 enforcement
- [ ] Implement `TestNagiosCfgRewrite` (5 tests) with `config_dir_with_nagios_cfg` fixture
- [ ] Implement `TestBackupExclusion` (1 test)
- [ ] Implement `TestCopyExcludes` (2 tests)
- [ ] Implement `TestConcurrency` (1 test)
- [ ] Implement `TestRestorePendingState` (3 tests)
- [ ] Implement `TestObjectOperations` (6 tests)
- [ ] Implement `TestReferenceAnalysis` (3 tests)
- [ ] Implement `TestPathSafety` (4 tests) — C4 enforcement
- [ ] Implement `TestParserCorruptionGuard` (1 test) — C4 enforcement
- [ ] Implement `TestUndo` (6 tests)
- [ ] Implement `TestFileOperations` (7 tests)
- [ ] Implement `TestDiffAndApply` (9 tests)
- [ ] Implement `TestApplyBackup` (1 test)
- [ ] Implement `TestValidation` (1 test)
- [ ] Implement `TestBulkOperations` (5 tests)
- [ ] Implement `TestBulkMoveInsertLine` (1 test)
- [ ] Run `ruff check` and `ruff format --check` — clean (C10)
- [ ] Run full test suite — all tests pass (or all fail in TDD red phase)

---

## Commandments Compliance

- [x] **C1 — No live config mutation until Apply.** Directly enforced by `TestLiveConfigImmutability` (4 tests) which snapshots the running directory before mutations and asserts byte-for-byte equality afterward. The `test_apply_copies_to_running` test verifies that only `apply()` modifies the running config.
- [x] **C2 — UI visual parity.** N/A — this is a unit test file with no UI components. UI parity is tested in frontend Playwright tests.
- [x] **C3 — Full audit logging.** Directly enforced by `TestAuditLogging` (4 tests) which patches `log_audit()` and asserts it is called with correct action strings for init, apply, discard, and edit operations.
- [x] **C4 — Proper error handling everywhere.** Enforced by `TestPathSafety` (4 tests), `TestParserCorruptionGuard` (1 test), `TestUndo.test_undo_at_baseline_fails`, and `TestSessionLifecycle.test_double_init_fails` — all verify that error conditions return `OperationResult(False, ...)` with meaningful messages, not silent failures.
- [x] **C5 — Dead code deletion.** N/A — this is a new file. Deletion of obsolete staging tests is tracked in later layer plans (see Dead Code section above).
- [x] **C6 — Full functionality migration.** The test suite covers every public method of `CandidateManager`, ensuring all migrated functionality works correctly. Missing coverage would surface as untested methods during code review.
- [x] **C7 — Palo Alto candidate model.** The tests validate the copy-edit-apply lifecycle: `TestSessionLifecycle` tests session creation (copy), `TestObjectOperations` tests editing the candidate, and `TestDiffAndApply` tests applying back to running config.
- [x] **C8 — Change tracking document.** The Change Tracking section above provides a tickable checklist of all test implementation tasks.
- [x] **C9 — Complete planning before implementation.** Every test class, method, fixture, and assertion is specified before any test code is written. TDD red-phase approach ensures tests are written first.
- [x] **C10 — Linting enforcement.** The Verification section includes `ruff check` and `ruff format --check` commands. The Change Tracking checklist includes a lint verification step.
- [x] **C11 — Playwright validation.** N/A — this is a backend unit test file. Playwright tests for UI validation are addressed in frontend layer plans where UI changes occur.
