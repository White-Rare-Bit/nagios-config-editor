# Shadow Copy Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace JSON-diff staging with a shadow copy architecture — full directory copy on first edit, direct mutations, file-level undo snapshots, simplified apply.

**Architecture:** `ShadowCopyManager` replaces `StagingManager`. Config directory is copied on first edit; all mutations write to shadow copy. Apply copies changed files back. Frontend becomes stateless (server-authoritative). ~5000 lines removed, ~700 added.

**Tech Stack:** Python/Flask backend, vanilla JS frontend. `multiprocessing.Lock` for thread safety. Atomic file operations via `file_operations.py`.

**Design doc:** `docs/plans/2026-03-10-shadow-copy-design.md`

**Migration catalog:** `docs/shadow-copy-migration-catalog.md`

---

## Phase 1: Foundation (Tasks 1-6)

Build the new `ShadowCopyManager` and test it in isolation. No existing code is modified yet.

---

### Task 1: Extract Stable Key Utilities

Stable key functions live in `staging_manager.py` (lines 1323-1377) but are needed after that file is deleted. Move them to a standalone module.

**Files:**
- Create: `stable_keys.py`
- Create: `tests/test_stable_keys_module.py`
- Modify: `staging_manager.py:1323-1377` (import from new module)
- Modify: `nagios_service.py` (update imports if needed)

**Step 1: Write the test for the new module**

```python
# tests/test_stable_keys_module.py
import pytest
from stable_keys import generate_stable_key, parse_stable_key, generate_stable_key_for_object


def test_generate_stable_key():
    key = generate_stable_key("hosts.cfg", "host", "webserver1")
    assert key == "hosts.cfg|host|webserver1"


def test_parse_stable_key():
    source_file, obj_type, name = parse_stable_key("hosts.cfg|host|webserver1")
    assert source_file == "hosts.cfg"
    assert obj_type == "host"
    assert name == "webserver1"


def test_generate_stable_key_for_object():
    class FakeObj:
        source_file = "hosts.cfg"
        object_type = "host"
        def get_display_name(self):
            return "webserver1"

    key = generate_stable_key_for_object(FakeObj())
    assert key == "hosts.cfg|host|webserver1"


def test_parse_stable_key_with_pipes_in_name():
    source_file, obj_type, name = parse_stable_key("hosts.cfg|host|name|with|pipes")
    assert source_file == "hosts.cfg"
    assert obj_type == "host"
    assert name == "name|with|pipes"
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_stable_keys_module.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stable_keys'`

**Step 3: Create `stable_keys.py`**

Copy the three functions from `staging_manager.py` lines 1323-1377 into `stable_keys.py`. Read the existing implementations exactly — do not rewrite. Add only the necessary imports.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_stable_keys_module.py -v`
Expected: PASS

**Step 5: Update imports in `staging_manager.py`**

Make `staging_manager.py` import from `stable_keys` and re-export (so existing callers still work during migration). Read `staging_manager.py` lines 1318-1380 first to understand the current code.

**Step 6: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All existing tests still pass.

**Step 7: Commit**

```bash
git add stable_keys.py tests/test_stable_keys_module.py staging_manager.py
git commit -m "extract stable key utilities to standalone module"
```

---

### Task 2: Add Shadow Path to Server Config

Add a configurable `shadow_path` setting alongside the existing `backup_path`.

**Files:**
- Modify: `server_config.py:35-42` (PathsConfig), `server_config.py:87-117` (properties)
- Modify: `config/settings.json` (add default)

**Step 1: Read `server_config.py`**

Read the full file to understand the existing pattern for `backup_path` — property getter/setter, env var override, config file key.

**Step 2: Add `shadow_path` to `PathsConfig`**

Add `shadow_path: str = None` to the `PathsConfig` dataclass (after `backup_path` on line 39). Follow the exact same pattern as `backup_path`.

**Step 3: Add property getter/setter**

Add `shadow_path` property to `ServerConfig` following the `backup_path` pattern at lines 96-101. Add env var override support (`NBE_SHADOW_PATH`).

**Step 4: Add to `load_config()` and `save_config()`**

Ensure `shadow_path` is read from and written to `config/settings.json` following the existing field pattern.

**Step 5: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All tests pass.

**Step 6: Commit**

```bash
git add server_config.py
git commit -m "add shadow_path to server configuration"
```

---

### Task 3: ShadowCopyManager — Lifecycle and Lock

Build the core class with create/destroy shadow and session-based lock management.

**Files:**
- Create: `shadow_copy_manager.py`
- Create: `tests/test_shadow_copy_manager.py`

**Step 1: Write failing tests for lifecycle and lock**

```python
# tests/test_shadow_copy_manager.py
import os
import shutil
import tempfile
import pytest
from shadow_copy_manager import ShadowCopyManager
from operation_result import OperationResult  # or wherever OperationResult lives


@pytest.fixture
def setup_dirs():
    """Create temp config and shadow directories."""
    config_dir = tempfile.mkdtemp()
    shadow_base = tempfile.mkdtemp()
    # Create a sample config file
    os.makedirs(os.path.join(config_dir, "subdir"))
    with open(os.path.join(config_dir, "hosts.cfg"), "w") as f:
        f.write("define host {\n    host_name webserver1\n}\n")
    with open(os.path.join(config_dir, "subdir", "services.cfg"), "w") as f:
        f.write("define service {\n    service_description HTTP\n}\n")
    yield config_dir, shadow_base
    shutil.rmtree(config_dir, ignore_errors=True)
    shutil.rmtree(shadow_base, ignore_errors=True)


