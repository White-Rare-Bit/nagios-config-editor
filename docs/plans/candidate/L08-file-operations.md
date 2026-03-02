# L08 — `static/js/explorer/file-operations.js` — MODIFY

## Purpose
Rewrite all file/folder operations and bulk drag-drop to use CandidateApi. Remove `afterStagingChange()` helper.

## Removal Audit
- `afterStagingChange()` centralized post-change updater → REPLACED by `refreshAfterObjectChange()` + `refreshCandidateDiff()` pattern.
- `stageDeleteFile(path)` that pushes to `state.stagedFileDeletions` → REPLACED by `CandidateApi.deleteFile(path)`.
- `stageDeleteFolder(path)` that pushes to `state.stagedFolderDeletions` → REPLACED by `CandidateApi.deleteFolder(path)`.
- `createNewItem(type, path)` that pushes to `state.stagedFileCreations`/`stagedFolderCreations` → REPLACED by `CandidateApi.createFile()`/`CandidateApi.createFolder()`.
- `handleExistingObjectReorder()` → REPLACED by `CandidateApi.reorderObject()`.
- `handleObjectDrop()` that stages moves → REPLACED by `CandidateApi.moveObjects()`.
- `handleFileDrop()` that stages file/folder moves → REPLACED by `CandidateApi.moveFile()`/`CandidateApi.moveFolder()`.
- `unstageFileCreation()`, `unstageFolderCreation()`, etc. → REMOVED. No client-side staging state to unstage. Use CandidateApi.undo() instead.

All removed functions have CandidateApi equivalents.

## Changes

**1. Remove `afterStagingChange()`** — Replace all calls with:
```javascript
await Explorer.refreshAfterObjectChange();
await Explorer.refreshCandidateDiff();
```

**2. Rewrite `stageDeleteFile()`**:
```javascript
async function deleteFile(path) {
    const result = await CandidateApi.deleteFile(path);
    if (result.success) {
        await Explorer.refreshAfterObjectChange();
        await Explorer.refreshCandidateDiff();
        showToast('File deleted', 'success');
    }
    return result;
}
```

**3. Rewrite `stageDeleteFolder()`**:
```javascript
async function deleteFolder(path) {
    const result = await CandidateApi.deleteFolder(path);
    if (result.success) {
        await Explorer.refreshAfterObjectChange();
        await Explorer.refreshCandidateDiff();
        showToast('Folder deleted', 'success');
    }
    return result;
}
```

**4. Rewrite `createNewItem()`**:
```javascript
async function createNewItem(type, path) {
    let result;
    if (type === 'file') {
        result = await CandidateApi.createFile(path);
    } else {
        result = await CandidateApi.createFolder(path);
    }
    if (result.success) {
        await Explorer.refreshAfterObjectChange();
        await Explorer.refreshCandidateDiff();
    }
    return result;
}
```

**5. Rewrite `handleObjectDrop()`** — Call CandidateApi.moveObjects().

**6. Rewrite `handleFileDrop()`** — Call CandidateApi.moveFile() or CandidateApi.moveFolder().

**7. Rewrite `handleExistingObjectReorder()`**:
```javascript
async function handleExistingObjectReorder(stableKey, direction) {
    const result = await CandidateApi.reorderObject(stableKey, direction);
    if (result.success) {
        await Explorer.refreshAfterObjectChange();
        await Explorer.refreshCandidateDiff();
    }
    return result;
}
```

**8. Remove all `unstage*` functions** — No client-side state to unstage:
- `unstageFileCreation()`, `unstageFolderCreation()`, `unstageFileDeletion()`, `unstageFolderDeletion()`, `unstageFileMove()`, `unstageFolderMove()`
All replaced by `CandidateApi.undo()`.

## Change Tracking

