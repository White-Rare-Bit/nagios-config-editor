# Stable Key Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate `pendingEdits` and `stagedObjectDeletions` from `global_index` to stable keys (`source_file|object_type|name`) for durable object identity across parser reloads.

**Architecture:** Clean break — bump staging schema version to 4, reject old-format files. JS data structures change key types (int → string). Python virtual tree and apply path resolve objects by stable key instead of array index. Secondary systems (orphanIndices, tabs, object-references API, health_checks) also migrate.

**Tech Stack:** Python/Flask backend, vanilla JS frontend (IIFE modules on `window.Explorer`), no JS test framework.

**Design doc:** `docs/plans/2026-03-02-stable-key-migration-design.md`

---

### Task 1: Fix `parse_stable_key` + bump schema version

**Files:**
- Modify: `staging_manager.py:31` (STAGING_SCHEMA_VERSION)
- Modify: `staging_manager.py:1420-1435` (parse_stable_key)
- Test: `tests/test_stable_keys.py`

**Step 1: Write the failing test**

In `tests/test_stable_keys.py`, add:

```python
def test_parse_stable_key_with_pipe_in_name():
    """parse_stable_key should handle names containing pipe characters."""
    from staging_manager import parse_stable_key
    result = parse_stable_key("servers/hosts.cfg|host|my|special|host")
    assert result is not None
    assert result["source_file"] == "servers/hosts.cfg"
    assert result["object_type"] == "host"
    assert result["name"] == "my|special|host"
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_stable_keys.py::test_parse_stable_key_with_pipe_in_name -v`
Expected: FAIL — current code requires exactly 3 parts

**Step 3: Fix `parse_stable_key`**

In `staging_manager.py`, change `parse_stable_key` (around line 1428):

```python
def parse_stable_key(key: str) -> dict[str, str] | None:
    parts = key.split("|")
    if len(parts) < 3:
        return None
    return {
        "source_file": parts[0],
        "object_type": parts[1],
        "name": "|".join(parts[2:]),
    }
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_stable_keys.py -v`
Expected: ALL PASS

**Step 5: Bump schema version**

In `staging_manager.py` line 31, change:

```python
STAGING_SCHEMA_VERSION = 4
```

**Step 6: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: ALL PASS

**Step 7: Commit**

```bash
git add staging_manager.py tests/test_stable_keys.py
git commit -m "fix: parse_stable_key handles pipe in name; bump schema to 4"
```

---

### Task 2: Migrate Python virtual tree builders

**Files:**
- Modify: `routes/staging.py:1622-1692` (three `_apply_staged_*_to_virtual` functions)
- Modify: `routes/staging.py:438-459` (delete `_enrich_deletion_identities`)
- Modify: `routes/staging.py:903-906` (remove call to `_enrich_deletion_identities`)
- Modify: `routes/staging.py:476-490` (`_get_existing_operation_keys`)
- Modify: `routes/staging.py:812-862` (comments and validation messages)
- Test: `tests/test_stable_keys.py`

**Context:** Virtual objects are dicts from `NagiosObject.to_dict()` with `display_name` and `name` fields. The stable key for a virtual object is built as `source_file|object_type|(display_name or name or "idx:N")`.

**Step 1: Write a test for virtual tree edit application by stable key**

In `tests/test_stable_keys.py`:

```python
def test_apply_staged_edits_by_stable_key(app):
    """Virtual tree should apply edits keyed by stable key."""
    with app.app_context():
        from routes.staging import _apply_staged_edits_to_virtual
        virtual_objects = [
            {"source_file": "hosts.cfg", "object_type": "host",
             "display_name": "webserver", "name": "webserver",
             "attributes": {"host_name": "webserver", "address": "1.1.1.1"},
             "global_index": 0, "_staged_status": None},
            {"source_file": "hosts.cfg", "object_type": "host",
             "display_name": "dbserver", "name": "dbserver",
             "attributes": {"host_name": "dbserver", "address": "2.2.2.2"},
             "global_index": 1, "_staged_status": None},
        ]
        pending_edits = {
            "hosts.cfg|host|dbserver": {
                "edited": {"address": "3.3.3.3"},
                "object": {"source_file": "hosts.cfg", "object_type": "host",
                           "display_name": "dbserver"}
            }
        }
        edited = _apply_staged_edits_to_virtual(virtual_objects, pending_edits)
        assert virtual_objects[1]["attributes"]["address"] == "3.3.3.3"
        assert virtual_objects[1]["_staged_status"] == "edited"
        assert virtual_objects[0]["attributes"]["address"] == "1.1.1.1"
        assert 1 in edited


def test_apply_staged_deletions_by_stable_key(app):
    """Virtual tree should apply deletions keyed by stable key."""
    with app.app_context():
        from routes.staging import _apply_staged_deletions_to_virtual
        virtual_objects = [
            {"source_file": "hosts.cfg", "object_type": "host",
             "display_name": "webserver", "name": "webserver",
             "attributes": {"host_name": "webserver"},
             "global_index": 0, "_staged_status": None},
            {"source_file": "hosts.cfg", "object_type": "host",
             "display_name": "dbserver", "name": "dbserver",
             "attributes": {"host_name": "dbserver"},
             "global_index": 1, "_staged_status": None},
        ]
        staged_deletions = ["hosts.cfg|host|dbserver"]
        deleted = _apply_staged_deletions_to_virtual(virtual_objects, staged_deletions)
        assert virtual_objects[1]["_staged_status"] == "deleted"
        assert virtual_objects[0]["_staged_status"] is None
        assert 1 in deleted
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_stable_keys.py::test_apply_staged_edits_by_stable_key tests/test_stable_keys.py::test_apply_staged_deletions_by_stable_key -v`
Expected: FAIL

**Step 3: Add helper function `_build_stable_key_index`**

