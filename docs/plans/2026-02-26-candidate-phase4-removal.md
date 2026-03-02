# Candidate Config — Phase 4: Old Staging Removal + E2E Verification

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove the old delta-based staging system (~5,100 lines) and run a comprehensive Playwright E2E test to verify the candidate config system works end-to-end.

**Architecture:** Surgical removal of old staging code, followed by full-stack E2E verification via Playwright MCP tools. The old staging system is dead code at this point — all functionality has been migrated to CandidateManager in Phases 1-3.

**Tech Stack:** Python, JavaScript, Playwright MCP, ruff, eslint

**Branch:** `feature/candidate-config` (continuing from Phase 3)

**Prerequisite:** Phase 3 must be complete including Playwright smoke test.

---

## Key Codebase Facts

| Fact | Detail |
|------|--------|
| **`NagiosService.__init__`** | Takes `(config_path, staging_manager=None)`. Staging manager is positional arg 2 — remove it |
| **Direct disk-write routes** | `files.py` has `/api/files/relocate`, `/api/folders/relocate`, `/api/delete` — these bypass staging and write to disk directly. Must be PRESERVED |
| **`bulk_ops.py` staging routes** | `api_apply_rename` and `api_move_objects` use `get_staging_manager()` — REMOVE these |
| **`bulk_ops.py` non-staging routes** | `api_search`, `api_preview_rename`, `api_diff_rename` — KEEP these |
| **`get_audit_user_identity()`** | In `routes/helpers.py:95`. Falls back to staging data for user identity — update to fall back to candidate session info |
| **`routes/backups.py`** | Imports `StagingStatus`, `get_staging_manager`. Uses staging lock check + `save_staging()` in restore route — must clean up |
| **`routes/git.py`** | Deep staging integration: `_check_staging_lock()`, `_resolve_user_identity()` (staging fallback), `_write_commit_audit_log()` (staging restore status), `api_git_identity_get/set()` (read/write staging data), staging lock checks in commit/discard/restore, `clear_staging()` after commit. **Largest route file change** |
| **`routes/settings.py`** | `_update_config_path()` creates `StagingManager` and registers in `app.extensions["staging"]` when switching config dirs — replace with `CandidateManager` |
| **`generate_stable_key_for_object()`** | Lives in `staging_manager.py`. Used by `NagiosService.find_object_by_stable_key()` and tests. Must be moved to `nagios_model.py` before deleting `staging_manager.py` |
| **`settings.js`** | Calls `/api/staging/lock` at 3 locations — not mentioned in Phase 3 and must be cleaned in Phase 4 |
| **Test files with staging imports** | `test_atomic_writes.py` (StagingManager), `test_stable_keys.py` (generate_stable_key_for_object), `test_reorder.py` (StagingManager + apply_object_composite), `test_health_check.py` (staging API calls) — all need cleanup or deletion |

---

## Prerequisites

**Step 1: Verify Phase 3 is complete**

```bash
cd .worktrees/candidate-config
python3 -m pytest tests/ -v
npm run lint:js
ruff check candidate_manager.py routes/candidate.py
```

Expected: all pass, 0 lint errors

---

## Task 1: Remove old staging backend

**Files to delete entirely:**
- `staging_manager.py` (~1,700 lines)
- `routes/staging.py` (~2,200 lines)
- `apply_verification.py` (~380 lines)
- `tests/test_staging_integration.py`
- `tests/test_composite_apply.py`
- `tests/test_apply_verification.py`
- `tests/test_apply_robustness.py` (bugs no longer possible with candidate model)
- `tests/test_reorder.py` (creates `StagingManager`, passes to `NagiosService`, calls `apply_object_composite()` — all removed)

**Files to delete partially (remove staging-only tests, keep remaining):**
- `tests/test_atomic_writes.py` — delete `TestStagingSaveAtomic` class (imports `StagingManager`, tests `save_staging()` round-trip). Keep `TestServerConfigSaveAtomic`.
- `tests/test_health_check.py` — delete `test_gitignore_references_correct_staging_dir()` (checks `.staging/` in gitignore) and `test_apply_staging_with_validate_flag()` (posts to `/api/staging` and `/api/staging/apply`). Keep all other health check tests.

**Files to modify (import cleanup only):**
- `tests/test_stable_keys.py` — `generate_stable_key_for_object` is imported from `staging_manager` (line 11). This function must be moved to `nagios_model.py` first (see below), then update the import.

**Function migration — `generate_stable_key_for_object()`, `generate_stable_key()`, and `parse_stable_key()`:** <!-- P4-B -->
- Currently in `staging_manager.py`. Also imported by `routes/bulk_ops.py` (line 12) and `tests/test_stable_keys.py` (line 11).
- The `bulk_ops.py` routes that use it (`api_apply_rename`, `api_move_objects`) are being removed — remove that import too.
- The function itself is still useful for stable key resolution (used by `NagiosService.find_object_by_stable_key()`). Move it to `nagios_model.py` before deleting `staging_manager.py`.
- **IMPORTANT (P4-B):** `generate_stable_key_for_object()` calls `generate_stable_key()` (the base helper at `staging_manager.py:1394`). All THREE functions must be moved together:
  - `generate_stable_key(source_file, object_type, name)` — the base function
  - `generate_stable_key_for_object(obj)` — convenience wrapper that calls `generate_stable_key()`
  - `parse_stable_key(key)` — parser
- Update all imports in `nagios_service.py`, `tests/test_stable_keys.py`, and any other surviving callers.

**Files to modify:**

**`nagios_service.py` — KEEP these methods:**
- `__init__` (remove `staging_manager` param)
- `reload()` — needed by `/api/reload` and after candidate apply
- `parser` property — read-only parser access
- `get_objects()` — used by analysis routes
- `edit_object()`, `delete_object()`, `add_object()`, `move_object()` — used by `file_operations.py` functions (called by CandidateManager)
- `health_check()` if it exists (check first)

**`nagios_service.py` — ALSO REMOVE (smart-grouping direct-write support):**
- `modification_context()` — was used by smart-grouping create/add-to-group routes which are being removed

**`nagios_service.py` — REMOVE these:**
- `_staging_manager` field and parameter
- `CompositeAction` dataclass
- `apply_object_composite()`, `_execute_composite_action()`
- All `_exec_*` methods
- `_build_composite_actions()`, `_resolve_insert_position()`, `_build_edit_detail()`, `_find_by_identity()`, `_find_by_attrs()`
- `get_typed_staging()`
- `apply_folder_creations()`, `apply_file_creations()`, `apply_file_moves()`, `apply_folder_moves()`, `apply_file_deletions()`, `apply_folder_deletions()`

**`app.py` — changes:**
- Remove `StagingManager` import and instantiation
- Remove `app.extensions["staging"]`
- Remove stale staging cleanup logic
- Remove `staging_manager` param from `NagiosService()` constructor call
- Keep `CandidateManager` registration (added in Phase 2)

**`routes/helpers.py` — changes:**
- Remove `get_staging_manager()`
- Update `get_audit_user_identity()` to not fall back to staging data (lines 106-113). Replace with candidate session info fallback:

```python
def get_audit_user_identity():
    data = request.get_json(silent=True) or {}
    user_name = data.get("user_name") or data.get("userName")
    user_email = data.get("user_email") or data.get("userEmail")

    if not user_name or not user_email:
        try:
            cm = get_candidate_manager()
            if cm.has_session():
                info = cm.get_session_info()
                user_name = user_name or info.get("user_name")
                user_email = user_email or info.get("user_email")
        except Exception as e:
            _logging.getLogger("nagios_bulk_editor.candidate").debug(
                "Could not fetch candidate session info for audit identity: %s", e,
            )

    return {"userName": user_name, "userEmail": user_email}
```

- **Remove `get_parser_for_modification()` (P4-E):** This helper wraps `NagiosService.modification_context()` which is being removed. However, `get_parser_for_modification()` is **still actively used** at 6 call sites:
  - `routes/objects.py:58` — `POST /api/delete-objects` (being removed in this task)
  - `routes/objects.py:163` — `POST /api/clone-objects` (being removed in this task)
  - `routes/files.py:404` — `POST /api/files/relocate` (being removed in this task)
  - `routes/files.py:457` — `POST /api/folders/relocate` (being removed in this task)
  - `routes/analysis.py:1356` — `POST /api/smart-grouping/create` (being removed in this task)
  - `routes/analysis.py:1405` — `POST /api/smart-grouping/add-to-group` (being removed in this task)

  **Dependency:** All 6 call-site routes must be removed BEFORE deleting `get_parser_for_modification()`. Since all 6 routes are being removed in this task (Steps 8-9), remove `get_parser_for_modification()` AFTER those route deletions. Verify no remaining callers with: `grep -rn "get_parser_for_modification" --include="*.py" routes/`

**`routes/__init__.py` — remove:**
- Staging blueprint import and registration

**`routes/objects.py` — REMOVE these direct-write routes (not wired to frontend, bypassed staging):**
- `POST /api/delete-objects` (`routes/objects.py:58`) — calls `write_objects_to_original_files()` directly. Replaced by `/api/candidate/delete-objects`
- `POST /api/clone-objects` (`routes/objects.py:163`) — calls `write_objects_to_original_files()` directly. Not wired to any frontend JS

**`routes/analysis.py` — REMOVE these direct-write routes (not wired to frontend, bypassed staging):**
- `POST /api/smart-grouping/create` (`routes/analysis.py:1341`) — calls `write_objects_to_original_files()` directly. The suggestions UI is read-only; if needed, should go through candidate
- `POST /api/smart-grouping/add-to-group` (`routes/analysis.py:1391`) — calls `write_objects_to_original_files()` directly. Same reason

**`routes/files.py` — KEEP these routes:**
- `GET /api/files` — read-only listing
- `GET /api/folders` — read-only listing

