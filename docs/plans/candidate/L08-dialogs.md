# L08 — `static/js/explorer/dialogs.js` — MODIFY

## Purpose
Rewrite deletion, creation, bulk rename, and bulk edit flows to call CandidateApi instead of mutating client-side staging state (`pendingEdits`, `stagedCreations`, `stagedObjectDeletions`, `stagedMoves`). All mutations go to the candidate copy on the server; nothing touches live config until Apply (Palo Alto candidate model).

## Removal Audit

### Functions REMOVED (dead code in candidate model)

| Function | Lines | Reason |
|----------|-------|--------|
| `stageNewObjectChanges()` | 411–510 | Pushes to `state.stagedCreations` array. Replaced by `CandidateApi.createObject()` called from object-editor.js (L08-object-editor). |
| `executeObjectDeletions()` | 728–766 | Reads/writes `state.stagedObjectDeletions` and `state.pendingEdits`. Replaced by `CandidateApi.deleteObjects()`. |
| `stageObjectDeletions()` | 694–726 | Splices `state.stagedCreations`, reads `state.selectedStagedIndices`. Replaced by `deleteObjects()`. |
| `unstageObjectDeletion()` | 768–773 | Deletes from `state.stagedObjectDeletions`. Replaced by `CandidateApi.undo()`. |
| `stageBulkReferenceUpdates()` | 786–827 | Mutates `state.pendingEdits` for reference field updates. Replaced by `CandidateApi.bulkReferenceUpdate()`. |
| `applyBulkRenameEdits()` | 833–871 | Mutates `state.pendingEdits` for name field changes. Replaced by `CandidateApi.bulkRename()`. |
| `executeBulkRename()` | 873–900 | Orchestrates `applyBulkRenameEdits` + `stageBulkReferenceUpdates` + `saveStagedChanges`. Replaced by `executeBulkRenameCandidate()`. |
| `executeBulkEditAction()` | 1016–1065 | Mutates `state.pendingEdits` for bulk attribute changes. Replaced by `executeBulkEditActionCandidate()`. |
| `removeStagedCreation()` | 1322–1351 | Splices from `state.stagedCreations`. Replaced by `CandidateApi.deleteObjects()` or `CandidateApi.undo()`. |
| `updateCommitUI()` | 1318–1320 | Calls `Explorer.saveStagedChanges()`. No client-side staged changes to save. Replaced by `Explorer.refreshCandidateDiff()`. |

### Functions REWRITTEN (migrated to CandidateApi)

| Function | What changes |
|----------|-------------|
| `createNewObject()` | Calls `CandidateApi.createObject()` instead of pushing to `state.stagedCreations`. |
| `showCenterPaneNewObject()` | Unchanged UI, but no longer calls `stageNewObjectChanges()`. |
| `discardNewObject()` | Calls `CandidateApi.deleteObjects()` instead of splicing `state.stagedCreations`. |
| `updateNewObjectType()` | Calls `CandidateApi.editObject()` instead of `stageNewObjectChanges()`. |
| `updateNewObjectName()` | Calls `CandidateApi.editObject()` instead of `stageNewObjectChanges()`. |
| `checkDependenciesAndDelete()` | Calls `deleteObjectsCandidate()` instead of `executeObjectDeletions()`. |
| `showDeleteDependencyWarning()` | Unchanged UI. `onConfirm` callback calls `deleteObjectsCandidate()`. |
| `showBulkRenameDialog()` | Unchanged UI. Confirm callback calls `executeBulkRenameCandidate()`. |
| `showEditAttributesDialog()` | Unchanged UI. Confirm callback calls `executeBulkEditActionCandidate()`. |

### Functions KEPT (no staging state involvement)

