# L12: nagios_service.py — MODIFY

**Layer:** 12 — Staging Removal
**Action:** MODIFY (remove staging/apply code)
**Path:** `nagios_service.py`
**Dependencies:** L01 (CandidateManager handles all apply logic), L02 (parse_stable_key migrated to nagios_model), L04 (routes no longer call apply methods), L12-staging-manager (staging_manager.py deleted)
**Goal:** Remove ~960 lines of staging/apply infrastructure from NagiosService, leaving it as a read/CRUD service only.

---

## Context

NagiosService currently contains two distinct roles:

1. **Read/CRUD service** — parse configs, query objects, create/update/delete/move individual objects with parser reload. This stays.
2. **Staging apply engine** — composite action builder, per-type apply methods (folders, files, moves, deletions), staging state access. This is fully replaced by CandidateManager (L01).

This plan surgically removes role #2 while preserving role #1 intact.

**No live config mutation changes.** The retained CRUD methods (`create_object`, `update_object`, `delete_object`, `move_object`) continue to operate on the running config with parser reload. In the candidate system, these methods are NOT called during normal user editing (CandidateManager operates on candidate files directly via `file_operations`). NagiosService CRUD methods may still be used by administrative routes that operate on the running config outside of a candidate session.

---

## Functionality Migration Audit

Before deleting any code, confirm that all removed functionality is fully present in CandidateManager (L01). This is critical per Commandment 6.

| Removed Method | CandidateManager Equivalent | Status |
|----------------|----------------------------|--------|
| `_build_composite_actions()` | Not needed. Candidate edits files directly; no delta merging required. | Verified |
| `apply_object_composite()` | `CandidateManager.apply()` copies candidate to running. Individual edits applied in real-time. | Verified |
| `_execute_composite_action()` / `_exec_*()` | Individual operations: `cm.edit_object()`, `cm.delete_object()`, `cm.create_object()`, `cm.move_object()` | Verified |
| `_find_by_identity()` / `_find_by_attrs()` | Not needed. Candidate operates on files by path+line, not by object lookup in staging deltas. | Verified |
| `modification_context()` | Not needed. CandidateManager uses file-level locking via `_FileLock`. | Verified |
| `get_typed_staging()` | Not needed. Session state accessed via `cm.get_session_info()`. | Verified |
| `apply_folder_creations()` | `cm.create_folder()` (real-time) + `cm.apply()` copies to running | Verified |
| `apply_file_creations()` | `cm.create_file()` (real-time) + `cm.apply()` copies to running | Verified |
| `apply_file_moves()` | `cm.move_file()` (real-time) + `cm.apply()` copies to running | Verified |
| `apply_folder_moves()` | `cm.move_folder()` (real-time) + `cm.apply()` copies to running | Verified |
| `apply_file_deletions()` | `cm.delete_file()` (real-time) + `cm.apply()` deletes orphans from running | Verified |
| `apply_folder_deletions()` | `cm.delete_folder()` (real-time) + `cm.apply()` deletes orphans from running | Verified |
| `_validate_path_safety()` | `cm._validate_candidate_path()` delegates to `is_safe_path()` | Verified |
| `_build_apply_result()` | Not needed. CandidateManager returns `OperationResult` directly. | Verified |
| `_resolve_on_disk_attrs()` | Not needed. Candidate operates on real files, not reconstructed attrs. | Verified |
| `_log_apply_result()` | Logging handled per-operation in CandidateManager + audit logging in `routes/candidate.py` (L03). | Verified |
| `_resolve_insert_position()` | Not needed. Candidate uses explicit line numbers from the candidate parser. | Verified |
| `_build_edit_detail()` | Replaced by `cm.get_structured_diff()` which computes per-field diffs from git history. | Verified |
| `_create_staged_file()` / `_create_new_file()` | `cm.create_file()` uses `Path.touch()`. | Verified |
| `_apply_staged_file_creations()` / `_apply_new_files()` | `cm.create_file()` (real-time). | Verified |