**`routes/files.py` — REMOVE these routes:**
- `POST /api/files/create` (staging)
- `POST /api/files/move` (staging)
- `POST /api/folders` create (staging)
- `POST /api/folders/move` (staging)
- `DELETE /api/files/<path>` (staging)
- `DELETE /api/folders/<path>` (staging)
- `POST /api/files/relocate` (`routes/files.py:404`) — calls `shutil.move()` on running .cfg files directly. Not wired to frontend. Replaced by `/api/candidate/file/move`
- `POST /api/folders/relocate` (`routes/files.py:457`) — calls `shutil.move()` on running folders directly. Not wired to frontend. Replaced by `/api/candidate/folder/move`
- `POST /api/delete` (batch delete) — calls `os.remove()` / `shutil.rmtree()` on running config directly. Not wired to frontend
- `ensure_staging_lock()` helper

**`routes/bulk_ops.py` — KEEP these routes:**
- `POST /api/search` — not staging-related
- `POST /api/preview-rename` — not staging-related
- `POST /api/diff/rename` — not staging-related

**`routes/bulk_ops.py` — REMOVE these routes:**
- `POST /api/apply-rename` — uses staging manager
- `POST /api/move-objects` — uses staging manager

**Note:** The bulk rename and move functionality should be re-implemented using CandidateManager in a future iteration if needed. For now, the candidate bulk-edit and bulk-move routes cover the core use case.

**`routes/backups.py` — remove staging imports and lock logic:**
- Remove `from staging_manager import StagingStatus` (line 9)
- Remove `get_staging_manager` from helpers import (line 16)
- In `api_restore_backup()`: remove staging lock check (lines 63-70: `staging_mgr = get_staging_manager()`, `lock_owner` check) and staging lock creation (lines 84-94: `staging_mgr.save_staging({...})` with `StagingStatus.RESTORE_PENDING`). The candidate guard added in Task 5 replaces this.

After cleanup, `api_restore_backup()` should be:
```python
@bp.route("/api/backups/<backup_name>/restore", methods=["POST"])
def api_restore_backup(backup_name):
    """Restore from a backup."""
    logger.info("Restore backup: backup_name=%s", backup_name)
    blocked = guard_candidate_or_abort()
    if blocked:
        return blocked

    data = request.get_json() or {}
    bm = get_backup_manager()
    try:
        user_name = data.get("userName", "")
        user_email = data.get("userEmail", "")

        result = bm.restore_backup(backup_name, user_name=user_name, user_email=user_email)
        get_service().reload()

        identity = get_audit_user_identity()
        log_audit(
            action="backup_restored",
            user=format_audit_user(identity),
            backup_name=backup_name,
        )

        return jsonify({"success": True, **result})
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
```

Updated imports:
```python
from .helpers import (
    format_audit_user,
    get_audit_user_identity,
    get_backup_manager,
    get_service,
    guard_candidate_or_abort,
)
```

**`routes/git.py` — extensive staging cleanup (BIGGEST route file change):**
- Remove `from staging_manager import StagingStatus` (line 9)
- Remove `get_staging_manager` from helpers import (line 17)
- **DELETE** `_check_staging_lock()` helper (lines 24-43) — replaced by `guard_candidate_or_abort()` on destructive routes
- **REWRITE** `_resolve_user_identity(data)` (lines 46-63) — remove staging fallback, use candidate session info:

```python
def _resolve_user_identity(data):
    """Resolve user identity from request body, falling back to candidate session.

    Returns:
        Tuple of (user_name, user_email) - either may be None.
    """
    user_name = data.get("user_name", "").strip() if data.get("user_name") else None
    user_email = data.get("user_email", "").strip() if data.get("user_email") else None

    if not user_name or not user_email:
        try:
            cm = get_candidate_manager()
            if cm.has_session():
                info = cm.get_session_info()
                user_name = user_name or info.get("user_name")
                user_email = user_email or info.get("user_email")
        except Exception:
            pass

    return user_name, user_email
```

- **REWRITE** `_write_commit_audit_log()` (lines 82-100) — remove staging restore status lookup:

```python
def _write_commit_audit_log(commit_hash, message, user_name, user_email, initialized):
    """Write audit log entry for a git commit."""
    user = format_audit_user(name=user_name, email=user_email)
    if initialized:
        log_audit(
            action="git_initialized", user=user,
            commit_hash=commit_hash, message=message,
        )
        return
    log_audit(action="git_commit", user=user, commit_hash=commit_hash, message=message)
```

- **REWRITE** `api_git_identity_get()` (lines 103-134) — read from candidate session instead of staging:

```python
@bp.route("/api/git/identity", methods=["GET"])
def api_git_identity_get():
    """Get the identity of the current editing session owner.

    Returns the userName and userEmail from the active candidate session.
    """
    try:
        cm = get_candidate_manager()
        if not cm.has_session():
            return jsonify({
                "user_name": "",
                "user_email": "",
                "is_configured": False,
                "has_lock": False,
            })

        info = cm.get_session_info()
        user_name = info.get("user_name", "")
        user_email = info.get("user_email", "")

        return jsonify({
            "user_name": user_name,
            "user_email": user_email,
            "is_configured": bool(user_name and user_email),
            "has_lock": True,
        })

    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500
```

- **REWRITE** `api_git_identity_set()` (lines 137-173) — frontend `settings.js:251` actively calls `POST /api/git/identity`. Rewire to update the candidate session identity instead of staging data:

```python
@bp.route("/api/git/identity", methods=["POST"])
def api_git_identity_set():
    """Update the identity stored in the active candidate session."""
    data = request.get_json(silent=True) or {}
    user_name = data.get("userName", "").strip()
    user_email = data.get("userEmail", "").strip()

    cm = get_candidate_manager()
    if cm.is_active():
        session_data = cm.get_session_data()
        session_data["user_name"] = user_name
        session_data["user_email"] = user_email
        cm.save_session_data(session_data)
        return jsonify({"success": True})

    # No active candidate session — just acknowledge
    return jsonify({"success": True})
```
- **UPDATE** `api_git_commit()` — remove `_check_staging_lock()` call (line 259) and `get_staging_manager().clear_staging()` call (line 320). Commit no longer needs to check staging lock or clear staging — candidate apply already happened before commit.
- **UPDATE** `api_git_discard()` — remove `_check_staging_lock()` call (line 356). Add `guard_candidate_or_abort()` (added in Task 5).
- **UPDATE** `api_git_discard_all()` — remove `_check_staging_lock()` call (line 388). Add `guard_candidate_or_abort()` (added in Task 5).
- **UPDATE** `api_git_clear_history()` — remove `_check_staging_lock()` call (line 428). This is a destructive operation; add `guard_candidate_or_abort()`.
- **UPDATE** `api_git_restore()` — remove staging lock check (lines 514-521) and staging lock creation (lines 547-559: `sm.save_staging({...})` and `sm.clear_staging()`). Add `guard_candidate_or_abort()` (added in Task 5).

Updated imports:
```python
from .helpers import (
    format_audit_user,
    get_audit_user_identity,
    get_candidate_manager,
    get_config_path,
    get_git_service,
    get_service,
    guard_candidate_or_abort,
)
```

**`routes/settings.py` — remove StagingManager re-creation:**
- In `_update_config_path()` (lines 85-107): remove `from staging_manager import StagingManager` import (line 89), remove `new_staging = StagingManager(normalized_path)` (line 94), remove `new_staging` param from `NagiosService()` call (line 95), remove `current_app.extensions["staging"] = new_staging` (line 102).
- Create `CandidateManager` instead if the app factory registers one. Check Phase 2 for how `candidate_manager` is registered in `app.extensions`.

After cleanup:
```python
def _update_config_path(server_config, path, updated, errors):
    if not os.path.isdir(path):
        errors.append(f"Invalid directory: {path}")
        return

    import file_operations
    from backup_manager import BackupManager
    from candidate_manager import CandidateManager
    from git_service import GitService
    from nagios_service import NagiosService

    normalized_path = os.path.abspath(path)

    try:
        new_service = NagiosService(normalized_path)
        _ = new_service.parser  # Force init to catch config errors early
        new_candidate = CandidateManager(normalized_path)
        new_backup = BackupManager(normalized_path, server_config.backup_path)
        new_git = GitService(normalized_path)

        server_config.paths.nagios_config_path = normalized_path
        current_app.extensions["service"] = new_service
        current_app.extensions["candidate"] = new_candidate
        current_app.extensions["backup"] = new_backup
        current_app.extensions["git"] = new_git
        updated.append("nagios_config_path")
    except Exception as e:  # noqa: BLE001
        errors.append(f"Failed to initialize services for path: {e}")
```

**`backup_manager.py` — update error messages (P4-C):**
- Line 271: Change `"1. Clear staging lock: DELETE /api/staging"` to `"1. Discard candidate session: DELETE /api/candidate"`
- Line 308: Change `"Recovery: DELETE /api/staging to clear lock, then POST /api/backups/<safety_backup>/restore"` to `"Recovery: DELETE /api/candidate to discard session, then POST /api/backups/<safety_backup>/restore"`

**`git_service.py` — clean up staging references (P4-D):**
- `git_service.py:281-282` — Replace `".staging/", ".staging"` with `".candidate/", ".candidate"` in `get_status()` default excluded_paths
- `git_service.py:452` — Same for `get_combined_diff()`
- `git_service.py:788` — In `init_repo()`, change `.gitignore` entry from `.staging/` to `.candidate/`
- `tests/test_git_service.py:159` — Update assertion from `assert ".staging/" in gitignore` to `assert ".candidate/" in gitignore`

