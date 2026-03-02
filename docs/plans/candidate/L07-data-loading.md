# L07 — `static/js/explorer/data-loading.js` — MODIFY

## Purpose
Rewrite data loading to use candidate API. Remove all staging sync/poll/save functions and module-local staging state. Add candidate session management (poll, diff refresh, clear, apply). Preserve all real functionality (analysis debounce, external change detection, concurrent-request guards, undo guard).

## Removal Audit

### Module-local state variables being removed (lines 18-25)
| Line | Variable | Action |
|------|----------|--------|
| 18 | `stagingPollInterval` | REPLACED by `candidatePollInterval` (same guard pattern) |
| 19 | `lastStagingTimestamp` | REMOVED. Candidate diff comparison replaces timestamp-based change detection. |
| 20 | `isSavingStaging` | REMOVED. No client-side save; edits go to server immediately via CandidateApi. |
| 21 | `saveDebounceTimer` | REMOVED. No client-side save debouncing needed. |
| 22 | `saveInProgress` | REMOVED. No client-side save. |
| 23 | `analysisDebounceTimer` | KEPT. Analysis debounce still needed after candidate operations. |
| 24 | `isPollingInProgress` | KEPT. Guard against concurrent polling still needed. |
| 25 | `undoInProgress` | KEPT. Guard against concurrent undo requests still needed. |

### CONFIG constants being removed (lines 11-15)
| Line | Constant | Action |
|------|----------|--------|
| 12 | `ANALYSIS_DEBOUNCE_MS: 500` | KEPT. Still used for analysis debounce. |
| 13 | `SAVE_DEBOUNCE_RETRY_MS: 100` | REMOVED. No client-side save. |
| 14 | `STAGING_POLL_INTERVAL_MS: 3000` | RENAMED to `CANDIDATE_POLL_INTERVAL_MS: 5000`. |

### Functions being removed and their candidate equivalents
| Line(s) | Function | Action | Candidate Equivalent |
|----------|----------|--------|---------------------|
| 31-40 | `triggerAnalysisUpdate()` | KEPT. Called after candidate operations to update suggestions badge. |
| 50-72 | `Explorer.loadObjects()` | KEPT but MODIFIED. Adds `?candidate=1` suffix to `/api/objects`, `/api/files`, `/api/folders` when `state.candidateActive`. Metadata fetch unchanged. |
| 81-86 | `Explorer.getStagingHeaders()` | REMOVED. Dead code — replaced by `getSessionHeaders()` in L06-session-manager.md. |
| 91-161 | `Explorer.saveStagedChanges()` | REMOVED. No client-side staging state to save. All edits go directly to server via CandidateApi. |
| 166-200 | `syncStagingFromData()` (private) | REMOVED. No client-side staging state to sync. |
| 202-232 | `Explorer.loadStagedChanges()` | REMOVED. No client-side staging state to load. Candidate state comes via `refreshCandidateDiff()`. |
| 237-251 | `Explorer.clearStagedChanges()` | REPLACED by `Explorer.clearCandidateSession()` which calls `CandidateApi.clearSession()`. |
| 256-293 | `Explorer.startStagingPoll()` | REPLACED by `Explorer.startCandidatePoll()` which polls `CandidateApi.getDiff()`. |
| 298-303 | `Explorer.stopStagingPoll()` | REPLACED by `Explorer.stopCandidatePoll()`. Same pattern, new name. |
| 309-318 | `Explorer.checkPendingExternalChanges()` | KEPT but SIMPLIFIED. Still checks `state.externalChangePending` flag and refreshes UI, but calls `refreshCandidateDiff()` instead of `loadStagedChanges()`. |
| 328-348 | `Explorer.loadVirtualTree()` | REMOVED. In candidate mode, `/api/objects?candidate=1` returns candidate objects directly — no virtual tree merge needed. |
| 354-376 | `Explorer.applyAllStaged()` | REPLACED by `Explorer.applyCandidateChanges()` which calls `CandidateApi.apply()`. |
| 382-417 | `Explorer.undoLastAction()` | KEPT but REWRITTEN. Calls `CandidateApi.undo()` instead of `/api/staging/undo`. Retains `undoInProgress` guard. |
| 423-434 | `Explorer.checkConflicts()` | REPLACED. Calls `CandidateApi.getConflicts()` instead of `/api/staging/conflicts`. |
| 440-447 | `Explorer.getStagingInfoExtended()` | REMOVED. Use `CandidateApi.getDiff()` via `refreshCandidateDiff()` instead. |
| 453-455 | `Explorer.getUndoCount()` | REMOVED. Undo count comes from `state.candidateDiff.undoCount`. No client-side undoStack. |
| 461-473 | `Explorer.getTotalStagedCount()` | REMOVED. Total change count comes from `state.candidateDiff.totalCount`. No client-side staging Maps/Sets. |

