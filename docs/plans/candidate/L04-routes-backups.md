# L04: routes/backups.py — MODIFY

**Layer:** 4 — Route Cleanup
**Action:** MODIFY
**Path:** `routes/backups.py`
**Dependencies:** L03 (`guard_candidate_or_abort` must exist in `routes/helpers.py`), L02 (`backup_manager.py` excludes `.candidate/` from backups)
**Goal:** Replace staging lock checks with candidate guards. Preserve all audit logging and error handling. Keep all five routes intact.

---

## Current State

### Imports (lines 1–18)

```python
from staging_manager import StagingStatus           # line 9 — REMOVE
from .helpers import (
    format_audit_user,
    get_audit_user_identity,
    get_backup_manager,
    get_service,
    get_staging_manager,                             # line 16 — REMOVE
)
```

### Routes (5 total)

| # | Route | Method | Function | Staging refs |
|---|-------|--------|----------|-------------|
| 1 | `GET /api/backups` | GET | `api_list_backups()` | None |
| 2 | `POST /api/backups` | POST | `api_create_backup()` | None |
| 3 | `POST /api/backups/<name>/restore` | POST | `api_restore_backup()` | Lines 61–70 (lock check), lines 84–94 (`save_staging` with `RESTORE_PENDING`) |
| 4 | `DELETE /api/backups/all` | DELETE | `api_delete_all_backups()` | None |
| 5 | `DELETE /api/backups/<name>` | DELETE | `api_delete_backup()` | None |

### Staging references in `api_restore_backup()` (lines 56–105)

| Line(s) | Code | Category |
|---------|------|----------|
| 61 | `session_id = request.headers.get("X-Session-Id")` | session header read |
| 63–70 | `staging_mgr = get_staging_manager()` + lock owner check + 423 | staging lock check |
| 84–94 | `staging_mgr = get_staging_manager()` + `staging_mgr.save_staging({...StagingStatus.RESTORE_PENDING...})` | post-restore staging state |

## Changes

### Step 1: Update imports

Remove staging imports. Add `guard_candidate_or_abort`:

```python
# REMOVE these two lines:
from staging_manager import StagingStatus
get_staging_manager,

# ADD to helpers import:
from .helpers import (
    format_audit_user,
    get_audit_user_identity,
    get_backup_manager,
    get_service,
    guard_candidate_or_abort,     # NEW — replaces staging lock check
)
```

### Step 2: Replace staging lock check in `api_restore_backup()`

Remove the manual `get_staging_manager()` + lock owner check (lines 61–70). Replace with `guard_candidate_or_abort()` at the top of the function. This blocks restore while any candidate session is active, because restoring live config would invalidate the candidate baseline.

**Before:**
```python
def api_restore_backup(backup_name):
    logger.info("Restore backup: backup_name=%s", backup_name)
    session_id = request.headers.get("X-Session-Id")
    data = request.get_json() or {}
    if session_id:
        staging_mgr = get_staging_manager()
        lock_owner = staging_mgr.get_lock_owner()
        if lock_owner and lock_owner != session_id:
            return jsonify({...}), 423
```

**After:**
```python
def api_restore_backup(backup_name):
    logger.info("Restore backup: backup_name=%s", backup_name)
    guard_candidate_or_abort()   # Blocks if ANY candidate session active (fail-CLOSED)
    data = request.get_json() or {}
```

Note: `guard_candidate_or_abort()` is stricter than the old staging lock check. The old check allowed the lock owner to restore; the new guard blocks ALL sessions. This is intentional — restoring live config while editing a candidate would corrupt the candidate's baseline checksums, making conflict detection unreliable. The user must discard their candidate session first.

### Step 3: Remove `save_staging()` call after restore

Remove the post-restore `save_staging({...RESTORE_PENDING...})` block (lines 84–94). Also remove the `session_id` variable read (no longer needed).

**Rationale:** In the staging system, `RESTORE_PENDING` told other sessions that live config had been replaced. In the candidate system, `guard_candidate_or_abort()` ensures no candidate session exists BEFORE restore runs, so there is no session to notify. After restore, the live config is updated and any future `init_session()` will snapshot the restored state as its baseline.

### Step 4: Keep all other routes UNCHANGED

The following routes have NO staging references and require NO modification:

| Route | Audit logging | Error handling | Status |
|-------|--------------|----------------|--------|
| `GET /api/backups` — `api_list_backups()` | N/A (read-only) | Returns empty list if no backups dir | KEEP |
| `POST /api/backups` — `api_create_backup()` | `log_audit(action="backup_created", ...)` | BackupManager handles errors internally | KEEP |
| `DELETE /api/backups/all` — `api_delete_all_backups()` | `log_audit(action="backups_deleted", ...)` | Iterates with per-backup error tolerance | KEEP |
| `DELETE /api/backups/<name>` — `api_delete_backup()` | `log_audit(action="backup_deleted", ...)` | Returns 404 if not found | KEEP |

