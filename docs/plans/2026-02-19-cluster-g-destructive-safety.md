# Cluster G — Destructive Operation Safety Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 3 missing-confirmation bugs: no confirmation dialog before staging file deletion (003-delete), no object-count warning when deleting a file that contains objects (038), no confirmation before context menu Delete (065).

**Architecture:** Three places in the frontend need a `showConfirmDialog` call before the destructive action proceeds. A `showConfirmDialog` function likely already exists (used for other confirmations). For file deletion, also fetch the object count in the file to include in the confirmation message.

**Tech Stack:** JavaScript. Key files: `static/js/explorer/file-operations.js`, `static/js/explorer/context-menu.js`.

---

### Task 1: Reproduce all 3 bugs with Playwright

**Files:**
- Read: `docs/test-discoveries/003-delete-file-no-confirmation.md`
- Read: `docs/test-discoveries/038-delete-file-with-objects-no-warning.md`
- Read: `docs/test-discoveries/065-context-menu-delete-no-confirmation.md`

**Step 1: Start app**, navigate to http://localhost:8080

**Step 2: Reproduce 003-delete — file deletion no confirmation**
1. In the file tree, right-click a .cfg file → Delete
2. Observe: file is staged for deletion immediately with no confirmation dialog
3. Undo to restore

**Step 3: Reproduce 038 — delete file with objects no warning**
1. Right-click hosts.cfg → Delete
2. Observe: file staged for deletion without mentioning how many hosts will be deleted
3. Undo

**Step 4: Reproduce 065 — context menu delete on object no confirmation**
1. Right-click any object → Delete
2. Observe: object is staged for deletion immediately with no confirmation

---

### Task 2: Fix 003-delete and 038 — Add confirmation to file deletion

**Files:**
- Read + Modify: `static/js/explorer/file-operations.js`

**Step 1: Find the file delete handler**
Read `static/js/explorer/file-operations.js`. Search for where a file is staged for deletion (likely a `deleteFile` function or similar handler for a delete button/menu item).

**Step 2: Find existing showConfirmDialog usage**
Search `static/js/` for `showConfirmDialog` to find the existing pattern and function signature. It likely looks like:
```javascript
const confirmed = await showConfirmDialog({
    title: 'Delete File?',
    message: '...',
    confirmText: 'Delete',
    type: 'danger'
});
if (!confirmed) { return; }
```

**Step 3: Count objects in the file**
Before showing the confirmation, count how many objects are in the file:
```javascript
const objectsInFile = state.allObjects.filter(o => o.source_file === filePath);
const objectCount = objectsInFile.length;
const objectSummary = objectCount > 0
    ? `\n\nThis file contains ${objectCount} object${objectCount > 1 ? 's' : ''} that will also be deleted.`
    : '';
```

**Step 4: Show confirmation with object count**
```javascript
const confirmed = await showConfirmDialog({
    title: `Delete ${fileName}?`,
    message: `Are you sure you want to delete "${fileName}"?${objectSummary}`,
    confirmText: 'Delete File',
    type: 'danger'
});
if (!confirmed) { return; }
// ... proceed with staging deletion
```

**Step 5: Validate with Playwright**
Reproduce Task 1 Steps 2 and 3. File deletion should now show a dialog. For hosts.cfg the dialog should mention the number of hosts.

**Step 6: Run ESLint**

**Step 7: Commit**
```bash
git add static/js/explorer/file-operations.js
git commit -m "fix: add confirmation dialog before staging file deletion

Fixes #003-delete, #038 — files (and all their objects) could be staged
for deletion with a single click and no confirmation or object-count warning.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Fix 065 — Add confirmation to context menu object Delete

**Files:**
- Read + Modify: `static/js/explorer/context-menu.js`

**Step 1: Find the context menu Delete handler**
Read `static/js/explorer/context-menu.js`. Find `contextAction` or the function that handles `action === 'delete'`.

**Step 2: Add confirmation before staging deletion**
```javascript
case 'delete':
    const objectName = Explorer.getEffectiveName(selectedObject);
    const confirmed = await showConfirmDialog({
        title: `Delete ${objectName}?`,
        message: `Are you sure you want to stage "${objectName}" for deletion?`,
        confirmText: 'Delete',
        type: 'danger'
    });
    if (!confirmed) { return; }
    // ... existing delete logic
    break;
```

For multi-select delete, show the count:
```javascript
const count = state.selectedKeys.size;
const message = count > 1
    ? `Delete ${count} selected objects?`
    : `Delete "${objectName}"?`;
```

**Step 3: Validate with Playwright**
Reproduce Task 1 Step 4. Right-click → Delete should show a confirmation dialog.

**Step 4: Run ESLint**

**Step 5: Commit**
```bash
git add static/js/explorer/context-menu.js
git commit -m "fix: add confirmation dialog before context menu object deletion

Fixes #065 — Delete from context menu immediately staged deletion with
no confirmation, allowing accidental single-click destruction.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 4: Final validation

Verify:
- [ ] File deletion shows confirmation with object count (003-delete, 038)
- [ ] Object deletion via context menu shows confirmation (065)

Run: `python3 -m pytest tests/ -v`