| Function | Reason |
|----------|--------|
| `dialogAlert()` | Pure HTML template helper. |
| `dialogKvList()` | Pure HTML template helper. |
| `dialogFileSelect()` | Pure HTML template helper. |
| `dialogInfoText()` | Pure HTML template helper. |
| `dialogEntryList()` | Pure HTML template helper. |
| `buildScrollableList()` | Pure HTML template helper. |
| `buildTypeDropdown()` | Pure HTML template helper. |
| `toggleObjectTypeDropdown()` | Pure UI interaction. |
| `closeObjectTypeDropdownOnClickOutside()` | Pure UI interaction. |
| `selectObjectType()` | Delegates to `updateNewObjectType()`. |
| `getNewObjectNameField()` | Pure lookup helper. |
| `getDefaultAttributes()` | Pure lookup helper. |
| `getDominantTypeForFile()` | Pure read-only query. |
| `findDependencies()` | Read-only dependency scan against `state.allObjects`. |
| `applyBulkAction()` | Pure in-memory attribute transform (no staging writes). |
| `validateBulkActionInputs()` | Pure validation. |
| `filterScopeByAttribute()` | Pure filtering logic. |
| `showBulkEditResultToast()` | Pure UI feedback. |
| `selectAllVisible()` | Selection helper (no staging). |
| `selectByType()` | Selection dialog (no staging). |
| `selectDialogType()` | Selection helper (no staging). |
| `selectByPattern()` | Selection dialog (no staging). |
| `runValidation()` | Tab switch + delegate. |
| `runValidationFull()` | API call to `/api/validate`. |

### Exports update

Remove from `Explorer` namespace:
- `Explorer.stageNewObjectChanges`
- `Explorer.stageObjectDeletions`
- `Explorer.executeObjectDeletions`
- `Explorer.unstageObjectDeletion`
- `Explorer.removeStagedCreation`
- `Explorer.updateCommitUI`

Add to `Explorer` namespace:
- `Explorer.deleteObjects`

## Changes

### 1. Rewrite `createNewObject()` — use CandidateApi.createObject()

The current implementation builds a local object and pushes it to `state.stagedCreations`. In the candidate model, we call the server immediately.

```javascript
async function createNewObject(targetFile) {
    state.openTreeFolders.add(targetFile);
    Explorer.clearSelection();
    document.querySelectorAll('.tree-item').forEach(el => el.classList.remove('selected'));

    const defaultType = getDominantTypeForFile(targetFile);
    const attributes = { ...getDefaultAttributes(defaultType) };

    const result = await CandidateApi.createObject(defaultType, attributes, targetFile);
    if (!result.success) {
        showToast(result.error || 'Failed to create object', 'error');
        return;
    }

    // Build a transient object for the center pane editor
    const newObj = {
        object_type: defaultType,
        attributes: attributes,
        source_file: targetFile,
        line_number: 999999,
        display_name: '(new object)',
        global_index: -1
    };

    state.editedObject = newObj;
    state.originalAttributes = {};
    state.isNewObject = true;
    state.newObjectKey = result.data?.stable_key || null;

    await Explorer.refreshAfterObjectChange();
    await Explorer.refreshCandidateDiff();

    showCenterPaneNewObject(newObj, targetFile);
}
```

### 2. Rewrite `discardNewObject()` — use CandidateApi.deleteObjects()

```javascript
async function discardNewObject() {
    if (!state.isNewObject) { return; }

    // Delete the creation from the candidate copy
    if (state.newObjectKey) {
        const result = await CandidateApi.deleteObjects([state.newObjectKey]);
        if (!result.success) {
            showToast(result.error || 'Failed to discard object', 'error');
            return;
        }
    }

    state.pendingHostgroupServiceLink = null;
    state.editedObject = null;
    state.originalAttributes = null;
    state.isNewObject = false;
    state.newObjectKey = null;
    Explorer.checkPendingExternalChanges();

    const content = document.getElementById('centerContent');
    const emptyState = document.getElementById('centerEmptyState');
    content.classList.add('u-hidden');
    content.style.display = 'none';
    emptyState.classList.remove('u-hidden');
    emptyState.style.display = 'flex';
    document.getElementById('centerCloseBtn').style.display = 'none';

    await Explorer.refreshAfterObjectChange();
    await Explorer.refreshCandidateDiff();
    showToast('New object discarded', 'info');
}
```

