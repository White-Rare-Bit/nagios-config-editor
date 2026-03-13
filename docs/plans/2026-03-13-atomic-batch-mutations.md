# Atomic Batch Mutations Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make all bulk frontend operations produce a single undo snapshot instead of one per item.

**Architecture:** Create one generic `/api/batch-mutations` endpoint that accepts an array of create/update operations and wraps them in a single snapshot. Then migrate 7 frontend functions to use it. Also fix `applyMove()` to use the existing `/api/move-objects` batch endpoint.

**Tech Stack:** Python/Flask backend, ES module JavaScript frontend

---

### Task 1: Create `/api/batch-mutations` backend endpoint

**Files:**
- Modify: `routes/bulk_ops.py` (add endpoint after `/api/move-objects`)
- Modify: `routes/__init__.py` (verify `bulk_ops` blueprint already registered — no change expected)

**Step 1: Add the batch mutations endpoint**

Add this after the existing `/api/move-objects` route in `routes/bulk_ops.py`:

```python
@bp.route("/api/batch-mutations", methods=["POST"])
def api_batch_mutations():
    """Execute multiple create/update mutations atomically (single undo).

    Expects JSON:
    - description: Human-readable description for undo history
    - operations: Array of operation objects:
        - {action: "update", stable_key: "...", attributes: {...}}
        - {action: "create", target_file: "...", object_type: "...", attributes: {...}}
    """
    data = request.get_json() or {}
    description = data.get("description", "batch operation")
    operations = data.get("operations", [])

    if not operations:
        return jsonify({"error": "operations required"}), 400

    session_id = request.headers.get("X-Session-Id")
    success, error = ensure_shadow_lock(session_id)
    if not success:
        return error

    service = get_service()
    sm = get_shadow_manager()

    from .objects import _resolve_stable_key, _resolve_target_file

    # Pre-resolve all operations and collect files to snapshot
    files_to_snapshot = set()
    resolved_ops = []
    for op in operations:
        action = op.get("action")
        if action == "update":
            stable_key = _resolve_stable_key(op.get("stable_key", ""))
            found = service.find_object_by_stable_key(stable_key)
            if not found:
                continue
            _, obj = found
            files_to_snapshot.add(os.path.relpath(obj.source_file, sm._config_dir))
            resolved_ops.append({"action": "update", "stable_key": stable_key, "attributes": op["attributes"]})
        elif action == "create":
            target_file = _resolve_target_file(op.get("target_file", ""))
            files_to_snapshot.add(os.path.relpath(target_file, sm._config_dir))
            resolved_ops.append({
                "action": "create",
                "target_file": target_file,
                "object_type": op["object_type"],
                "attributes": op["attributes"],
            })

    if not resolved_ops:
        return jsonify({"success": True, "completed": 0, "errors": []})

    # Single snapshot for all operations
    sm.snapshot_files(list(files_to_snapshot), description)

    # Execute each operation sequentially
    completed = 0
    errors = []
    for op in resolved_ops:
        if op["action"] == "update":
            found = service.find_object_by_stable_key(op["stable_key"])
            if not found:
                errors.append(f"Object not found: {op['stable_key']}")
                continue
            _, obj = found
            result = service.update_object(
                obj.source_file, obj.line_number, op["attributes"], obj.object_type,
            )
        elif op["action"] == "create":
            result = service.create_object(
                op["target_file"], op["object_type"], op["attributes"],
            )
        else:
            continue

        if result.success:
            completed += 1
        else:
            errors.append(result.error)

    return jsonify({
        "success": True,
        "completed": completed,
        "errors": errors if errors else None,
    })
```

**Step 2: Run tests**

Run: `python3 -m pytest tests/ -v`
Expected: All existing tests PASS (no test changes needed — this is a new endpoint)

**Step 3: Commit**

```bash
git add routes/bulk_ops.py
git commit -m "feat: add /api/batch-mutations endpoint for atomic bulk operations"
```

---

### Task 2: Migrate `applyMove()` to use `/api/move-objects`

**Files:**
- Modify: `static/js/explorer/context-menu.js` (lines 452-495)

**Step 1: Replace the loop**

Change `applyMove()` to build a `stable_keys` array and call `/api/move-objects` once:

```javascript
export async function applyMove() {
    let targetFile = document.getElementById('moveTarget').value;

    if (targetFile === '__new__') {
        const newFileName = document.getElementById('newFileName').value.trim();
        if (!newFileName) {
            showToast('Please enter a filename', 'warning');
            return;
        }
        const firstObj = state.allObjects.find(o => isSelectedByIndex(o.global_index));
        if (firstObj) {
            const dir = firstObj.source_file.substring(0, firstObj.source_file.lastIndexOf('/'));
            targetFile = dir + '/' + (newFileName.endsWith('.cfg') ? newFileName : newFileName + '.cfg');
        } else {
            targetFile = state.configPath + '/' + (newFileName.endsWith('.cfg') ? newFileName : newFileName + '.cfg');
        }
    }

    const stableKeys = [];
    for (const idx of getSelectedIndices()) {
        const obj = state.allObjects.find(o => o.global_index === idx);
        if (!obj || obj.source_file === targetFile) {continue;}
        stableKeys.push(getObjectKey(obj));
    }

    if (stableKeys.length === 0) {
        showToast('No objects to move', 'info');
        return;
    }

    const result = await ApiClient.post('/api/move-objects', {
        stable_keys: stableKeys,
        target_file: targetFile
    }, { silent: true });

    await afterFrontendMutation();
    closeDialog();

    if (result.success && result.data?.moved > 0) {
        showToast(`Moved ${result.data.moved} object(s) to ${targetFile.split('/').pop()}`, 'success');
    } else {
        showToast(result.error || result.data?.error || 'No objects moved', result.success ? 'info' : 'error');
    }
}
```

**Step 2: Manual test** — Select multiple objects, right-click → Move, confirm. Verify single Ctrl+Z undoes all moves.

**Step 3: Commit**

```bash
git add static/js/explorer/context-menu.js
git commit -m "refactor: applyMove uses batch endpoint for single undo"
```

---

### Task 3: Migrate `applyBulkAttribute()` to batch endpoint

**Files:**
- Modify: `static/js/explorer/context-menu.js` (lines 615-662)

**Step 1: Replace the loop**

Compute all update operations locally, then send as a single batch:

```javascript
export async function applyBulkAttribute() {
    const name = document.getElementById('bulkAttrName').value.trim();
    const value = document.getElementById('bulkAttrValue').value;
    const action = document.getElementById('bulkAttrAction').value;

    if (!name) {
        showToast('Please enter an attribute name', 'warning');
        return;
    }

    const operations = [];
    for (const idx of getSelectedIndices()) {
        const obj = state.allObjects.find(o => o.global_index === idx);
        if (!obj) {continue;}

        const newAttrs = {...obj.attributes};
        let madeChange = false;

        if (action === 'remove') {
            if (name in newAttrs) {
                delete newAttrs[name];
                madeChange = true;
            }
        } else if (newAttrs[name] !== value) {
            newAttrs[name] = value;
            madeChange = true;
        }

        if (madeChange) {
            operations.push({
                action: 'update',
                stable_key: getObjectKey(obj),
                attributes: newAttrs
            });
        }
    }

    if (operations.length === 0) {
        await afterFrontendMutation();
        closeDialog();
        showToast('No changes made', 'info');
        return;
    }

    const actionText = action === 'remove' ? 'remove' : 'set';
    await ApiClient.post('/api/batch-mutations', {
        description: `bulk ${actionText} ${name} on ${operations.length} objects`,
        operations
    }, { silent: true });

    await afterFrontendMutation();
    closeDialog();
    showToast(`Attribute ${action === 'remove' ? 'removed from' : 'set on'} ${operations.length} object(s)`, 'success');
}
```

**Step 2: Commit**

```bash
git add static/js/explorer/context-menu.js
git commit -m "refactor: applyBulkAttribute uses batch endpoint for single undo"
```

---

### Task 4: Migrate `addToGroup()` to batch endpoint

**Files:**
- Modify: `static/js/explorer/context-menu.js` (lines 805-852)

**Step 1: Replace the loop**

```javascript
export async function addToGroup(groupName) {
    hideContextMenu();
    closeDialog();

    if (!groupName) {
        showToast('Invalid group name', 'error');
        return;
    }

    const eligibleObjects = Array.from(getSelectedIndices())
        .map(i => state.allObjects.find(o => o.global_index === i))
        .filter(o => o && getGroupAttrMap()[o.object_type]);

    if (eligibleObjects.length === 0) {
        showToast('Please select hosts, services, or contacts', 'warning');
        return;
    }

    const operations = [];
    for (const obj of eligibleObjects) {
        const groupAttr = getGroupAttrMap()[obj.object_type];
        const currentGroups = (obj.attributes[groupAttr] || '').split(',').map(g => g.trim()).filter(g => g);

        if (!currentGroups.includes(groupName)) {
            currentGroups.push(groupName);
            operations.push({
                action: 'update',
                stable_key: getObjectKey(obj),
                attributes: {...obj.attributes, [groupAttr]: currentGroups.join(',')}
            });
        }
    }

    if (operations.length === 0) {
        showToast(`Selected objects already belong to "${groupName}"`, 'info');
        return;
    }

    await ApiClient.post('/api/batch-mutations', {
        description: `add group ${groupName} to ${operations.length} objects`,
        operations
    }, { silent: true });

    await afterFrontendMutation();

    if (state.editedObject) {
        showCenterPaneObject(state.editedObject);
    }

    showToast(`Added "${groupName}" to ${operations.length} object(s)`, 'success');
}
```

