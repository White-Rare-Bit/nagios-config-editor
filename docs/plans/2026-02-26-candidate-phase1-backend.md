# Candidate Config — Phase 1: Backend Core

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create the `CandidateManager` class with full TDD — session lifecycle, object operations, undo, file/folder ops, diff, validate, apply, bulk operations.

**Architecture:** When a user starts editing, copy the running config to `.candidate/`, git init it, and modify files directly via existing `file_operations.py` functions. Each action is a git commit. Undo = `git reset --hard HEAD~1`. Apply = copy candidate over running.

**Tech Stack:** Python, pytest, existing `file_operations.py`, `nagios_parser.py`, `nagios_model.py`

**Branch:** `feature/candidate-config` (same branch used for all 4 phases)

---

## Key Codebase Facts

Before implementing, know these facts about the existing code. Getting any of these wrong will cause crashes or silent corruption:

| Fact | Detail |
|------|--------|
| **OperationResult import** | `from nagios_model import OperationResult` — there is no `operation_result` module |
| **ServerConfig paths** | `sc.paths.nagios_bin` (NOT `nagios_binary`). Also `sc.nagios_bin` top-level property |
| **REFERENCE_FIELDS structure** | `dict[str, str \| None]` mapping **field name → object type** (e.g. `"host_name": "host"`). NOT indexed by object type |
| **NagiosValidator.validate()** | Returns `ValidationResult` (not `OperationResult`). Call `.to_dict()` and wrap in OperationResult |
| **operation_response()** | On success returns `{"success": True}` + `"data"` only if `result.data is not None`. On error returns `{"error": "..."}` without `"success": false` |

---

## Prerequisites

**Step 1: Set up worktree and branch**

```bash
cd /Users/ohm/Desktop/claude/nagios-bulk-editor
git worktree add .worktrees/candidate-config -b feature/candidate-config
cp -r sample-config/ .worktrees/candidate-config/sample-config/
cd .worktrees/candidate-config
```

**Step 2: Verify clean baseline**

```bash
python3 -m pytest tests/ -v
```

Expected: all tests pass. If not, stop and investigate.

---

## Task 1: Fix immediate _exec_delete bug

Closes the proven cross-file delete bug now, before the larger migration.

**Files:**
- Modify: `nagios_service.py:438-457`
- Modify: `tests/test_apply_robustness.py`

**Step 1: Make the fix**

In `nagios_service.py`, replace the `_exec_delete` method (lines 438-457):

```python
    def _exec_delete(
        self, action: CompositeAction
    ) -> tuple[OperationResult, dict | None]:
        """Execute a delete composite action."""
        self._parser = NagiosConfigParser(self._config_path)
        self._parser.parse_all()
        target_obj = self._find_by_identity(
            action.source_file, action.object_type, action.object_name
        )
        if not target_obj:
            return OperationResult(
                False, f"Delete: object not found: {action.stable_key}"
            ), None
        result = self.delete_object(target_obj.source_file, target_obj.line_number)
        if result.success:
            detail = {
                "action": "delete",
                "object_type": action.object_type,
                "object_name": action.object_name,
                "file": target_obj.source_file,
            }
            return result, detail
        return result, None
```

**Step 2: Remove xfail markers from tests**

In `tests/test_apply_robustness.py`, remove the `@pytest.mark.xfail(...)` decorators from:
- `test_delete_from_two_files_correct_objects`
- `test_delete_from_three_files`
- `test_delete_replay_does_not_delete_wrong_object`

**Step 3: Run tests**

Run: `python3 -m pytest tests/test_apply_robustness.py -v`
Expected: 8 passed, 0 xfailed

Run: `python3 -m pytest tests/ -v`
Expected: all pass

**Step 4: Lint and commit**

```bash
ruff check nagios_service.py tests/test_apply_robustness.py
ruff format --check nagios_service.py tests/test_apply_robustness.py
git add nagios_service.py tests/test_apply_robustness.py
git commit -m "fix: use identity lookup in _exec_delete to prevent cross-file index staleness"
```

---

## Task 2: Add .candidate/ to parser and backup skip lists

**Files:**
- Modify: `nagios_parser.py:66-67`
- Modify: `backup_manager.py` (in `_collect_config_files()`)

**Step 1: Add parser skip pattern**

In `nagios_parser.py`, after line 67 (`if "/.staging/" in file_path ...`), add:

```python
            if "/.candidate/" in file_path:
                continue
```

**Step 2: Add backup exclusion**

In `backup_manager.py`, in `_collect_config_files()`, after the backup directory skip (around line 50), add:

```python
            # Skip .candidate/ and .staging/ directories (ephemeral staging data)
            rel_to_config = root_path.relative_to(self.config_path)
            if ".candidate" in rel_to_config.parts or ".staging" in rel_to_config.parts:
                dirs[:] = []
                continue
```

**Step 3: Run existing tests**

Run: `python3 -m pytest tests/ -v`
Expected: all pass (no regressions)

**Step 4: Lint and commit**

```bash
ruff check nagios_parser.py backup_manager.py
ruff format --check nagios_parser.py backup_manager.py
git add nagios_parser.py backup_manager.py
git commit -m "chore: skip .candidate/ in nagios parser and backup collection"
```

---

## Task 3: CandidateManager — session lifecycle + nagios.cfg rewrite

**Files:**
- Create: `candidate_manager.py`
- Create: `tests/test_candidate_manager.py`

**Step 1: Write failing tests for session lifecycle**

