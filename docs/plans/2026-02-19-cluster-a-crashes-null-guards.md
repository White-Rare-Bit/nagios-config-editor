# Cluster A — Crashes & Null Guards Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 5 bugs that cause JavaScript crashes or produce corrupted state: cyclic template inheritance stack overflow (018, 075), null crash in stageCurrentChanges for new objects (023), drop-null object corrupts staged state (026), and [object Object] rendering in validation output (064).

**Architecture:** All fixes are defensive guards — add a visited Set for cycle detection in `buildParentChain`, add null guards before attribute access for new objects, validate drag payloads completely, and serialize Error objects properly before display.

**Tech Stack:** JavaScript (ES6+), Flask/Python. No new dependencies.

---

### Task 1: Reproduce all 5 crashes with Playwright

**Files:**
- Read: `docs/test-discoveries/018-cyclic-template-inheritance-causes-stack-overflow.md`
- Read: `docs/test-discoveries/075-cyclic-template-inheritance-stack-overflow.md`
- Read: `docs/test-discoveries/023-null-crash-stageCurrentChanges-new-object.md`
- Read: `docs/test-discoveries/026-drop-null-object-corrupts-staged-state.md`
- Read: `docs/test-discoveries/064-validation-object-object-rendering-bug.md`

**Step 1: Start the app**
Run: `python3 app.py` (in a separate terminal, keep running throughout)
Navigate to: http://localhost:8080

**Step 2: Reproduce 018/075 — cyclic inheritance stack overflow**
1. Navigate to Explorer → By Type → contact → generic-contact
2. Click "+ Add attribute", Name: `use`, Value: `generic-contact`, click OK
3. Open browser DevTools console — look for: `RangeError: Maximum call stack size exceeded`
4. Take screenshot: `.playwright-mcp/repro-018-cyclic.png`
5. Undo the change (Ctrl+Z)

**Step 3: Reproduce 075 — two-object cycle**
1. Navigate to linux-server template
2. Click "+ Add attribute", Name: `use`, Value: `linux-server`, click OK
3. Check DevTools console for same RangeError
4. Undo

**Step 4: Reproduce 023 — null crash in stageCurrentChanges**
1. Click "+" on any file (e.g., hosts.cfg) to open Create Object dialog
2. Immediately click somewhere else (trigger navigation away from new object)
3. Check DevTools console for: `TypeError: Cannot read properties of null (reading 'attributes')`
4. Take screenshot

**Step 5: Reproduce 064 — [object Object] in validation**
1. Navigate to Workspace → Validation tab
2. Click "Run Validation"
3. Check if any error shows `[object Object]` instead of a message
4. Take screenshot

**Step 6: Verify 026 setup**
Read `static/js/explorer/file-operations.js` and search for `processObject` to understand drop handling.

---

### Task 2: Fix 018/075 — Add cycle detection to buildParentChain

**Files:**
- Modify: `static/js/explorer/relations-loader.js`

**Step 1: Read the file and find buildParentChain**
Read `static/js/explorer/relations-loader.js`, search for `buildParentChain` (around line 155).

