# Fix Reference Changes in Commit Dialog

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix two bugs in the commit dialog's "fix references" feature: (1) reference count mismatch between Impact section and commit menu, and (2) reference changes shown as flat list instead of inline diffs.

**Architecture:** The backend `analyze-references` endpoint will be rewritten to use the same broad scan as `update_references()` (checking all attributes of all objects, not just REFERENCE_FIELDS). It will return per-reference diff data (source_file, object_type, object_name, field, old_value, new_value). The frontend will inject reference changes into the existing file-based diff view as synthetic modifications, eliminating the separate flat-list section entirely.

**Tech Stack:** Python/Flask backend, vanilla JavaScript frontend

---

### Task 1: Fix backend `analyze-references` to find all direct references

**Files:**
- Modify: `routes/staging.py:1689-1756` (the `api_staging_analyze_references` function)

**Step 1: Write the failing test**

Create a test that verifies `analyze-references` finds references across all attribute fields (not just REFERENCE_FIELDS). The test sets up a host rename where the old name appears in a service's `host_name` field and also in a hostdependency's `dependent_host_name` field.

Add to `tests/test_staging_integration.py`:

```python
class TestAnalyzeReferences:
    """Tests for the analyze-references endpoint."""

    def test_analyze_references_finds_all_direct_refs(self, client, app):
        """analyze-references should find refs in all attribute fields, not just REFERENCE_FIELDS."""
        # Create config with host + service + hostdependency referencing the host
        with app.app_context():
            config_path = Path(get_config_path())
            (config_path / "hosts.cfg").write_text("""
define host {
    host_name       web-server-01
    alias           Web Server
    address         10.0.0.1
}

define host {
    host_name       db-server-01
    alias           DB Server
    address         10.0.0.2
}
""")
            (config_path / "services.cfg").write_text("""
define service {
    host_name               web-server-01
    service_description     HTTP
    check_command           check_http
}

define service {
    host_name               web-server-01,db-server-01
    service_description     PING
    check_command           check_ping
}
""")
            (config_path / "dependencies.cfg").write_text("""
define hostdependency {
    host_name               db-server-01
    dependent_host_name     web-server-01
}
""")
            # Reload parser
            service = app.extensions["service"]
            service.reload()

        session_id = "test-session"
        headers = {"X-Session-Id": session_id}

        # Get objects to find web-server-01's global_index
        resp = client.get("/api/objects")
        objects = resp.json
        host_obj = next(o for o in objects
                        if o["attributes"].get("host_name") == "web-server-01")

        # Stage a rename: web-server-01 -> web-server-renamed
        edit_data = {
            "sessionId": session_id,
            "pendingEdits": {
                str(host_obj["global_index"]): {
                    "object": host_obj,
                    "original": host_obj["attributes"],
                    "edited": {**host_obj["attributes"], "host_name": "web-server-renamed"},
                },
            },
        }
        resp = client.post("/api/staging",
                           data=json.dumps(edit_data),
                           content_type="application/json",
                           headers=headers)
        assert resp.status_code == 200

        # Call analyze-references
        resp = client.get("/api/staging/analyze-references", headers=headers)
        assert resp.status_code == 200
        data = resp.json

        assert data["hasNameChanges"] is True
        assert len(data["nameChanges"]) == 1

        change = data["nameChanges"][0]
        assert change["oldName"] == "web-server-01"
        assert change["newName"] == "web-server-renamed"

        # Should find 3 references:
        # 1. SERVICE HTTP (host_name = web-server-01)
        # 2. SERVICE PING (host_name = web-server-01,db-server-01)
        # 3. HOSTDEPENDENCY (dependent_host_name = web-server-01)
        assert change["referenceCount"] == 3
        assert data["totalReferences"] == 3

    def test_analyze_references_returns_diff_data(self, client, app):
        """analyze-references should return old/new values and source_file for each ref."""
        with app.app_context():
            config_path = Path(get_config_path())
            (config_path / "hosts.cfg").write_text("""
define host {
    host_name       myhost
    alias           My Host
    address         10.0.0.1
}
""")
            (config_path / "services.cfg").write_text("""
define service {
    host_name               myhost
    service_description     HTTP
    check_command           check_http
}
""")
            service = app.extensions["service"]
            service.reload()

        session_id = "test-session"
        headers = {"X-Session-Id": session_id}

        resp = client.get("/api/objects")
        objects = resp.json
        host_obj = next(o for o in objects
                        if o["attributes"].get("host_name") == "myhost")

        edit_data = {
            "sessionId": session_id,
            "pendingEdits": {
                str(host_obj["global_index"]): {
                    "object": host_obj,
                    "original": host_obj["attributes"],
                    "edited": {**host_obj["attributes"], "host_name": "myhost-renamed"},
                },
            },
        }
        client.post("/api/staging",
                     data=json.dumps(edit_data),
                     content_type="application/json",
                     headers=headers)

        resp = client.get("/api/staging/analyze-references", headers=headers)
        data = resp.json
        change = data["nameChanges"][0]

        # Each reference should have diff data
        ref = change["references"][0]
        assert "sourceFile" in ref
        assert "field" in ref
        assert "oldValue" in ref
        assert "newValue" in ref
        assert "objectType" in ref
        assert "objectName" in ref

        # Verify the old/new values show the substitution
        assert "myhost" in ref["oldValue"]
        assert "myhost-renamed" in ref["newValue"]
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_staging_integration.py::TestAnalyzeReferences -v`
Expected: FAIL — `referenceCount` is wrong (too few refs found), and `sourceFile`/`oldValue`/`newValue` fields missing from response.