**`nagios_parser.py` — remove dead `.staging/` exclusion (P4-H):**
- Line 66 has: `if "/.staging/" in file_path or "/.nagios_staging/" in file_path: continue`
- **NOTE:** This code only becomes dead AFTER confirming no code creates `.staging/` directories anymore. Since Phase 4 removes `staging_manager.py` (the only code that creates `.staging/`), this exclusion is safe to remove. However, verify first: `grep -rn '\.staging/' --include="*.py" . | grep -v docs/plans | grep -v nagios_parser.py` — should return no matches that create `.staging/` directories.
- The `.candidate/` exclusion added in Phase 1 (Task 2) already covers the new system, so remove the `.staging/` and `.nagios_staging/` checks.

**Step 1: Move `generate_stable_key()`, `generate_stable_key_for_object()`, and `parse_stable_key()` to `nagios_model.py`** <!-- P4-B -->

Before deleting `staging_manager.py`, move all three functions to `nagios_model.py` so surviving code can still use them. The base function `generate_stable_key()` must be moved alongside the other two because `generate_stable_key_for_object()` depends on it. Update all imports:
- `nagios_service.py`: change `from staging_manager import ...` to `from nagios_model import ...`
- `tests/test_stable_keys.py`: change import source

```bash
ruff check nagios_model.py nagios_service.py tests/test_stable_keys.py
python3 -m pytest tests/test_stable_keys.py -v
```

Expected: pass

**Step 2: Delete files**

```bash
rm staging_manager.py
rm apply_verification.py
rm routes/staging.py
rm tests/test_staging_integration.py
rm tests/test_composite_apply.py
rm tests/test_apply_verification.py
rm tests/test_apply_robustness.py
rm tests/test_reorder.py
```

**Step 3: Clean up test files with partial staging references**

`tests/test_atomic_writes.py` — delete the entire `TestStagingSaveAtomic` class (lines 12-40). Keep `TestServerConfigSaveAtomic` (lines 44-80).

`tests/test_health_check.py` — delete `test_gitignore_references_correct_staging_dir()` (lines 136-149) and `test_apply_staging_with_validate_flag()` (lines 639-end). Keep all other health check tests.

**Step 4: Clean up nagios_service.py**

Remove all staging-related methods and imports. Keep only the core CRUD methods (`edit_object`, `delete_object`, `add_object`, `move_object`, `reload`, parser access) that CandidateManager delegates to via `file_operations.py`.

**Step 5: Clean up app.py**

Remove `StagingManager` import, instantiation, stale cleanup, and `app.extensions["staging"]`.

**Step 6: Clean up routes/helpers.py**

Remove `get_staging_manager()`. Remove `get_parser_for_modification()` (P4-E) — but only AFTER the routes that call it are removed in Steps 8-9. Verify no remaining callers: `grep -rn "get_parser_for_modification" --include="*.py" routes/`

**Step 7: Clean up routes/__init__.py**

Remove staging blueprint import and registration.

**Step 8: Clean up routes/files.py, routes/objects.py, routes/analysis.py, and routes/bulk_ops.py**

Remove staging-specific endpoints and helpers. Remove `generate_stable_key_for_object` import from `bulk_ops.py` (only used by the removed `api_apply_rename` and `api_move_objects`).

Remove the direct-write routes from `routes/objects.py` (`POST /api/delete-objects`, `POST /api/clone-objects`) and `routes/analysis.py` (`POST /api/smart-grouping/create`, `POST /api/smart-grouping/add-to-group`).

Remove all staging routes and the direct-write routes from `routes/files.py` (`POST /api/files/relocate`, `POST /api/folders/relocate`, `POST /api/delete`).

**Step 9: Clean up routes/backups.py**

Remove `from staging_manager import StagingStatus`, remove `get_staging_manager` import. In `api_restore_backup()`: remove staging lock check and `save_staging()` call. Replace with `guard_candidate_or_abort()` (see code above). The candidate guard is simpler: if a candidate session is active, block; otherwise allow.

**Step 10: Clean up routes/git.py**

This is the **largest route file change**. Remove all staging imports, delete `_check_staging_lock()`, rewrite `_resolve_user_identity()` and `_write_commit_audit_log()` to use candidate session instead of staging data, rewrite `api_git_identity_get()` to read from candidate session, delete `api_git_identity_set()` (or make it a no-op), remove `_check_staging_lock()` calls from commit/discard/restore/clear-history, remove `get_staging_manager().clear_staging()` from commit success path, remove staging lock creation from git restore. See code above for exact replacements.

**Step 11: Clean up routes/settings.py**

In `_update_config_path()`: remove `from staging_manager import StagingManager`, remove `new_staging = StagingManager(...)`, remove `current_app.extensions["staging"] = new_staging`. Replace with `CandidateManager` creation and registration. See code above.

**Step 12: Update backup_manager.py error messages** <!-- P4-C -->

Update the two error messages referencing `DELETE /api/staging` to reference `DELETE /api/candidate` instead. See P4-C details above.

**Step 13: Clean up git_service.py staging references** <!-- P4-D -->

Replace `.staging/` with `.candidate/` in `get_status()` default excluded_paths, `get_combined_diff()`, and `init_repo()` `.gitignore` entry. Update `tests/test_git_service.py` assertion. See P4-D details above.

**Step 14: Remove nagios_parser.py dead `.staging/` exclusion** <!-- P4-H -->

Remove the `.staging/` and `.nagios_staging/` exclusion at line 66. Verify no code still creates `.staging/` directories first. See P4-H details above.

**Step 15: Run tests**

```bash
python3 -m pytest tests/ -v
```

Expected: all remaining tests pass. The deleted test files are gone; no existing test should import from staging_manager.

**Step 16: Lint and commit**

```bash
ruff check nagios_model.py nagios_service.py app.py routes/helpers.py routes/__init__.py routes/files.py routes/objects.py routes/analysis.py routes/bulk_ops.py routes/backups.py routes/git.py routes/settings.py backup_manager.py git_service.py nagios_parser.py tests/test_atomic_writes.py tests/test_health_check.py tests/test_stable_keys.py tests/test_git_service.py
ruff format --check nagios_model.py nagios_service.py app.py routes/helpers.py routes/__init__.py routes/files.py routes/objects.py routes/analysis.py routes/bulk_ops.py routes/backups.py routes/git.py routes/settings.py backup_manager.py git_service.py nagios_parser.py tests/test_atomic_writes.py tests/test_health_check.py tests/test_stable_keys.py tests/test_git_service.py
git add -A
git commit -m "refactor: remove old delta-based staging system (replaced by candidate config)"
```

---

## Task 2: Remove old staging frontend

**Files to modify:**

**`static/js/explorer/main.js` — remove from `Explorer.state`:**
- `pendingEdits`, `stagedMoves`, `stagedCreations`, `stagedObjectDeletions`
- `stagedCreationDeletions`, `newFiles`
- `stagedFileCreations`, `stagedFileDeletions`, `stagedFileMoves`
- `stagedFolderCreations`, `stagedFolderDeletions`, `stagedFolderMoves`
- `undoStack` (undo is now server-side via git)
- `externalChangePending`
- `selectedStagedIndices`

**`static/js/explorer/state-management.js` — remove:**
- `getPendingEdit()`, `setPendingEdit()` functions
- Any `saveStagedChanges()`, `loadStagedChanges()`, `syncStagingFromData()` functions

**`static/js/explorer/data-loading.js` — remove:**
- Staging sync/polling (non-candidate path of `startStagingPoll`)
- `loadVirtualTree()` (no longer needed — candidate objects ARE the tree)

**`static/js/explorer/context-menu.js` — remove:**
- `getOrCreatePendingEdit()` helper
- All staging map manipulation (`stagedMoves.set()`, `stagedObjectDeletions.add()`, etc.)

**`static/js/explorer/dialogs.js` — remove:**
- Staging-specific dialog content (staged changes count, etc.)

**`static/js/explorer/object-editor.js` — remove:**
- `pendingEdits` map manipulation
- Old staging save path

**`static/js/explorer/file-operations.js` — remove:**
- Old staging file/folder operation stagers
- Non-candidate path of `afterStagingChange()`

**`static/js/base.js` — remove and rewrite:** <!-- P4-A -->
- Old staging undo path
- **CRITICAL (P4-A): `checkPendingChanges()` must be fully rewritten** — it currently calls `/api/staging/info` on every page to determine if changes are pending. Rewrite to call `/api/candidate` and `/api/candidate/diff` instead. Phase 3, Task 4 partially addressed this with candidate branches, but Phase 4 must verify the rewrite is complete and ALL staging fallback paths are removed. The candidate-only version should:
  1. Call `GET /api/candidate` to check if a session is active
  2. If active, call `GET /api/candidate/diff` to get changed file count
  3. Update the commit button badge with the count
  4. If no session, clear the badge
- Remove all staging else-paths — the `if (state.candidateActive)` branch becomes the only code path.

**`static/js/commit-dialog.js` — remove and rewrite:** <!-- P4-A -->
- **CRITICAL (P4-A): `showGlobalCommitDialog()` must be fully rewritten** — it currently loads diff data from `/api/staging/diff` and renders staging-specific UI. Rewrite to load from `/api/candidate/diff` and `/api/candidate/analyze-references`. Phase 3, Task 4 partially addressed this, but Phase 4 must verify:
  1. Diff data is loaded from `CandidateApi.getDiff()` (not `/api/staging/diff`)
  2. Changed files list renders from candidate diff response format
  3. Reference analysis (if any) uses candidate endpoints
  4. Apply button calls `CandidateApi.apply()` (not `/api/staging/apply`)
  5. All staging-specific UI rendering is removed
- Remove all staging fallback paths — the candidate path is now the only code path.

**`static/js/explorer/analysis.js` — remove staging state references:**
- `state.stagedObjectDeletions.has()` checks (lines 231, 315) — skip deleted objects in suggestions
- `state.stagedObjectDeletions.add()` calls (lines 746, 990, 1052) — these now go through CandidateApi
- `state.pendingEdits` references (lines 1315, 1329)
- Phase 3 added candidate branches; remove the old staging else-paths