```python
"""Tests for CandidateManager."""

import os
import shutil
import tempfile

import pytest

from candidate_manager import CandidateManager


@pytest.fixture
def config_dir():
    d = tempfile.mkdtemp()
    hosts = os.path.join(d, "hosts.cfg")
    with open(hosts, "w") as f:
        f.write(
            "define host {\n"
            "    host_name    web-01\n"
            "    alias        Web Server\n"
            "    address      10.0.0.1\n"
            "}\n\n"
            "define host {\n"
            "    host_name    web-02\n"
            "    alias        Web Server 2\n"
            "    address      10.0.0.2\n"
            "}\n"
        )
    services = os.path.join(d, "services.cfg")
    with open(services, "w") as f:
        f.write(
            "define service {\n"
            "    host_name            web-01\n"
            "    service_description  HTTP\n"
            "    check_command        check_http\n"
            "}\n"
        )
    yield d
    shutil.rmtree(d)


@pytest.fixture
def cm(config_dir):
    return CandidateManager(config_dir)


class TestSessionLifecycle:
    def test_no_session_initially(self, cm):
        assert not cm.has_session()
        assert cm.get_session_info() is None

    def test_init_session_creates_candidate_dir(self, cm, config_dir):
        result = cm.init_session("sess-1", "Test User", "test@example.com")
        assert result.success
        assert cm.has_session()
        candidate_path = os.path.join(config_dir, ".candidate")
        assert os.path.isdir(candidate_path)

    def test_init_session_copies_config_files(self, cm, config_dir):
        cm.init_session("sess-1")
        candidate_path = os.path.join(config_dir, ".candidate")
        assert os.path.exists(os.path.join(candidate_path, "hosts.cfg"))
        assert os.path.exists(os.path.join(candidate_path, "services.cfg"))

    def test_init_session_creates_git_repo(self, cm, config_dir):
        cm.init_session("sess-1")
        candidate_path = os.path.join(config_dir, ".candidate")
        assert os.path.isdir(os.path.join(candidate_path, ".git"))

    def test_session_info_returns_details(self, cm):
        cm.init_session("sess-1", "Test User", "test@example.com")
        info = cm.get_session_info()
        assert info["session_id"] == "sess-1"
        assert info["user_name"] == "Test User"
        assert info["undo_count"] == 0

    def test_can_modify_with_correct_session(self, cm):
        cm.init_session("sess-1")
        assert cm.can_modify("sess-1")
        assert not cm.can_modify("sess-2")

    def test_can_modify_when_no_session(self, cm):
        assert cm.can_modify("any-session")

    def test_discard_removes_candidate_dir(self, cm, config_dir):
        cm.init_session("sess-1")
        result = cm.discard()
        assert result.success
        assert not cm.has_session()
        assert not os.path.exists(os.path.join(config_dir, ".candidate"))

    def test_double_init_fails(self, cm):
        cm.init_session("sess-1")
        result = cm.init_session("sess-2")
        assert not result.success


class TestNagiosCfgRewrite:
    @pytest.fixture
    def config_dir_with_nagios_cfg(self, tmp_path):
        """Config dir with a nagios.cfg referencing cfg_file and cfg_dir."""
        d = str(tmp_path / "nagios")
        os.makedirs(d)
        hosts = os.path.join(d, "hosts.cfg")
        with open(hosts, "w") as f:
            f.write(
                "define host {\n    host_name web-01\n    alias Web\n    address 10.0.0.1\n}\n"
            )
        sub = os.path.join(d, "conf.d")
        os.makedirs(sub)
        svc = os.path.join(sub, "services.cfg")
        with open(svc, "w") as f:
            f.write(
                "define service {\n    host_name web-01\n"
                "    service_description HTTP\n    check_command check_http\n}\n"
            )
        res = os.path.join(d, "resource.cfg")
        with open(res, "w") as f:
            f.write("$USER1$=/usr/local/nagios/libexec\n")
        cfg = os.path.join(d, "nagios.cfg")
        with open(cfg, "w") as f:
            f.write(
                f"# Nagios config\n"
                f"cfg_file={hosts}\n"
                f"cfg_dir={sub}\n"
                f"resource_file={res}\n"
                f"log_file={d}/var/nagios.log\n"
                f"object_cache_file={d}/var/objects.cache\n"
                f"status_file={d}/var/status.dat\n"
            )
        return d, cfg

    def test_cfg_file_directives_rewritten(self, config_dir_with_nagios_cfg):
        d, cfg = config_dir_with_nagios_cfg
        cm = CandidateManager(d, nagios_cfg=cfg)
        cm.init_session("sess-1")
        candidate_cfg = os.path.join(cm.candidate_path, ".validation-nagios.cfg")
        assert os.path.exists(candidate_cfg)
        content = open(candidate_cfg).read()
        assert ".candidate/" in content
        # Original paths should NOT appear
        assert f"cfg_file={d}/hosts.cfg" not in content

    def test_cfg_dir_directives_rewritten(self, config_dir_with_nagios_cfg):
        d, cfg = config_dir_with_nagios_cfg
        cm = CandidateManager(d, nagios_cfg=cfg)
        cm.init_session("sess-1")
        content = open(
            os.path.join(cm.candidate_path, ".validation-nagios.cfg")
        ).read()
        assert f"cfg_dir={d}/conf.d" not in content
        assert ".candidate/conf.d" in content

    def test_resource_file_rewritten(self, config_dir_with_nagios_cfg):
        d, cfg = config_dir_with_nagios_cfg
        cm = CandidateManager(d, nagios_cfg=cfg)
        cm.init_session("sess-1")
        content = open(
            os.path.join(cm.candidate_path, ".validation-nagios.cfg")
        ).read()
        assert ".candidate/resource.cfg" in content

    def test_var_directories_created(self, config_dir_with_nagios_cfg):
        d, cfg = config_dir_with_nagios_cfg
        cm = CandidateManager(d, nagios_cfg=cfg)
        cm.init_session("sess-1")
        var_dir = os.path.join(cm.candidate_path, "var")
        assert os.path.isdir(var_dir)

    def test_comments_pass_through(self, config_dir_with_nagios_cfg):
        d, cfg = config_dir_with_nagios_cfg
        cm = CandidateManager(d, nagios_cfg=cfg)
        cm.init_session("sess-1")
        content = open(
            os.path.join(cm.candidate_path, ".validation-nagios.cfg")
        ).read()
        assert "# Nagios config" in content


class TestBackupExclusion:
    def test_backup_excludes_candidate_dir(self, cm, config_dir):
        """Backups should not include ephemeral .candidate/ files."""
        import zipfile

        from backup_manager import BackupManager

        cm.init_session("sess-1")
        bm = BackupManager(config_dir, os.path.join(config_dir, "backups"))
        zip_path = bm.create_backup("test")
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            for name in names:
                assert ".candidate/" not in name, (
                    f"Backup should exclude .candidate/, found: {name}"
                )


class TestCopyExcludes:
    """Verify expanded copy excludes match parser skip patterns."""  # [P1-D]

    def test_bak_files_excluded(self, config_dir):
        """Backup files (.bak, .backup, .tmp) should not be copied to candidate."""
        bak = os.path.join(config_dir, "hosts.cfg.bak")
        with open(bak, "w") as f:
            f.write("old backup content")
        cm = CandidateManager(config_dir)
        cm.init_session("sess-1")
        assert not os.path.exists(os.path.join(cm.candidate_path, "hosts.cfg.bak"))

    def test_backup_dir_excluded(self, config_dir):
        """backup/ (singular) directory should be excluded like backups/."""
        backup_dir = os.path.join(config_dir, "backup")
        os.makedirs(backup_dir, exist_ok=True)
        with open(os.path.join(backup_dir, "old.cfg"), "w") as f:
            f.write("old")
        cm = CandidateManager(config_dir)
        cm.init_session("sess-1")
        assert not os.path.exists(os.path.join(cm.candidate_path, "backup"))


class TestConcurrency:
    """Verify file-based locking works across instances."""  # [P1-G]

    def test_file_lock_prevents_double_init(self, config_dir):
        """Two CandidateManager instances serialize via file lock."""
        cm1 = CandidateManager(config_dir)
        cm2 = CandidateManager(config_dir)
        r1 = cm1.init_session("sess-1")
        r2 = cm2.init_session("sess-2")
        assert r1.success
        assert not r2.success


class TestRestorePendingState:
    """Verify session state tracking for backup restores."""  # [P1-I]

    def test_session_starts_active(self, cm):
        cm.init_session("sess-1")
        assert cm.get_session_state() == "active"

    def test_set_restore_pending(self, cm):
        cm.init_session("sess-1")
        cm.set_restore_pending()
        assert cm.get_session_state() == "restore_pending"

    def test_session_info_includes_state(self, cm):
        cm.init_session("sess-1")
        info = cm.get_session_info()
        assert info["state"] == "active"
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_candidate_manager.py -v`
Expected: ImportError (candidate_manager doesn't exist yet)

**Step 3: Write implementation**

Create `candidate_manager.py`:

```python
"""Candidate config manager.

Replaces the delta-based staging system with a candidate config model.
When a user starts editing, the running config is copied to .candidate/.
Each edit modifies files directly. Git tracks undo history. Apply copies
candidate over running config.
"""

import fcntl  # [P1-G]
import hashlib
import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

from nagios_model import OperationResult

logger = logging.getLogger("nagios_bulk_editor.candidate")

# Directories to exclude at top level when copying running config to candidate  # [P1-D]
_COPY_EXCLUDES_DIRS = {
    ".candidate", ".staging", ".nagios_staging", ".git",
    "backups", "backup", "__pycache__",
}

# File patterns to exclude when copying  # [P1-D]
_COPY_EXCLUDES_EXTENSIONS = {".bak", ".backup", ".tmp"}

# Session metadata filename inside candidate directory
_SESSION_FILE = ".session.json"

# Directives in nagios.cfg that contain filesystem paths
_PATH_DIRECTIVES = (
    "cfg_file=",
    "cfg_dir=",
    "resource_file=",
    "log_file=",
    "object_cache_file=",
    "precached_object_file=",
    "status_file=",
    "state_retention_file=",
    "debug_file=",
    "command_file=",
    "lock_file=",
    "temp_file=",
    "temp_path=",
    "check_result_path=",
    "log_archive_path=",
)


class _FileLock:  # [P1-G]
    """Process-safe file lock using fcntl."""

    def __init__(self, lock_path: str):
        self._lock_path = lock_path

    def __enter__(self):
        os.makedirs(os.path.dirname(self._lock_path), exist_ok=True)
        self._fd = open(self._lock_path, "w")
        fcntl.flock(self._fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *args):
        fcntl.flock(self._fd, fcntl.LOCK_UN)
        self._fd.close()


class CandidateManager:
    """Manages a candidate config directory for staging edits.

    Lifecycle: init_session() -> [edit/delete/create/move] -> apply() or discard()
    Each edit modifies candidate files directly, then git-commits for undo.
    """

    def __init__(self, running_config_path: str, nagios_cfg: str = "", backup_manager=None):  # [P1-B]
        self._running_path = os.path.realpath(running_config_path)
        self._candidate_path = os.path.join(self._running_path, ".candidate")
        self._nagios_cfg = nagios_cfg
        self._backup_manager = backup_manager  # [P1-B]
        self._lock = _FileLock(os.path.join(self._running_path, ".candidate.lock"))  # [P1-G]

    @property
    def candidate_path(self) -> str:
        return self._candidate_path

    @property
    def running_path(self) -> str:
        return self._running_path

    # -- Session lifecycle --

    def has_session(self) -> bool:
        """True if a candidate directory exists."""
        return os.path.isdir(self._candidate_path)

    def init_session(
        self,
        session_id: str,
        user_name: str = "",
        user_email: str = "",
    ) -> OperationResult:
        """Create candidate dir, copy running config, git init + baseline commit."""
        with self._lock:
            if self.has_session():
                return OperationResult(False, "A candidate session already exists")

            try:
                self._copy_running_to_candidate()
                self._rewrite_nagios_cfg()
                self._write_session_info(session_id, user_name, user_email)
                self._git_init()
                self._git_commit("baseline")
                logger.info(
                    "Candidate session created: session_id=%s user=%s",
                    session_id,
                    user_name,
                )
                return OperationResult(
                    True, data={"candidate_path": self._candidate_path}
                )
            except Exception as e:
                # Clean up partial state
                if os.path.exists(self._candidate_path):
                    shutil.rmtree(self._candidate_path, ignore_errors=True)
                logger.exception("Failed to create candidate session: %s", e)
                return OperationResult(
                    False, f"Failed to create candidate session: {e}"
                )

    def get_session_info(self) -> dict | None:
        """Return session metadata or None if no session."""
        if not self.has_session():
            return None
        info = self._read_session_info()
        info["undo_count"] = self._get_undo_count()
        return info

    def can_modify(self, session_id: str) -> bool:
        """True if session owns the lock or no session exists."""
        if not self.has_session():
            return True
        info = self._read_session_info()
        return info.get("session_id") == session_id

    def discard(self) -> OperationResult:
        """Delete candidate directory, release lock."""
        with self._lock:
            if not self.has_session():
                return OperationResult(True)
            try:
                shutil.rmtree(self._candidate_path)
                logger.info("Candidate session discarded")
                return OperationResult(True)
            except Exception as e:
                logger.exception("Failed to discard candidate: %s", e)
                return OperationResult(False, f"Failed to discard candidate: {e}")

    # -- Session state --  # [P1-I]

    def get_session_state(self) -> str:
        """Return session state: 'active', 'restore_pending', or '' if no session."""  # [P1-I]
        if not self.has_session():
            return ""
        info = self._read_session_info()
        return info.get("state", "active")

    def set_restore_pending(self) -> OperationResult:
        """Mark session as restore-pending (backup loaded, awaiting confirmation)."""  # [P1-I]
        if not self.has_session():
            return OperationResult(False, "No candidate session active")
        info = self._read_session_info()
        info["state"] = "restore_pending"
        path = os.path.join(self._candidate_path, _SESSION_FILE)
        with open(path, "w") as f:
            json.dump(info, f)
        return OperationResult(True)

    # -- Path translation --

    def to_candidate_path(self, running_file_path: str) -> str:
        """Map a running config path to the equivalent candidate path."""
        real = os.path.realpath(running_file_path)
        rel = os.path.relpath(real, self._running_path)
        return os.path.join(self._candidate_path, rel)

    def to_running_path(self, candidate_file_path: str) -> str:
        """Map a candidate path back to running config path."""
        rel = os.path.relpath(candidate_file_path, self._candidate_path)
        return os.path.join(self._running_path, rel)

    # -- Path safety --  # [P1-A]

    def _validate_candidate_path(self, path: str) -> OperationResult:
        """Ensure path is safely within the candidate directory."""  # [P1-A]
        from file_operations import is_safe_path

        return is_safe_path(path, base_dir=self._candidate_path)

    # -- Internal helpers --

    def _copy_running_to_candidate(self):  # [P1-D]
        """Copy running config to candidate, excluding system dirs and backup files."""
        logger.debug("Copying running config to candidate: %s", self._running_path)
        os.makedirs(self._candidate_path, exist_ok=True)
        for item in os.listdir(self._running_path):
            if item in _COPY_EXCLUDES_DIRS:
                continue
            if item.startswith("."):
                continue
            src = os.path.join(self._running_path, item)
            dst = os.path.join(self._candidate_path, item)
            if os.path.isdir(src):
                shutil.copytree(
                    src, dst, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(
                        "*.bak", "*.backup", "*.tmp",
                        "backups", "backup", ".staging", ".nagios_staging",
                    ),
                )
            else:
                _, ext = os.path.splitext(item)
                if ext in _COPY_EXCLUDES_EXTENSIONS:
                    continue
                shutil.copy2(src, dst)

    def _rewrite_nagios_cfg(self):
        """Create validation-only nagios.cfg with paths pointing to candidate.

        Stored as .validation-nagios.cfg to prevent accidental copy-back
        during apply(). Only used by validate().
        """
        if not self._nagios_cfg or not os.path.exists(self._nagios_cfg):
            return

        with open(self._nagios_cfg) as f:
            lines = f.readlines()

        running_dir = os.path.dirname(os.path.realpath(self._nagios_cfg))
        rewritten = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#") or "=" not in stripped:
                rewritten.append(line)
                continue
            for directive in _PATH_DIRECTIVES:
                if stripped.startswith(directive):
                    path = stripped[len(directive) :]
                    abs_path = os.path.realpath(os.path.join(running_dir, path))
                    if abs_path.startswith(self._running_path):
                        rel = os.path.relpath(abs_path, self._running_path)
                        line = (
                            f"{directive}"
                            f"{os.path.join(self._candidate_path, rel)}\n"
                        )
                    break
            rewritten.append(line)

        # Write to validation-specific location, NOT inside candidate tree
        validation_cfg = os.path.join(
            self._candidate_path, ".validation-nagios.cfg"
        )
        with open(validation_cfg, "w") as f:
            f.writelines(rewritten)

        # Create var/ subdirectories needed by nagios -v
        for subdir in ("var", "var/rw", "var/archives", "var/checkresults"):
            os.makedirs(os.path.join(self._candidate_path, subdir), exist_ok=True)

    def _write_session_info(self, session_id, user_name, user_email):
        checksums = {}
        for root, dirs, files in os.walk(self._running_path):  # [P1-D]
            dirs[:] = [
                d for d in dirs
                if d not in _COPY_EXCLUDES_DIRS and not d.startswith(".")
            ]
            for fname in files:
                _, ext = os.path.splitext(fname)
                if ext in _COPY_EXCLUDES_EXTENSIONS:
                    continue
                fpath = os.path.join(root, fname)
                checksums[fpath] = self._file_checksum(fpath)

        info = {
            "session_id": session_id,
            "user_name": user_name,
            "user_email": user_email,
            "state": "active",  # [P1-I]
            "created_at": time.time(),
            "baseline_checksums": checksums,
        }
        path = os.path.join(self._candidate_path, _SESSION_FILE)
        with open(path, "w") as f:
            json.dump(info, f)

    def _read_session_info(self) -> dict:
        path = os.path.join(self._candidate_path, _SESSION_FILE)
        if not os.path.exists(path):
            return {}
        with open(path) as f:
            return json.load(f)

    def _git_run(self, *args) -> subprocess.CompletedProcess:
        """Run a git command in the candidate directory."""
        result = subprocess.run(
            ["git", *args],
            cwd=self._candidate_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.debug("git %s failed (rc=%d): %s", args[0], result.returncode, result.stderr.strip())
        return result

    def _git_init(self):
        self._git_run("init")
        self._git_run("config", "user.name", "CandidateManager")
        self._git_run("config", "user.email", "candidate@localhost")

    def _git_commit(self, message: str) -> OperationResult:
        self._git_run("add", "-A")
        result = self._git_run("commit", "-m", message, "--allow-empty")
        if result.returncode != 0 and "nothing to commit" not in result.stdout:
            return OperationResult(False, f"git commit failed: {result.stderr}")
        return OperationResult(True)

    def _get_undo_count(self) -> int:
        """Number of commits above baseline."""
        result = self._git_run("rev-list", "--count", "HEAD")
        if result.returncode != 0:
            return 0
        count = int(result.stdout.strip())
        return max(0, count - 1)  # subtract baseline commit

    def _get_baseline_hash(self) -> str:
        """Get the first commit hash in candidate repo (baseline)."""
        result = self._git_run("rev-list", "--max-parents=0", "HEAD")
        if result.returncode != 0:
            return ""
        return result.stdout.strip().split("\n")[0]

    @staticmethod
    def _file_checksum(file_path: str) -> str:
        return hashlib.sha256(Path(file_path).read_bytes()).hexdigest()

    @staticmethod
    def _read_file_safe(path: str) -> str:  # [P1-J]
        """Read file with UTF-8, falling back to latin-1."""
        try:
            return Path(path).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return Path(path).read_text(encoding="latin-1")
```

**Step 4: Run tests**

Run: `python3 -m pytest tests/test_candidate_manager.py -v`
Expected: all pass

**Step 5: Lint and commit**

```bash
ruff check candidate_manager.py tests/test_candidate_manager.py
ruff format --check candidate_manager.py tests/test_candidate_manager.py
git add candidate_manager.py tests/test_candidate_manager.py
git commit -m "feat: CandidateManager session lifecycle with nagios.cfg rewrite"
```

---

## Task 4: CandidateManager — object operations + reference updates

**Files:**
- Modify: `candidate_manager.py`
- Modify: `tests/test_candidate_manager.py`

**Step 1: Write failing tests for object operations**

Add to `tests/test_candidate_manager.py`:

```python
from nagios_parser import NagiosConfigParser


class TestObjectOperations:
    def test_edit_object(self, cm, config_dir):
        cm.init_session("sess-1")
        parser = NagiosConfigParser(cm.candidate_path)
        parser.parse_all()
        web01 = next(
            o for o in parser.objects if o.attributes.get("host_name") == "web-01"
        )

        result = cm.edit_object(
            web01.source_file,
            web01.line_number,
            {**web01.attributes, "alias": "Updated Web"},
            "host",
            description="Edit web-01 alias",
        )
        assert result.success

        # Verify candidate file changed
        parser2 = NagiosConfigParser(cm.candidate_path)
        parser2.parse_all()
        updated = next(
            o for o in parser2.objects if o.attributes.get("host_name") == "web-01"
        )
        assert updated.attributes["alias"] == "Updated Web"

        # Verify running config unchanged
        running_parser = NagiosConfigParser(config_dir)
        running_parser.parse_all()
        original = next(
            o
            for o in running_parser.objects
            if o.attributes.get("host_name") == "web-01"
        )
        assert original.attributes["alias"] == "Web Server"

    def test_delete_object(self, cm, config_dir):
        cm.init_session("sess-1")
        parser = NagiosConfigParser(cm.candidate_path)
        parser.parse_all()
        web02 = next(
            o for o in parser.objects if o.attributes.get("host_name") == "web-02"
        )

        result = cm.delete_object(
            web02.source_file,
            web02.line_number,
            description="Delete web-02",
        )
        assert result.success

        parser2 = NagiosConfigParser(cm.candidate_path)
        parser2.parse_all()
        names = [
            o.attributes.get("host_name")
            for o in parser2.objects
            if o.object_type == "host"
        ]
        assert "web-02" not in names
        assert "web-01" in names

    def test_create_object(self, cm, config_dir):
        cm.init_session("sess-1")
        candidate_hosts = os.path.join(config_dir, ".candidate", "hosts.cfg")

        result = cm.create_object(
            candidate_hosts,
            "host",
            {"host_name": "web-03", "alias": "Web 3", "address": "10.0.0.3"},
            description="Create web-03",
        )
        assert result.success

        parser = NagiosConfigParser(cm.candidate_path)
        parser.parse_all()
        names = [
            o.attributes.get("host_name")
            for o in parser.objects
            if o.object_type == "host"
        ]
        assert "web-03" in names

    def test_move_object(self, cm, config_dir):
        cm.init_session("sess-1")
        parser = NagiosConfigParser(cm.candidate_path)
        parser.parse_all()
        web01 = next(
            o for o in parser.objects if o.attributes.get("host_name") == "web-01"
        )
        candidate_services = os.path.join(config_dir, ".candidate", "services.cfg")

        result = cm.move_object(
            web01.source_file,
            web01.line_number,
            candidate_services,
            "host",
            dict(web01.attributes),
            description="Move web-01 to services.cfg",
        )
        assert result.success

        parser2 = NagiosConfigParser(cm.candidate_path)
        parser2.parse_all()
        web01_moved = next(
            o for o in parser2.objects if o.attributes.get("host_name") == "web-01"
        )
        assert "services.cfg" in web01_moved.source_file

    def test_edit_creates_undo_entry(self, cm, config_dir):
        cm.init_session("sess-1")
        parser = NagiosConfigParser(cm.candidate_path)
        parser.parse_all()
        web01 = next(
            o for o in parser.objects if o.attributes.get("host_name") == "web-01"
        )

        cm.edit_object(
            web01.source_file,
            web01.line_number,
            {**web01.attributes, "alias": "Changed"},
            "host",
            description="Edit alias",
        )
        assert cm.get_session_info()["undo_count"] == 1

    def test_multi_file_delete_correct_objects(self, cm, config_dir):
        """The bug that motivated this rewrite — deletes across files must
        delete the correct objects, not victims of index shift."""
        cm.init_session("sess-1")
        parser = NagiosConfigParser(cm.candidate_path)
        parser.parse_all()

        web02 = next(
            o for o in parser.objects if o.attributes.get("host_name") == "web-02"
        )
        http_svc = next(
            o
            for o in parser.objects
            if o.attributes.get("service_description") == "HTTP"
        )

        cm.delete_object(
            web02.source_file, web02.line_number, description="Delete web-02"
        )
        cm.delete_object(
            http_svc.source_file,
            http_svc.line_number,
            description="Delete HTTP service",
        )

        parser2 = NagiosConfigParser(cm.candidate_path)
        parser2.parse_all()
        remaining_hosts = [
            o.attributes.get("host_name")
            for o in parser2.objects
            if o.object_type == "host"
        ]
        remaining_svcs = [
            o.attributes.get("service_description")
            for o in parser2.objects
            if o.object_type == "service"
        ]
        assert remaining_hosts == ["web-01"]
        assert remaining_svcs == []


class TestReferenceUpdate:
    def test_edit_with_reference_update(self, cm, config_dir):
        cm.init_session("sess-1")
        parser = NagiosConfigParser(cm.candidate_path)
        parser.parse_all()
        web01 = next(
            o for o in parser.objects if o.attributes.get("host_name") == "web-01"
        )

        # Rename host from web-01 to web-server-01, with reference update
        result = cm.edit_object(
            web01.source_file,
            web01.line_number,
            {**web01.attributes, "host_name": "web-server-01"},
            "host",
            update_references=True,
        )
        assert result.success

        # Service should now reference web-server-01
        parser2 = NagiosConfigParser(cm.candidate_path)
        parser2.parse_all()
        svc = next(
            o
            for o in parser2.objects
            if o.attributes.get("service_description") == "HTTP"
        )
        assert svc.attributes["host_name"] == "web-server-01"

    def test_edit_without_reference_update(self, cm, config_dir):
        cm.init_session("sess-1")
        parser = NagiosConfigParser(cm.candidate_path)
        parser.parse_all()
        web01 = next(
            o for o in parser.objects if o.attributes.get("host_name") == "web-01"
        )

        # Rename without reference update
        cm.edit_object(
            web01.source_file,
            web01.line_number,
            {**web01.attributes, "host_name": "web-server-01"},
            "host",
            update_references=False,
        )
        parser2 = NagiosConfigParser(cm.candidate_path)
        parser2.parse_all()
        svc = next(
            o
            for o in parser2.objects
            if o.attributes.get("service_description") == "HTTP"
        )
        # Service still references old name
        assert svc.attributes["host_name"] == "web-01"


class TestPathSafety:
    """Verify path traversal is rejected in all operations."""  # [P1-A]

    def test_edit_rejects_path_traversal(self, cm, config_dir):
        cm.init_session("sess-1")
        evil_path = os.path.join(cm.candidate_path, "..", "etc", "passwd")
        result = cm.edit_object(evil_path, 1, {"host_name": "x"}, "host")
        assert not result.success
        assert "Unsafe" in result.error or "outside" in result.error.lower()

    def test_create_file_rejects_null_byte(self, cm, config_dir):
        cm.init_session("sess-1")
        result = cm.create_file(os.path.join(cm.candidate_path, "evil\x00.cfg"))
        assert not result.success

    def test_move_file_rejects_escape(self, cm, config_dir):
        cm.init_session("sess-1")
        src = os.path.join(cm.candidate_path, "hosts.cfg")
        dst = os.path.join(cm.candidate_path, "..", "stolen.cfg")
        result = cm.move_file(src, dst)
        assert not result.success

    def test_delete_folder_rejects_traversal(self, cm, config_dir):
        cm.init_session("sess-1")
        result = cm.delete_folder(os.path.join(cm.candidate_path, ".."))
        assert not result.success


class TestParserCorruptionGuard:
    """Verify that edits producing unparseable config are auto-reverted."""  # [P1-C]

    def test_edit_reverts_on_corrupt_output(self, cm, config_dir):
        """If edit_object_in_file writes unparseable content, the edit is reverted."""
        cm.init_session("sess-1")
        parser = NagiosConfigParser(cm.candidate_path)
        parser.parse_all()
        web01 = next(o for o in parser.objects if o.attributes.get("host_name") == "web-01")

        # Manually corrupt the file before the edit to simulate a bad write
        hosts_path = os.path.join(cm.candidate_path, "hosts.cfg")

        # Patch edit_object_in_file to write garbage
        import file_operations
        real_edit = file_operations.edit_object_in_file
        def corrupt_edit(*args, **kwargs):
            result = real_edit(*args, **kwargs)
            if result.success:
                with open(hosts_path, "a") as f:
                    f.write("\ndefine host {\n  UNCLOSED GARBAGE\n")
            return result
        file_operations.edit_object_in_file = corrupt_edit
        try:
            result = cm.edit_object(
                web01.source_file, web01.line_number,
                {**web01.attributes, "alias": "Bad"}, "host",
            )
            assert not result.success
            assert "reverted" in result.error.lower() or "invalid" in result.error.lower()
        finally:
            file_operations.edit_object_in_file = real_edit

        # File should be back to pre-edit state
        after = Path(hosts_path).read_text()
        assert "UNCLOSED GARBAGE" not in after
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_candidate_manager.py::TestObjectOperations -v`
Expected: AttributeError (methods don't exist yet)

**Step 3: Add object operation methods to `candidate_manager.py`**

```python
    # -- Object operations --

    def edit_object(
        self,
        file_path: str,
        line_number: int,
        new_attrs: dict,
        obj_type: str,
        inline_comments: dict | None = None,
        description: str = "",
        update_references: bool = False,
    ) -> OperationResult:
        """Edit object in candidate. Optionally update references if name changed."""
        from file_operations import edit_object_in_file
        from nagios_parser import NagiosConfigParser

        with self._lock:
            if not self.has_session():
                return OperationResult(False, "No candidate session active")

            safe = self._validate_candidate_path(file_path)  # [P1-A]
            if not safe.success:
                return OperationResult(False, f"Unsafe path: {safe.error}")

            # Detect name change for reference updates
            old_name = None
            new_name = None
            if update_references:
                old_name, new_name = self._detect_name_change(
                    file_path, line_number, obj_type, new_attrs
                )

            result = edit_object_in_file(
                file_path,
                line_number,
                new_attrs,
                obj_type,
                inline_comments=inline_comments,
            )
            if not result.success:
                return result

            if old_name and new_name and old_name != new_name:
                ref_count = self._update_references(obj_type, old_name, new_name)
                desc = description or f"Edit {obj_type} + update {ref_count} references"
            else:
                desc = description or "Edit object"

            # Verify candidate is still parseable after edit  # [P1-C]
            try:
                verify_parser = NagiosConfigParser(self._candidate_path)
                verify_parser.parse_all()
            except Exception as e:
                # Revert the edit via git
                self._git_run("checkout", "--", ".")
                logger.error("Edit produced unparseable config, reverted: %s", e)
                return OperationResult(
                    False, f"Edit reverted — produced invalid config: {e}"
                )

            self._git_commit(desc)
            logger.info("Edit object: file=%s line=%d type=%s", file_path, line_number, obj_type)
            return result

    def delete_object(
        self,
        file_path: str,
        line_number: int,
        description: str = "",
    ) -> OperationResult:
        """Delete object from candidate. Commits."""
        from file_operations import delete_object_from_file
        from nagios_parser import NagiosConfigParser

        with self._lock:
            if not self.has_session():
                return OperationResult(False, "No candidate session active")

            safe = self._validate_candidate_path(file_path)  # [P1-A]
            if not safe.success:
                return OperationResult(False, f"Unsafe path: {safe.error}")

            result = delete_object_from_file(file_path, line_number)
            if not result.success:
                return result

            # Verify candidate is still parseable after delete  # [P1-C]
            try:
                verify_parser = NagiosConfigParser(self._candidate_path)
                verify_parser.parse_all()
            except Exception as e:
                self._git_run("checkout", "--", ".")
                logger.error("Delete produced unparseable config, reverted: %s", e)
                return OperationResult(
                    False, f"Delete reverted — produced invalid config: {e}"
                )

            self._git_commit(description or "Delete object")
            logger.info("Delete object: file=%s line=%d", file_path, line_number)
            return result

    def create_object(
        self,
        file_path: str,
        obj_type: str,
        attrs: dict,
        after_line: int | None = None,
        inline_comments: dict | None = None,
        description: str = "",
    ) -> OperationResult:
        """Create object in candidate. Commits."""
        from file_operations import add_object_to_file
        from nagios_parser import NagiosConfigParser

        with self._lock:
            if not self.has_session():
                return OperationResult(False, "No candidate session active")

            safe = self._validate_candidate_path(file_path)  # [P1-A]
            if not safe.success:
                return OperationResult(False, f"Unsafe path: {safe.error}")

            result = add_object_to_file(
                file_path,
                obj_type,
                attrs,
                after_line,
                inline_comments=inline_comments,
            )
            if not result.success:
                return result

            # Verify candidate is still parseable after create  # [P1-C]
            try:
                verify_parser = NagiosConfigParser(self._candidate_path)
                verify_parser.parse_all()
            except Exception as e:
                self._git_run("checkout", "--", ".")
                logger.error("Create produced unparseable config, reverted: %s", e)
                return OperationResult(
                    False, f"Create reverted — produced invalid config: {e}"
                )

            self._git_commit(description or "Create object")
            logger.info("Create object: file=%s type=%s", file_path, obj_type)
            return result

    def move_object(
        self,
        source_file: str,
        source_line: int,
        target_file: str,
        obj_type: str,
        attrs: dict,
        insert_line: int | None = None,
        description: str = "",
    ) -> OperationResult:
        """Move object between files in candidate. Commits."""
        from file_operations import move_object_between_files
        from nagios_parser import NagiosConfigParser

        with self._lock:
            if not self.has_session():
                return OperationResult(False, "No candidate session active")

            safe = self._validate_candidate_path(source_file)  # [P1-A]
            if not safe.success:
                return OperationResult(False, f"Unsafe path: {safe.error}")
            safe = self._validate_candidate_path(target_file)  # [P1-A]
            if not safe.success:
                return OperationResult(False, f"Unsafe path: {safe.error}")

            result = move_object_between_files(
                source_file,
                source_line,
                target_file,
                obj_type,
                attrs,
                insert_line,
            )
            if not result.success:
                return result

            # Verify candidate is still parseable after move  # [P1-C]
            try:
                verify_parser = NagiosConfigParser(self._candidate_path)
                verify_parser.parse_all()
            except Exception as e:
                self._git_run("checkout", "--", ".")
                logger.error("Move produced unparseable config, reverted: %s", e)
                return OperationResult(
                    False, f"Move reverted — produced invalid config: {e}"
                )

            self._git_commit(description or "Move object")
            logger.info("Move object: %s:%d -> %s", source_file, source_line, target_file)
            return result

    # -- Reference update helpers --

    def _detect_name_change(self, file_path, line_number, obj_type, new_attrs):
        """Compare old name vs new name for the object being edited.

        Reads only the single target file (not a full re-parse) for efficiency.
        """
        from nagios_model import NAME_FIELDS
        from nagios_parser import NagiosConfigParser

        name_field = NAME_FIELDS.get(obj_type)
        if not name_field:
            return None, None
        # Parse just the file containing the object
        parser = NagiosConfigParser(self._candidate_path)
        parser.parse_file(file_path)
        obj = next(
            (
                o
                for o in parser.objects
                if o.source_file == file_path and o.line_number == line_number
            ),
            None,
        )
        if not obj:
            return None, None
        old_name = obj.attributes.get(name_field)
        new_name = new_attrs.get(name_field)
        return old_name, new_name

    def _update_references(self, obj_type, old_name, new_name):
        """Rewrite all references to old_name -> new_name across candidate files.

        REFERENCE_FIELDS maps field_name -> referenced_type (e.g. "host_name" -> "host").
        We find all fields that reference obj_type, then scan all objects for those fields.
        Edits are applied bottom-to-top within each file to prevent line number shifts.
        """
        from file_operations import edit_object_in_file
        from nagios_model import REFERENCE_FIELDS
        from nagios_parser import NagiosConfigParser

        # Find which field names reference this object type
        ref_field_names = set()
        for field_name, ref_type in REFERENCE_FIELDS.items():
            if ref_type == obj_type or ref_type is None:
                ref_field_names.add(field_name)

        parser = NagiosConfigParser(self._candidate_path)
        parser.parse_all()

        # Collect edits needed, grouped by file
        edits_by_file = {}
        for obj in parser.objects:
            new_attrs = dict(obj.attributes)
            changed = False
            for field_name in ref_field_names:
                val = new_attrs.get(field_name, "")
                if not val:
                    continue
                parts = [p.strip() for p in val.split(",")]
                if old_name in parts:
                    parts = [new_name if p == old_name else p for p in parts]
                    new_attrs[field_name] = ",".join(parts)
                    changed = True
            if changed:
                edits_by_file.setdefault(obj.source_file, []).append(
                    (obj.line_number, new_attrs, obj.object_type)
                )

        # Apply edits bottom-to-top within each file
        count = 0
        for _file_path, file_edits in edits_by_file.items():
            for line_num, attrs, o_type in sorted(
                file_edits, key=lambda e: -e[0]
            ):
                edit_object_in_file(_file_path, line_num, attrs, o_type)
                count += 1

        return count
```

**Step 4: Run tests**

Run: `python3 -m pytest tests/test_candidate_manager.py -v`
Expected: all pass

**Step 5: Lint and commit**

```bash
ruff check candidate_manager.py tests/test_candidate_manager.py
ruff format --check candidate_manager.py tests/test_candidate_manager.py
git add candidate_manager.py tests/test_candidate_manager.py
git commit -m "feat: CandidateManager object operations with optional reference update"
```

---

## Task 5: CandidateManager — undo

**Files:**
- Modify: `candidate_manager.py`
- Modify: `tests/test_candidate_manager.py`

**Step 1: Write failing tests**

```python
class TestUndo:
    def test_undo_reverts_edit(self, cm, config_dir):
        cm.init_session("sess-1")
        parser = NagiosConfigParser(cm.candidate_path)
        parser.parse_all()
        web01 = next(
            o for o in parser.objects if o.attributes.get("host_name") == "web-01"
        )

        cm.edit_object(
            web01.source_file,
            web01.line_number,
            {**web01.attributes, "alias": "Changed"},
            "host",
        )
        result = cm.undo()
        assert result.success

        parser2 = NagiosConfigParser(cm.candidate_path)
        parser2.parse_all()
        web01_after = next(
            o for o in parser2.objects if o.attributes.get("host_name") == "web-01"
        )
        assert web01_after.attributes["alias"] == "Web Server"

    def test_undo_reverts_delete(self, cm, config_dir):
        cm.init_session("sess-1")
        parser = NagiosConfigParser(cm.candidate_path)
        parser.parse_all()
        web02 = next(
            o for o in parser.objects if o.attributes.get("host_name") == "web-02"
        )

        cm.delete_object(web02.source_file, web02.line_number)
        cm.undo()

        parser2 = NagiosConfigParser(cm.candidate_path)
        parser2.parse_all()
        names = [
            o.attributes.get("host_name")
            for o in parser2.objects
            if o.object_type == "host"
        ]
        assert "web-02" in names

    def test_undo_count_decrements(self, cm, config_dir):
        cm.init_session("sess-1")
        parser = NagiosConfigParser(cm.candidate_path)
        parser.parse_all()
        web01 = next(
            o for o in parser.objects if o.attributes.get("host_name") == "web-01"
        )

        cm.edit_object(
            web01.source_file,
            web01.line_number,
            {**web01.attributes, "alias": "A"},
            "host",
        )
        cm.edit_object(
            web01.source_file,
            web01.line_number,
            {**web01.attributes, "alias": "B"},
            "host",
        )
        assert cm.get_session_info()["undo_count"] == 2

        cm.undo()
        assert cm.get_session_info()["undo_count"] == 1

        cm.undo()
        assert cm.get_session_info()["undo_count"] == 0

    def test_undo_at_baseline_fails(self, cm):
        cm.init_session("sess-1")
        result = cm.undo()
        assert not result.success

    def test_undo_returns_description(self, cm, config_dir):
        cm.init_session("sess-1")
        parser = NagiosConfigParser(cm.candidate_path)
        parser.parse_all()
        web01 = next(
            o for o in parser.objects if o.attributes.get("host_name") == "web-01"
        )

        cm.edit_object(
            web01.source_file,
            web01.line_number,
            {**web01.attributes, "alias": "X"},
            "host",
            description="Edit web-01 alias",
        )
        result = cm.undo()
        assert "Edit web-01 alias" in result.data.get("description", "")

    def test_undo_cleans_empty_dirs(self, cm, config_dir):  # [P1-K]
        """Undo of folder creation should remove the empty directory."""
        cm.init_session("sess-1")
        sub = os.path.join(cm.candidate_path, "undo-test-dir")
        cm.create_folder(sub)
        assert os.path.isdir(sub)
        cm.undo()
        assert not os.path.exists(sub)
```

**Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_candidate_manager.py::TestUndo -v`
Expected: AttributeError (undo method doesn't exist)

**Step 3: Implement**

Add to `candidate_manager.py`:

```python
    def undo(self) -> OperationResult:
        """Revert last action. Returns description of undone commit."""
        with self._lock:
            if not self.has_session():
                return OperationResult(False, "No candidate session active")
            if self._get_undo_count() == 0:
                return OperationResult(False, "Nothing to undo")

            # Get the commit message before resetting
            result = self._git_run("log", "-1", "--format=%s")
            description = result.stdout.strip() if result.returncode == 0 else ""

            reset = self._git_run("reset", "--hard", "HEAD~1")
            if reset.returncode != 0:
                return OperationResult(False, f"Undo failed: {reset.stderr}")

            # Clean up empty directories left by git reset  # [P1-K]
            for root, dirs, files in os.walk(self._candidate_path, topdown=False):
                if root == self._candidate_path:
                    continue
                if os.path.basename(root) == ".git":
                    continue
                if not os.listdir(root):
                    try:
                        os.rmdir(root)
                    except OSError:
                        pass

            logger.info("Undo: %s", description)
            return OperationResult(True, data={"description": description})
```

**Step 4: Run tests**

Run: `python3 -m pytest tests/test_candidate_manager.py -v`
Expected: all pass

**Step 5: Lint and commit**

```bash
ruff check candidate_manager.py tests/test_candidate_manager.py
ruff format --check candidate_manager.py tests/test_candidate_manager.py
git add candidate_manager.py tests/test_candidate_manager.py
git commit -m "feat: CandidateManager undo via git reset"
```

---

## Task 6: CandidateManager — file/folder operations

**Files:**
- Modify: `candidate_manager.py`
- Modify: `tests/test_candidate_manager.py`

**Step 1: Write failing tests**

```python
class TestFileOperations:
    def test_create_file(self, cm, config_dir):
        cm.init_session("sess-1")
        new_file = os.path.join(cm.candidate_path, "new.cfg")
        result = cm.create_file(new_file)
        assert result.success
        assert os.path.exists(new_file)

    def test_delete_file(self, cm, config_dir):
        cm.init_session("sess-1")
        hosts = os.path.join(cm.candidate_path, "hosts.cfg")
        result = cm.delete_file(hosts)
        assert result.success
        assert not os.path.exists(hosts)

    def test_move_file(self, cm, config_dir):
        cm.init_session("sess-1")
        src = os.path.join(cm.candidate_path, "hosts.cfg")
        dst = os.path.join(cm.candidate_path, "renamed-hosts.cfg")
        result = cm.move_file(src, dst)
        assert result.success
        assert not os.path.exists(src)
        assert os.path.exists(dst)

    def test_create_folder(self, cm, config_dir):
        cm.init_session("sess-1")
        new_dir = os.path.join(cm.candidate_path, "subdir")
        result = cm.create_folder(new_dir)
        assert result.success
        assert os.path.isdir(new_dir)

    def test_delete_folder(self, cm, config_dir):
        cm.init_session("sess-1")
        sub = os.path.join(cm.candidate_path, "subdir")
        os.makedirs(sub)
        result = cm.delete_folder(sub)
        assert result.success
        assert not os.path.exists(sub)

    def test_move_folder(self, cm, config_dir):
        cm.init_session("sess-1")
        src = os.path.join(cm.candidate_path, "subdir")
        os.makedirs(src)
        (Path(src) / "test.cfg").write_text("define host { host_name test }\n")
        dst = os.path.join(cm.candidate_path, "renamed-subdir")
        result = cm.move_folder(src, dst)
        assert result.success
        assert not os.path.exists(src)
        assert os.path.isdir(dst)

    def test_file_ops_are_undoable(self, cm, config_dir):
        cm.init_session("sess-1")
        new_file = os.path.join(cm.candidate_path, "new.cfg")
        cm.create_file(new_file)
        assert os.path.exists(new_file)
        cm.undo()
        assert not os.path.exists(new_file)
```

**Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_candidate_manager.py::TestFileOperations -v`
Expected: AttributeError (methods don't exist)

**Step 3: Implement**

Add to `candidate_manager.py`:

```python
    # -- File/folder operations --

    def create_file(self, file_path: str, description: str = "") -> OperationResult:
        with self._lock:
            if not self.has_session():
                return OperationResult(False, "No candidate session active")

            safe = self._validate_candidate_path(file_path)  # [P1-A]
            if not safe.success:
                return OperationResult(False, f"Unsafe path: {safe.error}")

            try:
                Path(file_path).touch()
                self._git_commit(
                    description or f"Create file {os.path.basename(file_path)}"
                )
                logger.info("Create file: %s", file_path)
                return OperationResult(True)
            except Exception as e:
                logger.error("Create file failed: %s — %s", file_path, e)
                return OperationResult(False, str(e))

    def delete_file(self, file_path: str, description: str = "") -> OperationResult:
        with self._lock:
            if not self.has_session():
                return OperationResult(False, "No candidate session active")

            safe = self._validate_candidate_path(file_path)  # [P1-A]
            if not safe.success:
                return OperationResult(False, f"Unsafe path: {safe.error}")

            try:
                os.remove(file_path)
                self._git_commit(
                    description or f"Delete file {os.path.basename(file_path)}"
                )
                logger.info("Delete file: %s", file_path)
                return OperationResult(True)
            except Exception as e:
                logger.error("Delete file failed: %s — %s", file_path, e)
                return OperationResult(False, str(e))

    def move_file(
        self, source: str, target: str, description: str = ""
    ) -> OperationResult:
        with self._lock:
            if not self.has_session():
                return OperationResult(False, "No candidate session active")

            safe = self._validate_candidate_path(source)  # [P1-A]
            if not safe.success:
                return OperationResult(False, f"Unsafe path: {safe.error}")
            safe = self._validate_candidate_path(target)  # [P1-A]
            if not safe.success:
                return OperationResult(False, f"Unsafe path: {safe.error}")

            try:
                shutil.move(source, target)
                self._git_commit(
                    description or f"Move file {os.path.basename(source)}"
                )
                logger.info("Move file: %s -> %s", source, target)
                return OperationResult(True)
            except Exception as e:
                logger.error("Move file failed: %s -> %s — %s", source, target, e)
                return OperationResult(False, str(e))

    def create_folder(self, path: str, description: str = "") -> OperationResult:
        with self._lock:
            if not self.has_session():
                return OperationResult(False, "No candidate session active")

            safe = self._validate_candidate_path(path)  # [P1-A]
            if not safe.success:
                return OperationResult(False, f"Unsafe path: {safe.error}")

            try:
                os.makedirs(path, exist_ok=True)
                # Git doesn't track empty dirs -- add .gitkeep
                gitkeep = os.path.join(path, ".gitkeep")
                Path(gitkeep).touch()
                self._git_commit(
                    description or f"Create folder {os.path.basename(path)}"
                )
                logger.info("Create folder: %s", path)
                return OperationResult(True)
            except Exception as e:
                logger.error("Create folder failed: %s — %s", path, e)
                return OperationResult(False, str(e))

    def delete_folder(self, path: str, description: str = "") -> OperationResult:
        with self._lock:
            if not self.has_session():
                return OperationResult(False, "No candidate session active")

            safe = self._validate_candidate_path(path)  # [P1-A]
            if not safe.success:
                return OperationResult(False, f"Unsafe path: {safe.error}")

            try:
                shutil.rmtree(path)
                self._git_commit(
                    description or f"Delete folder {os.path.basename(path)}"
                )
                logger.info("Delete folder: %s", path)
                return OperationResult(True)
            except Exception as e:
                logger.error("Delete folder failed: %s — %s", path, e)
                return OperationResult(False, str(e))

    def move_folder(
        self, source: str, target: str, description: str = ""
    ) -> OperationResult:
        with self._lock:
            if not self.has_session():
                return OperationResult(False, "No candidate session active")

            safe = self._validate_candidate_path(source)  # [P1-A]
            if not safe.success:
                return OperationResult(False, f"Unsafe path: {safe.error}")
            safe = self._validate_candidate_path(target)  # [P1-A]
            if not safe.success:
                return OperationResult(False, f"Unsafe path: {safe.error}")

            try:
                shutil.move(source, target)
                self._git_commit(
                    description or f"Move folder {os.path.basename(source)}"
                )
                logger.info("Move folder: %s -> %s", source, target)
                return OperationResult(True)
            except Exception as e:
                logger.error("Move folder failed: %s -> %s — %s", source, target, e)
                return OperationResult(False, str(e))
```

**Step 4: Run tests, lint, commit**

Run: `python3 -m pytest tests/test_candidate_manager.py -v`

```bash
ruff check candidate_manager.py tests/test_candidate_manager.py
ruff format --check candidate_manager.py tests/test_candidate_manager.py
git add candidate_manager.py tests/test_candidate_manager.py
git commit -m "feat: CandidateManager file/folder operations"
```

---

## Task 7: CandidateManager — diff, conflicts, validate, apply

**Files:**
- Modify: `candidate_manager.py`
- Modify: `tests/test_candidate_manager.py`

**Step 1: Write failing tests**

```python
class TestDiffAndApply:
    def test_get_diff_shows_changes(self, cm, config_dir):
        cm.init_session("sess-1")
        parser = NagiosConfigParser(cm.candidate_path)
        parser.parse_all()
        web01 = next(
            o for o in parser.objects if o.attributes.get("host_name") == "web-01"
        )
        cm.edit_object(
            web01.source_file,
            web01.line_number,
            {**web01.attributes, "alias": "Changed"},
            "host",
        )

        result = cm.get_diff()
        assert result.success
        assert len(result.data["changed_files"]) > 0
        assert "unified_diff" in result.data

    def test_get_diff_empty_when_no_changes(self, cm):
        cm.init_session("sess-1")
        result = cm.get_diff()
        assert result.success
        assert len(result.data["changed_files"]) == 0

    def test_get_diff_includes_undo_count(self, cm, config_dir):
        cm.init_session("sess-1")
        parser = NagiosConfigParser(cm.candidate_path)
        parser.parse_all()
        web01 = next(
            o for o in parser.objects if o.attributes.get("host_name") == "web-01"
        )
        cm.edit_object(
            web01.source_file,
            web01.line_number,
            {**web01.attributes, "alias": "Changed"},
            "host",
        )
        result = cm.get_diff()
        assert result.data["undo_count"] == 1

    def test_get_file_diff_returns_unified(self, cm, config_dir):
        cm.init_session("sess-1")
        parser = NagiosConfigParser(cm.candidate_path)
        parser.parse_all()
        web01 = next(
            o for o in parser.objects if o.attributes.get("host_name") == "web-01"
        )
        cm.edit_object(
            web01.source_file,
            web01.line_number,
            {**web01.attributes, "alias": "Changed"},
            "host",
        )
        rel_path = os.path.relpath(web01.source_file, cm.candidate_path)
        result = cm.get_file_diff(rel_path)
        assert result.success
        assert "diff" in result.data
        assert "Changed" in result.data["diff"]

    def test_detect_conflicts_none_initially(self, cm):
        cm.init_session("sess-1")
        conflicts = cm.detect_conflicts()
        assert conflicts == []

    def test_detect_conflicts_after_external_change(self, cm, config_dir):
        cm.init_session("sess-1")
        running_hosts = os.path.join(config_dir, "hosts.cfg")
        with open(running_hosts, "a") as f:
            f.write(
                "\ndefine host {\n    host_name external\n    address 1.2.3.4\n}\n"
            )
        conflicts = cm.detect_conflicts()
        assert len(conflicts) > 0
        assert any("hosts.cfg" in c["file"] for c in conflicts)

    def test_apply_copies_to_running(self, cm, config_dir):
        cm.init_session("sess-1")
        parser = NagiosConfigParser(cm.candidate_path)
        parser.parse_all()
        web01 = next(
            o for o in parser.objects if o.attributes.get("host_name") == "web-01"
        )
        cm.edit_object(
            web01.source_file,
            web01.line_number,
            {**web01.attributes, "alias": "Applied"},
            "host",
        )

        result = cm.apply()
        assert result.success

        running_parser = NagiosConfigParser(config_dir)
        running_parser.parse_all()
        web01_running = next(
            o
            for o in running_parser.objects
            if o.attributes.get("host_name") == "web-01"
        )
        assert web01_running.attributes["alias"] == "Applied"

    def test_apply_cleans_up_candidate(self, cm, config_dir):
        cm.init_session("sess-1")
        cm.apply()
        assert not cm.has_session()

    def test_apply_does_not_copy_validation_cfg(self, config_dir):
        """Rewritten nagios.cfg must NOT overwrite running nagios.cfg."""
        running_cfg = os.path.join(config_dir, "nagios.cfg")
        original_content = "cfg_file=./hosts.cfg\n"
        with open(running_cfg, "w") as f:
            f.write(original_content)
        cm_with_cfg = CandidateManager(config_dir, nagios_cfg=running_cfg)
        cm_with_cfg.init_session("sess-1")
        cm_with_cfg.apply()
        with open(running_cfg) as f:
            content = f.read()
        assert ".candidate/" not in content

    def test_apply_does_not_copy_var_dir(self, cm, config_dir):
        """var/ subdirectories created for validation should not be copied."""
        cm.init_session("sess-1")
        var_dir = os.path.join(cm.candidate_path, "var")
        os.makedirs(var_dir, exist_ok=True)
        with open(os.path.join(var_dir, "test.dat"), "w") as f:
            f.write("test")
        cm.apply()
        assert not os.path.exists(os.path.join(config_dir, "var", "test.dat"))

    def test_apply_removes_empty_dirs(self, cm, config_dir):  # [P1-E]
        """After deleting files, empty directories should be cleaned up."""
        cm.init_session("sess-1")
        # Create a subdirectory with a file in running config
        sub = os.path.join(config_dir, "subdir")
        os.makedirs(sub, exist_ok=True)
        with open(os.path.join(sub, "test.cfg"), "w") as f:
            f.write("define host {\n    host_name sub-test\n    address 1.1.1.1\n}\n")
        # Reinitialize to pick up the new file
        cm.discard()
        cm.init_session("sess-2")
        # Delete the file in candidate
        cand_sub_file = os.path.join(cm.candidate_path, "subdir", "test.cfg")
        if os.path.exists(cand_sub_file):
            os.remove(cand_sub_file)
            cm._git_commit("Delete subdir/test.cfg")
        cm.apply()
        # The empty subdir should be cleaned up in running config
        assert not os.path.exists(sub) or os.listdir(sub) == []


class TestApplyBackup:
    """Verify pre-apply backup creation."""  # [P1-B]

    def test_apply_creates_backup(self, config_dir):
        from backup_manager import BackupManager

        backup_dir = os.path.join(config_dir, "backups")
        os.makedirs(backup_dir, exist_ok=True)
        bm = BackupManager(config_dir, backup_dir)
        cm = CandidateManager(config_dir, backup_manager=bm)
        cm.init_session("sess-1")

        parser = NagiosConfigParser(cm.candidate_path)
        parser.parse_all()
        web01 = next(o for o in parser.objects if o.attributes.get("host_name") == "web-01")
        cm.edit_object(web01.source_file, web01.line_number,
                       {**web01.attributes, "alias": "Changed"}, "host")
        cm.apply()

        backups = [f for f in os.listdir(backup_dir) if f.endswith(".zip")]
        assert len(backups) >= 1
        assert any("pre_candidate_apply" in b for b in backups)


class TestValidation:
    def test_validate_returns_result(self, cm, config_dir):
        cm.init_session("sess-1")
        result = cm.validate()
        # Without a real nagios binary, expect a skip/unavailable result
        assert result.success or "not configured" in (result.error or "")
```

**Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_candidate_manager.py::TestDiffAndApply -v`
Expected: AttributeError (methods don't exist)

**Step 3: Implement**

Add to `candidate_manager.py`:

```python
    # -- Diff --

    def get_diff(self) -> OperationResult:
        """Compare candidate vs running config. Includes unified git diff."""
        if not self.has_session():
            return OperationResult(False, "No candidate session active")

        changed_files = []
        for root, dirs, files in os.walk(self._candidate_path):
            # Skip .git directory properly via os.walk dir filtering
            dirs[:] = [d for d in dirs if d != ".git" and d != "var"]
            for fname in files:
                if fname == _SESSION_FILE or fname == ".gitkeep":
                    continue
                if fname.startswith(".validation-"):
                    continue
                cand_file = os.path.join(root, fname)
                run_file = self.to_running_path(cand_file)
                rel_path = os.path.relpath(cand_file, self._candidate_path)
                if not os.path.exists(run_file):
                    changed_files.append(
                        {"file": run_file, "status": "created", "relative_path": rel_path}
                    )
                elif self._read_file_safe(cand_file) != self._read_file_safe(run_file):  # [P1-J]
                    changed_files.append(
                        {"file": run_file, "status": "modified", "relative_path": rel_path}
                    )

        # Check for deleted files (in running but not in candidate)
        for root, dirs, files in os.walk(self._running_path):
            dirs[:] = [  # [P1-E]
                d for d in dirs
                if d not in _COPY_EXCLUDES_DIRS and not d.startswith(".")
            ]
            for fname in files:
                run_file = os.path.join(root, fname)
                cand_file = self.to_candidate_path(run_file)
                if not os.path.exists(cand_file):
                    rel_path = os.path.relpath(run_file, self._running_path)
                    changed_files.append(
                        {"file": run_file, "status": "deleted", "relative_path": rel_path}
                    )

        # Get unified diff from git
        baseline = self._get_baseline_hash()
        unified_diff = ""
        if baseline:
            result = self._git_run("diff", f"{baseline}..HEAD")
            if result.returncode == 0:
                unified_diff = result.stdout

        return OperationResult(
            True,
            data={
                "hasChanges": len(changed_files) > 0,
                "changed_files": changed_files,
                "unified_diff": unified_diff,
                "undo_count": self._get_undo_count(),
                "session_info": self.get_session_info(),
            },
        )

    def get_file_diff(
        self, relative_path: str, context_lines: int = 3
    ) -> OperationResult:
        """Get unified diff for a single file from baseline to HEAD."""
        if not self.has_session():
            return OperationResult(False, "No candidate session active")
        baseline = self._get_baseline_hash()
        if not baseline:
            return OperationResult(False, "No baseline commit found")
        result = self._git_run(
            "diff", f"-U{context_lines}", f"{baseline}..HEAD", "--", relative_path
        )
        if result.returncode != 0:
            return OperationResult(False, f"git diff failed: {result.stderr}")
        return OperationResult(True, data={"diff": result.stdout})

    # -- Conflict detection --

    def detect_conflicts(self) -> list[dict]:
        """Check if running config was modified since session started."""
        if not self.has_session():
            return []
        info = self._read_session_info()
        baseline = info.get("baseline_checksums", {})
        conflicts = []
        for file_path, original_hash in baseline.items():
            if not os.path.exists(file_path):
                conflicts.append({"file": file_path, "reason": "deleted externally"})
            elif self._file_checksum(file_path) != original_hash:
                conflicts.append({"file": file_path, "reason": "modified externally"})
        return conflicts

    # -- Validate --

    def validate(self, nagios_bin: str = "") -> OperationResult:
        """Run nagios -v on candidate config for pre-apply verification.

        Uses .validation-nagios.cfg (rewritten paths) stored outside the
        candidate file tree to prevent copy-back during apply.
        """
        if not self.has_session():
            return OperationResult(False, "No candidate session active")
        candidate_cfg = os.path.join(
            self._candidate_path, ".validation-nagios.cfg"
        )
        if not os.path.exists(candidate_cfg):
            return OperationResult(
                False, "No nagios.cfg in candidate (validation unavailable)"
            )
        if not nagios_bin:
            return OperationResult(False, "Nagios binary not configured")
        try:
            from validator import NagiosValidator

            v = NagiosValidator(nagios_bin, candidate_cfg)
            vr = v.validate(skip_binary_verification=True)
            return OperationResult(True, data=vr.to_dict())
        except Exception as e:
            return OperationResult(False, f"Validation failed: {e}")

    # -- Apply --

    def apply(self) -> OperationResult:
        """Copy candidate files over running config. Removes candidate dir.

        Computes the deletion list BEFORE copying to avoid race conditions.
        Skips .git, var/, .validation-*, .session.json, .gitkeep during copy.
        """
        with self._lock:
            if not self.has_session():
                return OperationResult(False, "No candidate session active")
            try:
                # Create safety backup before modifying running config  # [P1-B]
                if self._backup_manager:
                    try:
                        self._backup_manager.create_backup("pre_candidate_apply")
                    except Exception as e:
                        logger.warning("Pre-apply backup failed: %s", e)
                        # Continue anyway — backup failure should not block apply

                # Compute deletions BEFORE modifying running config
                files_to_delete = []
                for root, dirs, files in os.walk(self._running_path):
                    dirs[:] = [  # [P1-E]
                        d for d in dirs
                        if d not in _COPY_EXCLUDES_DIRS and not d.startswith(".")
                    ]
                    for fname in files:
                        run_file = os.path.join(root, fname)
                        cand_file = self.to_candidate_path(run_file)
                        if not os.path.exists(cand_file):
                            files_to_delete.append(run_file)

                # Copy candidate files to running
                for root, dirs, files in os.walk(self._candidate_path):
                    dirs[:] = [d for d in dirs if d not in (".git", "var")]
                    for fname in files:
                        if fname == _SESSION_FILE or fname == ".gitkeep":
                            continue
                        if fname.startswith(".validation-"):
                            continue
                        src = os.path.join(root, fname)
                        dst = self.to_running_path(src)
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        shutil.copy2(src, dst)

                # Remove running files that were deleted in candidate
                for run_file in files_to_delete:
                    if os.path.exists(run_file):
                        os.remove(run_file)

                # Remove empty directories left after file deletions  # [P1-E]
                for root, dirs, files in os.walk(self._running_path, topdown=False):
                    if root == self._running_path:
                        continue
                    rel = os.path.relpath(root, self._running_path)
                    if rel.split(os.sep)[0] in _COPY_EXCLUDES_DIRS:
                        continue
                    # Only remove if empty after our deletions
                    if not os.listdir(root):
                        try:
                            os.rmdir(root)
                        except OSError:
                            pass

                # Clean up candidate
                shutil.rmtree(self._candidate_path)
                logger.info("Candidate applied to running config")
                return OperationResult(True)
            except Exception as e:
                logger.exception("Failed to apply candidate: %s", e)
                return OperationResult(False, f"Apply failed: {e}")
```

**Step 4: Run tests, lint, commit**

Run: `python3 -m pytest tests/test_candidate_manager.py -v`

```bash
ruff check candidate_manager.py tests/test_candidate_manager.py
ruff format --check candidate_manager.py tests/test_candidate_manager.py
git add candidate_manager.py tests/test_candidate_manager.py
git commit -m "feat: CandidateManager diff, conflicts, validate, and apply"
```

---

## Task 8: CandidateManager — bulk operations

**Files:**
- Modify: `candidate_manager.py`
- Modify: `tests/test_candidate_manager.py`

**Step 1: Write failing tests**

```python
class TestBulkOperations:
    def test_bulk_edit(self, cm, config_dir):
        cm.init_session("sess-1")
        parser = NagiosConfigParser(cm.candidate_path)
        parser.parse_all()
        hosts = [o for o in parser.objects if o.object_type == "host"]
        edits = [
            {
                "file_path": h.source_file,
                "line_number": h.line_number,
                "new_attrs": {
                    **h.attributes,
                    "alias": f"Bulk {h.attributes.get('host_name', '')}",
                },
                "obj_type": "host",
            }
            for h in hosts
        ]
        result = cm.bulk_edit(edits, description="Bulk alias update")
        assert result.success
        assert result.data["count"] == len(hosts)
        # Only 1 git commit for the whole batch
        assert cm.get_session_info()["undo_count"] == 1

    def test_bulk_edit_two_objects_same_file(self, cm, config_dir):
        """Bulk editing multiple objects in the same file must not corrupt."""
        cm.init_session("sess-1")
        parser = NagiosConfigParser(cm.candidate_path)
        parser.parse_all()
        hosts = [o for o in parser.objects if o.object_type == "host"]
        assert len(hosts) >= 2
        assert hosts[0].source_file == hosts[1].source_file

        edits = [
            {
                "file_path": h.source_file,
                "line_number": h.line_number,
                "new_attrs": {
                    **h.attributes,
                    "alias": f"Bulk-{h.attributes['host_name']}",
                },
                "obj_type": "host",
            }
            for h in hosts
        ]
        result = cm.bulk_edit(edits)
        assert result.success

        parser2 = NagiosConfigParser(cm.candidate_path)
        parser2.parse_all()
        for h in parser2.objects:
            if h.object_type == "host":
                assert h.attributes["alias"].startswith("Bulk-"), (
                    f"Expected 'Bulk-' prefix, got: {h.attributes['alias']}"
                )

    def test_bulk_move(self, cm, config_dir):
        cm.init_session("sess-1")
        new_file = os.path.join(cm.candidate_path, "bulk-target.cfg")
        Path(new_file).touch()
        cm._git_commit("Create target file")

        parser = NagiosConfigParser(cm.candidate_path)
        parser.parse_all()
        hosts = [o for o in parser.objects if o.object_type == "host"]
        moves = [
            {
                "source_file": h.source_file,
                "source_line": h.line_number,
                "target_file": new_file,
                "obj_type": "host",
                "attrs": dict(h.attributes),
            }
            for h in hosts
        ]
        result = cm.bulk_move(moves, description="Bulk move to target")
        assert result.success

        parser2 = NagiosConfigParser(cm.candidate_path)
        parser2.parse_all()
        target_hosts = [
            o for o in parser2.objects if "bulk-target.cfg" in o.source_file
        ]
        assert len(target_hosts) == len(hosts)

    def test_bulk_delete(self, cm, config_dir):
        cm.init_session("sess-1")
        parser = NagiosConfigParser(cm.candidate_path)
        parser.parse_all()
        web01 = next(
            o for o in parser.objects if o.attributes.get("host_name") == "web-01"
        )
        web02 = next(
            o for o in parser.objects if o.attributes.get("host_name") == "web-02"
        )
        http_svc = next(
            o
            for o in parser.objects
            if o.attributes.get("service_description") == "HTTP"
        )

        deletes = [
            {"file_path": web02.source_file, "line_number": web02.line_number},
            {"file_path": http_svc.source_file, "line_number": http_svc.line_number},
        ]
        result = cm.bulk_delete(deletes, description="Delete web-02 and HTTP")
        assert result.success
        assert result.data["count"] == 2
        # Only 1 git commit for the batch
        assert cm.get_session_info()["undo_count"] == 1

        parser2 = NagiosConfigParser(cm.candidate_path)
        parser2.parse_all()
        remaining = [o.attributes.get("host_name") for o in parser2.objects if o.object_type == "host"]
        assert remaining == ["web-01"]
        svcs = [o for o in parser2.objects if o.object_type == "service"]
        assert svcs == []

    def test_bulk_delete_same_file(self, cm, config_dir):
        """Delete two hosts from the same file — line numbers must not collide."""
        cm.init_session("sess-1")
        parser = NagiosConfigParser(cm.candidate_path)
        parser.parse_all()
        hosts = [o for o in parser.objects if o.object_type == "host"]
        assert len(hosts) == 2
        assert hosts[0].source_file == hosts[1].source_file  # Both in hosts.cfg

        deletes = [
            {"file_path": h.source_file, "line_number": h.line_number}
            for h in hosts
        ]
        result = cm.bulk_delete(deletes)
        assert result.success

        parser2 = NagiosConfigParser(cm.candidate_path)
        parser2.parse_all()
        remaining_hosts = [o for o in parser2.objects if o.object_type == "host"]
        assert remaining_hosts == []


class TestBulkMoveInsertLine:
    """Verify bulk moves to same target don't corrupt positions."""  # [P1-H]

    def test_bulk_move_two_objects_to_same_target(self, cm, config_dir):
        """Moving two objects to the same target file should not corrupt positions."""
        cm.init_session("sess-1")
        # Create a target file with existing content
        target = os.path.join(cm.candidate_path, "target.cfg")
        with open(target, "w") as f:
            f.write("define host {\n    host_name existing\n    address 1.1.1.1\n}\n")
        cm._git_commit("add target")

        parser = NagiosConfigParser(cm.candidate_path)
        parser.parse_all()
        web01 = next(o for o in parser.objects if o.attributes.get("host_name") == "web-01")
        web02 = next(o for o in parser.objects if o.attributes.get("host_name") == "web-02")

        result = cm.bulk_move([
            {"source_file": web01.source_file, "source_line": web01.line_number,
             "target_file": target, "obj_type": "host", "attrs": dict(web01.attributes)},
            {"source_file": web02.source_file, "source_line": web02.line_number,
             "target_file": target, "obj_type": "host", "attrs": dict(web02.attributes)},
        ])
        assert result.success

        parser2 = NagiosConfigParser(cm.candidate_path)
        parser2.parse_all()
        target_hosts = [o for o in parser2.objects if "target.cfg" in o.source_file]
        assert len(target_hosts) == 3  # existing + web-01 + web-02
```

**Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_candidate_manager.py::TestBulkOperations -v`
Expected: AttributeError (methods don't exist)

**Step 3: Implement**

Add to `candidate_manager.py`:

```python
    # -- Bulk operations --

    def bulk_edit(
        self,
        edits: list[dict],
        description: str = "",
    ) -> OperationResult:
        """Apply multiple edits as a single git commit.

        Each entry: {file_path, line_number, new_attrs, obj_type, inline_comments}

        Edits are sorted by file path, then by line_number DESCENDING within
        each file. Editing bottom-to-top prevents line number shifts from
        affecting subsequent edits in the same file.
        """
        from file_operations import edit_object_in_file

        with self._lock:
            if not self.has_session():
                return OperationResult(False, "No candidate session active")

            sorted_edits = sorted(
                edits,
                key=lambda e: (e["file_path"], -e["line_number"]),
            )

            results = []
            for edit in sorted_edits:
                result = edit_object_in_file(
                    edit["file_path"],
                    edit["line_number"],
                    edit["new_attrs"],
                    edit["obj_type"],
                    inline_comments=edit.get("inline_comments"),
                )
                if not result.success:
                    return result  # Fail fast
                results.append(result)
            self._git_commit(description or f"Bulk edit ({len(edits)} objects)")
            logger.info("Bulk edit: %d objects", len(results))
            return OperationResult(True, data={"count": len(results)})

    def bulk_move(
        self,
        moves: list[dict],
        description: str = "",
    ) -> OperationResult:
        """Apply multiple moves as a single git commit.

        Each entry: {source_file, source_line, target_file, obj_type, attrs}

        Moves sorted by source line descending within each file to prevent
        line number shifts. Explicit insert_line is ignored in bulk moves
        to avoid stale positions when multiple moves target the same file.
        """
        from file_operations import move_object_between_files

        with self._lock:
            if not self.has_session():
                return OperationResult(False, "No candidate session active")

            sorted_moves = sorted(
                moves,
                key=lambda m: (m["source_file"], -m["source_line"]),
            )

            results = []
            for move in sorted_moves:
                result = move_object_between_files(
                    move["source_file"],
                    move["source_line"],
                    move["target_file"],
                    move["obj_type"],
                    move["attrs"],
                    None,  # Always append — explicit insert_line is unreliable in bulk  # [P1-H]
                )
                if not result.success:
                    return result
                results.append(result)
            self._git_commit(description or f"Bulk move ({len(moves)} objects)")
            logger.info("Bulk move: %d objects", len(results))
            return OperationResult(True, data={"count": len(results)})

    def bulk_delete(
        self,
        deletes: list[dict],
        description: str = "",
    ) -> OperationResult:
        """Delete multiple objects as a single git commit.

        Each entry: {file_path, line_number}

        Sorted by file path, then by line_number DESCENDING within each file
        so bottom-to-top deletion prevents line number shifts.
        """
        from file_operations import delete_object_from_file

        with self._lock:
            if not self.has_session():
                return OperationResult(False, "No candidate session active")

            sorted_deletes = sorted(
                deletes,
                key=lambda d: (d["file_path"], -d["line_number"]),
            )

            count = 0
            for delete in sorted_deletes:
                result = delete_object_from_file(
                    delete["file_path"],
                    delete["line_number"],
                )
                if not result.success:
                    return result
                count += 1
            self._git_commit(description or f"Bulk delete ({count} objects)")
            logger.info("Bulk delete: %d objects", count)
            return OperationResult(True, data={"count": count})
```

**Step 4: Run tests, lint, commit**

Run: `python3 -m pytest tests/test_candidate_manager.py -v`

```bash
ruff check candidate_manager.py tests/test_candidate_manager.py
ruff format --check candidate_manager.py tests/test_candidate_manager.py
git add candidate_manager.py tests/test_candidate_manager.py
git commit -m "feat: CandidateManager bulk edit, bulk move, and bulk delete with bottom-to-top ordering"
```

---

## Phase Gate: Verification

Before considering Phase 1 complete, ALL of these must pass:

**Step 1: Full test suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all tests pass (existing + new candidate_manager tests)

**Step 2: Python lint — all modified/created files**

```bash
ruff check candidate_manager.py nagios_service.py nagios_parser.py backup_manager.py tests/test_candidate_manager.py tests/test_apply_robustness.py
ruff format --check candidate_manager.py nagios_service.py nagios_parser.py backup_manager.py tests/test_candidate_manager.py tests/test_apply_robustness.py
```

Expected: 0 errors

**Step 3: Verify no regressions in existing functionality**

```bash
python3 -m pytest tests/test_staging_integration.py tests/test_composite_apply.py -v
```

Expected: all pass (old staging system untouched, still works)

**Step 4: Report**

Report: X tests passed, 0 lint errors, Phase 1 complete. Ready for Phase 2 (App Wiring + Routes).