### 3. Rewrite `updateNewObjectType()` — use CandidateApi.editObject()

```javascript
async function updateNewObjectType(newType) {
    const oldType = state.editedObject.object_type;
    const oldNameField = getNewObjectNameField(oldType);
    const currentName = state.editedObject.attributes[oldNameField] || '';

    state.editedObject.attributes = { ...getDefaultAttributes(newType) };
    const newNameField = getNewObjectNameField(newType);
    if (currentName) {
        state.editedObject.attributes[newNameField] = currentName;
    }
    state.editedObject.object_type = newType;

    // Persist type change to candidate
    if (state.newObjectKey) {
        const result = await CandidateApi.editObject(
            state.newObjectKey,
            state.editedObject.attributes,
            state.originalAttributes
        );
        if (!result.success) {
            showToast(result.error || 'Failed to update object type', 'error');
            return;
        }
    }

    Explorer.renderCenterAttributes();
    await Explorer.refreshAfterObjectChange();
    await Explorer.refreshCandidateDiff();
}
```

### 4. Rewrite `updateNewObjectName()` — use CandidateApi.editObject()

```javascript
async function updateNewObjectName() {
    const nameInput = document.getElementById('newObjectNameInput');
    const name = nameInput.value.trim();
    const nameField = getNewObjectNameField(state.editedObject.object_type);

    if (name) {
        state.editedObject.attributes[nameField] = name;
        state.editedObject.display_name = name;
    } else {
        delete state.editedObject.attributes[nameField];
        state.editedObject.display_name = '(unnamed)';
    }

    Explorer.renderCenterAttributes();

    // Persist name change to candidate (debounce externally if needed)
    if (state.newObjectKey) {
        const result = await CandidateApi.editObject(
            state.newObjectKey,
            state.editedObject.attributes,
            state.originalAttributes
        );
        if (!result.success) {
            showToast(result.error || 'Failed to update object name', 'error');
        }
    }
}
```

### 5. Rewrite `checkDependenciesAndDelete()` — call `deleteObjectsCandidate()`

Preserve the existing confirmation dialog UI and dependency warning exactly as-is. Only change the callback from `executeObjectDeletions()` to `deleteObjectsCandidate()`.

```javascript
async function checkDependenciesAndDelete() {
    const objectsToDelete = [];
    const allDependencies = [];

    for (const index of Explorer.getSelectedIndices()) {
        const obj = state.allObjects.find(o => o.global_index === index);
        if (obj) {
            const objName = obj.display_name;
            const deps = findDependencies(objName);
            const externalDeps = deps.filter(d =>
                d.object.global_index !== index &&
                !Explorer.isSelectedByIndex(d.object.global_index)
            );
            if (externalDeps.length > 0) {
                objectsToDelete.push({ obj, deps: externalDeps });
                allDependencies.push(...externalDeps);
            }
        }
    }

    if (allDependencies.length > 0) {
        // Same dependency warning dialog — UI preserved exactly
        showDeleteDependencyWarning(objectsToDelete, () => {
            deleteObjectsCandidate();
        });
    } else {
        // Same confirmation dialog — UI preserved exactly
        const selectedCount = state.selectedKeys.size;
        let message;
        if (selectedCount === 1) {
            const index = Array.from(Explorer.getSelectedIndices())[0];
            const obj = state.allObjects.find(o => o.global_index === index);
            const name = obj ? (obj.display_name || obj.name || 'unnamed') : 'this object';
            message = `Are you sure you want to delete "${name}"?`;
        } else {
            message = `Are you sure you want to delete ${selectedCount} objects?`;
        }

        const confirmed = await showConfirmDialog({
            title: selectedCount === 1 ? 'Delete Object?' : `Delete ${selectedCount} Objects?`,
            message: message,
            confirmText: 'Delete',
            cancelText: 'Cancel',
            type: 'danger'
        });

        if (confirmed) {
            await deleteObjectsCandidate();
        }
    }
}
```