**`static/js/explorer/badge-issues.js` — remove staging state references:**
- `state.pendingEdits.size` check (line 113)
- `state.pendingEdits` iteration for renames map (line 125)
- `state.stagedObjectDeletions` filtering (line 149)
- `state.pendingEdits` iteration in `buildEditedTemplatesMap()` (line 243)

**`static/js/explorer/analysis-suggestions.js` — remove staging state references:**
- `state.stagedCreations.push()` calls (lines 358, 472) — staging new objects
- `state.stagedCreations.length` / `.find()` checks (lines 365, 465)
- `state.pendingEdits.set()` calls (line 381)
- `Explorer.saveStagedChanges()` calls (lines 396, 486)

**`static/js/explorer/impact-section.js` — remove staging state references:**
- `state.pendingEdits.get()` check (line 215) — checking if template has pending edits

**`static/js/explorer/tab-manager.js` — remove staging state references:**
- `state.pendingEdits.has()` check (line 254) — checking if tab has pending edit

**`static/js/explorer/app.js` — remove staging state references:**
- `state.pendingEdits.size` and `state.stagedCreations.length` checks (lines 347-348, 361-362) — commit dialog gating
- `state.stagedMoves.has()` for tree item CSS class (line 1008)
- `getEffectiveAttributes()` / `getEffectiveName()` helpers (lines 850-877) that read from pendingEdits — replace with direct attribute access (candidate objects already have the latest attributes)

**`static/js/settings.js` — remove staging lock calls:**
- `ApiClient.get('/api/staging/lock')` calls at lines 249, 262, 446 — replace with candidate session status check via `ApiClient.get('/api/candidate')` or remove the lock-gating entirely (candidate guard on backend handles conflicts)

**`static/js/git.js` — remove staging diff reference (P4-F):**
- `static/js/git.js:48` calls `ApiClient.get('/api/staging/diff')`. Remove this call and the `buildStagingPreviewHtml()` rendering. Replace with candidate diff if session is active, or remove the section entirely.

**`session-manager.js` — rename `getStagingHeaders()` (P4-J):**
- Rename `getStagingHeaders()` at `session-manager.js:62` to `getSessionHeaders()`. This function is called by `ApiClient` on every request and the name is misleading now that staging is gone. Update:
  - `session-manager.js`: function definition
  - `api-client.js:82`: the call site
  - `eslint.config.mjs`: the global declaration (see P4-I below)

**`eslint.config.mjs` — update globals (P4-I):**
- Rename `getStagingHeaders` global to `getSessionHeaders` (matches P4-J rename)
- Rename or remove `discardStagingAfterFailedCommit` — if rewritten per P3-I, rename to `discardCandidateAfterFailedCommit`; if the function was fully replaced by the candidate apply+commit flow, remove the global entirely

**Step 1: Remove all staging references from JS**

For each file listed above, remove the dead staging code paths. The `if (state.candidateActive)` branches become the only code path. For files without explicit candidate branches (tab-manager, app.js, settings.js), remove the staging references and use candidate-aware alternatives where needed.

**Step 2: Rename getStagingHeaders() to getSessionHeaders()** <!-- P4-J -->

Update the function name in `session-manager.js`, its call site in `api-client.js`, and the global declaration in `eslint.config.mjs`.

**Step 3: Remove dead CSS classes from JS-referenced staging selectors** <!-- P4-K -->

After removing staging JS code, grep for any remaining JS references to staging CSS classes (`.staged-creation`, `.staged-for-deletion`, etc.) and remove them. The CSS class removal itself happens in Task 3 (documentation/cleanup), but JS references to those classes must be removed here.

Also remove `static/css/git.css:738-810` staging preview classes (`.git-staging-preview`, `.git-staging-preview-header`, etc.) — these are orphaned after the git.js staging preview is removed (P4-F).

**Step 4: Lint**

```bash
npm run lint:js
```

Fix any errors.

**Step 5: Run Python tests**

```bash
python3 -m pytest tests/ -v
```

**Step 6: Commit**

```bash
git add -A
git commit -m "refactor: remove old staging frontend code (candidate-only paths)"
```

---

## Task 3: Update documentation

**Files:**
- Delete: `.claude/STAGING_REFERENCE.md`
- Delete: `templates/docs/staging-system.html` (entire page about old staging system)
- Delete: `templates/docs/data-flow-staging.html` (staging data flow diagrams)
- Create: `.claude/CANDIDATE_REFERENCE.md`
- Modify: `CLAUDE.md`
- Modify: `routes/CLAUDE.md`
- Modify: `.claude/API_REFERENCE.md`
- Modify: `.claude/ROUTES_REFERENCE.md`
- Modify: `static/js/CLAUDE.md`
- Modify: `static/js/explorer/CLAUDE.md`
- Modify: `templates/CLAUDE.md`
- Modify: `.claude/DECISION_LOG.md`
- Modify: `templates/base.html` — update lock banner text from "pending changes" to "active editing session" language
- Modify: other doc templates that reference staging (api-reference.html, backend-services.html, frontend-architecture.html, bulk-operations.html, explorer-navigation.html, git-integration.html, quick-start.html, editing-objects.html, file-folder-management.html) — replace "staging" terminology with "candidate" where appropriate
- Clean: `static/css/explorer.css` — remove dead staging CSS classes (~25 classes: `.staged-creation`, `.staged-for-deletion`, `.staged-count`, `.staged-indicator`, `.staged-indicator--new/delete/move`, `.tree-item-staged-badge`, `.tree-label--staged`, `.tree-count--pending`, `.workspace-object-row.staged-creation`, `.staged-deletion`, `.context-menu.staged-context`, `.workspace-tree-row.staged-new/staged-deletion/staged-move`)
- Clean: `static/css/git.css` — remove dead staging CSS classes (~15 classes: `.git-file-item.staged-item`, `.git-status-badge.staged`, `.staged-item-*`, `.staged-detail-*`)

### Step 1: Delete obsolete documentation and CSS <!-- P4-K -->

```bash
rm .claude/STAGING_REFERENCE.md
rm templates/docs/staging-system.html
rm templates/docs/data-flow-staging.html
```

Remove dead CSS from `static/css/explorer.css` — delete all `.staged-*`, `.tree-item-staged-*`, `.tree-label--staged`, `.tree-count--pending`, `.staged-indicator*`, `.context-menu.staged-context`, `.workspace-tree-row.staged-*`, `.workspace-object-row.staged-creation` rules.

Remove dead CSS from `static/css/git.css` — delete all `.staged-item*`, `.staged-detail-*`, `.git-file-item.staged-item`, `.git-status-badge.staged`, `.git-staging-preview*` rules.

Update `templates/base.html` lock banner — change "Another user has pending changes" to "Another user is currently editing" (or similar candidate-appropriate text).

Update doc templates that reference staging — search for "staging" in `templates/docs/*.html` and replace with candidate terminology where appropriate. Key files: `api-reference.html`, `backend-services.html`, `frontend-architecture.html`, `bulk-operations.html`, `explorer-navigation.html`, `git-integration.html`, `editing-objects.html`, `file-folder-management.html`. Use judgment — some references may be in architecture history sections that should be updated, others may need full paragraph rewrites.

**Additional documentation templates (P4-L):** <!-- P4-L -->
The following templates have substantial staging content that must be updated. **NOTE:** Line numbers are approximate — the implementer should `grep -rn "staging" templates/docs/` to find ALL staging references rather than targeting specific lines:
1. `templates/docs/contributing.html` — references `get_staging_info`, staging route patterns, `ApiClient.post('/api/staging')`
2. `templates/docs/overview.html` — describes the staging system (architecture section)
3. `templates/docs/validation.html` — references staging

Update all to describe the candidate system instead.

### Step 2: Create CANDIDATE_REFERENCE

Create `.claude/CANDIDATE_REFERENCE.md`:

```markdown
# Candidate Config Reference

## Overview

The candidate config system replaces the old delta-based staging system. When a user starts editing, the running config is copied to `.candidate/`. Each edit modifies files directly in the candidate directory. Git tracks undo history. Apply copies candidate back over running config.

## Lifecycle

```
NO SESSION ──(first edit → auto-init)──> ACTIVE ──(apply/discard)──> NO SESSION
```

- **NO SESSION**: No `.candidate/` directory exists. Editing available.
- **ACTIVE**: `.candidate/` contains a git repo with modified config files. One session owns the lock.

## Architecture

```
CandidateManager (candidate_manager.py)
├── init_session()     → copytree + git init + baseline commit
├── edit_object()      → file_operations.edit_object_in_file() + git commit
├── delete_object()    → file_operations.delete_object_from_file() + git commit
├── create_object()    → file_operations.add_object_to_file() + git commit
├── move_object()      → file_operations.move_object_between_files() + git commit
├── bulk_edit()        → multiple edits + single git commit
├── bulk_delete()      → multiple deletes (bottom-to-top) + single git commit
├── bulk_move()        → multiple moves + single git commit
├── undo()             → git reset --hard HEAD~1
├── get_diff()         → git diff baseline..HEAD + file comparison
├── detect_conflicts() → compare running checksums vs baseline
├── validate()         → nagios -v on .validation-nagios.cfg
├── apply()            → copy candidate → running, delete .candidate/
└── discard()          → delete .candidate/
```

## Session Lock

- **Session-based**: Only one session can edit at a time
- **Auto-init**: First edit from frontend auto-creates session via `CandidateApi.ensureSession()`
- **Lock check**: `cm.can_modify(session_id)` — reads `X-Session-Id` header
- **Force discard**: `DELETE /api/candidate?force=1` bypasses session check (admin break lock)

Lock check pattern (routes):
```python
session_id = request.headers.get("X-Session-Id", "")
if not cm.can_modify(session_id):
    return jsonify({"success": False, "error": "Locked by another user"}), 423
