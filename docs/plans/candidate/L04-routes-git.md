# L04: routes/git.py — MODIFY

**Layer:** 4 — Route Cleanup
**Action:** MODIFY
**Path:** `routes/git.py`
**Dependencies:** L03 (guard_candidate_or_abort must exist)
**Goal:** Replace staging references with candidate session handling. Add candidate guards to destructive routes.

---

## Commandment 1 Rationale

Git routes operate on the **live config directory** — they commit, discard, and restore real files on disk. These routes run **after** the candidate has been applied (or independently of the candidate system). The `guard_candidate_or_abort()` guards on destructive routes (discard, restore, clear-history) ensure these operations cannot run while a candidate session is active, which would corrupt the candidate's baseline. This is the correct boundary: candidate edits happen in `.candidate/`, git operations happen on the live config.

## Changes

### Imports:
1. Remove `from staging_manager import StagingStatus`
2. Remove `get_staging_manager` from helpers import
3. Add `get_candidate_manager, guard_candidate_or_abort` to helpers import

### `_check_staging_lock()` helper:
- DELETE entirely. Not needed — candidate session handles locking via `guard_candidate_or_abort()`.

### `_resolve_user_identity()`:
- Remove staging manager lookup for user identity
- Fall back to candidate session info instead:
  ```python
  if not user_name or not user_email:
      cm = get_candidate_manager()
      session_info = cm.get_session_info()
      if session_info:
          user_name = user_name or session_info.get("user_name")
          user_email = user_email or session_info.get("user_email")
  ```

### `_write_commit_audit_log()`:
- Replace staging manager with candidate manager
- Replace `StagingStatus.RESTORE_PENDING.value` check with `cm.get_session_state() == "restore_pending"`
- Candidate session stores restore info in session state, accessed via `cm.get_session_info()`:
  ```python
  cm = get_candidate_manager()
  if cm.get_session_state() == "restore_pending":
      session_info = cm.get_session_info() or {}
      kwargs["restoreType"] = session_info.get("restore_type", "")
      kwargs["restoreFrom"] = session_info.get("restore_from", "")
  ```

### `api_git_identity_get()` / `api_git_identity_set()`:
- Read/write from candidate session data instead of staging data
- `api_git_identity_get()`: replace `staging_mgr.get_staging()` with `cm.get_session_info()`
- `api_git_identity_set()`: replace `staging_mgr.save_staging()` with candidate session update

### `api_git_commit()`:
- Remove `_check_staging_lock()` call
- Remove `clear_staging()` call (candidate session handled by frontend via `CandidateApi.clearAfterCommit()`)

### `api_git_discard()`:
- Remove `_check_staging_lock()` call
- Add `guard_candidate_or_abort()` at top
- **Add audit logging** (currently missing — Commandment 3 violation in existing code):
  ```python
  identity = get_audit_user_identity()
  log_audit(
      action="git_discarded_file", user=format_audit_user(identity),
      file=filepath, git_action=result.data["action"],
  )
  ```

### `api_git_discard_all()`:
- Remove `_check_staging_lock()` call
- Add `guard_candidate_or_abort()` at top
- Keep existing `log_audit()` call (already compliant)

### `api_git_restore()`:
- Remove inline staging lock check (lines 514-521)
- Add `guard_candidate_or_abort()` at top
- Replace staging `save_staging()` with `cm.set_restore_pending()`:
  ```python
  cm = get_candidate_manager()
  # No candidate session active (guard passed), but record restore state
  # so commit audit log captures the restore context
  ```
- Remove `sm.clear_staging()` fallback (no candidate session exists at this point since guard passed)
- Keep existing `log_audit()` call (already compliant)

### `api_git_clear_history()`:
- Remove `_check_staging_lock()` call
- Add `guard_candidate_or_abort()` at top
- Keep existing `log_audit()` call (already compliant)

### Read-only routes — NO changes needed:
- `api_git_status()` — no staging references
- `api_git_diff()` — no staging references
- `api_git_log()` — no staging references

## Removal Audit

**Import: `from staging_manager import StagingStatus`** (line 9):
- Used at line 96 in `_write_commit_audit_log()` to check `StagingStatus.RESTORE_PENDING` — REPLACED by `cm.get_session_state() == "restore_pending"`.