class TestShadowLifecycle:
    def test_has_shadow_initially_false(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        assert scm.has_shadow() is False

    def test_create_shadow_copies_all_cfg_files(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        result = scm.create_shadow("session-1", "user", "user@test.com")
        assert result.success
        assert scm.has_shadow()
        # Verify files copied
        shadow_hosts = os.path.join(shadow_base, "config", "hosts.cfg")
        shadow_services = os.path.join(shadow_base, "config", "subdir", "services.cfg")
        assert os.path.exists(shadow_hosts)
        assert os.path.exists(shadow_services)

    def test_create_shadow_when_already_exists_fails(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("session-1", "user", "user@test.com")
        result = scm.create_shadow("session-2", "user2", "user2@test.com")
        assert not result.success

    def test_destroy_shadow(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("session-1", "user", "user@test.com")
        result = scm.destroy_shadow()
        assert result.success
        assert scm.has_shadow() is False

    def test_destroy_when_no_shadow_succeeds(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        result = scm.destroy_shadow()
        assert result.success


class TestLockManagement:
    def test_lock_created_with_shadow(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("session-1", "Alice", "alice@test.com")
        status = scm.get_lock_status()
        assert status["locked"] is True
        assert status["session_id"] == "session-1"
        assert status["user_name"] == "Alice"

    def test_can_modify_correct_session(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("session-1", "Alice", "alice@test.com")
        assert scm.can_modify("session-1") is True
        assert scm.can_modify("session-2") is False

    def test_can_modify_when_no_shadow(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        assert scm.can_modify("any-session") is True

    def test_break_lock_destroys_shadow(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("session-1", "Alice", "alice@test.com")
        result = scm.break_lock()
        assert result.success
        assert scm.has_shadow() is False

    def test_get_lock_status_when_unlocked(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        status = scm.get_lock_status()
        assert status["locked"] is False
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_shadow_copy_manager.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shadow_copy_manager'`

**Step 3: Implement `ShadowCopyManager` — lifecycle + lock**

Create `shadow_copy_manager.py` with:
- `__init__(self, config_path, shadow_base_path)` — stores paths, creates `multiprocessing.Lock`
- `create_shadow()` — copies all files from config to `<shadow_base>/config/`, writes `<shadow_base>/lock.json`
- `destroy_shadow()` — removes `<shadow_base>/config/` and `<shadow_base>/lock.json` and `<shadow_base>/snapshots/`
- `has_shadow()` — checks if `<shadow_base>/config/` exists
- `get_lock_status()` — reads `lock.json`, returns dict
- `can_modify(session_id)` — if no shadow, return True; else check `lock.json` session_id matches
- `break_lock()` — calls `destroy_shadow()`

All methods return `OperationResult`. Use `multiprocessing.Lock` for all mutations. Read `OperationResult` from wherever it's defined in the codebase (check `nagios_service.py` or a shared module).

For the directory copy, use `shutil.copytree()`. Only copy `.cfg` files and preserve directory structure.

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_shadow_copy_manager.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add shadow_copy_manager.py tests/test_shadow_copy_manager.py
git commit -m "add ShadowCopyManager with lifecycle and lock management"
```

---

### Task 4: ShadowCopyManager — Undo Snapshots

Add file-level snapshot/restore for undo support.

**Files:**
- Modify: `shadow_copy_manager.py`
- Modify: `tests/test_shadow_copy_manager.py`

**Step 1: Write failing tests for snapshots**

```python
class TestUndoSnapshots:
    def test_snapshot_files_creates_copy(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        snapshot_id = scm.snapshot_files(["hosts.cfg"], "edit host")
        assert snapshot_id is not None
        assert scm.get_undo_count() == 1

    def test_undo_restores_file(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        # Read original content
        shadow_file = scm.shadow_path("hosts.cfg")
        with open(shadow_file) as f:
            original = f.read()
        # Snapshot before mutation
        scm.snapshot_files(["hosts.cfg"], "edit host")
        # Mutate
        with open(shadow_file, "w") as f:
            f.write("modified content")
        # Undo
        result = scm.undo()
        assert result.success
        with open(shadow_file) as f:
            assert f.read() == original
        assert scm.get_undo_count() == 0

    def test_multiple_undos_in_order(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        shadow_file = scm.shadow_path("hosts.cfg")
        with open(shadow_file) as f:
            v1 = f.read()
        # First edit
        scm.snapshot_files(["hosts.cfg"], "edit 1")
        with open(shadow_file, "w") as f:
            f.write("v2")
        # Second edit
        scm.snapshot_files(["hosts.cfg"], "edit 2")
        with open(shadow_file, "w") as f:
            f.write("v3")
        assert scm.get_undo_count() == 2
        # Undo second
        scm.undo()
        with open(shadow_file) as f:
            assert f.read() == "v2"
        # Undo first
        scm.undo()
        with open(shadow_file) as f:
            assert f.read() == v1

    def test_undo_when_empty_fails(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        result = scm.undo()
        assert not result.success

    def test_snapshot_multiple_files(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        scm.snapshot_files(["hosts.cfg", "subdir/services.cfg"], "bulk edit")
        assert scm.get_undo_count() == 1

    def test_snapshot_nonexistent_file_for_creation_undo(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        # Snapshot a file that doesn't exist yet (for undoing creation)
        scm.snapshot_files(["new_file.cfg"], "create file")
        # Create the file
        new_path = scm.shadow_path("new_file.cfg")
        with open(new_path, "w") as f:
            f.write("new content")
        # Undo should delete the file
        result = scm.undo()
        assert result.success
        assert not os.path.exists(new_path)
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_shadow_copy_manager.py::TestUndoSnapshots -v`
Expected: FAIL

**Step 3: Implement snapshot/undo**

Add to `ShadowCopyManager`:
- `snapshot_files(file_paths, description)` — for each relative path, copy from `<shadow_base>/config/<path>` to `<shadow_base>/snapshots/<uuid>/files/<path>`. If file doesn't exist, record it as `"absent"` in `meta.json`. Write `meta.json` with `{description, timestamp, files: [...]}`. Return snapshot UUID.
- `undo()` — read latest snapshot's `meta.json`, for each file: if was "absent", delete it from shadow config; else copy snapshot file back to shadow config. Remove snapshot directory. Return `OperationResult`.
- `get_undo_count()` — count directories in `<shadow_base>/snapshots/`.
- `shadow_path(relative_path)` — return `os.path.join(shadow_base, "config", relative_path)`.

Snapshots directory: ordered by timestamp. Use sorted directory listing to find latest for undo.

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_shadow_copy_manager.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add shadow_copy_manager.py tests/test_shadow_copy_manager.py
git commit -m "add undo snapshot support to ShadowCopyManager"
```

---

### Task 5: ShadowCopyManager — Diff Computation

Compute file-level and object-level diffs between shadow and original.

**Files:**
- Modify: `shadow_copy_manager.py`
- Modify: `tests/test_shadow_copy_manager.py`

**Step 1: Write failing tests for diff**

```python
class TestDiffComputation:
    def test_no_changes_empty_diff(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        changed = scm.get_changed_files()
        assert changed == []

    def test_modified_file_detected(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        # Modify a file in shadow
        shadow_file = scm.shadow_path("hosts.cfg")
        with open(shadow_file, "w") as f:
            f.write("modified content\n")
        changed = scm.get_changed_files()
        assert len(changed) == 1
        assert changed[0]["path"] == "hosts.cfg"
        assert changed[0]["status"] == "modified"

    def test_new_file_detected(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        # Create new file in shadow
        new_path = scm.shadow_path("new.cfg")
        with open(new_path, "w") as f:
            f.write("define host {\n    host_name new\n}\n")
        changed = scm.get_changed_files()
        assert len(changed) == 1
        assert changed[0]["path"] == "new.cfg"
        assert changed[0]["status"] == "added"

    def test_deleted_file_detected(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        # Delete file from shadow
        os.remove(scm.shadow_path("hosts.cfg"))
        changed = scm.get_changed_files()
        assert len(changed) == 1
        assert changed[0]["path"] == "hosts.cfg"
        assert changed[0]["status"] == "deleted"

    def test_get_file_diff_returns_unified_diff(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        shadow_file = scm.shadow_path("hosts.cfg")
        with open(shadow_file, "w") as f:
            f.write("define host {\n    host_name webserver1\n    alias Modified\n}\n")
        diff = scm.get_file_diff("hosts.cfg")
        assert "alias" in diff["diff_text"]

    def test_get_changed_object_count(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        # Modify shadow file
        shadow_file = scm.shadow_path("hosts.cfg")
        with open(shadow_file, "w") as f:
            f.write("define host {\n    host_name webserver1\n    alias Modified\n}\n")
        count = scm.get_changed_object_count()
        assert count >= 1
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_shadow_copy_manager.py::TestDiffComputation -v`
Expected: FAIL

**Step 3: Implement diff computation**

Add to `ShadowCopyManager`:

- `get_changed_files()` — walk both shadow config dir and original config dir. Compare files by content (not mtime). Return list of `{path, status}` where status is `added`, `modified`, or `deleted`.
- `get_file_diff(path)` — use Python's `difflib.unified_diff()` to produce a text diff between original and shadow versions of the file.
- `get_changed_object_count()` — parse both original and shadow configs using `NagiosParser`. Compare objects by stable key. Count objects that are added, modified (different attributes), or deleted.
- `original_path(relative_path)` — return `os.path.join(config_path, relative_path)`.

For `get_changed_object_count()`, import `NagiosParser` from `nagios_parser.py`. Parse both directories. Build stable key → attributes dict for each. Compare.

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_shadow_copy_manager.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add shadow_copy_manager.py tests/test_shadow_copy_manager.py
git commit -m "add diff computation to ShadowCopyManager"
```

---

### Task 6: ShadowCopyManager — Apply

All-or-nothing apply: backup, copy changed files, destroy shadow.

**Files:**
- Modify: `shadow_copy_manager.py`
- Modify: `tests/test_shadow_copy_manager.py`

**Step 1: Write failing tests for apply**

```python
class TestApply:
    def test_apply_copies_modified_files(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        # Modify shadow
        with open(scm.shadow_path("hosts.cfg"), "w") as f:
            f.write("modified\n")
        result = scm.apply()
        assert result.success
        # Original should now have modified content
        with open(os.path.join(config_dir, "hosts.cfg")) as f:
            assert f.read() == "modified\n"
        # Shadow should be destroyed
        assert not scm.has_shadow()

    def test_apply_handles_new_files(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        with open(scm.shadow_path("new.cfg"), "w") as f:
            f.write("new content\n")
        result = scm.apply()
        assert result.success
        assert os.path.exists(os.path.join(config_dir, "new.cfg"))

    def test_apply_handles_deleted_files(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        os.remove(scm.shadow_path("hosts.cfg"))
        result = scm.apply()
        assert result.success
        assert not os.path.exists(os.path.join(config_dir, "hosts.cfg"))

    def test_apply_handles_new_subdirectory(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        new_dir = os.path.join(scm.shadow_path(""), "newdir")
        os.makedirs(new_dir)
        with open(os.path.join(new_dir, "test.cfg"), "w") as f:
            f.write("content\n")
        result = scm.apply()
        assert result.success
        assert os.path.exists(os.path.join(config_dir, "newdir", "test.cfg"))

    def test_apply_with_no_changes(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        result = scm.apply()
        assert result.success
        assert not scm.has_shadow()

    def test_apply_creates_backup_when_manager_provided(self, setup_dirs):
        config_dir, shadow_base = setup_dirs
        from backup_manager import BackupManager
        backup_path = tempfile.mkdtemp()
        bm = BackupManager(config_dir, backup_path)
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")
        with open(scm.shadow_path("hosts.cfg"), "w") as f:
            f.write("modified\n")
        result = scm.apply(backup_manager=bm)
        assert result.success
        backups = bm.list_backups()
        assert len(backups.data) >= 1
        shutil.rmtree(backup_path, ignore_errors=True)
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_shadow_copy_manager.py::TestApply -v`
Expected: FAIL

**Step 3: Implement apply**

Add to `ShadowCopyManager`:

- `apply(backup_manager=None)`:
  1. Compute changed files via `get_changed_files()`
  2. If `backup_manager` provided and there are changes, call `backup_manager.create_backup("pre_shadow_apply")`
  3. For each changed file:
     - `added`: copy from shadow to original (create parent dirs if needed)
     - `modified`: copy from shadow to original (atomic: write to temp, `os.replace()`)
     - `deleted`: remove from original
  4. Handle deleted directories (empty dirs after file deletion)
  5. Handle new directories
  6. Call `destroy_shadow()`
  7. Return `OperationResult(success=True, data={changed_files: [...]})`
  8. On any error: return `OperationResult(success=False, error=str(e))` — backup can be used to restore

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_shadow_copy_manager.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add shadow_copy_manager.py tests/test_shadow_copy_manager.py
git commit -m "add all-or-nothing apply to ShadowCopyManager"
```

---

## Phase 2: Backend Integration (Tasks 7-13)

Wire the `ShadowCopyManager` into the app and rewrite routes to use it. Keep existing API endpoint shapes.

---

### Task 7: Wire ShadowCopyManager into App

Replace `StagingManager` initialization with `ShadowCopyManager`.

**Files:**
- Modify: `app.py:18,128-144` (imports and service init)
- Modify: `routes/helpers.py:74-81` (accessor functions)

**Step 1: Read current code**

Read `app.py` lines 97-170 and `routes/helpers.py` full file.

**Step 2: Modify `app.py`**

- Replace `from staging_manager import StagingManager` (line 18) with `from shadow_copy_manager import ShadowCopyManager`
- Replace `staging_manager = StagingManager(nagios_config_path)` (line 128) with `shadow_manager = ShadowCopyManager(nagios_config_path, shadow_path)` where `shadow_path` comes from `server_config`
- Replace `app.extensions["staging"] = staging_manager` with `app.extensions["shadow"] = shadow_manager`
- Keep `app.extensions["backup"]` as-is
- Handle stale shadow clear on startup (replace stale staging clear at lines 130-132)

**Step 3: Modify `routes/helpers.py`**

- Rename `get_staging_manager()` to `get_shadow_manager()`, change to `return current_app.extensions["shadow"]`
- Keep `get_backup_manager()` as-is
- Add backward-compatible alias: `get_staging_manager = get_shadow_manager` (temporary, remove in cleanup phase)

**Step 4: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: Tests that don't directly test staging internals should pass. Some staging integration tests may fail — that's expected.

**Step 5: Commit**

```bash
git add app.py routes/helpers.py
git commit -m "wire ShadowCopyManager into app factory"
```

---

### Task 8: Remove Checksums from file_operations.py

Remove the checksum system that's no longer needed.

**Files:**
- Modify: `file_operations.py:19-22,48-73,245-389`

**Step 1: Read `file_operations.py`**

Read the full file. Understand which functions have `expected_checksum` params.

**Step 2: Remove `_compute_checksum()`**

Delete the function at line 19-22.

**Step 3: Remove `expected_checksum` parameter from functions**

From `_read_file_content()` (line 48), `edit_object_in_file()` (line 245), `delete_object_from_file()` (line 288), `add_object_to_file()` (line 324):
- Remove the `expected_checksum` parameter
- Remove any checksum validation logic inside these functions
- Keep all other logic intact

**Step 4: Find and update all callers**

Search the codebase for calls to these functions that pass `expected_checksum`. Update them to not pass the parameter.

Run: `grep -rn "expected_checksum" --include="*.py" .`

**Step 5: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: PASS (or known failures from staging tests being obsolete)

**Step 6: Commit**

```bash
git add file_operations.py
# Add any caller files that were updated
git commit -m "remove checksum-based conflict detection from file operations"
```

---

### Task 9: Modify NagiosService CRUD for Shadow Copy

Point create/update/delete object methods at the shadow directory. Remove the composite action system.

**Files:**
- Modify: `nagios_service.py:40-548,824-842,875-938,1126-1662`

**Step 1: Read CRUD methods**

Read `nagios_service.py` lines 1126-1303 (create_object, update_object, delete_object).

**Step 2: Read composite action system**

Read lines 40-548 to understand what's being removed.

**Step 3: Remove composite action system**

Delete:
- `CompositeAction` dataclass (lines 40-58)
- `_build_apply_result()` (lines 130-148)
- `_resolve_on_disk_attrs()` (lines 150-175)
- `_build_composite_actions()` (lines 177-343)
- `apply_object_composite()` (lines 345-431)
- `_exec_delete()`, `_exec_edit()`, `_exec_create()` (lines 433-504)
- `_extract_raw_blocks_for_actions()` (lines 506-548)
- `_exec_moves_batched()` (lines 550-822)
- `_verify_move_ordering()` (lines 824-842)
- `_compute_expected_file_order()` (lines 875-938)
- `_log_apply_result()` (lines 1309-1323)
- All `apply_*` methods (lines 1325-1662): `apply_folder_creations`, `_create_staged_file`, `_create_new_file`, `_apply_staged_file_creations`, `_apply_new_files`, `apply_file_creations`, `_resolve_insert_position`, `_build_edit_detail`, `apply_file_moves`, `apply_folder_moves`, `apply_file_deletions`, `apply_folder_deletions`

**Step 4: Modify CRUD methods**

Modify `create_object()`, `update_object()`, `delete_object()` to:
- Accept a `config_path` parameter (defaults to the original path) so they can be pointed at the shadow directory
- Or: have the NagiosService configured with the shadow path when a shadow is active

The exact approach depends on how the parser is managed. Read how `modification_context()` works and decide:
- Option A: NagiosService gets a `set_working_path(path)` method that redirects all operations
- Option B: CRUD methods accept an explicit path parameter

**Step 5: Run existing tests**

Run: `python3 -m pytest tests/ -v`
Expected: Tests for removed code will fail/be absent. Core CRUD tests should pass.

**Step 6: Commit**

```bash
git add nagios_service.py
git commit -m "remove composite action system, prepare CRUD for shadow copy"
```

---

### Task 10: Rewrite Staging Routes

Replace the 2240-line `routes/staging.py` with a simplified version using `ShadowCopyManager`.

**Files:**
- Rewrite: `routes/staging.py`
- Create: `tests/test_shadow_staging_routes.py`

**Step 1: Write integration tests for new routes**

```python
# tests/test_shadow_staging_routes.py
# Test the simplified staging API against shadow copy
# Test: GET /api/staging returns changed files
# Test: DELETE /api/staging destroys shadow
# Test: GET /api/staging/info returns counts
# Test: POST /api/staging/apply copies files and destroys shadow
# Test: POST /api/staging/undo restores from snapshot
# Test: GET /api/staging/lock returns lock status
# Test: POST /api/staging/lock/break destroys shadow
# Test: GET /api/staging/diff returns file diffs
```

Write tests using the Flask test client (`app.test_client()`). Read `tests/conftest.py` and an existing route test file (e.g., `tests/test_docs_routes.py`) for fixture patterns.

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_shadow_staging_routes.py -v`
Expected: FAIL

**Step 3: Rewrite `routes/staging.py`**

Keep from the old file:
- `_make_relative_path()` (line 1008)
- `_run_post_apply_validation()` (line 1329)
- `_get_existing_folders()` (line 1958)

Rewrite endpoints:

```python
@bp.route('/api/staging', methods=['GET'])
def api_get_staging():
    sm = get_shadow_manager()
    if not sm.has_shadow():
        return jsonify({"success": True, "data": {"changes": [], "totalCount": 0}})
    changes = sm.get_changed_files()
    return jsonify({"success": True, "data": {"changes": changes, "totalCount": sm.get_changed_object_count()}})

@bp.route('/api/staging', methods=['DELETE'])
def api_clear_staging():
    sm = get_shadow_manager()
    result = sm.destroy_shadow()
    return jsonify({"success": result.success, "error": result.error})

@bp.route('/api/staging/info', methods=['GET'])
def api_staging_info():
    sm = get_shadow_manager()
    if not sm.has_shadow():
        return jsonify({"success": True, "data": {"totalCount": 0, "undoCount": 0, "changedFiles": 0}})
    return jsonify({"success": True, "data": {
        "totalCount": sm.get_changed_object_count(),
        "undoCount": sm.get_undo_count(),
        "changedFiles": len(sm.get_changed_files())
    }})

@bp.route('/api/staging/apply', methods=['POST'])
def api_apply_staging():
    sm = get_shadow_manager()
    bm = get_backup_manager()
    result = sm.apply(backup_manager=bm)
    if result.success:
        # Reload parser to pick up applied changes
        service = get_service()
        service._reload_parser_safe()
        # Write audit log
    return jsonify({"success": result.success, "data": result.data, "error": result.error})

@bp.route('/api/staging/undo', methods=['POST'])
def api_staging_undo():
    sm = get_shadow_manager()
    session_id = request.headers.get('X-Session-Id')
    if not sm.can_modify(session_id):
        return jsonify({"success": False, "error": "Not lock owner"}), 423
    result = sm.undo()
    return jsonify({"success": result.success, "error": result.error})

@bp.route('/api/staging/lock', methods=['GET'])
def api_staging_lock():
    sm = get_shadow_manager()
    return jsonify({"success": True, "data": sm.get_lock_status()})

@bp.route('/api/staging/lock/break', methods=['POST'])
def api_break_lock():
    sm = get_shadow_manager()
    result = sm.break_lock()
    return jsonify({"success": result.success, "error": result.error})

@bp.route('/api/staging/diff', methods=['GET'])
def api_staging_diff():
    sm = get_shadow_manager()
    if not sm.has_shadow():
        return jsonify({"success": True, "data": {"files": []}})
    files = sm.get_changed_files()
    for f in files:
        f["diff"] = sm.get_file_diff(f["path"])
    return jsonify({"success": True, "data": {"files": files}})
```

Also keep lock validation and audit logging from the existing routes — adapt them.

**Step 4: Run tests**

Run: `python3 -m pytest tests/test_shadow_staging_routes.py -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: Old staging tests will fail (expected). New tests pass.

**Step 6: Commit**

```bash
git add routes/staging.py tests/test_shadow_staging_routes.py
git commit -m "rewrite staging routes for shadow copy architecture"
```

---

### Task 11: Modify File Routes

Point file/folder operations at the shadow directory.

**Files:**
- Modify: `routes/files.py:37-476`

**Step 1: Read `routes/files.py`**

Read the full file. Understand `ensure_staging_lock()` and each file operation route.

**Step 2: Modify `ensure_staging_lock()`**

Replace staging manager lock check with shadow manager:
- Use `get_shadow_manager()` instead of `get_staging_manager()`
- Auto-create shadow on first mutation if not exists: `if not sm.has_shadow(): sm.create_shadow(session_id, ...)`
- Check `sm.can_modify(session_id)`, return 423 if not owner

**Step 3: Modify each file operation route**

For `api_create_file`, `api_create_folder`, `api_move_file`, `api_move_folder`, `api_delete_file`, `api_delete_folder`, `api_delete_path`:
- Call `sm.snapshot_files(affected_paths, description)` before mutation
- Operate on shadow directory path (`sm.shadow_path(relative_path)`) instead of original
- Remove any staging state updates (`sm.file_ops.stage_*` calls)
- Remove any undo entry creation
- Keep audit logging
- Keep path safety validation

**Step 4: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: PASS

**Step 5: Commit**

```bash
git add routes/files.py
git commit -m "point file routes at shadow copy directory"
```

---

### Task 12: Modify Git Routes

Update lock/identity references and commit flow.

**Files:**
- Modify: `routes/git.py:9,24-63,82-134,248-325,498-571`

**Step 1: Read `routes/git.py`**

Read the full file.

**Step 2: Update imports**

Replace `from staging_manager import StagingStatus` (line 9). If `StagingStatus` is still needed for restore flow, import it from wherever it was relocated.

**Step 3: Modify lock/identity functions**

- `_check_staging_lock()` (line 24): Use `get_shadow_manager().get_lock_status()`
- `_resolve_user_identity()` (line 46): Read from shadow lock state
- `api_git_identity_get()` (line 103): Read from shadow lock state
- `api_git_identity_set()` (line 137): Write to shadow lock state

**Step 4: Modify commit flow**

- `api_git_commit()` (line 248): Clear shadow on commit success
- `_execute_commit()` (line 294): Call `sm.destroy_shadow()` after successful commit
- `api_git_restore()` (line 498): Use shadow lock state

**Step 5: Run relevant tests**

Run: `python3 -m pytest tests/test_git_service.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add routes/git.py
git commit -m "update git routes for shadow copy lock management"
```

---

### Task 13: Modify Settings and Init Routes

Clean up settings routes and blueprint registration.

**Files:**
- Modify: `routes/settings.py:75-107`
- Modify: `routes/__init__.py` (no changes needed since we're keeping backups)

**Step 1: Read `routes/settings.py`**

Read the full file.

**Step 2: Modify `_update_config_path()`**

When the config path changes, the shadow manager needs to be re-initialized with the new path. Update to reinitialize `ShadowCopyManager` instead of (or in addition to) `StagingManager`.

**Step 3: Keep `_update_backup_path()`**

We're keeping the backup system, so this stays.

**Step 4: Run tests**

Run: `python3 -m pytest tests/ -v`
Expected: PASS

**Step 5: Commit**

```bash
git add routes/settings.py
git commit -m "update settings routes for shadow copy manager"
```

---

## Phase 3: Frontend Simplification (Tasks 14-20)

Remove client-side staging state. Every mutation becomes an immediate API call.

---

### Task 14: Simplify Explorer State and Data Loading

Remove staging state fields and the save/poll infrastructure.

**Files:**
- Modify: `static/js/explorer/main.js:19-106`
- Modify: `static/js/explorer/data-loading.js`
- Modify: `static/js/explorer/state-management.js`

**Step 1: Read all three files**

Read `main.js`, `data-loading.js`, `state-management.js` in full.

**Step 2: Remove staging fields from `Explorer.state` (main.js)**

Remove from state initialization (lines 29-45, 92-93):
- `pendingEdits`, `stagedMoves`, `stagedCreations`, `stagedObjectDeletions`, `stagedCreationDeletions`, `newFiles`
- `stagedFileCreations`, `stagedFileDeletions`, `stagedFileMoves`
- `stagedFolderCreations`, `stagedFolderDeletions`, `stagedFolderMoves`
- `undoStack`
- `currentStagingOwner`, `isEditingLocked`

**Step 3: Simplify `data-loading.js`**

Remove:
- `STAGING_POLL_INTERVAL_MS` (line 12-14)
- `stagingPollInterval`, `lastStagingTimestamp`, `isSavingStaging`, `saveDebounceTimer`, `saveInProgress`, `isPollingInProgress` (lines 18-24)
- `Explorer.getStagingHeaders()` (line 83)
- `Explorer.saveStaging()` (line 102)
- `Explorer.saveStagedChanges` alias (line 213)
- `syncStagingFromData()` (line 218)
- `Explorer.loadStagedChanges()` (line 251)
- `Explorer.startStagingPoll()` (line 305)
- `Explorer.stopStagingPoll()` (line 346)
- `Explorer.checkPendingExternalChanges()` (line 357)

Simplify:
- `Explorer.afterFrontendMutation()` (line 193) → just `rebuildUI()` + `updateBadges()`
- `Explorer.updateBadges()` (line 160) → keep, but simplify to only fetch from `/api/staging/info`
- `Explorer.clearStagedChanges()` (line 286) → calls `DELETE /api/staging`
- `Explorer.applyAllStaged()` (line 374) → calls `POST /api/staging/apply`
- `Explorer.undoLastAction()` (line 399) → calls `POST /api/staging/undo`
- `Explorer.checkConflicts()` (line 439) → diff-based conflict check
- `Explorer.getUndoCount()` (line 456) → server query
- `Explorer.getTotalStagedCount()` (line 464) → server query

**Step 4: Simplify `state-management.js`**

Remove:
- `Explorer.isObjectMarkedForDeletion()` (line 60)
- `Explorer.hasStagedChanges()` (line 123)
- `Explorer.resetStagingState()` (line 142)
- `Explorer.updateEditingLockedUI()` (line 213)
- `Explorer.canEdit()` (line 224)

**Step 5: Test manually**

Run: `python3 app.py` and open the explorer in a browser. Verify it loads without JS errors.

**Step 6: Commit**

```bash
git add static/js/explorer/main.js static/js/explorer/data-loading.js static/js/explorer/state-management.js
git commit -m "remove client-side staging state from explorer"
```

---

### Task 15: Migrate Object Editor to Immediate API Calls

Replace client-side staging mutations with server API calls.

**Files:**
- Modify: `static/js/explorer/object-editor.js`

**Step 1: Read `object-editor.js`**

Read the full file (1498 lines).

**Step 2: Migrate `handleFieldChange()`**

Currently mutates `pendingEdits` Map. Change to:
- Call `POST /api/objects/<stable_key>/update` (or equivalent CRUD endpoint) with the field change
- On success, call `Explorer.afterFrontendMutation()`
- Handle errors with `showNotification()`

**Step 3: Migrate creation/deletion functions**

- `stageNewObjectChanges()` → `POST /api/objects` (create object in shadow)
- `stageObjectDeletions()` → `DELETE /api/objects/<stable_key>` (delete from shadow)
- Remove `removeStagedCreation()`, `selectStagedCreationForEdit()`
- `addAttribute()` → immediate API call
- `deleteAttribute()` → immediate API call

**Step 4: Simplify rendering**

- `showCenterPaneObject()` — remove pending edit overlay logic
- `renderCenterAttributes()` — read attributes directly from parsed object (no `pendingEdits` overlay)
- `showCenterPaneNewObject()` — creation becomes API call

**Step 5: Test manually**

Open explorer, edit an object, verify changes persist across page reload.

**Step 6: Commit**

```bash
git add static/js/explorer/object-editor.js
git commit -m "migrate object editor to immediate API calls"
```

---

### Task 16: Migrate File Operations Frontend

Remove local staging state mutations from file operations.

**Files:**
- Modify: `static/js/explorer/file-operations.js`

**Step 1: Read `file-operations.js`**

Read the full file (1940 lines).

**Step 2: Remove staging state helpers**

Remove: `getFileStatus()`, `getFolderStatus()`, `hasStagedFileOperation()`, `hasStagedFolderOperation()`, `isNewFile()`, `afterStagingChange()`.

**Step 3: Simplify file/folder operations**

For `createInlineFile()`, `createInlineFolder()`, `deleteFile()`, `deleteFolder()`, `moveFile()`, `moveFolder()`, `renameFile()`, `renameFolder()`, `moveSelectedObjects()`:
- Remove `state.stagedFileCreations.push()` / `state.stagedFileDeletions.push()` etc.
- These already call API endpoints — just remove the local state mutation that follows
- Call `Explorer.afterFrontendMutation()` on success

**Step 4: Simplify tree rendering**

- `renderFileNode()`, `renderFolderNode()` — remove staging badge decorations
- `buildFileTree()` — remove staging overlays
- `renderTargetPane()` — remove staging decorations
- Add change indicator logic: fetch from server diff data to show modified/new/deleted badges

**Step 5: Test manually**

Create/move/delete files in explorer, verify operations work.

**Step 6: Commit**

```bash
git add static/js/explorer/file-operations.js
git commit -m "remove staging state from file operations frontend"
```

---

### Task 17: Migrate Context Menu, App.js, and Impact Section

Remove pending edit overlays and staging decorations from remaining explorer modules.

**Files:**
- Modify: `static/js/explorer/context-menu.js`
- Modify: `static/js/explorer/app.js`
- Modify: `static/js/explorer/impact-section.js`
- Remove: `static/js/explorer/badge-issues.js`

**Step 1: Read all files**

Read `context-menu.js`, `app.js`, `impact-section.js`, `badge-issues.js`.

**Step 2: Modify `context-menu.js`**

- Remove `getOrCreatePendingEdit()` (creates pendingEdits entries)
- Remove `canEdit()` guard from `showContextMenu()`
- Migrate bulk edit actions (`bulkEditAttribute`, `bulkDeleteAttribute`, `bulkAddToGroup`) to batch API calls
- Migrate `showBulkRenameDialog()` to API call
- Migrate `showPreview()` to show server-side diff

**Step 3: Modify `app.js`**

- Remove `getEffectiveAttributes()` pendingEdit overlay — attrs come from parsed object directly
- Remove `getEffectiveName()` pendingEdit overlay
- Remove `getStagedDisplayName()`
- `buildTree()` — remove staging decorations
- `renderTreeItem()` — remove pending-edit/deletion/move badges. Add change indicators from server diff.
- DOMContentLoaded — remove `loadStagedChanges()`, `startStagingPoll()`

**Step 4: Remove `badge-issues.js`**

Delete the file entirely. Remove its `<script>` tag from the explorer HTML template. Find and remove any calls to `computeStagedIssues()`, `updateStagedIssuesUI()`, `Explorer.stagedIssues`.

**Step 5: Modify `impact-section.js`**

Remove `overlayStagedTemplateEdits()`.

**Step 6: Test manually**

Open explorer, verify tree renders, context menus work, bulk operations work.

**Step 7: Commit**

```bash
git add static/js/explorer/context-menu.js static/js/explorer/app.js static/js/explorer/impact-section.js
git rm static/js/explorer/badge-issues.js
git commit -m "remove staging overlays from explorer tree and context menus"
```

---

### Task 18: Migrate Commit Dialog

Point commit dialog at server-side diff data.

**Files:**
- Modify: `static/js/commit-dialog.js`

**Step 1: Read `commit-dialog.js`**

Read the full file (1568 lines).

**Step 2: Remove staging-based functions**

Remove: `extractStagingArrays()`, `hasFileOperations()`, `hasGuiStagingChanges()`, `buildFileChangesFromStaging()`.

**Step 3: Migrate diff display**

- `showGlobalCommitDialog()` → fetch diff from `GET /api/staging/diff`, render file-level diffs
- `buildCommitSummaryStats()` → stats from `/api/staging/info` (totalCount, changedFiles)
- `buildGlobalCommitDialogHtml()` → render server-provided diff data

**Step 4: Migrate actions**

- `applyAndCommit()` → call `POST /api/staging/apply`, then commit. Or since shadow is the working state, just commit.
- `discardAllChanges()` → `DELETE /api/staging`
- `applyWithoutCommit()` → `POST /api/staging/apply`

**Step 5: Test manually**

Make some edits, open commit dialog, verify diff displays correctly.

**Step 6: Commit**

```bash
git add static/js/commit-dialog.js
git commit -m "migrate commit dialog to server-side diff"
```

---

### Task 19: Migrate Remaining Frontend Files

Clean up base.js, base-state.js, settings.js, git.js, tab-manager.js, analysis files, lock-manager.js.

**Files:**
- Modify: `static/js/base.js`
- Modify: `static/js/base-state.js`
- Modify: `static/js/settings.js`
- Modify: `static/js/git.js`
- Modify: `static/js/explorer/tab-manager.js`
- Modify: `static/js/explorer/analysis-issues.js`
- Modify: `static/js/explorer/analysis-suggestions.js`
- Remove: `static/js/lock-manager.js`

**Step 1: Read all files**

Read each file.

**Step 2: Modify `base.js`**

- `updateNavCommitButton()` — count source from `/api/staging/info`
- `updateUndoButton()` — undo count from server
- `handleUndoClick()` — call `POST /api/staging/undo`
- `checkPendingChanges()` — query shadow diff status
- Remove `startLockPoll()`, `actionHandlers['break-lock']`
- DOMContentLoaded — remove `checkLockStatus`, `startLockPoll`

**Step 3: Modify `base-state.js`**

Remove: `isEditingLocked`, `lockOwner`, `lockUserName`, `lockUserEmail`, `lockPollInterval` (lines 18-22, 42).

**Step 4: Modify `settings.js`**

Remove lock checks from `saveIdentity()`, `saveServerSettings()`. Remove `onLockCleared()`.

**Step 5: Modify `git.js`**

Remove `stagingInfo` state, `buildStagingPreviewHtml()`. Simplify `renderGitStatus()`.

**Step 6: Modify `tab-manager.js`**

Remove `computeStagedIssues` call from `refreshBadgesForActiveTab()`. Remove pendingEdits dot indicator from `renderTabBar()`. Simplify `openTab()` checkForChanges behavior.

**Step 7: Modify analysis files**

- `analysis-issues.js`: Replace `state.stagedCreations.push()` with API calls in `resolveGroupedError()`, `createAllMissing()`, `executeBatchCreate()`, `createObjectForIssue()`.
- `analysis-suggestions.js`: Replace staging pushes with API calls in `showCreateTemplateDialog()`, `showCreateGroupDialog()`.

**Step 8: Remove `lock-manager.js`**

Delete the file. Remove its `<script>` tag from HTML templates.

**Step 9: Test manually**

Full walkthrough: edit objects, create files, undo, check commit dialog, check git page.

**Step 10: Commit**

```bash
git add static/js/base.js static/js/base-state.js static/js/settings.js static/js/git.js
git add static/js/explorer/tab-manager.js static/js/explorer/analysis-issues.js static/js/explorer/analysis-suggestions.js
git rm static/js/lock-manager.js
git commit -m "complete frontend migration to server-authoritative model"
```

---

## Phase 4: Cleanup (Tasks 20-23)

Delete dead code, update tests, update documentation.

---

### Task 20: Delete Dead Backend Code

Remove files and code that are no longer referenced.

**Files:**
- Remove: `staging_manager.py` (after verifying no remaining imports)
- Remove: `apply_verification.py`
- Modify: `routes/__init__.py` (if any dead blueprint references)

**Step 1: Verify no remaining imports**

Search for imports of deleted modules:

```bash
grep -rn "from staging_manager import\|import staging_manager" --include="*.py" .
grep -rn "from apply_verification import\|import apply_verification" --include="*.py" .
```

Update or remove any remaining references.

**Step 2: Delete files**

```bash
git rm staging_manager.py
git rm apply_verification.py
```

**Step 3: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All active tests pass. Tests for deleted modules should already have been removed.

**Step 4: Commit**

```bash
git commit -m "remove dead staging manager and apply verification code"
```

---

### Task 21: Clean Up Tests

Remove obsolete tests, rewrite staging integration tests.

**Files:**
- Remove: `tests/test_composite_apply.py`
- Remove: `tests/test_apply_robustness.py`
- Remove: `tests/test_apply_verification.py`
- Rewrite: `tests/test_staging_integration.py`
- Modify: `tests/test_move_ordering.py`

**Step 1: Delete obsolete test files**

```bash
git rm tests/test_composite_apply.py
git rm tests/test_apply_robustness.py
git rm tests/test_apply_verification.py
```

**Step 2: Rewrite `test_staging_integration.py`**

Replace with integration tests that test the full shadow copy workflow:
1. Create shadow → make edits via API → verify diff → apply → verify original updated
2. Create shadow → make edits → undo → verify reverted
3. Create shadow → session lock prevents other sessions
4. Create shadow → break lock → shadow destroyed

Use the Flask test client. Model after the test patterns in `tests/test_shadow_copy_manager.py`.

**Step 3: Modify `test_move_ordering.py`**

Update for the new move flow — moves are direct file operations in the shadow directory, not staged operations.

**Step 4: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add tests/
git commit -m "update test suite for shadow copy architecture"
```

---

### Task 22: Update Documentation

Update all references to the old staging system.

**Files:**
- Rewrite: `.claude/STAGING_REFERENCE.md`
- Modify: `CLAUDE.md` (staging section)
- Rewrite: `templates/docs/staging-system.html`
- Rewrite: `templates/docs/data-flow-staging.html`

**Step 1: Read current docs**

Read each file.

**Step 2: Rewrite `.claude/STAGING_REFERENCE.md`**

Replace with shadow copy architecture description:
- Shadow copy lifecycle (create on first edit, destroy on apply/discard)
- Undo via file snapshots
- Diff computation
- Apply flow
- Lock management
- API endpoints

**Step 3: Update `CLAUDE.md`**

Update the "Staging System" section and the module index to reference `shadow_copy_manager.py` instead of `staging_manager.py`. Remove references to composite actions, apply phases, checksum-based conflict detection.

**Step 4: Rewrite in-app docs**

Update `templates/docs/staging-system.html` and `templates/docs/data-flow-staging.html` to explain the shadow copy system.

**Step 5: Commit**

```bash
git add .claude/STAGING_REFERENCE.md CLAUDE.md templates/docs/staging-system.html templates/docs/data-flow-staging.html
git commit -m "update documentation for shadow copy architecture"
```

---

### Task 23: Final Verification

End-to-end verification that everything works.

**Step 1: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All PASS

**Step 2: Manual smoke test**

1. Start app: `python3 app.py`
2. Open explorer, edit an object — verify shadow created
3. Edit more objects, create a file, delete a file
4. Check undo — verify file restored
5. Open commit dialog — verify diff shows correctly
6. Apply changes — verify original files updated
7. Verify shadow destroyed after apply
8. Check git page — verify status reflects changes
9. Test lock: open second browser tab, verify locked out

**Step 3: Verify line count reduction**

```bash
find . -name "*.py" -not -path "./tests/*" -not -path "./.worktrees/*" | xargs wc -l
find . -name "*.js" -path "./static/*" | xargs wc -l
```

Compare with pre-migration counts. Expect ~4500-5000 lines removed.

**Step 4: Final commit**

If any issues found, fix and commit. Tag the migration as complete:

```bash
git tag shadow-copy-migration-complete
```
