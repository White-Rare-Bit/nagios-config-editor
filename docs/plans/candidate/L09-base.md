# L09 — `static/js/base.js` — MODIFY

## Purpose
Rewrite `checkPendingChanges()` to use candidate diff. Rewrite `handleUndoClick()` to use CandidateApi. Remove all staging API references. Preserve navbar button appearance and polling behavior.

## Removal Audit

### Detailed Line-by-Line Staging References

**`checkPendingChanges()` function (lines 257-290):**
| Line | Reference | Action |
|------|-----------|--------|
| 259 | `ApiClient.get('/api/staging/info', { silent: true })` | REPLACE with `CandidateApi.getDiff()` |
| 263 | `info.totalCount` from staging info response | REPLACE with `result.data.totalCount` from candidate diff |
| 264 | `info.undoCount` from staging info response | REPLACE with `result.data.undoCount` from candidate diff |
| 267-272 | Git status fallback for external changes when staging count is 0 | REMOVE. Candidate diff already includes all changes |
| 279-284 | `Explorer.getTotalStagedCount()` / `Explorer.getUndoCount()` fallback | REMOVE. No client-side staging state in candidate model |
| 287 | `ApiClient.get('/api/staging/diff', { silent: true })` last-resort fallback | REMOVE. Single `CandidateApi.getDiff()` call replaces all fallbacks |
| 288 | `diffResult.data?.gitChanges` property access | REMOVE with fallback |

3 staging API endpoints removed. 2 client-side staging state fallbacks removed.

**`handleUndoClick()` function (lines 207-236):**
| Line | Reference | Action |
|------|-----------|--------|
| 208 | `Explorer.undoLastAction` branch delegating to Explorer module | REMOVE. Single unified undo path through CandidateApi |
| 219 | `ApiClient.post('/api/staging/undo', {}, { silent: true })` | REPLACE with `CandidateApi.undo()` |
| 226 | `if (typeof buildTree === 'function') {buildTree();}` | REPLACE with `Explorer.refreshAfterObjectChange()` |

1 staging API endpoint removed. Explorer delegation branch simplified.

**Total: 4 staging API references, 2 client-side staging state references. All accounted for.**

## Changes

**1. Rewrite `checkPendingChanges()` (line 257)** — Replace three-tier fallback with single candidate diff call:
```javascript
// BEFORE: Complex logic with /api/staging/info, git status fallback, Explorer state fallback, /api/staging/diff
async function checkPendingChanges() {
    const infoResult = await ApiClient.get('/api/staging/info', { silent: true });
    if (infoResult.success) {
        const info = infoResult.data;
        let count = info.totalCount || 0;
        updateUndoButton(info.undoCount || 0);
        if (count === 0) {
            const gitResult = await ApiClient.get('/api/git/status', { silent: true });
            if (gitResult.success && gitResult.data?.has_changes) {
                count = gitResult.data.files.length;
            }
        }
        updateNavCommitButton(count);
        return;
    }
    if (typeof Explorer !== 'undefined' && Explorer.getTotalStagedCount) {
        const count = Explorer.getTotalStagedCount();
        updateNavCommitButton(count);
        updateUndoButton(Explorer.getUndoCount ? Explorer.getUndoCount() : 0);
        return;
    }
    const diffResult = await ApiClient.get('/api/staging/diff', { silent: true });
    const count = (diffResult.data?.gitChanges || []).length;
    updateNavCommitButton(count);
}

// AFTER: Single candidate diff call
async function checkPendingChanges() {
    const result = await CandidateApi.getDiff();
    if (result.success) {
        const count = result.data.totalCount || 0;
        updateUndoButton(result.data.undoCount || 0);
        updateNavCommitButton(count);
    } else {
        // Candidate session may not exist — show zero changes
        DebugLogger.warning('checkPendingChanges: candidate diff failed', {
            error: result.error
        });
        updateUndoButton(0);
        updateNavCommitButton(0);
    }
}
```