### API endpoint changes
| Old Endpoint | Old Function | New CandidateApi Method |
|--------------|-------------|------------------------|
| `GET /api/staging` | `loadStagedChanges()` | REMOVED (no client-side state) |
| `POST /api/staging` | `saveStagedChanges()` | REMOVED (edits via CandidateApi) |
| `GET /api/staging/info` | `startStagingPoll()`, `getStagingInfoExtended()` | `CandidateApi.getDiff()` |
| `POST /api/staging/undo` | `undoLastAction()` | `CandidateApi.undo()` |
| `DELETE /api/staging` | `clearStagedChanges()` | `CandidateApi.clearSession()` |
| `POST /api/staging/apply` | `applyAllStaged()` | `CandidateApi.apply()` |
| `GET /api/staging/conflicts` | `checkConflicts()` | `CandidateApi.getConflicts()` |
| `GET /api/staging/virtual-tree` | `loadVirtualTree()` | REMOVED (candidate=1 on standard endpoints) |

## Changes

**1. Update CONFIG constants and module-local state:**
```javascript
const CONFIG = {
    ANALYSIS_DEBOUNCE_MS: 500,
    CANDIDATE_POLL_INTERVAL_MS: 5000
};

// Module-local state
let candidatePollInterval = null;
let analysisDebounceTimer = null;
let isPollingInProgress = false;
let undoInProgress = false;
```

**2. Keep `triggerAnalysisUpdate()` unchanged** — Still debounces analysis updates after candidate operations:
```javascript
function triggerAnalysisUpdate() {
    if (analysisDebounceTimer) {
        clearTimeout(analysisDebounceTimer);
    }
    analysisDebounceTimer = setTimeout(() => {
        if (typeof Explorer.loadAllSuggestions === 'function') {
            Explorer.loadAllSuggestions(true);
        }
    }, CONFIG.ANALYSIS_DEBOUNCE_MS);
}
```

**3. Modify `loadObjects()`** — Add `?candidate=1` suffix when candidate is active. Preserve existing Promise.all structure with `/api/objects`, `/api/files`, `/api/folders`, and `/api/metadata`:
```javascript
Explorer.loadObjects = async function() {
    const candidateSuffix = Explorer.state.candidateActive ? '?candidate=1&_=' + Date.now() : '?_=' + Date.now();

    const [objectsResult, filesResult, foldersResult, metadataResult] = await Promise.all([
        ApiClient.get('/api/objects' + candidateSuffix, { silent: true }),
        ApiClient.get('/api/files' + candidateSuffix, { silent: true }),
        ApiClient.get('/api/folders' + candidateSuffix, { silent: true }),
        Explorer.state.metadataLoaded
            ? Promise.resolve(null)
            : ApiClient.get('/api/metadata', { silent: true })
    ]);

    if (!objectsResult.success) {
        Explorer.handleApiError('Failed to load objects', objectsResult.error);
        return;
    }

    Explorer.state.allObjects = objectsResult.data || [];
    Explorer.state.allFiles = filesResult.data?.files || [];
    Explorer.state.existingFolders = foldersResult.data?.folders || [];

    // Populate constants from backend metadata (once)
    if (metadataResult && metadataResult.success) {
        Explorer.applyMetadata(metadataResult.data.data || metadataResult.data);
        Explorer.state.metadataLoaded = true;
    }

    // Validate open tabs against refreshed objects
    if (Explorer.validateTabs) { Explorer.validateTabs(); }
};
```