```

## Path Translation

Frontend always uses running-config paths. Backend translates:
- **Inbound** (frontend → backend): `cm.to_candidate_path(running_path)` before file ops
- **Outbound** (backend → frontend): `cm.to_running_path(candidate_path)` in GET responses

## Undo

Each edit = one git commit in `.candidate/`. Undo = `git reset --hard HEAD~1`.
- Undo count: `git rev-list --count HEAD` minus 1 (baseline commit)
- Undo returns the commit message (operation description)

## Conflict Detection

Baseline checksums stored in `.candidate/.session.json` at init time. `detect_conflicts()` compares current running-config checksums against baseline.

## Nagios Validation

`init_session()` creates `.candidate/.validation-nagios.cfg` with all path directives (`cfg_file`, `cfg_dir`, `resource_file`, etc.) rewritten to point into `.candidate/`. Also creates `var/` subdirectories needed by `nagios -v`.

## Apply

1. Compute deletion list (running files missing from candidate)
2. Copy candidate files → running config (skipping `.git/`, `var/`, `.session.json`, `.validation-*`, `.gitkeep`)
3. Delete running files not in candidate
4. Remove `.candidate/` directory
5. Caller (route) creates backup before apply and reloads NagiosService parser after

## Excluded from Candidate Copy

These are never copied from running → candidate or candidate → running:
- `.candidate/`, `.staging/`, `.git/`, `backups/`, `__pycache__`
- `.session.json`, `.validation-nagios.cfg`, `.gitkeep`, `var/`

## Commit Workflow

```
User edits objects (auto-inits candidate session)
    ↓
User clicks Commit button
    ↓
commit-dialog.js: showGlobalCommitDialog()
    ↓
CandidateApi.getDiff() → shows changed files + unified diff
    ↓
User enters message, clicks "Apply + Commit"
    ↓
CandidateApi.apply() → copies candidate → running, cleans up
    ↓
POST /api/git/commit {message, user_name, user_email}
    ↓
Show git result panel
```
```

```bash
git add -A .claude/STAGING_REFERENCE.md .claude/CANDIDATE_REFERENCE.md
git commit -m "docs: replace STAGING_REFERENCE with CANDIDATE_REFERENCE"
```

### Step 3: Replace root `CLAUDE.md` <!-- P4-G -->

Replace the entire file with (P4-G: all staging references updated to candidate):

```markdown
# CLAUDE.md

## Setup

```bash
pip install -r requirements.txt
python3 app.py
# Access at http://localhost:8080
```

Dependencies: `flask>=2.0.0,<4.0.0`

## Documentation Index

**Reference docs** (`.claude/`): ROUTES_REFERENCE.md, API_REFERENCE.md, CANDIDATE_REFERENCE.md, GIT_REFERENCE.md, FILE_OPS_REFERENCE.md, TYPOGRAPHY_REFERENCE.md, DECISION_LOG.md

**Module docs**: routes/CLAUDE.md, templates/CLAUDE.md, static/css/CLAUDE.md, static/js/CLAUDE.md, static/js/explorer/CLAUDE.md

## Backend Architecture

### App Factory (app.py)

Services stored in `app.extensions`, accessed via helpers:

```python
from .helpers import get_service, get_candidate_manager, get_backup_manager, get_server_config
```

### Thread Safety

`multiprocessing.Lock` (not `threading.Lock`) — WSGI servers may use multiple processes.
- **NagiosService**: Lock for all mutations
- **CandidateManager**: Lock for session lifecycle and object operations
- **GitService**: Lock for multi-step mutations

### OperationResult

All service methods return `OperationResult(success: bool, error: str = None, data: Any = None)`.

### Server Configuration

`config/settings.json`. Precedence: env vars > config file > defaults.

## Backend Module Index

| Module | What |
|--------|------|
| `app.py` | App factory, service init |
| `server_config.py` | Config load/save, env overrides |
| `nagios_service.py` | CRUD operations, parser access |
| `candidate_manager.py` | Candidate config: session lifecycle, edits, undo, diff, apply |
| `backup_manager.py` | Zip backups, restore |
| `nagios_parser.py` | Parse .cfg files |
| `nagios_writer.py` | Write .cfg files |
| `nagios_model.py` | NagiosObject, NAME_FIELDS, REFERENCE_FIELDS, domain constants |
| `file_operations.py` | Atomic file ops, path safety |
| `git_service.py` | Git wrapper, retry logic |
| `validator.py` | nagios -v validation |
| `audit_service.py` | JSON audit log (append-only JSONL) |

## Domain Metadata

All Nagios domain constants are defined in `nagios_model.py` and served via `GET /api/metadata`. The frontend fetches once at startup into `Explorer.constants`. **Never hardcode domain metadata in JavaScript.**

To add a new object type or reference field: update `nagios_model.py` — frontend picks it up automatically.

## Candidate Config System

Candidate config model: edits happen on a copy (`.candidate/`), apply writes back. See `.claude/CANDIDATE_REFERENCE.md`.

- **Auto-init**: First edit auto-creates candidate session (no manual "Start Editing" button)
- **Lock**: Session-based. Check: `cm.can_modify(session_id)`.
- **Undo**: Each edit = git commit in `.candidate/`. Undo = `git reset --hard HEAD~1`.
- **Path translation**: Frontend uses running paths; backend translates to/from candidate paths.

## Error Handling

**HTTP status codes:** 200 (success), 400 (invalid input), 404 (not found), 409 (candidate conflicts), 423 (locked), 500 (internal error)

**Backup on mutation:** `bm.create_backup("pre_operation_name")` before any write.

## Conventions

- **Python**: snake_case | **JavaScript**: camelCase | **CSS classes**: kebab-case | **CSS variables**: `--nbe-*`
- **API ↔ Frontend**: API returns snake_case; frontend preserves API field names in requests
- **Event delegation**: `data-action` attributes → `actionHandlers` map in `base.js`
- **API calls**: `ApiClient.get/post()` → `{success, data, error}`
```

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for candidate config system"
```

### Step 4: Replace `routes/CLAUDE.md`

Replace the entire file with:

```markdown
# Routes

Flask blueprints registered in `__init__.py`. Service access via `helpers.py`.

## Module Index

| Module | Routes |
|--------|--------|
| `pages.py` | GET /, /explorer, /backups, /git, /settings, /validate, etc. |
| `objects.py` | GET /api/objects |
| `candidate.py` | POST /api/candidate/init, GET /api/candidate, DELETE, /edit, /undo, /diff, /apply |
| `files.py` | GET /api/files, GET /api/folders |
| `bulk_ops.py` | POST /api/search, /api/preview-rename, /api/diff/rename |
| `git.py` | GET /api/git/status, POST /api/git/commit, /restore, GET /api/git/log |
| `backups.py` | GET/POST /api/backups, POST /api/backups/<name>/restore, DELETE |
| `analysis.py` | GET /api/dependencies, /inheritance, /object-references, /escalation-path, POST /api/smart-grouping/suggest |
| `templates.py` | GET /api/templates, /inheritance/<key>, /validate-use |
| `metadata.py` | GET /api/metadata |
| `validation.py` | POST /api/reload, /validate, GET /api/summary, /health-check |
| `settings.py` | GET/POST /api/settings, /logging |
| `logs.py` | GET /api/logs/audit, /app, POST /clear, GET /download |

## Key Helpers (helpers.py)

```python
operation_response(result, success_data=None, error_code=500)
# Converts OperationResult → (jsonify, status_code)

get_candidate_manager()
# Get the CandidateManager instance

get_parser_for_request()
# Returns (parser, is_candidate) based on ?candidate=1 query param

get_objects_for_request()
# Returns (objects_as_dicts, is_candidate) — safe, no shared state mutation
```

## Patterns

**Lock check** (required for candidate mutations):
```python
session_id = request.headers.get("X-Session-Id", "")
if not cm.can_modify(session_id):
    return jsonify({"success": False, "error": "Locked by another user"}), 423
```

**Backup before mutation**: `bm.create_backup("operation_name")` before any write.
```

```bash
git add routes/CLAUDE.md
git commit -m "docs: update routes/CLAUDE.md for candidate config system"
```

### Step 5: Replace `.claude/API_REFERENCE.md`

Replace the entire file with:

```markdown
# Service API Reference

## CandidateManager

| Function | What | Returns |
|----------|------|---------|
| init_session(session_id, user_name, user_email) | Create candidate dir, copy config, git init | OperationResult |
| has_session() | Check if candidate dir exists | bool |
| get_session_info() | Session metadata + undo count | Optional[Dict] |
| can_modify(session_id) | Check if session owns the lock | bool |
| discard() | Delete candidate dir, release lock | OperationResult |
| to_candidate_path(running_path) | Map running → candidate path | str |
| to_running_path(candidate_path) | Map candidate → running path | str |
| edit_object(file, line, attrs, type, inline_comments, desc, update_refs) | Edit + optional reference update + git commit | OperationResult |
| delete_object(file, line, desc) | Delete + git commit | OperationResult |
| create_object(file, type, attrs, after_line, inline_comments, desc) | Create + git commit | OperationResult |
| move_object(src_file, src_line, tgt_file, type, attrs, insert_line, desc) | Move + git commit | OperationResult |
| bulk_edit(edits, desc) | Multiple edits + single git commit | OperationResult |
| bulk_delete(deletes, desc) | Multiple deletes (bottom-to-top) + single commit | OperationResult |
| bulk_move(moves, desc) | Multiple moves + single git commit | OperationResult |
| undo() | git reset --hard HEAD~1 | OperationResult |
| get_diff() | Changed files + unified diff | OperationResult |
| get_file_diff(path, context_lines) | Per-file diff from baseline | OperationResult |
| detect_conflicts() | Compare running checksums vs baseline | List[Dict] |
| validate(nagios_bin) | Run nagios -v on candidate | OperationResult |
| apply() | Copy candidate → running, cleanup | OperationResult |
| create_file(path, desc) | Create file + git commit | OperationResult |
| delete_file(path, desc) | Delete file + git commit | OperationResult |
| move_file(src, tgt, desc) | Move file + git commit | OperationResult |
| create_folder(path, desc) | Create folder + git commit | OperationResult |
| delete_folder(path, desc) | Delete folder + git commit | OperationResult |
| move_folder(src, tgt, desc) | Move folder + git commit | OperationResult |