**Step 3: Rewrite the `api_staging_analyze_references` function**

In `routes/staging.py`, replace the `api_staging_analyze_references` function (lines 1689-1756) with a version that scans all attributes (matching what `update_references()` does at apply time) and returns diff data:

```python
@bp.route("/api/staging/analyze-references", methods=["GET"])
def api_staging_analyze_references():
    """Analyze pending name changes and count affected references.

    Returns information about objects whose names are being changed,
    and how many references to those objects exist in the configuration.
    Uses the same broad scan as update_references() to ensure the count
    matches what will actually be updated at apply time.
    """
    sm = get_staging_manager()
    staging = sm.get_staging()

    if not staging:
        return jsonify({"nameChanges": [], "totalReferences": 0})

    service = get_service()
    objects = service.get_objects()
    pending_edits = staging.get("pendingEdits", {})
    name_changes = []
    total_references = 0

    for gi_str, edit_data in pending_edits.items():
        if not isinstance(edit_data, dict):
            continue
        try:
            global_index = int(gi_str)
        except (ValueError, TypeError):
            continue

        obj = service.find_object_by_index(global_index)
        if obj is None:
            continue
        original = edit_data.get("original", {})
        edited = edit_data.get("edited", {})

        # Check if name field changed
        name_field = NAME_FIELDS.get(obj.object_type, "name")
        if not name_field:
            continue

        old_name = original.get(name_field) or obj.attributes.get(name_field)
        new_name = edited.get(name_field)

        if old_name and new_name and old_name != new_name:
            # Scan all attributes of all objects (same logic as update_references)
            refs = []
            for ref_obj in objects:
                for field_name, value in ref_obj.attributes.items():
                    values = [v.strip() for v in value.split(",")]
                    if old_name in values:
                        new_values = [new_name if v == old_name else v for v in values]
                        refs.append({
                            "objectType": ref_obj.object_type,
                            "objectName": ref_obj.get_display_name(),
                            "field": field_name,
                            "sourceFile": ref_obj.source_file,
                            "oldValue": value,
                            "newValue": ",".join(new_values),
                        })

            ref_count = len(refs)
            total_references += ref_count

            name_changes.append({
                "globalIndex": global_index,
                "objectType": obj.object_type,
                "oldName": old_name,
                "newName": new_name,
                "referenceCount": ref_count,
                "references": refs,
            })

    return jsonify({
        "nameChanges": name_changes,
        "totalReferences": total_references,
        "hasNameChanges": len(name_changes) > 0,
    })
```

