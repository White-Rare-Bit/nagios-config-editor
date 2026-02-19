# Cluster F — Rename Cascade & Reference Integrity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 5 rename cascade bugs: rename doesn't cascade to hostgroup references (001-rename), bulk rename only renames single object (003-bulk-rename), rename host doesn't update service host_name references (029), bulk rename has no reference-update option (030), rename without reference update can commit broken config (076).

**Architecture:** The backend `nagios_service.py` has `update_references` logic but the Rename dialog in the frontend doesn't expose the cascade option. Fix the dialog to call the cascade API, fix the bulk rename loop to process all selected objects, and add validation warning when reference update is unchecked.

**Tech Stack:** JavaScript, Python/Flask. Key files: `nagios_service.py`, `static/js/explorer/dialogs.js`, `routes/objects.py` or equivalent rename route.

---

### Task 1: Reproduce all 5 bugs with Playwright

**Files:**
- Read all 5 discovery files for 001-rename, 003-bulk-rename, 029, 030, 076

**Step 1: Start app**, navigate to http://localhost:8080

**Step 2: Reproduce 001-rename — rename doesn't cascade to hostgroup refs**
1. Open the PING service — note it has `hostgroup_name: linux-hosts`
2. Right-click `linux-hosts` hostgroup → Rename → `linux-hosts-new`
3. Check PING service after rename — `hostgroup_name` still shows `linux-hosts` (broken reference)
4. Take screenshot

**Step 3: Reproduce 003-bulk-rename — bulk rename only single object**
1. Select multiple hosts (Ctrl+click or via By Type → select all)
2. Use bulk rename (context menu or toolbar)
3. Observe only the first selected object was renamed

**Step 4: Reproduce 029 — rename host doesn't update service references**
1. Rename `web-prod-01` host to `web-prod-01-renamed`
2. Check all services that reference `web-prod-01` via `host_name`
3. Services still show `host_name: web-prod-01` (broken reference)

---

### Task 2: Fix rename cascade — expose update_references in Rename dialog

**Files:**
- Read: `nagios_service.py` (update_references method, around line 299-312)
- Read: `routes/objects.py` or equivalent (rename endpoint)
- Read + Modify: `static/js/explorer/dialogs.js` (Rename dialog)

**Step 1: Find the rename API endpoint**
Read the routes directory. Find the endpoint that handles object rename. Check if it accepts a `cascade` parameter.

**Step 2: Find update_references in nagios_service.py**
Read `nagios_service.py` around line 299. Understand the `update_references` method — it updates all objects that reference the renamed object. Check if the rename API calls it.

**Step 3: Expose cascade option in rename endpoint if missing**
If the rename endpoint doesn't call `update_references`, add it:
```python
@bp.route('/api/objects/<stable_key>/rename', methods=['POST'])
def rename_object(stable_key):
    data = request.json
    new_name = data.get('new_name')
    cascade = data.get('cascade', True)  # Default to True for safety

    result = svc.rename_object(stable_key, new_name)
    if result.success and cascade:
        svc.update_references(all_objects, old_name, new_name)
    # ...
```

**Step 4: Add "Update references" checkbox to Rename dialog**
Read `static/js/explorer/dialogs.js`. Find the Rename dialog HTML/rendering. Add a checkbox:
```html
<label>
  <input type="checkbox" id="renameUpdateRefs" checked>
  Update all references to this object
</label>
```

When the rename is submitted, include `cascade: updateRefsCheckbox.checked` in the API call.

**Step 5: For 076 — warn if cascade is unchecked**
If "Update references" is unchecked and impact count > 0, show a confirmation:
```javascript
if (!updateRefs && impactCount > 0) {
    const confirmed = await showConfirmDialog({
        title: 'Rename without updating references?',
        message: `${impactCount} objects reference this object. Renaming without updating references will create broken references.`,
        confirmText: 'Rename anyway',
        type: 'warning'
    });
    if (!confirmed) { return; }
}
```

**Step 6: Validate with Playwright**
Reproduce Task 1 Steps 2 and 4. After rename with "Update references" checked, PING service should show `hostgroup_name: linux-hosts-new`.

**Step 7: Run ruff and ESLint**

**Step 8: Commit**
```bash
git add nagios_service.py routes/objects.py static/js/explorer/dialogs.js
git commit -m "fix: rename dialog cascades reference updates to dependent objects

Fixes #001-rename, #029, #076 — rename did not update objects that
referenced the renamed object, leaving broken references in the config.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Fix 003-bulk-rename — fix bulk rename loop

**Files:**
- Read + Modify: `static/js/explorer/dialogs.js` OR `static/js/explorer/object-editor.js`

**Step 1: Find bulk rename submission handler**
Search for `bulkRename` or the handler that processes multiple selected objects for rename.

**Step 2: Identify the loop bug**
The bug says "only renames single object". Look for a loop that should iterate over `state.selectedKeys` but may be breaking early, or only processing `selectedKeys[0]`, or has an off-by-one error.

**Step 3: Fix the loop**
Ensure ALL selected objects are renamed:
```javascript
async function submitBulkRename(findText, replaceText, useRegex) {
    const selectedObjects = [...state.selectedKeys].map(key => Explorer.findObjectByKey(key));

    for (const obj of selectedObjects) {
        const oldName = Explorer.getEffectiveName(obj);
        const newName = useRegex
            ? oldName.replace(new RegExp(findText, 'g'), replaceText)
            : oldName.replace(findText, replaceText);

        if (newName !== oldName) {
            await ApiClient.post(`/api/objects/${encodeURIComponent(obj.stable_key)}/rename`, {
                new_name: newName, cascade: true
            });
        }
    }
    // ...
}
```

**Step 4: Validate with Playwright**
Reproduce Task 1 Step 3. All selected objects should be renamed.

**Step 5: Run ESLint**

**Step 6: Commit**
```bash
git add static/js/explorer/dialogs.js
git commit -m "fix: bulk rename processes all selected objects (not just first)

Fixes #003-bulk-rename, #030 — bulk rename stopped after first object due
to loop logic error.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 4: Final validation

Verify:
- [ ] Rename cascades to all referencing objects (001-rename, 029)
- [ ] All selected objects renamed in bulk rename (003-bulk-rename)
- [ ] Warning shown when renaming without reference update (076)

Run: `python3 -m pytest tests/ -v`