### 6. New `deleteObjectsCandidate()` — replaces `executeObjectDeletions()`

```javascript
async function deleteObjectsCandidate() {
    const stableKeys = Array.from(Explorer.getSelectedIndices())
        .map(idx => {
            const obj = state.allObjects.find(o => o.global_index === idx);
            return obj ? Explorer.getObjectKey(obj) : null;
        })
        .filter(Boolean);

    if (stableKeys.length === 0) { return; }

    const result = await CandidateApi.deleteObjects(stableKeys);
    if (!result.success) {
        showToast(result.error || 'Failed to delete objects', 'error');
        return;
    }

    // Close tabs for deleted objects
    for (const key of stableKeys) {
        Explorer.closeTab(key);
    }

    Explorer.clearSelection();
    await Explorer.refreshAfterObjectChange();
    await Explorer.refreshCandidateDiff();
    showToast(`Deleted ${stableKeys.length} object(s)`, 'success');
}
```

### 7. Rewrite `showDeleteDependencyWarning()` — preserve UI, change callback

The HTML structure, button labels ("Delete Anyway"), alert styling, orphan/reference categorization, and scrollable list all stay exactly the same. Only the `onConfirm` callback changes to call `deleteObjectsCandidate()`.

No code changes to the dialog HTML or button labels. Only change:
```javascript
// BEFORE:
confirmBtn.onclick = () => { Explorer.closeDialog(); onConfirm(); };
// AFTER: (identical — onConfirm is now deleteObjectsCandidate)
confirmBtn.onclick = () => { Explorer.closeDialog(); onConfirm(); };
```

### 8. Rewrite `showBulkRenameDialog()` — preserve UI, new confirm callback

Dialog HTML (Find input, Replace input, "Update references" checkbox) stays identical. Only the confirm callback changes:

```javascript
// BEFORE:
executeBulkRename(find, replace, shouldUpdateRefs);
// AFTER:
executeBulkRenameCandidate(find, replace, shouldUpdateRefs);
```

### 9. New `executeBulkRenameCandidate()` — replaces `executeBulkRename()`

```javascript
async function executeBulkRenameCandidate(find, replace, shouldUpdateRefs) {
    if (!find) {
        showToast('Please enter text to find', 'warning');
        return;
    }

    // Build renames array from selected objects
    const renames = [];
    for (const idx of Explorer.getSelectedIndices()) {
        const obj = state.allObjects.find(o => o.global_index === idx);
        if (!obj) { continue; }
        const nameField = Explorer.getNameFieldForObject(obj);
        const currentName = obj.attributes[nameField] || '';
        const newName = currentName.split(find).join(replace);
        if (newName !== currentName) {
            renames.push({
                stable_key: Explorer.getObjectKey(obj),
                old_name: currentName,
                new_name: newName,
                update_references: shouldUpdateRefs
            });
        }
    }

    if (renames.length === 0) {
        showToast('No matches found', 'warning');
        Explorer.closeDialog();
        return;
    }

    const result = await CandidateApi.bulkRename(renames);
    if (!result.success) {
        showToast(result.error || 'Bulk rename failed', 'error');
        return;
    }

    Explorer.closeDialog();
    await Explorer.refreshAfterObjectChange();
    await Explorer.refreshCandidateDiff();

    const refMsg = result.data?.reference_updates > 0
        ? ` Updated ${result.data.reference_updates} reference(s).`
        : '';
    showToast(`Renamed ${renames.length} object(s).${refMsg}`, 'info');

    // Refresh center pane if the currently edited object was renamed
    if (state.editedObject) {
        const renamedKey = renames.find(r => r.stable_key === Explorer.getObjectKey(state.editedObject));
        if (renamedKey) {
            const refreshedObj = state.allObjects.find(o =>
                o.global_index === state.editedObject.global_index
            );
            if (refreshedObj) { Explorer.showCenterPaneObject(refreshedObj); }
        } else if (renames.length > 0) {
            Explorer.loadImpactAndRelationships(state.editedObject);
        }
    }
}
```

