# Staging Orchestration Refactor

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace ad-hoc after-mutation call chains with two well-defined orchestrators, eliminating redundant network requests (from 7-16 per mutation down to 2-4).

**Architecture:** Every mutation site currently composes its own combination of `saveStagedChanges()`, `updateCommitUI()`, `checkPendingChanges()`, `buildTree()`, `renderTargetPane()`, etc. This creates hidden side effects and redundant API calls (`/api/staging/info` fetched 3x, staging re-POSTed via `updateCommitUI`). The fix: side-effect-free primitives composed by exactly two orchestrators — one for "frontend changed, push to server" and one for "server changed, pull to frontend".

**Tech Stack:** Vanilla JavaScript (IIFE modules on `window.Explorer`)

---

## Background: Current Problem

Three interlocking issues:

1. **`saveStagedChanges()`** (data-loading.js:91-161) has hidden side effects: internally calls `checkPendingChanges()` (which GETs `/api/staging/info`) AND `triggerAnalysisUpdate()` (which debounce-calls `loadAllSuggestions(true)`).

2. **`updateCommitUI()`** (dialogs.js:1318-1320) is just `Explorer.saveStagedChanges()` — callers that do `saveStagedChanges(); updateCommitUI()` trigger a double POST+GET cycle.

3. **`refreshAfterObjectChange()`** (state-management.js:301-332) calls both `loadAllSuggestions(true)` AND `updateCommitUI()` — so callers that already called `saveStagedChanges()` get triple-stacked saves and double analysis loads.

**Affected call sites:** ~50 total across 9 files.

## New Design

```
┌─────────────────────────────────────────────────┐
│  PRIMITIVES (no side effects)                   │
├─────────────────────────────────────────────────┤
│  saveStaging()     → POST /api/staging          │
│  updateBadges()    → GET /api/staging/info       │
│                      updates commit count + undo │
│  rebuildUI(opts)   → sync computeStagedIssues,  │
│                      buildTree, renderTargetPane,│
│                      syncCenterPane, renderTabBar│
│  debouncedAnalysis → debounced loadAllSuggestions│
└─────────────────────────────────────────────────┘
         │                         │
         ▼                         ▼
┌──────────────────┐  ┌──────────────────────────┐
│ afterFrontendMut │  │ afterServerSync          │
│                  │  │                          │
│ 1. saveStaging() │  │ 1. (no save)             │
│ 2. rebuildUI()   │  │ 2. rebuildUI()           │
│ 3. updateBadges()│  │ 3. updateBadges()        │
│ 4. debouncedAnal │  │ 4. debouncedAnalysis()   │
└──────────────────┘  └──────────────────────────┘

Network calls per mutation:         After server sync:
  POST /api/staging (1)               GET /api/staging/info (1)
  GET /api/staging/info (1)           debounced analysis (0-3)
  debounced analysis (0-3 after 500ms)
  TOTAL: 2 + debounced              TOTAL: 1 + debounced
```

---

## Task 1: Create New Primitives

**Files:**
- Modify: `static/js/explorer/data-loading.js:91-161` (extract saveStaging from saveStagedChanges)
- Modify: `static/js/explorer/state-management.js:301-332` (extract rebuildUI from refreshAfterObjectChange)
- Modify: `static/js/base.js:257-290` (extract updateBadges from checkPendingChanges)

**Step 1: Add `Explorer.saveStaging()` to data-loading.js**

Add this new function BEFORE the existing `saveStagedChanges` (around line 88). This is the side-effect-free version — it only POSTs and returns success/failure.