The `else` branch handles the case where no candidate session exists (e.g. fresh page load before any edits). It logs the failure through DebugLogger and shows zero changes rather than silently swallowing the error.

**2. Rewrite `handleUndoClick()` (line 207)** — Remove Explorer delegation branch; use single CandidateApi path with proper error handling:
```javascript
// BEFORE: Two branches — Explorer.undoLastAction or direct /api/staging/undo
async function handleUndoClick() {
    if (typeof Explorer !== 'undefined' && Explorer.undoLastAction) {
        const result = await Explorer.undoLastAction();
        if (result.success) { checkPendingChanges(); }
    } else {
        if (_undoInProgress) {return;}
        _undoInProgress = true;
        try {
            const result = await ApiClient.post('/api/staging/undo', {}, { silent: true });
            ...
        } finally { _undoInProgress = false; }
    }
}

// AFTER: Single CandidateApi.undo() path with concurrency guard
async function handleUndoClick() {
    if (_undoInProgress) { return; }
    _undoInProgress = true;
    try {
        const result = await CandidateApi.undo();
        if (result.success) {
            showToast(result.data.description || 'Undo successful', 'success');
            if (typeof Explorer !== 'undefined' && Explorer.refreshAfterObjectChange) {
                await Explorer.refreshAfterObjectChange();
            }
            await checkPendingChanges();
        } else if (result.status === 404) {
            showToast('Nothing to undo', 'info');
        } else {
            showToast(result.error || 'Failed to undo', 'error');
            DebugLogger.error('handleUndoClick: undo failed', {
                error: result.error, status: result.status
            });
        }
    } finally {
        _undoInProgress = false;
    }
}
```

Key details:
- **Concurrency guard** (`_undoInProgress`) is preserved from the existing code (H-028).
- **Explorer refresh**: After successful undo, calls `Explorer.refreshAfterObjectChange()` if on explorer page so the tree/center pane reflect the reverted state.
- **Error branches**: 404 gives "Nothing to undo" toast. All other failures show error toast AND log through DebugLogger.
- **Removed**: The `Explorer.undoLastAction` delegation branch. In candidate mode, undo is always server-side (`CandidateApi.undo()`), so the two-branch approach is dead code.
- **Removed**: The `buildTree()` fallback call. `Explorer.refreshAfterObjectChange()` is the proper candidate-era refresh mechanism.

**3. `startLockPoll()` — KEPT, no changes needed** — Still calls `checkLockStatus()` and `checkPendingChanges()` every 5 seconds. Both now use candidate endpoints internally (`checkLockStatus` rewired in L09-lock-manager, `checkPendingChanges` rewired above).

**4. `updateNavCommitButton()` and `updateUndoButton()` — KEPT, no changes** — These are pure UI functions that accept a count and toggle CSS classes/disabled state. They have no staging references. Visual parity is preserved: same button HTML, same `commit-count` badge, same `disabled`/`active` class toggling.

**5. Kept functions (no staging references, no changes needed)**:
- `DebugLogger` IIFE — no staging references
- `escapeJs()`, `pluralize()` — utility, no staging references
- `showLoadingState()`, `withLoadingButton()` — UI helpers, no staging references
- `showKeyboardShortcuts()`, `closeKeyboardShortcuts()` — dialog helpers, no staging references
- `checkIdentityRequired()` — identity check, no staging references
- `actionHandlers` map — handlers themselves are rewired above, map stays as-is
- `DOMContentLoaded` listener — calls `checkPendingChanges()` and `checkLockStatus()` which are rewired; the listener itself stays as-is
- Keyboard shortcut handler (`Ctrl+Z`, `Escape`, `?`) — delegates to `handleUndoClick()` which is rewired; handler stays as-is

## Dead Code Deletion Summary

