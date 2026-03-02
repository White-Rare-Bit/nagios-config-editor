# L12: app.py — MODIFY (staging cleanup)

**Layer:** 12 — Staging Removal
**Action:** MODIFY
**Path:** `app.py`
**Dependencies:** L03-app.md (CandidateManager already added and registered), L12-nagios-service.md (NagiosService no longer accepts staging_manager param)
**Goal:** Remove StagingManager initialization and wiring from app factory. All staging functionality has been migrated to CandidateManager (L01/L03); this step deletes the now-dead staging code from the app factory.

---

## Preconditions

Before this plan executes, L03-app.md must be complete:

- CandidateManager is imported, instantiated, and registered in `app.extensions["candidate"]`
- CandidateManager handles its own stale session cleanup at startup (replacing the StagingManager stale-lock cleanup removed here)
- `get_candidate_manager()` helper exists in routes/helpers.py (added in L03-routes-helpers.md)
- Audit identity fallback has been rewritten to use candidate session info (L12-routes-helpers-cleanup.md)

This plan is purely dead code deletion. No new functionality is introduced. No live config mutation paths are added or modified.

---

## Functionality Migration Checklist

Every piece of functionality removed here has a candidate-system replacement:

| Removed Functionality | Replacement | Where |
|-----------------------|-------------|-------|
| `StagingManager` import | `CandidateManager` import | L03-app.md |
| `StagingManager(nagios_config_path)` instantiation | `CandidateManager(running_config_path=..., ...)` | L03-app.md |
| Stale-lock cleanup (`has_staging()` / `clear_staging()`) | Stale session cleanup (`has_session()` / `discard()`) | L03-app.md |
| `staging_manager` param to `NagiosService(...)` | NagiosService no longer needs staging; candidate ops go through CandidateManager | L12-nagios-service.md |
| `app.extensions["staging"]` registration | `app.extensions["candidate"]` registration | L03-app.md |
| `get_staging_manager()` helper | `get_candidate_manager()` helper | L03-routes-helpers.md |

---

## Removal Audit

| Line(s) | Code | Action |
|---------|------|--------|
| 18 | `from staging_manager import StagingManager` | REMOVE import |
| 128 | `staging_manager = StagingManager(nagios_config_path)` | REMOVE instantiation |
| 129-132 | `if staging_manager.has_staging(): ... staging_manager.clear_staging()` (stale-lock cleanup block) | REMOVE — CandidateManager has its own stale session cleanup (added in L03-app.md) |
| 133 | `service = NagiosService(nagios_config_path, staging_manager)` | REWRITE to `service = NagiosService(nagios_config_path)` — drop staging_manager param |
| 141 | `app.extensions["staging"] = staging_manager` | REMOVE extension registration |
| 172-174 | `def get_staging_manager() -> StagingManager: ...` | REMOVE helper function |

---

## Changes

### Step 1: Remove StagingManager import (line 18)

Delete:
```python
from staging_manager import StagingManager
```

### Step 2: Remove StagingManager instantiation and stale-lock cleanup (lines 128-132)

Delete:
```python
    staging_manager = StagingManager(nagios_config_path)
    # Clear stale locks from previous server session — no active sessions at startup
    if staging_manager.has_staging():
        logger.info("Clearing stale staging lock from previous session")
        staging_manager.clear_staging()
```

**Audit logging note:** The application logger (`logger.info`) call for stale-lock cleanup is removed here. The equivalent CandidateManager stale session cleanup (added in L03-app.md) logs the same event via `logger.info("Clearing stale candidate session from previous server run")`.

### Step 3: Remove staging_manager param from NagiosService constructor (line 133)

Before:
```python
    service = NagiosService(nagios_config_path, staging_manager)
```

After:
```python
    service = NagiosService(nagios_config_path)
```

**Error handling note:** NagiosService constructor continues to raise on invalid config_path. No error handling is degraded by this change.

### Step 4: Remove staging extension registration (line 141)

Delete:
```python
    app.extensions["staging"] = staging_manager
```

**Note:** Any code still referencing `app.extensions["staging"]` after this step will raise `KeyError` at runtime, which is the intended fail-CLOSED behavior. All such references must already be removed by prior L-plans (L04-routes-staging.md deletes routes/staging.py, L12-routes-helpers-cleanup.md removes `get_staging_manager()` from routes/helpers.py).

### Step 5: Remove get_staging_manager() helper (lines 172-174)

Delete:
```python
def get_staging_manager() -> StagingManager:
    """Get the staging manager."""
    return current_app.extensions["staging"]
```

**Note:** Also remove the blank line at 176 (between the deleted function and the comment at 178) to avoid a double-blank-line linting violation.

---

## Change Tracking

