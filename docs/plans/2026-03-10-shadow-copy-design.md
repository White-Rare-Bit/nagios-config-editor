# Shadow Copy Migration Design

**Date:** 2026-03-10
**Status:** Approved
**Replaces:** JSON-diff staging system

## Summary

Replace the JSON-diff staging architecture with a shadow copy system. Instead of tracking individual operations as JSON entries (pendingEdits, stagedMoves, etc.), the app copies the entire Nagios config directory on first edit and performs all mutations directly on that copy. "Apply" copies changed files back to the original directory.

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Shadow mechanism | Real directory copy on disk | Simple, parser works unchanged |
| Concurrency model | Single editor, session-based lock | Retained from current system |
| Undo | File-level snapshots before each mutation | One mechanism replaces 18 typed handlers |
| Shadow creation | Full copy on first edit | Avoids overlay/union-filesystem complexity |
| Shadow location | Dedicated app-level directory (configurable) | Decoupled from config tree, follows backup path pattern |
| Backup system | Keep as-is | Independent safety net for post-apply restore |
| Frontend model | Server-authoritative, thin client | Eliminates all client-side staging state |
| Apply strategy | All-or-nothing with pre-apply backup | Consistent config state guaranteed |
| Change count badge | Object-level count (not file-level) | Users think in objects, not files |

## Architecture

### ShadowCopyManager

Core class replacing `StagingManager`. Responsibilities: shadow lifecycle, lock management, undo snapshots, diff computation, apply.

**Disk layout:**

```
<shadow_base_path>/
  config/              # Full copy of nagios cfg files
  snapshots/           # Undo stack
    <uuid>/
      meta.json        # {description, timestamp, files: ["path1.cfg", ...]}
      files/
        path1.cfg      # Pre-mutation copy of affected file
  lock.json            # {session_id, user_name, user_email, created_at}
```

**Interface:**

```python
class ShadowCopyManager:
    # Lifecycle
    create_shadow(session_id, user_name, user_email) -> OperationResult
    destroy_shadow() -> OperationResult
    has_shadow() -> bool

    # Lock
    get_lock_status() -> dict
    can_modify(session_id) -> bool
    break_lock() -> OperationResult

    # Undo
    snapshot_files(file_paths, description) -> str  # returns snapshot_id
    undo() -> OperationResult  # pops latest, restores files
    get_undo_count() -> int

    # Diff
    get_changed_files() -> list[dict]  # {path, status: added/modified/deleted}
    get_file_diff(path) -> dict  # unified diff
    get_changed_object_count() -> int  # for badge

    # Apply
    apply(backup_manager) -> OperationResult  # backup, copy changed, destroy shadow

    # Path helpers
    shadow_path(relative_path) -> str
    original_path(relative_path) -> str
```

**Thread safety:** `multiprocessing.Lock` wrapping all mutations.

**Parser integration:** Parser gets pointed at shadow directory. All CRUD operations write to shadow files via existing `file_operations.py`. Parser reloads read from shadow.

### Backend Route Changes

API endpoints stay the same; implementations change behind them.

**Staging routes (simplified):**

| Endpoint | New implementation |
|----------|--------------------|
| `GET /api/staging` | `get_changed_files()` summary |
| `DELETE /api/staging` | `destroy_shadow()` |
| `GET /api/staging/info` | `{totalCount (object-level), undoCount, changedFiles}` |
| `POST /api/staging/apply` | `shadow.apply(backup_manager)` |
| `POST /api/staging/undo` | `shadow.undo()` |
| `GET /api/staging/lock` | `shadow.get_lock_status()` |
| `POST /api/staging/lock/break` | `shadow.break_lock()` |
| `GET /api/staging/diff` | `get_changed_files()` + `get_file_diff()` |

**Removed endpoints:**
- `POST /api/staging` (save staging state) — mutations go through CRUD endpoints directly
- `GET /api/staging/virtual-tree` — parser reads shadow directly

**CRUD routes:** Object create/update/delete write to shadow via `file_operations.py`. Each mutation calls `snapshot_files()` before writing. Lock validated via `can_modify(session_id)`. First mutation auto-creates shadow.

**File/folder routes:** Operate directly on shadow directory. Same snapshot-before-mutate pattern.

**Backup routes:** Unchanged.

**Git routes:** Clear shadow on commit success. Read lock state from shadow manager.

### nagios_service.py Changes

**Remove (~800 lines):** Entire composite action system — `CompositeAction`, `_build_composite_actions`, `apply_object_composite`, `_exec_delete/edit/create`, `_exec_moves_batched`, all `apply_*` methods.

**Modify:** `create_object`, `update_object`, `delete_object` — repoint to write to shadow directory.

**Keep:** `_find_by_identity`, `_find_by_attrs`, `modification_context`, query methods, `_reload_parser_safe`, `_check_parser_state`.

### file_operations.py Changes

Remove `_compute_checksum()`. Strip `expected_checksum` parameter from `_read_file_content`, `edit_object_in_file`, `delete_object_from_file`, `add_object_to_file`.

### Stable Key Utilities

Extract `generate_stable_key`, `parse_stable_key`, `generate_stable_key_for_object` from `staging_manager.py` to `nagios_model.py` (or small `stable_keys.py`) before deletion.

### Frontend Simplification

**Core change:** Eliminate all client-side staging state. Server is single source of truth. Every mutation is an immediate API call.

