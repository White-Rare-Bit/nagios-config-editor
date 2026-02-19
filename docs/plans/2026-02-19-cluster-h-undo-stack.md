# Cluster H — Undo Stack Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 4 undo stack bugs: Ctrl+Z fires API even when undo button is disabled (005), Ctrl+Z undoes multiple operations per keystroke (020), undo description shows "Unknown" (027), concurrent undo race condition (028).

**Architecture:** Fixes span the keyboard handler (check disabled state before calling API), the undo stack pop logic (ensure only one operation per undo call), object name resolution for undo descriptions, and request debouncing to prevent concurrent undo calls.

**Tech Stack:** JavaScript, Python/Flask. Key files: `static/js/base.js`, `static/js/explorer/app.js`, `routes/staging.py`.

---

### Task 1: Reproduce all 4 bugs with Playwright

**Files:**
- Read: `docs/test-discoveries/005-ctrlz-fires-api-when-undo-disabled.md`
- Read: `docs/test-discoveries/020-ctrl-z-undoes-multiple-operations.md`
- Read: `docs/test-discoveries/027-undo-description-shows-unknown.md`
- Read: `docs/test-discoveries/028-concurrent-undo-race-condition.md`

**Step 1: Start app**, navigate to http://localhost:8080

**Step 2: Reproduce 005 — Ctrl+Z fires API when disabled**
1. Ensure undo stack is empty (no staged changes)
2. Verify Undo button shows as disabled
3. Open browser DevTools → Network tab
4. Press Ctrl+Z
5. Observe: a POST to /api/staging/undo is fired despite button being disabled
6. Take screenshot

**Step 3: Reproduce 020 — Ctrl+Z undoes multiple at once**
1. Make 3 separate edits (change 3 different field values)
2. Verify Undo count shows 3
3. Press Ctrl+Z once
4. Observe: undo count drops by more than 1 (or all 3 are undone at once)

**Step 4: Reproduce 027 — undo description shows Unknown**
1. Make an edit that creates an undo entry
2. Hover over the Undo button OR check the tooltip/description
3. Observe: description shows "Unknown" instead of the object name

**Step 5: Reproduce 028 — concurrent undo race**
1. Make 2+ edits
2. Rapidly press Ctrl+Z twice in quick succession
3. Check result — should undo 2 ops sequentially, but may produce errors or incorrect state

---

### Task 2: Fix 005 — Check disabled state before firing undo API

**Files:**
- Read + Modify: `static/js/base.js`

**Step 1: Find the Ctrl+Z keyboard handler**
Read `static/js/base.js`. Search for `keydown` event listener that handles `Ctrl+Z`. Based on prior analysis, `updateUndoButton` is at line 188, so the keyboard handler is likely nearby.

**Step 2: Find where the undo API is called**
Search for `api/staging/undo` or `undoLastAction`. Find the keyboard handler that calls the undo API.

**Step 3: Add disabled state check**
Before calling the undo API, check if the undo button is disabled:
```javascript
document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
        e.preventDefault();
        const undoBtn = document.getElementById('navUndoBtn');
        if (undoBtn && undoBtn.disabled) {
            return; // Don't call API if undo is disabled
        }
        performUndo();
    }
});
```

**Step 4: Validate with Playwright**
Reproduce Task 1 Step 2. Ctrl+Z with empty undo stack should not fire any network request.

**Step 5: Run ESLint**