Key changes:
- Scans ALL attributes of ALL objects (matching `update_references()` logic)
- No longer uses `parser.find_references()` which only checks REFERENCE_FIELDS
- Returns `sourceFile`, `oldValue`, `newValue` per reference for diff rendering
- Removes the `[:10]` limit — frontend needs all refs to render inline diffs

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_staging_integration.py::TestAnalyzeReferences -v`
Expected: PASS

**Step 5: Commit**

```bash
git add routes/staging.py tests/test_staging_integration.py
git commit -m "fix: analyze-references scans all attributes and returns diff data

Matches update_references() logic so commit menu count matches actual updates."
```

---

### Task 2: Integrate reference changes into file-based diff view (frontend)

**Files:**
- Modify: `static/js/commit-dialog.js` — `buildGlobalCommitDialogHtml`, `buildReferenceChangesSection`, `buildGlobalFileBasedChanges`

**Step 1: Modify `buildGlobalFileBasedChanges` to inject reference changes**

Add a new function `injectReferenceChanges` that takes the `refData` and `fileChanges` map and adds synthetic modifications for each reference. Then call it from `buildGlobalCommitDialogHtml`.

Replace the `buildReferenceChangesSection` function (lines 187-235) with:

```javascript
function buildReferenceChangesSection(refData) {
    // No longer used — reference changes are now shown inline in file diffs
    return '';
}
```

Add a new function after `buildReferenceChangesSection`:

```javascript
/**
 * Injects reference updates into the file-based changes map as synthetic modifications.
 * Each reference becomes a modification entry showing old_value -> new_value for the affected field.
 */
function injectReferenceChanges(fileChanges, refData, configPath) {
    if (!refData || !refData.nameChanges) return;

    for (const change of refData.nameChanges) {
        for (const ref of change.references) {
            const filePath = ref.sourceFile;
            if (!filePath) continue;

            const file = ensureFileChange(fileChanges, filePath, configPath);

            // Build original and updated attributes showing just the changed field
            const originalAttrs = {};
            originalAttrs[ref.field] = ref.oldValue;

            const finalAttrs = {};
            finalAttrs[ref.field] = ref.newValue;

            file.modifications.push({
                globalIndex: -1,  // Synthetic — no real global_index
                object: {
                    object_type: ref.objectType,
                    global_index: -1,
                    source_file: filePath,
                    line_number: 0,
                },
                originalAttrs,
                finalAttrs,
                lineNumber: 0,
                isReferenceUpdate: true,
                referenceMeta: {
                    objectName: ref.objectName,
                    renamedFrom: change.oldName,
                    renamedTo: change.newName,
                },
            });
        }
    }
}
```

**Step 2: Update `buildGlobalCommitDialogHtml` to inject references into file changes**

In `buildGlobalCommitDialogHtml` (line 95), after `buildGlobalFileBasedChanges` is called, inject reference changes:

Change line 95 from:
```javascript
    const fileChanges = buildGlobalFileBasedChanges(pendingEdits, stagedMoves, stagedCreations, stagedObjectDeletions, allObjects, configPath);
```

To:
```javascript
    const fileChanges = buildGlobalFileBasedChanges(pendingEdits, stagedMoves, stagedCreations, stagedObjectDeletions, allObjects, configPath);

    // Inject reference updates into file-based changes (when checkbox is checked)
    if (refData && refData.hasNameChanges) {
        injectReferenceChanges(fileChanges, refData, configPath);
    }
```

**Step 3: Remove the separate reference section from the HTML**

In `buildGlobalCommitDialogHtml`, remove line 144:
```javascript
        ${refData && refData.hasNameChanges ? buildReferenceChangesSection(refData) : ''}
