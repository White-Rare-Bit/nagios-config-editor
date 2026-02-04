# CLAUDE.md

## Setup & Dependencies

```bash
# Install and run
pip install -r requirements.txt
python3 app.py
# Access at http://localhost:8080
```

Dependencies: `flask>=2.0.0,<4.0.0`

### Claude for Chrome

- Use `read_page` to get element refs from the accessibility tree
- Use `find` to locate elements by description
- Click/interact using `ref`, not coordinates
- NEVER take screenshots unless explicitly requested by the user

## Reference Documentation

Detailed docs available on-demand in `.claude/`:

| File | Content |
|------|---------|
| ROUTES_REFERENCE.md | All 70+ API routes with descriptions |
| API_REFERENCE.md | Service function signatures |
| STAGING_REFERENCE.md | Staging system internals, apply phases, undo stack |
| GIT_REFERENCE.md | Git integration patterns, timeouts, identity |
| FILE_OPS_REFERENCE.md | File operations, block detection, path safety |
| TYPOGRAPHY_REFERENCE.md | Typography tokens, font system |
| DECISION_LOG.md | Historical architecture decisions |

## Backend Architecture Patterns

### App Factory Pattern

```python
# Initialization in app.py
def create_app(config_path=None) -> Flask:
    server_config = load_server_config()
    app.extensions['server_config'] = server_config
    app.extensions['service'] = NagiosService(...)
    app.extensions['staging'] = StagingManager(...)
    app.extensions['backup'] = BackupManager(...)
    app.extensions['git'] = GitService(...)
    app.extensions['op_logger'] = OperationLogger(...)
    return app
```

Service access in routes:

```python
from .helpers import get_service, get_staging_manager, get_backup_manager, get_server_config

service = get_service()         # current_app.extensions['service']
sm = get_staging_manager()      # current_app.extensions['staging']
bm = get_backup_manager()       # current_app.extensions['backup']
cfg = get_server_config()       # current_app.extensions['server_config']
```

### Thread Safety

- **NagiosService**: `multiprocessing.Lock` for all mutations
- **GitService**: `multiprocessing.Lock` for multi-step mutations
- **StagingManager**: Atomic file writes (temp file + rename)

Uses `multiprocessing.Lock` (not `threading.Lock`) because WSGI servers may use multiple processes.

```python
with self._lock:
    # Multi-step mutation
    # Parser reload after write
```

### OperationResult Pattern

All service methods return `OperationResult(success: bool, error: str = None, data: Any = None)`:

```python
result = service.create_object(file, obj_type, attrs)
if result.success:
    # Use result.data
else:
    # Handle result.error
```

### Server Configuration

Settings in `config/settings.json`. Precedence: env vars > config file > defaults.

```python
from server_config import load_config, save_config, update_config
config = load_config()
```

## Backend Module Index

| Module | What | When |
|--------|------|------|
| app.py | Flask app factory, service init | Changing startup |
| server_config.py | Config load/save, env overrides | Changing settings |
| nagios_service.py | CRUD operations, apply_* phases | Domain operations |
| staging_manager.py | Staging state, locks, undo stack | Staging behavior |
| backup_manager.py | Zip backups, restore | Backup features |
| nagios_parser.py | Parse .cfg files | Parsing logic |
| nagios_writer.py | Write .cfg files | Write format |
| nagios_model.py | NagiosObject, NAME_FIELDS, REFERENCE_FIELDS | Object types |
| file_operations.py | Atomic file ops, path safety | File manipulation |
| git_service.py | Git wrapper, retry logic | Git commands |
| validator.py | nagios -v validation | Validation |
| operation_logger.py | Structured JSON logging | Log format |
| audit_service.py | Audit log writer | Audit events |

## Frontend Module Index

### Core JavaScript

| Module | What |
|--------|------|
| app.js | Global utilities: escapeHtml, formatDate, debounce, keyboard shortcuts |
| js/base.js | Session/lock management, toast, commit dialog, staging state |
| js/api-client.js | Fetch wrapper with error handling, staging headers |

### Explorer Modules (static/js/explorer/)

| Module | What |
|--------|------|
| main.js | Namespace, shared state (allObjects, selections, staging maps) |
| app.js | Tree rendering, filtering, selection, autocomplete, dependencies |
| object-editor.js | Center pane attribute editor, validation, staging |
| file-operations.js | Target pane (file tree), move/create operations |
| context-menu.js | Right-click menus, dialogs, preview modal |
| dialogs.js | Move/create/delete dialogs, bulk operations |
| data-loading.js | Initial load, refresh, server sync |
| state-management.js | State persistence, sync, refreshAfterObjectChange() |
| drag-drop.js | Drag-and-drop for objects and files |
| analysis.js | Template detection, inheritance, suggestions |
| ui-utils.js | formatObjectName, buildBreadcrumb, badges |

### Page-Specific JS

git.js, backups.js, audit-log.js, dependencies.js, settings.js, find-replace.js, bulk-rename.js, bulk-attributes.js, reorganize.js, smart-grouping.js, inheritance.js, validate.js, health-check.js

## Style Guides