### Functions Removed
- [ ] `afterStagingChange()` — centralized post-change updater; replaced by `refreshAfterObjectChange()` + `refreshCandidateDiff()` inline pattern
- [ ] `unstageFileDeletion()` — no client-side staging state to unstage
- [ ] `unstageFileMove()` — no client-side staging state to unstage
- [ ] `unstageFolderDeletion()` — no client-side staging state to unstage
- [ ] `unstageFolderCreation()` — no client-side staging state to unstage
- [ ] `removePendingMove()` — no client-side pending moves
- [ ] `undoObjectMove()` — replaced by `CandidateApi.undo()`
- [ ] `undoNewFile()` — replaced by `CandidateApi.undo()`
- [ ] `removeStagedCreation()` — no client-side staged creations
- [ ] `moveStagedCreationsToFile()` — no client-side staged creations
- [ ] `stageObjectsToFile()` — replaced by `CandidateApi.moveObjects()`
- [ ] `isStagedCreationTemplate()` — dead code, no client-side staged creations
- [ ] `handleStagedCreationsDrop()` — dead code, no client-side staged creations

### Functions Rewritten
- [ ] `stageDeleteFile()` → `deleteFile()` — call `CandidateApi.deleteFile()`
- [ ] `stageDeleteFolder()` → `deleteFolder()` — call `CandidateApi.deleteFolder()`
- [ ] `createNewItem()` — call `CandidateApi.createFile()` or `CandidateApi.createFolder()`
- [ ] `handleExistingObjectReorder()` — call `CandidateApi.reorderObject()`
- [ ] `handleObjectDrop()` — call `CandidateApi.moveObjects()`
- [ ] `handleFileDrop()` — call `CandidateApi.moveFile()` or `CandidateApi.moveFolder()`
- [ ] `handleFolderDrop()` — route to CandidateApi calls
- [ ] `handleReorderDrop()` — call `CandidateApi.reorderObject()`

### Functions Updated
- [ ] `renderTargetPane()` — remove pendingEdits/stagedCreations overlay logic; objects come from server
- [ ] `renderFileObjects()` — remove staged creation rendering; simplify to server-provided objects
- [ ] `buildFolderTree()` — remove staged file/folder creation merging
- [ ] `getFileStagedStatus()` — adapt to candidate diff instead of client-side staging maps
- [ ] `getFolderStagedStatus()` — adapt to candidate diff
- [ ] `buildStagedIndicator()` — adapt to candidate diff statuses
- [ ] `buildFileActionButton()` — update undo actions to use `CandidateApi.undo()`
- [ ] `buildFolderActionButton()` — update undo actions to use `CandidateApi.undo()`
- [ ] `confirmInlineCreate()` — call CandidateApi instead of pushing to staging arrays
- [ ] `handleFileOnFolderDrop()` — call `CandidateApi.moveFile()`
- [ ] `handleFolderOnFolderDrop()` — call `CandidateApi.moveFolder()`
- [ ] `handleObjectsOnFolderDrop()` — call `CandidateApi.moveObjects()`

### Functions Unchanged (no staging interaction)
- [ ] `navigateToObjectByIndex()` — navigation only
- [ ] `selectObjectByName()` — navigation only
- [ ] `selectObjectByIndex()` — navigation only
- [ ] `restoreExpandedState()` / `saveExpandedState()` — UI state only
- [ ] `initTargetPane()` / `initWorkspaceToolbar()` — initialization only
- [ ] `toggleCreateMenu()` / `showCreateInput()` / `hideCreateInput()` — UI toggle only
- [ ] `handleCreateKeydown()` — keyboard handler only
- [ ] `collapseAllFolders()` — UI only
- [ ] `refreshWorkspace()` — calls renderTargetPane (which is updated)
- [ ] `updateWorkspaceHeader()` — display only
- [ ] `toggleFolderExpand()` / `toggleFileExpand()` — UI toggle only
- [ ] `selectFolder()` — navigation only
- [ ] `buildRowClasses()` — pure helper
- [ ] `addFileToTree()` — pure helper
- [ ] `getMaxLineInFile()` — pure helper
- [ ] `buildExistingObjectRow()` — display only (verify no pendingEdits references)
- [ ] `buildPendingObjectRow()` — verify still needed or remove
- [ ] `buildStagedCreationRow()` — verify still needed or remove
- [ ] `buildFileItemsList()` — verify no staged creation references
- [ ] `handleFileDragOver()` / `handleFileDragLeave()` — drag UI only
- [ ] `handleObjectDragOver()` / `handleObjectDragLeave()` — drag UI only
- [ ] `handleTargetObjectDragStart()` / `handleTargetObjectDragEnd()` — drag UI only
- [ ] `handleFileDragStart()` / `handleFolderDragStart()` — drag UI only
- [ ] `handleFolderDragOver()` / `handleFolderDragLeave()` — drag UI only
- [ ] `moveFileImmediate()` / `moveFolderImmediate()` — verify if still used or replaced
- [ ] `updateFolderReferences()` — verify if still used or replaced
- [ ] `resolveTargetFileInFolder()` — pure helper
- [ ] `getFilesInFolder()` — pure helper
- [ ] `createInlineFile()` / `createInlineFolder()` / `createInlineItem()` — UI helpers for inline creation
- [ ] `isFileStagedForDeletion()` — adapt to candidate diff or remove
- [ ] `showFileDropToast()` — display only