```javascript
/**
 * Save staging state to server (side-effect-free).
 * Only POSTs current state. Does NOT update badges or trigger analysis.
 * @returns {Promise<{success: boolean, error?: string}>}
 */
Explorer.saveStaging = async function() {
    if (saveDebounceTimer) {
        clearTimeout(saveDebounceTimer);
    }

    if (saveInProgress) {
        saveDebounceTimer = setTimeout(() => Explorer.saveStaging(), CONFIG.SAVE_DEBOUNCE_RETRY_MS);
        return { success: false, error: 'debounced' };
    }

    saveInProgress = true;
    isSavingStaging = true;

    try {
        const state = Explorer.state;
        const identity = typeof getUserIdentity === 'function' ? getUserIdentity() : {};

        const data = {
            sessionId: state.sessionId,
            userName: identity.userName || '',
            userEmail: identity.userEmail || '',
            pendingEdits: Object.fromEntries(state.pendingEdits),
            stagedMoves: Object.fromEntries(state.stagedMoves),
            stagedCreations: state.stagedCreations,
            newFiles: Array.from(state.newFiles),
            stagedObjectDeletions: Array.from(state.stagedObjectDeletions),
            stagedFileCreations: state.stagedFileCreations,
            stagedFileDeletions: state.stagedFileDeletions,
            stagedFileMoves: state.stagedFileMoves,
            stagedFolderCreations: state.stagedFolderCreations,
            stagedFolderDeletions: state.stagedFolderDeletions,
            stagedFolderMoves: state.stagedFolderMoves
        };

        const result = await ApiClient.post('/api/staging', data, { silent: true });

        if (result.success) {
            return { success: true };
        } else if (result.status === 423) {
            Explorer.showToast(result.data?.error || 'Staging is locked by another user', 'error');
            window.isEditingLocked = true;
            Explorer.updateEditingLockedUI();
            return { success: false, error: 'locked' };
        } else {
            console.error('Failed to save staging to server');
            Explorer.showToast('Failed to save changes to server.', 'error');
            return { success: false, error: 'save_failed' };
        }
    } finally {
        isSavingStaging = false;
        saveInProgress = false;
    }
};
```

**Step 2: Add `Explorer.updateBadges()` to data-loading.js**

Add this after `saveStaging`. It does a single `GET /api/staging/info` and updates both the commit count and undo button.

```javascript
/**
 * Fetch staging info and update nav badges (commit count + undo button).
 * Single GET /api/staging/info — no other side effects.
 */
Explorer.updateBadges = async function() {
    const infoResult = await ApiClient.get('/api/staging/info', { silent: true });

    if (infoResult.success) {
        const info = infoResult.data;
        lastStagingTimestamp = info.lastModified;
        let count = info.totalCount || 0;

        if (typeof updateUndoButton === 'function') {
            updateUndoButton(info.undoCount || 0);
        }

        // If no GUI staging, check git for external changes
        if (count === 0) {
            const gitResult = await ApiClient.get('/api/git/status', { silent: true });
            if (gitResult.success && gitResult.data?.has_changes) {
                count = gitResult.data.files.length;
            }
        }

        if (typeof updateNavCommitButton === 'function') {
            updateNavCommitButton(count);
        }
    }
};
```

**Step 3: Add `Explorer.rebuildUI()` to state-management.js**

Add this BEFORE `refreshAfterObjectChange` (around line 290). This is the synchronous UI rebuild with no network calls.

```javascript
/**
 * Synchronous UI rebuild — no network calls, no saves.
 * @param {Object} options
 * @param {boolean} options.skipTree - Skip tree + staged issues refresh
 * @param {boolean} options.skipTarget - Skip target pane refresh
 * @param {boolean} options.skipCenter - Skip center pane sync
 * @param {boolean} options.skipTabs - Skip tab bar refresh
 */
Explorer.rebuildUI = function(options = {}) {
    if (!options.skipTree && Explorer.computeStagedIssues) {
        Explorer.computeStagedIssues();
    }

    if (!options.skipTree && Explorer.buildTree) {
        Explorer.buildTree();
    }

    if (!options.skipTarget && Explorer.renderTargetPane) {
        Explorer.renderTargetPane();
    }

    if (!options.skipCenter && Explorer.syncCenterPaneAfterUndo && state.editedObject) {
        Explorer.syncCenterPaneAfterUndo();
    }

    if (Explorer.renderTabBar) {
        Explorer.renderTabBar();
    }
};
```

**Step 4: Add the two orchestrators to data-loading.js**

Add these after `updateBadges`:

```javascript
/**
 * ORCHESTRATOR: Call after any frontend-initiated mutation.
 * Saves to server, rebuilds UI, updates badges, triggers debounced analysis.
 * This is the ONE function to call after modifying staging state locally.
 *
 * @param {Object} options - Passed through to rebuildUI
 */
Explorer.afterFrontendMutation = async function(options = {}) {
    await Explorer.saveStaging();
    Explorer.rebuildUI(options);
    Explorer.updateBadges();
    triggerAnalysisUpdate();
};

/**
 * ORCHESTRATOR: Call after server-originated changes (undo, apply, polling).
 * Does NOT save (server already has the truth). Rebuilds UI, updates badges.
 *
 * @param {Object} options - Passed through to rebuildUI
 */
Explorer.afterServerSync = function(options = {}) {
    Explorer.rebuildUI(options);
    Explorer.updateBadges();
    triggerAnalysisUpdate();
};
```

**Step 5: Verify no regressions by running the app**

Run: `python3 app.py`
Open browser to http://localhost:8080. Navigate to Explorer page. Verify it loads without console errors. At this point no callers use the new functions yet — this is purely additive.

**Step 6: Commit**

```bash
git add static/js/explorer/data-loading.js static/js/explorer/state-management.js
git commit -m "refactor: add staging orchestration primitives (saveStaging, updateBadges, rebuildUI, afterFrontendMutation, afterServerSync)"
```

---

## Task 2: Migrate Pattern A — `saveStagedChanges()` + `refreshAfterObjectChange()`

These ~12 call sites do `saveStagedChanges(); refreshAfterObjectChange(options)`. Replace with `afterFrontendMutation(options)`.

**Files:**
- Modify: `static/js/explorer/dialogs.js` (7 sites)
- Modify: `static/js/explorer/object-editor.js` (2 sites)
- Modify: `static/js/explorer/analysis.js` (1 site)
- Modify: `static/js/explorer/analysis-suggestions.js` (2 sites)

**Step 1: Migrate dialogs.js**

Replace each pair. The `options` argument passes through unchanged.

| Lines | Context | Old | New |
|-------|---------|-----|-----|
| 284-285 | discardNewObject | `saveStagedChanges(); refreshAfterObjectChange()` | `afterFrontendMutation()` |
| 488-489 | createNewObject | `saveStagedChanges(); refreshAfterObjectChange({skipCenter:true})` | `afterFrontendMutation({skipCenter:true})` |
| 722-723 | delete staged creations only | `saveStagedChanges(); refreshAfterObjectChange()` | `afterFrontendMutation()` |
| 756-757 | stageObjectDeletions | `saveStagedChanges(); refreshAfterObjectChange()` | `afterFrontendMutation()` |
| 771-772 | unstageObjectDeletion | `saveStagedChanges(); refreshAfterObjectChange()` | `afterFrontendMutation()` |
| 881-884 | executeBulkRename | `saveStagedChanges(); healthCheckData=null; computeStagedIssues(); refreshAfterObjectChange()` | `state.healthCheckData=null; afterFrontendMutation()` |
| 1349-1350 | removeStagedCreation | `saveStagedChanges(); refreshAfterObjectChange()` | `afterFrontendMutation()` |

For the bulk rename (lines 881-884), `computeStagedIssues()` is already called inside `rebuildUI()`, so the explicit call is redundant. Keep the `healthCheckData = null` to force a fresh analysis on next debounce.

**Step 2: Migrate object-editor.js**

| Lines | Context | Old | New |
|-------|---------|-----|-----|
| 1177-1180 | cancelEdit (delete pending edit) | `saveStagedChanges(); refreshAfterObjectChange()` | `afterFrontendMutation()` |
| 1222-1231 | stageCurrentChanges | `saveStagedChanges(); [local state update]; refreshAfterObjectChange()` | `[local state update]; afterFrontendMutation()` |

For stageCurrentChanges: the local state update (lines 1224-1228 updating `state.allObjects`) must happen BEFORE `afterFrontendMutation` since `rebuildUI` reads `state.allObjects`.

**Step 3: Migrate analysis.js**

