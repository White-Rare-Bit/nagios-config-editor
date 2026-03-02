# L12: staging_manager.py -- DELETE

**Layer:** 12 -- Staging Removal
**Action:** DELETE
**Path:** `staging_manager.py`
**Dependencies:** L01 (CandidateManager replaces all staging functionality), L02 (stable key functions migrated to nagios_model.py), L04-routes-staging.md (routes/staging.py deleted), L12-nagios-service.md (NagiosService staging imports removed), L12-app-cleanup.md (StagingManager initialization removed from app.py), L12-routes-helpers-cleanup.md (get_staging_manager helper removed), L12-test-deletions.md (staging test files deleted), L12-test-stable-keys.md (import updated), L12-test-atomic-writes.md (import updated), L12-test-health-check.md (import updated)
**Goal:** Delete the old delta-based staging manager module (1697 lines). All functionality has been migrated to CandidateManager (L01) or nagios_model.py (L02), or intentionally dropped with documented rationale.

---

## Context

`staging_manager.py` (1697 lines) is the core of the old delta-based staging system. It stores all user edits as in-memory deltas (pendingEdits, stagedMoves, stagedCreations, etc.) in a `staging.json` file and only writes changes to disk at apply time via NagiosService's apply methods. The candidate system (L01) replaces this entirely: edits are made directly to a `.candidate/` copy of the config, each action is a git commit, undo is `git reset --hard HEAD~1`, and "Apply" copies the candidate files back to the running config.

This plan deletes the entire file. Every class, function, and constant in the module has been audited below for migration status.

---

## Removal Audit

### Classes

| Class | Lines | Replacement | Status |
|-------|-------|-------------|--------|
| `OperationType` (Enum) | 41-62 | Not needed. CandidateManager uses git commit messages to describe operations; no typed operation registry. | Dropped (no equivalent needed) |
| `StagingStatus` (Enum) | 64-68 | Replaced by CandidateManager session state: `has_session()` (bool) + `get_session_state()` returns `""` / `"active"` / `"restore_pending"`. | Migrated to L01 |
| `PendingEdit` (dataclass) | 71-77 | Not needed. Candidate edits are applied directly to files via `edit_object_in_file()`. | Dropped (no delta storage) |
| `StagedMove` (dataclass) | 80-86 | Not needed. Candidate moves use `move_object_between_files()` directly. | Dropped (no delta storage) |
| `StagedCreation` (dataclass) | 89-93 | Not needed. Candidate creations use `add_object_to_file()` directly. | Dropped (no delta storage) |
| `StagedDeletion` (dataclass) | 97-101 | Not needed. Candidate deletions use `delete_object_from_file()` directly. | Dropped (no delta storage) |
| `StagedFileOp` (dataclass) | 105-108 | Not needed. Candidate file ops operate directly on the candidate directory. | Dropped (no delta storage) |
| `UndoEntry` (dataclass) | 112-117 | Not needed. Undo is `git reset --hard HEAD~1` in candidate; no typed undo entries. | Dropped (git replaces undo stack) |
| `StagingState` (dataclass) | 121-228 | Not needed. Candidate state is the git repo in `.candidate/` plus `.session.json`. No JSON serialization of deltas. | Dropped (no delta storage) |
| `ChecksumManager` | 231-363 | Replaced by `CandidateManager.detect_conflicts()` which compares `baseline_checksums` from `.session.json` against current running file hashes. | Migrated to L01 |
| `UndoStackManager` | 366-497 | Replaced by git commits. `CandidateManager.undo()` runs `git reset --hard HEAD~1`. Undo count = `git rev-list --count HEAD` minus 1. | Migrated to L01 |
| `FileOperationsStager` | 500-717 | Replaced by `CandidateManager.create_file/delete_file/move_file/create_folder/delete_folder/move_folder`. These operate directly on the candidate directory instead of staging deltas. | Migrated to L01 |
| `StagingManager` | 720-1391 | Replaced entirely by `CandidateManager`. See per-method audit below. | Migrated to L01 |
| `UndoKeyError` (ValueError subclass) | 1454-1457 | Not needed. CandidateManager returns `OperationResult(False, error)` for undo failures. | Dropped (error handling via OperationResult) |

### StagingManager Methods (per-method audit)

