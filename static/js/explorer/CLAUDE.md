# Explorer Module Reference

Modular architecture for Nagios config explorer: shared namespace, three-pane UI (tree/editor/files), staging system integration.

## Module Index

| File | What | When |
|------|------|------|
| `main.js` | Namespace definition (`window.Explorer`), state structure (allObjects, selections, staging maps, undo stack) | Understanding state or initialization |
| `state-management.js` | Stable key helpers, pending edit getters/setters, refresh coordination (`refreshAfterObjectChange`) | Modifying staging or refresh logic |
| `app.js` | Tree pane: rendering, filtering, selection, autocomplete, references/inheritance display | Tree UI or object relationships |
| `object-editor.js` | Center pane: attribute editor, validation, edit staging, create/delete workflows | Object editing UI |
| `file-operations.js` | Target pane: file tree rendering, navigation, folder operations | File tree or move operations |
| `context-menu.js` | Right-click menus, bulk actions, preview modal, drag-drop from tree | Context menus or bulk operations |
| `dialogs.js` | Create/delete/rename dialogs, validation | Dialog UI |
| `data-loading.js` | API calls, staging sync/polling, initial load | Data loading or sync |
| `drag-drop.js` | Unified drag-drop handler (objects and files), drop zones, visual feedback | Drag-drop behavior |
| `analysis.js` | Suggestions tab: template detection, cleanup, validation errors | Analysis features |
| `ui-utils.js` | Icons, formatting (formatObjectName, buildBreadcrumb), tab switching | UI utilities |

## State Management

**Namespace**: All modules attach to `window.Explorer` and access `Explorer.state`.

**Shared State** (`Explorer.state`):
- `allObjects`, `allFiles` - Server data
- `selectedKeys` (Set) - Selected object stable keys
- `pendingEdits` (Map) - `global_index -> {original, edited, object}`
- `stagedMoves` (Map) - `stableKey -> {targetFile, originalFile, object}`
- `stagedCreations`, `stagedObjectDeletions`, `stagedFileCreations`, etc. - Staging operations
- `undoStack` - Operation history
- `editedObject`, `isNewObject` - Center pane edit state

**Stable Keys**: Objects identified by `"source_file|object_type|name"` instead of global_index for staging persistence.

## Key Patterns

### Refresh After Changes

```javascript
Explorer.refreshAfterObjectChange({
    skipTree: false,      // Refresh tree pane
    skipCenter: false,    // Refresh center editor
    skipTarget: false,    // Refresh target file pane
    skipSuggestions: false, // Refresh analysis
    skipCommit: false     // Update commit button badge
});
```

Call after ANY object mutation (create, edit, delete, move, undo).

### Staging Integration

All operations use staging system - changes NOT written to disk until "Apply".

```javascript
// Stage object edit
Explorer.setPendingEdit(obj.global_index, {original, edited, object});

// Stage object move
state.stagedMoves.set(stableKey, {targetFile, originalFile, object});

// Stage object creation
state.stagedCreations.push({object_type, attributes, targetFile, displayName});

// Stage object deletion
state.stagedObjectDeletions.add(global_index);
```

### Three-Pane Architecture

| Pane | Module | Purpose |
|------|--------|---------|
| Left (Tree) | `app.js` | Browse objects by file or type, filter, select |
| Center (Editor) | `object-editor.js` | Edit attributes, view inheritance/references |
| Right (Files) | `file-operations.js` | File tree, move targets, folder operations |

### Selection

Uses stable keys (`Set`). Helper functions:
- `Explorer.isSelectedByKey(key)` / `Explorer.isSelectedByIndex(index)`
- `Explorer.getSelectedIndices()` - Returns array of global_index values
- `Explorer.clearSelection()`, `Explorer.selectObjectByKey(key)`

### Cross-Module Communication

Modules delegate via `Explorer` namespace:

```javascript
// app.js delegates to object-editor.js
function showCenterPaneObject(obj) { Explorer.showCenterPaneObject(obj); }

// object-editor.js delegates to state-management.js
Explorer.refreshAfterObjectChange({ skipTree: true });
```
