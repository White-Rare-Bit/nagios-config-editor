# L01: candidate_manager.py — CREATE

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Layer:** 1 — Backend Core
**Action:** CREATE
**Path:** `candidate_manager.py`
**Dependencies:** None (first file in the project)
**Goal:** Create the CandidateManager class that replaces the delta-based staging system with a file-copy approach.

---

## Architecture

When a user starts editing, the running Nagios config is copied to a `.candidate/` directory, a git repo is initialized inside it, and all edits modify files directly in that copy. Each action becomes a git commit, undo is `git reset --hard HEAD~1`, and "Apply" copies the candidate back over the running config.

## Module Structure

```
candidate_manager.py
├── _FileLock           — Process-safe file lock using fcntl
├── CandidateManager    — Main class
│   ├── Session lifecycle: init_session, has_session, get_session_info, can_modify, discard
│   ├── Session state: get_session_state, set_restore_pending
│   ├── Path translation: to_candidate_path, to_running_path
│   ├── Object operations: edit_object, delete_object, create_object, move_object
│   ├── Reference analysis: analyze_references, _update_references
│   ├── Undo: undo
│   ├── File/folder ops: create_file, delete_file, move_file, create_folder, delete_folder, move_folder
│   ├── Diff: get_diff, get_file_diff, get_structured_diff
│   ├── Conflicts: detect_conflicts
│   ├── Validation: validate
│   ├── Apply: apply
│   └── Bulk: bulk_edit, bulk_move, bulk_delete
└── Constants: _COPY_EXCLUDES_DIRS, _COPY_EXCLUDES_EXTENSIONS, _PATH_DIRECTIVES, _SESSION_FILE
```

## Audit Logging (Commandment 3)

Every public method that mutates state MUST call `log_audit()` with an appropriate action string. The following actions are logged:

| Method | Audit Action |
|--------|-------------|
| `init_session()` | `candidate_init` |
| `discard()` | `candidate_discard` |
| `apply()` | `candidate_apply` |
| `edit_object()` | `candidate_edit` |
| `delete_object()` | `candidate_delete` |
| `create_object()` | `candidate_create` |
| `move_object()` | `candidate_move` |
| `undo()` | `candidate_undo` |
| `create_file()` | `candidate_create_file` |
| `delete_file()` | `candidate_delete_file` |
| `move_file()` | `candidate_move_file` |
| `create_folder()` | `candidate_create_folder` |
| `delete_folder()` | `candidate_delete_folder` |
| `move_folder()` | `candidate_move_folder` |
| `bulk_edit()` | `candidate_bulk_edit` |
| `bulk_move()` | `candidate_bulk_move` |
| `bulk_delete()` | `candidate_bulk_delete` |

All audit calls include at minimum: action, session_id (when available), and a details dict with relevant context (file paths, object types, counts, etc.). Both `log_audit()` and `logger.info()`/`logger.error()` are used — audit for the structured log, logger for the application log.

## Error Handling (Commandment 4)

Every public method follows this error handling pattern:

1. Wrap the entire method body in `try/except Exception`
2. On exception: `logger.exception("descriptive message")`, return `OperationResult(False, "user-facing error message")`
3. Never swallow exceptions silently — every except block either logs+returns or re-raises
4. Path validation failures return `OperationResult(False, "Path validation failed: ...")` before any I/O
5. Missing session returns `OperationResult(False, "No active candidate session")` before any work

## Imports

```python
import fcntl
import hashlib
import json
import logging
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from audit_service import log_audit
from file_operations import (
    add_object_to_file,
    delete_object_from_file,
    edit_object_in_file,
    is_safe_path,
    move_object_between_files,
)
from nagios_model import NAME_FIELDS, REFERENCE_FIELDS, OperationResult
from nagios_parser import NagiosConfigParser

logger = logging.getLogger(__name__)
```

## Constants

```python
_COPY_EXCLUDES_DIRS = {".candidate", ".staging", ".nagios_staging", ".git", "backups", "backup", "__pycache__"}
_COPY_EXCLUDES_EXTENSIONS = {".bak", ".backup", ".tmp"}
_SESSION_FILE = ".session.json"

_PATH_DIRECTIVES = (
    "cfg_file=", "cfg_dir=", "resource_file=",
    "log_file=", "object_cache_file=", "precached_object_file=",
    "status_file=", "state_retention_file=", "debug_file=",
    "command_file=", "lock_file=", "temp_file=",
    "temp_path=", "check_result_path=", "log_archive_path=",
)
```