| Lines | Context | Old | New |
|-------|---------|-----|-----|
| 753-754 | stageCleanupSuggestion | `saveStagedChanges(); refreshAfterObjectChange()` | `afterFrontendMutation()` |

Note: line 755 (`renderUnifiedSuggestionsList()`) can remain — it's a local render, not a network call.

**Step 4: Migrate analysis-suggestions.js**

| Lines | Context | Old | New |
|-------|---------|-----|-----|
| 396-397 | createConsolidation | `saveStagedChanges(); refreshAfterObjectChange()` | `afterFrontendMutation()` |
| 486-487 | createHostgroup | `saveStagedChanges(); refreshAfterObjectChange()` | `afterFrontendMutation()` |

**Step 5: Verify no regressions**

Run: `python3 app.py`
Open browser. Test these operations:
- Create a new object → verify tree updates and commit count badge shows
- Edit an object attribute → stage it → verify tree shows modified indicator
- Delete an object → verify tree updates
- Undo (Ctrl+Z) still works (not migrated yet, uses old path)
- Open browser DevTools Network tab → verify no double POST to /api/staging on a single edit

**Step 6: Commit**

```bash
git add static/js/explorer/dialogs.js static/js/explorer/object-editor.js static/js/explorer/analysis.js static/js/explorer/analysis-suggestions.js
git commit -m "refactor: migrate Pattern A sites to afterFrontendMutation (dialogs, object-editor, analysis)"
```

---

## Task 3: Migrate Pattern B — `saveStagedChanges()` + `updateCommitUI()` + manual UI

These ~12 call sites manually compose `saveStagedChanges(); updateCommitUI(); buildTree(); ...`. Replace with `afterFrontendMutation()`.

**Files:**
- Modify: `static/js/explorer/context-menu.js` (7 sites)
- Modify: `static/js/explorer/analysis.js` (3 sites)
- Modify: `static/js/explorer/analysis-issues.js` (1 site)

**Step 1: Migrate context-menu.js**

For each site, replace the `saveStagedChanges(); updateCommitUI(); ...` block with a single `Explorer.afterFrontendMutation()` call. Keep any non-UI logic (toast messages, state mutations, `closeDialog()`) in place.

| Lines | Context | Old code block | New |
|-------|---------|---------------|-----|
| 512-515 | cloneObject | `saveStagedChanges(); updateCommitUI(); buildTree(); closeDialog()` | `afterFrontendMutation(); closeDialog()` |
| 573-579 | renameObject | `saveStagedChanges(); updateCommitUI(); healthCheckData=null; computeStagedIssues(); buildTree(); renderTargetPane(); closeDialog()` | `state.healthCheckData=null; afterFrontendMutation(); closeDialog()` |
| 660-664 | moveObjectDrag | `saveStagedChanges(); updateCommitUI(); buildTree(); renderTargetPane(); closeDialog()` | `afterFrontendMutation(); closeDialog()` |
| 725-729 | moveObjectMenu | `saveStagedChanges(); updateCommitUI(); buildTree(); closeDialog()` | `afterFrontendMutation(); closeDialog()` |
| 926-929 | editObjectAttribute | `saveStagedChanges(); updateCommitUI(); buildTree();` | `afterFrontendMutation()` |
| 1068-1069 | moveCreationsToFile | `saveStagedChanges(); buildTree()` | `afterFrontendMutation()` |
| 1104-1107 | moveObjectsToFile | `saveStagedChanges(); toast; updateCommitUI(); buildTree()` | `afterFrontendMutation()` (keep toast before it) |

For rename (573-579): `computeStagedIssues()` is already inside `rebuildUI()`, so it's redundant. Keep `healthCheckData = null`.

For line 1068: this currently skips `updateCommitUI` which was a bug — `afterFrontendMutation` will now correctly update badges here too.

**Step 2: Migrate analysis.js Pattern B sites**

