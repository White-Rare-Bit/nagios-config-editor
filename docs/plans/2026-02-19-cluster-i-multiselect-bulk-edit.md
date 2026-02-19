# Cluster I — Multi-Select & Bulk Edit Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 4 multi-select and bulk edit bugs: right-click during multi-select navigates to clicked object (031), bulk edit count mismatch with no explanation (032), mixed-type bulk edit applies invalid attributes to all types (033), select-by-type dialog throws InvalidStateError (034).

**Architecture:** Frontend-only fixes. The right-click handler must detect multi-select mode before navigating. Bulk edit needs type-compatibility filtering with a count explanation. The InvalidStateError in select-by-type is likely a DOM state issue in the dialog.

**Tech Stack:** JavaScript. Key files: `static/js/explorer/context-menu.js`, `static/js/explorer/app.js`, `static/js/explorer/dialogs.js`.

---

### Task 1: Reproduce all 4 bugs with Playwright

**Files:**
- Read: `docs/test-discoveries/031-right-click-during-multiselect-navigates-to-object.md`
- Read: `docs/test-discoveries/032-bulk-edit-count-mismatch-no-explanation.md`
- Read: `docs/test-discoveries/033-mixed-type-bulk-edit-applies-invalid-attributes.md`
- Read: `docs/test-discoveries/034-select-by-type-dialog-invalidstateerror.md`

**Step 1: Start app**, navigate to http://localhost:8080

**Step 2: Reproduce 031 — right-click during multi-select navigates**
1. Select multiple objects (Ctrl+click 3 objects)
2. Verify multi-select is active (count badge shows)
3. Right-click one of the selected objects
4. Observe: navigation happens to the right-clicked object, clearing multi-select

**Step 3: Reproduce 032 — bulk edit count mismatch**
1. Select 5 objects of mixed types (hosts and services)
2. Open bulk edit
3. Apply a change (e.g., set `alias`)
4. Observe: "Edited 3 objects" when 5 were selected — no explanation of why 2 were skipped

**Step 4: Reproduce 033 — mixed-type bulk edit applies invalid attrs**
1. Select hosts and services together
2. Bulk edit: set `max_check_attempts` to `4`
3. Note that `max_check_attempts` is valid for both — but try a host-only attr
4. Apply a host-only attribute (e.g., `parents`) to the mix
5. Observe: attribute applied to services too (invalid)

**Step 5: Reproduce 034 — InvalidStateError**
1. Right-click → "Select by type" (if this option exists)
2. Observe console for InvalidStateError

---

### Task 2: Fix 031 — Right-click preserves multi-select

**Files:**
- Read + Modify: `static/js/explorer/context-menu.js`
- Read + Modify: `static/js/explorer/app.js`

**Step 1: Find the right-click handler on tree items**
Read `static/js/explorer/app.js`. Find the `contextmenu` event handler on tree rows. Find where it calls `selectObjectByIndex` or navigates to the clicked object.

**Step 2: Check multi-select state before navigating**
When right-clicking, if multi-select is already active (more than 1 object selected), do NOT navigate to the right-clicked object — only show the context menu:

```javascript
element.addEventListener('contextmenu', (e) => {
    e.preventDefault();

    const clickedIndex = getIndexFromElement(e.target);

    // If multi-select active and clicked object is already selected,
    // show context menu without navigating
    if (state.selectedKeys.size > 1 && Explorer.isSelectedByIndex(clickedIndex)) {
        showContextMenu(e, clickedIndex);
        return;
    }

    // Otherwise, select the clicked object and show menu
    Explorer.clearSelection();
    Explorer.selectObjectByIndex(clickedIndex);
    showContextMenu(e, clickedIndex);
});
```

**Step 3: Validate with Playwright**
Reproduce Task 1 Step 2. Right-clicking should show the context menu without clearing the multi-selection or navigating.

**Step 4: Run ESLint**

**Step 5: Commit**
```bash
git add static/js/explorer/app.js static/js/explorer/context-menu.js
git commit -m "fix: right-click preserves multi-select when clicked object is already selected

Fixes #031 — right-clicking during multi-select navigated to the clicked
object, destroying the multi-selection before the context menu appeared.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Fix 032/033 — Bulk edit: type filter and count explanation

**Files:**
- Read + Modify: `static/js/explorer/dialogs.js` (bulk edit dialog)

**Step 1: Find the bulk edit submission handler**
Read `static/js/explorer/dialogs.js`. Search for bulk edit logic. Find where it iterates over selected objects and applies the attribute change.

**Step 2: Add type compatibility check (033)**
When applying an attribute to multiple objects, skip objects where the attribute is not valid for their type:
```javascript
async function submitBulkEdit(attrName, attrValue) {
    let applied = 0;
    let skipped = 0;

    for (const key of state.selectedKeys) {
        const obj = Explorer.findObjectByKey(key);
        const validAttrs = Explorer.constants.REQUIRED_FIELDS[obj.object_type] || [];
        const isValidAttr = /* check if attrName is valid for obj.object_type */;

        if (!isValidAttr && isRestrictedAttr(attrName)) {
            skipped++;
            continue; // Skip type-incompatible objects
        }

        await applyEdit(obj, attrName, attrValue);
        applied++;
    }

    // Show count with explanation (032)
    if (skipped > 0) {
        showToast(`Applied to ${applied} objects (${skipped} skipped — incompatible attribute for their type)`, 'info');
    } else {
        showToast(`Applied to ${applied} objects`, 'success');
    }
}
```

**Step 3: Validate with Playwright**
Reproduce Task 1 Steps 3 and 4:
- Mixed-type selection with type-incompatible attribute should skip incompatible objects
- Toast should explain the count discrepancy

**Step 4: Run ESLint**

**Step 5: Commit**
```bash
git add static/js/explorer/dialogs.js
git commit -m "fix: bulk edit skips type-incompatible objects and explains count

Fixes #032, #033 — bulk edit applied attributes to objects of wrong types
and showed count mismatch without explanation.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 4: Fix 034 — InvalidStateError in select-by-type dialog

**Files:**
- Read: `docs/test-discoveries/034-select-by-type-dialog-invalidstateerror.md`
- Read + Modify: `static/js/explorer/app.js` or `static/js/explorer/dialogs.js`

**Step 1: Read the full bug report**
Read the discovery file to understand what exact action triggers the InvalidStateError and what DOM operation causes it.

**Step 2: Find the select-by-type dialog code**
Search for "select by type" or `selectByType` in the JS files.

**Step 3: Fix the DOM state error**
`InvalidStateError` usually occurs when calling `setSelectionRange` on an element that is not visible/focused, or calling `select()` on a detached element. Find the problematic DOM operation and add a check:
```javascript
// Before calling .select() or .setSelectionRange():
if (element && document.body.contains(element)) {
    element.select();
}
```

**Step 4: Validate with Playwright**
Reproduce Task 1 Step 5. No InvalidStateError should appear in the console.

**Step 5: Run ESLint**

**Step 6: Commit**
```bash
git add static/js/explorer/app.js
git commit -m "fix: guard DOM state before selection operation in select-by-type dialog

Fixes #034 — InvalidStateError thrown when dialog tried to select text
in an element that was not yet in a valid focus state.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 5: Final validation

Verify:
- [ ] Right-click preserves multi-selection (031)
- [ ] Bulk edit count mismatch explained in toast (032)
- [ ] Type-incompatible attributes not applied to wrong object types (033)
- [ ] No InvalidStateError from select-by-type (034)

Run: `python3 -m pytest tests/ -v`
