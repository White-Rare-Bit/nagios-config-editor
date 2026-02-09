# Explorer Modules

All modules attach to `window.Explorer` namespace. State in `Explorer.state`.

## Module Index

| File | What |
|------|------|
| `main.js` | Namespace, state structure (allObjects, selections, staging maps, undo stack) |
| `constants.js` | Domain metadata from `/api/metadata`, UI-only constants, shared helpers |
| `state-management.js` | Stable key helpers, pending edit get/set, `refreshAfterObjectChange()` |
| `app.js` | Left pane: tree rendering, filtering, selection, autocomplete |
| `object-editor.js` | Center pane: attribute editor, validation, create/delete workflows |
| `file-operations.js` | Right pane: file tree, navigation, folder ops. Helper: `afterStagingChange()` |
| `context-menu.js` | Right-click menus, bulk actions. Helper: `getOrCreatePendingEdit(obj)` |
| `dialogs.js` | Create/delete/rename dialogs, `buildWarningBox()`, `buildTypeDropdown()` |
| `data-loading.js` | API calls, staging sync/polling, initial load |
| `drag-drop.js` | Drag-drop cleanup utilities (handlers in context-menu.js and file-operations.js) |
| `analysis.js` | Suggestions tab: template detection, validation errors |
| `analysis-issues.js` | Grouped validation errors, batch create missing objects |
| `analysis-suggestions.js` | Template consolidation and hostgroup suggestions |
| `badge-issues.js` | Issue badge rendering and counts for tree nodes |
| `relations-loader.js` | Reference and inheritance loading for center pane |
| `impact-section.js` | Impact analysis and resolved attributes in center pane |
| `ui-utils.js` | Icons, `formatObjectName()`, `buildBreadcrumb()`, tab switching |

## Constants: Metadata vs Hardcoded

From `/api/metadata` (source of truth: `nagios_model.py`):
`typeLabels`, `nameFields`, `REQUIRED_FIELDS`, `referenceFields`, `ATTR_REFERENCE_MAP`, `NAGIOS_ATTRIBUTES`, `defaultAttributes`, `groupStructure`, notification options, failure criteria

Hardcoded (UI-only, no backend equivalent):
`identityFields`, `inheritanceAttrs`, `referenceAttrs`