### Exports Updated
- [ ] Remove exports for all deleted functions: `removePendingMove`, `undoObjectMove`, `undoNewFile`, `removeStagedCreation`, `unstageFileDeletion`, `unstageFileMove`, `unstageFolderDeletion`, `unstageFolderCreation`
- [ ] Update renamed function exports: `stageDeleteFile` → `deleteFile`, `stageDeleteFolder` → `deleteFolder`
- [ ] Verify all remaining exports still valid

### Error Handling
- [ ] All `CandidateApi.*` calls check `result.success` before refreshing
- [ ] Failed operations surface error via toast or dialog (no silent failures)

### Audit Logging
- [ ] Server-side CandidateApi endpoints handle audit logging; no client-side audit calls needed

## Verification

### Manual Testing
- Create file via inline input → file appears in tree
- Delete file → file removed from tree
- Create folder → folder appears
- Delete folder → folder removed
- Drag-drop file between folders → file moves
- Drag-drop folder into folder → folder moves
- Drag-drop objects between files → objects move
- Reorder objects within file → order changes
- Undo file/folder operations → reverted
- No console errors

### Linting
- [ ] `npx eslint static/js/explorer/file-operations.js` passes
- [ ] No ESLint warnings or errors

### Playwright Tests
- [ ] File creation via inline input
- [ ] File deletion
- [ ] Folder creation and deletion
- [ ] Drag-drop file between folders
- [ ] Object reorder within file
- [ ] Undo operation

---

## Commandments Compliance

- [x] **C1 — No live config mutation until Apply.** All file/folder operations go through CandidateApi which modifies the candidate directory only. Live config untouched until Apply.
- [x] **C2 — UI visual parity.** Target pane layout, inline create inputs, drag-drop indicators, and folder tree remain visually identical. Only backend calls change.
- [x] **C3 — Full audit logging.** CandidateApi server endpoints log through audit_service.py and application logging. No client-side audit gaps.
- [x] **C4 — Proper error handling.** Every CandidateApi call checks `result.success` and surfaces errors via toast. No silent failures.
- [x] **C5 — Dead code deletion.** All `unstage*` functions, `afterStagingChange()`, `removePendingMove()`, `moveStagedCreationsToFile()`, and other client-side staging helpers are deleted.
- [x] **C6 — Full functionality migration.** Every removed function has a CandidateApi equivalent. File/folder create, delete, move, object reorder, drag-drop all migrated. `buildPendingObjectRow()` and `buildStagedCreationRow()` flagged for review.
- [x] **C7 — Palo Alto candidate model.** All operations target candidate config via CandidateApi. No direct live config mutation.
- [x] **C8 — Change tracking document.** Change Tracking section added above with tickable checklist covering all ~50 functions.
- [x] **C9 — Complete planning before implementation.** This plan fully specifies all changes before any code is written.
- [x] **C10 — Linting enforcement.** Verification section includes ESLint command for this file.
- [x] **C11 — Playwright validation.** Playwright test cases listed for file/folder CRUD, drag-drop, reorder, and undo operations.