```

Replace with just an empty string (remove the line).

**Step 4: Update `renderGlobalModifiedObject` to handle reference updates**

Reference modifications only have the changed field (not all attributes). Update `renderGlobalModifiedObject` to handle the `isReferenceUpdate` flag by showing a compact diff with a label.

In `renderGlobalFileDiff` (around line 1073-1076), where modifications are rendered, change:

```javascript
        } else if (item.isModification) {
            const mod = modificationMap.get(item.object.global_index);
            if (mod) {
                diffHtml += renderGlobalModifiedObject(mod.object, mod.originalAttrs, mod.finalAttrs);
            }
```

To:

```javascript
        } else if (item.isModification) {
            const mod = modificationMap.get(item.object.global_index);
            if (mod) {
                if (mod.isReferenceUpdate) {
                    diffHtml += renderReferenceUpdateDiff(mod);
                } else {
                    diffHtml += renderGlobalModifiedObject(mod.object, mod.originalAttrs, mod.finalAttrs);
                }
            }
```

Add a new function `renderReferenceUpdateDiff`:

```javascript
function renderReferenceUpdateDiff(mod) {
    const meta = mod.referenceMeta;
    const objType = mod.object.object_type;
    let html = `<div class="diff-line modify">  define ${escapeHtml(objType)} {</div>`;
    html += `<div class="diff-line context">      # ${escapeHtml(meta.objectName)} — ref update (${escapeHtml(meta.renamedFrom)} → ${escapeHtml(meta.renamedTo)})</div>`;

    const allKeys = [...new Set([...Object.keys(mod.originalAttrs), ...Object.keys(mod.finalAttrs)])].sort();
    allKeys.forEach(key => {
        const origVal = mod.originalAttrs[key];
        const newVal = mod.finalAttrs[key];
        if (origVal !== newVal) {
            html += `<div class="diff-line remove">-     ${escapeHtml(key.padEnd(30))} ${escapeHtml(origVal || '')}</div>`;
            html += `<div class="diff-line add">+     ${escapeHtml(key.padEnd(30))} ${escapeHtml(newVal || '')}</div>`;
        }
    });

    html += `<div class="diff-line modify">  }</div>`;
    return html;
}
```

**Step 5: Fix the modification lookup for reference updates**

The `modificationMap` in `renderGlobalFileDiff` uses `global_index` as key, but reference updates have `global_index: -1`. Multiple reference updates for the same file would collide on key `-1`. Change the data structure to handle this.

In `renderGlobalFileDiff`, replace the existing approach. Instead of using `modificationMap` keyed by global_index, render reference updates separately since they won't match existing objects.

The cleanest approach: reference modifications should be appended to `unifiedItems` as their own type. Change the approach:

In `renderGlobalFileDiff`, after building the `unifiedItems` from existing objects and additions (around line 990-998), add reference updates as separate items:

```javascript
    // Add reference updates as separate items (they don't correspond to existing objects in this file)
    modifications.filter(m => m.isReferenceUpdate).forEach(mod => {
        unifiedItems.push({
            type: 'referenceUpdate',
            sortKey: Infinity,  // Show at end of file
            modification: mod,
        });
    });
```

Then in the rendering loop (around line 1028-1081), add a case for `referenceUpdate`:

After the `item.isModification` block, before the `else` (context) block:

```javascript
        } else if (item.type === 'referenceUpdate') {
            diffHtml += renderReferenceUpdateDiff(item.modification);
```

And filter out reference updates from the `modificationIndices` and `modificationMap` so they don't interfere:

Change line 966-967 from:
```javascript
    const modificationIndices = new Set(modifications.map(m => m.object.global_index));
    const modificationMap = new Map(modifications.map(m => [m.object.global_index, m]));
```

To:
```javascript
    const regularMods = modifications.filter(m => !m.isReferenceUpdate);
    const modificationIndices = new Set(regularMods.map(m => m.object.global_index));
    const modificationMap = new Map(regularMods.map(m => [m.object.global_index, m]));
```

**Step 6: Update `updateGlobalContextLines` to pass refData**

In `updateGlobalContextLines` (line 1137), the function rebuilds the file changes when the context slider changes. It needs to also inject reference changes.

After the `buildGlobalFileBasedChanges` call on line 1168, add:

```javascript
            if (baseState.referenceData && baseState.referenceData.hasNameChanges) {
                const updateRefsCheckbox = document.getElementById('globalUpdateReferences');
                if (updateRefsCheckbox && updateRefsCheckbox.checked) {
                    injectReferenceChanges(fileChanges, baseState.referenceData, configPath);
                }
            }
```

**Step 7: Update `toggleReferencePreview` to rebuild the diff**

Replace the `toggleReferencePreview` function (lines 180-185) to rebuild the entire file diff view when the checkbox is toggled, since reference changes are now inline:

```javascript
function toggleReferencePreview(checked) {
    // Rebuild the file changes view to include/exclude reference updates
    updateGlobalContextLines(
        baseState.commitContextLines > 9 ? 10 : baseState.commitContextLines
    );
}
```

**Step 8: Update the summary counts to include reference updates**

In `buildGlobalCommitDialogHtml`, the summary stats (lines 97-102) count modifications. When references are injected, they should be reflected. Since `injectReferenceChanges` adds to `modifications`, the existing count code will automatically include them. However, let's add a separate ref count badge.

After the modifyCount line (line 101), add:

```javascript
    let refCount = 0;
    fileChanges.forEach(fc => {
        refCount += fc.modifications.filter(m => m.isReferenceUpdate).length;
    });
```

Then in the summary HTML (around line 131), after the modified stat, add:

```javascript
                ${refCount > 0 ? `<div class="commit-stat refs"><span class="commit-stat-count">${refCount}</span> ref update${refCount !== 1 ? 's' : ''}</div>` : ''}
```

And subtract refCount from modifyCount so regular edits aren't inflated:

Change line 101 from:
```javascript
        modifyCount += fc.modifications.length;
```

To:
```javascript
        modifyCount += fc.modifications.filter(m => !m.isReferenceUpdate).length;
```

**Step 9: Manually test in browser**

1. Open the app, edit a host's `host_name`
2. Open commit dialog — verify the "Update references" checkbox is present
3. Verify reference changes appear inline within file diffs (not as a separate section)
4. Verify the diff shows `- host_name  old-name` / `+ host_name  new-name` format
5. Toggle the "Update references" checkbox — verify diffs appear/disappear
6. Verify the ref count in the summary header matches the inline entries

**Step 10: Commit**

```bash
git add static/js/commit-dialog.js
git commit -m "feat: show reference changes as inline diffs in commit dialog

Reference updates now appear grouped by file alongside other edits,
with proper before/after diff rendering instead of a flat list."
```

---

### Task 3: Clean up unused CSS

**Files:**
- Modify: `templates/base.html` — remove ref-changes CSS rules

**Step 1: Remove the CSS rules for the old reference section**

In `templates/base.html`, remove the CSS block for `.ref-changes-section`, `.ref-changes-title`, `.ref-changes-badge`, `.ref-changes-diff`, `.ref-changes-content`, `.ref-changes-hint`, and `.ref-changes-diff .ref-item` (approximately lines 2224-2261).

**Step 2: Add a CSS rule for the new ref stat badge**

Add after the existing `.commit-stat` rules:

```css
    .commit-stat.refs {
        color: var(--nbe-info);
    }
```

**Step 3: Commit**

```bash
git add templates/base.html
git commit -m "cleanup: remove unused ref-changes CSS, add ref stat style"
```

---

### Task 4: Run full test suite

**Step 1: Run all tests**

Run: `python3 -m pytest tests/ -v`
Expected: All tests pass.

**Step 2: Final manual verification**

1. Start the app: `python3 app.py`
2. Navigate to explorer, edit a host's name
3. Open commit dialog
4. Verify reference changes are inline in file diffs
5. Toggle checkbox, verify diffs update
6. Apply the changes — verify references are actually updated on disk