| Lines | Context | Old | New |
|-------|---------|-----|-----|
| 1001-1004 | processCleanup | `saveStagedChanges(); updateCommitUI(); buildTree(); closeDialog()` | `afterFrontendMutation(); Explorer.closeDialog()` |
| 1053-1056 | deleteCleanupObject | `saveStagedChanges(); updateCommitUI(); buildTree(); renderTargetPane()` | `afterFrontendMutation()` |
| 1178-1181 | consolidateTemplate | `saveStagedChanges(); updateCommitUI(); buildTree(); renderTargetPane()` | `afterFrontendMutation()` |

**Step 3: Migrate analysis-issues.js**

| Lines | Context | Old | New |
|-------|---------|-----|-----|
| 416-418 | batchCreateMissing | `saveStagedChanges(); updateCommitUI(); buildTree(); ...` | `afterFrontendMutation(); state.healthCheckData=null; loadIssues()` |

Keep the `state.healthCheckData = null` and `loadIssues()` calls that follow — those are specific post-action logic.

**Step 4: Verify no regressions**

Run: `python3 app.py`
Test in browser:
- Right-click → Clone an object → verify commit count updates
- Right-click → Rename → verify tree updates with new name
- Right-click → Move to file → verify tree and commit count update
- Analysis tab → apply a suggestion → verify it works
- DevTools Network tab: verify single POST /api/staging per operation (not double)

**Step 5: Commit**

```bash
git add static/js/explorer/context-menu.js static/js/explorer/analysis.js static/js/explorer/analysis-issues.js
git commit -m "refactor: migrate Pattern B sites to afterFrontendMutation (context-menu, analysis)"
```

---

## Task 4: Migrate Pattern C — `afterStagingChange()` in file-operations.js

The `afterStagingChange({save, tree})` helper has 25 call sites. It does `saveStagedChanges(); updateCommitUI(); renderTargetPane(); buildTree()` — a Pattern B variant. Replace it and its callers.

**Files:**
- Modify: `static/js/explorer/file-operations.js` (helper + 25 call sites)

**Step 1: Replace `afterStagingChange` definition**

Current code (lines 26-32):
```javascript
function afterStagingChange(options = {}) {
    const { save = true, tree = true } = options;
    if (save) {Explorer.saveStagedChanges();}
    Explorer.updateCommitUI();
    renderTargetPane();
    if (tree) {Explorer.buildTree();}
}
```

Replace with a thin wrapper that delegates to the orchestrators:
```javascript
function afterStagingChange(options = {}) {
    const { save = true, tree = true } = options;
    const uiOptions = tree ? {} : { skipTree: true };
    if (save) {
        Explorer.afterFrontendMutation(uiOptions);
    } else {
        Explorer.afterServerSync(uiOptions);
    }
}
```

This preserves the existing call-site API (`save` and `tree` options) while routing through the correct orchestrator. The `save: false` sites are server-sync flows (unstage operations that already called `saveStagedChanges()` before the helper, or that reload from server).

Also handle the 3 direct `saveStagedChanges(); updateCommitUI()` pairs in file-operations.js:

| Lines | Context | Old | New |
|-------|---------|-----|-----|
| 1019-1020 | dragObjectsToFile | `saveStagedChanges(); updateCommitUI()` (+ buildTree on next line) | `afterStagingChange()` |
| 1125-1126 | dragFoldersToFile | `saveStagedChanges(); updateCommitUI()` | `afterStagingChange()` |
| 1419-1420 | createMoveObjects | `saveStagedChanges(); updateCommitUI()` | `afterStagingChange()` |

**Step 2: Handle `save: false` sites — verify they're truly server-sync**

Sites using `afterStagingChange({ save: false })` (9 sites at lines 1254, 1269, 1563, 1631, 1644, 1657, 1670, 1683, 1735, 1871): These are unstage/revert operations where `saveStagedChanges()` was already called immediately before. Verify each one by reading the surrounding code. They should map to `afterServerSync()` via the wrapper.

**Step 3: Verify no regressions**

Run: `python3 app.py`
Test in browser:
- Drag an object to a different file → verify move is staged
- Create a new file → verify it appears in tree
- Delete a file → verify it's marked for deletion
- Unstage a file deletion → verify it reverts
- DevTools Network tab: verify reduced requests

