# L12: routes/helpers.py — MODIFY (staging cleanup)

**Layer:** 12 — Staging Removal
**Action:** MODIFY
**Path:** `routes/helpers.py`
**Dependencies:** L03-routes-helpers.md (adds candidate helpers), L12-nagios-service.md (removes modification_context), L04-routes-staging.md (deletes staging.py — removes all callers of get_staging_manager from staging routes), L04-routes-objects.md (removes get_parser_for_modification import/calls), L04-routes-analysis.md (removes get_parser_for_modification import/calls), L04-routes-files.md (removes get_parser_for_modification import/calls, removes get_staging_manager import/calls), L04-routes-bulk-ops.md (removes get_staging_manager import/calls), L04-routes-backups.md (removes get_staging_manager import/calls), L04-routes-git.md (removes get_staging_manager import/calls)
**Goal:** Remove staging helper functions and rewrite audit identity to use candidate session.

---

## Context

After L03 adds candidate helpers and L04 removes/rewrites all route callers, two staging helpers in `routes/helpers.py` become dead code:

- `get_staging_manager()` — called by staging routes (deleted in L04-routes-staging.md), files routes, bulk_ops, backups, git routes (all rewritten in L04 plans to use candidate helpers instead)
- `get_parser_for_modification()` — wraps `NagiosService.modification_context()` which is removed in L12-nagios-service.md. Called by objects.py, analysis.py, files.py (all rewritten in L04 plans)

Additionally, `get_audit_user_identity()` falls back to staging data for user identity — this must be migrated to fall back to candidate session info instead.

Functions that are RETAINED unchanged:
- `operation_response()` (lines 9-32) — generic OperationResult-to-Flask-response converter, no staging references
- `get_config_path()` (lines 35-40) — reads server config, no staging references
- `get_server_config()` (lines 43-45) — reads server config, no staging references
- `get_config()` (lines 48-61) — backward compat dict, no staging references
- `get_service()` (lines 64-66) — returns NagiosService, no staging references
- `get_parser()` (lines 69-71) — read-only parser access, no staging references
- `get_backup_manager()` (lines 84-86) — returns backup manager, no staging references
- `get_git_service()` (lines 89-91) — returns git service, no staging references
- `format_audit_user()` (lines 121-132) — formats identity dict to string, no staging references. Callers: backups.py, git.py, candidate.py (all working correctly after migration)

---

## Removal Audit

| Line(s) | Code | Action | Reason |
|---------|------|--------|--------|
| 74-76 | `def get_parser_for_modification(): ...` | REMOVE | `modification_context()` removed from NagiosService in L12-nagios-service.md. All 6 call sites (objects.py x2, analysis.py x2, files.py x2) removed by L04 plans. |
| 79-81 | `def get_staging_manager(): ...` | REMOVE | StagingManager deleted in L12-staging-manager.md. All callers rewritten or deleted by L04 plans. |
| 95-118 | `def get_audit_user_identity(): ...` | REWRITE | Replace staging fallback with candidate session fallback (functionality migration, Commandment 6). |

### Caller Verification (get_parser_for_modification)

All callers are removed by their respective L04 plans BEFORE this L12 cleanup runs:

| File | Line | Call | Handled By |
|------|------|------|------------|
| `routes/objects.py` | 14, 58, 163 | import + 2 calls | L04-routes-objects.md (removes direct-write mutation routes) |
| `routes/analysis.py` | 27, 1356, 1405 | import + 2 calls | L04-routes-analysis.md (removes direct-write mutation routes) |
| `routes/files.py` | 15, 404, 457 | import + 2 calls | L04-routes-files.md (removes direct-write mutation routes) |

### Caller Verification (get_staging_manager)

All callers are removed/rewritten by their respective L04 plans BEFORE this L12 cleanup runs:

| File | Calls | Handled By |
|------|-------|------------|
| `routes/staging.py` | 15 calls | L04-routes-staging.md (entire file deleted) |
| `routes/bulk_ops.py` | 2 calls | L04-routes-bulk-ops.md (rewritten to candidate) |
| `routes/backups.py` | 2 calls | L04-routes-backups.md (rewritten to candidate guard) |
| `routes/git.py` | 8 calls | L04-routes-git.md (rewritten to candidate guard) |
| `routes/files.py` | 7 calls | L04-routes-files.md (rewritten to candidate ops) |
| `routes/helpers.py` | 1 call (in `get_audit_user_identity`) | This plan (Step 3 rewrites it) |
| `app.py` | 1 definition (module-level helper) | L12-app-cleanup.md (removes) |

---

## Changes

### Step 1: Remove `get_parser_for_modification()` (lines 74-76)

Delete:
```python
def get_parser_for_modification():
    """Get parser with lock held for modification operations."""
    return get_service().modification_context()
```