### Step 5: Verify audit logging preserved in restore route

The existing audit log call in `api_restore_backup()` must remain intact:

```python
# This block STAYS — do not remove
log_audit(
    action="backup_restored",
    user=format_audit_user(identity),
    backup_name=backup_name,
)
```

## Final State of `api_restore_backup()`

```python
@bp.route("/api/backups/<backup_name>/restore", methods=["POST"])
def api_restore_backup(backup_name):
    """Restore from a backup."""
    logger.info("Restore backup: backup_name=%s", backup_name)
    guard_candidate_or_abort()
    data = request.get_json() or {}

    bm = get_backup_manager()
    try:
        user_name = data.get("userName", "")
        user_email = data.get("userEmail", "")

        result = bm.restore_backup(backup_name, user_name=user_name, user_email=user_email)
        get_service().reload()

        identity = get_audit_user_identity()

        # Write audit log entry
        log_audit(
            action="backup_restored",
            user=format_audit_user(identity),
            backup_name=backup_name,
        )

        return jsonify({"success": True, **result})
    except ValueError as e:
        logger.error("Restore backup failed: backup_name=%s error=%s", backup_name, e)
        return jsonify({"error": str(e)}), 404
```

## Removal Audit

| # | Removed Code | Lines | Candidate Equivalent | Functionality preserved? |
|---|-------------|-------|---------------------|------------------------|
| 1 | `from staging_manager import StagingStatus` | 9 | Not needed — no staging states | Yes — guard replaces state tracking |
| 2 | `get_staging_manager` import | 16 | `guard_candidate_or_abort` import | Yes — guard replaces lock check |
| 3 | `session_id = request.headers.get("X-Session-Id")` | 61 | Not needed — guard doesn't need session ID | Yes — guard checks session existence, not ownership |
| 4 | Staging lock owner check (`if session_id: staging_mgr = ...`) | 63–70 | `guard_candidate_or_abort()` | Yes — stricter (blocks all sessions, not just non-owners) |
| 5 | `save_staging({...RESTORE_PENDING...})` | 84–94 | Not needed — no session to notify after guard passes | Yes — guard ensures no session exists pre-restore |

**Dead code removed:** 5 items (2 imports, 1 variable read, 1 lock check block, 1 save_staging block)
**Functionality preserved:** All audit logging, all error handling, all 5 routes

## Error Handling Audit

| Route | Error scenario | Handling | Status |
|-------|---------------|----------|--------|
| `GET /api/backups` | Backup dir missing | Returns `[]` | OK |
| `POST /api/backups` | Disk full / permission error | BackupManager raises, Flask 500 | OK |
| `POST /api/backups/<name>/restore` | Candidate session active | `guard_candidate_or_abort()` returns 409 | OK |
| `POST /api/backups/<name>/restore` | Guard can't verify candidate state | `guard_candidate_or_abort()` returns 500 (fail-CLOSED) | OK |
| `POST /api/backups/<name>/restore` | Backup not found | `ValueError` caught, returns 404 | OK |
| `POST /api/backups/<name>/restore` | Restore fails mid-way | `ValueError` with safety backup path, returns 404 | OK |
| `POST /api/backups/<name>/restore` | Unexpected error | Uncaught → Flask 500 with traceback in logs | OK — add `logger.error` in except block |
| `DELETE /api/backups/all` | Individual delete fails | Silently skips (per-backup tolerance) | OK |
| `DELETE /api/backups/<name>` | Not found | Returns 404 JSON | OK |

**Improvement:** Add `logger.error` in the `except ValueError` block of `api_restore_backup()` to ensure restore failures are logged at ERROR level (not just returned as 404). See Final State above.

## Audit Logging Inventory

Every mutation route in this file has audit logging. Verified:

| Route | Audit action | Fields logged |
|-------|-------------|---------------|
| `POST /api/backups` | `backup_created` | user, description, backup_path |
| `POST /api/backups/<name>/restore` | `backup_restored` | user, backup_name |
| `DELETE /api/backups/all` | `backups_deleted` | user, deleted_count |
| `DELETE /api/backups/<name>` | `backup_deleted` | user, backup_name |

Read-only route `GET /api/backups` does not require audit logging.

## Cross-References