In `routes/staging.py`, add before `_apply_staged_edits_to_virtual`:

```python
def _build_stable_key_index(virtual_objects):
    """Build a stable_key -> list_index map from virtual object dicts.

    Uses the same name resolution as StableKey.build() in JS:
    display_name ?? name ?? "idx:{global_index}"
    """
    index_map = {}
    for i, obj in enumerate(virtual_objects):
        name = obj.get("display_name") or obj.get("name") or f"idx:{obj.get('global_index', i)}"
        key = f"{obj['source_file']}|{obj['object_type']}|{name}"
        index_map[key] = i
    return index_map
```

**Step 4: Rewrite `_apply_staged_edits_to_virtual`**

Replace the function at lines 1622-1645:

```python
def _apply_staged_edits_to_virtual(virtual_objects, pending_edits):
    """Apply pending edits to virtual objects in place.

    Args:
        virtual_objects: List of virtual object dicts (modified in place)
        pending_edits: Dict {stableKey: edit_data} from staging

    Returns:
        Set of edited global indices

    """
    key_index = _build_stable_key_index(virtual_objects)
    edited_indices = set()
    for stable_key, edit_data in pending_edits.items():
        if not isinstance(edit_data, dict):
            continue
        idx = key_index.get(stable_key)
        if idx is not None:
            edited_attrs = edit_data.get("edited", {})
            if edited_attrs:
                virtual_objects[idx]["attributes"].update(edited_attrs)
                virtual_objects[idx]["_staged_status"] = "edited"
                edited_indices.add(idx)
    return edited_indices
```

**Step 5: Rewrite `_apply_staged_deletions_to_virtual`**

Replace the function at lines 1648-1666:

```python
def _apply_staged_deletions_to_virtual(virtual_objects, staged_deletions):
    """Mark objects for deletion in virtual objects list.

    Args:
        virtual_objects: List of virtual object dicts (modified in place)
        staged_deletions: List of stable key strings from staging

    Returns:
        Set of deleted global indices

    """
    key_index = _build_stable_key_index(virtual_objects)
    deleted_indices = set()
    for stable_key in staged_deletions:
        if not isinstance(stable_key, str):
            continue
        idx = key_index.get(stable_key)
        if idx is not None:
            virtual_objects[idx]["_staged_status"] = "deleted"
            deleted_indices.add(idx)
    return deleted_indices
```

**Step 6: Rewrite `_apply_staged_moves_to_virtual`**

Replace the function at lines 1669-1692:

```python
def _apply_staged_moves_to_virtual(virtual_objects, staged_moves):
    """Mark objects for move in virtual objects list.

    Args:
        virtual_objects: List of virtual object dicts (modified in place)
        staged_moves: Dict {stableKey: move_data} from staging

    """
    key_index = _build_stable_key_index(virtual_objects)
    for stable_key, move_data in staged_moves.items():
        if not isinstance(move_data, dict):
            continue
        target_file = move_data.get("targetFile")
        idx = key_index.get(stable_key)
        if idx is not None:
            virtual_objects[idx]["_staged_status"] = "moved"
            virtual_objects[idx]["_staged_target_file"] = target_file
```

**Step 7: Delete `_enrich_deletion_identities` and its call**

Remove the function at lines 438-459. Remove the call at lines 903-906:

```python
    # Resolve deletion indices to stable identities while indices are valid.
    # Preserves existing identities so they survive partial-apply retries.
    if data.get("stagedObjectDeletions"):
        _enrich_deletion_identities(data)
```

Also remove its import of `get_object_name` if no longer needed.

**Step 8: Update `_get_existing_operation_keys` (lines 484-489)**

Change the deletion key extraction from int to string:

```python
    deletion_keys = set(str(d) for d in existing.get("stagedObjectDeletions", []))
```

**Step 9: Update comments and validation message**

In `_validate_staging_format` (line 826):
```python
        return "pendingEdits must be a dict {stableKey: entry}"
```

Update wire format comments (lines 850-854):
```python
    #   pendingEdits: dict[str, object]   — key is stable key (source_file|type|name)
    #   stagedMoves: dict[str, object]    — key is stable key
    #   stagedCreations: list[object]
    #   stagedObjectDeletions: list[str]  — stable key values
```

**Step 10: Run tests**

Run: `python3 -m pytest tests/ -v`
Expected: ALL PASS

**Step 11: Commit**

```bash
git add routes/staging.py tests/test_stable_keys.py
git commit -m "refactor: virtual tree builders use stable keys instead of global_index"
```

---

### Task 3: Migrate `_build_composite_actions` in apply path

**Files:**
- Modify: `nagios_service.py:192-238` (pendingEdits + stagedObjectDeletions indexing)
- Modify: `nagios_service.py:280-291` (delete action creation)
- Modify: `nagios_service.py:340-356` (edit action + sort)
- Test: `tests/test_reorder.py` (existing apply tests)

**Step 1: Write a test for composite actions with stable-key-keyed edits**

In `tests/test_stable_keys.py`:

```python
def test_build_composite_actions_with_stable_key_edits(app):
    """_build_composite_actions should accept stable-key-keyed pendingEdits."""
    with app.app_context():
        from routes.helpers import get_service
        service = get_service()
        objects = service.get_objects()
        if not objects:
            pytest.skip("No objects in sample config")

        obj = objects[0]
        from staging_manager import generate_stable_key_for_object
        key = generate_stable_key_for_object(obj)

        staging_data = {
            "pendingEdits": {
                key: {
                    "object": {
                        "source_file": obj.source_file,
                        "object_type": obj.object_type,
                        "display_name": obj.get_display_name(),
                    },
                    "original": dict(obj.attributes),
                    "edited": {**obj.attributes, "alias": "test_alias"},
                }
            },
            "stagedMoves": {},
            "stagedObjectDeletions": [],
            "stagedCreations": [],
        }
        actions = service._build_composite_actions(staging_data)
        assert len(actions) == 1
        assert actions[0].action_type == "edit"
        assert actions[0].final_attrs.get("alias") == "test_alias"


def test_build_composite_actions_with_stable_key_deletions(app):
    """_build_composite_actions should accept stable-key stagedObjectDeletions."""
    with app.app_context():
        from routes.helpers import get_service
        service = get_service()
        objects = service.get_objects()
        if not objects:
            pytest.skip("No objects in sample config")

        obj = objects[0]
        from staging_manager import generate_stable_key_for_object
        key = generate_stable_key_for_object(obj)

        staging_data = {
            "pendingEdits": {},
            "stagedMoves": {},
            "stagedObjectDeletions": [key],
            "stagedCreations": [],
        }
        actions = service._build_composite_actions(staging_data)
        assert len(actions) == 1
        assert actions[0].action_type == "delete"
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_stable_keys.py::test_build_composite_actions_with_stable_key_edits tests/test_stable_keys.py::test_build_composite_actions_with_stable_key_deletions -v`
Expected: FAIL — current code expects integer keys

**Step 3: Rewrite the pendingEdits indexing loop (lines 192-204)**

```python
        # Index pendingEdits by normalized stable key
        for stable_key, entry in staging_data.get("pendingEdits", {}).items():
            if not isinstance(entry, dict):
                continue
            parsed = parse_stable_key(stable_key)
            if parsed:
                norm_key = f"{os.path.realpath(parsed['source_file'])}|{parsed['object_type']}|{parsed['name']}"
                edits_by_key[norm_key] = {"entry": entry}
```

**Step 4: Rewrite the stagedObjectDeletions indexing loop (lines 216-238)**

```python
        # Index stagedObjectDeletions by normalized stable key
        for deletion_key in staging_data.get("stagedObjectDeletions", []):
            if not isinstance(deletion_key, str):
                continue
            parsed = parse_stable_key(deletion_key)
            if not parsed:
                continue
            norm_key = f"{os.path.realpath(parsed['source_file'])}|{parsed['object_type']}|{parsed['name']}"
            deletes_by_key[norm_key] = {}
```

**Step 5: Update delete action creation (around line 282-291)**

Remove the `global_index` from the delete action:

```python
            if has_delete:
                delete_actions.append(
                    CompositeAction(
                        action_type="delete",
                        stable_key=key,
                        object_type=obj_type,
                        object_name=obj_name,
                        source_file=source_file,
                    )
                )
```

**Step 6: Update edit action creation (around line 340-353)**

Remove `global_index` from edit:

```python
            elif has_edit:
                edit_info = edits_by_key[key]
                final_attrs = edit_info["entry"].get("edited", {})
                modify_actions.append(
                    CompositeAction(
                        action_type="edit",
                        stable_key=key,
                        object_type=obj_type,
                        object_name=obj_name,
                        source_file=source_file,
                        final_attrs=final_attrs,
                    )
                )
```

**Step 7: Fix delete sort (line 356)**

The sort previously used `global_index` as a proxy for line order. Use `_find_by_identity` to get actual line numbers:

```python
        # Sort deletes by reverse line order within same file
        def _delete_sort_key(action):
            obj = self._find_by_identity(action.source_file, action.object_type, action.object_name)
            line = obj.line_number if obj else 0
            return (action.source_file or "", -line)
        delete_actions.sort(key=_delete_sort_key)
```

**Step 8: Run tests**

Run: `python3 -m pytest tests/ -v`
Expected: ALL PASS (including existing `test_reorder.py` apply tests)

**Step 9: Commit**

```bash
git add nagios_service.py tests/test_stable_keys.py
git commit -m "refactor: _build_composite_actions accepts stable-key-keyed staging data"
```

---

### Task 4: Migrate Python undo handlers + `stage_bulk_rename` + `bulk_ops.py`

**Files:**
- Modify: `staging_manager.py:1293-1301` (`stage_bulk_rename`)
- Modify: `staging_manager.py:1551-1556` (`_undo_edit`)
- Modify: `staging_manager.py:1559-1564` (`_undo_move`)
- Modify: `staging_manager.py:1578-1588` (`_undo_deletion`)
- Modify: `staging_manager.py:1599-1610` (`_undo_bulk_move`)
- Modify: `staging_manager.py:1613-1624` (`_undo_bulk_edit`)
- Modify: `staging_manager.py:1641-1654` (`_undo_bulk_deletion`)
- Modify: `routes/bulk_ops.py:258-311` (rename entries)

**Step 1: Update `stage_bulk_rename` (lines 1293-1301)**

Change key from `globalIndex` to `stableKey`:

```python
        for entry in renames:
            key = entry["stableKey"]
            pending_edits[key] = {
                "stableKey": key,
                "object": entry["object"],
                "original": entry["originalAttrs"],
                "edited": entry["editedAttrs"],
            }
            undo_items.append({"key": key, "object": entry["object"]})
```

**Step 2: Update `_undo_edit` (line 1553)**

Remove `globalIndex` fallback:

```python
def _undo_edit(staging, action_data):
    """Remove pending edit."""
    edit_key = str(action_data.get("key", ""))
    pending_edits = staging.get("pendingEdits", {})
    staging["pendingEdits"] = _filter_staged_entries(pending_edits, edit_key)
    return f"Unstaged edit: {action_data.get('object', {}).get('name', 'unknown')}"
```

**Step 3: Update `_undo_move` (line 1561)**

```python
def _undo_move(staging, action_data):
    """Remove staged move."""
    move_key = str(action_data.get("key", ""))
    staged_moves = staging.get("stagedMoves", {})
    staging["stagedMoves"] = _filter_staged_entries(staged_moves, move_key)
    return f"Unstaged move: {action_data.get('object', {}).get('name', 'unknown')}"
```

