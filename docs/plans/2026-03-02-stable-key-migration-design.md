# Stable Key Migration Design

**Date:** 2026-03-02
**Status:** Approved

## Problem

`pendingEdits` and `stagedObjectDeletions` use `global_index` (array position) as their identity key throughout the stack. `global_index` is ephemeral — it changes when the parser reloads (e.g., after a partial apply or file change). This makes the staging system fragile: edits and deletions can target the wrong object if indices shift between staging and applying.

The `stagedMoves` system already uses stable keys (`source_file|object_type|name`) and works correctly. This migration brings the rest of the staging system into alignment.

## Approach

**Key-at-the-edges (Approach A):** Change the keys used in `pendingEdits` and `stagedObjectDeletions` from `global_index` to stable keys. Clean break — bump schema version, reject old-format staging files.

## Core Data Structure Changes

### `pendingEdits`

- **JS:** `Map<int(global_index), editEntry>` → `Map<string(stableKey), editEntry>`
- **Wire:** `{"42": {object, original, edited}}` → `{"path/file.cfg|host|myhost": {object, original, edited}}`
- **Python:** `pending_edits` dict keys become stable key strings

### `stagedObjectDeletions`

- **JS:** `Set<int(global_index)>` → `Set<string(stableKey)>`
- **Wire:** `[42, 78]` → `["path/file.cfg|host|myhost", "path/file.cfg|service|myservice"]`
- **Python:** `staged_object_deletions` list entries become stable key strings

### Schema version bump

Clean break. Old staging files rejected on load.

### `_deletionIdentities` sidecar

Removed entirely. The stable key *is* the identity.

## JavaScript Touch Points

Every `.get()` / `.set()` / `.has()` / `.delete()` on `pendingEdits` switches from `obj.global_index` to `Explorer.getObjectKey(obj)`:

| File | Sites | What changes |
|------|-------|------|
| `object-editor.js` | ~5 | `stageCurrentChanges()`, `loadObjectForEditing()`, existing-edit check |
| `context-menu.js` | ~8 | All edit/delete staging in context menu actions |
| `dialogs.js` | ~7 | Bulk rename, bulk edit attributes, delete confirmation |
| `analysis-suggestions.js` | ~1 | Auto-fix staging |
| `analysis.js` | ~3 | Delete from analysis, iteration over pendingEdits |
| `app.js` | ~3 | Edit indicator checks, deletion staging |
| `badge-issues.js` | ~3 | Iteration over pendingEdits + stagedObjectDeletions |
| `impact-section.js` | ~1 | Template pending-edit check |
| `tab-manager.js` | 1 | `pendingEdits.has(tab.objectIndex)` → `pendingEdits.has(tab.key)` |

### `data-loading.js` deserialization

The `Number(key)` coercion (line 226) is removed. Keys stay as strings. `stagedObjectDeletions` Set contains strings instead of ints.

### Proxy key cleanup

`object-editor.js` `getDeletedObjectKeys()` builds `source_file:line_number` strings — replaced with direct `stagedObjectDeletions.has(Explorer.getObjectKey(obj))` checks.

### `orphanIndices`

Changes from `Set<int>` to `Set<stableKey>`. Set in `analysis.js`, checked in `app.js`.

### Tab `objectIndex`

Dropped from tab objects entirely. `validateTabs()` global_index fallback removed. Tabs already use `tab.key` as primary identity. The modified-dot check becomes `pendingEdits.has(tab.key)`.

## Python Backend Touch Points

### Virtual tree builders (`routes/staging.py`)

All three functions gain a shared preamble that builds a `stable_key → list_index` map from `virtual_objects`, then use it for O(1) lookups:

| Function | Current | After |
|----------|---------|-------|
| `_apply_staged_edits_to_virtual` | `virtual_objects[int(gi_str)]` | Lookup map by stable key |
| `_apply_staged_deletions_to_virtual` | `virtual_objects[int(entry)]` | Lookup map by stable key |
| `_apply_staged_moves_to_virtual` | Full attribute dict comparison | Stable key from dict key against lookup map |

### `_enrich_deletion_identities`

Deleted entirely.

### `_build_composite_actions` (`nagios_service.py`)

- `pendingEdits` loop: dict key *is* the stable key — normalize path with `os.path.realpath()`.
- `stagedObjectDeletions` loop: parse stable key directly, no sidecar needed.
- `global_index` field in `edits_by_key`/`deletes_by_key` becomes unnecessary.

### `api_staging_analyze_references`

`int(gi_str)` + `find_object_by_index` → parse stable key, find object by `source_file + object_type + name`.

### `stage_bulk_rename` (`staging_manager.py`)

Keys by `entry["stableKey"]` instead of `str(entry["globalIndex"])`.

### Undo handlers

- `_undo_edit` / `_undo_bulk_edit`: `globalIndex` fallback becomes dead code, removed.
- `_undo_deletion` / `_undo_bulk_deletion`: `int()` cast and integer filtering replaced with string comparison.

### `parse_stable_key` bug fix

Python version rejects names containing `|` (`len(parts) != 3`). Fixed to match JS: `parts[0]`, `parts[1]`, `"|".join(parts[2:])`.

## API Route Migration

### `GET /api/object-references/<int:global_index>`

Replaced with `GET /api/object-references?key=<url_encoded_stable_key>`. Stable key contains `/` and `|` so query parameter is cleaner than path segment. Old integer route removed. Called from `relations-loader.js` and `impact-section.js`.

### `health_checks.py` `object_indices`

Replaced with `object_keys: [stableKey]`. Backend builds stable keys from objects in hand:
```python
"object_keys": [generate_stable_key_for_object(obj) for _, obj in matching_entries]
```

Frontend switches from `find(o => o.global_index === idx)` to `StableKey.findObject(key, state.allObjects)`.

## What `global_index` Remains For

`global_index` is **not removed from the system**. It remains as:

- A field on objects returned by `GET /api/objects` and the virtual tree — the object's position in the parser array, useful for efficient array access within a single request/response cycle
- Used internally by the parser and writer for positional operations (finding text ranges in files)

**Invariant after migration:** `global_index` is ephemeral (valid for one parser load), stable keys are durable (valid across reloads).
