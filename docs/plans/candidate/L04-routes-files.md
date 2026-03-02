# L04: routes/files.py — MODIFY

**Layer:** 4 — Route Cleanup
**Action:** MODIFY
**Path:** `routes/files.py`
**Dependencies:** L03 (candidate file operation routes exist)
**Goal:** Remove 9 staging/direct-write routes and all associated dead helper functions/imports. Keep GET endpoints.

---

## Routes to REMOVE

| Route | Candidate Equivalent | Reason |
|-------|---------------------|--------|
| `POST /api/files/create` | `POST /api/candidate/file/create` | Staging route replaced by candidate route (L03) |
| `POST /api/files/move` | `POST /api/candidate/file/move` | Staging route replaced by candidate route (L03) |
| `DELETE /api/files/<path>` | `POST /api/candidate/file/delete` | Staging route replaced by candidate route (L03) |
| `POST /api/folders` (create) | `POST /api/candidate/folder/create` | Staging route replaced by candidate route (L03) |
| `POST /api/folders/move` | `POST /api/candidate/folder/move` | Staging route replaced by candidate route (L03) |
| `DELETE /api/folders/<path>` | `POST /api/candidate/folder/delete` | Staging route replaced by candidate route (L03) |
| `POST /api/files/relocate` | None | Dead code: direct-write, zero JS callers, violates no-mutation-until-Apply |
| `POST /api/folders/relocate` | None | Dead code: direct-write, zero JS callers, violates no-mutation-until-Apply |
| `POST /api/delete` (batch) | None | Dead code: direct-write, zero JS callers, violates no-mutation-until-Apply |

**Dead code verification:** `grep -r "api/files/relocate\|api/folders/relocate\|api/delete" static/` returns zero hits. The only references are in `templates/docs/api-reference.html` (documentation), which is updated separately in L14-api-reference.md.

## Routes to KEEP

| Route | Reason |
|-------|--------|
| `GET /api/files` | Used by explorer to list config files. Read-only, no mutation. |
| `GET /api/folders` | Used by explorer to list folders. Read-only, no mutation. |

## Helper Functions to REMOVE

All helper functions in this file (except the blueprint and GET routes) become dead code when the routes are removed:

| Function | Lines | Used By | Action |
|----------|-------|---------|--------|
| `ensure_staging_lock()` | 37-70 | 6 staging routes (all being deleted) | DELETE |
| `is_safe_path()` wrapper | 25-34 | `POST /api/files/create` only (being deleted) | DELETE |
| `_validate_move_paths()` | 77-100 | `POST /api/files/move`, `POST /api/folders/move` (both being deleted) | DELETE |
| `_validate_relocate_paths()` | 103-117 | `POST /api/files/relocate`, `POST /api/folders/relocate` (both being deleted) | DELETE |
| `_validate_relocate_file_exists()` | 120-131 | `POST /api/files/relocate` only (being deleted) | DELETE |
| `_validate_relocate_folder_exists()` | 134-147 | `POST /api/folders/relocate` only (being deleted) | DELETE |

## Imports to REMOVE

Imports that become unused after all routes and helpers above are deleted:

| Import | Line | Used By (all being deleted) | Action |
|--------|------|-----------------------------|--------|
| `import os` | 4 | All route functions + helpers | KEEP — still used by `GET /api/files` and `GET /api/folders` |
| `import shutil` | 5 | `api_relocate_file()`, `api_relocate_folder()`, `api_delete_path()` | DELETE |
| `from file_operations import is_safe_path as file_ops_is_safe_path` | 9 | `is_safe_path()` wrapper (being deleted) | DELETE |
| `get_audit_user_identity` | 12 | `ensure_staging_lock()` (being deleted) | DELETE |
| `get_backup_manager` | 13 | `api_relocate_file()`, `api_relocate_folder()`, `api_delete_path()` | DELETE |
| `get_parser_for_modification` | 15 | `api_relocate_file()`, `api_relocate_folder()` | DELETE |
| `get_service` | 16 | `api_relocate_file()`, `api_relocate_folder()`, `api_delete_path()` | DELETE |
| `get_staging_manager` | 17 | `ensure_staging_lock()` + 6 staging routes | DELETE |
| `operation_response` | 18 | `api_create_file()` | DELETE |
| `import re` (inline) | 208, 264 | `api_create_file()`, `api_create_folder()` | DELETE (removed with routes) |

