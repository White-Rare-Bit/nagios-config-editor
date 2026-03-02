# Candidate Config — Phase 3: Frontend Integration

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create the CandidateApi JS wrapper, integrate candidate-aware data loading and object operations into the explorer, update the commit dialog and git page, and verify with linting + Playwright smoke test.

**Architecture:** Thin JS wrapper (`CandidateApi`) calls candidate routes. Explorer modules check `state.candidateActive` to decide whether to call CandidateApi or the old staging endpoints. Auto-init on first edit eliminates the "Start Editing" button.

**Tech Stack:** JavaScript (IIFE pattern), ESLint, Playwright MCP

**Branch:** `feature/candidate-config` (continuing from Phase 2)

**Prerequisite:** Phase 2 must be complete. Verify before starting.

---

## Key Codebase Facts

| Fact | Detail |
|------|--------|
| **ApiClient methods** | `ApiClient.post()`, `ApiClient.get()`, `ApiClient.del()` — there is NO `.delete()` method |
| **Session ID location** | `getSessionId()` global function (from `session-manager.js`), also stored in `Explorer.state.sessionId`. `baseState` has NO `sessionId` field |
| **getUserIdentity()** | Returns `{userName, userEmail}` from `session-manager.js`. Available on all pages |
| **Explorer namespace** | All modules attach to `window.Explorer`. State in `Explorer.state` |
| **Event delegation** | `data-action` attributes → `actionHandlers` map in `main.js` |
| **ESLint globals** | Defined in `eslint.config.mjs` → `projectGlobals` object |
| **Script load order** | `base.html`: `base-state.js` → `api-client.js` → `session-manager.js` → `ui-notifications.js` → ... → page scripts |
| **`Explorer.refreshAfterObjectChange()`** | Exists in `state-management.js`. Calls buildTree, renderTargetPane, syncCenterPaneAfterUndo, loadAllSuggestions, updateCommitUI, renderTabBar. Use this everywhere — do NOT create `refreshAfterCandidateChange()` |
| **`afterStagingChange()`** | Local function inside `file-operations.js` IIFE (line 26). NOT on Explorer namespace. Cannot be called from other modules |
| **`stageCurrentChanges()`** | Local function inside `object-editor.js` IIFE (line 1184). NOT on Explorer namespace |
| **`stageObjectDeletions()`** | Defined in `dialogs.js`, NOT `context-menu.js`. Exported at line 1376 |
| **`checkPendingChanges()`** | In `base.js:257`. Calls `/api/staging/info` for change count |
| **`handleUndoClick()`** | In `base.js:207`. Delegates to `Explorer.undoLastAction()` then falls back to `/api/staging/undo` |
| **Field value reading** | `object-editor.js` does NOT have `readFieldValues()` or `readInlineComments()` functions. Edited attributes are stored in `state.editedObject.attributes` (set via `updateAttribute()` at line 911-916). Inline comments are in `state.editedObject.inline_comments`. Read these from state, not from DOM |
| **`saveStagedChanges()` call count** | 38 call sites across `context-menu.js`, `dialogs.js`, `object-editor.js`, `file-operations.js`, `analysis.js`, `analysis-issues.js`, `analysis-suggestions.js`. Every site must be handled |
| **`applyBulkAttribute()`** | In `context-menu.js` — bulk attribute change from context menu. There is NO `executeBulkEditAction()` function |

---

## Prerequisites

**Step 1: Verify Phase 2 is complete**

```bash
cd .worktrees/candidate-config
python3 -m pytest tests/ -v
```

Expected: all tests pass including `test_candidate_routes.py`

---

## Task 1: CandidateApi wrapper

**Files:**
- Create: `static/js/candidate-api.js`
- Modify: `eslint.config.mjs` (add `CandidateApi` to `projectGlobals`)
- Modify: `templates/base.html` (add `<script>` tag after `api-client.js`)

**Step 1: Create candidate-api.js**

```javascript
/* global ApiClient, getSessionId, getUserIdentity, Explorer, showToast, DebugLogger */
/**
 * Thin wrapper around ApiClient for candidate config endpoints.
 * All business logic lives on the backend.
 *
 * IMPORTANT: Uses getSessionId() (from session-manager.js), NOT baseState.sessionId
 * which does not exist. getSessionId() is available on all pages.
 */
// eslint-disable-next-line no-unused-vars
const CandidateApi = {
    _sessionId() {
        return typeof getSessionId === 'function' ? getSessionId() : 'default';
    },

    init(userName, userEmail) {
        return ApiClient.post('/api/candidate/init', {
            session_id: this._sessionId(),
            user_name: userName || '',
            user_email: userEmail || '',
        });
    },

    status() {
        return ApiClient.get('/api/candidate');
    },

    // IMPORTANT: ApiClient exposes .del(), NOT .delete()
    discard() {
        return ApiClient.del('/api/candidate');
    },

    editObject(filePath, lineNumber, attributes, objectType, inlineComments, updateReferences) {
        return ApiClient.post('/api/candidate/edit', {
            session_id: this._sessionId(),
            file_path: filePath,
            line_number: lineNumber,
            attributes: attributes,
            object_type: objectType,
            inline_comments: inlineComments || {},
            update_references: updateReferences || false,
        });
    },

    deleteObjects(objects) {
        return ApiClient.post('/api/candidate/delete-objects', {
            session_id: this._sessionId(),
            objects: objects,
        });
    },

    createObject(filePath, objectType, attributes, afterLine, inlineComments) {
        return ApiClient.post('/api/candidate/create', {
            session_id: this._sessionId(),
            file_path: filePath,
            object_type: objectType,
            attributes: attributes,
            after_line: afterLine || null,
            inline_comments: inlineComments || {},
        });
    },

    moveObject(sourceFile, sourceLine, targetFile, objectType, attributes, insertLine) {
        return ApiClient.post('/api/candidate/move', {
            session_id: this._sessionId(),
            source_file: sourceFile,
            source_line: sourceLine,
            target_file: targetFile,
            object_type: objectType,
            attributes: attributes,
            insert_line: insertLine || null,
        });
    },

    undo() {
        return ApiClient.post('/api/candidate/undo', {
            session_id: this._sessionId(),
        });
    },

    getDiff() {
        return ApiClient.get('/api/candidate/diff');
    },

    getFileDiff(path, contextLines) {
        return ApiClient.post('/api/candidate/diff/file', {
            path: path,
            context_lines: contextLines || 3,
        });
    },

    getObjects() {
        return ApiClient.get('/api/candidate/objects');
    },

    getFiles() {
        return ApiClient.get('/api/candidate/files');
    },

    getFolders() {
        return ApiClient.get('/api/candidate/folders');
    },

    getConflicts() {
        return ApiClient.get('/api/candidate/conflicts');
    },

    healthCheck() {
        return ApiClient.get('/api/candidate/health-check');
    },

    validate() {
        return ApiClient.post('/api/candidate/validate');
    },

    apply(options) {
        const payload = {
            session_id: this._sessionId(),
        };
        // [P3-I] Support deferClear for apply+commit recovery flow
        if (options && options.deferClear) {
            payload.deferClear = true;
        }
        return ApiClient.post('/api/candidate/apply', payload);
    },

    // [P3-I] Clean up candidate after successful git commit (deferred clear)
    clearAfterCommit() {
        return ApiClient.post('/api/candidate/clear-after-commit', {
            session_id: this._sessionId(),
        });
    },

    bulkEdit(edits, description) {
        return ApiClient.post('/api/candidate/bulk-edit', {
            session_id: this._sessionId(),
            edits: edits,
            description: description || '',
        });
    },

    bulkMove(moves, description) {
        return ApiClient.post('/api/candidate/bulk-move', {
            session_id: this._sessionId(),
            moves: moves,
            description: description || '',
        });
    },

    // File/folder operations
    createFile(filePath) {
        return ApiClient.post('/api/candidate/file/create', {
            session_id: this._sessionId(),
            file_path: filePath,
        });
    },

    deleteFile(filePath) {
        return ApiClient.post('/api/candidate/file/delete', {
            session_id: this._sessionId(),
            file_path: filePath,
        });
    },

    moveFile(source, target) {
        return ApiClient.post('/api/candidate/file/move', {
            session_id: this._sessionId(),
            source: source,
            target: target,
        });
    },

    createFolder(path) {
        return ApiClient.post('/api/candidate/folder/create', {
            session_id: this._sessionId(),
            path: path,
        });
    },

    deleteFolder(path) {
        return ApiClient.post('/api/candidate/folder/delete', {
            session_id: this._sessionId(),
            path: path,
        });
    },

    moveFolder(source, target) {
        return ApiClient.post('/api/candidate/folder/move', {
            session_id: this._sessionId(),
            source: source,
            target: target,
        });
    },

    /**
     * Ensure a candidate session exists. Auto-inits if needed.
     * Safe against race conditions (checks status if init fails).
     * [P3-F] Deduplicates concurrent init calls via _initPromise.
     * @returns {Promise<boolean>} True if session is active
     */
    _initPromise: null, // [P3-F] Debounce guard

    async ensureSession() {
        // Check Explorer state first (avoid unnecessary API call)
        if (typeof Explorer !== 'undefined' && Explorer.state.candidateActive) {
            return true;
        }
        // [P3-F] Deduplicate concurrent init calls
        if (this._initPromise) {
            return this._initPromise;
        }

        this._initPromise = this._doEnsureSession();
        try {
            return await this._initPromise;
        } finally {
            this._initPromise = null;
        }
    },

    async _doEnsureSession() {
        // Check server
        const status = await this.status();
        if (status.success && status.data?.active) {
            if (typeof Explorer !== 'undefined') {
                Explorer.state.candidateActive = true;
            }
            return true;
        }
        // Init new session
        const identity = typeof getUserIdentity === 'function' ? getUserIdentity() : {};
        const initResult = await this.init(identity.userName, identity.userEmail);
        if (initResult.success) {
            if (typeof Explorer !== 'undefined') {
                Explorer.state.candidateActive = true;
            }
            return true;
        }
        // Race: another tab may have created it
        const recheck = await this.status();
        if (recheck.success && recheck.data?.active) {
            if (typeof Explorer !== 'undefined') {
                Explorer.state.candidateActive = true;
            }
            return true;
        }
        if (typeof DebugLogger !== 'undefined') {
            DebugLogger.log('ensureSession failed — init:', initResult.error, 'recheck:', recheck.error);
        }
        showToast('Failed to start editing session: ' + (initResult.error || 'Unknown error'), 'error');
        return false;
    },
};
```

