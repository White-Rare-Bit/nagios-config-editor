# Explorer Modules

All modules use ES module `import`/`export` syntax. Shared state in `state.js`.

## Module Index

| File | What |
|------|------|
| `main.js` | Entry point: imports, initializes event delegation, registers callbacks |
| `state.js` | Shared state object (allObjects, selections, filters, etc.), `TreeExpansionState` class, path conversion utilities |
| `constants.js` | Domain metadata from `/api/metadata` via `applyMetadata()`, badge tiers, UI-only constants (`identityFields`, `inheritanceAttrs`), `isObjectTemplate()` |
| `state-management.js` | Stable key helpers, pending edit get/set, `rebuildUI()` |
| `action-registry.js` | Maps `data-action` names to handler functions for event delegation |
| `app.js` | Left pane: tree rendering, filtering, selection, autocomplete |
| `object-editor.js` | Center pane: attribute editor, validation, create/delete workflows |
| `file-operations.js` | Right pane: file tree, navigation, folder ops. Helper: `afterStagingChange()` |
| `context-menu.js` | Right-click menus, bulk actions. Helper: `getOrCreatePendingEdit(obj)` |
| `dialogs.js` | Create/delete/rename dialogs, dialog content helpers (`dialogAlert`, `dialogKvList`, etc.), `buildTypeDropdown()` |
| `data-loading.js` | API calls, staging orchestrators, sync/polling, initial load |
| `drag-drop.js` | Drag-drop cleanup utilities (handlers in context-menu.js and file-operations.js) |
| `analysis.js` | Suggestions tab: template detection, validation errors |
| `analysis-issues.js` | Grouped validation errors, batch create missing objects |
| `analysis-suggestions.js` | Template consolidation and hostgroup suggestions |
| `badge-issues.js` | Issue badge rendering and counts for tree nodes |
| `relations-loader.js` | Reference and inheritance loading for center pane |
| `impact-section.js` | Impact analysis and resolved attributes in center pane |
| `panel-resizer.js` | Resizable panel dividers |
| `tab-manager.js` | Tab switching for center/right panes |
| `ui-utils.js` | Icons (`icons`, `getIcon()`), `switchTabs()`, `updateBadge()`, `explorerShowToast()`, path utilities (`extractFileName`, `toRelativePath`, `toDisplayPath`), `handleApiError()` |

## Constants: Metadata vs Hardcoded

From `/api/metadata` (source of truth: `app/nagios_model.py`):
`typeLabels`, `nameFields`, `REQUIRED_FIELDS`, `referenceFields`, `NAGIOS_ATTRIBUTES`, `defaultAttributes`, `groupStructure`, notification options, failure criteria

Hardcoded (UI-only, no backend equivalent):
`identityFields`, `inheritanceAttrs`, `referenceAttrs`

## After-Mutation Protocol

Two orchestrators in `data-loading.js` handle all post-mutation work:

| Function | When to use | What it does |
|----------|-------------|--------------|
| `afterFrontendMutation(opts)` | User edited/created/deleted/moved something | rebuildUI -> updateBadges -> debouncedAnalysis |
| `afterServerSync(opts)` | Undo, apply, polling detected change | rebuildUI -> updateBadges -> debouncedAnalysis |

Both accept `options`: `{ skipTree, skipTarget, skipCenter, skipTabs }`.

**Rule:** After mutating state, call `afterFrontendMutation()`. After loading state from server, call `afterServerSync()`. Never manually compose build steps.