## NagiosService

| Function | What | Returns |
|----------|------|---------|
| get_objects() | Return all parsed objects | List[NagiosObject] |
| find_object_by_index(idx) | Get object by global index | Optional[NagiosObject] |
| find_object_by_stable_key(key) | Get object by stable key | Optional[Tuple[int, NagiosObject]] |
| search_objects(query, type, field, regex) | Search objects | List[NagiosObject] |
| get_object_stats() | Get counts by type and file | Dict |
| get_name_field(object_type) | Get name field for object type | str |
| transform_name(name, find, replace, prefix, suffix, regex) | Transform name with find/replace/prefix/suffix | Optional[str] |
| update_references(objects, old_name, new_name) | Update all references when object renamed | int (count updated) |
| create_object(target_file, obj_type, attrs, after_block_line) | Create new object | OperationResult |
| update_object(file, line, attrs, type) | Update object in place | OperationResult |
| delete_object(file, line) | Delete object | OperationResult |
| move_object(src_file, src_line, tgt_file, type, attrs, insert_line) | Move object between files | OperationResult |
| reload() | Force parser reload | NagiosConfigParser |

## GitService

| Function | What | Returns |
|----------|------|---------|
| is_repo() | Check if inside git repo | OperationResult[Bool] |
| get_user_identity() | Get configured user.name/email | OperationResult[Dict] |
| get_status(excluded_paths) | Git status porcelain | OperationResult[GitStatusResult] |
| get_diff(filepath, staged, full_file, context_lines) | Get diff for file/all | OperationResult[str] |
| get_workspace_diff(excluded) | Structured diff for commit dialog | OperationResult[Dict] |
| get_log(limit) | Commit history | OperationResult[Dict] |
| has_uncommitted_changes() | Check if dirty working dir | OperationResult[Bool] |
| init_repo() | Initialize git repo | OperationResult |
| commit(message, files, user_name, user_email) | Stage and commit | OperationResult[Dict] |
| discard(filepath) | Discard changes to file | OperationResult[Dict] |
| discard_all() | Hard reset + clean | OperationResult[Dict] |
| restore(commit_hash) | Restore to specific commit | OperationResult[Dict] |
| clear_history(user_name, user_email) | Wipe history, fresh commit | OperationResult[Dict] |

## BackupManager

| Function | What | Returns |
|----------|------|---------|
| create_backup(desc, user_name, user_email) | Create zip backup with metadata | str (backup path) |
| list_backups() | List all backups (zip + legacy) | List[Dict] |
| restore_backup(name, user_name, user_email) | Restore from backup | Dict |
| delete_backup(name) | Delete specific backup | bool |
| cleanup_old_backups(keep_count) | Keep N recent, delete rest | int (deleted count) |

## OperationResult

```python
@dataclass
class OperationResult:
    success: bool
    error: Optional[str] = None
    data: Any = None
```

Usage:

```python
result = service.create_object(...)
if not result.success:
    return jsonify({'error': result.error}), 500
return jsonify({'success': True, 'data': result.data})
```
```

```bash
git add .claude/API_REFERENCE.md
git commit -m "docs: update API_REFERENCE for candidate config system"
```

### Step 6: Update `.claude/ROUTES_REFERENCE.md`

Remove the entire "Staging Operations" section and replace with:

```markdown
## Candidate Config (routes/candidate.py)

| Route | Method | What |
|-------|--------|------|
| /api/candidate/init | POST | Create candidate session (copy running → .candidate/) |
| /api/candidate | GET | Get session status (active, user, undo count) |
| /api/candidate | DELETE | Discard candidate session (?force=1 for admin break) |
| /api/candidate/edit | POST | Edit object in candidate |
| /api/candidate/delete-objects | POST | Bulk delete objects in candidate |
| /api/candidate/create | POST | Create object in candidate |
| /api/candidate/move | POST | Move object between files in candidate |
| /api/candidate/undo | POST | Undo last action (git reset HEAD~1) |
| /api/candidate/objects | GET | Parse candidate, return objects (running paths) |
| /api/candidate/files | GET | List .cfg files in candidate (running paths) |
| /api/candidate/folders | GET | List folders in candidate (running paths) |
| /api/candidate/diff | GET | Changed files + unified diff from baseline |
| /api/candidate/diff/file | POST | Per-file unified diff |
| /api/candidate/conflicts | GET | Detect externally modified running-config files |
| /api/candidate/health-check | GET | Run health checks on candidate objects |
| /api/candidate/validate | POST | Run nagios -v on candidate config |
| /api/candidate/apply | POST | Apply candidate → running + backup + reload parser |
| /api/candidate/bulk-edit | POST | Bulk edit with single git commit |
| /api/candidate/bulk-move | POST | Bulk move with single git commit |
| /api/candidate/file/create | POST | Create file in candidate |
| /api/candidate/file/delete | POST | Delete file in candidate |
| /api/candidate/file/move | POST | Move file in candidate |
| /api/candidate/folder/create | POST | Create folder in candidate |
| /api/candidate/folder/delete | POST | Delete folder in candidate |
| /api/candidate/folder/move | POST | Move folder in candidate |
```

Update the "File/Folder Operations" section to only show surviving routes:

```markdown
## File/Folder Operations (routes/files.py)

| Route | Method | What |
|-------|--------|------|
| /api/files | GET | List all .cfg files in config directory |
| /api/folders | GET | List all folders in config directory |
```

Update the "Bulk Operations" section:

```markdown
## Bulk Operations (routes/bulk_ops.py)

| Route | Method | What |
|-------|--------|------|
| /api/search | POST | Search objects by query, type, field, regex |
| /api/preview-rename | POST | Preview bulk rename with pattern/prefix/suffix |
| /api/diff/rename | POST | Generate diff for bulk rename operation |
```

```bash
git add .claude/ROUTES_REFERENCE.md
git commit -m "docs: update ROUTES_REFERENCE for candidate config system"
```

### Step 7: Update `static/js/CLAUDE.md`

Replace the core modules table:

```markdown
## Core Modules (loaded on every page)

| File | What |
|------|------|
| `api-client.js` | Fetch wrapper, `{success, data, error}` format |
| `candidate-api.js` | Candidate config API wrapper, `ensureSession()` auto-init |
| `base-state.js` | Shared state (lock status, session) |
| `session-manager.js` | Session ID and user identity management |
| `ui-notifications.js` | Toast notifications, flash messages |
| `git-ui.js` | Git result panel UI |
| `commit-dialog.js` | Commit overlay, candidate diff display |
| `lock-manager.js` | Candidate lock polling and banner |
| `base.js` | Initialization, event delegation, keyboard shortcuts, DebugLogger |
```

```bash
git add static/js/CLAUDE.md
git commit -m "docs: update static/js/CLAUDE.md for candidate-api.js"
```

### Step 8: Update `static/js/explorer/CLAUDE.md`

Replace with:

```markdown
# Explorer Modules

All modules attach to `window.Explorer` namespace. State in `Explorer.state`.

## Module Index

| File | What |
|------|------|
| `main.js` | Namespace, state structure (allObjects, selections, `candidateActive` flag) |
| `constants.js` | Domain metadata from `/api/metadata`, UI-only constants, shared helpers |
| `state-management.js` | Stable key helpers, `refreshAfterObjectChange()` |
| `app.js` | Left pane: tree rendering, filtering, selection, autocomplete |
| `object-editor.js` | Center pane: attribute editor, save via `CandidateApi.editObject()` |
| `file-operations.js` | Right pane: file tree, navigation, folder ops via `CandidateApi.*` |
| `context-menu.js` | Right-click menus, bulk actions |
| `dialogs.js` | Create/delete/rename dialogs, `stageObjectDeletions()` via `CandidateApi.deleteObjects()` |
| `data-loading.js` | API calls, candidate-aware object loading, polling, undo |
| `drag-drop.js` | Drag-drop cleanup utilities (handlers in context-menu.js and file-operations.js) |
| `analysis.js` | Suggestions tab: template detection, validation errors (supports `?candidate=1`) |
| `analysis-issues.js` | Grouped validation errors, batch create missing objects |
| `analysis-suggestions.js` | Template consolidation and hostgroup suggestions |
| `badge-issues.js` | Issue badge rendering and counts for tree nodes |
| `relations-loader.js` | Reference and inheritance loading for center pane |
| `impact-section.js` | Impact analysis and resolved attributes in center pane |
| `ui-utils.js` | Icons, `formatObjectName()`, `buildBreadcrumb()`, tab switching |

## Candidate Mode

When `Explorer.state.candidateActive` is true:
- `loadObjects()` fetches from `/api/candidate/objects`, `/files`, `/folders`
- Save calls `CandidateApi.editObject()` directly (no pending edits map)
- Delete calls `CandidateApi.deleteObjects()`
- File/folder ops call `CandidateApi.createFile()`, etc.
- Undo calls `CandidateApi.undo()`
- All mutations auto-init the session via `CandidateApi.ensureSession()`

## Constants: Metadata vs Hardcoded

From `/api/metadata` (source of truth: `nagios_model.py`):
`typeLabels`, `nameFields`, `REQUIRED_FIELDS`, `referenceFields`, `ATTR_REFERENCE_MAP`, `NAGIOS_ATTRIBUTES`, `defaultAttributes`, `groupStructure`, notification options, failure criteria