---

## Removal Audit

### Imports to Remove

| Lines | What | Action |
|-------|------|--------|
| 11 | `import shutil` | REMOVE — only used by apply file/folder methods |
| 12 | `from contextlib import contextmanager` | REMOVE — only used by `modification_context()` |
| 13 | `from dataclasses import dataclass` | REMOVE — only used by `CompositeAction` |
| 14 | `from pathlib import Path` | REMOVE — only used by `_create_new_file()` |
| 20 | `is_safe_path,` (from file_operations import) | REMOVE — only used by `_validate_path_safety()` |
| 25-29 | `from staging_manager import (StagingManager, StagingState, parse_stable_key,)` | REMOVE ENTIRELY — `StagingManager` and `StagingState` deleted with staging; `parse_stable_key` migrated to `nagios_model.py` in L02 |

### Imports to Modify

| Line | What | Action |
|------|------|--------|
| 23 | `from nagios_model import NAME_FIELDS, NagiosObject, OperationResult, get_object_name` | MODIFY — remove `get_object_name` (only used in removed methods at lines 220, 1355), ADD `parse_stable_key` (migrated from staging_manager in L02) |

**Important:** The `parse_stable_key` import MUST move from `staging_manager` to `nagios_model` because `staging_manager.py` is deleted in L12-staging-manager.md. L02-nagios-model.md migrates the function.

### Top-Level Class to Remove

| Lines | What | Action |
|-------|------|--------|
| 34-54 | `@dataclass class CompositeAction` — merged per-entity action for the apply phase | REMOVE |

### Constructor Parameter to Remove

| Lines | What | Action |
|-------|------|--------|
| 63 | `staging_manager: StagingManager \| None = None` parameter in `__init__` | MODIFY — remove parameter |
| 67 | `self._staging_manager = staging_manager` field assignment | REMOVE |

### Methods to Remove — Apply Infrastructure

| Lines | What | Action |
|-------|------|--------|
| 104-123 | `_validate_path_safety()` — path safety wrapper for apply methods | REMOVE |
| 125-143 | `_build_apply_result()` — result dict builder for apply operations | REMOVE |
| 145-170 | `_resolve_on_disk_attrs()` — look up on-disk attributes by identity | REMOVE |
| 172-345 | `_build_composite_actions()` — merge staging operations into per-entity CompositeActions | REMOVE |
| 347-407 | `apply_object_composite()` — execute all object operations as composite actions | REMOVE |
| 409-436 | `_execute_composite_action()` — dispatch to per-type executor | REMOVE |
| 438-457 | `_exec_delete()` — execute delete composite action | REMOVE |
| 459-486 | `_exec_edit()` — execute edit composite action | REMOVE |
| 488-524 | `_exec_move()` — execute move composite action | REMOVE |
| 526-594 | `_exec_move_edit()` — execute move+edit composite action | REMOVE |
| 596-614 | `_exec_create()` — execute create composite action | REMOVE |
| 616-631 | `_find_by_identity()` — find object by stable identity (source_file + type + name) | REMOVE |
| 633-645 | `_find_by_attrs()` — find object by exact attribute match | REMOVE |
| 647-660 | `modification_context()` — context manager for parser modification with lock held | REMOVE |
| 662-674 | `get_typed_staging()` — get typed staging state from staging manager | REMOVE |

### Methods to Remove — Staging Apply Phases