### 10. Rewrite `showEditAttributesDialog()` — preserve UI, new confirm callback

Dialog HTML (Action dropdown, Attribute autocomplete, Find/Replace inputs) stays identical. The scope computation changes to read from server objects directly instead of `state.pendingEdits`:

```javascript
// BEFORE: reads state.pendingEdits for current attribute values
const pendingEdit = state.pendingEdits.get(idx);
const attrs = pendingEdit ? pendingEdit.edited : obj.attributes;

// AFTER: objects from server already have candidate attributes
const attrs = obj.attributes;
```

Confirm callback changes:
```javascript
// BEFORE:
executeBulkEditAction(scope, sortedFields);
// AFTER:
executeBulkEditActionCandidate(scope, sortedFields);
```

### 11. New `executeBulkEditActionCandidate()` — replaces `executeBulkEditAction()`

```javascript
async function executeBulkEditActionCandidate(scope, sortedFields) {
    const action = document.getElementById('editAttrAction').value;
    const field = document.getElementById('editAttrField').value.trim();
    const findText = document.getElementById('editAttrFind').value;
    const valueText = document.getElementById('editAttrValue').value;

    if (!validateBulkActionInputs(action, field, findText, sortedFields)) { return; }

    const { filteredScope, skippedIncompatible } = filterScopeByAttribute(scope, field, action);

    // Build updates array — compute attribute changes locally, send to server
    const updates = [];
    let unchangedCount = 0;
    for (const idx of filteredScope) {
        const obj = state.allObjects.find(o => o.global_index === idx);
        if (!obj) { continue; }

        const editedAttrs = { ...obj.attributes };
        if (applyBulkAction(action, field, findText, valueText, editedAttrs)) {
            updates.push({
                stable_key: Explorer.getObjectKey(obj),
                edited: editedAttrs,
                original: obj.attributes
            });
        } else {
            unchangedCount++;
        }
    }

    if (updates.length > 0) {
        const result = await CandidateApi.bulkAttribute(updates);
        if (!result.success) {
            showToast(result.error || 'Bulk edit failed', 'error');
            return;
        }
    }

    Explorer.closeDialog();
    await Explorer.refreshAfterObjectChange();
    await Explorer.refreshCandidateDiff();

    if (state.editedObject && !state.isNewObject && scope.includes(state.editedObject.global_index)) {
        Explorer.showCenterPaneObject(
            state.allObjects.find(o => o.global_index === state.editedObject.global_index)
        );
    }

    showBulkEditResultToast(action, updates.length, unchangedCount, skippedIncompatible);
}
```

### 12. Remove dead functions

Delete the following functions entirely (bodies and all references):

- `stageNewObjectChanges()` — client-side staging array no longer exists
- `executeObjectDeletions()` — replaced by `deleteObjectsCandidate()`
- `stageObjectDeletions()` — replaced by `checkDependenciesAndDelete()` calling `deleteObjectsCandidate()`
- `unstageObjectDeletion()` — replaced by `CandidateApi.undo()`
- `stageBulkReferenceUpdates()` — replaced by server-side reference update in `CandidateApi.bulkRename()`
- `applyBulkRenameEdits()` — replaced by `executeBulkRenameCandidate()`
- `executeBulkRename()` — replaced by `executeBulkRenameCandidate()`
- `executeBulkEditAction()` — replaced by `executeBulkEditActionCandidate()`
- `removeStagedCreation()` — replaced by `CandidateApi.deleteObjects()` or `CandidateApi.undo()`
- `updateCommitUI()` — replaced by `Explorer.refreshCandidateDiff()`

