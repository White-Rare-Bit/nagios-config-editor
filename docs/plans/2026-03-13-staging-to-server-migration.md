# Staging-to-Server Migration Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate the last 3 bulk operations (`executeObjectDeletions`, `executeBulkRename`, `executeBulkEditAction`) and 1 suggestion action (`handleHostgroupServiceLink`) from local staging (`state.pendingEdits`, `state.stagedObjectDeletions`) to immediate server-side API calls, then remove the dead state.

**Architecture:** These functions are remnants of the pre-shadow-copy architecture where edits were staged locally and committed in a batch. Every other mutation in the app now calls the API immediately. We migrate these using `/api/objects/delete-multiple` (deletions) and `/api/batch-mutations` (updates), then remove the dead `state.pendingEdits`, `state.stagedObjectDeletions`, and `state.stagedMoves` state objects.

**Tech Stack:** ES module JavaScript frontend, Flask/Python backend (endpoints already exist)

---

### Task 1: Migrate `executeObjectDeletions()` to server-side deletion

**Files:**
- Modify: `static/js/explorer/dialogs.js` (lines 734-770)

**Step 1: Rewrite `executeObjectDeletions`**

Replace the current function (lines 734-770) with:

```javascript
export async function executeObjectDeletions(stagedCreationDeletedCount = 0) {
    // Collect stable keys for deletion via API
    const stableKeys = [];
    for (const key of state.selectedKeys) {
        const obj = findObjectByKey(key);
        if (!obj) {continue;}
        stableKeys.push(getObjectKey(obj));
    }

    // Close tabs for deleted objects
    for (const key of state.selectedKeys) {
        closeTab(key);
    }

    // Clear selection
    clearSelection();

    if (stableKeys.length > 0) {
        const result = await ApiClient.post('/api/objects/delete-multiple', {
            stable_keys: stableKeys,
        });

        if (!result.success) {
            showToast(result.data?.error || result.error || 'Failed to delete objects', 'error');
            afterFrontendMutation();
            return;
        }

        const deletedCount = result.data?.deleted || 0;
        afterFrontendMutation();

        if (stagedCreationDeletedCount > 0 && deletedCount > 0) {
            showToast(`Deleted ${deletedCount} object(s), removed ${stagedCreationDeletedCount} staged creation(s)`, 'success');
        } else if (deletedCount > 0) {
            showToast(`Deleted ${deletedCount} object(s)`, 'success');
        }
    } else if (stagedCreationDeletedCount > 0) {
        afterFrontendMutation();
        showToast(`Removed ${stagedCreationDeletedCount} staged creation(s)`, 'success');
    }
}
```

**Step 2: Update confirmation dialog text in `checkDependenciesAndDelete`**

In `checkDependenciesAndDelete` (line 589), change:

```javascript
            message = `Are you sure you want to stage "${name}" for deletion?`;
```
to:
```javascript
            message = `Are you sure you want to delete "${name}"?`;
```

And (line 591), change:
```javascript
            message = `Are you sure you want to stage ${selectedCount} objects for deletion?`;
```
to:
```javascript
            message = `Are you sure you want to delete ${selectedCount} objects?`;
```

**Step 3: Run tests**

Run: `python3 -m pytest tests/ -v`
Expected: All tests PASS (frontend-only change)

**Step 4: Commit**

```bash
git add static/js/explorer/dialogs.js
git commit -m "refactor: executeObjectDeletions calls server API instead of local staging"
```

---

### Task 2: Remove dead deletion staging code

**Files:**
- Modify: `static/js/explorer/dialogs.js` (lines 772-776)
- Modify: `static/js/explorer/analysis.js` (lines 21-24)

**Step 1: Remove `unstageObjectDeletion` from dialogs.js**

Delete lines 772-776:

```javascript
export function unstageObjectDeletion(key) {
    state.stagedObjectDeletions.delete(key);
    // Centralized refresh ensures all UI components stay in sync
    afterFrontendMutation();
}
```

**Step 2: Remove dead `filterActiveSuggestions` from analysis.js**

Delete lines 21-24 (the function is defined but never called):

```javascript
// A-02: Filter out suggestions for objects marked for deletion (used 11+ times)
function filterActiveSuggestions(suggestions) {
    return suggestions.filter(s => s.object && !state.stagedObjectDeletions.has(getObjectKey(s.object)));
}
```

**Step 3: Verify no remaining references to `unstageObjectDeletion`**

Search codebase for `unstageObjectDeletion` — should find zero hits after removal.

**Step 4: Commit**

```bash
git add static/js/explorer/dialogs.js static/js/explorer/analysis.js
git commit -m "chore: remove dead unstageObjectDeletion and filterActiveSuggestions"
```

---

### Task 3: Migrate `executeBulkRename()` to use `/api/batch-mutations`

**Files:**
- Modify: `static/js/explorer/dialogs.js` (lines 789-904)

**Step 1: Replace `stageBulkReferenceUpdates` with `computeBulkReferenceUpdates`**

Replace lines 789-831 with a function that returns operations instead of staging edits:

```javascript
/**
 * Compute reference update operations for a batch of renames, excluding
 * renamed objects from each other's reference scans.
 * @param {Array<{oldName: string, newName: string, key: string}>} renames
 * @returns {Array} batch mutation operations
 */
function computeBulkReferenceUpdates(renames) {
    const allRenamedKeys = new Set(renames.map(r => r.key));
    const refUpdates = new Map();

    for (const { oldName, newName } of renames) {
        const deps = findDependencies(oldName)
            .filter(d => !allRenamedKeys.has(getObjectKey(d.object)));

        for (const dep of deps) {
            const depKey = getObjectKey(dep.object);
            const existing = refUpdates.get(depKey);
            const editedAttrs = existing ? {...existing.attributes} : {...dep.object.attributes};
            let changed = false;

            for (const fieldName of dep.fields) {
                const currentValue = editedAttrs[fieldName] || '';
                const updatedValue = updateReferenceValue(currentValue, oldName, newName);
                if (updatedValue !== currentValue) {
                    editedAttrs[fieldName] = updatedValue;
                    changed = true;
                }
            }

            if (changed) {
                refUpdates.set(depKey, {
                    action: 'update',
                    stable_key: depKey,
                    attributes: editedAttrs
                });
            }
        }
    }

    return Array.from(refUpdates.values());
}
```

**Step 2: Replace `applyBulkRenameEdits` + `executeBulkRename` with a single async function**

Replace lines 833-904 with:

```javascript
async function executeBulkRename(find, replace, shouldUpdateRefs) {
    const renames = [];
    const operations = [];
    let centerPaneNeedsRefresh = false;

    for (const key of state.selectedKeys) {
        const obj = findObjectByKey(key);
        if (!obj) {continue;}

        const objKey = getObjectKey(obj);
        const nameField = getNameFieldForObject(obj);
        const currentName = obj.attributes[nameField] || '';
        const newName = currentName.split(find).join(replace);

        if (newName !== currentName) {
            const editedAttrs = {...obj.attributes};
            editedAttrs[nameField] = newName;
            operations.push({
                action: 'update',
                stable_key: objKey,
                attributes: editedAttrs
            });
            renames.push({ oldName: currentName, newName, key: objKey });

            if (state.editedObject && getObjectKey(state.editedObject) === objKey) {
                centerPaneNeedsRefresh = true;
            }
        }
    }

    let totalRefUpdates = 0;
    if (shouldUpdateRefs && renames.length > 0) {
        const refOps = computeBulkReferenceUpdates(renames);
        totalRefUpdates = refOps.length;
        operations.push(...refOps);
    }

    if (operations.length === 0) {
        closeDialog();
        showToast('No matches found', 'warning');
        return;
    }

    const result = await ApiClient.post('/api/batch-mutations', {
        description: `bulk rename ${renames.length} objects`,
        operations
    });

    closeDialog();

    if (!result.success) {
        showToast(result.error || 'Failed to apply renames', 'error');
        afterFrontendMutation();
        return;
    }

    state.healthCheckData = null;
    afterFrontendMutation();

    if (centerPaneNeedsRefresh && state.editedObject) {
        const editedKey = getObjectKey(state.editedObject);
        const obj = findObjectByKey(editedKey);
        if (obj) {showCenterPaneObject(obj);}
    } else if (state.editedObject && renames.length > 0) {
        loadImpactAndRelationships(state.editedObject);
    }

    const refMsg = totalRefUpdates > 0 ? ` Updated ${totalRefUpdates} reference${totalRefUpdates !== 1 ? 's' : ''}.` : '';
    showToast(`Renamed ${renames.length} object(s).${refMsg}`, 'success');
}
```

**Step 3: Commit**

```bash
git add static/js/explorer/dialogs.js
git commit -m "refactor: executeBulkRename uses batch endpoint for single undo"
```

---

### Task 4: Migrate `executeBulkEditAction()` to use `/api/batch-mutations`

**Files:**
- Modify: `static/js/explorer/dialogs.js` (lines 1020-1072)

**Step 1: Rewrite `executeBulkEditAction`**

Replace the function with:

```javascript
async function executeBulkEditAction(scope, sortedFields) {
    const action = document.getElementById('editAttrAction').value;
    const field = document.getElementById('editAttrField').value.trim();
    const findText = document.getElementById('editAttrFind').value;
    const valueText = document.getElementById('editAttrValue').value;

    if (!validateBulkActionInputs(action, field, findText, sortedFields)) {return;}

    const { filteredScope, skippedIncompatible } = filterScopeByAttribute(scope, field, action);

    const operations = [];
    let unchangedCount = 0;
    for (const key of filteredScope) {
        const obj = findObjectByKey(key);
        if (!obj) {continue;}

        const objKey = getObjectKey(obj);
        const editedAttrs = {...obj.attributes};

        if (applyBulkAction(action, field, findText, valueText, editedAttrs)) {
            operations.push({
                action: 'update',
                stable_key: objKey,
                attributes: editedAttrs
            });
        } else {
            unchangedCount++;
        }
    }

    if (operations.length > 0) {
        const ACTION_DESCS = { findreplace: 'find/replace', set: 'set attribute', remove: 'remove attribute' };
        const result = await ApiClient.post('/api/batch-mutations', {
            description: `bulk ${ACTION_DESCS[action] || action} on ${operations.length} objects`,
            operations
        });
        if (!result.success) {
            showToast(result.error || 'Failed to apply edits', 'error');
            closeDialog();
            afterFrontendMutation();
            return;
        }
    }

    state.healthCheckData = null;
    afterFrontendMutation();
    closeDialog();

    if (state.editedObject && !state.isNewObject) {
        const editedKey = getObjectKey(state.editedObject);
        if (scope.includes(editedKey)) {
            const obj = findObjectByKey(editedKey);
            if (obj) {showCenterPaneObject(obj);}
        }
    }

    showBulkEditResultToast(action, operations.length, unchangedCount, skippedIncompatible);
}
```