**Step 6: Commit**
```bash
git add static/js/base.js
git commit -m "fix: Ctrl+Z keyboard shortcut respects undo button disabled state

Fixes #005 — Ctrl+Z fired API undo endpoint even when button was disabled
and undo stack was empty.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Fix 020 — Undo pops only one operation per keystroke

**Files:**
- Read + Modify: `routes/staging.py` (undo endpoint)
- Read + Modify: `static/js/base.js` or `static/js/explorer/app.js`

**Step 1: Find the undo endpoint**
Read `routes/staging.py`. Search for the `/api/staging/undo` endpoint. Find how it pops from the undo stack — does it pop all operations with the same transaction ID, or just one?

**Step 2: Find the undo stack grouping logic**
Read `staging_manager.py`. Find the undo stack data structure. Understand if operations are grouped by transaction or all stored separately. The bug is that one Ctrl+Z pops multiple operations.

**Step 3: Fix the pop behavior**
Ensure the undo endpoint pops exactly one logical operation (which may be a single field change or a rename, but NOT multiple unrelated edits):

Option A — If operations are grouped by txn_id, ensure only the latest group is popped.
Option B — If a while loop is popping until empty, change it to pop exactly once.

**Step 4: Validate with Playwright**
Reproduce Task 1 Step 3. Each Ctrl+Z should decrement the undo count by exactly 1.

**Step 5: Run ruff**

**Step 6: Commit**
```bash
git add routes/staging.py staging_manager.py
git commit -m "fix: undo pops exactly one operation per Ctrl+Z

Fixes #020 — Ctrl+Z was undoing multiple operations simultaneously due
to incorrect grouping in the undo stack pop logic.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 4: Fix 027 — Undo description resolves object names

**Files:**
- Read + Modify: `routes/staging.py` OR `staging_manager.py` (undo stack entry creation)

**Step 1: Find where undo stack entries are created**
Read `staging_manager.py`. Search for where undo entries are pushed onto the stack. Find the `description` or `name` field that shows "Unknown".

**Step 2: Find the object name resolution**
When an edit is staged, the undo entry needs the object's display name. Find where the name is supposed to come from. It likely reads from `state.editedObject.display_name` or resolves from the stable key.

**Step 3: Fix name resolution**
Ensure the undo entry stores the display name at the time of staging:
```python
def push_undo(self, operation_type, stable_key, description=None, **kwargs):
    # If description not provided, try to resolve from the object
    if not description:
        # Parse stable key to get name component
        parts = base64.b64decode(stable_key).decode('utf-8').split('|')
        description = parts[2] if len(parts) >= 3 else 'Unknown'

    self.undo_stack.append({
        'type': operation_type,
        'key': stable_key,
        'description': description,
        **kwargs
    })
```

**Step 4: Validate with Playwright**
Make an edit and hover the undo button. The tooltip/description should show the object name, not "Unknown".

**Step 5: Run ruff**

**Step 6: Commit**
```bash
git add staging_manager.py
git commit -m "fix: undo stack entries resolve object name from stable key

Fixes #027 — undo description showed 'Unknown' because object name was
not stored when the undo entry was created.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 5: Fix 028 — Debounce concurrent undo requests

**Files:**
- Read + Modify: `static/js/base.js` OR `static/js/explorer/app.js`

**Step 1: Find the performUndo function**
Read `static/js/base.js` or `app.js`. Find the `performUndo` function that calls the undo API.

**Step 2: Add in-flight debounce**
Add a flag that prevents concurrent undo calls:
```javascript
let isUndoing = false;

async function performUndo() {
    if (isUndoing) { return; } // Prevent concurrent calls
    isUndoing = true;
    try {
        const result = await ApiClient.post('/api/staging/undo');
        // ... handle result
    } finally {
        isUndoing = false;
    }
}
```

**Step 3: Validate with Playwright**
Reproduce Task 1 Step 5. Rapid Ctrl+Z should process operations sequentially, not concurrently.

**Step 4: Run ESLint**

**Step 5: Commit**
```bash
git add static/js/base.js
git commit -m "fix: debounce rapid Ctrl+Z to prevent concurrent undo API calls

Fixes #028 — rapid Ctrl+Z fired multiple concurrent undo requests,
creating race conditions in the undo stack.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 6: Final validation

Verify:
- [ ] Ctrl+Z with empty stack fires no network request (005)
- [ ] Each Ctrl+Z undoes exactly one operation (020)
- [ ] Undo tooltip shows object name, not Unknown (027)
- [ ] Rapid Ctrl+Z processes sequentially without race conditions (028)

Run: `python3 -m pytest tests/ -v`
