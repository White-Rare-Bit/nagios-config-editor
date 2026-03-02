# Candidate Config — Implementation Index

## Overview

Replace the delta-based staging system with a file-copy candidate config system. Each file is touched exactly once — no dual-mode intermediate state.

**Total**: 14 layers, 70 file plans, ~90 file operations.

**Execution model**: Complete all file plans within a layer before moving to the next. Within a layer, files can be done in any order. Each layer ends with a verification gate.

**Per-file plan location**: `docs/plans/candidate/L<nn>-<filename>.md`

---

## Layer 1: Backend Core — New CandidateManager

Creates the CandidateManager from scratch. No existing code changes.

- [ ] `candidate_manager.py` — CREATE — Full CandidateManager: session lifecycle, object CRUD, file/folder ops, undo, diff, conflicts, validate, apply, bulk ops
- [ ] `tests/test_candidate_manager.py` — CREATE — ~60 tests covering all CandidateManager methods

**Phase gate**: `python3 -m pytest tests/test_candidate_manager.py -v` — all pass

---

## Layer 2: Backend Prep — Wire Into Existing Backend

Prepare existing backend to coexist with candidate system. Migrate stable keys, update exclusions. Safe additive changes only — no staging removal yet.

- [ ] `nagios_parser.py` — MODIFY — Add `.candidate/` to skip list
- [ ] `backup_manager.py` — MODIFY — Exclude `.candidate/` from backups, update error messages
- [ ] `nagios_model.py` — MODIFY — Receive 3 migrated stable key functions from `staging_manager.py`
- [ ] `git_service.py` — MODIFY — Replace `.staging/` with `.candidate/` in exclusions and `.gitignore`
- [ ] `tests/test_git_service.py` — MODIFY — Update `.staging/` to `.candidate/` assertion (keeps phase gate passing)
- [x] `tests/test_apply_robustness.py` — SKIP — Dead code; `_exec_delete` bug is in staging code deleted in L12

**Phase gate**: `python3 -m pytest tests/ -v` — all existing tests pass

---

## Layer 3: App Wiring + Routes

Register CandidateManager in app, create candidate API blueprint, add route helpers.

- [ ] `app.py` — MODIFY — Register CandidateManager in extensions (keep StagingManager for now, removed in L4)
- [ ] `routes/helpers.py` — MODIFY — Add `get_candidate_manager()`, `get_parser_for_request()`, `get_objects_for_request()`, `guard_candidate_or_abort()` (keep staging helpers for now, removed in L4)
- [ ] `routes/__init__.py` — MODIFY — Register candidate blueprint (keep staging blueprint for now, removed in L4)
- [ ] `routes/candidate.py` — CREATE — 20 candidate API endpoints
- [ ] `tests/test_candidate_routes.py` — CREATE — ~30 tests for candidate routes + guard tests

**Phase gate**: `python3 -m pytest tests/test_candidate_routes.py tests/test_candidate_manager.py -v`

---

## Layer 4: Route Cleanup — Remove Old Staging Routes

Remove staging endpoints and direct-write routes from existing route files.

- [ ] `routes/staging.py` — DELETE — Entire staging blueprint
- [ ] `routes/files.py` — MODIFY — Remove 9 staging/direct-write routes, keep GET endpoints
- [ ] `routes/objects.py` — MODIFY — Remove `POST /api/delete-objects`, `POST /api/clone-objects`
- [ ] `routes/analysis.py` — MODIFY — Remove staging mutation routes, add `?candidate=1` to read routes
- [ ] `routes/bulk_ops.py` — MODIFY — Remove `apply-rename`, `move-objects`; keep search/preview
- [ ] `routes/backups.py` — MODIFY — Replace staging lock checks with candidate guards
- [ ] `routes/git.py` — MODIFY — Replace staging refs with candidate session, add guards
- [ ] `routes/settings.py` — MODIFY — Replace StagingManager with CandidateManager in path update

**Phase gate**: `python3 -m pytest tests/ -v`, verify `python3 -c "from app import create_app; create_app()"`

---