**Step 2: Commit**

```bash
git add static/js/explorer/context-menu.js
git commit -m "refactor: addToGroup uses batch endpoint for single undo"
```

---

### Task 5: Migrate `updateReferencesViaApi()` + `applyRename()` to batch endpoint

**Files:**
- Modify: `static/js/explorer/context-menu.js` (lines 66-96 and 501-555)

This is the most involved change. Currently `applyRename()` does two steps:
1. Update the object name (1 API call → 1 snapshot)
2. `updateReferencesViaApi()` updates N references (N API calls → N snapshots)

**Step 1: Change `updateReferencesViaApi` to return operations instead of executing them**

Rename to `buildReferenceUpdateOps` (internal helper, no longer exported):

```javascript
function buildReferenceUpdateOps(oldName, newName, excludeIndex) {
    const deps = findDependencies(oldName);
    const operations = [];

    for (const dep of deps) {
        const obj = dep.object;
        if (obj.global_index === excludeIndex) {continue;}

        const editedAttrs = {...obj.attributes};
        let changed = false;

        for (const fieldName of dep.fields) {
            const currentValue = editedAttrs[fieldName] || '';
            const updatedValue = updateReferenceValue(currentValue, oldName, newName);
            if (updatedValue !== currentValue) {
                editedAttrs[fieldName] = updatedValue;
                changed = true;
            }
        }

        if (changed) {
            operations.push({
                action: 'update',
                stable_key: getObjectKey(obj),
                attributes: editedAttrs
            });
        }
    }

    return operations;
}
```

**Step 2: Update `applyRename()` to batch rename + reference updates**

```javascript
export async function applyRename() {
    const newName = document.getElementById('renameValue').value.trim();
    if (!newName) {
        showToast('Please enter a name', 'warning');
        return;
    }

    const obj = state.allObjects.find(o => o.global_index === state.contextTarget);
    if (!obj) {
        closeDialog();
        return;
    }

    const nameField = getNameFieldForObject(obj);
    const currentName = obj.attributes[nameField] || '';

    if (newName === currentName) {
        closeDialog();
        showToast('Name unchanged', 'info');
        return;
    }

    // Build all operations: rename + reference updates
    const operations = [{
        action: 'update',
        stable_key: getObjectKey(obj),
        attributes: {...obj.attributes, [nameField]: newName}
    }];

    const updateRefsCheckbox = document.getElementById('renameUpdateRefs');
    const shouldUpdateRefs = updateRefsCheckbox ? updateRefsCheckbox.checked : false;
    if (shouldUpdateRefs) {
        operations.push(...buildReferenceUpdateOps(currentName, newName, state.contextTarget));
    }

    const result = await ApiClient.post('/api/batch-mutations', {
        description: `rename ${obj.object_type} ${currentName} to ${newName}`,
        operations
    });

    if (!result.success) {
        showToast(result.error || 'Failed to rename', 'error');
        return;
    }

    state.healthCheckData = null;
    await afterFrontendMutation();
    closeDialog();

    if (state.editedObject && state.editedObject.global_index === state.contextTarget) {
        showCenterPaneObject(obj);
    } else if (state.editedObject) {
        loadImpactAndRelationships(state.editedObject);
    }

    const refCount = operations.length - 1;
    const refMsg = refCount > 0 ? ` Updated ${refCount} reference${refCount !== 1 ? 's' : ''}.` : '';
    showToast(`Renamed successfully.${refMsg}`, 'success');
}
```

**Step 3: Check if `updateReferencesViaApi` is exported and used elsewhere**

It's exported but only called from `applyRename()` (line 540). The new `buildReferenceUpdateOps` can be a module-private function (no `export`). Remove the old `export async function updateReferencesViaApi` and replace with the non-exported `function buildReferenceUpdateOps`.

**Step 4: Commit**

```bash
git add static/js/explorer/context-menu.js
git commit -m "refactor: applyRename batches rename + reference updates for single undo"
```

---

### Task 6: Migrate `applyClone()` to batch endpoint

**Files:**
- Modify: `static/js/explorer/context-menu.js` (lines 558-602)

**Step 1: Replace the loop**