**Imports to KEEP** (used by GET endpoints or blueprint):

| Import | Used By |
|--------|---------|
| `import logging` | `logger` definition |
| `import os` | `GET /api/files`, `GET /api/folders` |
| `from flask import Blueprint, jsonify` | Blueprint, GET route responses |
| `from .helpers import get_config_path` | `GET /api/files`, `GET /api/folders` |

Note: `request` from Flask is no longer needed (only GET routes remain, they don't use `request`). REMOVE from Flask import.

## Removal Audit — Staging References

**Import: `get_staging_manager`** (line 17):
- Imported from `.helpers` — REMOVE. Only used by staging routes being deleted.

**Function: `ensure_staging_lock()` definition** (lines 37-70):
- Lines 37-41: Function signature and docstring — REMOVE entire function.
- Line 45: `sm = get_staging_manager()` — removed with function.
- Lines 53-58: Creates staging dict with `sessionId`, `userName`, `userEmail` and calls `sm.save_staging(staging)` — removed with function.
- Line 59: `"Failed to acquire staging lock"` error text — removed with function.
- Line 68: `"Staging is locked by another user"` error text — removed with function.
- Not replaced; candidate routes use `cm.can_modify(session_id)` directly.

**7 `get_staging_manager()` calls** (all inside route functions being deleted):
- Line 45: in `ensure_staging_lock()` — REMOVED with function.
- Line 235: in `POST /api/files/create` route — REMOVED with route.
- Line 281: in `POST /api/folders` create route — REMOVED with route.
- Line 324: in `POST /api/files/move` route — REMOVED with route.
- Line 371: in `POST /api/folders/move` route — REMOVED with route.
- Line 515: in `DELETE /api/files/<path>` route — REMOVED with route.
- Line 559: in `DELETE /api/folders/<path>` route — REMOVED with route.

**`sm.stage_*` method calls** (all inside route functions being deleted):
- Line 236: `sm.stage_file_creation(file_path)` — REMOVED with route. Replaced by `CandidateApi.createFile()`.
- Line 282: `sm.stage_folder_creation(abs_folder_path)` — REMOVED with route. Replaced by `CandidateApi.createFolder()`.
- Line 325: `sm.stage_file_move(abs_source, target_path)` — REMOVED with route. Replaced by `CandidateApi.moveFile()`.
- Line 372: `sm.stage_folder_move(abs_source, target_path)` — REMOVED with route. Replaced by `CandidateApi.moveFolder()`.
- Line 516: `sm.stage_file_deletion(abs_path)` — REMOVED with route. Replaced by `CandidateApi.deleteFile()`.
- Line 560: `sm.stage_folder_deletion(abs_path)` — REMOVED with route. Replaced by `CandidateApi.deleteFolder()`.

**6 `ensure_staging_lock(session_id)` calls** (all inside route functions being deleted):
- Line 230: in `POST /api/files/create` — REMOVED with route.
- Line 276: in `POST /api/folders` create — REMOVED with route.
- Line 319: in `POST /api/files/move` — REMOVED with route.
- Line 366: in `POST /api/folders/move` — REMOVED with route.
- Line 510: in `DELETE /api/files/<path>` — REMOVED with route.
- Line 554: in `DELETE /api/folders/<path>` — REMOVED with route.

15 staging references total (1 import + 1 function definition + 7 `get_staging_manager()` calls + 6 `sm.stage_*` calls). All removed with their enclosing routes. No replacements needed in this file — candidate equivalents live in L03 routes.

## Audit Logging Note

The routes being removed have **zero audit logging** — no `log_audit()` calls exist anywhere in the current `routes/files.py`. The only logging is two `logger.debug` calls inside the dead-code `api_relocate_folder()` route. The candidate equivalents in L03-routes-candidate.md include full audit logging for all file/folder operations at apply time, which is an improvement over the current state.

## Functionality Migration Summary

| Current Route | Useful? | Migration |
|---------------|---------|-----------|
| `POST /api/files/create` (staging) | Yes | Migrated to `POST /api/candidate/file/create` (L03) |
| `POST /api/files/move` (staging) | Yes | Migrated to `POST /api/candidate/file/move` (L03) |
| `DELETE /api/files/<path>` (staging) | Yes | Migrated to `POST /api/candidate/file/delete` (L03) |
| `POST /api/folders` create (staging) | Yes | Migrated to `POST /api/candidate/folder/create` (L03) |
| `POST /api/folders/move` (staging) | Yes | Migrated to `POST /api/candidate/folder/move` (L03) |
| `DELETE /api/folders/<path>` (staging) | Yes | Migrated to `POST /api/candidate/folder/delete` (L03) |
| `POST /api/files/relocate` | No | Dead code — zero JS callers, direct-write, violates Commandment 1 |
| `POST /api/folders/relocate` | No | Dead code — zero JS callers, direct-write, violates Commandment 1 |
| `POST /api/delete` (batch) | No | Dead code — zero JS callers, direct-write, violates Commandment 1 |

**Key validation behaviors preserved in candidate equivalents:**
- `.cfg` extension enforcement (file create)
- Invalid character rejection in filenames/folder names
- `is_safe_path()` / path traversal protection
- Source existence checks (move/delete)
- Circular move prevention (folder move)
- Config root deletion prevention (folder delete)
- Lock/session ownership checks

## Change Tracking

- [ ] 1. Delete `ensure_staging_lock()` function (lines 37-70)
- [ ] 2. Delete `is_safe_path()` wrapper function (lines 25-34)
- [ ] 3. Delete `_validate_move_paths()` function (lines 77-100)
- [ ] 4. Delete `_validate_relocate_paths()` function (lines 103-117)
- [ ] 5. Delete `_validate_relocate_file_exists()` function (lines 120-131)
- [ ] 6. Delete `_validate_relocate_folder_exists()` function (lines 134-147)
- [ ] 7. Delete `api_create_file()` route (lines 189-243)
- [ ] 8. Delete `api_create_folder()` route (lines 246-292)
- [ ] 9. Delete `api_move_file()` route (lines 295-335)
- [ ] 10. Delete `api_move_folder()` route (lines 338-382)
- [ ] 11. Delete `api_relocate_file()` route (lines 385-431)
- [ ] 12. Delete `api_relocate_folder()` route (lines 434-485)
- [ ] 13. Delete `api_delete_file()` route (lines 488-525)
- [ ] 14. Delete `api_delete_folder()` route (lines 528-569)
- [ ] 15. Delete `api_delete_path()` route (lines 572-626)
- [ ] 16. Remove unused imports: `shutil`, `file_ops_is_safe_path`, `get_audit_user_identity`, `get_backup_manager`, `get_parser_for_modification`, `get_service`, `get_staging_manager`, `operation_response`, `request`
- [ ] 17. Keep: `logging`, `os`, `Blueprint`, `jsonify`, `get_config_path`, `bp`, `logger`, `api_files()`, `api_list_folders()`
- [ ] 18. Run Ruff linter — verify no unused imports, no lint errors
- [ ] 19. Run `python3 -c "from app import create_app; create_app()"` — verify app starts
- [ ] 20. Run `python3 -m pytest tests/ -v` — verify all tests pass

## Expected Result

After this change, `routes/files.py` should contain approximately 35 lines:

```python
"""File and folder management routes."""

import logging
import os

from flask import Blueprint, jsonify

from .helpers import get_config_path

bp = Blueprint("files", __name__)
logger = logging.getLogger("nagios_bulk_editor.files")


@bp.route("/api/files")
def api_files():
    """Get list of all .cfg files in the config directory."""
    config_dir = get_config_path()
    files = []

    if os.path.exists(config_dir):
        for root, dirs, filenames in os.walk(config_dir):
            dirs[:] = [d for d in dirs if d not in ("backups", "backup")]
            for filename in filenames:
                if filename.endswith(".cfg"):
                    files.append(os.path.join(root, filename))

    return jsonify({"files": sorted(files)})


@bp.route("/api/folders", methods=["GET"])
def api_list_folders():
    """List all folders in the config directory."""
    config_dir = get_config_path()
    folders = []

    if os.path.exists(config_dir):
        for root, dirs, _files in os.walk(config_dir):
            dirs[:] = [d for d in dirs if d not in ["backups", "backup"] and not d.startswith(".")]

            for d in dirs:
                folder_path = os.path.join(root, d)
                folders.append(folder_path)

    return jsonify({"folders": sorted(folders)})
```

## Verification

```bash
# Lint check (Commandment 10)
python3 -m ruff check routes/files.py

# App startup
python3 -c "from app import create_app; create_app()"

# Full test suite
python3 -m pytest tests/ -v
```

## Playwright Validation

Not applicable for this change. This is a backend-only route removal. The GET endpoints (`/api/files`, `/api/folders`) are unchanged. The removed mutation routes are replaced by candidate routes (L03) which are tested in `tests/test_candidate_routes.py`. Frontend E2E tests for file/folder operations are covered by L08-file-operations.md's Playwright plan, which tests the new candidate flow end-to-end.

---

## Commandments Compliance

- [x] **1. No live config mutation until Apply.** The three dead-code direct-write routes (`/api/files/relocate`, `/api/folders/relocate`, `/api/delete`) that violated this commandment are deleted. The six staging routes are replaced by candidate equivalents (L03) that edit the candidate directory only; nothing touches live config until Apply.
- [x] **2. UI visual parity.** This is a backend-only route removal. No UI changes. The two GET endpoints that the explorer UI depends on are preserved unchanged.
- [x] **3. Full audit logging.** The removed routes had zero audit logging (no `log_audit()` calls). The candidate replacements in L03-routes-candidate.md include full per-operation audit logging at apply time. Net improvement.
- [x] **4. Proper error handling.** No error handling is lost. The validation behaviors (path safety, extension enforcement, existence checks, circular move prevention) are all preserved in the candidate equivalents. No exceptions are swallowed. Unused error-handling helpers are deleted as dead code, not left dangling.
- [x] **5. Dead code deletion.** All 9 route functions, 6 helper functions, and 9 unused imports are deleted. Zero dead code remains. Every function and import in the resulting file is actively used.
- [x] **6. Full functionality migration.** All 6 useful staging routes are migrated to candidate equivalents in L03. All validation behaviors are preserved. The 3 dead-code direct-write routes have zero JS callers and are correctly deleted without replacement. Migration summary table documents each route's disposition.
- [x] **7. Palo Alto candidate model.** Removing old staging routes is required for the transition. File/folder operations now go through the candidate directory (copy, edit, apply) per the Palo Alto model.
- [x] **8. Change tracking document.** 20-item tickable checklist provided in "Change Tracking" section covering every deletion, cleanup, and verification step.
- [x] **9. Complete planning before implementation.** Plan includes: routes to remove/keep, helper functions to remove, imports to remove/keep, removal audit with line numbers, functionality migration summary, expected result with full code listing, verification steps.
- [x] **10. Linting enforcement.** Verification section includes `python3 -m ruff check routes/files.py`. Expected result code listing is clean (no unused imports, no lint issues).
- [x] **11. Playwright validation.** Explicitly noted as not applicable for this backend-only change. Frontend E2E coverage for file/folder operations is delegated to L08-file-operations.md.
