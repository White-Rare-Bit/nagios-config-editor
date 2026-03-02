# L03: tests/test_candidate_routes.py — CREATE

**Layer:** 3 — App Wiring + Routes
**Action:** CREATE
**Path:** `tests/test_candidate_routes.py`
**Dependencies:** L03-routes-candidate.md, L03-app.md
**Goal:** Test suite for candidate API routes (~30 tests).

---

## Fixtures

### `config_dir`
Creates temp directory with `hosts.cfg` (2 hosts) and `services.cfg` (1 service). Same as test_candidate_manager.py fixtures.

### `candidate_app(config_dir)`
Creates Flask app via `create_app()` with config pointing to `config_dir`. Returns app.

### `client(candidate_app)`
Returns `candidate_app.test_client()`.

## Test Classes

### TestSessionLifecycleRoutes (6 tests)
- `test_init_creates_session` — POST /api/candidate/init with X-Session-Id header
- `test_init_requires_session_header` — POST without header returns 400
- `test_status_no_session` — GET /api/candidate returns {active: false}
- `test_status_after_init` — GET /api/candidate returns {active: true, session_id: ...}
- `test_discard` — DELETE /api/candidate after init
- `test_double_init_fails` — second POST /api/candidate/init returns error

### TestCandidateObjectRoutes (3 tests)
- `test_objects_returns_list` — GET /api/candidate/objects returns JSON array
- `test_source_file_uses_running_path` — source_file in response uses running path, not .candidate/ path
- `test_objects_without_session_returns_404` — GET without init returns 404

### TestCandidateEditRoutes (2 tests)
- `test_edit_accepts_running_path` — POST /api/candidate/edit with running-config path
- `test_edit_locked_returns_423` — POST with wrong session ID returns 423

### TestCandidateUndoRoute (1 test)
- `test_undo_after_edit` — edit then undo, verify reverted

### TestCandidateDiffRoute (1 test)
- `test_diff_after_edit` — edit then GET /api/candidate/diff, verify changed_files

### TestCandidateApplyRoute (4 tests)
- `test_apply_updates_running` — apply then check running config
- `test_apply_creates_backup` — verify backup zip exists
- `test_apply_blocked_by_conflicts` — modify running file externally, apply returns 409
- `test_apply_with_defer_clear` — apply with deferClear=true, session stays alive

### TestCandidateFileRoutes (2 tests)
- `test_files_returns_normalized_paths` — GET /api/candidate/files returns running paths
- `test_folders_returns_normalized_paths` — GET /api/candidate/folders returns running paths

### TestCandidateCreateRoute (1 test)
- `test_create_object` — POST /api/candidate/create

### TestCandidateMoveRoute (1 test)
- `test_move_object` — POST /api/candidate/move

### TestCandidateDeleteObjectsRoute (1 test)
- `test_delete_objects` — POST /api/candidate/delete-objects

### TestCandidateBulkRoutes (2 tests)
- `test_bulk_edit` — POST /api/candidate/bulk-edit
- `test_bulk_move` — POST /api/candidate/bulk-move

### TestCandidateFileOperationRoutes (6 tests)
- `test_create_file` / `test_create_file_adds_cfg` / `test_create_file_rejects_bad_name`
- `test_delete_file` / `test_create_folder` / `test_delete_folder`

### TestCandidateConflictsRoute (1 test)
- `test_conflicts_none_initially`

### TestCandidateClearRoute (1 test)
- `test_clear_after_deferred_apply`

### TestCandidateGuards (7 tests)
- Tests for guard_candidate_or_abort() on admin routes:
- `test_backup_restore_blocked` / `test_git_discard_blocked` / `test_git_discard_all_blocked`
- `test_git_restore_blocked` / `test_git_clear_history_blocked`
- `test_backup_restore_allowed_without_session` / `test_git_discard_allowed_without_session`

## Change Tracking

- [ ] Create `tests/test_candidate_routes.py`
- [ ] **Fixtures:**
  - [ ] `config_dir` — temp directory with sample .cfg files
  - [ ] `candidate_app(config_dir)` — Flask app via create_app()
  - [ ] `client(candidate_app)` — test client
- [ ] **TestSessionLifecycleRoutes (6 tests):**
  - [ ] `test_init_creates_session`
  - [ ] `test_init_requires_session_header`
  - [ ] `test_status_no_session`
  - [ ] `test_status_after_init`
  - [ ] `test_discard`
  - [ ] `test_double_init_fails`