**Import: `get_staging_manager`** (line 17):
- Imported from `.helpers` — REMOVE. All 8 call sites below are replaced or deleted.

**Function: `_check_staging_lock()` definition** (lines 24-43):
- Line 33: `staging_mgr = get_staging_manager()` — REMOVED with function.
- Line 34: `staging_mgr.get_lock_owner()` — REMOVED with function.
- Line 41: `staging_mgr.get_lock_status(session_id)` — REMOVED with function.
- REPLACED by `guard_candidate_or_abort()` on destructive routes.

**Function: `_resolve_user_identity()`** (lines 46-63):
- Line 57: `staging_mgr = get_staging_manager()` — REPLACED by `cm = get_candidate_manager()`.
- Line 58: `staging = staging_mgr.get_staging()` — REPLACED by `cm.get_session_info()`.
- Lines 60-61: `staging.get("userName")` / `staging.get("userEmail")` fallback — REPLACED by `session_info.get("user_name")` / `session_info.get("user_email")`.

**Function: `_write_commit_audit_log()`** (lines 94-100):
- Line 94: `staging_mgr = get_staging_manager()` — REPLACED by `cm = get_candidate_manager()`.
- Line 95: `staging = staging_mgr.get_staging()` — REPLACED by `cm.get_session_info()`.
- Line 96: `staging.get("status") == StagingStatus.RESTORE_PENDING.value` — REPLACED by `cm.get_session_state() == "restore_pending"`.
- Lines 97-98: `staging.get("restoreType")` / `staging.get("restoreFrom")` — REPLACED by `session_info.get("restore_type")` / `session_info.get("restore_from")`.

**Route: `api_git_identity_get()`** (lines 103-134):
- Line 112: `staging_mgr = get_staging_manager()` — REPLACED by `cm = get_candidate_manager()`.
- Line 113: `staging = staging_mgr.get_staging()` — REPLACED by `cm.get_session_info()`.
- Lines 123-124: `staging.get("userName")` / `staging.get("userEmail")` — REPLACED by `session_info.get("user_name")` / `session_info.get("user_email")`.

**Route: `api_git_identity_set()`** (lines 137-173):
- Line 149: `_check_staging_lock(session_id)` call — REMOVED (candidate session check replaces it).
- Line 162: `staging_mgr = get_staging_manager()` — REPLACED by `cm = get_candidate_manager()`.
- Line 163: `staging = staging_mgr.get_staging() or {}` — REPLACED by candidate session update.
- Lines 164-166: Setting `staging["sessionId"]`, `staging["userName"]`, `staging["userEmail"]` — REPLACED by candidate session update.
- Line 168: `staging_mgr.save_staging(staging)` — REPLACED by candidate session field update.

**Route: `api_git_commit()`** (lines 259, 320):
- Line 259: `_check_staging_lock(session_id, "commit")` call — REMOVED. No candidate guard needed here (commit operates on live config files already on disk).
- Line 320: `get_staging_manager().clear_staging()` — REMOVED. Frontend calls `CandidateApi.clearAfterCommit()`.

**Route: `api_git_discard()`** (line 356):
- Line 356: `_check_staging_lock(session_id, "discard_file")` — REMOVED. Replaced by `guard_candidate_or_abort()`.
- **NEW**: `log_audit()` call added (was missing — Commandment 3).

**Route: `api_git_discard_all()`** (line 388):
- Line 388: `_check_staging_lock(session_id, "discard_all")` — REMOVED. Replaced by `guard_candidate_or_abort()`.

**Route: `api_git_clear_history()`** (line 428):
- Line 428: `_check_staging_lock(session_id, "clear_history")` — REMOVED. Replaced by `guard_candidate_or_abort()`.

**Route: `api_git_restore()`** (lines 512-559):
- Line 515: `staging_mgr = get_staging_manager()` — REMOVED. Replaced by `guard_candidate_or_abort()`.
- Line 516: `staging_mgr.get_lock_owner()` — REMOVED.
- Line 548: `sm = get_staging_manager()` — REMOVED.
- Lines 550-557: `sm.save_staging({...StagingStatus.RESTORE_PENDING...})` — REMOVED. `guard_candidate_or_abort()` already ensures no candidate session is active. Restore-pending state is no longer written to staging; the commit audit log uses `get_audit_user_identity()` which is already called above (line 539).
- Line 559: `sm.clear_staging()` — REMOVED. No staging to clear.

