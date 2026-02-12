# Editor Tabs Design

## Summary

Add a tabbed interface to the object editor center pane, allowing users to have multiple objects open simultaneously and switch between them. Tabs are purely a frontend navigation concept — no server changes, no impact on locking or staging.

## Data Model

### State

```javascript
state.openTabs = [];       // Array of { key, objectIndex, label, typeIcon }
state.activeTabKey = null;  // Stable key of the currently active tab
```

- `key`: existing stable key (`"source_file|object_type|name"`)
- `objectIndex`: `global_index` for fast lookup in `state.allObjects`
- `label`: display name for the tab
- `typeIcon`: type identifier for the icon

### Persistence

- Stored in `sessionStorage` under `explorerTabs` as `{ openTabs, activeTabKey }`
- Per-browser-tab — different browser tabs get independent workspaces
- On page load, restore and revalidate that stable keys still exist in loaded objects
- Persists across navbar navigation (e.g., switching to Audit Log and back)

### No Server Changes

Tabs are purely frontend. Existing staging system, locking, and session management are unaffected.

## Tab Bar UI

### Location

Top of the center pane, above the existing breadcrumb. New `<div class="tab-bar">` element.

### Tab Rendering

Each tab shows:
- Type icon (small, from existing `getTypeIcon()`)
- Display name (truncated with ellipsis if too long)
- Close button (x) on the right
- Active tab: distinct background/border-bottom
- Staging indicator: small dot for objects with pending edits

### Overflow

- Container uses `overflow-x: auto` with hidden scrollbar
- Left/right arrow buttons appear at edges only when tabs overflow
- Active tab auto-scrolls into view on activation

### Interactions

- Click tab → auto-stage current edits, switch to clicked tab
- Click x → auto-stage edits, close tab, activate adjacent tab
- Middle-click → close tab
- No tab bar visible when zero tabs are open (show placeholder)

### Styling

- CSS variables following `--nbe-*` convention
- Dark mode via existing theme system
- Flat VS Code-style tabs, lightweight appearance

## Navigation Flow

### Core Function: `openTab(obj)`

New module `tab-manager.js`:

1. Compute stable key for `obj`
2. If tab with that key exists → activate it, scroll into view
3. If not → create new tab entry, append to `state.openTabs`, activate it
4. Call existing `showCenterPaneObject(obj)` to render center pane
5. Persist tabs to `sessionStorage`

### Tab Switch Flow

1. Call `checkForChanges()` on current tab's object
2. If changes detected, auto-stage them (existing behavior)
3. Activate new tab, render its object

### Universal Rule

Any navigation that opens an object in the center pane opens it as a tab. No duplicates — if already open, switch to the existing tab.

### Entry Points Modified

| Entry Point | File | Current Path | Change |
|---|---|---|---|
| Tree item click | `app.js` | `selectObjectByIndex()` → `showCenterPaneObject()` | → `openTab(obj)` |
| Impact/Relationships clicks | `impact-section.js` | `navigateToObjectByIndex()` | → `openTab(obj)` |
| Suggestion clicks | `analysis.js` | `navigateToObjectByIndex()` | → `openTab(obj)` |
| Cross-page from Graph View | `app.js` | `selectObjectByName()` → `showCenterPaneObject()` | → `openTab(obj)` |
| Context menu go-to | `context-menu.js` | `navigateToObjectByIndex()` | → `openTab(obj)` |
| URL param navigation | `app.js` | `selectObjectByName()` | → `openTab(obj)` |
| Post-create navigation | `dialogs.js` | `navigateToObjectByIndex()` | → `openTab(obj)` |

**Key insight**: `navigateToObjectByIndex()` in `file-operations.js` is the central navigation function used by most paths. Updating it to call `openTab()` captures most entry points.

## Edge Cases

### Object deleted while tab is open
On `loadObjects()` refresh, validate all open tabs against `state.allObjects`. Remove tabs whose stable keys no longer exist. If active tab removed, activate nearest remaining tab.

### Object renamed/moved while tab is open
Reconcile by matching on `global_index` as fallback. If index exists but key changed, update the tab entry's key.

### Closing the last tab
Return to empty "Select an object" placeholder. Clear `state.editedObject` and `state.currentCenterObject`.

### Tab + tree selection sync
Activating a tab highlights the corresponding tree item. Guard against infinite loop with `state.isTabSwitch` flag when calling `selectObjectByIndex()` from tab activation.

### Bulk operations
Multi-select (Ctrl/Shift+click) continues to work for bulk context menu actions without opening tabs. Only plain single-click opens a tab.

### No duplicate tabs
If navigating to an already-open object, switch to its existing tab.

### No hard limit on tab count
Tabs are lightweight references. Users manage their own workspace.

## Behaviors Unchanged

- Auto-staging on navigation away (now "on tab switch")
- Staging lock mechanics — only triggered by actual edits, not by opening tabs
- Session isolation — `sessionStorage` is per-browser-tab by definition
- Undo system
- Bulk selection and context menus