```javascript
export async function applyClone() {
    const newNameInput = document.getElementById('cloneNewName');
    const suffixInput = document.getElementById('cloneSuffix');
    const targetFileSelect = document.getElementById('cloneTargetFile');
    const isSingleClone = newNameInput !== null;
    const suffix = suffixInput ? (suffixInput.value || '-copy') : '-copy';

    if (isSingleClone && !newNameInput.value.trim()) {
        showToast('Please enter a name', 'warning');
        return;
    }

    const operations = [];
    for (const idx of getSelectedIndices()) {
        const obj = state.allObjects.find(o => o.global_index === idx);
        if (!obj) {continue;}

        const nameField = getNameFieldForObject(obj);
        const currentName = obj.attributes[nameField] || obj.name || obj.display_name || 'unnamed';
        const newName = isSingleClone ? newNameInput.value.trim() : currentName + suffix;

        const cloneTargetFile = (targetFileSelect && targetFileSelect.value) || obj.source_file;
        operations.push({
            action: 'create',
            target_file: cloneTargetFile,
            object_type: obj.object_type,
            attributes: {...obj.attributes, [nameField]: newName}
        });
    }

    if (operations.length === 0) {return;}

    const result = await ApiClient.post('/api/batch-mutations', {
        description: `clone ${operations.length} objects`,
        operations
    }, { silent: true });

    if (!result.success) {
        showToast(result.error || 'Clone failed', 'error');
        if (isSingleClone) {return;}
    }

    await afterFrontendMutation();
    closeDialog();
    showToast(`Cloned ${result.data?.completed || operations.length} object(s)`, 'success');
}
```

**Step 2: Commit**

```bash
git add static/js/explorer/context-menu.js
git commit -m "refactor: applyClone uses batch endpoint for single undo"
```

---

### Task 7: Migrate `executeBatchCreate()` to batch endpoint

**Files:**
- Modify: `static/js/explorer/analysis-issues.js` (lines 359-396)

**Step 1: Replace the loop**

```javascript
export async function executeBatchCreate(groups, targetFile) {
    closeDialog();

    const operations = groups.map(group => {
        const issue = group.firstIssue;
        const isTemplate = issue.type === 'missing_template';
        const objectType = isTemplate ? issue.object_type : group.objectType;
        return {
            action: 'create',
            target_file: targetFile,
            object_type: objectType,
            attributes: buildDefaultAttributes(objectType, group.missingName, isTemplate)
        };
    });

    const result = await ApiClient.post('/api/batch-mutations', {
        description: `create ${operations.length} missing objects`,
        operations
    }, { silent: true });

    state.healthCheckData = null;
    await afterFrontendMutation();
    loadIssues();

    const completed = result.data?.completed || 0;
    const errors = result.data?.errors || [];
    if (errors.length === 0) {
        showToast(`Created ${completed} new object${completed !== 1 ? 's' : ''}`, 'success');
    } else {
        showToast(`Created ${completed} objects, ${errors.length} failed`, 'warning');
    }
}
```

**Step 2: Commit**

```bash
git add static/js/explorer/analysis-issues.js
git commit -m "refactor: executeBatchCreate uses batch endpoint for single undo"
```

---

### Task 8: Migrate template consolidation to batch endpoint

**Files:**
- Modify: `static/js/explorer/analysis-suggestions.js` (lines 331-395, inside `showCreateTemplateDialog` callback)

**Step 1: Replace the create + update loop**

In the dialog callback, replace the separate create call + update loop with a single batch:

```javascript
    // Build batch: create template + update objects
    const operations = [{
        action: 'create',
        target_file: targetFile,
        object_type: suggestion.type,
        attributes: templateAttrs
    }];

    if (updateObjects) {
        for (const obj of suggestion.objects) {
            const newAttrs = { ...obj.attributes };
            newAttrs.use = name;
            for (const key of Object.keys(suggestion.attributes)) {
                delete newAttrs[key];
            }
            operations.push({
                action: 'update',
                stable_key: getObjectKey(obj),
                attributes: newAttrs
            });
        }
    }

    const result = await ApiClient.post('/api/batch-mutations', {
        description: `consolidate template ${name}`,
        operations
    }, { silent: true });

    if (!result.success) {
        showToast(`Failed: ${result.error}`, 'error');
        return;
    }

    closeDialog();
    await afterFrontendMutation();

    const msg = updateObjects
        ? `Created template "${name}" and updated ${suggestion.count} objects`
        : `Created template "${name}"`;
    showToast(msg, 'success');
```

**Step 2: Commit**

```bash
git add static/js/explorer/analysis-suggestions.js
git commit -m "refactor: template consolidation uses batch endpoint for single undo"
```

---

### Task 9: Final verification

**Step 1:** Run full test suite: `python3 -m pytest tests/ -v`

**Step 2:** Manual smoke test each operation:
- Bulk move → single Ctrl+Z undoes all
- Bulk attribute set → single Ctrl+Z
- Add to group → single Ctrl+Z
- Rename with references → single Ctrl+Z undoes rename + all reference updates
- Bulk clone → single Ctrl+Z
- Batch create missing objects → single Ctrl+Z
- Template consolidation → single Ctrl+Z undoes template creation + object updates