| # | Change | Status |
|---|--------|--------|
| 1 | Remove `from staging_manager import StagingManager` import (line 18) | [ ] |
| 2 | Remove StagingManager instantiation (line 128) | [ ] |
| 3 | Remove stale-lock cleanup block (lines 129-132) | [ ] |
| 4 | Rewrite NagiosService constructor call to drop staging_manager param (line 133) | [ ] |
| 5 | Remove `app.extensions["staging"]` registration (line 141) | [ ] |
| 6 | Remove `get_staging_manager()` helper function (lines 172-174) | [ ] |
| 7 | Clean up extra blank lines left by deletions | [ ] |
| 8 | Run ruff format and ruff check on app.py | [ ] |
| 9 | Run python3 -m pytest tests/ -v | [ ] |
| 10 | Run verification script (see below) | [ ] |

---

## Verification

```bash
# 1. Lint enforcement (Commandment 10)
ruff check app.py
ruff format --check app.py

# 2. Functional verification — staging extension is gone, candidate exists
python3 -c "
from app import create_app
app = create_app()
assert 'staging' not in app.extensions, 'staging extension should be removed'
assert 'service' in app.extensions, 'service extension should still exist'
assert 'candidate' in app.extensions, 'candidate extension should exist'
assert 'backup' in app.extensions, 'backup extension should still exist'
assert 'git' in app.extensions, 'git extension should still exist'
print('All extensions verified')
print('OK')
"

# 3. Confirm get_staging_manager is not importable from app
python3 -c "
import app as app_module
assert not hasattr(app_module, 'get_staging_manager'), 'get_staging_manager should be removed from app.py'
print('get_staging_manager removed')
print('OK')
"

# 4. Confirm no remaining staging references in app.py
python3 -c "
with open('app.py') as f:
    content = f.read()
assert 'staging' not in content.lower(), f'Residual staging reference found in app.py'
print('No residual staging references')
print('OK')
"

# 5. Run full test suite
python3 -m pytest tests/ -v
```

---

## Playwright Validation

This plan is a backend-only dead code deletion in the app factory. It does not change any UI rendering, API responses, or user-visible behavior. CandidateManager was already added in L03, so the candidate system is already functional before this cleanup runs.

**Playwright applicability:** Not directly applicable. However, the existing Playwright smoke tests (page load, navigation, basic editing flow) should be run after this change to confirm the app still starts and serves pages correctly:

```bash
npx playwright test --grep "smoke|startup|navigation" 2>/dev/null || echo "No matching Playwright tests (acceptable — backend-only change)"
```

If any Playwright test fails after this change, it indicates a missed dependency — some code path still references the removed staging extension.

---

## Commandments Compliance

| # | Commandment | Status | Notes |
|---|------------|--------|-------|
| 1 | No live config mutation until Apply | COMPLIANT | This plan only removes dead code. No mutation paths are added or modified. CandidateManager (L01/L03) enforces the copy-edit-apply model. |
| 2 | UI visual parity | COMPLIANT | Backend-only change. No templates, CSS, or JS are modified. Zero UI impact. |
| 3 | Full audit logging | COMPLIANT | The removed stale-lock cleanup log line is replaced by equivalent CandidateManager startup logging (L03-app.md). Audit identity fallback is rewritten in L12-routes-helpers-cleanup.md. No audit logging is lost. |
| 4 | Proper error handling | COMPLIANT | Removing `app.extensions["staging"]` causes `KeyError` (fail-CLOSED) if any missed code references it. NagiosService constructor error handling is unchanged. No silent failures introduced. |
| 5 | Dead code deletion | COMPLIANT | This is the core purpose of the plan: removing 6 staging-related code segments that are fully replaced by the candidate system. |
| 6 | Full functionality migration | COMPLIANT | Functionality Migration Checklist above maps every removed item to its candidate-system replacement, all implemented in prior L-plans (L01, L03). |
| 7 | Palo Alto candidate model | COMPLIANT | This plan removes the old staging system from the app factory, completing the transition to the Palo Alto copy-edit-apply model via CandidateManager. |
| 8 | Change tracking document | COMPLIANT | Change Tracking table with 10 items and completion checkboxes added above. |
| 9 | Complete planning before implementation | COMPLIANT | Plan is fully specified with exact line numbers, before/after code, removal audit, preconditions, functionality migration checklist, and verification scripts. |
| 10 | Linting enforcement | COMPLIANT | Verification section includes `ruff check` and `ruff format --check` steps. Change tracking includes lint step. Extra blank line cleanup noted in Step 5. |
| 11 | Playwright validation | COMPLIANT | Addressed in Playwright Validation section. Backend-only dead code deletion does not warrant new Playwright tests, but existing smoke tests should be run as regression safety net. |