**Dead code deletion (Commandment 5):** This function wraps `NagiosService.modification_context()` which no longer exists after L12-nagios-service.md. Zero remaining callers after L04 plans execute.

### Step 2: Remove `get_staging_manager()` (lines 79-81)

Delete:
```python
def get_staging_manager():
    """Get the staging manager."""
    return current_app.extensions["staging"]
```

**Dead code deletion (Commandment 5):** StagingManager is deleted in L12-staging-manager.md. The `app.extensions["staging"]` key no longer exists after L12-app-cleanup.md. Zero remaining callers after L04 plans execute.

### Step 3: Rewrite `get_audit_user_identity()` (lines 95-118)

**Functionality migration (Commandment 6):** The fallback to staging data for user identity must be migrated to use candidate session info. The function signature and return type are unchanged — callers (`routes/backups.py`, `routes/git.py`, `routes/files.py`) require no updates.

**Audit logging preservation (Commandment 3):** This function is part of the audit logging chain (`get_audit_user_identity()` -> `format_audit_user()` -> audit log entry). The rewrite preserves the same identity resolution order: (1) request JSON body, (2) candidate session info fallback. No audit logging is lost.

**Error handling (Commandment 4):** The `try/except` block is preserved for the candidate session fallback. The `except Exception` with `pass` is intentional best-effort behavior — if the candidate manager is unavailable, we still return whatever identity we found from the request body rather than failing the entire operation.

Before:
```python
def get_audit_user_identity():
    """Get user identity for audit log entries.

    Checks request JSON body first, then staging data.
    Returns dict with userName and userEmail keys.
    """
    data = request.get_json(silent=True) or {}
    user_name = data.get("user_name") or data.get("userName")
    user_email = data.get("user_email") or data.get("userEmail")

    if not user_name or not user_email:
        try:
            sm = get_staging_manager()
            staging = sm.get_staging()
            if staging:
                user_name = user_name or staging.get("userName")
                user_email = user_email or staging.get("userEmail")
        except Exception:  # noqa: BLE001, S110
            pass  # Best-effort fallback to staging data for user identity

    return {
        "userName": user_name,
        "userEmail": user_email,
    }
```

After:
```python
def get_audit_user_identity():
    """Get user identity for audit log entries.

    Checks request JSON body first, then candidate session info.
    Returns dict with userName and userEmail keys.
    """
    data = request.get_json(silent=True) or {}
    user_name = data.get("user_name") or data.get("userName")
    user_email = data.get("user_email") or data.get("userEmail")

    if not user_name or not user_email:
        try:
            cm = get_candidate_manager()
            session_info = cm.get_session_info()
            if session_info:
                user_name = user_name or session_info.get("userName")
                user_email = user_email or session_info.get("userEmail")
        except Exception:  # noqa: BLE001, S110
            pass  # Best-effort fallback to candidate session for user identity

    return {
        "userName": user_name,
        "userEmail": user_email,
    }
```

**Note:** `get_candidate_manager()` is added by L03-routes-helpers.md and is already present in helpers.py at this layer. No new imports needed.

---

## What Remains After Cleanup

After this plan executes, `routes/helpers.py` contains these functions:

| Function | Lines | Purpose | Staging References |
|----------|-------|---------|-------------------|
| `operation_response()` | 9-32 | OperationResult to Flask response | None |
| `get_config_path()` | 35-40 | Get Nagios config path | None |
| `get_server_config()` | 43-45 | Get ServerConfig | None |
| `get_config()` | 48-61 | Backward-compat config dict | None |
| `get_service()` | 64-66 | Get NagiosService | None |
| `get_parser()` | 69-71 | Read-only parser | None |
| `get_backup_manager()` | ~72 | Get BackupManager | None |
| `get_git_service()` | ~75 | Get GitService | None |
| `get_candidate_manager()` | ~78 | Get CandidateManager (added L03) | None |
| `get_objects_for_request()` | ~82 | Candidate-aware object getter (added L03) | None |
| `get_parser_for_request()` | ~100 | Candidate-aware parser getter (added L03) | None |
| `guard_candidate_or_abort()` | ~120 | Block admin ops during candidate session (added L03) | None |
| `get_audit_user_identity()` | ~140 | Audit identity with candidate fallback (rewritten here) | None |
| `format_audit_user()` | ~158 | Format identity to "Name <email>" | None |

Zero staging references remain.

---

## Change Tracking