**Step 4: Commit**

```bash
git add static/js/explorer/file-operations.js
git commit -m "refactor: migrate file-operations.js to staging orchestrators"
```

---

## Task 5: Migrate Server-Sync Flows

These are flows where the server is the source of truth — undo, apply, polling, clear, external changes.

**Files:**
- Modify: `static/js/explorer/data-loading.js` (undoLastAction, applyAllStaged, clearStagedChanges, checkPendingExternalChanges, polling)
- Modify: `static/js/explorer/app.js` (polling handler, init)
- Modify: `static/js/base.js` (handleUndoClick)

**Step 1: Migrate `undoLastAction` (data-loading.js:382-417)**

Current code calls `loadObjects(); loadStagedChanges(); refreshAfterObjectChange()`. The undo happened server-side, so this is a server-sync flow. Replace:

```javascript
Explorer.undoLastAction = async function() {
    if (undoInProgress) {
        return { success: false, message: 'Undo already in progress' };
    }
    undoInProgress = true;

    try {
        const result = await ApiClient.post('/api/staging/undo', {}, { silent: true });

        if (result.success && result.data?.success) {
            await Explorer.loadObjects();
            await Explorer.loadStagedChanges(false);
            Explorer.afterServerSync();

            const description = result.data.undone?.description || 'action';
            Explorer.showToast(`Undone: ${description}`, 'info');
            return { success: true, undone: result.data.undone };
        } else if (result.status === 404) {
            Explorer.showToast('Nothing to undo', 'info');
            return { success: false, message: 'Nothing to undo' };
        }
        const errorMsg = result.data?.error || result.error || 'Failed to undo';
        Explorer.showToast(errorMsg, 'error');
        return { success: false, message: errorMsg };
    } finally {
        undoInProgress = false;
    }
};
```

**Step 2: Migrate `handleUndoClick` (base.js:207-236)**

Remove the redundant `checkPendingChanges()` call after `undoLastAction()` returns — `afterServerSync` inside `undoLastAction` already calls `updateBadges()`.

```javascript
async function handleUndoClick() {
    if (typeof Explorer !== 'undefined' && Explorer.undoLastAction) {
        await Explorer.undoLastAction();
        // No checkPendingChanges() — afterServerSync inside undoLastAction handles badges
    } else {
        // Fallback: call API directly with concurrency guard
        if (_undoInProgress) {return;}
        _undoInProgress = true;
        try {
            const result = await ApiClient.post('/api/staging/undo', {}, { silent: true });

            if (result.success && result.data?.success) {
                const description = result.data.undone?.description || 'action';
                showToast(`Undone: ${description}`, 'info');
                checkPendingChanges();
                if (typeof buildTree === 'function') {buildTree();}
            } else if (result.status === 404) {
                showToast('Nothing to undo', 'info');
            } else {
                showToast(result.data?.error || result.error || 'Failed to undo', 'error');
            }
        } finally {
            _undoInProgress = false;
        }
    }
}
```

Note: the fallback path (non-Explorer pages) keeps `checkPendingChanges()` since it doesn't have access to `afterServerSync`.

**Step 3: Migrate `applyAllStaged` (data-loading.js:354-376)**

Current code does `resetStagingState(); loadObjects(); buildTree(); renderTargetPane(); updateCommitUI()`. Replace the manual UI calls with `afterServerSync`:

```javascript
Explorer.applyAllStaged = async function() {
    const result = await ApiClient.post('/api/staging/apply', {}, { silent: true });

    if (result.success && result.data?.success) {
        Explorer.resetStagingState();
        lastStagingTimestamp = null;
        await Explorer.loadObjects();
        Explorer.afterServerSync();

        Explorer.showToast('Changes applied successfully', 'success');
        return { success: true, results: result.data };
    }
    const errorMsg = result.data?.error || result.error || 'Failed to apply changes';
    Explorer.showToast(errorMsg, 'error');
    return { success: false, message: errorMsg };
};
```

**Step 4: Migrate `clearStagedChanges` (data-loading.js:237-251)**