**Step 2: Add `CandidateApi` to eslint globals**

In `eslint.config.mjs`, add to `projectGlobals`:
```javascript
CandidateApi: 'readonly',
```

**Step 3: Add `<script>` tag to `templates/base.html`**

After the `api-client.js` script tag, add:
```html
<script src="{{ url_for('static', filename='js/candidate-api.js') }}"></script>
```

**Step 4: Lint and commit**

```bash
npx eslint static/js/candidate-api.js
git add static/js/candidate-api.js eslint.config.mjs templates/base.html
git commit -m "feat: CandidateApi JS wrapper for candidate endpoints"
```

---

## Task 2: Candidate-aware data loading

**Files:**
- Modify: `static/js/explorer/data-loading.js`
- Modify: `static/js/explorer/state-management.js`
- Modify: `static/js/explorer/main.js`

**Amendments integrated:** P3-E (staged issues badges), P3-K (conflict polling), P3-M (tab modification indicators), P3-O (loadStagedChanges guards), P3-P (double API call optimization)

**Step 1: Add `candidateActive` and `candidateDiff` to state in main.js**

In `Explorer.state`, add:
```javascript
candidateActive: false,
candidateDiff: null, // [P3-M] Cached diff data for badge computation
```

**Step 2: Modify `loadObjects()` in data-loading.js**

At the top of `loadObjects()`, check for active candidate session. If active, fetch objects/files/folders from candidate endpoints instead:

```javascript
Explorer.loadObjects = async function() {
    const state = Explorer.state;

    // Detect candidate mode
    const candidateResult = await ApiClient.get('/api/candidate', { silent: true });
    const useCandidate = candidateResult.success && candidateResult.data?.active;
    state.candidateActive = useCandidate;

    const [objectsResult, filesResult, foldersResult, metadataResult] = await Promise.all([
        useCandidate
            ? CandidateApi.getObjects()
            : ApiClient.get('/api/objects?_=' + Date.now(), { silent: true }),
        useCandidate
            ? CandidateApi.getFiles()
            : ApiClient.get('/api/files?_=' + Date.now(), { silent: true }),
        useCandidate
            ? CandidateApi.getFolders()
            : ApiClient.get('/api/folders?_=' + Date.now(), { silent: true }),
        state.metadataLoaded
            ? Promise.resolve(null)
            : ApiClient.get('/api/metadata', { silent: true })
    ]);

    // Candidate responses nest data differently
    if (useCandidate) {
        state.allObjects = objectsResult.data?.data || [];
        state.allFiles = filesResult.data?.files || [];
        state.existingFolders = foldersResult.data?.folders || [];
    } else {
        state.allObjects = objectsResult.data || [];
        state.allFiles = filesResult.data?.files || [];
        state.existingFolders = foldersResult.data?.folders || [];
    }

    if (metadataResult && metadataResult.success) {
        Explorer.applyMetadata(metadataResult.data.data || metadataResult.data);
        state.metadataLoaded = true;
    }

    // [P3-M] Cache candidate diff for badge/indicator computation
    if (useCandidate) {
        const diffResult = await CandidateApi.getDiff();
        if (diffResult.success) {
            state.candidateDiff = diffResult.data?.data || diffResult.data;
        }
    } else {
        state.candidateDiff = null;
    }

    if (Explorer.validateTabs) { Explorer.validateTabs(); }
};
```

**Step 3: Add `loadStagedChanges()` candidate guard [P3-O]**

At the top of `loadStagedChanges()` in `data-loading.js`, add a guard to prevent calling `/api/staging` in candidate mode (which may not exist after Phase 4):

```javascript
async function loadStagedChanges(showErrors) {
    // [P3-O] In candidate mode, staging state comes from candidate diff — skip staging load
    if (state.candidateActive) {
        return;
    }
    // ... existing staging load path unchanged ...
}
```

**Step 4: Rewrite `startStagingPoll()` for candidate mode (data-loading.js:256)**

When `state.candidateActive`, poll candidate status instead of staging info. Includes [P3-K] conflict detection and [P3-P] single API call optimization:

```javascript
Explorer.startStagingPoll = function() {
    if (stagingPollInterval) { return; }

    stagingPollInterval = setInterval(async () => {
        if (isSavingStaging || isPollingInProgress) { return; }
        isPollingInProgress = true;
        try {
            // Candidate mode: poll candidate status
            const candidateResult = await ApiClient.get('/api/candidate', { silent: true });
            if (!candidateResult.success) {
                // Network error or server down — skip this poll cycle
                if (typeof DebugLogger !== 'undefined') {
                    DebugLogger.log('Candidate poll failed:', candidateResult.error);
                }
                return;
            }
            if (candidateResult.data?.active) {
                const sessionData = candidateResult.data.data || {};
                const mySessionId = typeof getSessionId === 'function' ? getSessionId() : '';
                const isOwner = sessionData.session_id === mySessionId;

                if (!isOwner && !Explorer.state.candidateActive) {
                    // Another user started a session
                    window.isEditingLocked = true;
                    Explorer.updateEditingLockedUI();
                } else if (isOwner && Explorer.state.candidateActive) {
                    // Our session — check for external changes (e.g., edits from another tab)
                    // [P3-K] Also check for conflicts with running config
                    pollCandidateConflicts();
                }
                return;
            }

            // No candidate session
            if (Explorer.state.candidateActive) {
                // Session was discarded externally (break lock or other tab)
                Explorer.state.candidateActive = false;
                Explorer.state.candidateDiff = null;
                window.isEditingLocked = false;
                Explorer.updateEditingLockedUI();
                await Explorer.loadObjects();
                Explorer.refreshAfterObjectChange();
                Explorer.showToast('Editing session ended externally', 'info');
            }
        } catch (pollError) {
            if (typeof DebugLogger !== 'undefined') {
                DebugLogger.log('Candidate poll exception:', pollError);
            }
        } finally {
            isPollingInProgress = false;
        }
    }, CONFIG.STAGING_POLL_INTERVAL_MS);
};
```

**Step 5: Add candidate conflict polling [P3-K]**

Add this function inside the `data-loading.js` IIFE:

```javascript
// [P3-K] Poll for conflicts between candidate and running config
async function pollCandidateConflicts() {
    if (!state.candidateActive) { return; }
    const result = await ApiClient.get('/api/candidate/conflicts', { silent: true });
    if (result.success && result.data?.length > 0) {
        state.externalChangePending = true;
        Explorer.showToast(
            'External changes detected in running config. Review conflicts before applying.',
            'warning'
        );
    }
}
```

**Step 6: Add candidate badge computation [P3-E, P3-M]**

Add these functions to `state-management.js` (or wherever `computeStagedIssues()` is defined):

```javascript
// [P3-M] Compute file modification badges from candidate diff data
function computeCandidateBadges() {
    if (!state.candidateDiff) { return {}; }
    const badges = {};
    for (const file of state.candidateDiff.changed_files || []) {
        badges[file.relative_path] = file.status;  // "modified", "created", "deleted"
    }
    return badges;
}
```

Update `computeStagedIssues()` to use candidate diff data when in candidate mode:

```javascript
// [P3-E] In the existing computeStagedIssues(), add a candidate branch at top:
function computeStagedIssues() {
    // [P3-E] Candidate mode: derive badge counts from diff, not pendingEdits
    if (state.candidateActive) {
        return computeCandidateBadges();
    }
    // ... existing staging badge computation unchanged ...
}
```

**Step 7: Optimize `checkPendingChanges()` polling [P3-P]**

When `checkPendingChanges()` runs in candidate mode, it makes two API calls (status + diff). Use the cached `state.candidateDiff` when available to avoid the second call:

```javascript
// [P3-P] In the candidate branch of checkPendingChanges() (base.js),
// use cached diff if available to reduce polling overhead:
if (state.candidateDiff) {
    const count = (state.candidateDiff.changed_files || []).length;
    const undoCount = state.candidateDiff.undo_count || 0;
    updateNavCommitButton(count);
    updateUndoButton(undoCount);
    return;
}
// Otherwise fall through to fetch diff from API
```