| Lines | What | Action |
|-------|------|--------|
| 1136-1154 | `_log_apply_result()` — log helper for apply phases | REMOVE |
| 1156-1181 | `apply_folder_creations()` — create staged folders | REMOVE |
| 1183-1202 | `_create_staged_file()` — create a single staged file with header content | REMOVE |
| 1204-1220 | `_create_new_file()` — create a new empty file, resolving relative paths | REMOVE |
| 1222-1238 | `_apply_staged_file_creations()` — process stagedFileCreations entries | REMOVE |
| 1240-1255 | `_apply_new_files()` — process newFiles entries | REMOVE |
| 1257-1271 | `apply_file_creations()` — create staged files | REMOVE |
| 1273-1329 | `_resolve_insert_position()` — convert virtual insertPosition to line number | REMOVE |
| 1331-1366 | `_build_edit_detail()` — build detail entry for applied edits | REMOVE |
| 1368-1401 | `apply_file_moves()` — move staged files | REMOVE |
| 1403-1440 | `apply_folder_moves()` — move staged folders | REMOVE |
| 1442-1466 | `apply_file_deletions()` — delete staged files | REMOVE |
| 1468-1493 | `apply_folder_deletions()` — delete staged folders | REMOVE |

### Line Count Summary

| Category | Lines Removed |
|----------|---------------|
| Imports (partial lines) | ~8 |
| `CompositeAction` dataclass | 21 |
| Constructor changes | 2 |
| Apply infrastructure methods (104-674) | ~571 |
| Apply phase methods (1136-1493) | ~358 |
| **Total** | **~960** |

Note: The actual removal is closer to 960 lines, significantly more than the initial ~500 estimate. The apply infrastructure (composite action builder, executors, helpers) and the six per-phase apply methods together account for most of the file.

---

## What Remains

After removal, NagiosService retains its role as a thin service layer over the parser and file_operations:

### Imports (cleaned)

```python
import logging
import multiprocessing
import os
import re

from file_operations import (
    add_object_to_file,
    delete_object_from_file,
    edit_object_in_file,
    move_object_between_files,
)
from nagios_model import NAME_FIELDS, NagiosObject, OperationResult, parse_stable_key
from nagios_parser import NagiosConfigParser
```

Note: `parse_stable_key` now imported from `nagios_model` (migrated from `staging_manager` in L02). No remaining `staging_manager` import.

### Constructor (cleaned)

```python
def __init__(self, config_path: str):
    self._config_path = config_path
    self._parser: NagiosConfigParser | None = None
    self._lock = multiprocessing.Lock()
    self._parser_corrupted = False
```

### Properties and Parser Management

| Method | Description |
|--------|-------------|
| `config_path` (property getter) | Return config path |
| `config_path` (property setter) | Set config path, clear parser |
| `parser` (property) | Lazy-init parser, thread-safe |
| `reload()` | Force reload, clear corrupted flag |

### Query Methods

| Method | Description |
|--------|-------------|
| `get_objects()` | Return all parsed objects |
| `find_object_by_index()` | Find object by global index |
| `search_objects()` | Search with query, type, field, regex |
| `get_object_stats()` | Stats: total, by_type, file_count |

### Domain Logic

| Method | Description |
|--------|-------------|
| `get_name_field()` | Name field lookup for object type |
| `find_object_by_stable_key()` | Find object by stable key string |
| `transform_name()` | Find/replace and prefix/suffix on names |
| `update_references()` | Update all references when object renamed |

### CRUD Operations

| Method | Description |
|--------|-------------|
| `_reload_parser_safe()` | Reload parser with corruption guard |
| `_check_parser_state()` | Check corrupted flag |
| `create_object()` | Create object in file + reload |
| `update_object()` | Update object attrs + reload |
| `delete_object()` | Delete object from file + reload |
| `move_object()` | Move object between files + reload |

### Post-Removal File Size

- **Before:** ~1494 lines
- **Removed:** ~960 lines
- **After:** ~534 lines

---

## Cleaned `__init__` Signature

```python
class NagiosService:
    """Service layer for Nagios configuration management.

    Wraps the parser and file operations, providing a unified interface
    with automatic state synchronization (reload after write).
    """

    def __init__(self, config_path: str):
        self._config_path = config_path
        self._parser: NagiosConfigParser | None = None
        self._lock = multiprocessing.Lock()
        # Flag to indicate parser state is inconsistent with disk state.
        # When True, all CRUD operations are blocked until explicit reload succeeds.
        self._parser_corrupted = False
```

