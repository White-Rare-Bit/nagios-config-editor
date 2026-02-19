# Cluster K — Object Creation & Cloning Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 7 object creation and cloning bugs: inline comments not visible in preview (001-inline-comments), plus button uses wrong default type for file context (001-plus), inline object creation has no cancel mechanism (002-inline), clone drops inline comments (003-clone), plus button inherits type from previous form (007), name field primary key desync on initial fill (010), clone dialog has no target file selection (036).

**Architecture:** Mostly independent small fixes. The inline comment bugs require API/staging to preserve the `inline_comments` field. The plus button bugs require resetting form state between uses. The cancel mechanism requires a staged creation to be removed on ESC. The clone file selection is a new dialog field.

**Tech Stack:** JavaScript, Python/Flask. Key files: `static/js/explorer/object-editor.js`, `static/js/explorer/dialogs.js`, backend staging/object routes.

---

### Task 1: Reproduce key bugs with Playwright

**Files:**
- Read all 7 discovery files for bugs 001-inline-comments, 001-plus, 002-inline, 003-clone, 007, 010, 036

**Step 1: Start app**, navigate to http://localhost:8080

**Step 2: Reproduce 007/001-plus — plus button type issues**
1. Click "+" on hosts.cfg → observe default type in dialog
2. Create a host → close dialog
3. Click "+" again on hosts.cfg → observe if type field still shows "host" or something else

**Step 3: Reproduce 002-inline — no cancel for inline creation**
1. Click "+" to create a new object
2. The new unnamed object form opens
3. Try pressing Escape — dialog should close with no staged object
4. Check staging: new object may still be staged

**Step 4: Reproduce 010 — name field primary key desync**
1. Create new object, type a name in the name field
2. Tab to another field
3. Change the name field again
4. Observe if the stable key / primary key is out of sync with what's displayed

---

### Task 2: Fix 007/001-plus — Plus button resets type between uses

**Files:**
- Read + Modify: `static/js/explorer/object-editor.js` or `static/js/explorer/dialogs.js`

**Step 1: Find the plus button handler**
Search for where the Create Object dialog is initialized. Find where the object type dropdown is set.

**Step 2: Determine the correct default type**
For 001-plus, the default should be inferred from the file context (most common type in the file). For 007, the type should reset to this default between creations (not persist from previous).

**Step 3: Set default type from file context**
```javascript
function getDefaultTypeForFile(filePath) {
    const objectsInFile = state.allObjects.filter(o => o.source_file === filePath);
    if (objectsInFile.length === 0) { return 'host'; } // fallback

    // Count object types and return the most common
    const typeCounts = {};
    objectsInFile.forEach(o => typeCounts[o.object_type] = (typeCounts[o.object_type] || 0) + 1);
    return Object.entries(typeCounts).sort(([,a],[,b]) => b-a)[0][0];
}
```

**Step 4: Reset form state on open**
Ensure the dialog always starts fresh:
```javascript
function openCreateDialog(targetFile) {
    const defaultType = getDefaultTypeForFile(targetFile);
    typeDropdown.value = defaultType;
    nameInput.value = '';
    // ... reset all form fields
}
```

**Step 5: Validate with Playwright**
Reproduce Task 1 Step 2. Plus button on hosts.cfg should default to host. After creating one object, clicking "+" again should still default to the file's type.

**Step 6: Run ESLint**

**Step 7: Commit**
```bash
git add static/js/explorer/object-editor.js
git commit -m "fix: plus button infers default type from file context and resets between uses

Fixes #001-plus, #007 — create dialog used wrong default type and persisted
type from previous creation session.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Fix 002-inline — Add cancel to inline creation

**Files:**
- Read + Modify: `static/js/explorer/object-editor.js`

**Step 1: Find where inline creation stages the empty object**
Find where clicking "+" immediately stages a new empty object (before the user has filled anything in).

**Step 2: Add ESC cancel handler**
When the inline creation form is open, add an ESC keydown handler that:
1. Removes the staged creation from `stagedCreations`
2. Closes the form
3. Updates the tree

```javascript
function openInlineCreation(targetFile, objectType) {
    // ... open form ...

    const onEsc = (e) => {
        if (e.key === 'Escape') {
            cancelInlineCreation(newObjectId);
            document.removeEventListener('keydown', onEsc);
        }
    };
    document.addEventListener('keydown', onEsc);
}