**Step 8: Lint and commit**

```bash
npx eslint static/js/explorer/data-loading.js static/js/explorer/state-management.js static/js/explorer/main.js
git add static/js/explorer/data-loading.js static/js/explorer/state-management.js static/js/explorer/main.js
git commit -m "feat: candidate-aware object loading, badges, conflict polling, and UI refresh"
```

---

## Task 3: Candidate-aware save, delete, create, move, undo

**Files:**
- Modify: `static/js/explorer/object-editor.js`
- Modify: `static/js/explorer/context-menu.js`
- Modify: `static/js/explorer/file-operations.js`
- Modify: `static/js/explorer/dialogs.js` (bulk rename candidate branch)
- Modify: `static/js/base.js`

**Amendments integrated:** P3-A (fix field reading), P3-B (stay in edit mode), P3-C (context menu ops), P3-F (debounce — already in Task 1), P3-G (new object creation), P3-H (hostgroup service link), P3-J (revert-to-original), P3-L (clearStagedChanges discard), P3-N (enumerate saveStagedChanges call sites), P3-Q (async dialog callbacks)

**Key pattern for all operations — auto-init with race protection:**

```javascript
CandidateApi.ensureSession()
```

All operations call `CandidateApi.ensureSession()` (defined in `candidate-api.js`, includes [P3-F] debounce) before their API call — no separate helper function needed.

**Step 1: Rewrite `stageCurrentChanges()` for candidate mode (object-editor.js:1184) [P3-A, P3-B]**

The current function stores edits in `state.pendingEdits` then posts to `/api/staging`. Replace the staging path with direct API calls.

**CRITICAL [P3-A]:** The plan originally referenced `readFieldValues()` and `readInlineComments()` — these functions DO NOT EXIST. The actual pattern in `object-editor.js` reads edited attributes from `state.editedObject.attributes` (set via `updateAttribute()` at line 911-916) and inline comments from `state.editedObject.inline_comments`. Use these state references, not DOM reads.

```javascript
async function stageCurrentChanges() {
    const globalIndex = state.editedObject.global_index;

    // C-05: Validate required fields (warning only)
    // [P3-A] Read from state.editedObject.attributes, NOT readFieldValues()
    const editedAttrs = { ...state.editedObject.attributes };
    const validation = validateRequiredFields(
        state.editedObject.object_type,
        editedAttrs
    );
    if (validation.missing.length > 0) {
        Explorer.showToast(
            `Warning: Missing recommended fields: ${validation.missing.join(', ')}`,
            'warning'
        );
    }

    // [P3-A] Read inline comments from state, NOT readInlineComments()
    const inlineComments = state.editedObject.inline_comments || {};
    const updateRefs = document.getElementById('updateReferencesCheckbox')?.checked || false;

    // Ensure candidate session exists (auto-init)
    const ready = await CandidateApi.ensureSession();
    if (!ready) { return; }

    const result = await CandidateApi.editObject(
        state.editedObject.source_file,
        state.editedObject.line_number,
        editedAttrs,
        state.editedObject.object_type,
        inlineComments,
        updateRefs
    );

    if (!result.success) {
        if (typeof DebugLogger !== 'undefined') {
            DebugLogger.log('Candidate edit failed:', result.error, 'file:', state.editedObject.source_file);
        }
        Explorer.showToast(result.error || 'Failed to save', 'error');
        return;
    }

    // [P3-B] Reload objects but STAY in edit mode (existing behavior)
    await Explorer.loadObjects();
    Explorer.refreshAfterObjectChange();

    // [P3-B] Re-select edited object and keep edit mode open
    const updatedObj = state.allObjects.find(o => o.global_index === globalIndex);
    if (updatedObj) {
        state.currentCenterObject = updatedObj;
        Explorer.renderCenterPane(updatedObj);
        state.editedObject = updatedObj; // Stay in edit mode
        Explorer.loadImpactAndRelationships(updatedObj);
    }

    Explorer.showToast('Saved', 'success');
}
```

**Important:** This replaces the `pendingEdits` map pattern entirely. In candidate mode, saves go directly to the backend. The `pendingEdits` map becomes dead code (removed in Phase 4).

**Step 2: Add candidate branch to `stageObjectDeletions()` (dialogs.js:1376)**

**IMPORTANT:** The delete code is in `dialogs.js`, NOT `context-menu.js`. `stageObjectDeletions()` is exported at line 1376.

Add a candidate branch at the top of `stageObjectDeletions(objectsToDelete)`:

```javascript
// At the start of stageObjectDeletions(objectsToDelete):
if (state.candidateActive) {
    const ready = await CandidateApi.ensureSession();
    if (!ready) { return; }
    const deletePayload = objectsToDelete.map(obj => ({
        file_path: obj.source_file,
        line_number: obj.line_number,
    }));
    const result = await CandidateApi.deleteObjects(deletePayload);
    if (!result.success) {
        if (typeof DebugLogger !== 'undefined') {
            DebugLogger.log('Candidate delete failed:', result.error, 'count:', objectsToDelete.length);
        }
        Explorer.showToast(result.error || 'Delete failed', 'error');
        return;
    }
    await Explorer.loadObjects();
    Explorer.refreshAfterObjectChange();
    Explorer.showToast(`Deleted ${objectsToDelete.length} object(s)`, 'success');
    return;
}
// ... existing staging code below unchanged ...
```

**Note:** The function must become `async` if it isn't already.

**Step 3: Add candidate branch to `afterStagingChange()` (file-operations.js:26)**

`afterStagingChange()` is a local function inside the `file-operations.js` IIFE — NOT on the Explorer namespace. Add a candidate branch:

```javascript
function afterStagingChange(options = {}) {
    // Candidate mode: skip staging save, just refresh
    if (state.candidateActive) {
        Explorer.refreshAfterObjectChange();
        return;
    }
    // Original staging path
    const { save = true, tree = true } = options;
    if (save) {Explorer.saveStagedChanges();}
    Explorer.updateCommitUI();
    renderTargetPane();
    if (tree) {Explorer.buildTree();}
}
```

**Step 4: Add candidate branches to file/folder operation handlers (file-operations.js)**

For each file/folder operation (create file, delete file, move file, create folder, delete folder, move folder), add a candidate branch before the staging code:

```javascript
// Example: in the file creation handler
if (state.candidateActive) {
    const ready = await CandidateApi.ensureSession();
    if (!ready) { return; }
    const result = await CandidateApi.createFile(filePath);
    if (!result.success) {
        if (typeof DebugLogger !== 'undefined') {
            DebugLogger.log('Candidate file op failed:', result.error, 'path:', filePath);
        }
        Explorer.showToast(result.error || 'Failed to create file', 'error');
        return;
    }
    await Explorer.loadObjects();
    afterStagingChange(); // Will hit the candidate branch
    return;
}
```

Apply the same pattern for `deleteFile`, `moveFile`, `createFolder`, `deleteFolder`, `moveFolder` — each calls the matching `CandidateApi.*` method, then reloads and refreshes.

**Step 5: Add candidate branch to `Explorer.undoLastAction()` (data-loading.js:382)**

```javascript
Explorer.undoLastAction = async function() {
    if (undoInProgress) {
        return { success: false, message: 'Undo already in progress' };
    }
    undoInProgress = true;

    try {
        // Candidate mode: undo via CandidateApi
        if (Explorer.state.candidateActive) {
            const result = await CandidateApi.undo();
            if (result.success) {
                await Explorer.loadObjects();
                Explorer.refreshAfterObjectChange();
                const description = result.data?.data?.description || 'action';
                Explorer.showToast(`Undone: ${description}`, 'info');
                return { success: true, undone: { description } };
            }
            if (result.error?.includes('Nothing to undo')) {
                Explorer.showToast('Nothing to undo', 'info');
                return { success: false, message: 'Nothing to undo' };
            }
            if (typeof DebugLogger !== 'undefined') {
                DebugLogger.log('Candidate undo failed:', result.error);
            }
            Explorer.showToast(result.error || 'Failed to undo', 'error');
            return { success: false, message: result.error };
        }

        // ... existing staging undo code unchanged ...
```

**Step 6: Add candidate branch to `checkPendingChanges()` (base.js:257)**

```javascript
async function checkPendingChanges() {
    // Candidate mode: check candidate status
    const candidateResult = await ApiClient.get('/api/candidate', { silent: true });
    if (candidateResult.success && candidateResult.data?.active) {
        // [P3-P] Use cached diff if available
        if (typeof Explorer !== 'undefined' && Explorer.state.candidateDiff) {
            const diffData = Explorer.state.candidateDiff;
            const count = (diffData.changed_files || []).length;
            const undoCount = diffData.undo_count || 0;
            updateNavCommitButton(count);
            updateUndoButton(undoCount);
            return;
        }
        const diffResult = await CandidateApi.getDiff();
        if (diffResult.success) {
            const diffData = diffResult.data?.data || diffResult.data;
            const count = (diffData?.changed_files || []).length;
            const undoCount = diffData?.undo_count || 0;
            updateNavCommitButton(count);
            updateUndoButton(undoCount);
        }
        return;
    }

    // No candidate session — check for git-only changes
    const gitResult = await ApiClient.get('/api/git/status', { silent: true });
    if (gitResult.success && gitResult.data?.has_changes) {
        updateNavCommitButton(gitResult.data.files.length);
    } else {
        updateNavCommitButton(0);
    }
    updateUndoButton(0);
}
```