| Method | Lines | Replacement | Status |
|--------|-------|-------------|--------|
| `__init__()` | 744-760 | `CandidateManager.__init__()` | Migrated |
| `_ensure_staging_dir()` | 762-768 | Not needed. `.candidate/` created by `init_session()`. | Dropped |
| `_is_empty_staging()` | 770-792 | `CandidateManager.has_session()` (bool check on directory existence) | Migrated |
| `_extract_staging_paths()` | 794-832 | Not needed. No delta paths to extract; candidate operates on real files. | Dropped |
| `_has_stale_paths()` | 834-848 | Not needed. No path staleness concept in candidate model. | Dropped |
| `get_staging()` | 850-880 | `CandidateManager.get_session_info()` + `get_diff()` + `get_structured_diff()` | Migrated |
| `save_staging()` | 882-929 | Not needed. No staging.json to save; edits go directly to candidate files. | Dropped |
| `save_staging_atomic()` | 931-955 | Not needed. Git commits provide atomicity. | Dropped |
| `clear_staging()` | 957-969 | `CandidateManager.discard()` (removes `.candidate/` directory) | Migrated |
| `has_staging()` | 971-994 | `CandidateManager.has_session()` | Migrated |
| `_count_staged_operations()` | 996-1008 | `CandidateManager.get_diff()` returns `undo_count` and `changed_files` list | Migrated |
| `get_staging_info()` | 1010-1046 | `CandidateManager.get_session_info()` | Migrated |
| `get_lock_owner()` | 1048-1058 | `CandidateManager.get_session_info()` returns `session_id` | Migrated |
| `can_modify()` | 1060-1077 | `CandidateManager.can_modify()` | Migrated |
| `validate_or_acquire_lock()` | 1079-1119 | `CandidateManager.init_session()` (implicit on first edit via routes) | Migrated |
| `get_lock_status()` | 1121-1148 | `GET /api/candidate` returns session info including lock status | Migrated |
| `get_empty_staging_structure()` | 1150-1157 | Not needed. No empty staging structure concept. | Dropped |
| `migrate_staging_schema()` | 1159-1187 | Not needed. No staging.json schema to migrate. | Dropped |
| Undo delegate methods (1189-1205) | 1189-1205 | Delegated to `CandidateManager.undo()` | Migrated |
| Checksum delegate methods (1213-1225) | 1213-1225 | Delegated to `CandidateManager.detect_conflicts()` | Migrated |
| File ops delegate methods (1233-1257) | 1233-1257 | Delegated to `CandidateManager.create_file/delete_file/move_file/create_folder/delete_folder/move_folder` | Migrated |
| `stage_bulk_rename()` | 1261-1317 | `CandidateManager.bulk_edit()` | Migrated |
| `stage_bulk_move()` | 1319-1376 | `CandidateManager.bulk_move()` | Migrated |
| `get_total_staged_count()` | 1378-1391 | `CandidateManager.get_diff()` returns `undo_count` | Migrated |

### Module-Level Functions

| Function | Lines | Replacement | Status |
|----------|-------|-------------|--------|
| `generate_stable_key()` | 1394-1410 | Migrated to `nagios_model.py` in L02 | Migrated |
| `parse_stable_key()` | 1412-1431 | Migrated to `nagios_model.py` in L02 | Migrated |
| `generate_stable_key_for_object()` | 1433-1452 | Migrated to `nagios_model.py` in L02 | Migrated |
| `_filter_staged_entries()` | 1459-1488 | Not needed. No staged entries to filter. | Dropped |
| `_remove_by_op_id()` | 1490-1508 | Not needed. No op_id tracking in candidate model. | Dropped |
| Undo handlers (`_undo_edit`, `_undo_move`, etc.) | 1510-1697 | Not needed. Undo is `git reset --hard HEAD~1`. No per-type undo handlers. | Dropped |

### Module-Level Constants

| Constant | Line | Replacement | Status |
|----------|------|-------------|--------|
| `STAGING_SCHEMA_VERSION` | 31 | Not needed. No staging.json schema. | Dropped |
| `UNDO_HANDLERS` dict | (referenced but defined inline) | Not needed. Git-based undo replaces handler dispatch. | Dropped |

### Functionality Migration Checklist

