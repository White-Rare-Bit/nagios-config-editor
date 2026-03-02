# L04: routes/bulk_ops.py — MODIFY

**Layer:** 4 — Route Cleanup
**Action:** MODIFY
**Path:** `routes/bulk_ops.py`
**Dependencies:** L03 (candidate routes registered with bulk-edit/bulk-move equivalents)
**Goal:** Remove staging mutation routes and their helper functions. Keep search/preview/diff. Clean up dead imports.

---

## Routes to REMOVE

| Route | Lines | Candidate Equivalent | Why Remove |
|-------|-------|---------------------|------------|
| `POST /api/apply-rename` | 224-322 | `POST /api/candidate/bulk-edit` (L03-routes-candidate.md) | Stages renames via old `StagingManager` — candidate system edits files directly in candidate dir |
| `POST /api/move-objects` | 325-395 | `POST /api/candidate/bulk-move` (L03-routes-candidate.md) | Stages moves via old `StagingManager` — candidate system moves files directly in candidate dir |

Both routes use `get_staging_manager()`, `sm.can_modify()`, `sm.stage_bulk_rename()`, `sm.stage_bulk_move()` — all StagingManager methods that no longer exist after L12. Removing them here in L04 prevents broken references during migration.

**Commandment 1 compliance:** These routes staged mutations (never wrote to live config directly). Their candidate equivalents in `routes/candidate.py` write to the candidate directory only — live config is not touched until Apply.

**Commandment 6 compliance:** Both operations are fully migrated:
- `api_apply_rename` → `POST /api/candidate/bulk-edit` handles name changes + reference updates in candidate
- `api_move_objects` → `POST /api/candidate/bulk-move` handles object relocation in candidate

## Routes to KEEP

| Route | Lines | Reason |
|-------|-------|--------|
| `POST /api/search` | 160-176 | Read-only search against live parser. No staging dependency. |
| `POST /api/preview-rename` | 179-221 | Read-only preview (computes renames without applying). No staging dependency. |
| `POST /api/diff/rename` | 398-431 | Read-only diff generation. Uses `copy.deepcopy` on copies — never mutates live config. No staging dependency. |

All three kept routes are pure reads against `get_service().parser` — they never call `get_staging_manager()` and never mutate any state.

## Helper Functions to REMOVE (dead code after route removal)

These helper functions are used ONLY by the removed routes. Per Commandment 5, delete them.

| Function | Lines | Used By (removed route) |
|----------|-------|------------------------|
| `_validate_move_objects_input()` | 28-39 | `api_move_objects` only |
| `_resolve_and_validate_target()` | 42-55 | `api_move_objects` only |
| `_create_target_file_if_needed()` | 58-71 | DEAD CODE — not called by any route (was used by old direct-write move, superseded by staging) |
| `_move_objects_in_parser()` | 74-94 | DEAD CODE — not called by any route |
| `_parse_move_item()` | 97-109 | `api_move_objects` only (via `_validate_move_objects_input` call chain) |

Also remove the `api_move_objects helpers` section comment (lines 24-26) and the `Route handlers` section comment (lines 156-158).

## Helper Functions to KEEP

| Function | Lines | Used By (kept route) |
|----------|-------|---------------------|
| `_group_objects_by_file()` | 116-123 | `api_diff_rename` |
| `_apply_renames_to_objects()` | 126-139 | `api_diff_rename` |
| `_generate_file_diffs()` | 142-153 | `api_diff_rename` |

Keep the `api_diff_rename helpers` section comment (lines 112-114).

## Imports to REMOVE

| Import | Line | Reason |
|--------|------|--------|
| `from staging_manager import generate_stable_key_for_object` | 12 | Only used by `api_move_objects` (removed). Stable key functions migrated to `nagios_model.py` in L02 — but this file no longer needs them. |
| `get_staging_manager` from `.helpers` | 17 | Only used by `api_apply_rename` and `api_move_objects` (both removed). |
| `get_config_path` from `.helpers` | 15 | Only used by `api_move_objects` (removed). |
| `REFERENCE_FIELDS` from `nagios_model` | 10 | Only used by `api_apply_rename` (removed). |

## Imports to KEEP