## Class: _FileLock

Context manager using `fcntl.flock` for process-safe file locking.

```python
class _FileLock:
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
```

Lock file path: `<running_config_path>/.candidate.lock`

## Class: CandidateManager

### Constructor

```python
def __init__(self, running_config_path: str, nagios_cfg: str = "", backup_manager=None):
```

- `running_config_path`: Absolute path to running Nagios config directory. Resolve via `os.path.realpath()`.
- `nagios_cfg`: Optional path to nagios.cfg file (for validation rewrite).
- `backup_manager`: Optional BackupManager instance for pre-apply backups.
- Sets `self._candidate_path = os.path.join(self._running_path, ".candidate")`
- Creates `_FileLock` at `<running_path>/.candidate.lock`

### Properties

- `candidate_path -> str`: Returns `self._candidate_path`
- `running_path -> str`: Returns `self._running_path`

### Session Lifecycle

**`has_session() -> bool`**: Returns `os.path.isdir(self._candidate_path)`

**`init_session(session_id: str, user_name: str = "", user_email: str = "") -> OperationResult`**:
1. Acquire `_FileLock`
2. If session already exists, return `OperationResult(False, "A candidate session already exists")`
3. Call `_copy_running_to_candidate()`
4. Call `_rewrite_nagios_cfg()` (if `nagios_cfg` is set)
5. Call `_write_session_info(session_id, user_name, user_email)`
6. Call `_git_init()` then `_git_commit("baseline")`
7. On success: return `OperationResult(True, data={"candidate_path": self._candidate_path})`
8. On exception: `shutil.rmtree(self._candidate_path, ignore_errors=True)`, return failure

**`get_session_info() -> dict | None`**:
- Return `None` if no session
- Read `.session.json`, append `undo_count` from `_get_undo_count()`
- Return dict with: session_id, user_name, user_email, state, created_at, baseline_checksums, undo_count

**`can_modify(session_id: str) -> bool`**:
- Return `True` if no session (allows first editor)
- Return `True` if session_id matches stored session
- Return `False` otherwise

**`discard() -> OperationResult`**:
- Acquire lock. If no session, return success.
- `shutil.rmtree(self._candidate_path)`, return success.

### Session State

**`get_session_state() -> str`**: Return `""` if no session, else `info.get("state", "active")`.

**`set_restore_pending() -> OperationResult`**: Write `"state": "restore_pending"` to `.session.json`.

### Path Translation

**`to_candidate_path(running_file_path: str) -> str`**:
- `rel = os.path.relpath(os.path.realpath(running_file_path), self._running_path)`
- Return `os.path.join(self._candidate_path, rel)`

**`to_running_path(candidate_file_path: str) -> str`**:
- `rel = os.path.relpath(candidate_file_path, self._candidate_path)`
- Return `os.path.join(self._running_path, rel)`

### Path Safety

**`_validate_candidate_path(path: str) -> OperationResult`**:
- Delegates to `is_safe_path(path, base_dir=self._candidate_path)`

### Object Operations

All follow this pattern:
1. Acquire lock
2. Check session exists (return error if not)
3. Validate path safety via `_validate_candidate_path()`
4. Perform the operation via `file_operations.*`
5. Post-operation parse verification: re-parse candidate via `NagiosConfigParser(self._candidate_path).parse_all()`. If it raises, revert via `self._git_run("checkout", "--", ".")` and return error containing "reverted".
6. Git commit with description
7. Return OperationResult

**`edit_object(file_path, line_number, new_attrs, obj_type, inline_comments=None, description="")`**:
- Delegate to `edit_object_in_file(file_path, line_number, new_attrs, obj_type, inline_comments=inline_comments)`
- Note: do NOT pass `expected_checksum` — candidate files are our own copies
- Note: references are NOT updated at edit time. Reference updates are deferred to apply time (see `apply()` and `analyze_references()`).

**`delete_object(file_path, line_number, description="")`**:
- Delegate to `delete_object_from_file(file_path, line_number)`

**`create_object(file_path, obj_type, attrs, after_line=None, inline_comments=None, description="")`**:
- Delegate to `add_object_to_file(file_path, obj_type, attrs, after_line, inline_comments=inline_comments)`