- [ ] **TestCandidateObjectRoutes (3 tests):**
  - [ ] `test_objects_returns_list`
  - [ ] `test_source_file_uses_running_path`
  - [ ] `test_objects_without_session_returns_404`
- [ ] **TestCandidateEditRoutes (2 tests):**
  - [ ] `test_edit_accepts_running_path`
  - [ ] `test_edit_locked_returns_423`
- [ ] **TestCandidateUndoRoute (1 test):**
  - [ ] `test_undo_after_edit`
- [ ] **TestCandidateDiffRoute (1 test):**
  - [ ] `test_diff_after_edit`
- [ ] **TestCandidateApplyRoute (4 tests):**
  - [ ] `test_apply_updates_running`
  - [ ] `test_apply_creates_backup`
  - [ ] `test_apply_blocked_by_conflicts`
  - [ ] `test_apply_with_defer_clear`
- [ ] **TestCandidateFileRoutes (2 tests):**
  - [ ] `test_files_returns_normalized_paths`
  - [ ] `test_folders_returns_normalized_paths`
- [ ] **TestCandidateCreateRoute (1 test):**
  - [ ] `test_create_object`
- [ ] **TestCandidateMoveRoute (1 test):**
  - [ ] `test_move_object`
- [ ] **TestCandidateDeleteObjectsRoute (1 test):**
  - [ ] `test_delete_objects`
- [ ] **TestCandidateBulkRoutes (2 tests):**
  - [ ] `test_bulk_edit`
  - [ ] `test_bulk_move`
- [ ] **TestCandidateFileOperationRoutes (6 tests):**
  - [ ] `test_create_file`
  - [ ] `test_create_file_adds_cfg`
  - [ ] `test_create_file_rejects_bad_name`
  - [ ] `test_delete_file`
  - [ ] `test_create_folder`
  - [ ] `test_delete_folder`
- [ ] **TestCandidateConflictsRoute (1 test):**
  - [ ] `test_conflicts_none_initially`
- [ ] **TestCandidateClearRoute (1 test):**
  - [ ] `test_clear_after_deferred_apply`
- [ ] **TestCandidateGuards (7 tests):**
  - [ ] `test_backup_restore_blocked`
  - [ ] `test_git_discard_blocked`
  - [ ] `test_git_discard_all_blocked`
  - [ ] `test_git_restore_blocked`
  - [ ] `test_git_clear_history_blocked`
  - [ ] `test_backup_restore_allowed_without_session`
  - [ ] `test_git_discard_allowed_without_session`

## Verification

```bash
python3 -m pytest tests/test_candidate_routes.py -v
# Expected: ~30 tests, all passing
python3 -m ruff check tests/test_candidate_routes.py
python3 -m ruff format --check tests/test_candidate_routes.py
```

## Commandments Compliance

- [x] **C1 — No live config mutation until Apply.** Tests verify this directly: object routes operate on candidate only, apply is the sole mutation path to running config, and `test_apply_updates_running` confirms the apply-only write behavior.
- [x] **C2 — UI visual parity.** N/A — test file, no UI. Tests do verify path normalization (`test_source_file_uses_running_path`, `test_files_returns_normalized_paths`) which supports frontend visual parity.
- [x] **C3 — Full audit logging.** N/A — test infrastructure. Audit logging behavior is tested indirectly through the routes being exercised; dedicated audit log assertions can be added if needed.
- [x] **C4 — Proper error handling.** Tests explicitly validate error responses: 400 (missing header), 404 (no session), 423 (locked), 409 (conflicts/guard). Each error path has a dedicated test.
- [x] **C5 — Dead code deletion.** N/A — new test file; no dead code.
- [x] **C6 — Full functionality migration.** All ~26 candidate routes have corresponding test coverage. Guard tests verify admin routes are blocked during candidate sessions.
- [x] **C7 — Palo Alto candidate model.** Tests validate the full copy-edit-apply lifecycle: init (copy), edit/create/move/delete (candidate ops), apply (copy back to running).
- [x] **C8 — Change tracking.** Tickable checklist added above covering all ~30 tests organized by test class.
- [x] **C9 — Complete planning before implementation.** All test classes, test names, and expected behaviors specified before any test code is written.
- [x] **C10 — Linting enforcement.** Ruff check and format commands included in Verification section.
- [x] **C11 — Playwright validation.** N/A — unit/integration test file. Playwright tests are planned for UI validation in later layers. These pytest tests validate the API contract that Playwright tests will exercise through the frontend.