| Import | Line | Reason |
|--------|------|--------|
| `import copy` | 1 | Used by `api_diff_rename` (`copy.deepcopy`) |
| `import logging` | 2 | Used by logger |
| `import os` | 3 | Used by `_generate_file_diffs` (`os.path.basename`) |
| `from flask import Blueprint, jsonify, request` | 5 | Used by all kept routes |
| `import file_operations` | 9 | Used by `_generate_file_diffs` |
| `from nagios_model import NAME_FIELDS` | 10 | Used by `_apply_renames_to_objects` |
| `from nagios_writer import NagiosConfigWriter` | 11 | Used by `api_diff_rename` |
| `get_service` from `.helpers` | 14 | Used by all three kept routes |

**Note:** `REFERENCE_FIELDS` is removed from the `from nagios_model import ...` line, but `NAME_FIELDS` stays.

## Removal Audit

Complete line-by-line accounting of every staging reference in `routes/bulk_ops.py`:

| Line | Reference | Action |
|------|-----------|--------|
| 12 | `from staging_manager import generate_stable_key_for_object` | REMOVE — only caller (`api_move_objects`) is deleted |
| 15 | `get_config_path,` in helpers import | REMOVE — only caller (`api_move_objects`) is deleted |
| 17 | `get_staging_manager,` in helpers import | REMOVE — only callers (`api_apply_rename`, `api_move_objects`) are deleted |
| 227 | `sm = get_staging_manager()` in `api_apply_rename` | REMOVED with entire route |
| 245 | `if not sm.can_modify(session_id):` in `api_apply_rename` | REMOVED with entire route |
| 314 | `result = sm.stage_bulk_rename(session_id, renames)` in `api_apply_rename` | REMOVED with entire route |
| 328 | `sm = get_staging_manager()` in `api_move_objects` | REMOVED with entire route |
| 337 | `if not sm.can_modify(session_id):` in `api_move_objects` | REMOVED with entire route |
| 351 | `sm.file_ops.stage_file_creation(target_file)` in `api_move_objects` | REMOVED with entire route |
| 369 | `generate_stable_key_for_object(obj)` in `api_move_objects` | REMOVED with entire route |
| 385 | `result = sm.stage_bulk_move(session_id, moves)` in `api_move_objects` | REMOVED with entire route |

**11 staging references total. All accounted for. All removed.**

## Error Handling Audit

The three kept routes already have proper error handling per Commandment 4:

| Route | Error Handling |
|-------|---------------|
| `api_search` | Returns 400 if request body is not a dict |
| `api_preview_rename` | Returns 400 if `object_type` missing; returns 400 if regex is invalid (`transform_name` returns `None`) |
| `api_diff_rename` | Returns 400 if `object_type` missing |

No silent failures. No swallowed exceptions.

## Audit Logging Assessment

The three kept routes are **read-only** operations (search, preview, diff). Per Commandment 3:
- Read-only operations do not require audit log entries (audit_service.py logs mutations only).
- The `logger` instance is retained for application-level logging of errors and debug info.
- The removed mutation routes (`api_apply_rename`, `api_move_objects`) had logging via `logger.info()` — their candidate equivalents in `routes/candidate.py` include full audit logging (see L03-routes-candidate.md, Audit Logging section).

## UI Visual Parity

Per Commandment 2: No frontend changes in this plan. The bulk rename UI continues to call `POST /api/preview-rename` and `POST /api/diff/rename` for preview/diff. The actual "apply rename" button is rewired to `POST /api/candidate/bulk-edit` by the frontend migration in L08.

## Resulting File After Changes

After modification, `routes/bulk_ops.py` will contain:
- 3 routes: `api_search`, `api_preview_rename`, `api_diff_rename`
- 3 helper functions: `_group_objects_by_file`, `_apply_renames_to_objects`, `_generate_file_diffs`
- ~150 lines (down from ~432)

Imports after cleanup:
```python
import copy
import logging
import os

from flask import Blueprint, jsonify, request

import file_operations
from nagios_model import NAME_FIELDS
from nagios_writer import NagiosConfigWriter

from .helpers import get_service
```

## Change Tracking