Hardcoded (UI-only, no backend equivalent):
`identityFields`, `inheritanceAttrs`, `referenceAttrs`
```

```bash
git add static/js/explorer/CLAUDE.md
git commit -m "docs: update explorer/CLAUDE.md for candidate mode"
```

### Step 9: Update `templates/CLAUDE.md`

Replace the JS load order line with:
```markdown
**JS** (before `</body>`): Bootstrap JS → `app.js` → `base-state.js` → `session-manager.js` → `ui-notifications.js` → `git-ui.js` → `api-client.js` → `candidate-api.js` → `commit-dialog.js` → `lock-manager.js` → `base.js` → `{% block scripts %}`
```

Update the Lock Banner description:
```markdown
**Lock Banner** (`#lockBanner`): Shown when another user has an active candidate session.
```

Update the globalCommitOverlay description:
```markdown
| `#globalCommitOverlay` | Candidate changes + git commit dialog |
```

```bash
git add templates/CLAUDE.md
git commit -m "docs: update templates/CLAUDE.md for candidate-api.js load order"
```

### Step 10: Add decision log entry

Append to `.claude/DECISION_LOG.md`:

```markdown
## 2026-02-26: Replace delta-based staging with candidate config

**Decision:** Replace the delta-based staging system (~5,100 lines) with a candidate config model. When a user starts editing, copy the running config to `.candidate/`, git init it, edit files directly, use git for undo. Apply = copy back to running.

**Why:**
1. The old staging system had a proven cross-file delete bug caused by stale line numbers during multi-phase apply
2. Delta-based staging required complex composite action merging that was fragile and hard to test
3. The candidate model is simpler: each edit modifies real files, git handles undo, apply is a directory copy
4. Net reduction of ~3,700 lines of code

**Removed:** `staging_manager.py`, `routes/staging.py`, `apply_verification.py`, `test_reorder.py`, related tests, staging imports/logic from `routes/backups.py`, `routes/git.py`, `routes/settings.py`, `tests/test_atomic_writes.py` (partial), `tests/test_health_check.py` (partial), `tests/test_stable_keys.py` (import updated), direct-write routes not wired to frontend (`/api/delete-objects`, `/api/clone-objects`, `/api/smart-grouping/create`, `/api/smart-grouping/add-to-group`, `/api/files/relocate`, `/api/folders/relocate`, batch `/api/delete`), `templates/docs/staging-system.html`, `templates/docs/data-flow-staging.html`, dead staging CSS classes
**Migrated:** `generate_stable_key()`, `generate_stable_key_for_object()`, and `parse_stable_key()` moved from `staging_manager.py` to `nagios_model.py`
**Added:** `candidate_manager.py`, `routes/candidate.py`, `static/js/candidate-api.js`, `guard_candidate_or_abort()` helper for admin/recovery routes
**Guarded:** Admin/recovery routes (`/api/backups/<name>/restore`, `/api/git/discard`, `/api/git/discard-all`, `/api/git/restore`, `/api/git/clear-history`) return 409 during active candidate session
**Preserved:** Non-staging bulk ops (`/api/search`, `/api/preview-rename`, `/api/diff/rename`), read-only file/folder listing (`GET /api/files`, `GET /api/folders`)
```

```bash
git add .claude/DECISION_LOG.md
git commit -m "docs: add decision log entry for candidate config migration"
```

### Step 11: Verify documentation — no stale references

```bash
grep -rn "staging_manager\|StagingManager\|get_staging_manager\|staging.py\|staging.json\|STAGING_REFERENCE" \
  CLAUDE.md .claude/ routes/CLAUDE.md templates/CLAUDE.md static/js/CLAUDE.md static/js/explorer/CLAUDE.md \
  | grep -v DECISION_LOG | grep -v "docs/plans"
```

Expected: 0 matches

```bash
# Verify candidate_manager.py mentioned in root CLAUDE.md
grep "candidate_manager" CLAUDE.md

# Verify candidate.py mentioned in routes/CLAUDE.md
grep "candidate.py" routes/CLAUDE.md

# Verify candidate-api.js mentioned in static/js/CLAUDE.md
grep "candidate-api" static/js/CLAUDE.md

# Verify CANDIDATE_REFERENCE exists
ls .claude/CANDIDATE_REFERENCE.md
```

Expected: all matches found

```bash
git add -A
git commit -m "docs: final documentation cleanup for candidate config"
```

---

## Task 4: Verify no dead references remain

**Step 1: Check Python staging references**

```bash
# Python staging references (BLOCKER: app won't start if any remain)
grep -rn "staging_manager\|StagingManager\|get_staging_manager\|ensure_staging_lock\|StagingStatus" \
  --include="*.py" . | grep -v __pycache__ | grep -v docs/plans

# Python apply/composite references
grep -rn "CompositeAction\|apply_object_composite\|get_typed_staging\|apply_verification" \
  --include="*.py" . | grep -v __pycache__ | grep -v docs/plans
```

Expected: no matches (except docs/plans/)

**Step 2: Check removed direct-write route references**

```bash
# Frontend calls to removed routes (should be 0 — they were never wired)
grep -rn "/api/delete-objects\|/api/clone-objects\|/api/smart-grouping/create\|/api/smart-grouping/add-to-group\|/api/files/relocate\|/api/folders/relocate" \
  --include="*.js" static/

# Python route definitions (should be 0 in routes/ after removal)
grep -rn "api_delete_objects\|api_clone_objects\|api_smart_grouping_create\|api_add_to_group\|api_relocate_file\|api_relocate_folder" \
  --include="*.py" routes/ | grep -v docs/plans
```

Expected: no matches

**Step 3: Check JavaScript staging references**

```bash
# JS staging state references (check ALL JS files, not just explorer/)
grep -rn "pendingEdits\|stagedMoves\|stagedCreations\|stagedObjectDeletions\|stagedCreationDeletions" \
  --include="*.js" static/

# JS staging API references (includes settings.js, lock-manager.js, git.js)
grep -rn "/api/staging\|saveStagedChanges\|loadStagedChanges\|syncStagingFromData\|loadVirtualTree" \
  --include="*.js" static/

# JS staging helper references
grep -rn "getOrCreatePendingEdit\|selectedStagedIndices\|externalChangePending\|undoStack" \
  --include="*.js" static/

# JS old function name references (P4-J)
grep -rn "getStagingHeaders" --include="*.js" static/
grep -rn "getStagingHeaders" eslint.config.mjs
```

Expected: no matches

**Step 4: Check CSS staging references**

```bash
grep -rn "\.staged-\|\.staging\|\.pending-indicator\|\.tree-count--pending\|\.git-staging-preview" \
  --include="*.css" static/css/
```

Expected: no matches (or only candidate-reused classes if any were intentionally kept)

**Step 5: Check template staging references**

```bash
# Doc pages (staging-system.html and data-flow-staging.html should be deleted)
ls templates/docs/staging-system.html templates/docs/data-flow-staging.html 2>&1

# Staging terminology in remaining templates
grep -rn "staging\|pending changes" --include="*.html" templates/ | grep -v "docs/plans"
```

Expected: deleted files not found; remaining matches only in appropriate context (e.g., "candidate" system descriptions, not old "staging" references)

**Step 6: Check for broken imports**

```bash
python3 -c "from app import create_app; app = create_app(); print('App starts OK')"
```

Expected: prints `App starts OK`

**Step 7: Full test suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all pass

**Step 8: Full lint**

```bash
ruff check .
npm run lint:js
```

Expected: 0 errors

**Step 9: Commit any fixes**

```bash
git add -A
git commit -m "fix: clean up remaining dead staging references"
```

---

## Task 5: Guard admin/recovery routes during active candidate session

**CRITICAL SAFETY PRINCIPLE:** Nothing modifies the running Nagios .cfg files until the user clicks Apply. Admin/recovery routes (backup restore, git discard/restore) write directly to running config and would corrupt the candidate baseline if executed during an active editing session.

**IMPORTANT:** The staging cleanup for `routes/backups.py` and `routes/git.py` in Task 1 already removes the old staging lock checks. This task adds the NEW candidate guards to replace them. If doing Tasks 1 and 5 in sequence, the guard additions in this task should be applied as part of the same commit or immediately after Task 1's cleanup.

**Files:**
- Modify: `routes/helpers.py`
- Modify: `routes/backups.py`
- Modify: `routes/git.py`
- Modify: `tests/test_candidate_routes.py`

**Step 1: Add guard helper to `routes/helpers.py`**

```python
def require_no_candidate_session():
    """Return error response if a candidate session is active.

    Direct-write routes must not modify running config while a candidate
    session exists — it would corrupt the candidate baseline.
    Returns None if safe to proceed, or (response, status_code) if blocked.

    IMPORTANT: Fails CLOSED — if we can't check candidate status, we block
    the request rather than allow a potentially destructive write.
    """
    import logging as _logging

    try:
        cm = get_candidate_manager()
        if cm.has_session():
            _logging.getLogger("nagios_bulk_editor.candidate").warning(
                "Blocked direct-write route: candidate session active (endpoint=%s)",
                request.path,
            )
            return jsonify({
                "success": False,
                "error": "Cannot modify running config while an editing session is active. "
                         "Apply or discard your changes first.",
            }), 409
    except Exception as e:
        # Fail CLOSED: if we can't verify candidate status, block the write
        _logging.getLogger("nagios_bulk_editor.candidate").error(
            "Candidate guard check failed — blocking write for safety: %s", e,
        )
        return jsonify({
            "success": False,
            "error": "Cannot verify editing session status. Try again later.",
        }), 500
    return None


def guard_candidate_or_abort():
    """Call at start of direct-write routes. Returns error response if candidate active."""
    blocked = require_no_candidate_session()
    if blocked:
        return blocked
    return None
```

**Step 2: Guard admin/recovery routes**

In `routes/backups.py`:
```python
@bp.route("/api/backups/<backup_name>/restore", methods=["POST"])
def api_restore_backup(backup_name):
    blocked = guard_candidate_or_abort()
    if blocked:
        return blocked
    # ... existing code ...
```

In `routes/git.py`:
```python
@bp.route("/api/git/discard", methods=["POST"])
def api_git_discard():
    blocked = guard_candidate_or_abort()
    if blocked:
        return blocked
    # ... existing code ...