**Step 2: Update `showBulkEditResultToast` — remove "Commit to apply" text**

In `showBulkEditResultToast` (around line 1007), remove ` Commit to apply.`:

Change:
```javascript
        msg += ' Commit to apply.';
```
to:
```javascript
        // (no trailing message — changes are applied immediately)
```

**Step 3: Update `showEditAttributesDialog` — remove `state.pendingEdits` read**

In `showEditAttributesDialog` (line 1087-1088), change:

```javascript
        const pendingEdit = state.pendingEdits.get(objKey);
        const attrs = pendingEdit ? pendingEdit.edited : obj.attributes;
```
to:
```javascript
        const attrs = obj.attributes;
```

**Step 4: Commit**

```bash
git add static/js/explorer/dialogs.js
git commit -m "refactor: executeBulkEditAction uses batch endpoint for single undo"
```

---

### Task 5: Migrate `handleHostgroupServiceLink()` to use API

**Files:**
- Modify: `static/js/explorer/analysis.js` (lines 1310-1326)

**Step 1: Replace local staging with API call**

Replace lines 1310-1328 (the block starting at `// Stage edit to update the service`) with:

```javascript
    // Update the service via API — remove host_name, add hostgroup_name
    const serviceObj = state.allObjects.find(o => getObjectKey(o) === serviceKey);
    if (serviceObj) {
        const newAttrs = { ...serviceObj.attributes };
        delete newAttrs.host_name;
        newAttrs.hostgroup_name = hostgroupName;

        const result = await ApiClient.post('/api/objects/update', {
            stable_key: serviceKey,
            attributes: newAttrs
        }, { silent: true });

        if (result.success) {
            showToast(`Service "${serviceObj.display_name}" will now use hostgroup "${hostgroupName}"`, 'success');
        }
    }
```

Also make the function async — change `export function handleHostgroupServiceLink()` to `export async function handleHostgroupServiceLink()`.

**Step 2: Add `afterFrontendMutation` call** after the API call succeeds, before the suggestion cleanup:

```javascript
        if (result.success) {
            showToast(`Service "${serviceObj.display_name}" will now use hostgroup "${hostgroupName}"`, 'success');
            await afterFrontendMutation();
        }
```

**Step 3: Commit**

```bash
git add static/js/explorer/analysis.js
git commit -m "refactor: handleHostgroupServiceLink calls API instead of local staging"
```

---

### Task 6: Remove dead state properties

**Files:**
- Modify: `static/js/explorer/dialogs.js` — remove any remaining `state.pendingEdits` / `state.stagedObjectDeletions` / `state.stagedMoves` references
- Modify: `static/js/explorer/analysis.js` — remove any remaining references
- Modify: `static/js/explorer/object-editor.js` (line 265) — remove stale comment about `pendingEdits`

**Step 1: Search and verify**

Grep for `pendingEdits`, `stagedObjectDeletions`, and `stagedMoves` across all JS files. After Tasks 1-5, the only remaining references should be:
- `object-editor.js:265` — a comment (remove it)
- `context-menu.js:4` — a doc comment (update it)

If any functional references remain, they are bugs — flag them.

**Step 2: Clean up the comment in `context-menu.js` line 4**

Change:
```javascript
 * No local pendingEdits/stagedMoves/stagedCreations — the shadow copy IS the edited state.
```
to:
```javascript
 * All mutations go to the server via API. The shadow copy IS the edited state.
```

**Step 3: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add static/js/explorer/dialogs.js static/js/explorer/analysis.js static/js/explorer/object-editor.js static/js/explorer/context-menu.js
git commit -m "chore: remove dead pendingEdits/stagedObjectDeletions/stagedMoves state"
```

---

### Task 7: Final verification

**Step 1:** Run full test suite: `python3 -m pytest tests/ -v`

**Step 2:** Manual smoke test each migrated operation:
- Multi-select objects → right-click → Delete → single Ctrl+Z undoes all
- Multi-select same-type → right-click → Bulk rename → single Ctrl+Z undoes all renames + references
- Multi-select → right-click → Edit attributes → set/remove/find-replace → single Ctrl+Z
- Create hostgroup from suggestion → verify service gets updated immediately