| Guide | What |
|-------|------|
| .claude/BUTTON_STYLE_GUIDE.md | Button styling: .nbe-btn variants, sizes, states |

## Frontend Architecture Patterns

### Event Delegation

Uses `data-action` attributes for click handlers:

```javascript
document.addEventListener('click', function(e) {
    const actionEl = e.target.closest('[data-action]');
    if (actionEl) {
        const handler = actionHandlers[actionEl.dataset.action];
        if (handler) handler(e);
    }
});
```

Add actions to `actionHandlers` map in base.js.

### ApiClient Pattern

```javascript
const result = await ApiClient.get('/api/endpoint', { silent: true });
if (result.success) { /* use result.data */ }

const result = await ApiClient.post('/api/endpoint', { key: 'value' });
```

Features: automatic staging headers, `{success, data, error}` format, toast notifications.

### Global Functions

**app.js**: `escapeHtml()`, `formatDate()`, `debounce()`, `escapeRegex()`, `copyToClipboard()`, `setButtonLoading()`

**base.js**: `showToast()`, `showConfirmDialog()`, `getSessionId()`, `getUserIdentity()`, `getStagingHeaders()`

### Explorer State Management

```javascript
Explorer.state = {
    allObjects: [],
    selectedKeys: new Set(),
    pendingEdits: new Map(),
    stagedMoves: new Map(),
    undoStack: [],
    // ...
};
```

### UI Refresh After Object Changes

```javascript
Explorer.refreshAfterObjectChange(options = {
    skipTree: false,
    skipCenter: false,
    skipTarget: false,
    skipSuggestions: false,
    skipCommit: false
});
```

Call after ANY object mutation (delete, create, edit, move, undo).

### Reference Field Synchronization

Reference fields duplicated across 4 locations that must stay in sync:

| Location | Purpose |
|----------|---------|
| nagios_model.py:REFERENCE_FIELDS | Backend dependency analysis |
| object-editor.js:ATTR_REFERENCE_MAP | Autocomplete hints (~line 43) |
| main.js:referenceAttrs | Dependencies refresh triggers (~line 136) |
| app.js:loadCenterReferences:referenceFields | Center pane deps (~line 2173) |

Each location has sync comments. Only sync when adding Nagios reference fields (rare).

### Design Tokens (tokens.css)

```css
var(--nbe-primary)      /* #006fcc */
var(--nbe-success)      /* Green for create */
var(--nbe-danger)       /* Red for delete */
var(--nbe-warning)      /* Orange for move */
var(--nbe-text-primary) /* #1f2937 */
var(--nbe-bg-surface)   /* White */
var(--nbe-space-md)     /* 12px */
var(--nbe-radius-md)    /* 4px */
```

Use tokens instead of hard-coded values.

### Template Inheritance

```
base.html (master)
  ├─ navbar with commit button
  ├─ lock banner
  ├─ global dialogs
  └─ blocks: title, extra_css, content, scripts
```

Load order: Bootstrap CSS → tokens.css → style.css → page CSS → Bootstrap JS → app.js → api-client.js → base.js → page JS

## Staging System Overview

True staging: NO changes written to disk until "Apply".

### Lock Management

- Session-based: first edit acquires lock
- Check with `sm.can_modify(session_id)`
- Release on apply, discard, or clear

### Staged Operations

| Type | Field |
|------|-------|
| Object edits | pendingEdits |
| Object moves | stagedMoves |
| Object creates | stagedCreations |
| Object deletes | stagedObjectDeletions |
| File creates | stagedFileCreations |
| File deletes | stagedFileDeletions |
| File moves | stagedFileMoves |
| Folder creates | stagedFolderCreations |
| Folder deletes | stagedFolderDeletions |
| Folder moves | stagedFolderMoves |

### Stable Keys

Objects identified by `"source_file|object_type|name"` instead of global_index.

See `.claude/STAGING_REFERENCE.md` for apply phase order, undo stack, conflict detection.

## Error Handling

### HTTP Status Codes

| Code | Use Case |
|------|----------|
| 200 | Success |
| 400 | Invalid input |
| 404 | Not found |
| 409 | Staging conflicts |
| 423 | Locked by another session |
| 500 | Internal error |

### Backup on Mutation

All mutating operations create backup first:

```python
bm = get_backup_manager()
backup_path = bm.create_backup("pre_operation_name")
```

## Key Conventions

### Naming

- **Python**: snake_case (session_id, user_name)
- **JavaScript functions**: camelCase (showToast, escapeHtml)
- **CSS classes**: kebab-case (commit-btn, toast-message)
- **CSS variables**: `--nbe-*` namespace

### Cross-Language (API ↔ Frontend)

API returns snake_case. Frontend uses camelCase locally but preserves API field names in requests.

### State Management

- **Explorer**: `Explorer.state`
- **Session**: localStorage (`nagios_session_id`, `nagios_user_name`)
- **Lock**: `baseState` in base.js, synced with `window.isEditingLocked`

### Keyboard Shortcuts

- Global: Escape, Ctrl+Z, ?
- Explorer: Space (preview), M (move), Delete
- Selection: Ctrl+Click (toggle), Shift+Click (range)

Add to `handleGlobalKeydown` in app.js.