---

## Error Handling in Retained Code

The retained CRUD methods (`create_object`, `update_object`, `delete_object`, `move_object`) already have proper error handling per Commandment 4:

- Each wraps its operation in `try/except Exception` with structured logging via `logger.exception()`
- Each checks `_check_parser_state()` before proceeding (blocks on corrupted parser)
- Each calls `_reload_parser_safe()` after file mutation, with corruption flag on failure
- All return `OperationResult(False, error_message)` on any failure -- no silent failures

No error handling changes are required by this plan.

---

## Audit Logging in Retained Code

The retained CRUD methods already emit structured log entries via `logger.info()` on success and `logger.error()` / `logger.exception()` on failure per Commandment 3. These methods are NOT the primary edit path in the candidate system (CandidateManager handles that), but they log correctly if called.

Audit trail for candidate edits is handled in `routes/candidate.py` (L03-routes-candidate.md) which calls `log_audit()` during apply.

---

## Callers to Update

These files pass `staging_manager=` to `NagiosService.__init__` and must be updated to omit it:

| File | What to change | Handled by |
|------|---------------|------------|
| `app.py` | Remove `staging_manager=sm` from `NagiosService(...)` constructor call | L12-app-cleanup.md |
| `tests/test_reorder.py` (line 178) | Remove `staging_manager=sm` parameter | L12-test-deletions.md (file deleted) |
| `tests/test_composite_apply.py` | Entire file deleted (tests removed apply code) | L12-test-deletions.md |
| `tests/test_apply_robustness.py` | Entire file deleted (tests removed apply code) | L12-test-deletions.md |

These files call removed methods and must be updated (handled by their own L-plans):

| File | Methods called | Handled by |
|------|---------------|------------|
| `routes/staging.py` (lines 927-933) | `apply_object_composite()`, `apply_folder_creations()`, `apply_file_creations()`, `apply_file_moves()`, `apply_folder_moves()`, `apply_file_deletions()`, `apply_folder_deletions()` | L04-routes-staging.md (file deleted) |
| `routes/helpers.py` (line 76) | `modification_context()` via `get_parser_for_modification()` | L12-routes-helpers-cleanup.md |

---

## Linting Verification

After all removals, the modified file must pass Ruff (per Commandment 10):

```bash
# Ruff lint check
python3 -m ruff check nagios_service.py

# Ruff format check
python3 -m ruff format --check nagios_service.py
```

---

## Verification