**4. Rewrite `undoLastAction()`** — Call CandidateApi with concurrent-request guard preserved:
```javascript
Explorer.undoLastAction = async function() {
    // H-028: Prevent concurrent undo requests (rapid Ctrl+Z / key repeat)
    if (undoInProgress) {
        return { success: false, message: 'Undo already in progress' };
    }
    undoInProgress = true;

    try {
        const result = await CandidateApi.undo();

        if (result.success) {
            await Explorer.loadObjects();
            await Explorer.refreshCandidateDiff();
            Explorer.refreshAfterObjectChange();
            triggerAnalysisUpdate();

            const description = result.data.description || 'action';
            Explorer.showToast(`Undone: ${description}`, 'info');
            return { success: true, undone: result.data };
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

**5. Replace `startStagingPoll()` with `startCandidatePoll()`** — Preserve concurrent-polling guard and external-change detection:
```javascript
Explorer.startCandidatePoll = function() {
    if (candidatePollInterval) { return; }

    candidatePollInterval = setInterval(async () => {
        if (isPollingInProgress) { return; }

        isPollingInProgress = true;
        try {
            const result = await CandidateApi.getDiff();

            if (result.success) {
                const diff = result.data;
                const state = Explorer.state;

                // Detect external changes (another tab/user edited the candidate)
                const prevCount = state.candidateDiff?.totalCount || 0;
                const newCount = diff.totalCount || 0;

                if (prevCount !== newCount) {
                    // If user is actively editing, don't disrupt them
                    if (state.editedObject) {
                        state.externalChangePending = true;
                        Explorer.showToast('External changes detected. Save or cancel your edit to refresh.', 'info');
                    } else {
                        state.candidateDiff = diff;
                        state.candidateActive = diff.active || false;
                        Explorer.computeCandidateBadges();
                        updateNavCommitButton(diff.totalCount || 0);
                        updateUndoButton(diff.undoCount || 0);
                        await Explorer.loadObjects();
                        Explorer.buildTree();
                    }
                }
            }
        } finally {
            isPollingInProgress = false;
        }
    }, CONFIG.CANDIDATE_POLL_INTERVAL_MS);
};
```

**6. Replace `stopStagingPoll()` with `stopCandidatePoll()`:**
```javascript
Explorer.stopCandidatePoll = function() {
    if (candidatePollInterval) {
        clearInterval(candidatePollInterval);
        candidatePollInterval = null;
    }
};
```

**7. Add `refreshCandidateDiff()`** — Updates candidate state from server:
```javascript
Explorer.refreshCandidateDiff = async function() {
    const result = await CandidateApi.getDiff();
    if (result.success) {
        Explorer.state.candidateDiff = result.data;
        Explorer.state.candidateActive = result.data.active || false;
        Explorer.computeCandidateBadges();
        if (typeof updateNavCommitButton === 'function') {
            updateNavCommitButton(result.data.totalCount || 0);
        }
        if (typeof updateUndoButton === 'function') {
            updateUndoButton(result.data.undoCount || 0);
        }
        triggerAnalysisUpdate();
    } else {
        console.error('Failed to refresh candidate diff:', result.error);
    }
};
```

**8. Add `clearCandidateSession()`:**
```javascript
Explorer.clearCandidateSession = async function() {
    const result = await CandidateApi.clearSession();
    if (result.success) {
        Explorer.state.candidateActive = false;
        Explorer.state.candidateDiff = null;
        await Explorer.loadObjects();
        Explorer.buildTree();
        Explorer.renderTargetPane();
        if (typeof updateNavCommitButton === 'function') {
            updateNavCommitButton(0);
        }
        if (typeof updateUndoButton === 'function') {
            updateUndoButton(0);
        }
        Explorer.showToast('Candidate session cleared', 'success');
    } else {
        const errorMsg = result.data?.error || result.error || 'Failed to clear candidate session';
        Explorer.showToast(errorMsg, 'error');
    }
    return result;
};
```

**9. Add `applyCandidateChanges()`:**
```javascript
Explorer.applyCandidateChanges = async function(options = {}) {
    const result = await CandidateApi.apply(options);
    if (result.success) {
        Explorer.state.candidateActive = false;
        Explorer.state.candidateDiff = null;
        await Explorer.loadObjects();
        Explorer.buildTree();
        Explorer.renderTargetPane();
        if (typeof updateNavCommitButton === 'function') {
            updateNavCommitButton(0);
        }
        if (typeof updateUndoButton === 'function') {
            updateUndoButton(0);
        }
        Explorer.showToast('Changes applied successfully', 'success');
        return { success: true, results: result.data };
    }
    const errorMsg = result.data?.error || result.error || 'Failed to apply changes';
    Explorer.showToast(errorMsg, 'error');
    return { success: false, message: errorMsg };
};
```

**10. Replace `checkConflicts()`** — Call CandidateApi:
```javascript
Explorer.checkConflicts = async function() {
    const result = await CandidateApi.getConflicts();
    if (result.success) {
        return {
            hasConflicts: result.data.hasConflicts || false,
            conflicts: result.data.conflicts || []
        };
    }
    Explorer.handleApiError('Failed to check conflicts', result.error);
    return { hasConflicts: false, conflicts: [] };
};
```

**11. Simplify `checkPendingExternalChanges()`** — Call candidate refresh instead of staging load:
```javascript
Explorer.checkPendingExternalChanges = async function() {
    const state = Explorer.state;
    if (state.externalChangePending) {
        state.externalChangePending = false;
        await Explorer.refreshCandidateDiff();
        await Explorer.loadObjects();
        Explorer.buildTree();
        Explorer.renderTargetPane();
    }
};
```

**12. Remove the following functions entirely (dead code in candidate mode):**
- `Explorer.getStagingHeaders()` — replaced by `getSessionHeaders()` in session-manager.js (L06)
- `Explorer.saveStagedChanges()` — no client-side staging state to save
- `syncStagingFromData()` (private) — no client-side staging state to sync
- `Explorer.loadStagedChanges()` — no client-side staging state to load
- `Explorer.loadVirtualTree()` — candidate=1 on standard endpoints replaces virtual tree
- `Explorer.getStagingInfoExtended()` — use `refreshCandidateDiff()` instead
- `Explorer.getUndoCount()` — use `state.candidateDiff.undoCount` instead
- `Explorer.getTotalStagedCount()` — use `state.candidateDiff.totalCount` instead

**13. Audit logging note:** All CandidateApi methods route to `/api/candidate/*` endpoints in routes/candidate.py, which handle audit logging per L03-routes-candidate.md. No additional frontend logging is required; the backend logs every candidate operation with session identity, operation type, and target details.

## Change Tracking

| # | Change | Status |
|---|--------|--------|
| 1 | Remove `isSavingStaging`, `saveDebounceTimer`, `saveInProgress`, `lastStagingTimestamp`, `stagingPollInterval` module vars | [ ] |
| 2 | Add `candidatePollInterval` module var | [ ] |
| 3 | Remove `SAVE_DEBOUNCE_RETRY_MS`, rename `STAGING_POLL_INTERVAL_MS` to `CANDIDATE_POLL_INTERVAL_MS` in CONFIG | [ ] |
| 4 | Keep `triggerAnalysisUpdate()` unchanged | [ ] |
| 5 | Modify `loadObjects()` to add `?candidate=1` when `state.candidateActive` | [ ] |
| 6 | Remove `getStagingHeaders()` | [ ] |
| 7 | Remove `saveStagedChanges()` | [ ] |
| 8 | Remove `syncStagingFromData()` | [ ] |
| 9 | Remove `loadStagedChanges()` | [ ] |
| 10 | Remove `clearStagedChanges()` | [ ] |
| 11 | Add `clearCandidateSession()` | [ ] |
| 12 | Remove `startStagingPoll()` | [ ] |
| 13 | Add `startCandidatePoll()` | [ ] |
| 14 | Remove `stopStagingPoll()` | [ ] |
| 15 | Add `stopCandidatePoll()` | [ ] |
| 16 | Simplify `checkPendingExternalChanges()` | [ ] |
| 17 | Remove `loadVirtualTree()` | [ ] |
| 18 | Remove `applyAllStaged()` | [ ] |
| 19 | Add `applyCandidateChanges()` | [ ] |
| 20 | Rewrite `undoLastAction()` to call CandidateApi | [ ] |
| 21 | Rewrite `checkConflicts()` to call CandidateApi | [ ] |
| 22 | Remove `getStagingInfoExtended()` | [ ] |
| 23 | Remove `getUndoCount()` | [ ] |
| 24 | Remove `getTotalStagedCount()` | [ ] |
| 25 | Add `refreshCandidateDiff()` | [ ] |
| 26 | Run `npm run lint:js` and fix any issues | [ ] |

## Verification
- `npm run lint:js` passes with zero errors
- Explorer loads and displays objects from live config (no candidate active)
- With candidate active, Explorer loads objects from candidate copy
- `Explorer.loadObjects` is callable and returns object/file/folder data
- `Explorer.undoLastAction()` reverts last change with toast notification; concurrent calls blocked
- `Explorer.startCandidatePoll()` / `Explorer.stopCandidatePoll()` start/stop polling without errors
- `Explorer.refreshCandidateDiff()` updates `state.candidateDiff` and badge counts
- `Explorer.clearCandidateSession()` resets state and reloads live data
- `Explorer.applyCandidateChanges()` writes candidate to live and resets state
- `Explorer.checkConflicts()` returns conflict data
- `Explorer.checkPendingExternalChanges()` refreshes UI when external changes were deferred
- No console errors
- No references to `saveStagedChanges`, `loadStagedChanges`, `getStagingHeaders`, `loadVirtualTree`, `getStagingInfoExtended`, `getUndoCount`, `getTotalStagedCount`, `startStagingPoll`, `stopStagingPoll` remain in this file

### Playwright Tests
- Load Explorer page, verify object tree renders without JS errors
- Perform an edit via candidate, verify undo reverts the change
- Verify polling starts/stops without console errors
- Verify apply flow: edit object, apply, confirm changes written to live config

## Commandments Compliance

- [x] **1. No live config mutation until Apply.** `loadObjects()` reads from candidate copy when `state.candidateActive`. All mutations route through CandidateApi to candidate directory. `applyCandidateChanges()` is the only path that writes to live config.
- [x] **2. UI visual parity.** `loadObjects()` preserves existing Promise.all structure with all 4 endpoints. External change detection, toast notifications, undo guards, and analysis debounce all preserved. No gratuitous UI changes.
- [x] **3. Full audit logging.** All CandidateApi methods route to `/api/candidate/*` endpoints which handle audit logging per L03-routes-candidate.md. Noted explicitly in Change 13.
- [x] **4. Proper error handling.** Every function has explicit error handling: `loadObjects()` calls `handleApiError` on failure; `undoLastAction()` handles 404 and generic errors; `refreshCandidateDiff()` logs errors to console; `clearCandidateSession()` shows error toast; `applyCandidateChanges()` shows error toast and returns error result; `checkConflicts()` calls `handleApiError`; polling has try/finally guard.
- [x] **5. Dead code deletion.** All 8 staging-only functions explicitly listed for removal: `getStagingHeaders`, `saveStagedChanges`, `syncStagingFromData`, `loadStagedChanges`, `loadVirtualTree`, `getStagingInfoExtended`, `getUndoCount`, `getTotalStagedCount`. Module-local staging variables removed.
- [x] **6. Full functionality migration.** Every existing function has a candidate equivalent or is explicitly kept: `triggerAnalysisUpdate()` kept, `checkPendingExternalChanges()` simplified but kept, `stopStagingPoll()` replaced by `stopCandidatePoll()`, concurrent-request guards preserved, undo guard preserved, analysis debounce preserved.
- [x] **7. Palo Alto candidate model.** `loadObjects()` reads from candidate copy when active. Edits go to candidate via CandidateApi. Only `applyCandidateChanges()` promotes candidate to live. `clearCandidateSession()` discards without touching live.
- [x] **8. Change tracking document.** Change Tracking table with 26 items covers every addition, removal, and modification.
- [x] **9. Complete planning before implementation.** Full code snippets for all 12 new/modified functions. Line-number references to existing code. Removal audit with line numbers for all 18 existing functions and all module-local state.
- [x] **10. Linting enforcement.** `npm run lint:js` listed as first verification step. Change tracking item 26 explicitly requires lint pass.
- [x] **11. Playwright validation.** Playwright test cases listed in Verification section covering load, edit/undo, polling, and apply flows.