**State removed from `Explorer.state`:**
- `pendingEdits`, `stagedMoves`, `stagedCreations`, `stagedObjectDeletions`, `stagedCreationDeletions`, `newFiles`
- `stagedFileCreations/Deletions/Moves`, `stagedFolderCreations/Deletions/Moves`
- `undoStack`, `currentStagingOwner`, `isEditingLocked`

**Files removed:** `static/js/lock-manager.js`

**Mutation flow:** `User action → API call → on success → rebuildUI() + updateBadges()`

**Module changes:**

| Module | Change |
|--------|--------|
| `data-loading.js` | Remove `saveStaging`, `loadStagedChanges`, `startStagingPoll`, `stopStagingPoll`, `checkPendingExternalChanges`, `syncStagingFromData`. Keep `updateBadges`. Simplify `afterFrontendMutation` to `rebuildUI() + updateBadges()`. |
| `state-management.js` | Remove `isObjectMarkedForDeletion`, `hasStagedChanges`, `resetStagingState`, `updateEditingLockedUI`, `canEdit`. |
| `object-editor.js` | `handleFieldChange` → immediate API call. `stageNewObjectChanges` → create API call. `stageObjectDeletions` → delete API call. Remove `removeStagedCreation`, `selectStagedCreationForEdit`. `renderCenterAttributes` reads from server. |
| `file-operations.js` | Remove local state mutations, `afterStagingChange` wrapper, `getFileStatus`, `getFolderStatus`, `hasStagedFileOperation`, `isNewFile`. Remove staging badges from `renderFileNode`/`renderFolderNode`. |
| `context-menu.js` | Remove `getOrCreatePendingEdit`, `canEdit()` guard. Bulk ops become batch API calls. |
| `badge-issues.js` | Remove entirely. Server validates shadow copy directly. |
| `app.js` | Remove `getEffectiveAttributes`/`getEffectiveName` overlays. Remove staging decorations from tree. Remove `loadStagedChanges`/`startStagingPoll` from init. |
| `tab-manager.js` | Remove `computeStagedIssues` call, pendingEdits dot indicator. |
| `commit-dialog.js` | Diff from `GET /api/staging/diff`. Remove `extractStagingArrays`, `hasFileOperations`, `hasGuiStagingChanges`, `buildFileChangesFromStaging`. `discardAllChanges` → `DELETE /api/staging`. |
| `base.js` | Counts from server. Remove `startLockPoll`, `break-lock` handler. |
| `base-state.js` | Remove `isEditingLocked`, `lockOwner`, lock-related fields. |
| `git.js` | Remove `stagingInfo`, `buildStagingPreviewHtml`. |
| `settings.js` | Remove lock checks. Remove `onLockCleared`. |
| `analysis-issues.js` | Creation/resolution → API calls instead of `state.stagedCreations.push()`. |
| `analysis-suggestions.js` | Template/group creation → API calls. |
| `impact-section.js` | Remove `overlayStagedTemplateEdits`. |

**UI behavior preserved:**
- Attribute editor: renders from shadow parser (no overlay needed)
- File tree: reflects shadow directory, with change indicators from `get_changed_files()`
- Object list: objects from shadow parser, diff indicators from server
- Health checks: server validates shadow config directly (more accurate than client-side)
- Suggestions: analyze shadow-parsed objects, create via API
- Change count badge: object-level count from server
- Diff view in commit dialog: from `GET /api/staging/diff`
- Undo: `POST /api/staging/undo`, count from `GET /api/staging/info`

### Audit Logging

- Each individual mutation audited (more granular than current batch-save approach)
- Apply audit simplified: files changed, objects added/modified/deleted, backup name, success/failure
- Undo audited: files restored, snapshot ID
- JSONL format, append-only, user identity from lock state — all unchanged

## Migration Strategy: Bottom-Up Replacement

1. **Build `ShadowCopyManager`** — test in isolation
2. **Rewire backend routes** — same API shape, shadow implementation behind them
3. **Simplify frontend** — remove client-side staging state
4. **Delete dead code** — remove old staging/composite/verification modules

Each phase produces a working, testable system.

## Files Removed Entirely

| File | Lines |
|------|-------|
| `staging_manager.py` (except stable key utils) | ~1600 |
| `apply_verification.py` | ~376 |
| `nagios_service.py` composite action system | ~800 |
| `routes/staging.py` (undo creation, staging data mgmt, apply infra, virtual overlay) | ~1200 |
| `static/js/lock-manager.js` | ~100 |
| `static/js/explorer/badge-issues.js` | ~200 |

**Estimated lines removed:** ~5000
**Estimated lines added:** ~500-700 (ShadowCopyManager + tests)

## Tests

**Remove:** `test_composite_apply.py`, `test_apply_robustness.py`, `test_apply_verification.py`

**Rewrite:** `test_staging_integration.py` → shadow copy lifecycle

**Keep:** `test_stable_keys.py`, `test_atomic_writes.py`, `test_backup_manager.py`

**Modify:** `test_move_ordering.py`

**New:** `test_shadow_copy_manager.py`, `test_shadow_crud.py`, `test_shadow_file_ops.py`, `test_shadow_apply.py`

## Documentation Updates

- `.claude/STAGING_REFERENCE.md` — rewrite for shadow copy
- `CLAUDE.md` staging section — update
- `templates/docs/staging-system.html` — rewrite in-app docs
- `templates/docs/data-flow-staging.html` — rewrite data flow docs

## Key Invariants Preserved

- Session-based locking (one editor at a time)
- `X-Session-Id` header for lock ownership
- `OperationResult` return convention
- Audit logging for all mutations
- Path safety validation via `is_safe_path`
- Parser reload after disk writes
- Backup system as safety net