- **L02-backup-manager.md**: Excludes `.candidate/` and `.staging/` directories from `_collect_config_files()` and `_replace_config_files()`. This ensures backups never contain candidate data, and restores never overwrite the candidate directory.
- **L03-routes-helpers.md**: Defines `guard_candidate_or_abort()` with fail-CLOSED behavior.
- **L04-routes-git.md**: Uses the same `guard_candidate_or_abort()` pattern for git restore operations.

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Guard blocks ALL sessions (not just non-owners) | Restoring live config invalidates candidate baseline checksums. Even the session owner should discard first. |
| No RESTORE_PENDING equivalent | Guard ensures no session exists pre-restore, so no session needs notification. |
| Restore writes directly to live config | Correct — backup restore IS the apply action. No candidate intermediary needed. |
| `guard_candidate_or_abort()` fail-CLOSED | If candidate state can't be verified, safer to reject than risk corrupting an unknown session. |

## Verification

### Unit tests

```bash
python3 -m pytest tests/ -v
# All existing backup tests should pass
```

### Manual verification checklist

- [ ] `GET /api/backups` — returns backup list (unchanged behavior)
- [ ] `POST /api/backups` — creates backup, audit logged (unchanged behavior)
- [ ] `POST /api/backups/<name>/restore` — succeeds with no candidate session
- [ ] `POST /api/backups/<name>/restore` — returns 409 when candidate session active
- [ ] `POST /api/backups/<name>/restore` — returns 404 for missing backup
- [ ] `POST /api/backups/<name>/restore` — audit log entry written on success
- [ ] `DELETE /api/backups/all` — deletes all, audit logged (unchanged behavior)
- [ ] `DELETE /api/backups/<name>` — deletes one, audit logged (unchanged behavior)

### Linting

```bash
ruff check routes/backups.py
ruff format --check routes/backups.py
```

### Playwright (if wired to backup UI)

Test candidate session guard on restore:
1. Start candidate session (init)
2. Attempt backup restore via API — expect 409
3. Discard candidate session
4. Retry backup restore — expect success

## Change Tracking

- [ ] Remove `from staging_manager import StagingStatus` import
- [ ] Remove `get_staging_manager` from helpers import
- [ ] Add `guard_candidate_or_abort` to helpers import
- [ ] Replace staging lock check with `guard_candidate_or_abort()` call
- [ ] Remove `session_id` variable read
- [ ] Remove `save_staging({...RESTORE_PENDING...})` block
- [ ] Add `logger.error` in `except ValueError` block
- [ ] Run `ruff check` and `ruff format` — verify clean
- [ ] Run `python3 -m pytest tests/ -v` — verify all pass

## Commandments Compliance

- [x] **C1 — No live config mutation until Apply.** Backup restore intentionally writes to live config (it IS the apply action for backups). The `guard_candidate_or_abort()` ensures no candidate session is in progress, preventing conflicts between restore and the candidate editing workflow.
- [x] **C2 — UI visual parity.** No UI changes in this file. All 5 API routes maintain their existing request/response contracts. Frontend backup page behavior is unchanged.
- [x] **C3 — Full audit logging.** All four mutation routes have `log_audit()` calls (backup_created, backup_restored, backups_deleted, backup_deleted). Audit logging inventory table verifies every mutation is covered. Added `logger.error` for restore failures.
- [x] **C4 — Proper error handling.** Error handling audit table covers all 9 error scenarios across all 5 routes. `guard_candidate_or_abort()` is fail-CLOSED (returns 500 if candidate state cannot be verified). `logger.error` added to restore failure path. No silent failures.
- [x] **C5 — Dead code deletion.** Removes 2 staging imports, 1 unused variable read, 1 staging lock check block, and 1 `save_staging()` block. All are zero-use after candidate migration. Removal audit table tracks each item.
- [x] **C6 — Full functionality migration.** Removal audit maps each removed feature to its candidate equivalent. Staging lock check migrated to `guard_candidate_or_abort()`. RESTORE_PENDING state no longer needed (guard ensures no session exists pre-restore). All 5 routes preserved.
- [x] **C7 — Palo Alto candidate model.** Backup restore operates on live config, not the candidate directory. L02-backup-manager.md ensures `.candidate/` is excluded from both backup creation and restore file replacement. Cross-reference section documents this dependency.
- [x] **C8 — Change tracking document.** Change tracking checklist included with all implementation steps as tickable items.
- [x] **C9 — Complete planning before implementation.** Plan includes: current state analysis with line numbers, step-by-step changes, final state code, removal audit, error handling audit, audit logging inventory, cross-references, design decisions, and verification steps.
- [x] **C10 — Linting enforcement.** Verification section includes `ruff check` and `ruff format` commands. Change tracking includes linting as a required step.
- [x] **C11 — Playwright validation.** Playwright test scenario included: verify 409 when candidate session active, verify success after discard. Scoped to the guard behavior which is the only changed behavior.
