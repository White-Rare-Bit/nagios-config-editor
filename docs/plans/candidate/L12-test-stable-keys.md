# L12: tests/test_stable_keys.py — MODIFY

**Layer:** 12 — Staging Removal
**Action:** MODIFY (update import source)
**Path:** `tests/test_stable_keys.py`
**Dependencies:** L02-nagios-model.md (stable key functions migrated to `nagios_model.py`), L12-staging-manager.md (deletes `staging_manager.py`)
**Goal:** Update the import of stable key functions from the deleted `staging_manager` module to their new home in `nagios_model`, ensuring all existing test coverage is preserved.

---

## Context

`tests/test_stable_keys.py` tests stable key generation and uniqueness for Nagios objects. It currently imports `generate_stable_key_for_object` from `staging_manager`. In L02, these functions were copied to `nagios_model.py`. In L12, `staging_manager.py` is deleted, so this import must point to the new location.

No test logic changes. No test additions or removals. The tests validate domain logic (stable key uniqueness for services with duplicate `service_description` on different hosts) that remains critical in the candidate model.

---

## Current State

The file imports one function from `staging_manager`:

```python
from staging_manager import generate_stable_key_for_object
```

It contains 3 test functions (96 lines total):
- `test_duplicate_service_descriptions_get_unique_keys` — verifies services with same `service_description` on different hostgroups get unique stable keys
- `test_find_object_by_stable_key_with_display_name` — verifies `find_object_by_stable_key()` resolves display-name-based keys
- `test_inheritance_api_resolves_correct_service` — verifies the `/api/templates/inheritance/<key>` endpoint finds the correct service

All three tests remain valid in the candidate model. `NagiosService.find_object_by_stable_key()` is retained (see L12-nagios-service.md). The inheritance API route is unchanged.

---

## Removal Audit

| Line | Current Code | Action | Reason |
|------|-------------|--------|--------|
| 11 | `from staging_manager import generate_stable_key_for_object` | REPLACE import source | Function migrated to `nagios_model.py` in L02. `staging_manager.py` deleted in L12. |

No dead code in this file — all 3 tests exercise live functionality (`NagiosService.find_object_by_stable_key`, `/api/templates/inheritance/` route) that is retained in the candidate model.

---

## Changes

### Step 1: Update import (line 11)

Before:
```python
from staging_manager import generate_stable_key_for_object
```

After:
```python
from nagios_model import generate_stable_key_for_object
```

This is the only change. All test functions, fixtures, and assertions remain identical.

---

## Verification

```bash
# All 3 tests pass with the updated import
python3 -m pytest tests/test_stable_keys.py -v

# No remaining imports from staging_manager in this file
grep -c "from staging_manager\|import staging_manager" tests/test_stable_keys.py
# Expected: 0

# Linting passes (ruff)
python3 -m ruff check tests/test_stable_keys.py
python3 -m ruff format --check tests/test_stable_keys.py
```

---

## Change Tracking

| # | Change | File | Status |
|---|--------|------|--------|
| 1 | Update `generate_stable_key_for_object` import from `staging_manager` to `nagios_model` | `tests/test_stable_keys.py` line 11 | PENDING |

Referenced in: L00-migration-inventory.md section 1.12 (`tests/test_stable_keys.py` — MODIFY (import) — [covered]).

---

## Commandments Compliance

| # | Commandment | Status | Notes |
|---|------------|--------|-------|
| 1 | No live config mutation until Apply | COMPLIANT | This plan modifies a test file only. No config mutation logic is touched. The tested stable key functions are pure (string formatting/parsing) with no side effects. |
| 2 | UI visual parity | N/A | Test file change only. No UI impact. |
| 3 | Full audit logging | N/A | Test file change only. No auditable operations affected. The tested API endpoint (`/api/templates/inheritance/`) is a read-only GET route with no audit logging requirement. |
| 4 | Proper error handling | COMPLIANT | No error handling paths are modified. All existing test assertions are preserved. |
| 5 | Dead code deletion | COMPLIANT | No dead code exists in this file. All 3 tests exercise retained functionality (`find_object_by_stable_key`, inheritance API route). The old import from `staging_manager` is replaced, not left behind. |
| 6 | Full functionality migration | COMPLIANT | All 3 tests are preserved with identical logic. The import change is the only modification — `generate_stable_key_for_object` in `nagios_model` is the same function (migrated in L02). |
| 7 | Palo Alto candidate model | COMPLIANT | The import change aligns with the candidate model: stable key functions live in `nagios_model.py` (domain layer), not in the deleted staging module. |
| 8 | Change tracking document | COMPLIANT | Change tracking table included above. Referenced in L00-migration-inventory.md. |
| 9 | Complete planning before implementation | COMPLIANT | This plan fully specifies the single-line change with current state, removal audit, step-by-step instructions, and verification commands. |
| 10 | Linting enforcement | COMPLIANT | Verification section includes `ruff check` and `ruff format --check` commands. |
| 11 | Playwright validation | N/A | Test file import change only. No UI behavior is affected. The inheritance API tested here is exercised by existing Playwright E2E tests if applicable. |