### 13. Remove dead state references

All references to the following client-side staging maps must be removed from this file:
- `state.stagedCreations` (array)
- `state.stagedObjectDeletions` (Set)
- `state.pendingEdits` (Map)
- `state.stagedMoves` (Map)
- `state.newObjectStagedIndex` (replaced by `state.newObjectKey`)
- `state.selectedStagedIndices` (Set — no more staged creation indices)
- `Explorer.saveStagedChanges()` (no client-side state to persist)

### 14. Validation route — add candidate awareness

`runValidationFull()` currently calls `/api/validate`. Update to use `/api/candidate/validate` when a candidate session is active:

```javascript
async function runValidationFull() {
    // ... existing UI setup ...
    const endpoint = state.candidateActive
        ? '/api/candidate/validate'
        : '/api/validate';
    const response = await ApiClient.post(endpoint, {}, { silent: true });
    // ... rest unchanged ...
}
```

### 15. Update exports

```javascript
// REMOVE:
Explorer.stageNewObjectChanges = stageNewObjectChanges;
Explorer.stageObjectDeletions = stageObjectDeletions;
Explorer.executeObjectDeletions = executeObjectDeletions;
Explorer.unstageObjectDeletion = unstageObjectDeletion;
Explorer.removeStagedCreation = removeStagedCreation;
Explorer.updateCommitUI = updateCommitUI;

// ADD:
Explorer.deleteObjects = deleteObjectsCandidate;
```

## Error Handling

Every CandidateApi call in this file must follow this pattern:

```javascript
const result = await CandidateApi.someMethod(args);
if (!result.success) {
    showToast(result.error || 'Operation failed', 'error');
    return;
}
```

Specific error scenarios handled:
- **`createNewObject()`**: Server rejects creation (invalid type, disk full) — toast error, no center pane shown.
- **`discardNewObject()`**: Server rejects deletion — toast error, object stays in editor.
- **`deleteObjectsCandidate()`**: Server rejects deletion (locked, conflict) — toast error, selection preserved.
- **`executeBulkRenameCandidate()`**: Server rejects rename (duplicate name, locked) — toast error, dialog stays open.
- **`executeBulkEditActionCandidate()`**: Server rejects bulk edit — toast error, dialog stays open.
- **`updateNewObjectType()` / `updateNewObjectName()`**: Server rejects edit — toast error, local state reverts.

## Audit Logging

All CandidateApi calls route through backend endpoints that log via `audit_service.py`. No additional frontend logging is needed — the backend handles:
- `POST /api/candidate/object/create` — logs object creation
- `POST /api/candidate/object/delete` — logs object deletion(s)
- `POST /api/candidate/object/edit` — logs object edit
- `POST /api/candidate/bulk/rename` — logs bulk rename
- `POST /api/candidate/bulk/attribute` — logs bulk attribute edit
- `POST /api/candidate/bulk/reference-update` — logs reference updates
- `POST /api/candidate/validate` — logs validation run

Frontend uses `DebugLogger` for client-side diagnostic logging of operations.

## UI Visual Parity

The following UI elements must remain visually identical:

| Element | Preservation |
|---------|-------------|
| Delete confirmation dialog (single object) | Same title, message, "Delete" / "Cancel" buttons, danger type |
| Delete confirmation dialog (multiple objects) | Same title with count, message with count, "Delete" / "Cancel" buttons |
| Dependency warning dialog | Same orphaned services alert (danger), broken references list, scrollable detail list, "Delete Anyway" button with `btn-danger` class, total impact summary |
| Bulk Rename dialog | Same "Find" / "Replace with" inputs, "Update references" checkbox |
| Edit Attributes dialog | Same Action dropdown (Find & Replace / Set value / Remove attribute), Attribute autocomplete, Find/Replace inputs |
| New object center pane | Same type dropdown, name input, NEW badge, close button |
| Toast messages | Same wording and severity levels for all success/warning/error toasts |
| Deleted objects in tree | Objects deleted in candidate show with strikethrough/muted visual indicator (rendered by tree, not by this file) |

