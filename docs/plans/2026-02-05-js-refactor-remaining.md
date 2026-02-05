# JavaScript Refactoring - Remaining Work Plan

**Created:** 2026-02-05
**Status:** Planning
**Total Estimated Effort:** 80-110 hours (prioritized subset)

---

## Executive Summary

Of the 27 original refactor plans, significant progress has been made on quick wins and medium-complexity tasks. The remaining work falls into three categories:

1. **Large Module Splits** (40-55 hours) - High impact, high effort
2. **Medium Cleanups** (25-35 hours) - Medium impact, manageable effort
3. **Minor Polishing** (10-15 hours) - Low priority, optional

This plan focuses on the highest-value remaining work, organized into executable phases.

---

## Completed Work (Reference)

The following has already been completed:

| Module | Refactoring Done |
|--------|-----------------|
| file-operations.js | `afterStagingChange()` helper (26 replacements, -42 lines) |
| dependencies.js | Edge traversal utilities |
| objects.js | IIFE wrapper |
| find-replace.js | Constants + IIFE |
| smart-grouping.js | Constants + IIFE |
| reorganize.js | `performBulkOperation()` + IIFE |
| object-editor.js | Attribute configs → constants.js |
| dialogs.js | HTML template helpers |
| context-menu.js | Pending edit helper |
| data-loading.js | Centralized error handling |
| analysis.js | `stripPrefix()`, `SEVERITY_ORDER` |
| health-check.js | Severity constants |
| bulk-rename.js | Form data helper |
| audit-log.js | Error display, date parser helpers |

---

## Phase 1: Dead Code Removal (2-4 hours)

Low-risk, high-value cleanup that reduces maintenance burden.

### Task 1.1: explorer/ui-utils.js - Remove Dead Code
**Reference:** `explorer-ui-utils-refactor.md`
**Effort:** 1-2 hours
**Risk:** Low

Remove ~60% dead code:
- Unused `debounce()` and `throttle()` (use app.js versions)
- Unused keyboard shortcut helpers
- Duplicate icon definitions (already in constants.js)
- Unused formatting functions

**Target:** 227 → ~90 lines

**Commit:** `refactor(ui-utils): remove dead code and duplicate utilities`

---

### Task 1.2: explorer/drag-drop.js - Clean Up Dead Code
**Reference:** `explorer-drag-drop-refactor.md`
**Effort:** 30-60 minutes
**Risk:** Low

The refactor plan identifies 91% of the module as dead code from a previous implementation. Verify and remove:
- Legacy drag handlers
- Unused drop zone code
- Obsolete event listeners

**Commit:** `refactor(drag-drop): remove legacy dead code`

---

## Phase 2: ApiClient Migration (3-5 hours)

Standardize API calls across remaining modules for consistent error handling.

### Task 2.1: inheritance.js - Migrate to ApiClient
**Reference:** `inheritance-refactor.md`
**Effort:** 45 minutes
**Risk:** Low

Replace raw `fetch()` calls with `ApiClient.get/post()`:
- Line 23: Load inheritance data
- Line 89: Load object details

Add loading states with `setButtonLoading()`.

**Commit:** `refactor(inheritance): migrate to ApiClient`

---

### Task 2.2: validate.js - Migrate to ApiClient
**Reference:** `validate-refactor.md`
**Effort:** 35 minutes
**Risk:** Low

Replace fetch calls and fix timeout cleanup:
- Line 15: Validation endpoint
- Fix: Clear timeout on component unmount

**Commit:** `refactor(validate): migrate to ApiClient, fix timeout cleanup`

---

### Task 2.3: git.js - Consolidate and Migrate
**Reference:** `git-refactor.md`
**Effort:** 1.5-2 hours
**Risk:** Low

1. Consolidate `updateResultPanel*()` functions into single configurable function
2. Extract color constants (`STATUS_COLORS`)
3. Ensure all API calls use ApiClient

**Commit:** `refactor(git): consolidate result panel, extract constants`

---

### Task 2.4: settings.js - Modernize Patterns
**Reference:** `settings-refactor.md`
**Effort:** 1-1.5 hours
**Risk:** Low

1. Consolidate path field definitions into config object
2. Convert `onclick` handlers to `data-action` pattern
3. Add IIFE wrapper

**Commit:** `refactor(settings): consolidate config, use data-action pattern`

---

## Phase 3: Medium Module Improvements (15-20 hours)

### Task 3.1: explorer/state-management.js - DRY Violations
**Reference:** `explorer-state-management-refactor.md`
**Effort:** 2-3 hours
**Risk:** Medium

Extract duplicated index resolution pattern (~60 lines repeated):
```javascript
// Create helper for the repeated pattern
function resolveObjectFromEdit(edit) {
    // Consolidate the 4 variations of this logic
}
```

Fix `hasStagedChanges()` alignment with actual staging checks.

**Commit:** `refactor(state-management): extract index resolution helper`

---

### Task 3.2: explorer/context-menu.js - Complete Extraction
**Reference:** `explorer-context-menu-refactor.md`
**Effort:** 3-4 hours
**Risk:** Medium

Building on the pending edit helper already extracted:
1. Consolidate `GROUP_ATTR_MAP`, `GROUP_TYPE_MAP` usage patterns
2. Extract target pane object rendering to file-operations.js
3. Remove trivial wrapper functions that just delegate

**Target:** 1,387 → ~900 lines

**Commit:** `refactor(context-menu): consolidate group logic, remove wrappers`

---

### Task 3.3: audit-log.js - Split God Functions
**Reference:** `audit-log-refactor.md`
**Effort:** 2-3 hours
**Risk:** Low