**Step 2: Understand the recursion**
Identify where `buildParentChain` calls itself recursively. It should be passing `templateUse` (the parent's `use` field) back into itself without checking if it's already been visited.

**Step 3: Add a visited Set parameter**
Find the function signature like:
```javascript
function buildParentChain(parentNames, objType) {
```
Change it to:
```javascript
function buildParentChain(parentNames, objType, visited = new Set()) {
```

At the start of the loop body, before processing each name:
```javascript
for (const name of parentNames) {
    if (visited.has(name)) {
        console.warn(`buildParentChain: cycle detected at '${name}' — skipping`);
        continue;
    }
    visited.add(name);
    // ... rest of existing code
```

When the recursive call is made, pass `visited`:
```javascript
parents: buildParentChain(templateUse, objType, visited)
```

**Step 4: Also add a backend cycle check in nagios_service.py (for 018)**
Read `nagios_service.py`, search for `buildParentChain` or template cycle handling.
Also search for `use` field validation during staging. If there is no backend cycle check, add one.

Read `routes/objects.py` or wherever the `use` field edit is staged to see if there is a validation opportunity.

**Step 5: Validate with Playwright**
Repeat Task 1 Steps 2 and 3. The RangeError should NOT appear. The `use` field change should either be blocked with an error toast or the Impact & Relationships panel should render without crashing.

**Step 6: Run ESLint**
Run: `npx eslint static/js/explorer/relations-loader.js --no-eslintrc -c .eslintrc.js 2>/dev/null || npx eslint static/js/explorer/relations-loader.js`
Fix any new lint errors.

**Step 7: Commit**
```bash
git add static/js/explorer/relations-loader.js
git commit -m "fix: add cycle detection to buildParentChain to prevent stack overflow

Fixes #018, #075 — self-referential or two-object cyclic template
inheritance caused RangeError: Maximum call stack size exceeded.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Fix 023 — Null crash in stageCurrentChanges for new objects

**Files:**
- Modify: `static/js/explorer/object-editor.js`
- Modify: `static/js/explorer/impact-section.js`

**Step 1: Read the crash location**
Read `static/js/explorer/impact-section.js` around line 141 — that's where `obj.attributes` is accessed on a null object.

Read `static/js/explorer/object-editor.js` around line 1225 — the call to `Explorer.loadImpactAndRelationships(state.editedObject)`.

**Step 2: Understand what makes editedObject null**
The crash happens when a new object (not yet in `state.allObjects`) triggers `stageCurrentChanges`. The new object has no corresponding entry in `state.allObjects`, so `findObjectByKey` or similar lookup returns null.

In `impact-section.js` at the crash site, add a null guard:
```javascript
// Before the line that accesses obj.attributes:
if (!obj || !obj.attributes) {
    console.warn('loadImpactAndRelationships: object is null or has no attributes, skipping');
    return;
}
```

In `object-editor.js` around line 1225, guard the loadImpactAndRelationships call:
```javascript
if (state.editedObject && state.editedObject.global_index >= 0) {
    Explorer.loadImpactAndRelationships(state.editedObject);
}
```
(New objects typically have `global_index = -1` or similar sentinel value — verify what value is used.)

**Step 3: Validate with Playwright**
Repeat Task 1 Step 4. The TypeError should not appear. The editor should handle new objects without crashing.

**Step 4: Run ESLint**
Run: `npx eslint static/js/explorer/object-editor.js static/js/explorer/impact-section.js`

**Step 5: Commit**
```bash
git add static/js/explorer/object-editor.js static/js/explorer/impact-section.js
git commit -m "fix: guard null object in stageCurrentChanges for new staged objects

Fixes #023 — new objects not yet in allObjects caused TypeError when
loadImpactAndRelationships was called during stageCurrentChanges.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 4: Fix 026 — Drop null object corrupts staged state

**Files:**
- Modify: `static/js/explorer/file-operations.js`
- Modify: `static/js/explorer/constants.js` (Explorer.isObjectTemplate)

**Step 1: Find processObject in file-operations.js**
Read `static/js/explorer/file-operations.js`, search for `processObject`. Note that it has a guard `if (!objData) {return;}` but this doesn't catch `{}` (empty object, which is truthy).

**Step 2: Strengthen the null check**
Change the guard from:
```javascript
if (!objData) {return;}
```
To:
```javascript
if (!objData || !objData.attributes || !objData.source_file || !objData.object_type) {
    console.warn('processObject: skipping incomplete object payload', objData);
    return;
}
```

**Step 3: Guard isObjectTemplate in constants.js**
Read `static/js/explorer/constants.js` around line 143. The `isObjectTemplate` function likely accesses `obj.attributes.register` without checking if `obj.attributes` is defined.

Add guard:
```javascript
Explorer.isObjectTemplate = function(obj) {
    if (!obj || !obj.attributes) { return false; }
    // ... existing logic
};
```

**Step 4: Validate with Playwright**
Navigate to the file tree, try drag and drop operations. Verify no crashes occur. Check DevTools console for errors.

**Step 5: Run ESLint**
Run: `npx eslint static/js/explorer/file-operations.js static/js/explorer/constants.js`

**Step 6: Commit**
```bash
git add static/js/explorer/file-operations.js static/js/explorer/constants.js
git commit -m "fix: guard null/empty drag payload in processObject and isObjectTemplate

Fixes #026 — empty object {} passed through null check (truthy), stored
corrupted staged move entry, crashed renderer on next drag operation.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 5: Fix 064 — [object Object] in validation error rendering

**Files:**
- Search: all JS files for where validation errors are rendered to DOM

**Step 1: Find the rendering code**
Run validation in the browser (Workspace → Validation → Run Validation) and check what JS file renders the errors. Search for `ERRORS` or `validation` in `static/js/`.

**Step 2: Find the string concatenation bug**
Search for where error objects are inserted into HTML. Look for patterns like:
```javascript
`${error}`  // or
"" + error  // or
innerHTML = error  // where error is an Error object
```

**Step 3: Fix the serialization**
Change `${error}` or `"" + error` to `${error.message || error}` or `String(error.message || error)`.

**Step 4: Validate with Playwright**
Run Workspace → Validation. If the binary path is wrong, the error should show a readable message, not `[object Object]`.

**Step 5: Run ESLint**

**Step 6: Commit**
```bash
git add <modified files>
git commit -m "fix: serialize Error objects before inserting into validation output

Fixes #064 — template literal of an Error object produced [object Object]
instead of the actual error message.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 6: Final Playwright validation — all 5 bugs resolved

Repeat all reproduction steps from Task 1. Verify:
- [ ] No `RangeError: Maximum call stack size exceeded` when setting cyclic `use` field
- [ ] No `TypeError: Cannot read properties of null` when creating new objects
- [ ] Drag operations work without renderer crashes
- [ ] Validation errors show readable text, not `[object Object]`

Run full test suite: `python3 -m pytest tests/ -v`