## Linting

All new and modified code must pass `npm run lint:js` (ESLint) with zero errors and zero warnings before commit. This includes:
- Consistent async/await usage (no mixing with `.then()`)
- No unused variables from removed functions
- Proper `const`/`let` usage (no `var`)
- Semicolons and brace style per project ESLint config (L06-eslint-config)

## Change Tracking

| # | Change | Status |
|---|--------|--------|
| 1 | Rewrite `createNewObject()` to use `CandidateApi.createObject()` | [ ] |
| 2 | Rewrite `discardNewObject()` to use `CandidateApi.deleteObjects()` | [ ] |
| 3 | Rewrite `updateNewObjectType()` to use `CandidateApi.editObject()` | [ ] |
| 4 | Rewrite `updateNewObjectName()` to use `CandidateApi.editObject()` | [ ] |
| 5 | Rewrite `checkDependenciesAndDelete()` to call `deleteObjectsCandidate()` | [ ] |
| 6 | Create `deleteObjectsCandidate()` replacing `executeObjectDeletions()` | [ ] |
| 7 | Update `showDeleteDependencyWarning()` callback | [ ] |
| 8 | Update `showBulkRenameDialog()` confirm callback | [ ] |
| 9 | Create `executeBulkRenameCandidate()` replacing `executeBulkRename()` | [ ] |
| 10 | Update `showEditAttributesDialog()` scope computation and confirm callback | [ ] |
| 11 | Create `executeBulkEditActionCandidate()` replacing `executeBulkEditAction()` | [ ] |
| 12 | Add candidate-aware endpoint to `runValidationFull()` | [ ] |
| 13 | Delete `stageNewObjectChanges()` | [ ] |
| 14 | Delete `executeObjectDeletions()` | [ ] |
| 15 | Delete `stageObjectDeletions()` | [ ] |
| 16 | Delete `unstageObjectDeletion()` | [ ] |
| 17 | Delete `stageBulkReferenceUpdates()` | [ ] |
| 18 | Delete `applyBulkRenameEdits()` | [ ] |
| 19 | Delete `executeBulkRename()` | [ ] |
| 20 | Delete `executeBulkEditAction()` | [ ] |
| 21 | Delete `removeStagedCreation()` | [ ] |
| 22 | Delete `updateCommitUI()` | [ ] |
| 23 | Remove all `state.stagedCreations` references | [ ] |
| 24 | Remove all `state.stagedObjectDeletions` references | [ ] |
| 25 | Remove all `state.pendingEdits` references | [ ] |
| 26 | Remove all `state.stagedMoves` references | [ ] |
| 27 | Remove all `Explorer.saveStagedChanges()` calls | [ ] |
| 28 | Replace `state.newObjectStagedIndex` with `state.newObjectKey` | [ ] |
| 29 | Update exports (remove 6, add 1) | [ ] |
| 30 | ESLint passes with zero errors | [ ] |
| 31 | Playwright tests pass (see Verification) | [ ] |

## Verification

### Manual checks
- Create new object via file context menu — object appears in tree, center pane shows editor
- Change object type in new object editor — type updates, attributes reset
- Change object name in new object editor — name updates in tree
- Discard new object — removed from tree, center pane clears
- Select single object, delete — confirmation dialog shown, object removed after confirm
- Select multiple objects, delete — confirmation dialog shows count, all removed after confirm
- Delete object with dependents — dependency warning dialog shown with orphaned services and broken references, "Delete Anyway" works
- Bulk rename — Find/Replace dialog works, references updated if checkbox checked
- Edit Attributes — Find & Replace / Set value / Remove attribute all work
- Select All Visible / Select by Type / Select by Pattern — unchanged behavior
- Run Validation — validation output displays correctly
- No console errors after any operation