**Step 4: Update `_undo_deletion` (lines 1578-1588)**

Replace integer filtering with string comparison:

```python
def _undo_deletion(staging, action_data):
    """Remove staged deletion."""
    deletion_key = str(action_data.get("key", ""))
    staged_deletions = staging.get("stagedObjectDeletions", [])
    staging["stagedObjectDeletions"] = [d for d in staged_deletions if d != deletion_key]
    return f"Unstaged deletion: {action_data.get('deletion', {}).get('name', 'unknown')}"
```

**Step 5: Update `_undo_bulk_move` (line 1604)**

```python
        move_key = str(item.get("key", ""))
```

**Step 6: Update `_undo_bulk_edit` (line 1618)**

```python
        edit_key = str(item.get("key", ""))
```

**Step 7: Update `_undo_bulk_deletion` (lines 1647-1649)**

Replace integer set with string set:

```python
    keys_to_remove = set()
    for item in items:
        deletion_key = str(item.get("key", ""))
        if deletion_key:
            keys_to_remove.add(deletion_key)
    staged_deletions = staging.get("stagedObjectDeletions", [])
    staging["stagedObjectDeletions"] = [d for d in staged_deletions if d not in keys_to_remove]
```

Remove the `import contextlib` if it was only used for the `suppress` in this function.

**Step 8: Update `routes/bulk_ops.py` (lines 258-311)**

Add `stableKey` to rename entries, use it for dedup. Add import at top:

```python
from staging_manager import generate_stable_key_for_object
```

Change line 266-271:
```python
        renames.append({
            "stableKey": generate_stable_key_for_object(obj),
            "object": obj.to_dict(),
            "originalAttrs": {name_field: old_name},
            "editedAttrs": {name_field: new_name},
        })
```

Change line 299 (dedup check):
```python
                existing = next((r for r in renames if r["stableKey"] == generate_stable_key_for_object(obj)), None)
```

Change lines 306-311 (ref-edit append):
```python
                    renames.append({
                        "stableKey": generate_stable_key_for_object(obj),
                        "object": obj.to_dict(),
                        "originalAttrs": {f: obj.attributes[f] for f in ref_edits},
                        "editedAttrs": ref_edits,
                    })
```

**Step 9: Run tests**

Run: `python3 -m pytest tests/ -v`
Expected: ALL PASS

**Step 10: Commit**

```bash
git add staging_manager.py routes/bulk_ops.py
git commit -m "refactor: undo handlers and bulk rename use stable keys"
```

---

### Task 5: Migrate `api_staging_analyze_references` + object-references route

**Files:**
- Modify: `routes/staging.py:2108-2169` (`api_staging_analyze_references`)
- Modify: `routes/analysis.py:1517-1575` (`api_object_references`)
- Modify: `static/js/explorer/relations-loader.js:372-378,640-646`

**Step 1: Update `api_staging_analyze_references`**

Replace integer key resolution with stable key parsing (lines 2112-2120):

```python
    for stable_key, edit_data in pending_edits.items():
        if not isinstance(edit_data, dict):
            continue

        result = service.find_object_by_stable_key(stable_key)
        if result is None:
            continue
        _, obj = result
```

Update the response dict (line 2160-2162) — replace `"globalIndex": global_index` with `"stableKey": stable_key`:

```python
            name_changes.append(
                {
                    "stableKey": stable_key,
                    "objectType": obj.object_type,
                    "oldName": old_name,
                    "newName": new_name,
                    "referenceCount": ref_count,
                    "references": refs,
                }
            )
```

**Step 2: Migrate object-references route to query param**

In `routes/analysis.py`, change the route (line 1517):

```python
@bp.route("/api/object-references")
def api_object_references():
    """Return all relationships for an object by stable key."""
    stable_key = request.args.get("key")
    if not stable_key:
        return jsonify({"error": "Missing 'key' parameter"}), 400

    service = get_service()
    result = service.find_object_by_stable_key(stable_key)
    if result is None:
        return jsonify({"error": "Object not found"}), 404

    global_index, obj = result
    p = service.parser
    objects = list(p.objects)
```

The rest of the function stays the same — `global_index` and `obj` are now resolved from the stable key, but the internal helper functions still work with these values for the duration of the request.

Keep the import of `request` (should already be imported).

**Step 3: Update JS callers**

In `static/js/explorer/relations-loader.js`, change line 378:

```javascript
            const result = await ApiClient.get(`/api/object-references?key=${encodeURIComponent(Explorer.getObjectKey(obj))}`);
```

Change the guard at line 373 from `obj.global_index == null` to just `!obj`:

```javascript
    async function loadCenterReferences(obj) {
        if (!obj) {
            renderCenterReferences({ outgoing: [], incoming: [] });
            return;
        }
```

Change line 646 similarly:

```javascript
            const result = await ApiClient.get(`/api/object-references?key=${encodeURIComponent(Explorer.getObjectKey(obj))}`);
```

And the guard at line 641:

```javascript
    async function loadCenterMembers(obj) {
        if (!obj) {
            renderCenterMembers([], obj);
            return;
        }
```

**Step 4: Run tests**

Run: `python3 -m pytest tests/ -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add routes/staging.py routes/analysis.py static/js/explorer/relations-loader.js
git commit -m "refactor: analyze-references and object-references use stable keys"
```

---

### Task 6: Migrate health_checks `object_indices` → `object_keys`

**Files:**
- Modify: `routes/health_checks.py:1448` (response field)
- Modify: `static/js/explorer/analysis.js` (consumer)
- Modify: `static/js/explorer/analysis-suggestions.js` (consumer)

**Step 1: Update health_checks.py**

At line 1448, add import at top of function or file:

```python
from staging_manager import generate_stable_key_for_object
```

Change line 1448:
```python
            "object_keys": [generate_stable_key_for_object(obj) for _, obj in matching_entries],
```

**Step 2: Update `analysis.js` consumer**

Find where `object_indices` is mapped to objects (around line 131-133 in `analysis.js`). The exact location may be in `analysis-suggestions.js` — search for `object_indices` and change to:

```javascript
objects: (s.object_keys || []).map(key => StableKey.findObject(key, state.allObjects)).filter(Boolean),
```

**Step 3: Update `analysis-suggestions.js` consumer**

Search for any other `object_indices` references and change similarly.

**Step 4: Run tests**

Run: `python3 -m pytest tests/ -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add routes/health_checks.py static/js/explorer/analysis.js static/js/explorer/analysis-suggestions.js
git commit -m "refactor: health_checks emits object_keys instead of object_indices"
```

---

### Task 7: Migrate JS `state-management.js` wrapper functions

**Files:**
- Modify: `static/js/explorer/state-management.js:22-123`

**Context:** This file has `resolveToGlobalIndex()` which all wrappers call. After migration, `pendingEdits` and `stagedObjectDeletions` are keyed by stable key strings. The wrappers need to resolve inputs to stable keys instead of global indices.

**Step 1: Replace `resolveToGlobalIndex` with `resolveToStableKey`**

```javascript
    /**
     * Resolve various input types to a stable key
     * @param {string|number|Object} objOrKeyOrIndex - Stable key, global_index, or object
     * @returns {string|null} The stable key or null if not resolvable
     */
    function resolveToStableKey(objOrKeyOrIndex) {
        if (typeof objOrKeyOrIndex === 'string') {
            // Already a stable key — verify it's valid
            return objOrKeyOrIndex.indexOf('|') !== -1 ? objOrKeyOrIndex : null;
        }
        if (typeof objOrKeyOrIndex === 'number') {
            // Legacy: global_index — convert to stable key
            return Explorer.getObjectKeyByIndex(objOrKeyOrIndex);
        }
        if (objOrKeyOrIndex && typeof objOrKeyOrIndex === 'object') {
            return Explorer.getObjectKey(objOrKeyOrIndex);
        }
        return null;
    }
```

**Step 2: Update `getPendingEdit`**

```javascript
    Explorer.getPendingEdit = function(objOrKeyOrIndex) {
        const key = resolveToStableKey(objOrKeyOrIndex);
        return key !== null ? state.pendingEdits.get(key) : undefined;
    };
```

**Step 3: Update `setPendingEdit`**

```javascript
    Explorer.setPendingEdit = function(objOrKeyOrIndex, editData) {
        const key = resolveToStableKey(objOrKeyOrIndex);
        if (key !== null) {
            state.pendingEdits.set(key, editData);
            return true;
        }
        return false;
    };
```

**Step 4: Update `deletePendingEdit`**

```javascript
    Explorer.deletePendingEdit = function(objOrKeyOrIndex) {
        const key = resolveToStableKey(objOrKeyOrIndex);
        if (key !== null) {
            state.pendingEdits.delete(key);
            return true;
        }
        return false;
    };
```

**Step 5: Update `isObjectMarkedForDeletion`**

```javascript
    Explorer.isObjectMarkedForDeletion = function(objOrKeyOrIndex) {
        const key = resolveToStableKey(objOrKeyOrIndex);
        return key !== null && state.stagedObjectDeletions.has(key);
    };
```

**Step 6: Update `markObjectForDeletion`**

```javascript
    Explorer.markObjectForDeletion = function(objOrKeyOrIndex) {
        const key = resolveToStableKey(objOrKeyOrIndex);
        if (key !== null) {
            state.stagedObjectDeletions.add(key);
            return true;
        }
        return false;
    };
```

**Step 7: Update `unmarkObjectForDeletion`**

```javascript
    Explorer.unmarkObjectForDeletion = function(objOrKeyOrIndex) {
        const key = resolveToStableKey(objOrKeyOrIndex);
        if (key !== null) {
            state.stagedObjectDeletions.delete(key);
            return true;
        }
        return false;
    };
```

**Step 8: Commit**

```bash
git add static/js/explorer/state-management.js
git commit -m "refactor: state-management wrappers resolve to stable keys"
```

---

### Task 8: Migrate JS `data-loading.js` serialization

**Files:**
- Modify: `static/js/explorer/data-loading.js:218-240` (`syncStagingFromData`)

**Step 1: Fix deserialization — remove `Number(key)` coercion**

In `syncStagingFromData` (lines 218-227), change:

```javascript
    function syncStagingFromData(state, data) {
        // pendingEdits: keyed by stable key strings
        if (data.pendingEdits) {
            const validEdits = Object.entries(data.pendingEdits).filter(([key, edit]) => {
                return edit && edit.object && edit.object.source_file;
            });
            state.pendingEdits = new Map(validEdits);
        }
```

The serialization path (`Explorer.saveStaging`, line 123) already uses `Object.fromEntries(state.pendingEdits)` — this works with string keys without changes.

The `stagedObjectDeletions` path (line 239) already uses `new Set(data.stagedObjectDeletions)` — this works with string values without changes.

**Step 2: Commit**

```bash
git add static/js/explorer/data-loading.js
git commit -m "refactor: data-loading deserializes stable key strings (not integers)"
```

---

### Task 9: Migrate JS `object-editor.js`

**Files:**
- Modify: `static/js/explorer/object-editor.js`

**Step 1: Update `showCenterPaneObject` (line 170)**

```javascript
        const pendingEdit = state.pendingEdits.get(Explorer.getObjectKey(obj));
```

**Step 2: Update orphan check (line 184)**

```javascript
        const isOrphan = Explorer.state.orphanIndices.has(Explorer.getObjectKey(obj));
```