| Function/Code | Status | Reason |
|--------------|--------|--------|
| `checkPendingChanges()` git status fallback (lines 267-272) | DELETED | Candidate diff includes all changes; no need for separate git check |
| `checkPendingChanges()` Explorer state fallback (lines 279-284) | DELETED | No client-side staging state in candidate model |
| `checkPendingChanges()` `/api/staging/diff` fallback (lines 287-289) | DELETED | Single `CandidateApi.getDiff()` replaces all fallbacks |
| `handleUndoClick()` Explorer.undoLastAction branch (lines 208-213) | DELETED | Undo is always server-side in candidate model |
| `handleUndoClick()` `buildTree()` call (line 226) | DELETED | Replaced by `Explorer.refreshAfterObjectChange()` |

## UI Visual Parity

The following navbar elements are unchanged:
- **Commit button** (`#navCommitBtn`): Same `commit-count` badge HTML, same `disabled`/`active` class toggling, same enabled/disabled logic. Only the data source changes (candidate diff instead of staging info).
- **Undo button** (`#navUndoBtn`): Same tooltip format (`"Undo last action (N in stack) - Ctrl+Z"`), same `disabled`/`active` class toggling. Same concurrency guard behavior.
- **Git pending indicator** (`#gitPendingIndicator`): Same `u-hidden`/`u-visible-flex` toggling.
- **Polling interval**: 5 seconds, unchanged.

No visual changes are introduced. The buttons render identically.

## Verification
- Commit button shows count badge when candidate changes exist
- Commit button shows no badge and is disabled when no candidate changes exist
- Undo button is enabled when undo stack is non-empty
- Undo from navbar reverts last candidate operation and shows success toast
- Undo when nothing to undo shows "Nothing to undo" info toast
- Undo failure shows error toast and logs to DebugLogger
- Polling updates badge counts every 5 seconds
- `Ctrl+Z` / `Cmd+Z` keyboard shortcut triggers undo
- No console errors on any page (explorer, git, settings, backups)
- `npm run lint:js` passes

## Playwright Test Guidance
- Navigate to explorer, make an edit via CandidateApi, verify commit button badge appears with count > 0
- Click undo, verify badge count decrements and success toast appears
- Verify commit button is disabled and badge-less when no candidate changes exist
- Verify keyboard shortcut `Ctrl+Z` triggers undo when undo button is enabled

## Commandments Compliance

- [x] **1. No live config mutation until Apply.** All changes go through `CandidateApi.getDiff()` and `CandidateApi.undo()` — no disk writes occur. The commit button count reflects candidate state, not live config.
- [x] **2. UI visual parity.** Navbar commit button (with count badge), undo button, and git pending indicator render identically. No HTML structure, CSS class, or visual behavior changes.
- [x] **3. Full audit logging.** `CandidateApi.undo()` calls the candidate undo endpoint which logs through `audit_service.py` server-side. Client-side errors logged through `DebugLogger` which sends to `/api/logs/frontend`.
- [x] **4. Proper error handling.** `checkPendingChanges()` has an explicit `else` branch that logs failures and shows zero state. `handleUndoClick()` handles success, 404, and generic error cases with toasts and DebugLogger.
- [x] **5. Dead code deletion.** Three fallback tiers in `checkPendingChanges()` removed. `Explorer.undoLastAction` delegation branch removed. `buildTree()` call removed. All replaced by candidate equivalents.
- [x] **6. Full functionality migration.** Pending change counting, undo, polling, keyboard shortcuts — all migrated. Commit button badge, undo button state, git indicator — all driven by candidate diff. Explorer refresh after undo preserved.
- [x] **7. Palo Alto candidate model.** `checkPendingChanges()` reads from candidate diff (candidate directory state). `handleUndoClick()` reverts candidate changes via `CandidateApi.undo()`. No staging system references remain.
- [x] **8. Change tracking document.** Detailed line-by-line removal audit with line numbers. Dead code deletion summary table. All staging references enumerated and accounted for.
- [x] **9. Complete planning before implementation.** Full before/after code shown. All kept/removed/modified functions explicitly listed. No ambiguity in what changes.
- [x] **10. Linting enforcement.** Verification includes `npm run lint:js` pass requirement.
- [x] **11. Playwright validation.** Playwright test guidance section added with specific scenarios for badge count, undo, and keyboard shortcut validation.