```bash
# File should be importable after changes
python3 -c "from nagios_service import NagiosService; print('OK')"

# Constructor should no longer accept staging_manager
python3 -c "
from nagios_service import NagiosService
import inspect
sig = inspect.signature(NagiosService.__init__)
params = list(sig.parameters.keys())
assert 'staging_manager' not in params, f'staging_manager still in params: {params}'
print(f'Constructor params: {params}')
print('OK')
"

# parse_stable_key should be imported from nagios_model, not staging_manager
python3 -c "
import ast, sys
with open('nagios_service.py') as f:
    tree = ast.parse(f.read())
for node in ast.walk(tree):
    if isinstance(node, ast.ImportFrom):
        if node.module == 'staging_manager':
            print(f'FAIL: still imports from staging_manager')
            sys.exit(1)
print('No staging_manager imports found')
print('OK')
"

# Removed methods should not exist
python3 -c "
from nagios_service import NagiosService
removed = [
    'apply_object_composite', '_build_composite_actions',
    '_execute_composite_action', '_exec_delete', '_exec_edit',
    '_exec_move', '_exec_move_edit', '_exec_create',
    'modification_context', 'get_typed_staging',
    'apply_folder_creations', 'apply_file_creations',
    'apply_file_moves', 'apply_folder_moves',
    'apply_file_deletions', 'apply_folder_deletions',
    '_validate_path_safety', '_build_apply_result',
    '_resolve_on_disk_attrs', '_find_by_identity', '_find_by_attrs',
    '_log_apply_result', '_resolve_insert_position', '_build_edit_detail',
    '_create_staged_file', '_create_new_file',
    '_apply_staged_file_creations', '_apply_new_files',
]
for name in removed:
    assert not hasattr(NagiosService, name), f'{name} still exists'
print(f'Verified {len(removed)} methods removed')
print('OK')
"

# Retained methods should still exist
python3 -c "
from nagios_service import NagiosService
retained = [
    'reload', 'get_objects', 'find_object_by_index', 'search_objects',
    'get_object_stats', 'get_name_field', 'find_object_by_stable_key',
    'transform_name', 'update_references',
    'create_object', 'update_object', 'delete_object', 'move_object',
]
for name in retained:
    assert hasattr(NagiosService, name), f'{name} missing'
print(f'Verified {len(retained)} methods retained')
print('OK')
"

# CompositeAction should no longer be importable
python3 -c "
try:
    from nagios_service import CompositeAction
    assert False, 'CompositeAction should not be importable'
except ImportError:
    print('CompositeAction correctly removed')
print('OK')
"

# Ruff lint and format checks (Commandment 10)
python3 -m ruff check nagios_service.py
python3 -m ruff format --check nagios_service.py

# Run existing tests (apply tests are deleted by L12-test-deletions.md)
python3 -m pytest tests/ -v -k "not test_apply and not test_composite and not test_reorder and not test_staging_integration" --tb=short
```

---

## Change Tracking

| # | Change | Status |
|---|--------|--------|
| 1 | Remove `import shutil` (line 11) | [ ] |
| 2 | Remove `from contextlib import contextmanager` (line 12) | [ ] |
| 3 | Remove `from dataclasses import dataclass` (line 13) | [ ] |
| 4 | Remove `from pathlib import Path` (line 14) | [ ] |
| 5 | Remove `is_safe_path` from file_operations import (line 20) | [ ] |
| 6 | Remove entire `from staging_manager import (...)` block (lines 25-29) | [ ] |
| 7 | Modify nagios_model import: remove `get_object_name`, add `parse_stable_key` (line 23) | [ ] |
| 8 | Remove `CompositeAction` dataclass (lines 34-54) | [ ] |
| 9 | Remove `staging_manager` param from `__init__` (line 63) | [ ] |
| 10 | Remove `self._staging_manager` assignment (line 67) | [ ] |
| 11 | Remove `_validate_path_safety()` (lines 104-123) | [ ] |
| 12 | Remove `_build_apply_result()` (lines 125-143) | [ ] |
| 13 | Remove `_resolve_on_disk_attrs()` (lines 145-170) | [ ] |
| 14 | Remove `_build_composite_actions()` (lines 172-345) | [ ] |
| 15 | Remove `apply_object_composite()` (lines 347-407) | [ ] |
| 16 | Remove `_execute_composite_action()` (lines 409-436) | [ ] |
| 17 | Remove `_exec_delete()` (lines 438-457) | [ ] |
| 18 | Remove `_exec_edit()` (lines 459-486) | [ ] |
| 19 | Remove `_exec_move()` (lines 488-524) | [ ] |
| 20 | Remove `_exec_move_edit()` (lines 526-594) | [ ] |
| 21 | Remove `_exec_create()` (lines 596-614) | [ ] |
| 22 | Remove `_find_by_identity()` (lines 616-631) | [ ] |
| 23 | Remove `_find_by_attrs()` (lines 633-645) | [ ] |
| 24 | Remove `modification_context()` (lines 647-660) | [ ] |
| 25 | Remove `get_typed_staging()` (lines 662-674) | [ ] |
| 26 | Remove `_log_apply_result()` (lines 1136-1154) | [ ] |
| 27 | Remove `apply_folder_creations()` (lines 1156-1181) | [ ] |
| 28 | Remove `_create_staged_file()` (lines 1183-1202) | [ ] |
| 29 | Remove `_create_new_file()` (lines 1204-1220) | [ ] |
| 30 | Remove `_apply_staged_file_creations()` (lines 1222-1238) | [ ] |
| 31 | Remove `_apply_new_files()` (lines 1240-1255) | [ ] |
| 32 | Remove `apply_file_creations()` (lines 1257-1271) | [ ] |
| 33 | Remove `_resolve_insert_position()` (lines 1273-1329) | [ ] |
| 34 | Remove `_build_edit_detail()` (lines 1331-1366) | [ ] |
| 35 | Remove `apply_file_moves()` (lines 1368-1401) | [ ] |
| 36 | Remove `apply_folder_moves()` (lines 1403-1440) | [ ] |
| 37 | Remove `apply_file_deletions()` (lines 1442-1466) | [ ] |
| 38 | Remove `apply_folder_deletions()` (lines 1468-1493) | [ ] |
| 39 | Run Ruff lint + format checks | [ ] |
| 40 | Run verification scripts | [ ] |

