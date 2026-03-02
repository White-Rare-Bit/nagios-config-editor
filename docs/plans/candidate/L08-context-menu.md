# L08 — `static/js/explorer/context-menu.js` — MODIFY

## Purpose
Rewrite move/clone/rename/bulk-attr context menu actions to call CandidateApi. Remove `getOrCreatePendingEdit()`.

## Removal Audit
- `getOrCreatePendingEdit(obj)` → REMOVED. No client-side pendingEdits. Edits go to server.
- `applyMove()` that sets `state.stagedMoves` → REPLACED by `CandidateApi.moveObjects()`.
- `applyRename()` that mutates pendingEdits → REPLACED by `CandidateApi.editObject()`.
- `applyClone()` that pushes to `state.stagedCreations` → REPLACED by `CandidateApi.cloneObjects()`.
- `applyBulkAttribute()` that mutates pendingEdits → REPLACED by `CandidateApi.bulkAttribute()`.
- `addToGroup()` that calls `/api/smart-grouping/create` or `/api/smart-grouping/add-to-group` → These routes move to candidate in L04. Updated to use candidate-aware endpoints.
- `stageReferenceUpdates()` that mutates pendingEdits → REPLACED by `CandidateApi.bulkReferenceUpdate()`.
- `handleDrop()` drag-drop handler → Updated to call CandidateApi.moveObjects().

All removed functions have CandidateApi equivalents that perform the same operations server-side.

## Changes

**1. Remove `getOrCreatePendingEdit(obj)`** — This helper created or fetched a pendingEdits entry for mutation. No longer needed.

**2. Rewrite `applyMove()`**:
```javascript
async function applyMove(stableKeys, targetFile, insertPosition) {
    const moves = stableKeys.map(key => ({
        stable_key: key,
        target_file: targetFile,
        insert_position: insertPosition
    }));
    const result = await CandidateApi.moveObjects(moves);
    if (result.success) {
        await Explorer.refreshAfterObjectChange();
        await Explorer.refreshCandidateDiff();
    }
    return result;
}
```

**3. Rewrite `applyRename()`**:
```javascript
async function applyRename(obj, newName) {
    const nameField = Explorer.constants.nameFields[obj.object_type] || 'name';
    const edited = { ...obj.attributes, [nameField]: newName };
    const stableKey = Explorer.getObjectKey(obj);
    const result = await CandidateApi.editObject(stableKey, edited, obj.attributes);
    if (result.success) {
        await Explorer.refreshAfterObjectChange();
        await Explorer.refreshCandidateDiff();
    }
    return result;
}
```

**4. Rewrite `applyClone()`**:
```javascript
async function applyClone(objects, targetFile) {
    const clones = objects.map(obj => ({
        stable_key: Explorer.getObjectKey(obj),
        target_file: targetFile
    }));
    const result = await CandidateApi.cloneObjects(clones);
    if (result.success) {
        await Explorer.refreshAfterObjectChange();
        await Explorer.refreshCandidateDiff();
    }
    return result;
}
```

**5. Rewrite `applyBulkAttribute()`**:
```javascript
async function applyBulkAttribute(updates) {
    const result = await CandidateApi.bulkAttribute(updates);
    if (result.success) {
        await Explorer.refreshAfterObjectChange();
        await Explorer.refreshCandidateDiff();
    }
    return result;
}
```

**6. Rewrite `handleDrop()`** — Drag-drop calls CandidateApi.moveObjects() instead of staging.

**7. Rewrite `stageReferenceUpdates()`** → `applyReferenceUpdates()`:
```javascript
async function applyReferenceUpdates(updates) {
    const result = await CandidateApi.bulkReferenceUpdate(updates);
    if (result.success) {
        await Explorer.refreshAfterObjectChange();
        await Explorer.refreshCandidateDiff();
    }
    return result;
}
```

## Change Tracking

### Functions Removed
- [ ] `getOrCreatePendingEdit(obj)` — client-side pendingEdits helper
- [ ] `stageReferenceUpdates()` — client-side reference mutation