| Capability | Old System | New System | Status |
|------------|-----------|------------|--------|
| Session-based locking | `StagingManager.can_modify(session_id)` checks staging.json `sessionId` | `CandidateManager.can_modify(session_id)` checks `.session.json` | Migrated |
| True staging (no live mutation until Apply) | Deltas stored in staging.json; applied via NagiosService apply methods | Edits applied to `.candidate/` copy; `apply()` copies back to running | Migrated (Commandment 1 preserved) |
| Undo/redo | UndoStackManager with typed handlers per OperationType | `git reset --hard HEAD~1` (each action = commit) | Migrated (simpler, more reliable) |
| Conflict detection | ChecksumManager compares base vs current file checksums | `CandidateManager.detect_conflicts()` compares baseline_checksums from `.session.json` | Migrated |
| File/folder staging operations | FileOperationsStager stores deltas in staging.json | CandidateManager operates directly on candidate directory files | Migrated |
| Bulk rename | `stage_bulk_rename()` stores edits in staging.json | `CandidateManager.bulk_edit()` edits candidate files directly | Migrated |
| Bulk move | `stage_bulk_move()` stores moves in staging.json | `CandidateManager.bulk_move()` moves files in candidate directly | Migrated |
| Atomic staging persistence | `save_staging_atomic()` with temp file + rename | Git commits provide atomic state transitions | Migrated |
| Schema migration | `migrate_staging_schema()` for staging.json format changes | Not needed -- no JSON schema to migrate | Intentionally dropped |
| Stale path detection | `_has_stale_paths()` checks for path validity | Not needed -- candidate operates on real files, stale paths are impossible | Intentionally dropped |

---

## Import References (must be zero before deletion)

All imports from `staging_manager` in source and test files must be removed or redirected before this file can be deleted. Each is handled by a specific L-plan:

| File | Line | Reference | Handled By |
|------|------|-----------|------------|
| `app.py` | 18 | `from staging_manager import StagingManager` | L12-app-cleanup.md |
| `nagios_service.py` | 25-29 | `from staging_manager import (StagingManager, StagingState, parse_stable_key,)` | L12-nagios-service.md (StagingManager/StagingState removed; `parse_stable_key` import redirected to `nagios_model`) |
| `apply_verification.py` | 13 | `from staging_manager import parse_stable_key` | L12-apply-verification.md (entire file deleted) |
| `routes/staging.py` | 15 | `from staging_manager import UNDO_HANDLERS, OperationType, UndoKeyError` | L04-routes-staging.md (entire file deleted) |
| `routes/settings.py` | 89 | `from staging_manager import StagingManager` | L04-routes-settings.md |
| `routes/bulk_ops.py` | 12 | `from staging_manager import generate_stable_key_for_object` | L04-routes-bulk-ops.md (import redirected to nagios_model) |
| `routes/backups.py` | 9 | `from staging_manager import StagingStatus` | L04-routes-backups.md |
| `routes/git.py` | 9 | `from staging_manager import StagingStatus` | L04-routes-git.md |
| `tests/test_stable_keys.py` | 11 | `from staging_manager import generate_stable_key_for_object` | L12-test-stable-keys.md (import redirected to nagios_model) |
| `tests/test_atomic_writes.py` | 17 | `from staging_manager import StagingManager` | L12-test-atomic-writes.md |
| `tests/test_reorder.py` | 23 | `from staging_manager import StagingManager` | L12-test-deletions.md (entire file deleted) |

**Dependency ordering:** All 11 import references above must be resolved (by their respective L-plans) before this deletion executes. This plan is at Layer 12, and all dependency plans are at L02-L12, so the ordering is satisfied.

---

## Changes

Delete entire file: `staging_manager.py` (1697 lines)

---

## Audit Logging

No audit logging changes needed. `staging_manager.py` itself contains no audit log calls (it delegates to `audit_service.log_audit()` from route handlers, not from the manager itself). All audit logging for candidate operations is handled by `routes/candidate.py` (L03-routes-candidate.md), which logs every operation through both `audit_service.log_audit()` and the application logger.

---

## Error Handling

No error handling changes needed. This deletion removes error handling code that is no longer reachable. The replacement error handling in CandidateManager (L01) follows the same patterns:
- All methods return `OperationResult(success, error, data)` -- no silent failures
- Per-operation parse verification catches config corruption immediately with auto-revert via `git checkout -- .`
- Lock contention returns `OperationResult(False, "A candidate session already exists")`
- Path safety validation via `is_safe_path()` on every mutation

---

## Verification

```bash
# Confirm file is deleted
test ! -f staging_manager.py && echo "DELETED" || echo "STILL EXISTS"

# No import references remain in source files
grep -r "from staging_manager\|import staging_manager" *.py routes/ tests/ && echo "FAIL: references found" || echo "OK: no references"

# All tests pass with no import errors
python3 -m pytest tests/ -v

# Lint check (ruff)
python3 -m ruff check .
python3 -m ruff format --check .
```

---

## Playwright Validation