12 staging references total (2 imports + 1 function definition with 3 internal calls + 8 `get_staging_manager()` calls across routes + `StagingStatus` usage). All accounted for.

| Removed Feature | Candidate Equivalent |
|----------------|---------------------|
| `_check_staging_lock()` | `guard_candidate_or_abort()` on destructive routes |
| Staging user identity | Candidate session stores `user_name`, `user_email` |
| `clear_staging()` after commit | Frontend calls `CandidateApi.clearAfterCommit()` |
| `save_staging(RESTORE_PENDING)` after restore | Not needed — guard ensures no candidate session active; restore context captured in existing audit log call |
| Missing audit log on `api_git_discard()` | Added `log_audit()` call (Commandment 3 fix) |

## Error Handling Audit

Every route in this file handles errors as follows (verified against Commandment 4):

| Route | Input validation | Operation errors | Unexpected exceptions |
|-------|-----------------|------------------|----------------------|
| `api_git_identity_get()` | N/A (GET) | N/A | `except Exception` → 500 |
| `api_git_identity_set()` | 400 if missing session/fields/email | 500 if save fails | `except Exception` → 500 |
| `api_git_status()` | N/A (GET) | `result.error` → 500 | `except Exception` → 500 |
| `api_git_diff()` | 400 if unsafe path | `result.error` → 500 | `except Exception` → 500 |
| `api_git_commit()` | 400 if no message/identity/bad files | `result.error` → 400 | `except Exception` → 500 |
| `api_git_discard()` | 400 if no file/unsafe path | `result.error` → 400 | `except Exception` → 500 |
| `api_git_discard_all()` | N/A | `result.error` → 400 | `except Exception` → 500 |
| `api_git_clear_history()` | 400 if no identity | `result.error` → 400 | `except Exception` → 500 |
| `api_git_log()` | N/A (GET) | `result.error` → 400 | `except Exception` → 500 |
| `api_git_restore()` | 400 if no hash/bad format | 404/400 on failure | `except Exception` → 500 |

All error paths return proper JSON error responses with appropriate HTTP status codes. No silent failures.

## Audit Logging Inventory

Every mutating route must have both app logging (`logger.*`) and audit logging (`log_audit()`). Status after this plan:

| Route | App logging | Audit logging |
|-------|-------------|---------------|
| `api_git_identity_set()` | N/A (identity-only, non-destructive) | N/A |
| `api_git_commit()` | `logger.info` at entry | `_write_commit_audit_log()` on success |
| `api_git_discard()` | `logger.info` at entry, `logger.error` on failure | **ADDED** `log_audit(action="git_discarded_file")` on success |
| `api_git_discard_all()` | `logger.info` at entry, `logger.error` on failure | `log_audit(action="git_discarded")` on success |
| `api_git_clear_history()` | `logger.warning` at entry, `logger.error` on failure | `log_audit(action="git_clear_history")` on success |
| `api_git_restore()` | N/A (via git_svc) | `log_audit(action="git_restored")` on success |

## Change Tracking