Drag-drop handler: when `state.candidateActive`, call `CandidateApi.moveObject()` directly.

**Step 7: Add candidate branch to bulk rename (dialogs.js:873)**

`executeBulkRename()` currently stages edits into `state.pendingEdits` via `applyBulkRenameEdits()`, then calls `stageBulkReferenceUpdates()` and `Explorer.saveStagedChanges()`. In candidate mode, use `CandidateApi.bulkEdit()` instead.

Add a candidate branch at the top of `executeBulkRename()`:

```javascript
function executeBulkRename(find, replace, shouldUpdateRefs) {
    if (state.candidateActive) {
        executeBulkRenameCandidate(find, replace, shouldUpdateRefs);
        return;
    }
    // ... existing staging code unchanged ...
}
```

Add the new async function after `executeBulkRename()`:

```javascript
async function executeBulkRenameCandidate(find, replace, shouldUpdateRefs) {
    const ready = await CandidateApi.ensureSession();
    if (!ready) { return; }

    // [P3-Q] Show loading state in dialog during async operation
    const confirmBtn = document.querySelector('.dialog-confirm-btn');
    if (confirmBtn) {
        confirmBtn.disabled = true;
        confirmBtn.textContent = 'Renaming...';
    }

    // Build list of edits: each {file_path, line_number, attributes, object_type}
    const edits = [];
    const renames = []; // Track for reference updates

    for (const idx of Explorer.getSelectedIndices()) {
        const obj = state.allObjects.find(o => o.global_index === idx);
        if (!obj) { continue; }

        const nameField = Explorer.getNameFieldForObject(obj);
        const currentName = obj.attributes[nameField] || '';
        const newName = currentName.split(find).join(replace);

        if (newName !== currentName) {
            const newAttrs = { ...obj.attributes };
            newAttrs[nameField] = newName;
            edits.push({
                file_path: obj.source_file,
                line_number: obj.line_number,
                attributes: newAttrs,
                object_type: obj.object_type,
            });
            renames.push({ oldName: currentName, newName, idx });
        }
    }

    // Reference updates
    if (shouldUpdateRefs && renames.length > 0) {
        const allRenamedIndices = new Set(renames.map(r => r.idx));
        for (const { oldName, newName } of renames) {
            const deps = Explorer.findDependencies(oldName)
                .filter(d => !allRenamedIndices.has(d.object.global_index));

            for (const dep of deps) {
                const editedAttrs = { ...dep.object.attributes };
                let changed = false;
                for (const fieldName of dep.fields) {
                    const currentValue = editedAttrs[fieldName] || '';
                    const updatedValue = Explorer.updateReferenceValue(currentValue, oldName, newName);
                    if (updatedValue !== currentValue) {
                        editedAttrs[fieldName] = updatedValue;
                        changed = true;
                    }
                }
                if (changed) {
                    edits.push({
                        file_path: dep.object.source_file,
                        line_number: dep.object.line_number,
                        attributes: editedAttrs,
                        object_type: dep.object.object_type,
                    });
                }
            }
        }
    }

    if (edits.length === 0) {
        showToast('No matches found', 'warning');
        Explorer.closeDialog();
        return;
    }

    const result = await CandidateApi.bulkEdit(edits, `Bulk rename: ${find} → ${replace}`);
    if (!result.success) {
        if (typeof DebugLogger !== 'undefined') {
            DebugLogger.log('Candidate bulk rename failed:', result.error);
        }
        Explorer.showToast(result.error || 'Bulk rename failed', 'error');
        // [P3-Q] Re-enable button on failure
        if (confirmBtn) {
            confirmBtn.disabled = false;
            confirmBtn.textContent = 'Rename';
        }
        return;
    }

    await Explorer.loadObjects();
    state.healthCheckData = null;
    Explorer.refreshAfterObjectChange();
    Explorer.closeDialog();

    const refCount = edits.length - renames.length;
    const refMsg = refCount > 0 ? ` Updated ${refCount} reference(s).` : '';
    showToast(`Renamed ${renames.length} object(s).${refMsg}`, 'info');
}
```

**Step 8: Add candidate branch to bulk move (context-menu.js and file-operations.js)**

Bulk moves via context menu (`context-menu.js:497`) and drag-drop (`file-operations.js:909,994`) stage into `state.stagedMoves` then call `Explorer.saveStagedChanges()`. In candidate mode, call `CandidateApi.moveObject()` directly.

In **context-menu.js**, where the move is staged (around line 497, in the move-to-file handler), add a candidate branch:

```javascript
// Before: state.stagedMoves.set(objKey, {...})
if (state.candidateActive) {
    const ready = await CandidateApi.ensureSession();
    if (!ready) { return; }

    const result = await CandidateApi.moveObject(
        obj.source_file, obj.line_number,
        targetFile, obj.object_type, obj.attributes
    );
    if (!result.success) {
        if (typeof DebugLogger !== 'undefined') {
            DebugLogger.log('Candidate move failed:', result.error, 'from:', obj.source_file, 'to:', targetFile);
        }
        Explorer.showToast(result.error || 'Move failed', 'error');
        return;
    }
    await Explorer.loadObjects();
    Explorer.refreshAfterObjectChange();
    Explorer.showToast('Moved object', 'success');
    return;
}
// ... existing staging code ...
```

In **file-operations.js**, for `handleExistingObjectReorder()` (line 909) and the bulk drag-drop handler (line 994), add the same pattern — but for multiple objects, collect them into a `CandidateApi.bulkMove()` call:

```javascript
// Bulk drag-drop candidate branch (file-operations.js, around line 994):
if (state.candidateActive && data.type === 'objects' && data.objects?.length > 0) {
    const ready = await CandidateApi.ensureSession();
    if (!ready) { return; }

    const moves = data.objects
        .filter(o => o && o.source_file && o.source_file !== targetFile)
        .map(o => ({
            source_file: o.source_file,
            source_line: o.line_number,
            target_file: targetFile,
            object_type: o.object_type,
            attributes: o.attributes,
        }));

    if (moves.length === 0) { return; }
    const result = await CandidateApi.bulkMove(moves, `Move ${moves.length} object(s)`);
    if (!result.success) {
        if (typeof DebugLogger !== 'undefined') {
            DebugLogger.log('Candidate bulk move failed:', result.error);
        }
        Explorer.showToast(result.error || 'Move failed', 'error');
        return;
    }
    await Explorer.loadObjects();
    afterStagingChange();
    Explorer.showToast(`Moved ${moves.length} object(s)`, 'success');
    return;
}
```

**Step 9: Add candidate branches to context menu operations [P3-C]**

The following context menu operations mutate state and must be candidate-aware. Note: the function is `applyBulkAttribute()` (NOT `executeBulkEditAction()` which does not exist).

**9a. `applyBulkAttribute()` in `context-menu.js` — bulk attribute change from context menu [P3-C]**

```javascript
// [P3-C] At the top of applyBulkAttribute():
if (state.candidateActive) {
    const ready = await CandidateApi.ensureSession();
    if (!ready) { return; }

    const edits = [];
    for (const idx of Explorer.getSelectedIndices()) {
        const obj = state.allObjects.find(o => o.global_index === idx);
        if (!obj) { continue; }
        const newAttrs = { ...obj.attributes };
        newAttrs[attributeName] = attributeValue;
        edits.push({
            file_path: obj.source_file,
            line_number: obj.line_number,
            attributes: newAttrs,
            object_type: obj.object_type,
        });
    }
    if (edits.length === 0) { return; }

    const result = await CandidateApi.bulkEdit(edits, `Bulk set ${attributeName}`);
    if (!result.success) {
        if (typeof DebugLogger !== 'undefined') {
            DebugLogger.log('Candidate bulk edit failed:', result.error);
        }
        Explorer.showToast(result.error || 'Bulk edit failed', 'error');
        return;
    }
    await Explorer.loadObjects();
    Explorer.refreshAfterObjectChange();
    Explorer.showToast(`Set ${attributeName} on ${edits.length} object(s)`, 'success');
    return;
}
// ... existing staging code ...
```

**9b. `applyClone()` in `context-menu.js` — clone operations [P3-C]**

```javascript
// [P3-C] At the top of applyClone():
if (state.candidateActive) {
    const ready = await CandidateApi.ensureSession();
    if (!ready) { return; }

    const result = await CandidateApi.createObject(
        obj.source_file,
        obj.object_type,
        clonedAttrs,
        obj.line_number,
        obj.inline_comments || {}
    );
    if (!result.success) {
        if (typeof DebugLogger !== 'undefined') {
            DebugLogger.log('Candidate clone failed:', result.error);
        }
        Explorer.showToast(result.error || 'Clone failed', 'error');
        return;
    }
    await Explorer.loadObjects();
    Explorer.refreshAfterObjectChange();
    Explorer.showToast('Cloned object', 'success');
    return;
}
// ... existing staging code ...
```

**9c. `addToGroup()` in `context-menu.js` — add objects to hostgroup/servicegroup [P3-C]**

