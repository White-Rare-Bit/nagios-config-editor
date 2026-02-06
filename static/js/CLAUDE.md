# CLAUDE.md

## Core Modules

| File | What | When |
| ---- | ---- | ---- |
| `api-client.js` | Fetch wrapper with error handling, staging headers, {success, data, error} format | Changing API patterns or error handling |
| `base.js` | Session/lock management, toast notifications, commit dialog, git operations UI, DebugLogger | Modifying lock UI, commit workflow, or notifications |

## Page-Specific Modules

All page modules use the IIFE pattern for scope isolation and extract configuration into named constants.

| File | What | When |
| ---- | ---- | ---- |
| `audit-log.js` | Audit log filtering, pagination. Constants: `ENTRIES_PER_PAGE` | Modifying audit log page |
| `backups.js` | Backup list/restore/delete UI | Modifying backup page |
| `bulk-rename.js` | Pattern-based bulk rename, preview | Modifying bulk rename page |
| `dependencies.js` | Cytoscape graph visualization, edge categories, quick view presets. Utilities: `getEdgesInSubgraph()`, `getConnectedNodeIdsFromEdges()` | Modifying dependency graph page |
| `find-replace.js` | Search, preview, bulk replacement. Constants: `MIN_SEARCH_CHARS`, `DEBOUNCE_MS`, `MAX_SUGGESTIONS` | Modifying find/replace page |
| `git.js` | File list, diff viewer, commit/discard UI | Modifying git page |
| `inheritance.js` | Inheritance tree visualization | Modifying inheritance page |
| `reorganize.js` | File/folder restructuring UI. Helper: `performBulkOperation()` for move/clone/delete | Modifying reorganize page |
| `settings.js` | Identity config, git preferences, config paths | Modifying settings page |
| `smart-grouping.js` | Auto-suggest grouping patterns. Constants: `TYPE_COLORS`, `TYPE_LABELS`, `PREVIEW_LIMIT` | Modifying smart grouping page |
| `validate.js` | Nagios -v output display | Modifying validate page |

## Module Patterns

### IIFE Wrapper
All page modules use the Immediately Invoked Function Expression pattern:
```javascript
(function() {
    'use strict';
    // Module code here
})();
```

### Constants Extraction
Magic numbers and configuration are extracted to named constants at module top:
```javascript
const DEBOUNCE_MS = 150;
const MAX_SUGGESTIONS = 20;
```

### Bulk Operation Pattern (reorganize.js)
The `performBulkOperation()` helper consolidates validation, confirmation, API call, and result handling:
```javascript
await performBulkOperation({
    operationName: 'move',
    endpoint: '/api/move-objects',
    getPayload: (indices) => ({ objects: indices, target_file: targetFile }),
    getSuccessMessage: (data) => `Moved ${data.moved} objects`,
    confirm: { title: 'Move Objects', message: 'Move {count} objects?', type: 'warning' }
});
```

## Explorer Modules

See `explorer/CLAUDE.md` for modular explorer architecture (tree, editor, file panes, staging).