1. Extract `renderDetailSection()` helper
2. Extract `matchesSearch()` predicate
3. Extract `generateBadge()` helper
4. Split `renderAuditEntry()` (currently 150+ lines)

**Commit:** `refactor(audit-log): extract rendering helpers, split god function`

---

### Task 3.4: backups.js - Extract Pagination
**Reference:** `backups-refactor.md`
**Effort:** 2-3 hours
**Risk:** Low

1. Extract reusable pagination component (also used by audit-log.js)
2. Convert to data-driven rendering pattern
3. Add IIFE wrapper

**Commit:** `refactor(backups): extract pagination, data-driven rendering`

---

### Task 3.5: bulk-attributes.js - Fix and Clean
**Reference:** `bulk-attributes-refactor.md`
**Effort:** 2-3 hours
**Risk:** Low

1. **Bug fix:** Add missing event listener for attribute removal
2. Extract form data collection helper
3. Ensure ApiClient usage throughout

**Commit:** `fix(bulk-attributes): add missing event listener, extract helpers`

---

## Phase 4: Large Module Splits (40-55 hours)

These are significant architectural changes that should be done carefully with thorough testing.

### Task 4.1: base.js - Module Extraction
**Reference:** `base-refactor.md`
**Effort:** 13-17 hours
**Risk:** High

Split 2,196-line god module into focused modules:

| New Module | Responsibility | Est. Lines |
|------------|---------------|------------|
| `session-manager.js` | Session ID, user identity | ~80 |
| `lock-manager.js` | Edit lock state, sync | ~150 |
| `ui-notifications.js` | Toast, confirm dialog | ~200 |
| `commit-dialog.js` | Commit modal, validation | ~400 |
| `file-changes-builder.js` | Staged changes formatting | ~200 |
| `git-operations.js` | Git API calls, diff display | ~300 |
| `base.js` (remaining) | Coordination, exports | ~300 |

**Approach:**
1. Extract one module at a time
2. Keep exports on `window` for backwards compatibility
3. Test each extraction before proceeding
4. Update all import references

**Commits:** One per extracted module

---

### Task 4.2: explorer/app.js - Feature Extraction
**Reference:** `explorer-app-refactor.md`
**Effort:** 16-22 hours
**Risk:** High

Split 4,204-line module:

| New Module | Responsibility | Est. Lines |
|------------|---------------|------------|
| `badge-issues.js` | Issue badge rendering, counts | ~300 |
| `orphan-detection.js` | Orphan analysis, display | ~250 |
| `relations-loader.js` | Reference/inheritance loading | ~400 |
| `impact-section.js` | Impact analysis UI | ~200 |
| `app.js` (remaining) | Tree rendering, core selection | ~1,500 |

Also:
- Remove identified dead code (~500 lines)
- Consolidate duplicate tree rendering logic

**Commits:** One per extracted module + dead code removal

---

### Task 4.3: explorer/data-loading.js - Staging Modules
**Reference:** `explorer-data-loading-refactor.md`
**Effort:** 6-8 hours
**Risk:** Medium

Extract staging-related code into focused modules:

| New Module | Responsibility |
|------------|---------------|
| `staging-serializer.js` | Serialize/deserialize staging state |
| `staging-sync.js` | Sync state with server |
| `staging-poller.js` | Background polling logic |

**Commits:** One per extracted module

---

### Task 4.4: analysis.js - Feature Modules
**Reference:** `explorer-analysis-refactor.md`
**Effort:** 8-12 hours
**Risk:** Medium

Split ~1,700 lines into feature modules:

| New Module | Responsibility |
|------------|---------------|
| `analysis-templates.js` | Template suggestions |
| `analysis-cleanup.js` | Cleanup recommendations |
| `analysis-issues.js` | Validation issues display |
| `analysis-grouping.js` | Grouping suggestions |

**Commits:** One per extracted module

---

## Phase 5: Optional Polish (5-10 hours)

Lower priority improvements for when time permits.

### Task 5.1: api-client.js - Internal Cleanup
**Effort:** 1-2 hours

- Extract common request logic
- Remove redundant header handling
- Fix timeout error message

---

### Task 5.2: dependencies.js - Further Extraction
**Effort:** 3-5 hours

- Extract layout algorithm configurations
- Split node/edge rendering helpers
- Consider extracting to dependencies-config.js (partially done)

---

### Task 5.3: objects.js - Deprecation Path
**Effort:** 30 minutes

- Add deprecation banner in UI
- Document migration path to Explorer
- Consider removal timeline

---

## Verification Checklist

After each phase:
- [ ] `python3 app.py` starts without error
- [ ] Browser console shows no JS errors
- [ ] Explorer page loads and displays objects
- [ ] Can create, edit, delete objects
- [ ] Commit dialog works
- [ ] All data-action handlers respond
- [ ] No regressions in functionality

---

## Recommended Execution Order

1. **Phase 1** (Dead code) - Quick wins, reduces noise
2. **Phase 2** (ApiClient) - Standardization, low risk
3. **Phase 3** (Medium) - Incremental improvements
4. **Phase 4** (Large splits) - Do one at a time with full testing
5. **Phase 5** (Polish) - As time permits

**Suggested First Session:** Phase 1 + Phase 2 (5-9 hours total)

---

## Risk Mitigation

- **Always work in feature branch** (current: `feature/js-refactor`)
- **Commit after each task** for easy rollback
- **Test in browser** after each module extraction
- **Keep backwards compatibility** via window exports during transition
- **Document breaking changes** if any exports are removed