**`move_object(source_file, source_line, target_file, obj_type, attrs, insert_line=None, description="")`**:
- Validate both source and target paths
- Delegate to `move_object_between_files(source_file, source_line, target_file, obj_type, attrs, insert_line)`

### Reference Analysis & Update

References are deferred: edits never update cross-references automatically. Instead, the user previews reference impacts at commit time and opts in before apply.

**`analyze_references() -> OperationResult`**:
1. Get baseline hash via `_get_baseline_hash()`
2. Parse objects at baseline: `git show <baseline>:<file>` for each .cfg file, parse with `NagiosConfigParser`
3. Parse objects at HEAD (current candidate state)
4. Diff to find name changes: for each object type, match by `(source_file, line_number)` or `(object_type, name)` to pair baseline ↔ HEAD objects. Detect where `NAME_FIELDS[obj_type]` changed.
5. For each name change, scan all HEAD objects for reference fields containing `old_name` (using `REFERENCE_FIELDS`)
6. Return `OperationResult(True, data={"nameChanges": [...], "totalReferences": N})`
   - Each nameChange: `{objectType, oldName, newName, referenceCount, references: [{objectType, objectName, field, sourceFile, oldValue, newValue}]}`

**`_update_references(obj_type, old_name, new_name) -> int`** (internal helper, called during apply):
- Use `REFERENCE_FIELDS` to find all fields that reference `obj_type`
- Parse all candidate files
- For each object, check if any reference field contains `old_name` in its comma-separated value list
- Collect edits grouped by file, apply bottom-to-top (sorted by line number descending) within each file
- Use `edit_object_in_file()` for each edit
- Return count of objects updated

### Undo

**`undo() -> OperationResult`**:
1. Acquire lock, check session, check `_get_undo_count() > 0`
2. Get commit message: `git log -1 --format=%s`
3. Execute `git reset --hard HEAD~1`
4. Clean empty directories: walk candidate bottom-up, skip `.git`, remove empty dirs except candidate root
5. Return `OperationResult(True, data={"description": commit_message})`

### File/Folder Operations

All follow the same pattern as object operations (lock, session check, path validation, operation, commit).

| Method | Implementation |
|--------|---------------|
| `create_file(file_path, description="")` | `Path(file_path).touch()` |
| `delete_file(file_path, description="")` | `os.remove(file_path)` |
| `move_file(source, target, description="")` | Validate both paths. `shutil.move(source, target)` |
| `create_folder(path, description="")` | `os.makedirs(path, exist_ok=True)` + write `.gitkeep` inside |
| `delete_folder(path, description="")` | `shutil.rmtree(path)` |
| `move_folder(source, target, description="")` | Validate both paths. `shutil.move(source, target)` |

### Diff

**`get_diff() -> OperationResult`**:
1. Walk candidate tree (skip `.git`, `var/`, `_SESSION_FILE`, `.gitkeep`, `.validation-*`)
2. Compare each candidate file against running equivalent:
   - No running file → status="created"
   - Content differs (via `_read_file_safe`) → status="modified"
3. Walk running tree (skip `_COPY_EXCLUDES_DIRS` and dotfiles):
   - No candidate equivalent → status="deleted"
4. Get unified diff: `git diff <baseline_hash>..HEAD`
5. Return `OperationResult(True, data={"hasChanges": bool, "changed_files": list, "unified_diff": str, "undo_count": int, "session_info": dict})`

**`get_file_diff(relative_path, context_lines=3) -> OperationResult`**:
- `git diff -U<context_lines> <baseline>..HEAD -- <relative_path>`
- Return `OperationResult(True, data={"diff": str})`

**`get_structured_diff() -> OperationResult`**:
Per-object structured diff for the commit dialog. Expensive (two full parses) but only called once when dialog opens.
1. Get baseline hash via `_get_baseline_hash()`
2. Parse objects at baseline: for each .cfg file in `git ls-tree --name-only -r <baseline>`, run `git show <baseline>:<file>`, parse with `NagiosConfigParser`
3. Parse objects at HEAD: `NagiosConfigParser(self._candidate_path).parse_all()`
4. Build stable key for each object: `(relative_path, object_type, name)`
5. Match baseline ↔ HEAD objects by stable key
6. Classify: additions (HEAD only), removals (baseline only), modifications (both, attrs differ)
7. For modifications, compute field-level diffs
8. Detect file/folder operations by comparing directory structures
9. Return `OperationResult(True, data={"files": [...], "counts": {...}, "file_operations": {...}})`
   - See L03-routes-candidate.md "Structured Diff Endpoint" for the full response schema