```javascript
// [P3-C] At the top of addToGroup():
if (state.candidateActive) {
    const ready = await CandidateApi.ensureSession();
    if (!ready) { return; }

    const edits = [];
    for (const obj of objectsToAdd) {
        const newAttrs = { ...obj.attributes };
        // Append to members field
        const currentMembers = newAttrs[membersField] || '';
        newAttrs[membersField] = currentMembers
            ? currentMembers + ',' + newMember
            : newMember;
        edits.push({
            file_path: obj.source_file,
            line_number: obj.line_number,
            attributes: newAttrs,
            object_type: obj.object_type,
        });
    }
    if (edits.length === 0) { return; }

    const result = await CandidateApi.bulkEdit(edits, `Add to group`);
    if (!result.success) {
        Explorer.showToast(result.error || 'Failed to add to group', 'error');
        return;
    }
    await Explorer.loadObjects();
    Explorer.refreshAfterObjectChange();
    return;
}
// ... existing staging code ...
```

**9d. `applyRename()` in `context-menu.js` — single rename [P3-C]**

```javascript
// [P3-C] At the top of applyRename():
if (state.candidateActive) {
    const ready = await CandidateApi.ensureSession();
    if (!ready) { return; }

    const newAttrs = { ...obj.attributes };
    newAttrs[nameField] = newName;
    const edits = [{
        file_path: obj.source_file,
        line_number: obj.line_number,
        attributes: newAttrs,
        object_type: obj.object_type,
    }];

    // If updateReferences, find and update dependent objects
    if (shouldUpdateRefs) {
        const deps = Explorer.findDependencies(oldName);
        for (const dep of deps) {
            const depAttrs = { ...dep.object.attributes };
            let changed = false;
            for (const fieldName of dep.fields) {
                const currentValue = depAttrs[fieldName] || '';
                const updatedValue = Explorer.updateReferenceValue(currentValue, oldName, newName);
                if (updatedValue !== currentValue) {
                    depAttrs[fieldName] = updatedValue;
                    changed = true;
                }
            }
            if (changed) {
                edits.push({
                    file_path: dep.object.source_file,
                    line_number: dep.object.line_number,
                    attributes: depAttrs,
                    object_type: dep.object.object_type,
                });
            }
        }
    }

    const result = await CandidateApi.bulkEdit(edits, `Rename: ${oldName} → ${newName}`);
    if (!result.success) {
        Explorer.showToast(result.error || 'Rename failed', 'error');
        return;
    }
    await Explorer.loadObjects();
    Explorer.refreshAfterObjectChange();
    Explorer.showToast('Renamed', 'success');
    return;
}
// ... existing staging code ...
```

**9e. Fix `getOrCreatePendingEdit()` for candidate mode [P3-C]**

In candidate mode, `pendingEdits` is always empty. `getOrCreatePendingEdit()` must return the object's current attributes from `state.allObjects` (which were loaded from the candidate parser) rather than from `state.pendingEdits`:

```javascript
// [P3-C] At the top of getOrCreatePendingEdit(globalIndex):
if (state.candidateActive) {
    // In candidate mode, there are no pendingEdits — return current object attributes
    const obj = state.allObjects.find(o => o.global_index === globalIndex);
    if (!obj) { return null; }
    return {
        attributes: { ...obj.attributes },
        original: { ...obj.attributes },
        source_file: obj.source_file,
        line_number: obj.line_number,
        object_type: obj.object_type,
    };
}
// ... existing staging path ...
```

**Step 10: Add candidate branch to `clearStagedChanges()` [P3-L]**

`clearStagedChanges()` in `data-loading.js` calls `DELETE /api/staging`. In candidate mode, it must call `DELETE /api/candidate`:

```javascript
// [P3-L] At the top of clearStagedChanges():
if (state.candidateActive) {
    const result = await CandidateApi.discard();
    if (result.success) {
        state.candidateActive = false;
        state.candidateDiff = null;
        await Explorer.loadObjects();
        Explorer.refreshAfterObjectChange();
    }
    return result;
}
// ... existing staging path unchanged ...
```

**Step 11: Migrate new object creation flow [P3-G, P3-H]**

The `stageNewObjectChanges()` function in `object-editor.js` creates objects by pushing to `state.stagedCreations` and calling `saveStagedChanges()`. In candidate mode, this must call `CandidateApi.createObject()` instead.

Add candidate branch to `stageNewObjectChanges()`:

```javascript
async function stageNewObjectChanges() {
    // ... collect attrs from form fields (same as existing code) ...

    // [P3-G] Candidate mode: create via API
    if (state.candidateActive) {
        const ready = await CandidateApi.ensureSession();
        if (!ready) { return; }

        const targetFile = state.newObjectTargetFile || state.currentFile;
        // [P3-A] Read attributes from state, not DOM
        const editedAttrs = { ...state.editedObject.attributes };
        const inlineComments = state.editedObject.inline_comments || {};

        const result = await CandidateApi.createObject(
            targetFile,
            state.newObjectType,
            editedAttrs,
            null, // afterLine
            inlineComments
        );
        if (!result.success) {
            Explorer.showToast(result.error || 'Failed to create object', 'error');
            return;
        }
        state.isNewObject = false;
        state.newObjectStagedIndex = null;
        await Explorer.loadObjects();
        Explorer.refreshAfterObjectChange();
        Explorer.handleHostgroupServiceLink();  // [P3-H] Preserve hostgroup service link call
        return;
    }

    // ... existing staging path unchanged ...
}
```

Also update `discardNewObject()` for candidate mode [P3-G]:

```javascript
function discardNewObject() {
    if (!state.isNewObject) { return; }

    // [P3-G] In candidate mode, new object was already created via API — undo it
    if (state.candidateActive) {
        CandidateApi.undo().then(() => {
            state.isNewObject = false;
            state.editedObject = null;
            state.pendingHostgroupServiceLink = null;
            Explorer.loadObjects().then(() => Explorer.refreshAfterObjectChange());
        });
        return;
    }
    // ... existing staging path unchanged ...
}
```

**Step 12: Add revert-to-original for candidate mode [P3-J]**

The existing "Revert" button restores original attributes from `pendingEdits[idx].original`. In candidate mode, `pendingEdits` is empty, so revert must use undo:

```javascript
// [P3-J] At the top of the revert handler (e.g., revertObjectToOriginal()):
if (state.candidateActive) {
    // In candidate mode, "revert" means undo the last operation
    CandidateApi.undo().then(result => {
        if (result.success) {
            Explorer.loadObjects().then(() => {
                Explorer.refreshAfterObjectChange();
                const desc = result.data?.data?.description || result.data?.description || 'last change';
                Explorer.showToast(`Reverted: ${desc}`, 'info');
            });
        } else {
            Explorer.showToast(result.error || 'Nothing to revert', 'info');
        }
    });
    return;
}
// ... existing staging revert path ...
```

**Note:** This is a behavioral difference — staging revert was per-object, candidate undo is per-action. Accept the simpler semantics or document the difference in the UI.

**Step 13: Enumerate and handle ALL `saveStagedChanges()` call sites [P3-N]**

**CRITICAL:** `saveStagedChanges()` is called from 38 locations across the codebase. Every call site must either be guarded with `if (!state.candidateActive)` before calling, or be replaced with the candidate equivalent.

Run this grep to find all call sites:

```bash
grep -rn "saveStagedChanges" static/js/
```

For each call site, determine if it's:
1. **Already covered** by another amendment (P3-C covers context-menu.js ops, Step 11 covers object-editor.js creation, Step 7 covers bulk rename)
2. **Needs a new candidate branch** — add one following the same pattern
3. **Is dead code in candidate mode** — safe to skip with a guard: `if (!state.candidateActive) { Explorer.saveStagedChanges(); }`

The implementer MUST handle every single call site. Do not assume the amendments above cover them all — they only cover the explicitly listed operations.

**Step 14: Handle async dialog callbacks [P3-Q]**

For critical async dialog actions (bulk rename, bulk move, template consolidation), the existing `showDialog()` confirm callback is synchronous. If candidate-mode callbacks are `async`, the dialog closes before API calls complete. Apply this pattern:

```javascript
// [P3-Q] For async dialog confirm callbacks:
// 1. Disable the confirm button and show a spinner
const confirmBtn = document.querySelector('.dialog-confirm-btn');
if (confirmBtn) {
    confirmBtn.disabled = true;
    confirmBtn.textContent = 'Processing...';
}
// 2. Run the async operation
// 3. Re-enable on failure, or close dialog on success
```

This has already been applied to `executeBulkRenameCandidate()` in Step 7. Apply the same pattern to other async dialog callbacks added in this task.

**Step 15: Lint and commit**

```bash
npx eslint static/js/explorer/object-editor.js static/js/explorer/context-menu.js static/js/explorer/file-operations.js static/js/explorer/dialogs.js static/js/base.js
git add static/js/explorer/object-editor.js static/js/explorer/context-menu.js static/js/explorer/file-operations.js static/js/explorer/dialogs.js static/js/base.js
git commit -m "feat: candidate-aware save/delete/create/move/rename/undo in explorer"
```

---

## Task 4: Commit dialog, git page, analysis integration