- [ ] Remove `from staging_manager import StagingStatus` import
- [ ] Remove `get_staging_manager` from helpers import
- [ ] Add `get_candidate_manager, guard_candidate_or_abort` to helpers import
- [ ] Delete `_check_staging_lock()` function (lines 24-43)
- [ ] Rewrite `_resolve_user_identity()` to use candidate manager (lines 46-63)
- [ ] Rewrite `_write_commit_audit_log()` to use candidate manager (lines 82-100)
- [ ] Rewrite `api_git_identity_get()` to use candidate manager (lines 103-134)
- [ ] Rewrite `api_git_identity_set()` to use candidate manager (lines 137-173)
- [ ] Remove `_check_staging_lock()` call from `api_git_commit()` (line 259)
- [ ] Remove `get_staging_manager().clear_staging()` from `_execute_commit()` (line 320)
- [ ] Add `guard_candidate_or_abort()` to `api_git_discard()` (line 344)
- [ ] Remove `_check_staging_lock()` from `api_git_discard()` (line 356)
- [ ] Add `log_audit()` call to `api_git_discard()` on success
- [ ] Add `guard_candidate_or_abort()` to `api_git_discard_all()` (line 382)
- [ ] Remove `_check_staging_lock()` from `api_git_discard_all()` (line 388)
- [ ] Add `guard_candidate_or_abort()` to `api_git_clear_history()` (line 422)
- [ ] Remove `_check_staging_lock()` from `api_git_clear_history()` (line 428)
- [ ] Add `guard_candidate_or_abort()` to `api_git_restore()` (line 498)
- [ ] Remove inline staging lock check from `api_git_restore()` (lines 514-521)
- [ ] Remove `save_staging(RESTORE_PENDING)` from `api_git_restore()` (lines 548-559)
- [ ] Remove `sm.clear_staging()` fallback from `api_git_restore()` (line 559)
- [ ] Run `ruff check routes/git.py` and fix any issues
- [ ] Run `ruff format routes/git.py`
- [ ] Run `python3 -m pytest tests/ -v` and verify all pass

## Verification

```bash
# Linting (Commandment 10)
ruff check routes/git.py
ruff format --check routes/git.py

# Unit tests
python3 -m pytest tests/ -v

# Smoke test: app starts without import errors
python3 -c "from app import create_app; create_app()"

# Verify no remaining staging references in this file
grep -n "staging" routes/git.py && echo "FAIL: staging references remain" || echo "PASS: no staging references"
grep -n "StagingStatus" routes/git.py && echo "FAIL: StagingStatus reference remains" || echo "PASS: no StagingStatus"
```

## Playwright Validation

Git routes are exercised by the git page UI. Playwright tests should verify:

- Commit flow works end-to-end (enter message, commit, see success)
- Discard file reverts the file and shows success
- Discard-all reverts all files and shows success
- Guard blocks git operations when a candidate session is active (409 response)

These tests are best written as part of the L09-git.md frontend plan (which modifies the git page UI) since the route changes here are purely backend and the existing tests in `tests/` cover the Python layer. The Playwright tests validate the integrated frontend + backend flow.

## Commandments Compliance

- [x] **1. No live config mutation until Apply.** Git routes operate on live config *after* apply. `guard_candidate_or_abort()` prevents destructive git ops during active candidate sessions. Rationale documented above.
- [x] **2. UI visual parity.** No UI changes in this plan (backend routes only). API contract preserved.
- [x] **3. Full audit logging.** All mutating routes have `log_audit()` calls. Added missing `log_audit()` to `api_git_discard()`. App logging via `logger.*` on all routes. Full inventory above.
- [x] **4. Proper error handling.** Error handling audit table above confirms all routes return proper HTTP status codes with JSON error payloads. No silent failures, no swallowed exceptions.
- [x] **5. Dead code deletion.** `_check_staging_lock()` deleted. `StagingStatus` import deleted. `get_staging_manager` import deleted. Zero staging references remain.
- [x] **6. Full functionality migration.** Lock checking migrated to `guard_candidate_or_abort()`. User identity migrated to candidate session. Commit audit log restore-pending check migrated to `cm.get_session_state()`. `clear_staging()` after commit migrated to frontend. Restore-pending staging save removed (not needed — guard ensures no candidate session). Migration table above.
- [x] **7. Palo Alto candidate model.** Staging references replaced with candidate manager calls. Guards enforce candidate session boundaries around destructive git operations.
- [x] **8. Change tracking document.** Itemized checklist above with 23 trackable items.
- [x] **9. Complete planning before implementation.** This plan fully specifies all changes, removals, replacements, and verification steps before any code is written.
- [x] **10. Linting enforcement.** Verification section includes `ruff check` and `ruff format --check` commands. Change tracking includes linting as explicit checklist items.
- [x] **11. Playwright validation.** Playwright test scope documented. Route-level changes are covered by unit tests; integrated UI flow tests deferred to L09-git.md where the frontend is modified.