### Conflict Detection

**`detect_conflicts() -> list[dict]`**:
- Read `baseline_checksums` from `.session.json`
- For each file in baseline: if deleted from running → `{"file": ..., "reason": "deleted externally"}`; if checksum differs → `{"file": ..., "reason": "modified externally"}`
- Return empty list if no session

### Validation

**`validate(nagios_bin="") -> OperationResult`**:
- Check for `.validation-nagios.cfg` in candidate
- If no nagios binary: return `OperationResult(False, "Nagios binary not configured")`
- Import and use `NagiosValidator` from `validator.py`
- Return validation result wrapped in OperationResult

### Apply

**`apply(update_references=False) -> OperationResult`**:
1. Acquire lock, check session
2. If `update_references=True`: call `analyze_references()` to find name changes, then call `_update_references()` for each, then `_git_commit("update references")`. This modifies candidate files in-place before copying to running.
3. Create backup via `backup_manager.create_backup("pre_candidate_apply")` if available. Failure logs warning but does NOT block apply.
4. Compute deletion list BEFORE modifying running config (walk running tree, find files not in candidate)
5. Copy candidate to running (walk candidate, skip `.git`, `var/`, `_SESSION_FILE`, `.gitkeep`, `.validation-*`). Use `shutil.copy2`.
6. Delete running files not in candidate
7. Remove empty directories in running (bottom-up walk, skip `_COPY_EXCLUDES_DIRS` and root)
8. Remove `.candidate/` via `shutil.rmtree`
9. Return success

### Bulk Operations

All three: acquire lock, check session, sort entries, iterate with fail-fast, single git commit.

**`bulk_edit(edits: list[dict], description="") -> OperationResult`**:
- Sort: `key=lambda e: (e["file_path"], -e["line_number"])`
- Each entry: `{file_path, line_number, new_attrs, obj_type, inline_comments}`
- Call `edit_object_in_file()` for each (no parse verification per item)
- Single commit. Return `OperationResult(True, data={"count": N})`

**`bulk_move(moves: list[dict], description="") -> OperationResult`**:
- Sort: `key=lambda m: (m["source_file"], -m["source_line"])`
- Each entry: `{source_file, source_line, target_file, obj_type, attrs}`
- Force `insert_line=None` always (append to target)
- Call `move_object_between_files()` for each
- Single commit. Return `OperationResult(True, data={"count": N})`

**`bulk_delete(deletes: list[dict], description="") -> OperationResult`**:
- Sort: `key=lambda d: (d["file_path"], -d["line_number"])`
- Each entry: `{file_path, line_number}`
- Call `delete_object_from_file()` for each
- Single commit. Return `OperationResult(True, data={"count": N})`

### Internal Helpers

**`_copy_running_to_candidate()`**:
- Walk running config directory
- Skip top-level items starting with `.` or in `_COPY_EXCLUDES_DIRS`
- For files: skip extensions in `_COPY_EXCLUDES_EXTENSIONS`, copy with `shutil.copy2`
- For directories: `shutil.copytree` with `ignore=shutil.ignore_patterns("*.bak", "*.backup", "*.tmp", "backups", "backup", ".staging", ".nagios_staging")`

**`_rewrite_nagios_cfg()`**:
- Read original `nagios.cfg` line by line
- For each line matching a `_PATH_DIRECTIVES` prefix:
  - Extract path after `=`
  - Resolve to absolute path relative to nagios.cfg directory
  - If under running path, rewrite to candidate equivalent
  - If not under running path, leave unchanged
- Comments and non-directive lines pass through unchanged
- Write output to `<candidate_path>/.validation-nagios.cfg`
- Create subdirectories: `var/`, `var/rw/`, `var/archives/`, `var/checkresults/`

**`_write_session_info(session_id, user_name, user_email)`**:
- Compute SHA-256 checksums of all running config files
- Write `.session.json` with: session_id, user_name, user_email, state="active", created_at (ISO format), baseline_checksums dict

**`_read_session_info() -> dict`**: Read `.session.json`, return `{}` if missing.