**Files:**
- Modify: `static/js/commit-dialog.js`
- Modify: `static/js/git.js`
- Modify: `templates/git.html`
- Modify: `static/js/explorer/analysis.js`
- Modify: `static/js/explorer/analysis-suggestions.js` (suggestion apply candidate branches)

**Amendments integrated:** P3-I (apply+commit recovery flow with deferClear)

**Step 1: Add candidate branch to `showGlobalCommitDialog()` (commit-dialog.js:27)**

```javascript
async function showGlobalCommitDialog() {
    const overlay = document.getElementById('globalCommitOverlay');
    const content = document.getElementById('globalCommitContent');

    overlay.classList.add('visible');
    content.innerHTML = '<div class="dialog-loading">Loading changes...</div>';

    // Candidate mode: fetch diff from candidate API
    const candidateStatus = await CandidateApi.status();
    const useCandidate = candidateStatus.success && candidateStatus.data?.active;

    if (useCandidate) {
        const diffResult = await CandidateApi.getDiff();
        if (!diffResult.success) {
            if (typeof DebugLogger !== 'undefined') {
                DebugLogger.log('Candidate diff failed in commit dialog:', diffResult.error);
            }
            content.innerHTML = `<div class="commit-empty commit-error-text">Error: ${escapeHtml(diffResult.error)}</div>`;
            return;
        }
        const diffData = diffResult.data?.data || diffResult.data;
        if (!diffData?.hasChanges) {
            content.innerHTML = '<div class="commit-empty">No pending changes.</div>';
            return;
        }
        baseState.diffData = diffData;
        baseState.candidateMode = true;
        content.innerHTML = buildCandidateCommitDialogHtml(diffData);
        return;
    }

    // ... existing staging commit dialog code unchanged ...
```

**Step 2: Add `buildCandidateCommitDialogHtml()` function**

```javascript
function buildCandidateCommitDialogHtml(diffData) {
    const changedFiles = diffData.changed_files || [];
    const undoCount = diffData.undo_count || 0;
    const isGitConfigured = hasUserIdentity();

    let html = '<div class="commit-summary">';
    html += `<div class="commit-stat">${changedFiles.length} file(s) changed, ${undoCount} edit(s)</div>`;
    html += '</div>';

    // File list with status badges
    html += '<div class="commit-file-list">';
    for (const file of changedFiles) {
        const statusClass = file.status === 'created' ? 'file-added' :
                           file.status === 'deleted' ? 'file-deleted' : 'file-modified';
        html += `<div class="commit-item ${statusClass}">`;
        html += `<div class="commit-item-header" data-path="${escapeHtml(file.relative_path)}">`;
        html += `<span class="file-status-badge">${file.status}</span> `;
        html += escapeHtml(file.relative_path);
        html += '</div>';
        html += '</div>';
    }
    html += '</div>';

    // Unified diff
    if (diffData.unified_diff) {
        html += '<div class="commit-diff-section">';
        html += '<h4>Unified Diff</h4>';
        html += `<pre class="diff-block">${escapeHtml(diffData.unified_diff)}</pre>`;
        html += '</div>';
    }

    // Action buttons
    html += '<div class="commit-actions">';
    if (isGitConfigured) {
        html += '<button class="btn btn-primary" onclick="applyCandidateAndCommit()">Apply + Commit</button>';
    }
    html += '<button class="btn btn-secondary" onclick="applyCandidateOnly()">Apply Only</button>';
    html += '<button class="btn btn-danger" onclick="discardCandidate()">Discard All</button>';
    html += '<button class="btn" onclick="closeGlobalCommitDialog()">Cancel</button>';
    html += '</div>';

    return html;
}
```

**Step 3: Add candidate apply/discard handlers [P3-I]**

The apply+commit flow uses `deferClear: true` so the candidate directory survives if the git commit fails, enabling retry.

```javascript
async function applyCandidateOnly() {
    showGitRunningPanel('Applying changes...');
    const result = await CandidateApi.apply();
    if (!result.success && typeof DebugLogger !== 'undefined') {
        DebugLogger.log('Candidate apply failed:', result.error);
    }
    if (result.success) {
        closeGlobalCommitDialog();
        if (typeof Explorer !== 'undefined') {
            Explorer.state.candidateActive = false;
            Explorer.state.candidateDiff = null;
            await Explorer.loadObjects();
            Explorer.refreshAfterObjectChange();
        }
        showToast('Changes applied to running config', 'success');
        checkPendingChanges();
    } else {
        showToast(result.error || 'Apply failed', 'error');
    }
    closeGitResultOverlay();
}

// [P3-I] Apply+commit with deferClear-based recovery flow
async function applyCandidateAndCommit() {
    showGitRunningPanel('Applying and committing...');

    // [P3-I] Apply with deferClear so candidate survives if commit fails
    const result = await CandidateApi.apply({ deferClear: true });
    if (!result.success) {
        if (typeof DebugLogger !== 'undefined') {
            DebugLogger.log('Candidate apply+commit failed at apply step:', result.error);
        }
        showToast(result.error || 'Apply failed', 'error');
        closeGitResultOverlay();
        return;
    }

    // Now do git commit
    const commitResult = await applyGitCommit();

    if (commitResult && commitResult.success) {
        // [P3-I] Commit succeeded — now safe to clean up candidate
        await CandidateApi.clearAfterCommit();
        if (typeof Explorer !== 'undefined') {
            Explorer.state.candidateActive = false;
            Explorer.state.candidateDiff = null;
        }
    } else {
        // [P3-I] Commit failed — candidate still exists for retry
        showToast(
            'Apply succeeded but commit failed. Your changes are applied but not committed. ' +
            'The candidate session is preserved — you can retry the commit.',
            'warning'
        );
    }
}

async function discardCandidate() {
    const confirmed = await showConfirmDialog({
        title: 'Discard All Changes',
        message: 'Are you sure? All pending edits will be lost.',
        confirmText: 'Discard',
        type: 'danger'
    });
    if (!confirmed) { return; }
    const result = await ApiClient.del('/api/candidate');
    if (!result.success && typeof DebugLogger !== 'undefined') {
        DebugLogger.log('Candidate discard failed:', result.error);
    }
    if (result.success) {
        closeGlobalCommitDialog();
        if (typeof Explorer !== 'undefined') {
            Explorer.state.candidateActive = false;
            Explorer.state.candidateDiff = null;
            await Explorer.loadObjects();
            Explorer.refreshAfterObjectChange();
        }
        showToast('All changes discarded', 'info');
        checkPendingChanges();
    } else {
        showToast(result.error || 'Discard failed', 'error');
    }
}
```

**Step 4: Add to eslint globals**

Add to `projectGlobals` in `eslint.config.mjs`:
```javascript
applyCandidateOnly: 'readonly',
applyCandidateAndCommit: 'readonly',
discardCandidate: 'readonly',
buildCandidateCommitDialogHtml: 'readonly',
```

**Step 5: git.js + git.html — candidate tab**

Add "Candidate" tab (hidden by default). When candidate active, show tab with changed files + unified diff from `CandidateApi.getDiff()`. Click file -> `CandidateApi.getFileDiff(path)`.

**Step 6: Add `?candidate=1` to all analysis API calls (16 calls across 8 files)**

**Pattern for all `ApiClient.get()` calls in explorer modules:**

```javascript
const suffix = Explorer.state.candidateActive ? '?candidate=1' : '';
```

Prepend this line before the API call, then append `suffix` to the URL. For URLs with existing query params, use `&candidate=1` instead.

**Pattern for `fetch()` calls (2 locations):**

Same suffix pattern, but applied to the raw URL string.

---

**File 1: `static/js/explorer/analysis.js`** (3 calls)

**Line 66** — `loadAllSuggestions()`:
```javascript
// Before:
const result = await ApiClient.get('/api/health-check');
// After:
const suffix = state.candidateActive ? '?candidate=1' : '';
const result = await ApiClient.get('/api/health-check' + suffix);
```

**Line 785** — `loadCleanupSuggestions()`:
```javascript
// Before:
const result = await ApiClient.get('/api/health-check');
// After:
const suffix = state.candidateActive ? '?candidate=1' : '';
const result = await ApiClient.get('/api/health-check' + suffix);
```

**Line 1369** — `loadNotificationSuggestions()`:
```javascript
// Before:
const result = await ApiClient.get('/api/health-check');
// After:
const suffix = state.candidateActive ? '?candidate=1' : '';
const result = await ApiClient.get('/api/health-check' + suffix);
```

---

**File 2: `static/js/explorer/analysis-issues.js`** (1 call)

**Line 36** — `loadIssues()`:
```javascript
// Before:
const result = await ApiClient.get('/api/health-check', { silent: true });
// After:
const suffix = Explorer.state.candidateActive ? '?candidate=1' : '';
const result = await ApiClient.get('/api/health-check' + suffix, { silent: true });
```

**Note:** This file is outside the IIFE that has `state` in closure. Use `Explorer.state.candidateActive`.

---

**File 3: `static/js/explorer/analysis-suggestions.js`** (3 calls)

**Line 52** — `loadTemplateIssues()`:
```javascript
// Before:
const result = await ApiClient.get('/api/templates/issues', {silent: true});
// After:
const suffix = Explorer.state.candidateActive ? '?candidate=1' : '';
const result = await ApiClient.get('/api/templates/issues' + suffix, {silent: true});
```