**Step 3: Replace `getDeletedObjectKeys()` (lines 338-348)**

The function currently builds `source_file:line_number` keys. Replace with direct stable key check:

```javascript
    function isObjectStagedForDeletion(obj) {
        return state.stagedObjectDeletions.has(Explorer.getObjectKey(obj));
    }
```

**Step 4: Update autocomplete filter (lines 395-399)**

Replace:
```javascript
                return !deletedKeys.has(`${o.source_file}:${o.line_number}`);
```
With:
```javascript
                return !isObjectStagedForDeletion(o);
```

Remove the `const deletedKeys = getDeletedObjectKeys();` call above it.

**Step 5: Replace duplicate logic in `getTemplatesForType` (lines 1444-1462)**

Replace the inline deletion-key building (lines 1447-1454) with the same pattern:

```javascript
        const templates = state.allObjects
            .filter(o => {
                if (o.object_type !== objectType || o.attributes.register !== '0') {return false;}
                if (isObjectStagedForDeletion(o)) {return false;}
```

Remove the `stagedDeletionIndices` / `deletedKeys` block entirely.

**Step 6: Update `stageCurrentChanges` (around lines 1184-1208)**

Find `const globalIndex = state.editedObject.global_index;` and the subsequent `state.pendingEdits.set(globalIndex, ...)`. Change to:

```javascript
        const objKey = Explorer.getObjectKey(state.editedObject);
        // ...
        state.pendingEdits.set(objKey, {
            original: originalState,
            edited: {...state.editedObject.attributes},
            object: {
                source_file: state.editedObject.source_file,
                line_number: state.editedObject.line_number,
                object_type: state.editedObject.object_type,
                name: state.editedObject.name,
                display_name: state.editedObject.display_name
            }
        });
```

Also update the existing-edit check (around line 1168):

```javascript
        const existingEdit = state.pendingEdits.get(Explorer.getObjectKey(state.editedObject));
```

**Step 7: Commit**

```bash
git add static/js/explorer/object-editor.js
git commit -m "refactor: object-editor uses stable keys for pendingEdits and deletions"
```

---

### Task 10: Migrate JS `context-menu.js`

**Files:**
- Modify: `static/js/explorer/context-menu.js`

**Step 1: Update `getOrCreatePendingEdit` (line 36)**

```javascript
        const existingEdit = state.pendingEdits.get(Explorer.getObjectKey(obj));
```

**Step 2: Update bulk group-add (line 95)**

```javascript
                state.pendingEdits.set(Explorer.getObjectKey(obj), {
```

**Step 3: Update `getCurrentName` (line 218)**

```javascript
            const pendingEdit = state.pendingEdits.get(Explorer.getObjectKey(obj));
```

**Step 4: Update preview panel (line 283)**

```javascript
            const pendingEdit = state.pendingEdits.get(Explorer.getObjectKey(obj));
```

**Step 5: Update clone (line 593)**

```javascript
            attributes: {...(state.pendingEdits.get(Explorer.getObjectKey(obj))?.edited || obj.attributes)},
```

**Step 6: Update add-to-group bulk (line 901)**

```javascript
                state.pendingEdits.set(Explorer.getObjectKey(obj), {
```

**Step 7: Update refresh center pane (line 920)**

```javascript
            const pendingEdit = state.pendingEdits.get(Explorer.getObjectKey(state.editedObject));
```

**Step 8: Commit**

```bash
git add static/js/explorer/context-menu.js
git commit -m "refactor: context-menu uses stable keys for pendingEdits"
```

---

### Task 11: Migrate JS `dialogs.js`

**Files:**
- Modify: `static/js/explorer/dialogs.js`

**Step 1: Update `executeObjectDeletions` (lines 729-748)**

This function gets indices from `Explorer.getSelectedIndices()`, then does `stagedObjectDeletions.has/add(index)` and `pendingEdits.delete(index)`. Rewrite to use stable keys:

```javascript
    function executeObjectDeletions(stagedCreationDeletedCount = 0) {
        let deletedCount = 0;

        for (const key of Explorer.state.selectedKeys) {
            const obj = Explorer.findObjectByKey(key);
            if (!obj) {continue;}
            const objKey = Explorer.getObjectKey(obj);
            if (!state.stagedObjectDeletions.has(objKey)) {
                state.stagedObjectDeletions.add(objKey);
                state.pendingEdits.delete(objKey);
                state.stagedMoves.delete(objKey);
                deletedCount++;
            }
        }

        // Close tabs for deleted objects
        for (const key of Explorer.state.selectedKeys) {
            Explorer.closeTab(key);
        }

        Explorer.clearSelection();
        Explorer.afterFrontendMutation();
        // ... toast messages unchanged
    }
```

**Step 2: Update `unstageObjectDeletion` (line 764-765)**

This takes an `index` param. Change callers to pass a stable key, and update:

```javascript
    function unstageObjectDeletion(key) {
        state.stagedObjectDeletions.delete(key);
        Explorer.afterFrontendMutation();
    }
```

Check all callers of `unstageObjectDeletion` and ensure they pass a stable key.

**Step 3: Update bulk rename cascade (lines 787-813)**

Replace `d.object.global_index` with stable keys:

```javascript
            const deps = Explorer.findDependencies(oldName)
                .filter(d => !allRenamedKeys.has(Explorer.getObjectKey(d.object)));

            for (const dep of deps) {
                const depKey = Explorer.getObjectKey(dep.object);
                const existingEdit = state.pendingEdits.get(depKey);
```

And the `.set`:

```javascript
                    state.pendingEdits.set(depKey, {
```