@bp.route("/api/git/discard-all", methods=["POST"])
def api_git_discard_all():
    blocked = guard_candidate_or_abort()
    if blocked:
        return blocked
    # ... existing code ...

@bp.route("/api/git/restore", methods=["POST"])
def api_git_restore():
    blocked = guard_candidate_or_abort()
    if blocked:
        return blocked
    # ... existing code ...

@bp.route("/api/git/clear-history", methods=["POST"])
def api_git_clear_history():
    blocked = guard_candidate_or_abort()
    if blocked:
        return blocked
    # ... existing code ...
```

**Step 3: Write tests**

Add to `tests/test_candidate_routes.py`:

```python
class TestCandidateGuards:
    """Admin/recovery routes must be blocked during active candidate session."""

    def test_backup_restore_blocked_during_candidate(self, client):
        client.post("/api/candidate/init", json={"session_id": "s1"})
        resp = client.post("/api/backups/test/restore", json={})
        assert resp.status_code == 409

    def test_git_discard_blocked_during_candidate(self, client):
        client.post("/api/candidate/init", json={"session_id": "s1"})
        resp = client.post("/api/git/discard", json={"file": "hosts.cfg"})
        assert resp.status_code == 409

    def test_git_discard_all_blocked_during_candidate(self, client):
        client.post("/api/candidate/init", json={"session_id": "s1"})
        resp = client.post("/api/git/discard-all", json={})
        assert resp.status_code == 409

    def test_git_restore_blocked_during_candidate(self, client):
        client.post("/api/candidate/init", json={"session_id": "s1"})
        resp = client.post("/api/git/restore", json={"commit": "abc123"})
        assert resp.status_code == 409

    def test_git_clear_history_blocked_during_candidate(self, client):
        client.post("/api/candidate/init", json={"session_id": "s1"})
        resp = client.post("/api/git/clear-history", json={})
        assert resp.status_code == 409

    def test_backup_restore_allowed_without_candidate(self, client):
        """Admin routes work normally when no candidate session exists."""
        resp = client.post("/api/backups/test/restore", json={})
        assert resp.status_code != 409

    def test_git_discard_allowed_without_candidate(self, client):
        resp = client.post("/api/git/discard", json={"file": "hosts.cfg"})
        assert resp.status_code != 409
```

**Step 4: Lint and commit**

```bash
ruff check routes/helpers.py routes/backups.py routes/git.py tests/test_candidate_routes.py
git add routes/helpers.py routes/backups.py routes/git.py tests/test_candidate_routes.py
git commit -m "safety: block admin/recovery routes during active candidate session"
```

---

## Task 6: Playwright E2E — full workflow verification

Start the server and exercise every candidate workflow via Playwright MCP tools.

**Step 1: Start server**

```bash
python3 app.py &
sleep 2
```

**Step 2: Explorer — initial load**

```
browser_navigate: http://localhost:8080/explorer
browser_console_messages(level: "error")
browser_snapshot(filename: "e2e-01-initial-load.md")
```

Verify:
- Page loads with objects in left tree
- No JS console errors
- No "Start Editing" or "Lock" button visible

**Step 3: Edit a host — auto-init**

1. `browser_snapshot` — find a host node in the tree
2. Click the host to open it in center pane
3. `browser_snapshot` — find the alias field
4. Clear alias field, type new value "E2E-Test-Host"
5. Click Save button
6. `browser_snapshot(filename: "e2e-02-after-edit.md")`

Verify:
- Candidate session auto-created (no manual "Start Editing")
- Left tree shows updated host
- Center pane reflects edit
- `browser_console_messages(level: "error")` — no errors

**Step 4: Delete a service**

1. Right-click a service in the tree
2. Click Delete in context menu
3. Confirm deletion
4. `browser_snapshot(filename: "e2e-03-after-delete.md")`

Verify:
- Service removed from left tree
- Service removed from right file tree
- `browser_console_messages(level: "error")` — no errors

**Step 5: Create a new host**

1. Right-click in tree, select "Create Object"
2. Fill in host_name: "e2e-new-host", alias: "E2E New", address: "10.0.0.99"
3. Select target file
4. Click Create
5. `browser_snapshot(filename: "e2e-04-after-create.md")`

Verify:
- New host appears in left tree
- New host appears in right file tree
- `browser_console_messages(level: "error")` — no errors

**Step 6: Undo each operation (x3)**

1. Click Undo (or Ctrl+Z) — verify create is undone
2. `browser_snapshot(filename: "e2e-05-after-undo-1.md")`
3. Click Undo — verify delete is undone (service reappears)
4. `browser_snapshot(filename: "e2e-06-after-undo-2.md")`
5. Click Undo — verify edit is undone (alias reverts)
6. `browser_snapshot(filename: "e2e-07-after-undo-3.md")`

Verify:
- Each undo correctly reverts one operation
- All panes update correctly after each undo
- `browser_console_messages(level: "error")` — no errors

**Step 7: Re-do changes for commit testing**

1. Edit a host alias to "CommitTest"
2. Delete a service
3. Verify changes visible in tree

**Step 8: Check diff view**

1. Navigate to `/git` page
2. `browser_snapshot(filename: "e2e-08-git-page.md")`
3. Look for "Candidate" tab or diff display
4. Click to view diffs

Verify:
- Changed files listed
- Unified diff shows alias change and service deletion
- `browser_console_messages(level: "error")` — no errors

**Step 9: Apply changes via commit dialog**

1. Navigate back to `/explorer`
2. Open commit dialog (via toolbar button or keyboard shortcut)
3. `browser_snapshot(filename: "e2e-09-commit-dialog.md")`
4. Verify summary shows changed files and diffs
5. Enter commit message
6. Click Apply/Commit

Verify:
- Dialog shows correct summary
- After apply: candidate session cleaned up
- Running config reflects changes (check a changed host)
- `browser_console_messages(level: "error")` — no errors

**Step 10: Verify audit log entries**

```bash
# Check that candidate operations were audit-logged
tail -20 logs/audit.log
```

Verify: audit log contains AUDIT entries for `candidate_init`, `candidate_edit`, `candidate_delete`, `candidate_apply`. Each entry should include `txn=`, `user=`, `action=`, and a timestamp.

**Step 11: Verify running config updated**

1. `browser_snapshot(filename: "e2e-10-after-apply.md")`
2. Check that the edited host shows "CommitTest" alias
3. Check that the deleted service is gone

Verify: running config correctly updated.

**Step 12: Fresh session — discard test**

1. Edit another host alias to "DiscardTest"
2. `browser_snapshot(filename: "e2e-11-before-discard.md")`
3. Click "Discard All" / reset candidate
4. `browser_snapshot(filename: "e2e-12-after-discard.md")`

Verify:
- Candidate session discarded
- UI reverts to running config
- Edit is lost (host alias back to original)
- `browser_console_messages(level: "error")` — no errors

**Step 13: Final console check**

```
browser_console_messages(level: "warning")
```

Document any warnings. Errors should be zero.

**Step 14: Stop server**

```bash
kill %1
```

**Step 15: Document results**

Save any discovered issues to `docs/test-discoveries/`. Take screenshots of failures.

---

## Phase Gate: Final Verification

Before considering Phase 4 (and the entire candidate config migration) complete:

**Step 1: Full Python test suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all pass

**Step 2: Full Python lint**

```bash
ruff check .
ruff format --check .
```

Expected: 0 errors

**Step 3: Full JavaScript lint**

```bash
npm run lint:js
```

Expected: 0 errors

**Step 4: No dead staging references**

```bash
# Python (includes StagingStatus which routes/backups.py and routes/git.py imported)
grep -rn "staging_manager\|StagingManager\|StagingStatus\|get_staging_manager\|ensure_staging_lock\|CompositeAction\|apply_object_composite\|get_typed_staging\|apply_verification\|_check_staging_lock" \
  --include="*.py" . | grep -v __pycache__ | grep -v docs/plans

# JavaScript (includes settings.js staging lock calls)
grep -rn "pendingEdits\|stagedMoves\|stagedCreations\|stagedObjectDeletions\|/api/staging\|saveStagedChanges\|loadStagedChanges\|syncStagingFromData\|loadVirtualTree\|getOrCreatePendingEdit\|selectedStagedIndices\|externalChangePending\|undoStack\|stagedCreationDeletions\|getStagingHeaders" \
  --include="*.js" static/

# CSS dead classes
grep -rn "\.staged-\|\.staging\|\.tree-count--pending\|\.git-staging-preview" \
  --include="*.css" static/css/

# Templates — deleted doc pages should not exist
ls templates/docs/staging-system.html templates/docs/data-flow-staging.html 2>&1
```

Expected: no matches (Python, JS, CSS). Deleted template files not found.

**Step 5: Audit logging verified during E2E**

After the Playwright E2E test (Task 6), verify audit log contains entries for candidate operations:

```bash
# Check audit log for candidate init, edit, delete, apply entries
grep -c "candidate_init\|candidate_edit\|candidate_delete\|candidate_apply\|candidate_discard" logs/audit.log
```

Expected: at least 4 entries (init + edit + delete + apply from the E2E test).

If `logs/audit.log` doesn't exist or has 0 candidate entries, there is a gap in the Phase 2 route audit logging — fix before completing.

**Step 6: Playwright E2E passed**

All 13 verification steps passed (including audit log check). No JS console errors.

**Step 7: LOC delta**

```bash
git diff --stat main...HEAD
```

Expected: net negative LOC change (~-3,700 lines)

**Step 8: Report**

Report final summary:
- Tests: X passed
- Lint: 0 errors (Python + JS)
- E2E: 13/13 steps passed
- Audit log: candidate operations logged (init, edit, delete, apply)
- LOC: -~3,700 lines
- Dead references: 0
- Phase 4 and full candidate config migration complete.