**Line 146** — `loadTemplateConsolidationSuggestions()`:
```javascript
// Before:
const result = await ApiClient.get('/api/health-check');
// After:
const suffix = Explorer.state.candidateActive ? '?candidate=1' : '';
const result = await ApiClient.get('/api/health-check' + suffix);
```

**Line 234** — `loadGroupingSuggestions()`:
```javascript
// Before:
const result = await ApiClient.get('/api/smart-grouping/suggest', { silent: true });
// After:
const suffix = Explorer.state.candidateActive ? '?candidate=1' : '';
const result = await ApiClient.get('/api/smart-grouping/suggest' + suffix, { silent: true });
```

---

**File 4: `static/js/explorer/badge-issues.js`** (3 calls)

**Line 24** — `loadIssuesForBadges()`:
```javascript
// Before:
const result = await ApiClient.get('/api/health-check');
// After:
const suffix = Explorer.state.candidateActive ? '?candidate=1' : '';
const result = await ApiClient.get('/api/health-check' + suffix);
```

**Line 63** — `loadSuggestionsForBadges()` (first call):
```javascript
// Before:
const result = await ApiClient.get('/api/health-check');
// After:
const suffix = Explorer.state.candidateActive ? '?candidate=1' : '';
const result = await ApiClient.get('/api/health-check' + suffix);
```

**Line 70** — `loadSuggestionsForBadges()` (second call, same function):
```javascript
// Before:
const groupingResult = await ApiClient.get('/api/smart-grouping/suggest', { silent: true });
// After:
const groupingResult = await ApiClient.get('/api/smart-grouping/suggest' + suffix, { silent: true });
```

**Note:** Reuse the `suffix` variable computed on line 63 — it's the same function scope.

---

**File 5: `static/js/explorer/object-editor.js`** (1 call)

**Line 1330** — `getInheritanceData()`:
```javascript
// Before:
const result = await ApiClient.get(`/api/templates/inheritance/${encodeURIComponent(stableKey)}`, {silent: true});
// After:
const suffix = state.candidateActive ? '?candidate=1' : '';
const result = await ApiClient.get(`/api/templates/inheritance/${encodeURIComponent(stableKey)}${suffix}`, {silent: true});
```

---

**File 6: `static/js/explorer/relations-loader.js`** (3 calls, 1 uses `fetch()`)

**Line 123** — `loadCenterInheritance()` — **uses `fetch()`, not `ApiClient`**:
```javascript
// Before:
const response = await fetch(`/api/inheritance/${obj.object_type}/${encodeURIComponent(obj.name || obj.display_name)}`);
// After:
const suffix = Explorer.state.candidateActive ? '?candidate=1' : '';
const response = await fetch(`/api/inheritance/${obj.object_type}/${encodeURIComponent(obj.name || obj.display_name)}${suffix}`);
```

**Line 378** — `loadCenterReferences()`:
```javascript
// Before:
const result = await ApiClient.get(`/api/object-references/${obj.global_index}`);
// After:
const suffix = Explorer.state.candidateActive ? '?candidate=1' : '';
const result = await ApiClient.get(`/api/object-references/${obj.global_index}${suffix}`);
```

**Line 654** — `loadCenterMembers()`:
```javascript
// Before:
const result = await ApiClient.get(`/api/object-references/${obj.global_index}`);
// After:
const suffix = Explorer.state.candidateActive ? '?candidate=1' : '';
const result = await ApiClient.get(`/api/object-references/${obj.global_index}${suffix}`);
```

---

**File 7: `static/js/explorer/impact-section.js`** (1 call)

**Line 92** — `loadImpactAndRelationships()`:
```javascript
// Before:
const result = await ApiClient.get(`/api/object-references/${obj.global_index}`);
// After:
const suffix = Explorer.state.candidateActive ? '?candidate=1' : '';
const result = await ApiClient.get(`/api/object-references/${obj.global_index}${suffix}`);
```

---

**File 8: `static/js/dependencies.js`** — STANDALONE PAGE (1 call + init logic)

**This is NOT an explorer module.** It runs on the `/dependencies` page and has no access to `Explorer.state`. It also uses native `fetch()`, not `ApiClient`.

**Sub-step 1:** At the top of the IIFE (or in the page init function), check candidate status:

```javascript
// Near top of dependencies.js init, after variable declarations:
let candidateSuffix = '';

async function checkCandidateStatus() {
    try {
        const resp = await fetch('/api/candidate');
        const data = await resp.json();
        if (data.active) {
            candidateSuffix = '?candidate=1';
        }
    } catch (e) {
        // Ignore — will use running config
    }
}
```

**Sub-step 2:** Call this before the first data load. In the page initialization:

```javascript
// Before the existing loadAllData() call:
await checkCandidateStatus();
```

**Sub-step 3:** Update the fetch call at line 1164:

```javascript
// Before:
const response = await fetch('/api/dependencies');
// After:
const response = await fetch('/api/dependencies' + candidateSuffix);
```

**Sub-step 4:** If there are any type-specific dependency calls elsewhere in the file using `?type=`, use `&candidate=1`:

```javascript
// If existing URL is: /api/dependencies?type=host
// Then: /api/dependencies?type=host&candidate=1
const candidateParam = candidateSuffix ? '&candidate=1' : '';
const response = await fetch(`/api/dependencies?type=${type}${candidateParam}`);
```

---

**Call inventory summary:**

| File | Calls | Endpoints |
|------|-------|-----------|
| `analysis.js` | 3 | `/api/health-check` x3 |
| `analysis-issues.js` | 1 | `/api/health-check` |
| `analysis-suggestions.js` | 3 | `/api/templates/issues`, `/api/health-check`, `/api/smart-grouping/suggest` |
| `badge-issues.js` | 3 | `/api/health-check` x2, `/api/smart-grouping/suggest` |
| `object-editor.js` | 1 | `/api/templates/inheritance/{key}` |
| `relations-loader.js` | 3 | `/api/inheritance/{type}/{name}` (fetch), `/api/object-references/{idx}` x2 |
| `impact-section.js` | 1 | `/api/object-references/{idx}` |
| `dependencies.js` | 1 | `/api/dependencies` (fetch, standalone page) |
| **Total** | **16** | **6 unique endpoints** |

**Step 7: Add candidate branches to suggestion apply buttons (analysis-suggestions.js)**

The analysis-suggestions module has two apply flows that stage locally into `state.stagedCreations` and `state.pendingEdits`. In candidate mode, these must call `CandidateApi` directly.

**7a. Template consolidation apply (analysis-suggestions.js:356)**

In the `showConsolidateDialog()` confirm callback, the code pushes to `state.stagedCreations` (line 358) and sets `state.pendingEdits` (line 381). Add a candidate branch before this code:

```javascript
// Inside the confirm callback, before the "Stage the template creation" comment:
// [P3-Q] For async candidate operation, disable confirm button first
if (Explorer.state.candidateActive) {
    const confirmBtn = document.querySelector('.dialog-confirm-btn');
    if (confirmBtn) {
        confirmBtn.disabled = true;
        confirmBtn.textContent = 'Creating...';
    }

    const ready = await CandidateApi.ensureSession();
    if (!ready) {
        if (confirmBtn) { confirmBtn.disabled = false; confirmBtn.textContent = 'Create'; }
        return;
    }

    // Create the template object directly
    const templateAttrs = { ...suggestion.attributes, name: name, register: '0' };
    const createResult = await CandidateApi.createObject(
        targetFile, suggestion.type, templateAttrs
    );
    if (!createResult.success) {
        if (typeof DebugLogger !== 'undefined') {
            DebugLogger.log('Candidate template create failed:', createResult.error);
        }
        showToast(createResult.error || 'Failed to create template', 'error');
        if (confirmBtn) { confirmBtn.disabled = false; confirmBtn.textContent = 'Create'; }
        return;
    }

    // If updating objects, edit each to add 'use' and remove common attrs
    if (updateObjects) {
        const edits = suggestion.objects.map(obj => {
            const newAttrs = { ...obj.attributes };
            newAttrs.use = name;
            for (const key of Object.keys(suggestion.attributes)) {
                delete newAttrs[key];
            }
            return {
                file_path: obj.source_file,
                line_number: obj.line_number,
                attributes: newAttrs,
                object_type: obj.object_type,
            };
        });
        const editResult = await CandidateApi.bulkEdit(
            edits, `Apply template "${name}" to ${edits.length} objects`
        );
        if (!editResult.success) {
            if (typeof DebugLogger !== 'undefined') {
                DebugLogger.log('Candidate template apply edits failed:', editResult.error);
            }
            showToast(editResult.error || 'Template created but failed to update objects', 'warning');
        }
    }

    Explorer.closeDialog();
    await Explorer.loadObjects();
    Explorer.refreshAfterObjectChange();

    const msg = updateObjects
        ? `Created template "${name}" and updated ${suggestion.count} objects.`
        : `Created template "${name}".`;
    showToast(msg, 'success');

    // Remove suggestion from list
    const suggestionIdx = state.allTemplateSuggestions.indexOf(suggestion);
    if (suggestionIdx > -1) {
        state.allTemplateSuggestions.splice(suggestionIdx, 1);
    }
    Explorer.renderUnifiedSuggestionsList();
    return;
}
// ... existing staging code below unchanged ...
```