## Layer 5: Route Analysis — Candidate-Aware Read Endpoints

Make read-only analysis/validation/template routes candidate-aware via `get_objects_for_request()`.

- [ ] `routes/validation.py` — MODIFY — Use `get_objects_for_request()` in 4 endpoints
- [ ] `routes/templates.py` — MODIFY — Use `get_objects_for_request()` in 3 endpoints

**Phase gate**: `python3 -m pytest tests/ -v`

---

## Layer 6: Frontend Foundation

Create CandidateApi wrapper, update script loading, rename session headers.

- [ ] `static/js/candidate-api.js` — CREATE — CandidateApi wrapper with all methods
- [ ] `static/js/session-manager.js` — MODIFY — Rename `getStagingHeaders` to `getSessionHeaders`
- [ ] `static/js/api-client.js` — MODIFY — Update call to `getSessionHeaders`
- [ ] `eslint.config.mjs` — MODIFY — Add CandidateApi + new globals, rename staging globals
- [ ] `templates/base.html` — MODIFY — Add `candidate-api.js` script tag, update lock banner text

**Phase gate**: App loads without JS errors, `npm run lint:js` passes

---

## Layer 7: Frontend State + Data Loading

Replace staging state with candidate state, rewrite data loading.

- [ ] `static/js/explorer/main.js` — MODIFY — Replace staging state fields with `candidateActive`, `candidateDiff`
- [ ] `static/js/explorer/state-management.js` — MODIFY — Remove staging helpers, add `computeCandidateBadges`
- [ ] `static/js/explorer/data-loading.js` — MODIFY — Rewrite `loadObjects()`/`startStagingPoll()`/undo/clear for candidate

**Phase gate**: Explorer loads, objects display, no console errors

---

## Layer 8: Frontend Editors

All edit/save/delete/move/create/undo operations go through CandidateApi.

- [ ] `static/js/explorer/object-editor.js` — MODIFY — Rewrite save/create/revert for candidate, add `?candidate=1` to inheritance fetch
- [ ] `static/js/explorer/dialogs.js` — MODIFY — Rewrite deletions/bulk rename for candidate
- [ ] `static/js/explorer/context-menu.js` — MODIFY — Rewrite move/bulk-attr/clone/rename for candidate, remove `getOrCreatePendingEdit()`
- [ ] `static/js/explorer/file-operations.js` — MODIFY — Rewrite all file/folder ops + bulk drag-drop for candidate

**Phase gate**: Edit a host, save, undo, delete, create — all work via candidate API. No console errors.

---

## Layer 9: Frontend Features

Commit dialog, git page, lock manager, nav badge, settings.

- [ ] `static/js/commit-dialog.js` — MODIFY — Rewrite for candidate diff, add apply+commit/apply-only/discard flows
- [ ] `static/js/git.js` — MODIFY — Replace staging diff with candidate diff, add candidate tab
- [ ] `templates/git.html` — NO CHANGE — Template provides container divs; JS generates content; CSS renames in L13
- [ ] `static/js/lock-manager.js` — MODIFY — Rewrite to poll candidate session instead of staging lock
- [ ] `static/js/base.js` — MODIFY — Rewrite `checkPendingChanges()` for candidate
- [ ] `static/js/settings.js` — MODIFY — Replace staging lock checks with candidate session checks

**Phase gate**: Commit dialog shows candidate diff, lock banner works, nav badges update

---

## Layer 10: Frontend Analysis

Add `?candidate=1` to all read-only analysis API calls, remove staging state refs.

- [ ] `static/js/explorer/analysis.js` — MODIFY — Add `?candidate=1` to 3 calls, remove staging state refs
- [ ] `static/js/explorer/analysis-issues.js` — MODIFY — Add `?candidate=1` to 1 call
- [ ] `static/js/explorer/analysis-suggestions.js` — MODIFY — Add `?candidate=1` to 3 calls, rewrite apply actions for candidate
- [ ] `static/js/explorer/badge-issues.js` — MODIFY — Add `?candidate=1` to 3 calls, remove `pendingEdits` refs
- [ ] `static/js/explorer/relations-loader.js` — MODIFY — Add `?candidate=1` to 3 calls
- [ ] `static/js/explorer/impact-section.js` — MODIFY — Add `?candidate=1` to 1 call, remove `pendingEdits` ref
- [ ] `static/js/dependencies.js` — MODIFY — Add candidate status check + suffix to dependency fetch