---

## Commandments Compliance

| # | Commandment | Compliance | Notes |
|---|-------------|------------|-------|
| 1 | No live config mutation until Apply | COMPLIANT | This plan only removes dead staging code. Retained CRUD methods are NOT called during candidate editing -- CandidateManager (L01) handles all edits on the candidate copy. Live config is only mutated by `CandidateManager.apply()`. |
| 2 | UI visual parity | COMPLIANT | This is a backend-only change. No UI modifications. The frontend never called NagiosService methods directly -- it called API routes which are handled by other L-plans. |
| 3 | Full audit logging | COMPLIANT | Retained CRUD methods already have structured logging via `logger.info/error/exception`. Candidate-system audit logging is handled in `routes/candidate.py` (L03-routes-candidate.md) which calls `log_audit()` during apply with per-operation detail. |
| 4 | Proper error handling | COMPLIANT | Retained CRUD methods have `try/except` with `OperationResult(False, error)` returns, parser corruption guard (`_check_parser_state`), and safe reload (`_reload_parser_safe`). No silent failures. Explicit section added documenting error handling in retained code. |
| 5 | Dead code deletion | COMPLIANT | All 28 staging/apply methods removed. All 6 staging-only imports removed. `CompositeAction` dataclass removed. `staging_manager` constructor parameter removed. Zero staging code remains in the file. |
| 6 | Full functionality migration | COMPLIANT | Functionality migration audit table added proving all 20 removed methods have equivalents in CandidateManager (L01). Every apply phase, composite action, and helper has a verified candidate-system replacement. |
| 7 | Palo Alto candidate model | COMPLIANT | By removing the delta-based staging apply engine, this plan completes the transition to the Palo Alto model where edits happen on a candidate copy and apply copies it back to running config. |
| 8 | Change tracking document | COMPLIANT | 40-item change tracking checklist added with per-line granularity. |
| 9 | Complete planning before implementation | COMPLIANT | This plan provides line-level specificity for all removals, exact import changes, caller cross-references to other L-plans, and complete verification scripts. No ambiguity remains. |
| 10 | Linting enforcement | COMPLIANT | Ruff lint and format checks added to both the Linting Verification section and the Verification script block. Change tracking item #39 requires Ruff pass. |
| 11 | Playwright validation | NOT APPLICABLE | This plan removes backend code only (no routes, no UI). The removed methods are staging-era apply infrastructure that is deleted along with its route callers (L04-routes-staging.md). Playwright tests for the candidate system are covered by L03-test-candidate-routes.md and the E2E test plan. |
