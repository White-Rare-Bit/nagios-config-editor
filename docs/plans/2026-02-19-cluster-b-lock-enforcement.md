# Cluster B — Lock Enforcement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 4 lock enforcement bugs: context menu operations bypass staging lock entirely (067), editor fields remain editable while locked (042), editor shows rejected values after lock releases (043), stale session lock persists after server restart (002-stale).

**Architecture:** Three frontend fixes (disable context menu items, add `disabled` to field inputs, refresh fields on lock release) plus one backend fix (clear stale lock on startup or add TTL-based expiry).

**Tech Stack:** JavaScript (ES6+), Python/Flask. Key files: `context-menu.js`, `object-editor.js`, `app.js`, `state-management.js`, `staging_manager.py`.

---

### Task 1: Reproduce all 4 bugs with Playwright

**Files:**
- Read: `docs/test-discoveries/067-context-menu-bypass-staging-lock.md`
- Read: `docs/test-discoveries/042-fields-not-readonly-while-locked.md`
- Read: `docs/test-discoveries/043-editor-shows-rejected-value-after-unlock.md`
- Read: `docs/test-discoveries/002-stale-session-lock-persists-across-restart.md`

**Step 1: Start the app**
Run: `python3 app.py`
Navigate to: http://localhost:8080

**Step 2: Set up two-tab scenario (for 067, 042, 043)**
1. Open Explorer in Tab 1: http://localhost:8080
2. In Tab 1: Select any host → edit the alias field → blur to stage the change
3. Verify Tab 1 owns the lock: check for Undo badge > 0
4. Open Tab 2: open a new browser tab to http://localhost:8080
5. Tab 2 should show a lock banner

**Step 3: Reproduce 067 — context menu bypasses lock**
In Tab 2:
1. Right-click any service → Rename...
2. Enter a new name → click Rename
3. Expected: error/lock warning. Actual: rename silently succeeds
4. Take screenshot: `.playwright-mcp/repro-067.png`
5. Undo from Tab 1 to restore state

**Step 4: Reproduce 042 — fields editable while locked**
In Tab 2:
1. Select any host
2. Click into the `alias` field and type "Tab2 attempt"
3. Click elsewhere to blur/save
4. Expected: field should be uneditable. Actual: typing is allowed, 423 toast fires
5. Take screenshot

**Step 5: Reproduce 043 — rejected value persists after unlock**
1. Continue from Step 4 state (Tab 2 has stale typed value)
2. In Tab 1: click Discard (releases lock)
3. Observe Tab 2: lock banner should disappear
4. Check Tab 2's alias field: still shows "Tab2 attempt" instead of original value
5. Take screenshot

**Step 6: Reproduce 002 — stale lock after restart**
1. In Tab 1, make an edit (acquire lock)
2. Stop the Flask server (Ctrl+C)
3. Restart: `python3 app.py`
4. Open a fresh browser tab → try to edit any object
5. Expected: should work. Actual: "Locked by another user" error

---

### Task 2: Fix 067 — Add lock check to context menu

**Files:**
- Read + Modify: `static/js/explorer/context-menu.js`
- Read: `static/js/explorer/state-management.js` (find where isEditingLocked is stored)

**Step 1: Find the lock state variable**
Read `static/js/explorer/state-management.js` and `static/js/explorer/app.js` around line 147-179.
Find the state variable for lock status (likely `state.isEditingLocked` or `Explorer.isEditingLocked`).

**Step 2: Find context menu show function**
Read `static/js/explorer/context-menu.js`. Find the function that shows the context menu (likely `showContextMenu` or `handleContextMenu`, around line 50).

**Step 3: Add lock check before context menu items are enabled**
In the function that sets up the context menu, after building the menu but before showing it, check the lock state. Disable mutation items (Rename, Clone, Move to File, Add to Group, Delete) when locked:

```javascript
// After menu.classList.add('visible'):
const isLocked = /* check state.isEditingLocked or equivalent */;
if (isLocked) {
    const mutationItems = menu.querySelectorAll('[data-action="rename"], [data-action="clone"], [data-action="move"], [data-action="addToGroup"], [data-action="delete"]');
    mutationItems.forEach(item => item.classList.add('disabled'));
}
```

**Step 4: Also guard contextAction handler**
Find `contextAction` function (around line 133). At the start, check the lock and return early with a toast if locked:

```javascript
function contextAction(action) {
    const mutationActions = ['rename', 'clone', 'moveToFile', 'addToGroup', 'delete'];
    if (mutationActions.includes(action) && /* isLocked */) {
        Explorer.showToast('Staging is locked by another session', 'error');
        hideContextMenu();
        return;
    }
    hideContextMenu();
    // ... rest of existing code
}
```

**Step 5: Validate with Playwright**
Reproduce Step 3 of Task 1. In Tab 2, right-clicking should either show disabled menu items or show a toast when rename is attempted.

**Step 6: Run ESLint**
Run: `npx eslint static/js/explorer/context-menu.js`

**Step 7: Commit**
```bash
git add static/js/explorer/context-menu.js
git commit -m "fix: disable context menu mutation actions while staging is locked

Fixes #067 — context menu Rename/Clone/Move/Delete bypassed staging lock,
allowing silent writes by non-owner sessions.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Fix 042 — Disable editor fields while locked

**Files:**
- Read + Modify: `static/js/explorer/object-editor.js`

**Step 1: Find renderCenterAttributes function**
Read `static/js/explorer/object-editor.js` around lines 626-677. This function renders the attribute input fields.

**Step 2: Find where inputs are constructed**
Locate the template literals that build `<input type="text">` and `<textarea>` elements. They likely look like:
```javascript
`<input type="text" class="attr-value" value="${escapedValue}" ...>`
```

**Step 3: Add disabled attribute based on lock state**
Determine how to access the lock state from within object-editor.js (likely `state.isEditingLocked` where `state` is the module's local state object, OR `Explorer.isEditingLocked`).

Add to each input/textarea:
```javascript
const isLocked = state.isEditingLocked; // or however lock state is accessed
// In the template literal:
`<input type="text" class="attr-value" value="${escapedValue}"${isLocked ? ' disabled' : ''} ...>`
```

Also disable the "+ Add attribute" button and remove/edit buttons while locked.

**Step 4: Ensure re-render when lock state changes**
Find where `updateEditingLockedUI` or `updateLockState` is called. After it is called, ensure `renderCenterAttributes` is also called if an object is currently open:

```javascript
function updateEditingLockState(isLocked) {
    // existing code that adds/removes body class
    // ADD:
    if (state.editedObject) {
        Explorer.renderCenterAttributes(); // re-render to add/remove disabled
    }
}
```

**Step 5: Validate with Playwright**
Reproduce Task 1 Step 4. In the locked Tab 2, clicking into fields should not allow typing (inputs should be visually disabled/greyed out).

**Step 6: Run ESLint**

**Step 7: Commit**
```bash
git add static/js/explorer/object-editor.js
git commit -m "fix: disable editor input fields while staging lock is held by another session

Fixes #042 — fields were editable while locked, creating false impression
of saved state when all edits were rejected 423.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 4: Fix 043 — Refresh field values when lock releases

**Files:**
- Read + Modify: `static/js/explorer/app.js` OR `static/js/explorer/state-management.js`

**Step 1: Find the lock polling / lock release detection**
Read `static/js/explorer/app.js` around lines 162-201 (`checkStagingChanges` or `checkLockStatus`).
Find where `state.isEditingLocked` transitions from `true` to `false`.

**Step 2: Trigger editor refresh on lock release**
After the lock transitions to `false`, if an object is currently being viewed, reload the editor from the authoritative source (the server or `state.allObjects`), discarding any locally-typed rejected values:

```javascript
const wasLocked = state.isEditingLocked;
await checkLockStatus();
const nowLocked = state.isEditingLocked;

if (wasLocked && !nowLocked) {
    // Lock was just released — refresh editor to discard rejected typed values
    if (state.editedObject) {
        // Reload the object's current values from state.allObjects (disk values)
        const freshObj = state.allObjects.find(o => o.global_index === state.editedObject.global_index);
        if (freshObj) {
            state.editedObject = { ...freshObj };
            state.originalAttributes = { ...freshObj.attributes };
            Explorer.renderCenterAttributes();
        }
    }
}
```

**Step 3: Validate with Playwright**
Reproduce Task 1 Steps 4 and 5. After Tab 1 releases the lock, Tab 2's alias field should revert from "Tab2 attempt" back to the actual value.

**Step 4: Run ESLint**

**Step 5: Commit**
```bash
git add static/js/explorer/app.js
git commit -m "fix: refresh editor fields when staging lock is released

Fixes #043 — after lock release, editor showed rejected (never-saved)
typed values instead of actual current values.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 5: Fix 002-stale — Clear stale session lock on server startup

**Files:**
- Read + Modify: `staging_manager.py`
- Read: `routes/staging.py` (around line 611, api_break_lock)
- Read: `app.py` (startup initialization)

**Step 1: Understand the lock persistence**
Read `staging_manager.py` around lines 751, 637 (staging_file path and clear_staging). Understand where the sessionId is persisted.

**Step 2: Add stale lock detection on startup**
In `app.py` or in the StagingManager constructor/init, after loading `staging.json`, check if the lock should be considered stale.

Option A — clear lock on startup (safest UX: lock is always released after restart):
In `staging_manager.py`, in the `__init__` or `load_staging` method, after reading the file:
```python
# After loading staging data:
if staging_data.get('sessionId'):
    # Lock from previous session is now stale — clear it
    # but preserve pendingEdits, stagedCreations, etc.
    staging_data['sessionId'] = None
    staging_data['userName'] = None
    self.save_staging(staging_data)
    logger.info("Cleared stale session lock on startup")
```

Option B — add TTL-based expiry in can_modify:
Read `staging_manager.py` around line 987, 1006. In `can_modify`:
```python
def can_modify(self, session_id: str) -> bool:
    owner = self.get_lock_owner()
    if owner is None:
        return True
    if owner == session_id:
        return True
    # Check if lock timestamp is stale (server restart means no active sessions)
    data = self.get_staging()
    lock_time = data.get('lockAcquiredAt', 0)
    if time.time() - lock_time > 3600:  # 1 hour stale threshold
        return True
    return False
```

The file must also save `lockAcquiredAt` when lock is first acquired.

**Step 3: Fix api_break_lock (routes/staging.py:611)**
Read `routes/staging.py` around line 611. Verify that `clear_staging()` fully zeroes the sessionId. If it doesn't, fix it. Also surface the git discard side-effect in the API response.

**Step 4: Validate with Playwright**
Reproduce Task 1 Step 6 (restart cycle). After restart, new tab should be able to edit freely.
Also verify: after restart, the staging changes (pending edits) should still be visible.

**Step 5: Run ruff**
Run: `ruff check staging_manager.py routes/staging.py app.py`
Fix any issues.

**Step 6: Commit**
```bash
git add staging_manager.py routes/staging.py
git commit -m "fix: clear stale session lock on server startup

Fixes #002 — staging.json retained previous session's sessionId across
server restarts, permanently blocking all new sessions from editing.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 6: Final Playwright validation — all 4 bugs resolved

Verify:
- [ ] Context menu Rename/Clone/Delete blocked while locked (067)
- [ ] Editor fields not editable while locked (042)
- [ ] Fields refresh to actual values when lock releases (043)
- [ ] Fresh tab after server restart can edit normally (002-stale)

Run: `python3 -m pytest tests/ -v`