function cancelInlineCreation(objectId) {
    state.stagedCreations.delete(objectId);
    Explorer.refreshAfterObjectChange();
    closeInlineForm();
}
```

**Step 3: Also add a visible Cancel button**
Show a cancel button in the new object form next to Save.

**Step 4: Validate with Playwright**
Reproduce Task 1 Step 3. After opening inline creation, pressing Escape should remove the staged object.

**Step 5: Run ESLint**

**Step 6: Commit**
```bash
git add static/js/explorer/object-editor.js
git commit -m "fix: add ESC cancel and Cancel button to inline object creation

Fixes #002-inline — pressing Escape during inline creation left an empty
staged object with no way to discard it except Undo.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 4: Fix 001-inline-comments and 003-clone — Preserve inline comments

**Files:**
- Read + Modify: relevant backend staging/object code (where clone is staged)
- Read: `nagios_model.py` or `nagios_parser.py` (inline_comments field)

**Step 1: Find where clone staging happens**
Read `routes/objects.py` or equivalent. Find the clone endpoint. Verify whether `inline_comments` from the source object is included in the cloned object's attributes.

**Step 2: Include inline_comments in clone**
If `inline_comments` is omitted:
```python
cloned_attrs = dict(source_obj.attributes)
# Include inline comments from the source
if hasattr(source_obj, 'inline_comments'):
    cloned_obj.inline_comments = source_obj.inline_comments
```

**Step 3: Fix preview API response (001-inline-comments)**
Find where the object preview API is served. Ensure `inline_comments` is included in the response JSON.

**Step 4: Validate with Playwright**
Create an object with inline comments (`# this is a comment`). Clone it. Verify the clone shows the same comments.

**Step 5: Run ruff / ESLint**

**Step 6: Commit**
```bash
git add routes/objects.py
git commit -m "fix: preserve inline_comments in clone and object preview

Fixes #001-inline-comments, #003-clone — inline comments were dropped
from cloned objects and excluded from the preview API response.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 5: Fix 010 — Name field primary key stays in sync

**Files:**
- Read + Modify: `static/js/explorer/object-editor.js`

**Step 1: Read the full bug report**
Read `docs/test-discoveries/010-name-field-primary-key-desync.md` carefully.

**Step 2: Find name field change handler**
Find where changes to the name field update the object's primary key / stable key. There may be an initial auto-population that doesn't update the stable key on subsequent changes.

**Step 3: Fix to always sync on name change**
Ensure the name change handler always updates the primary key:
```javascript
nameField.addEventListener('input', (e) => {
    const newName = e.target.value.trim();
    state.editedObject.display_name = newName;
    // Also update the primary key attribute
    const nameFieldKey = Explorer.getNameField(state.editedObject.object_type);
    state.editedObject.attributes[nameFieldKey] = newName;
    stageCurrentChanges();
});
```

**Step 4: Validate with Playwright**
Reproduce Task 1 Step 4. After changing the name field multiple times, the stable key and display should be consistent.

**Step 5: Run ESLint**

**Step 6: Commit**
```bash
git add static/js/explorer/object-editor.js
git commit -m "fix: name field change always syncs primary key

Fixes #010 — two-way binding between name field and primary key broke
after initial auto-population; subsequent name changes weren't reflected.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 6: Final validation

Verify:
- [ ] Plus button uses correct default type, resets between opens (001-plus, 007)
- [ ] ESC cancels inline creation without leaving staged object (002-inline)
- [ ] Clone preserves inline comments (003-clone, 001-inline-comments)
- [ ] Name field changes stay in sync with primary key (010)

Run: `python3 -m pytest tests/ -v`