**`_git_run(*args) -> CompletedProcess`**: Run git command in candidate dir, timeout=30s.

**`_git_init()`**: `git init` + `git config user.name "CandidateManager"` + `git config user.email "candidate@localhost"`

**`_git_commit(message) -> OperationResult`**: `git add -A` then `git commit -m <message> --allow-empty`

**`_get_undo_count() -> int`**: `git rev-list --count HEAD` minus 1 (baseline).

**`_get_baseline_hash() -> str`**: `git rev-list --max-parents=0 HEAD` (first commit).

**`_file_checksum(file_path) -> str`** (static): SHA-256 hex digest.

**`_read_file_safe(path) -> str`** (static): Read UTF-8, fallback to latin-1 on UnicodeDecodeError.

---

## Dead Code & Functionality Migration (Commandments 5 & 6)

This file is a **new creation** — there is no dead code to delete within it. However, once the full candidate system is complete (all layers), the following existing modules become dead code and must be removed:

- `staging_manager.py` — replaced entirely by `candidate_manager.py`
- Staging-related helpers in `nagios_service.py` — any methods that delegate to StagingManager

These deletions are tracked in later layer plans (L04+). This plan does NOT delete them because the system must remain functional during incremental migration.

**Functionality migration:** Every public method in `StagingManager` has a corresponding method in `CandidateManager`. The mapping is documented in the phase plans (L03-routes-candidate.md). No staging functionality is dropped.

## Verification

After implementing this file:

```bash
# File should exist and be importable
python3 -c "from candidate_manager import CandidateManager; print('OK')"

# Lint checks (Commandment 10)
ruff check candidate_manager.py
ruff format --check candidate_manager.py

# Run Layer 1 tests (written in the companion test plan)
python3 -m pytest tests/test_candidate_manager.py -v
```

## Verification Model: Continuous vs Post-Apply

The existing staging system uses `apply_verification.py` for post-apply verification. That module performs two layers of checking after staging data is written to disk:

1. **File-level verification** (`compare_file_changes`): Compares git status before/after apply to verify exactly the expected files changed — no unexpected modifications, no missing changes.
2. **Object-level verification** (`verify_objects`): Re-parses the config after apply and checks that each staged edit, creation, deletion, and move produced the expected result (correct attribute values, objects present/absent in correct files).

`CandidateManager.apply()` does **not** replicate this post-apply verification. This is intentional.

**What replaces it:** The candidate system validates continuously rather than only at apply time. Each object operation (step 5 in the operation pattern) performs a post-mutation parse verification — it re-parses the entire candidate directory via `NagiosConfigParser(self._candidate_path).parse_all()` and reverts via `git checkout -- .` if parsing fails. This means:

- **Preserved guarantee:** Every mutation produces a parseable config. If an edit would corrupt the config file syntax, it is caught and reverted immediately, not discovered minutes later at apply time.
- **Preserved guarantee:** Object identity is maintained — the parse check confirms all objects are still discoverable after each change.
- **Dropped guarantee:** No file-level git diff verification at apply time. The candidate apply is a straightforward `shutil.copy2` of known files — there is no delta/phase system that could apply the wrong set of changes, so file-level verification adds no value.
- **Dropped guarantee:** No post-apply re-parse of the running config. The candidate directory was already validated operation-by-operation. The apply just copies those validated files.

**Why this is better:** Post-apply verification in the staging system exists because the staging system builds changes as deltas (pendingEdits, stagedMoves, etc.) and applies them in phases. Each phase can fail independently, producing partial results. The candidate system operates on real files, so each mutation is immediately verifiable. Catching errors at mutation time gives the user immediate feedback and the ability to undo, rather than discovering problems during a bulk apply.

## Design Decision Tags

| Tag | Decision |
|-----|----------|
| [P1-A] | Path safety: every mutation validates via `is_safe_path` |
| [P1-B] | Pre-apply backup: optional, failure doesn't block apply |
| [P1-C] | Parser corruption guard: post-mutation parse verification with auto-revert |
| [P1-D] | Copy excludes match parser skip patterns |
| [P1-E] | Empty directory cleanup after apply (bottom-up walk) |
| [P1-G] | File-based locking via fcntl for cross-process safety |
| [P1-H] | Bulk move always appends (insert_line=None) |
| [P1-I] | Restore-pending state tracking |
| [P1-J] | UTF-8 with latin-1 fallback for file reading |
| [P1-K] | Undo cleans empty directories |