Current code does `resetStagingState(); updateEditingLockedUI(); updateCommitUI()`. Replace:

```javascript
Explorer.clearStagedChanges = async function() {
    const result = await ApiClient.del('/api/staging', { silent: true });

    if (result.success) {
        Explorer.resetStagingState();
        window.isEditingLocked = false;
        Explorer.state.currentStagingOwner = null;
        lastStagingTimestamp = null;

        Explorer.updateEditingLockedUI();
        Explorer.afterServerSync();
    } else {
        Explorer.handleApiError('Failed to clear staged changes', result.error);
    }
};
```

**Step 5: Migrate `checkPendingExternalChanges` (data-loading.js:309-318)**

Current code does `loadStagedChanges(); buildTree(); renderTargetPane(); updateCommitUI()`. Replace:

```javascript
Explorer.checkPendingExternalChanges = async function() {
    const state = Explorer.state;
    if (state.externalChangePending) {
        state.externalChangePending = false;
        await Explorer.loadStagedChanges(false);
        Explorer.afterServerSync();
    }
};
```

**Step 6: Migrate polling in data-loading.js (lines 259-292)**

The polling handler at line 286 calls `refreshAfterObjectChange()`. Replace with `afterServerSync()`:

Change line 286 from:
```javascript
Explorer.refreshAfterObjectChange();
```
to:
```javascript
Explorer.afterServerSync();
```

**Step 7: Migrate app.js polling handler (lines 170-201)**

Current code at lines 181-183 does `updateCommitUI(); renderTargetPane(); buildTree()`. Replace with `Explorer.afterServerSync({ skipTarget: false })`.

At lines 191-195 does `updateCommitUI(); loadObjects(); renderTargetPane(); buildTree(); loadIssues()`. Replace:

```javascript
// Lines 173-184 (staging modified):
if (info.lastModified && info.lastModified !== lastStagingTimestamp) {
    if (isSavingStaging) {return;}
    await Explorer.loadStagedChanges(false);
    Explorer.afterServerSync();
}

// Lines 185-197 (staging cleared):
} else if (Explorer.hasStagedChanges() || state.isEditingLocked) {
    Explorer.resetStagingState();
    lastStagingTimestamp = null;
    state.isEditingLocked = false;
    Explorer.updateEditingLockedUI();
    await Explorer.loadObjects();
    Explorer.afterServerSync();
    loadIssues();
}
```

**Step 8: Migrate app.js init (line 314)**

Change `updateCommitUI()` at line 314 to `Explorer.updateBadges()`. At init, we just need badge counts — no need to POST staging or rebuild UI (tree is already built by this point).

**Step 9: Verify the undo flow specifically**

Run: `python3 app.py`
Open browser DevTools Network tab. Click undo (Ctrl+Z) after making an edit. Verify:
- Only these requests fire: POST /api/staging/undo → GET /api/objects + /api/files + /api/folders (parallel) → GET /api/staging → GET /api/staging/info → (500ms later) GET /api/health-check + suggestions
- NO POST /api/staging (staging is NOT re-sent to server)
- `/api/staging/info` is fetched exactly ONCE (not 3 times)

**Step 10: Commit**

```bash
git add static/js/explorer/data-loading.js static/js/explorer/app.js static/js/base.js
git commit -m "refactor: migrate server-sync flows to afterServerSync (undo, apply, polling)"
```

---

## Task 6: Remove Dead Code

Now that all callers use the new orchestrators, remove the old functions and side effects.

**Files:**
- Modify: `static/js/explorer/data-loading.js` (remove old saveStagedChanges, or gut it to delegate)
- Modify: `static/js/explorer/dialogs.js` (remove updateCommitUI wrapper)
- Modify: `static/js/explorer/state-management.js` (remove refreshAfterObjectChange or delegate)

**Step 1: Remove side effects from `saveStagedChanges`**

The old `saveStagedChanges` is still called by `afterStagingChange` wrapper (save=true path) through the old API. After Task 4, `afterStagingChange` no longer calls `saveStagedChanges` — it calls `afterFrontendMutation`. So we can now make `saveStagedChanges` a thin alias for `saveStaging`:

```javascript
// Backwards compatibility — delegates to side-effect-free saveStaging
Explorer.saveStagedChanges = Explorer.saveStaging;
```

**Step 2: Gut `refreshAfterObjectChange` to delegate to `rebuildUI` + `afterServerSync`**

Check if any callers still use `refreshAfterObjectChange` directly. After Tasks 2-5, there should be none (the polling handler in data-loading.js was migrated in Task 5 Step 6). If any remain, update them first.

Then replace the function body:

```javascript
// Backwards compatibility — delegates to rebuildUI + badges
// DEPRECATED: Use afterFrontendMutation() or afterServerSync() instead.
Explorer.refreshAfterObjectChange = function(options = {}) {
    Explorer.afterServerSync(options);
};
```

**Step 3: Remove `updateCommitUI` from dialogs.js**

Remove the function definition at lines 1318-1320. Remove the export at line 1387. Remove the wrapper in app.js line 21.

Check: `window.updateCommitUI` is referenced in state-management.js:325 (inside old `refreshAfterObjectChange`) — but that's now gutted. Search for any remaining references:

```bash
grep -r "updateCommitUI" static/js/ --include="*.js"
```

Remove all remaining references. If any call sites were missed in Tasks 2-5, migrate them now.

**Step 4: Verify `checkPendingChanges` in base.js**

`checkPendingChanges()` in base.js is still used by:
- The 5-second lock poll at base.js:313 (keep this — it's the non-Explorer fallback polling)
- The fallback undo path in base.js (keep this — non-Explorer pages)

It should NOT be called from `saveStagedChanges` anymore (which is now an alias for `saveStaging`). Verify this is the case.

**Step 5: Full regression test**

Run: `python3 app.py`
Open browser. Test the full workflow:
1. Open Explorer page — verify it loads cleanly
2. Edit an object → stage changes → verify tree + commit badge update
3. Create a new object → verify it appears
4. Delete an object → verify deletion staged
5. Undo (Ctrl+Z) → verify it reverts, commit count drops
6. Bulk rename → verify all objects renamed
7. Move object to different file (drag) → verify staged
8. Right-click → Clone → verify clone appears
9. Apply all changes → verify clean state
10. DevTools Network tab: spot-check each operation has minimal requests

**Step 6: Commit**

```bash
git add static/js/explorer/data-loading.js static/js/explorer/dialogs.js static/js/explorer/state-management.js static/js/explorer/app.js
git commit -m "refactor: remove dead staging orchestration code (updateCommitUI, refreshAfterObjectChange side effects)"
```

---

## Task 7: Final Cleanup and Documentation

**Files:**
- Modify: `static/js/explorer/CLAUDE.md` (document new pattern)

**Step 1: Update CLAUDE.md**

Add to the module index or a new section:

```markdown
## After-Mutation Protocol

Two orchestrators in `data-loading.js` handle all post-mutation work:

| Function | When to use | What it does |
|----------|-------------|--------------|
| `Explorer.afterFrontendMutation(opts)` | User edited/created/deleted/moved something | saveStaging → rebuildUI → updateBadges → debouncedAnalysis |
| `Explorer.afterServerSync(opts)` | Undo, apply, polling detected change | rebuildUI → updateBadges → debouncedAnalysis |

Both accept `options`: `{ skipTree, skipTarget, skipCenter, skipTabs }`.

**Rule:** After mutating staging state locally, call `afterFrontendMutation()`. After loading state from server, call `afterServerSync()`. Never manually compose `saveStagedChanges` + `buildTree` + `updateCommitUI`.
```

**Step 2: Verify the `afterStagingChange` wrapper in file-operations.js is still needed**

If all 25 call sites could be directly replaced with `afterFrontendMutation`/`afterServerSync`, remove the wrapper. Otherwise keep it as a convenience. Given its `save` and `tree` options map cleanly, the wrapper is fine to keep for now.

**Step 3: Commit**

```bash
git add static/js/explorer/CLAUDE.md
git commit -m "docs: document after-mutation protocol in explorer CLAUDE.md"
```