| # | Change | Status |
|---|--------|--------|
| 1 | Remove `from staging_manager import generate_stable_key_for_object` | [ ] |
| 2 | Remove `get_config_path` from helpers import | [ ] |
| 3 | Remove `get_staging_manager` from helpers import | [ ] |
| 4 | Remove `REFERENCE_FIELDS` from nagios_model import | [ ] |
| 5 | Delete `_validate_move_objects_input()` function (lines 28-39) | [ ] |
| 6 | Delete `_resolve_and_validate_target()` function (lines 42-55) | [ ] |
| 7 | Delete `_create_target_file_if_needed()` function (lines 58-71) | [ ] |
| 8 | Delete `_move_objects_in_parser()` function (lines 74-94) | [ ] |
| 9 | Delete `_parse_move_item()` function (lines 97-109) | [ ] |
| 10 | Delete `api_move_objects helpers` section comment (lines 24-26) | [ ] |
| 11 | Delete `api_apply_rename()` route (lines 224-322) | [ ] |
| 12 | Delete `api_move_objects()` route (lines 325-395) | [ ] |
| 13 | Run `ruff check routes/bulk_ops.py` — fix any lint errors | [ ] |
| 14 | Run `ruff format routes/bulk_ops.py` — format | [ ] |

## Verification

```bash
# Lint (Commandment 10)
ruff check routes/bulk_ops.py
ruff format --check routes/bulk_ops.py

# App starts without error
python3 -c "from app import create_app; create_app()"

# Tests pass
python3 -m pytest tests/ -v

# Verify removed routes are gone
python3 -c "
from app import create_app
app = create_app()
rules = [r.rule for r in app.url_map.iter_rules()]
assert '/api/apply-rename' not in rules, 'apply-rename route still registered'
assert '/api/move-objects' not in rules, 'move-objects route still registered'
assert '/api/search' in rules, 'search route missing'
assert '/api/preview-rename' in rules, 'preview-rename route missing'
assert '/api/diff/rename' in rules, 'diff/rename route missing'
print('OK: routes verified')
"

# Verify no staging imports remain
python3 -c "
import ast, sys
with open('routes/bulk_ops.py') as f:
    tree = ast.parse(f.read())
for node in ast.walk(tree):
    if isinstance(node, ast.ImportFrom):
        if node.module and 'staging' in node.module:
            print(f'ERROR: staging import found: {node.module}', file=sys.stderr)
            sys.exit(1)
        for alias in node.names:
            if 'staging' in alias.name.lower():
                print(f'ERROR: staging name imported: {alias.name}', file=sys.stderr)
                sys.exit(1)
print('OK: no staging imports')
"
```

### Playwright Validation

Per Commandment 11: After this change, run a Playwright smoke test to confirm:
1. The bulk rename preview dialog still shows results (calls `POST /api/preview-rename`)
2. The bulk rename diff view still renders (calls `POST /api/diff/rename`)
3. The search functionality still works (calls `POST /api/search`)

These are read-only routes so the risk of regression is low, but a quick visual validation confirms the kept routes are still wired correctly after the dead code is removed.

---

## Commandments Compliance

- [x] **C1 — No live config mutation until Apply.** Removed routes were staging mutations (never wrote to live). Kept routes are read-only. Candidate equivalents write only to candidate dir.
- [x] **C2 — UI visual parity.** No frontend changes in this plan. Preview/diff/search UI unchanged.
- [x] **C3 — Full audit logging.** Removed mutation routes have candidate equivalents with full audit logging (L03). Kept routes are read-only (no audit needed). Application logger retained.
- [x] **C4 — Proper error handling.** All three kept routes return proper HTTP error codes (400, 500) for invalid input. No silent failures. No swallowed exceptions.
- [x] **C5 — Dead code deletion.** 5 helper functions, 2 route handlers, and 4 dead imports removed. `_create_target_file_if_needed` and `_move_objects_in_parser` are doubly dead (not called by any route even before this plan).
- [x] **C6 — Full functionality migration.** `api_apply_rename` migrated to `POST /api/candidate/bulk-edit`. `api_move_objects` migrated to `POST /api/candidate/bulk-move`. Both in L03-routes-candidate.md.
- [x] **C7 — Palo Alto candidate model.** Mutation routes removed from old staging system. Candidate equivalents follow copy-edit-apply pattern.
- [x] **C8 — Change tracking document.** 14-item change tracking checklist included above.
- [x] **C9 — Complete planning before implementation.** This plan fully specifies every removal, every kept item, every import change, and every verification step before any code is touched.
- [x] **C10 — Linting enforcement.** Verification section includes `ruff check` and `ruff format --check` steps.
- [x] **C11 — Playwright validation.** Playwright smoke test specified for the three kept routes (preview, diff, search).