---

## Change Tracking (Commandment 8)

All implementation tasks for this file. Tick off as completed.

- [ ] Create `candidate_manager.py` with imports and constants
- [ ] Implement `_FileLock` class
- [ ] Implement `CandidateManager.__init__()` and properties
- [ ] Implement `_copy_running_to_candidate()`
- [ ] Implement `_rewrite_nagios_cfg()`
- [ ] Implement `_write_session_info()` and `_read_session_info()`
- [ ] Implement `_git_init()`, `_git_run()`, `_git_commit()`
- [ ] Implement `_get_undo_count()` and `_get_baseline_hash()`
- [ ] Implement `_file_checksum()` and `_read_file_safe()`
- [ ] Implement `_validate_candidate_path()`
- [ ] Implement `has_session()`, `init_session()`, `get_session_info()`, `can_modify()`, `discard()`
- [ ] Implement `get_session_state()` and `set_restore_pending()`
- [ ] Implement `to_candidate_path()` and `to_running_path()`
- [ ] Implement `edit_object()` with audit logging and error handling
- [ ] Implement `delete_object()` with audit logging and error handling
- [ ] Implement `create_object()` with audit logging and error handling
- [ ] Implement `move_object()` with audit logging and error handling
- [ ] Implement `analyze_references()` and `_update_references()`
- [ ] Implement `undo()` with audit logging
- [ ] Implement file/folder operations (create_file, delete_file, move_file, create_folder, delete_folder, move_folder) with audit logging
- [ ] Implement `get_diff()`, `get_file_diff()`, `get_structured_diff()`
- [ ] Implement `detect_conflicts()`
- [ ] Implement `validate()`
- [ ] Implement `apply()` with audit logging, backup, and reference update support
- [ ] Implement `bulk_edit()`, `bulk_move()`, `bulk_delete()` with audit logging
- [ ] Verify all methods have try/except error handling (C4)
- [ ] Verify all public methods call `log_audit()` (C3)
- [ ] Run `ruff check` and `ruff format --check` — clean (C10)
- [ ] Run `python3 -m pytest tests/test_candidate_manager.py -v` — all pass

---

## Commandments Compliance

- [x] **C1 — No live config mutation until Apply.** The candidate system copies running config to `.candidate/`, all edits operate on candidate files only, and `apply()` is the sole method that writes back to the running config. The `TestLiveConfigImmutability` test class in the companion test plan enforces this.
- [x] **C2 — UI visual parity.** N/A — this is a backend-only module with no UI components. UI parity is addressed in frontend layer plans.
- [x] **C3 — Full audit logging.** Every public mutating method calls `log_audit()` with a structured action string (see Audit Logging section above). Application-level logging via `logger.info()`/`logger.error()` is also used throughout.
- [x] **C4 — Proper error handling everywhere.** Every public method wraps its body in try/except, logs exceptions via `logger.exception()`, and returns `OperationResult(False, ...)`. No silent failures (see Error Handling section above).
- [x] **C5 — Dead code deletion.** This is a new file — no dead code exists within it. Deletion of the replaced `staging_manager.py` is tracked in later layer plans (see Dead Code section above).
- [x] **C6 — Full functionality migration.** Every public method in `StagingManager` has a corresponding method in `CandidateManager`. The mapping is documented in L03 route plans. No functionality is dropped.
- [x] **C7 — Palo Alto candidate model.** The architecture section explicitly describes the copy-edit-apply flow: copy running config to `.candidate/`, edit the copy, apply the copy back to running. This is the Palo Alto Networks candidate configuration methodology.
- [x] **C8 — Change tracking document.** The Change Tracking section above provides a tickable checklist of all implementation tasks.
- [x] **C9 — Complete planning before implementation.** This plan specifies every class, method, parameter, return type, and implementation step before any code is written. The companion test plan provides TDD coverage.
- [x] **C10 — Linting enforcement.** The Verification section includes `ruff check` and `ruff format --check` commands. The Change Tracking checklist includes a lint verification step.
- [x] **C11 — Playwright validation.** N/A — this is a backend-only module with no UI surface. Playwright tests for the candidate system are addressed in frontend layer plans where UI changes occur.