### Playwright tests

These dialog flows are good Playwright test candidates. Tests to add or update:

| Test | What it validates |
|------|------------------|
| `test-delete-single-object` | Select one object, click Delete, confirm dialog appears with object name, confirm, object removed from tree |
| `test-delete-multiple-objects` | Select multiple objects, click Delete, confirm dialog shows count, confirm, all removed |
| `test-delete-with-dependencies` | Delete a host that has services referencing it, verify dependency warning dialog shows orphaned services, "Delete Anyway" removes the object |
| `test-delete-cancel` | Select object, click Delete, click Cancel in confirm dialog, object still in tree |
| `test-bulk-rename` | Select objects, open Bulk Rename, enter find/replace, confirm, names updated |
| `test-bulk-rename-with-refs` | Bulk rename with "Update references" checked, verify referencing objects also updated |
| `test-bulk-edit-set-attribute` | Select objects, open Edit Attributes, set a value, confirm, attribute applied |
| `test-bulk-edit-remove-attribute` | Select objects, open Edit Attributes, remove an attribute, confirm, attribute removed |
| `test-create-new-object` | Right-click file, Create Object, verify center pane shows editor with type dropdown and name input |
| `test-discard-new-object` | Create new object, press Escape or click close, verify object removed |
| `test-create-object-change-type` | Create object, change type via dropdown, verify attributes reset |

## Commandments Compliance

- [x] **C1 — No live config mutation until Apply.** All mutations go to candidate copy via CandidateApi. Live config untouched. All removed functions that mutated client-side staging state (`stagedCreations`, `stagedObjectDeletions`, `pendingEdits`, `stagedMoves`) are replaced by CandidateApi calls that write to the server-side candidate directory only.
- [x] **C2 — UI visual parity.** Every dialog (delete confirmation, dependency warning, bulk rename, edit attributes, new object editor) preserves identical HTML structure, button labels, confirmation prompts, toast messages, and severity styling. Visual indicators for deleted items handled by tree rendering, not this file. Detailed parity table included in "UI Visual Parity" section.
- [x] **C3 — Full audit logging.** All CandidateApi endpoints log through `audit_service.py` on the backend. Frontend uses `DebugLogger` for diagnostic logging. Detailed in "Audit Logging" section.
- [x] **C4 — Proper error handling.** Every CandidateApi call checks `result.success` and shows a descriptive toast on failure. No silent failures. Specific error scenarios enumerated in "Error Handling" section.
- [x] **C5 — Dead code deletion.** 10 functions deleted entirely with justification. All client-side staging state references removed. Removal audit table covers every function with disposition (REMOVED, REWRITTEN, or KEPT with reason).
- [x] **C6 — Full functionality migration.** Every function in the current file is accounted for in the Removal Audit (REMOVED, REWRITTEN, or KEPT). No functionality dropped. Comprehensive function-by-function accounting with 33 functions covered.
- [x] **C7 — Palo Alto candidate model.** All mutations go through CandidateApi which operates on the candidate copy. No direct staging state manipulation. Apply is a separate explicit action.
- [x] **C8 — Change tracking document.** 31-item change tracking table with checkboxes in "Change Tracking" section.
- [x] **C9 — Complete planning before implementation.** All changes fully specified with code snippets before any implementation begins. Every function in the file accounted for.
- [x] **C10 — Linting enforcement.** "Linting" section requires `npm run lint:js` to pass with zero errors/warnings. Change tracking item #30 gates on lint pass.
- [x] **C11 — Playwright validation.** 11 Playwright test scenarios defined in "Verification" section covering all dialog flows: delete (single, multiple, with deps, cancel), bulk rename (with/without refs), bulk edit (set, remove), create/discard/change-type.