**Phase gate**: Analysis panels load in candidate mode, no console errors

---

## Layer 11: Frontend Cleanup

Remove remaining staging state references from UI modules.

- [ ] `static/js/explorer/app.js` — MODIFY — Remove `pendingEdits`/`stagedCreations`/`stagedMoves` refs, simplify attribute access
- [ ] `static/js/explorer/tab-manager.js` — MODIFY — Remove `pendingEdits.has()` check

**Phase gate**: Full explorer functional, `npm run lint:js` clean

---

## Layer 12: Test + Backend Cleanup

Delete obsolete staging code and tests, update imports in surviving tests.

- [ ] `staging_manager.py` — DELETE — Old staging manager
- [ ] `apply_verification.py` — DELETE — Old apply verification
- [ ] `tests/test_staging_integration.py` — DELETE (consolidated in L12-test-deletions.md)
- [ ] `tests/test_composite_apply.py` — DELETE (consolidated in L12-test-deletions.md)
- [ ] `tests/test_apply_verification.py` — DELETE (consolidated in L12-test-deletions.md)
- [ ] `tests/test_apply_robustness.py` — DELETE (consolidated in L12-test-deletions.md)
- [ ] `tests/test_reorder.py` — DELETE (consolidated in L12-test-deletions.md)
- [ ] `tests/test_atomic_writes.py` — MODIFY — Delete `TestStagingSaveAtomic` class
- [ ] `tests/test_health_check.py` — MODIFY — Delete 2 staging-specific tests
- [ ] `tests/test_stable_keys.py` — MODIFY — Update import from `staging_manager` to `nagios_model`

**Phase gate**: `python3 -m pytest tests/ -v` — all pass, no import errors

---

## Layer 13: Asset Cleanup

Remove dead CSS classes, update template docs.

- [ ] `static/css/explorer.css` — MODIFY — Remove ~25 dead staging CSS classes
- [ ] `static/css/git.css` — MODIFY — Remove ~15 dead staging CSS classes
- [ ] `nagios_parser.py` — MODIFY — Remove `.staging/` exclusion (dead code)
- [ ] `templates/docs/staging-system.html` — DELETE
- [ ] `templates/docs/data-flow-staging.html` — DELETE
- [ ] 14 `templates/docs/*.html` files — MODIFY — Replace "staging" with "candidate" terminology
- [ ] `templates/docs.html` — MODIFY — Update navigation sidebar (remove links to deleted pages)

**Phase gate**: App loads, all styles correct

---

## Layer 14: Documentation

Update all reference docs to candidate terminology.

- [ ] `.claude/STAGING_REFERENCE.md` — DELETE
- [ ] `.claude/CANDIDATE_REFERENCE.md` — CREATE — Full candidate system docs
- [ ] `CLAUDE.md` — MODIFY — Full rewrite for candidate terminology
- [ ] `routes/CLAUDE.md` — MODIFY — Update for candidate routes
- [ ] `.claude/API_REFERENCE.md` — MODIFY — Replace staging API with candidate API
- [ ] `.claude/ROUTES_REFERENCE.md` — MODIFY — Replace staging routes with candidate routes
- [ ] `static/js/CLAUDE.md` — MODIFY — Add candidate-api.js
- [ ] `static/js/explorer/CLAUDE.md` — MODIFY — Update for candidate mode
- [ ] `templates/CLAUDE.md` — MODIFY — Update load order
- [ ] `.claude/DECISION_LOG.md` — MODIFY — Append candidate decision

**Phase gate**: `grep -ri "staging" CLAUDE.md .claude/ routes/CLAUDE.md static/js/CLAUDE.md static/js/explorer/CLAUDE.md templates/CLAUDE.md` — no stale references