| # | Change | Status |
|---|--------|--------|
| 1 | Remove `get_parser_for_modification()` definition (lines 74-76) | [ ] |
| 2 | Remove `get_staging_manager()` definition (lines 79-81) | [ ] |
| 3 | Rewrite `get_audit_user_identity()` docstring (line 98: "staging data" -> "candidate session info") | [ ] |
| 4 | Rewrite `get_audit_user_identity()` body: `get_staging_manager()` -> `get_candidate_manager()` (line 107) | [ ] |
| 5 | Rewrite `get_audit_user_identity()` body: `sm.get_staging()` -> `cm.get_session_info()` (line 108) | [ ] |
| 6 | Rewrite `get_audit_user_identity()` body: `staging.get(...)` -> `session_info.get(...)` (lines 110-111) | [ ] |
| 7 | Rewrite `get_audit_user_identity()` comment: "staging data" -> "candidate session" (line 113) | [ ] |
| 8 | Verify `format_audit_user()` still works with rewritten identity dict (unchanged return shape) | [ ] |

---

## Verification

```bash
# Lint check (Commandment 10)
ruff check routes/helpers.py
ruff format --check routes/helpers.py

# Import verification
python3 -c "
from app import create_app
app = create_app()
with app.test_request_context('/'):
    from routes.helpers import get_audit_user_identity
    identity = get_audit_user_identity()
    print(f'Identity: {identity}')
    assert 'userName' in identity, 'Missing userName key'
    assert 'userEmail' in identity, 'Missing userEmail key'
    print('OK')
"

# Confirm removed functions are gone (Commandment 5)
python3 -c "
from routes import helpers
assert not hasattr(helpers, 'get_staging_manager'), 'get_staging_manager should be removed'
assert not hasattr(helpers, 'get_parser_for_modification'), 'get_parser_for_modification should be removed'
assert hasattr(helpers, 'get_candidate_manager'), 'get_candidate_manager should exist (added in L03)'
assert hasattr(helpers, 'get_audit_user_identity'), 'get_audit_user_identity should still exist'
assert hasattr(helpers, 'format_audit_user'), 'format_audit_user should still exist'
print('OK')
"

# Confirm no remaining staging references in helpers.py (Commandment 5)
grep -n 'staging\|StagingManager\|get_staging' routes/helpers.py && echo 'FAIL: staging references found' || echo 'PASS: no staging references'

# Confirm audit identity returns correct shape for format_audit_user (Commandment 3)
python3 -c "
from app import create_app
app = create_app()
with app.test_request_context('/'):
    from routes.helpers import get_audit_user_identity, format_audit_user
    identity = get_audit_user_identity()
    formatted = format_audit_user(identity)
    print(f'Formatted: {formatted!r}')
    print('OK')
"

# Full test suite
python3 -m pytest tests/ -v
```

---

## UI Visual Parity (Commandment 2)

This plan modifies only backend helper functions. No UI changes. No templates, CSS, or JavaScript affected. Visual parity is maintained by definition.

## Playwright Validation (Commandment 11)

This is a backend-only helper cleanup. The rewritten `get_audit_user_identity()` affects audit log content (user identity resolution), not UI behavior. Playwright tests are not applicable for this plan. However, any Playwright tests that exercise operations triggering audit logging (e.g., backup restore, git commit) will implicitly validate that the audit identity chain still works end-to-end.

---

## Commandments Compliance

| # | Commandment | Status | Notes |
|---|-------------|--------|-------|
| 1 | No live config mutation until Apply | COMPLIANT | Removed functions (`get_parser_for_modification`, `get_staging_manager`) were part of the old direct-mutation path. Their removal enforces the candidate model where all edits go through CandidateManager. No new mutation paths introduced. |
| 2 | UI visual parity | N/A | Backend-only change. No UI, templates, CSS, or JavaScript modified. |
| 3 | Full audit logging | COMPLIANT | `get_audit_user_identity()` is migrated (not removed) to use candidate session fallback. `format_audit_user()` is retained unchanged. The audit identity chain is fully preserved. |
| 4 | Proper error handling | COMPLIANT | The `try/except` in `get_audit_user_identity()` is preserved with best-effort fallback semantics. No silent failures introduced. |
| 5 | Dead code deletion | COMPLIANT | `get_parser_for_modification()` and `get_staging_manager()` are dead code after L04/L12 dependencies execute. Both are deleted. |
| 6 | Full functionality migration | COMPLIANT | `get_audit_user_identity()` staging fallback is migrated to candidate session fallback. Same return shape, same callers, same behavior. `format_audit_user()` works unchanged. |
| 7 | Palo Alto candidate model | COMPLIANT | Replaces staging-based identity lookup with candidate session-based identity lookup, consistent with the candidate configuration model. |
| 8 | Change tracking document | COMPLIANT | Change tracking table with 8 items added to this plan. |
| 9 | Complete planning before implementation | COMPLIANT | Full removal audit, caller verification tables, before/after code, and dependency chain documented before any code changes. |
| 10 | Linting enforcement | COMPLIANT | Verification section includes `ruff check` and `ruff format --check` commands. |
| 11 | Playwright validation | N/A | Backend-only helper cleanup. No UI behavior changes. Existing Playwright tests that trigger audit-logged operations provide implicit coverage. |