**Note:** The confirm callback must become `async` if it isn't already. Check the `Explorer.showDialog(title, html, callback)` pattern — the third argument is the callback. If the existing code doesn't use `async`, add it: `async () => {`.

**7b. Hostgroup creation apply (analysis-suggestions.js:471)**

In `showCreateGroupDialog()`, the confirm callback pushes to `state.stagedCreations` (line 472). Add a candidate branch:

```javascript
// Inside the confirm callback, before the "Stage the creation" comment:
if (Explorer.state.candidateActive) {
    // [P3-Q] Disable button during async operation
    const confirmBtn = document.querySelector('.dialog-confirm-btn');
    if (confirmBtn) {
        confirmBtn.disabled = true;
        confirmBtn.textContent = 'Creating...';
    }

    const ready = await CandidateApi.ensureSession();
    if (!ready) {
        if (confirmBtn) { confirmBtn.disabled = false; confirmBtn.textContent = 'Create'; }
        return;
    }

    const result = await CandidateApi.createObject(targetFile, 'hostgroup', {
        hostgroup_name: name,
        alias: name,
        members: suggestion.members.join(',')
    });
    if (!result.success) {
        if (typeof DebugLogger !== 'undefined') {
            DebugLogger.log('Candidate hostgroup create failed:', result.error);
        }
        showToast(result.error || 'Failed to create hostgroup', 'error');
        if (confirmBtn) { confirmBtn.disabled = false; confirmBtn.textContent = 'Create'; }
        return;
    }

    Explorer.closeDialog();
    await Explorer.loadObjects();
    Explorer.refreshAfterObjectChange();
    showToast(`Created hostgroup "${name}"`, 'success');

    // Remove suggestion from list
    const suggestionIdx = state.allGroupingSuggestions.indexOf(suggestion);
    if (suggestionIdx > -1) {
        state.allGroupingSuggestions.splice(suggestionIdx, 1);
    }
    Explorer.renderUnifiedSuggestionsList();
    return;
}
// ... existing staging code below unchanged ...
```

**Step 8: Lint and commit**

```bash
npx eslint static/js/commit-dialog.js static/js/git.js static/js/explorer/analysis.js static/js/explorer/analysis-issues.js static/js/explorer/analysis-suggestions.js static/js/explorer/badge-issues.js static/js/explorer/object-editor.js static/js/explorer/relations-loader.js static/js/explorer/impact-section.js static/js/dependencies.js
git add static/js/commit-dialog.js static/js/git.js templates/git.html static/js/explorer/analysis.js static/js/explorer/analysis-issues.js static/js/explorer/analysis-suggestions.js static/js/explorer/badge-issues.js static/js/explorer/object-editor.js static/js/explorer/relations-loader.js static/js/explorer/impact-section.js static/js/dependencies.js
git commit -m "feat: candidate commit dialog, git page tab, analysis integration, and suggestion apply migration"
```

---

## Task 5: Update lock manager for candidate system

**Files:**
- Modify: `static/js/lock-manager.js`

**Gap:** `lock-manager.js` polls `GET /api/staging/lock` which won't exist after Phase 4 removal. Update to use candidate status.

**Step 1: Replace `checkLockStatus()`**

```javascript
async function checkLockStatus() {
    // Try candidate status first
    const candidateResult = await ApiClient.get('/api/candidate', { silent: true });
    if (candidateResult.success && candidateResult.data?.active) {
        const sessionData = candidateResult.data.data || {};
        const mySessionId = typeof getSessionId === 'function' ? getSessionId() : '';
        const isOwner = sessionData.session_id === mySessionId;

        const wasLocked = baseState.isEditingLocked;
        baseState.isEditingLocked = !isOwner;
        baseState.lockOwner = sessionData.session_id;
        baseState.lockUserName = sessionData.user_name;
        baseState.lockUserEmail = sessionData.user_email;
        window.isEditingLocked = baseState.isEditingLocked;

        updateLockBannerUI();

        if (wasLocked !== baseState.isEditingLocked) {
            if (typeof Explorer !== 'undefined' && typeof Explorer.renderCenterAttributes === 'function') {
                Explorer.renderCenterAttributes();
            }
        }
        return { locked: !isOwner, isOwner, owner: sessionData.session_id,
                 userName: sessionData.user_name, userEmail: sessionData.user_email };
    }

    // No candidate session — no lock
    const wasLocked = baseState.isEditingLocked;
    baseState.isEditingLocked = false;
    baseState.lockOwner = null;
    baseState.lockUserName = null;
    baseState.lockUserEmail = null;
    window.isEditingLocked = false;
    updateLockBannerUI();

    if (wasLocked) {
        if (typeof Explorer !== 'undefined' && typeof Explorer.renderCenterAttributes === 'function') {
            Explorer.renderCenterAttributes();
        }
    }
    return { locked: false, isOwner: true };
}
```

**Step 2: Update `breakLock()` to use candidate discard with force**

```javascript
async function breakLock() {
    const confirmed = await showConfirmDialog({
        title: 'Break Lock',
        message: 'Are you sure? This will discard the other user\'s pending changes.',
        confirmText: 'Break Lock',
        cancelText: 'Cancel',
        type: 'danger'
    });
    if (!confirmed) { return; }

    // Discard candidate session with force (bypasses session check)
    const result = await ApiClient.del('/api/candidate?force=1');
    if (result.success) {
        baseState.isEditingLocked = false;
        baseState.lockOwner = null;
        window.isEditingLocked = false;
        updateLockBannerUI();
        showToast('Lock broken - changes discarded', 'success');
        if (typeof onLockCleared === 'function') { onLockCleared(); }
    } else {
        showToast(result.error || 'Failed to break lock', 'error');
    }
}
```

**Note:** This requires Phase 2's `DELETE /api/candidate` route to accept `?force=1` query param to skip `can_modify()` check (already included in Phase 2 plan via amendment A1).

**Step 3: Lint and commit**

```bash
npx eslint static/js/lock-manager.js
git add static/js/lock-manager.js
git commit -m "feat: candidate-aware lock manager"
```

---

## Task 6: Full lint verification

**Step 1: Python linting**

```bash
ruff check candidate_manager.py routes/candidate.py routes/helpers.py tests/test_candidate_manager.py tests/test_candidate_routes.py
ruff format --check candidate_manager.py routes/candidate.py routes/helpers.py tests/test_candidate_manager.py tests/test_candidate_routes.py
```

**Step 2: JavaScript linting**

```bash
npm run lint:js
```

Fix any errors and re-run.

**Step 3: Full test suite**

```bash
python3 -m pytest tests/ -v
```

**Step 4: Commit lint fixes if any**

```bash
git add -A
git commit -m "style: lint fixes for candidate config implementation"
```

---

## Task 7: Playwright smoke test

Start the server and verify core candidate workflows via Playwright MCP.

**Step 1: Start server**

```bash
python3 app.py &
```

Wait for server to be ready.

**Step 2: Navigate to explorer**

```
browser_navigate: http://localhost:8080/explorer
browser_snapshot (to file)
```

Verify: Page loads, left pane shows objects, no JS errors in console.

**Step 3: Edit a host — verify auto-init**

1. Click a host in the left tree
2. Take snapshot, find the alias field
3. Change alias value
4. Click Save
5. Take snapshot

Verify:
- No "Start Editing" button was needed (auto-init)
- Left tree updates to show the change
- Center pane reflects the edit
- **[P3-B]** Editor stays in edit mode after save (not reset to read mode)
- `browser_console_messages` shows no errors

**Step 4: Undo the edit**

1. Click Undo (Ctrl+Z or undo button)
2. Take snapshot

Verify:
- Alias reverts to original value
- All panes update

**Step 5: Check console for errors**

```
browser_console_messages(level: "error")
```

Verify: No JS errors throughout the test.

**Step 6: Stop server**

```bash
kill %1
```

**Step 7: Report**

Document any issues found. If smoke test passes, Phase 3 is complete.

---

## Phase Gate: Verification

Before considering Phase 3 complete, ALL of these must pass:

**Step 1: Full Python test suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all pass

**Step 2: Python lint**

```bash
ruff check candidate_manager.py routes/candidate.py routes/helpers.py app.py
ruff format --check candidate_manager.py routes/candidate.py routes/helpers.py app.py
```

Expected: 0 errors

**Step 3: JavaScript lint**

```bash
npm run lint:js
```

Expected: 0 errors

**Step 4: Playwright smoke test passed**

Confirmed: app loads, edit works (stays in edit mode per [P3-B]), undo works, no JS console errors.

**Step 5: Old staging still works**

```bash
python3 -m pytest tests/test_staging_integration.py -v
```

Expected: all pass (old code still present, still functional)

**Step 6: `saveStagedChanges()` audit [P3-N]**

Confirmed: all 38 `saveStagedChanges()` call sites have been handled (guarded, replaced, or confirmed dead code in candidate mode).

**Step 7: Report**

Report: X tests passed, 0 lint errors (Python + JS), Playwright smoke passed, saveStagedChanges audit complete. Phase 3 complete. Ready for Phase 4 (Removal + E2E).