The `allRenamedIndices` set (wherever it's built in the function) should become `allRenamedKeys` using `Explorer.getObjectKey(obj)`.

**Step 4: Update `applyBulkRenameEdits` (lines 832-866)**

Replace all `idx` / `global_index` usage with stable keys:

```javascript
    function applyBulkRenameEdits(find, replace) {
        const renames = [];
        let centerPaneNeedsRefresh = false;

        for (const key of Explorer.state.selectedKeys) {
            const obj = Explorer.findObjectByKey(key);
            if (!obj) {continue;}

            const objKey = Explorer.getObjectKey(obj);
            const nameField = Explorer.getNameFieldForObject(obj);
            const existingEdit = state.pendingEdits.get(objKey);
            const currentName = existingEdit ? (existingEdit.edited[nameField] || '') : (obj.attributes[nameField] || '');
            const newName = currentName.split(find).join(replace);

            if (newName !== currentName) {
                const originalAttrs = existingEdit ? existingEdit.original : {...obj.attributes};
                const editedAttrs = existingEdit ? {...existingEdit.edited} : {...obj.attributes};
                editedAttrs[nameField] = newName;

                state.pendingEdits.set(objKey, {
                    original: originalAttrs,
                    edited: editedAttrs,
                    object: {
                        source_file: obj.source_file,
                        line_number: obj.line_number,
                        object_type: obj.object_type,
                        name: obj.name,
                        display_name: obj.display_name
                    }
                });
                renames.push({ oldName: currentName, newName, objKey });

                if (state.editedObject && Explorer.getObjectKey(state.editedObject) === objKey) {
                    centerPaneNeedsRefresh = true;
                }
            }
        }
        return { renames, centerPaneNeedsRefresh };
    }
```

**Step 5: Commit**

```bash
git add static/js/explorer/dialogs.js
git commit -m "refactor: dialogs uses stable keys for edits and deletions"
```

---

### Task 12: Migrate JS `analysis.js` + `analysis-suggestions.js`

**Files:**
- Modify: `static/js/explorer/analysis.js`
- Modify: `static/js/explorer/analysis-suggestions.js`

**Step 1: Update `filterActiveSuggestions` (analysis.js line 15)**

The call is `Explorer.isObjectMarkedForDeletion(s.object.global_index)`. Since we updated the wrapper in Task 7 to accept any type, passing an object is cleaner:

```javascript
        return suggestions.filter(s => s.object && !Explorer.isObjectMarkedForDeletion(s.object));
```

**Step 2: Update orphanIndices (analysis.js lines 152, 162, 166)**

```javascript
        state.orphanIndices.add(Explorer.getObjectKey(obj));
```

(Three handlers: `orphan`, `orphan_service`, `service_on_empty_hostgroup`)

**Step 3: Update issue dispatch skip (analysis.js line 231)**

```javascript
            if (obj && state.stagedObjectDeletions.has(Explorer.getObjectKey(obj))) {continue;}
```

**Step 4: Update warning collection skip (analysis.js line 315)**

This line checks `issue.global_index` directly against `stagedObjectDeletions`. After migration, look up the object first:

```javascript
            if (issue.global_index != null) {
                const issueObj = objectsByIndex.get(issue.global_index);
                if (issueObj && state.stagedObjectDeletions.has(Explorer.getObjectKey(issueObj))) {continue;}
            }
```

**Step 5: Update deletion staging (analysis.js lines 746-748)**

```javascript
    if (!state.stagedObjectDeletions.has(Explorer.getObjectKey(obj))) {
        state.stagedObjectDeletions.add(Explorer.getObjectKey(obj));
        state.pendingEdits.delete(Explorer.getObjectKey(obj));
```

**Step 6: Update bulk delete (analysis.js lines 986-991)**

```javascript
                state.stagedObjectDeletions.add(Explorer.getObjectKey(s.object));
```

**Step 7: Update cleanup action (analysis.js line 1048)**

```javascript
    state.stagedObjectDeletions.add(Explorer.getObjectKey(obj));
```

**Step 8: Update resolve duplicates (analysis.js line 1166)**

```javascript
            state.stagedObjectDeletions.add(Explorer.getObjectKey(obj));
```

**Step 9: Update analysis-suggestions.js (line 381)**

```javascript
                state.pendingEdits.set(Explorer.getObjectKey(obj), {
                    original: { ...obj.attributes },
                    edited: newAttrs,
                    object: {
                        source_file: obj.source_file,
                        line_number: obj.line_number,
                        object_type: obj.object_type,
                        display_name: obj.display_name,
                    }
                });
```

Remove the `global_index` from the `object` sub-dict.

**Step 10: Commit**

```bash
git add static/js/explorer/analysis.js static/js/explorer/analysis-suggestions.js
git commit -m "refactor: analysis modules use stable keys"
```

---

### Task 13: Migrate JS `app.js` + `badge-issues.js` + `impact-section.js`

**Files:**
- Modify: `static/js/explorer/app.js`
- Modify: `static/js/explorer/badge-issues.js`
- Modify: `static/js/explorer/impact-section.js`

**Step 1: Update `app.js` orphan filter (lines 449-453)**

```javascript
        filtered = filtered.filter(o =>
            state.orphanIndices.has(Explorer.getObjectKey(o)) || getObjectIssue(o) !== null
        );
    } else if (orphansOnly) {
        filtered = filtered.filter(o => state.orphanIndices.has(Explorer.getObjectKey(o)));
    }
```

**Step 2: Update `renderTreeItem` (lines 730-733)**

```javascript
        const isOrphan = state.orphanIndices.has(Explorer.getObjectKey(obj));
        const isDeleted = state.stagedObjectDeletions.has(Explorer.getObjectKey(obj));
```

**Step 3: Update `getStagedDisplayName` (line 799)**

```javascript
        const edit = state.pendingEdits.get(Explorer.getObjectKey(obj));
```

**Step 4: Update `getEffectiveAttributes` (line 846)**

```javascript
        const pendingEdit = state.pendingEdits.get(Explorer.getObjectKey(obj));
```

**Step 5: Update `badge-issues.js` `computeStagedIssues` (lines 125-126)**

Replace the `find(o.global_index === idx)` pattern:

```javascript
        for (const [key, edit] of state.pendingEdits) {
            const obj = StableKey.findObject(key, state.allObjects);
            if (!obj) {continue;}
```

**Step 6: Update `badge-issues.js` `buildEditedTemplatesMap` (lines 242-243)**

```javascript
        for (const [key, edit] of state.pendingEdits) {
            const obj = StableKey.findObject(key, state.allObjects);
            if (!obj) {continue;}
```

**Step 7: Update `badge-issues.js` deletion skip (line 149)**

```javascript
            if (state.stagedObjectDeletions.has(Explorer.getObjectKey(o))) {return;}
```

**Step 8: Update `impact-section.js` (line 215)**

```javascript
            const pendingEdit = state.pendingEdits.get(Explorer.getObjectKey(tmplObj));
```

**Step 9: Commit**

```bash
git add static/js/explorer/app.js static/js/explorer/badge-issues.js static/js/explorer/impact-section.js
git commit -m "refactor: app, badge-issues, impact-section use stable keys"
```

---

### Task 14: Migrate JS `tab-manager.js` + `main.js` cleanup

**Files:**
- Modify: `static/js/explorer/tab-manager.js`
- Modify: `static/js/explorer/main.js`

**Step 1: Update tab bar modified dot (tab-manager.js line 254)**

```javascript
            const hasPendingEdit = state.pendingEdits.has(tab.key);
```

**Step 2: Remove `objectIndex` from tab objects**

In `openTab()` (lines 79-99), remove `objectIndex` assignments:

```javascript
    function openTab(obj) {
        if (!obj) {return;}
        const key = Explorer.getObjectKey(obj);
        const existingIdx = state.openTabs.findIndex(t => t.key === key);
        if (existingIdx >= 0) {
            state.openTabs[existingIdx].label = obj.display_name;
            state.openTabs[existingIdx].typeIcon = obj.object_type;
            state.activeTabKey = key;
        } else {
            state.openTabs.push({
                key: key,
                label: obj.display_name,
                typeIcon: obj.object_type
            });
        }
```

**Step 3: Simplify `validateTabs` (lines 193-225)**

Remove the `global_index` fallback path:

```javascript
    function validateTabs() {
        const before = state.openTabs.length;
        state.openTabs = state.openTabs.filter(tab => {
            const obj = Explorer.findObjectByKey(tab.key);
            if (obj) {
                tab.label = obj.display_name;
                return true;
            }
            return false;
        });
```

**Step 4: Update tab loading from localStorage (lines 40-64)**

Remove `objectIndex`:

```javascript
        for (const tab of openTabs) {
            const obj = Explorer.findObjectByKey(tab.key);
            if (obj) {
                state.openTabs.push({
                    key: tab.key,
                    label: obj.display_name || tab.label,
                    typeIcon: obj.object_type
                });
            }
        }
```

**Step 5: Update `main.js` state comments (lines 29, 32, 78)**

```javascript
    pendingEdits: new Map(),      // stableKey -> {original, edited, object}
    // ...
    stagedObjectDeletions: new Set(),  // Set of stable keys
    // ...
    orphanIndices: new Set(),   // Set of stable keys for orphan objects
```

**Step 6: Update `main.js` `openTabs` comment (line 59)**

```javascript
    openTabs: [],   // Array of { key, label, typeIcon }
```

**Step 7: Clean up `getObjectKeyByIndex` and `getSelectedIndices`**

`getSelectedIndices` (lines 135-142) is only used by `dialogs.js:executeObjectDeletions` and `dialogs.js:applyBulkRenameEdits` — both were rewritten in Task 11 to use `selectedKeys` directly. Check if any remaining callers exist; if not, remove it. If callers remain, keep it but note it's legacy.

`getObjectKeyByIndex` (lines 147-150) is used by `resolveToStableKey` as a fallback for numeric input — keep it.

**Step 8: Commit**

```bash
git add static/js/explorer/tab-manager.js static/js/explorer/main.js
git commit -m "refactor: tabs use stable keys; clean up main.js state comments"
```

---

### Task 15: Verify end-to-end and final cleanup

**Step 1: Run full Python test suite**

Run: `python3 -m pytest tests/ -v`
Expected: ALL PASS

**Step 2: Manual smoke test**

Start the app: `python3 app.py`

Test these flows in the browser:
1. Edit an object → verify pending edit appears (modified dot on tab and tree)
2. Save staging → reload page → verify edit persists
3. Delete an object → verify deletion marker in tree
4. Undo the deletion → verify it's restored
5. Move an object → verify move marker
6. Bulk rename → verify all renames staged
7. Apply all changes → verify they write to disk
8. Check the Relations/Impact panel loads for an object
9. Check analysis suggestions still show template opportunities

**Step 3: Search for any remaining `global_index` identity usage**

Run: `grep -rn 'global_index' static/js/explorer/ --include='*.js' | grep -v '// ' | grep -v 'global_index:' | grep -v '.global_index =' | grep -v 'obj_dict\["global_index"\]'`

Verify all remaining `global_index` references are:
- Field access on objects (display, passing to UI)
- Not used as Map/Set keys or API identity tokens

**Step 4: Remove dead code**

- `_deletionIdentities` references in `_build_composite_actions` (lines 219)
- Any `globalIndex` references in undo data that are dead paths
- Remove `getDeletedObjectKeys` function in `object-editor.js` (replaced by `isObjectStagedForDeletion`)

**Step 5: Commit**

```bash
git add -A
git commit -m "chore: remove dead global_index identity code after stable key migration"
```