### Functions Rewritten
- [ ] `applyMove()` — call `CandidateApi.moveObjects()` instead of setting `state.stagedMoves`
- [ ] `applyRename()` — call `CandidateApi.editObject()` instead of mutating pendingEdits
- [ ] `applyClone()` / `applyBulkClone()` — call `CandidateApi.cloneObjects()` instead of pushing to `state.stagedCreations`
- [ ] `applyBulkAttribute()` — call `CandidateApi.bulkAttribute()` instead of mutating pendingEdits
- [ ] `handleDrop()` — call `CandidateApi.moveObjects()` instead of staging
- [ ] `stageReferenceUpdates()` → renamed to `applyReferenceUpdates()`, calls `CandidateApi.bulkReferenceUpdate()`

### Functions Updated
- [ ] `addToGroup()` — updated to use candidate-aware smart-grouping endpoints (migrated in L04)
- [ ] `handleDragStart()` — no staging state changes needed, verify compatibility

### Functions Unchanged (no staging interaction)
- [ ] `handleContextMenu()` — display only, no changes needed
- [ ] `hideContextMenu()` — display only
- [ ] `contextAction()` — dispatcher, routes to rewritten functions
- [ ] `showPreview()` / `closePreview()` — display only
- [ ] `showDialog()` / `closeDialog()` — display only
- [ ] `showBulkAction()` — display only
- [ ] `showAddToGroupDialog()` — display only
- [ ] `viewInGraph()` — navigation only
- [ ] `toggleNewFileInput()` — UI toggle only
- [ ] `buildCloneCreation()` — pure helper, verify still used by rewritten `applyClone()`
- [ ] `updateReferenceValue()` — pure string helper, no staging interaction
- [ ] `handleDragEnd()` / `handleDragOver()` — drag UI only

### Exports Updated
- [ ] Remove `stageReferenceUpdates` export, add `applyReferenceUpdates`
- [ ] Verify all other exports still valid

### Error Handling
- [ ] All `CandidateApi.*` calls check `result.success` before refreshing
- [ ] Failed operations surface error via toast or dialog (no silent failures)

### Audit Logging
- [ ] Server-side CandidateApi endpoints handle audit logging; no client-side audit calls needed

## Verification

### Manual Testing
- Right-click → Move → objects move to new file
- Right-click → Clone → cloned objects appear
- Right-click → Rename → name changes
- Drag-drop objects between files → works
- Bulk attribute change → all selected objects updated
- Add to group → group membership updated
- Reference updates cascade on rename
- No console errors

### Linting
- [ ] `npx eslint static/js/explorer/context-menu.js` passes
- [ ] No ESLint warnings or errors

### Playwright Tests
- [ ] Context menu move operation
- [ ] Context menu clone operation
- [ ] Context menu rename operation
- [ ] Drag-drop between files
- [ ] Bulk attribute change

---

## Commandments Compliance

- [x] **C1 — No live config mutation until Apply.** All operations go through CandidateApi which edits the candidate directory only. Live config is untouched until Apply.
- [x] **C2 — UI visual parity.** Context menus, dialogs, and drag-drop behavior remain visually identical. Only the backend calls change.
- [x] **C3 — Full audit logging.** CandidateApi server endpoints log through audit_service.py and application logging. No client-side audit gaps.
- [x] **C4 — Proper error handling.** Every CandidateApi call checks `result.success` and surfaces errors. No silent failures.
- [x] **C5 — Dead code deletion.** `getOrCreatePendingEdit()` and `stageReferenceUpdates()` are deleted, not left behind.
- [x] **C6 — Full functionality migration.** Every removed function has a CandidateApi equivalent listed in the Removal Audit. Move, clone, rename, bulk attribute, reference updates, drag-drop, and add-to-group are all migrated.
- [x] **C7 — Palo Alto candidate model.** All edits target the candidate config directory via CandidateApi. No direct live config mutation.
- [x] **C8 — Change tracking document.** Change Tracking section added above with tickable checklist for all functions.
- [x] **C9 — Complete planning before implementation.** This plan fully specifies all changes before any code is written.
- [x] **C10 — Linting enforcement.** Verification section includes ESLint command for this file.
- [x] **C11 — Playwright validation.** Playwright test cases listed for context menu move, clone, rename, drag-drop, and bulk attribute operations.
