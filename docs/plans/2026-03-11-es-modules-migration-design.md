# ES Modules Migration Design

**Date:** 2026-03-11
**Approach:** Big bang — convert all 41 JS files in a single pass
**Build tooling:** None — native browser ES modules only

## Goal

Replace IIFE + window globals architecture with ES module `import`/`export` to make dependencies explicit and traceable. No build step, no TypeScript, no bundling.

## Current State

- 41 JS files (25k LOC), all loaded via `<script>` tags in templates
- 10 core modules always loaded in `base.html` in strict order
- 18 explorer modules use `(function(Explorer) { ... })(window.Explorer || {})` IIFE pattern
- 7 page modules (git, logs, backups, settings, dependencies, docs, explorer)
- 40+ functions exported to `window`, dependencies implicit in load order
- No existing build tooling (no bundler, no TypeScript)

## Design

### Core Modules (10 files)

The 10 always-loaded scripts in `base.html` become ES modules with explicit imports.

**Dependency graph (arrows = imports):**
```
app.js (standalone utilities: escapeHtml, formatDate, etc.)
  ^
  |-- ui-notifications.js (showToast, showConfirmDialog)
  |-- git-ui.js (showGitRunningPanel, etc.)

base-state.js (standalone: shared state object)
  ^
  |-- git-ui.js
  |-- commit-dialog.js
  |-- base.js

session-manager.js (standalone: getSessionId, getStagingHeaders)
  ^
  |-- api-client.js
  |-- base.js

stable-key.js (standalone: StableKey.build/parse/find)

api-client.js (imports showToast, getStagingHeaders)
  ^
  |-- commit-dialog.js
  |-- base.js
  |-- all page modules
  |-- explorer data-loading

ui-notifications.js (imports escapeHtml)
  ^
  |-- commit-dialog.js
  |-- base.js
  |-- most page modules
```

**Per-file changes:**
- Remove IIFE wrappers
- Add `export` to public functions/objects
- Add `import { ... } from './...'` at top
- Remove all `window.X = X` assignments

`base.html` drops 10 individual `<script>` tags, replaced by:
```html
<script type="module" src="{{ url_for('static', filename='js/base.js') }}"></script>
```

`base.js` imports everything it needs; the import chain pulls in all core modules.

**Note:** `app.js` currently lives at `/static/app.js` (not `/static/js/`). It moves to `/static/js/app.js` or import paths account for the directory difference.

### Page Modules (7 pages)

Each page template gets a single `<script type="module">`:

| Page | Entry point |
|------|-------------|
| explorer.html | `js/explorer/main.js` |
| dependencies.html | `js/dependencies.js` (imports dependencies-config.js) |
| git.html | `js/git.js` |
| logs.html | `js/logs.js` |
| backups.html | `js/backups.js` |
| settings.html | `js/settings.js` |
| docs.html | `js/docs.js` (imports docs-data.js) |

`shared/pagination.js` exports `renderPagination()`, imported by logs, backups, and git modules.

### Explorer Modules (18 files) — Drop Namespace

The `Explorer` namespace object is eliminated. Every `Explorer.foo = function()` becomes `export function foo()`. Every call site imports what it needs.

**Action registry (new file: `explorer/action-registry.js`):**

Replaces `Explorer.initEventDelegation()` action map. Each handler is imported from its source module:

```javascript
import { setView, selectAllVisible, filterTree } from './app.js';
import { deleteObject, createObject } from './data-loading.js';
// ...

export const actionHandlers = {
    'setView': setView,
    'deleteObject': deleteObject,
    // ... ~50 entries
};
```

**Shared state (new file: `explorer/state.js`):**

Extracted from `main.js`:
```javascript
export const state = { allObjects: [], selectedKeys: new Set(), ... };
```

Modules import state directly: `import { state } from './state.js'`

**Console debugging:**

Optional debug export in `main.js`:
```javascript
import { state } from './state.js';
import { loadObjects } from './data-loading.js';
window.__debug = { state, loadObjects, ... };
```

### Template Changes

**base.html:** 10 script tags become 1 module script tag. Vendor scripts (Bootstrap) stay as regular `<script>`.

**Page templates:** Each `{% block scripts %}` gets one `<script type="module">`.

**Inline Jinja scripts:** e.g., explorer.html init becomes:
```html
<script type="module">
import { init } from '{{ url_for("static", filename="js/explorer/main.js") }}';
init('{{ config_path }}');
</script>
```

**Module defer behavior:** `type="module"` scripts are deferred by default (run after DOM parse). This is better than current behavior — no `DOMContentLoaded` listeners needed.

### What Doesn't Change

- Python backend (zero changes)
- CSS
- Vendor scripts (Bootstrap, Cytoscape, Dagre — stay as global `<script>`)
- API contracts (same endpoints, field names, request/response shapes)
- `data-action` HTML attributes (same attributes, wired through action registry)
- Python tests
- `docs-data.js` content (just gets `export` added)

## Known Trade-offs

- **Console debugging harder:** Functions not on `window` unless explicitly wired via `__debug`
- **More verbose imports:** Every file gains an import block
- **Extra coordination step:** New explorer actions need an import in `action-registry.js`
- **No bundling:** 18 explorer modules = 18 HTTP requests on first load (negligible on localhost, measurable on slow networks)

## Verification Plan

1. Every page loads without console errors (6 pages)
2. Explorer: create, edit, delete, move objects
3. Explorer: context menu actions, bulk operations, analysis panel
4. Commit dialog: diff display, apply, discard
5. Git page: status, diff, commit, history
6. Dependencies page: graph renders, search works
7. Settings, Logs, Backups, Docs: basic functionality

## Risk Areas

- Explorer action registry — 50+ handlers, each needs correct import
- `commit-dialog.js` — imports from 6 different modules
- Any function called via string reference (e.g., `onclick="foo()"`) that gets missed — silently breaks because modules don't put functions on window
- Rollback: single branch, `git revert` if fundamentally broken