No Playwright tests needed for this plan. This is a backend-only module deletion with no UI impact. The CandidateManager's replacement functionality is tested by:
- `tests/test_candidate_manager.py` (L01) -- unit tests for all CandidateManager operations
- `tests/test_candidate_routes.py` (L03) -- integration tests for all candidate API routes
- Existing Playwright E2E tests validate that the UI continues to function after migration (Commandment 2: UI visual parity)

---

## Change Tracking

| # | Change | File | Status |
|---|--------|------|--------|
| 1 | Delete `staging_manager.py` (1697 lines) | `staging_manager.py` | PENDING |

**Pre-conditions (must be completed before this change):**

| # | Pre-condition | L-Plan | Status |
|---|---------------|--------|--------|
| 1 | Stable key functions migrated to `nagios_model.py` | L02-nagios-model.md | PENDING |
| 2 | CandidateManager created with full replacement functionality | L01-candidate-manager.md | PENDING |
| 3 | All route files updated to remove staging_manager imports | L04-routes-staging.md, L04-routes-settings.md, L04-routes-bulk-ops.md, L04-routes-backups.md, L04-routes-git.md | PENDING |
| 4 | app.py updated to remove StagingManager initialization | L12-app-cleanup.md | PENDING |
| 5 | nagios_service.py updated to remove staging imports and apply methods | L12-nagios-service.md | PENDING |
| 6 | routes/helpers.py updated to remove get_staging_manager() | L12-routes-helpers-cleanup.md | PENDING |
| 7 | apply_verification.py deleted (references staging_manager) | L12-apply-verification.md | PENDING |
| 8 | Test files deleted or updated to remove staging_manager imports | L12-test-deletions.md, L12-test-stable-keys.md, L12-test-atomic-writes.md, L12-test-health-check.md | PENDING |

Referenced in: L00-migration-inventory.md Section 1.1, row 1 (`staging_manager.py` -- [covered]).

---

## Commandments Compliance

| # | Commandment | Status | Notes |
|---|-------------|--------|-------|
| 1 | No live config mutation until Apply | COMPLIANT | Module being deleted is part of the old staging system. Its replacement (CandidateManager, L01) edits only the `.candidate/` directory; live config is untouched until `apply()` copies candidate files back. The "no live mutation until Apply" guarantee is preserved by the candidate model. |
| 2 | UI visual parity | COMPLIANT | No UI changes. `staging_manager.py` is a backend module with no frontend impact. All UI-visible behavior (undo, commit, conflict detection) is replicated by CandidateManager with identical API semantics via `routes/candidate.py`. |
| 3 | Full audit logging | COMPLIANT | `staging_manager.py` contains no audit log calls; audit logging is done by route handlers. Candidate route handlers (L03-routes-candidate.md) log all operations through both `audit_service.log_audit()` and the application logger. |
| 4 | Proper error handling | COMPLIANT | Replacement error handling in CandidateManager uses `OperationResult(success, error, data)` for all methods, per-operation parse verification with auto-revert on corruption, and explicit lock contention errors. No silent failures. |
| 5 | Dead code deletion | COMPLIANT | This plan IS the dead code deletion -- the entire 1697-line module is removed because it has zero use in the candidate system after all import references are resolved by dependency plans. |
| 6 | Full functionality migration | COMPLIANT | Every class, method, and function has been audited above with explicit migration status. 3 stable key functions migrated to `nagios_model.py` (L02). All manager functionality migrated to `CandidateManager` (L01). Delta storage dataclasses and undo handlers intentionally dropped (replaced by git-based approach). No functionality dropped without documented rationale. |
| 7 | Palo Alto candidate model | COMPLIANT | The deletion of the delta-based staging system is the final step in adopting the Palo Alto candidate model: copy config to candidate directory, edit candidate directly, apply candidate back to live. `staging_manager.py` represents the old delta/patch approach that is incompatible with this model. |
| 8 | Change tracking document | COMPLIANT | Change tracking table with pre-conditions included above. File tracked in L00-migration-inventory.md (Section 1.1, row 1) with status [covered]. All 11 import references enumerated with handling L-plan. |
| 9 | Complete planning before implementation | COMPLIANT | Full removal audit covering all 14 classes, 30+ methods, 7 module-level functions, and 2 constants completed. All 11 import references mapped to dependency plans. Functionality migration checklist covers 11 capabilities. Pre-condition ordering verified. |
| 10 | Linting enforcement | COMPLIANT | Verification section includes `ruff check .` and `ruff format --check .` to confirm no lint regressions after deletion. |
| 11 | Playwright validation | COMPLIANT | Not directly applicable -- backend module deletion with no UI impact. Documented in Playwright Validation section. Existing Playwright E2E tests validate that the UI continues to function after migration. |
