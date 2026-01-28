# CLAUDE.md

## Setup & Dependencies

### Python Backend

```bash
# Install Python dependencies
pip install -r requirements.txt
```

Dependencies:
- `flask>=2.0.0,<4.0.0` - Web framework

### Frontend Testing (Jest)

```bash
# Install Node.js dependencies
npm install

# Run tests with coverage
npm test

# Run tests in watch mode
npm run test:watch
```

Test configuration in `package.json`:
- Test environment: jsdom
- Coverage: `static/**/*.js`
- Test files: `tests/frontend/**/*.test.js`

### Running the Application

```bash
# Development server (Flask built-in)
python3 app.py

# Access at http://localhost:8080
```

### Running Backend Tests

```bash
# Run pytest
python3 -m pytest tests/ --tb=short -q

# Run with coverage
python3 -m pytest tests/ --cov=. --cov-report=term-missing
```

## Backend Architecture Patterns

### App Factory Pattern

```python
# Initialization in app.py
def create_app(config_path=None) -> Flask:
    # Load server config from config/settings.json
    server_config = load_server_config()

    # Service instances stored in app.extensions dict
    app.extensions['server_config'] = server_config
    app.extensions['service'] = NagiosService(...)
    app.extensions['staging'] = StagingManager(...)
    app.extensions['backup'] = BackupManager(...)
    app.extensions['git'] = GitService(...)
    app.extensions['op_logger'] = OperationLogger(...)
    return app
```

Service access in routes via helpers:

```python
from .helpers import get_service, get_staging_manager, get_backup_manager, get_server_config

service = get_service()         # → current_app.extensions['service']
sm = get_staging_manager()      # → current_app.extensions['staging']
bm = get_backup_manager()       # → current_app.extensions['backup']
cfg = get_server_config()       # → current_app.extensions['server_config']
```

### Dependency Injection

All services accept `op_logger` parameter for structured logging:

```python
service = NagiosService(config_path, staging_manager, op_logger=op_logger)
op_logger.info('service', 'create_object', params={'file': path}, result='success')
```

Services are injected at app startup and accessed via `current_app.extensions` in request context.

### Thread Safety

- **NagiosService**: Holds internal `_lock` (multiprocessing.Lock) for all mutations
- **GitService**: Serializes multi-step mutations (commit, restore) via `_lock` (multiprocessing.Lock)
- **StagingManager**: Atomic file writes using temp file + rename pattern
- **BackupManager**: No internal locking (operations are serialized by StagingManager)

Note: Uses `multiprocessing.Lock` (not `threading.Lock`) because Flask's development server and production WSGI servers may use multiple processes. A threading.Lock only protects within a single process.

Pattern:

```python
with self._lock:
    # Multi-step mutation
    # Parser reload after write
```

Context manager for parser modification:

```python
with service.modification_context() as parser:
    # Modify parser.objects
    # Write changes
    # Lock released automatically
```

### Retry Logic (Git Operations)

GitService implements exponential backoff for transient lock errors:

```python
_TRANSIENT_PATTERNS = ('index.lock', 'unable to create', 'cannot lock ref')

# In _run_git():
if retry and any(pat in combined for pat in _TRANSIENT_PATTERNS):
    delay = (0.1 * (2 ** attempt)) + random.uniform(0, 0.05)
    time.sleep(delay)
    continue  # Retry up to 3 times
```

### OperationResult Pattern

All service methods return `OperationResult(success: bool, error: str = None, data: Any = None)`:

```python
result = service.create_object(file, obj_type, attrs)
if result.success:
    # Use result.data if present
else:
    # Handle result.error
```

### Server Configuration

All server-wide settings are consolidated in `config/settings.json`:

```json
{
  "version": 1,
  "paths": {
    "nagios_config_path": "./sample-config",
    "backup_path": null,
    "nagios_bin": "/usr/local/nagios/bin/nagios",
    "nagios_cfg": "./sample-config/nagios.cfg"
  },
  "logging": {
    "enabled": true,
    "log_level": "INFO",
    "log_dir": "logs",
    "log_filename": "operations.jsonl",
    "max_file_size_mb": 10,
    "max_backup_files": 5
  }
}
```

**Precedence order** (highest to lowest):
1. Environment variables (NAGIOS_CONFIG_PATH, BACKUP_PATH, NAGIOS_BIN, NAGIOS_CFG)
2. `config/settings.json` file
3. Default values

**Key functions** in `server_config.py`:

```python
from server_config import load_config, save_config, update_config

config = load_config()           # Load with env var overrides
save_config(config)              # Persist to file
config = update_config({'nagios_bin': '/new/path'})  # Update and save
```

**Migration**: Legacy `logging_config.json` is automatically migrated to `config/settings.json` on first load.

## Backend Module Index

| Module | What | When |
|--------|------|------|
| app.py | Flask app factory, service initialization, extensions dict, loads server_config | Changing startup logic or adding new services |
| server_config.py | Centralized config: load/save config/settings.json, env var overrides, migration | Changing config schema, adding settings, or modifying persistence |
| nagios_service.py | Business logic layer: CRUD operations, apply_* phases, parser wrapper, thread-safe mutations | Adding domain operations or changing staging apply order |
| staging_manager.py | Staging state persistence, session lock management, StagingStatus enum, undo stack, checksum tracking | Modifying staging behavior, lock semantics, or conflict detection |
| backup_manager.py | Zip-based timestamped backups, restore with safety backup, metadata tracking | Adding backup features or changing backup format |
| nagios_parser.py | Parse .cfg files into NagiosObject list, file discovery, brace-aware parsing | Changing parsing logic or adding object type support |
| nagios_writer.py | Write NagiosObject list to .cfg files, atomic writes, formatting | Changing write format or adding object formatting rules |
| nagios_model.py | Domain model: NagiosObject, NAME_FIELDS, REFERENCE_FIELDS, OperationResult, formatting | Adding object types, name fields, or reference field rules |
| file_operations.py | Atomic file operations: edit, create, delete, move objects in .cfg files, path safety checks | Modifying direct file manipulation or adding security checks |
| git_service.py | Git subprocess wrapper: status, diff, commit, discard, restore, log, retry logic, thread safety | Adding git commands or changing timeout/retry behavior |
| validator.py | Nagios configuration validation via nagios -v subprocess, error/warning parsing | Changing validation logic or output parsing |
| operation_logger.py | Structured logging to JSON, log levels, rotation, context fields | Adding log fields or changing log format |
| audit_service.py | Audit log writer: operation history, user tracking, timestamp, archival | Adding audit event types or changing audit format |
| logging_config.py | Logging config wrapper: reads from server_config, backward compatibility | Legacy code using logging_config functions |

## Backend Routes Index

### Core Object Operations (routes/objects.py)

| Route | Method | What |
|-------|--------|------|
| /api/objects | GET | List objects with optional type/search filter |
| /api/objects/by-key/<stable_key> | GET | Get object by stable key (file\|type\|name) |
| /api/object/update | POST | Update single object attributes |
| /api/objects/batch-update | POST | Update multiple objects atomically |
| /api/objects/create | POST | Create new object in target file |
| /api/objects/update-references | POST | Update references after rename (renames array) |
| /api/delete-objects | POST | Delete multiple objects, optional reference cleanup |
| /api/clone-objects | POST | Clone objects with name transformation |

### Staging Operations (routes/staging.py)

| Route | Method | What |
|-------|--------|------|
| /api/staging | GET | Get full staging data (shared across sessions) |
| /api/staging | POST | Save staged changes to staging.json (no disk writes) |
| /api/staging | DELETE | Clear all staging data and release lock |
| /api/staging/info | GET | Lightweight summary (counts only, for polling) |
| /api/staging/info-extended | GET | Extended summary with file/folder operation counts |
| /api/staging/apply | POST | Apply all staged changes to disk (10-phase process) |
| /api/staging/virtual-tree | GET | Merged view of objects with staged changes applied (preview) |
| /api/staging/undo | POST | Pop and reverse last staged operation |
| /api/staging/conflicts | GET | Detect external file modifications via checksums |
| /api/staging/diff | GET | Git diff + staging metadata for commit dialog |
| /api/staging/analyze-references | GET | Count references for pending name changes |
| /api/staging/commit | POST | Apply staged changes + clear lock (deprecated, use apply) |

### Git Integration (routes/git.py)

| Route | Method | What |
|-------|--------|------|
| /api/git/identity | GET | Get configured git user.name and user.email |
| /api/git/identity | POST | Set git user.name and user.email (local config) |
| /api/git/status | GET | Git status porcelain, excludes backups/staging |
| /api/git/diff | POST | Get diff for specific file or all changes |
| /api/git/commit | POST | Stage and commit changes with user identity |
| /api/git/discard | POST | Discard changes to specific file |
| /api/git/discard-all | POST | Hard reset + clean untracked files |
| /api/git/clear-history | POST | Delete .git, reinitialize with fresh commit |
| /api/git/log | GET | Commit history (limit 200), null-byte separated |
| /api/git/restore | POST | Restore working dir to specific commit |

### File/Folder Operations (routes/files.py)

| Route | Method | What |
|-------|--------|------|
| /api/files | GET | List all .cfg files in config directory |
| /api/folders | GET | List all folders in config directory |
| /api/files/create | POST | Create new .cfg file with header comment |
| /api/folders | POST | Create new folder |
| /api/files/move | POST | Move file to new path (rename or relocate) |
| /api/folders/move | POST | Move folder to new path |
| /api/files/relocate | POST | Move file and update object source_file references |
| /api/folders/relocate | POST | Move folder and update all contained object references |
| /api/files/<file_path> | DELETE | Delete specific file |
| /api/folders/<folder_path> | DELETE | Delete folder recursively |
| /api/delete | POST | Batch delete files/folders |

### Backup Management (routes/backups.py)

| Route | Method | What |
|-------|--------|------|
| /api/backups | GET | List all backups (zip + legacy directory format) |
| /api/backups | POST | Create timestamped zip backup with metadata |
| /api/backups/<name>/restore | POST | Restore from backup (creates safety backup first) |
| /api/backups/all | DELETE | Delete all backups (with confirmation) |
| /api/backups/<name> | DELETE | Delete specific backup |

### Bulk Operations (routes/bulk_ops.py)

| Route | Method | What |
|-------|--------|------|
| /api/search | POST | Search objects by query, type, field, regex |
| /api/preview-rename | POST | Preview bulk rename with pattern/prefix/suffix |
| /api/apply-rename | POST | Apply bulk rename to selected objects |
| /api/preview-replace | POST | Preview find/replace on object attributes |
| /api/apply-replace | POST | Apply find/replace to selected objects |
| /api/move-objects | POST | Bulk move objects to target file |
| /api/diff/rename | POST | Generate diff for bulk rename operation |
| /api/bulk-attributes/preview | POST | Preview bulk attribute set/append/delete |
| /api/bulk-attributes/apply | POST | Apply bulk attribute changes |

### Analysis (routes/analysis.py)

| Route | Method | What |
|-------|--------|------|
| /api/dependencies | GET | Build dependency graph with nodes/edges |
| /api/inheritance/list/<type> | GET | List all objects of type (for inheritance tree) |
| /api/inheritance/<type>/<name> | GET | Get full inheritance chain for object |
| /api/smart-grouping/suggest | GET | Suggest groupings based on patterns |
| /api/smart-grouping/create | POST | Create folder and reorganize objects by pattern |
| /api/smart-grouping/add-to-group | POST | Add objects to existing folder |

### Validation & Health (routes/validation.py)

| Route | Method | What |
|-------|--------|------|
| /api/reload | POST | Force reload parser (clears cache) |
| /api/summary | GET | Object counts by type, file count, config path |
| /api/validate | POST | Run nagios -v, return errors/warnings |
| /api/validate/check | GET | Check if nagios binary exists |
| /api/health-check | GET | Run sanity checks (orphans, circular deps, templates) |

### Settings & Logging (routes/settings.py)

| Route | Method | What |
|-------|--------|------|
| /api/settings | GET | Get all app settings (identity, git, paths) |
| /api/settings | POST | Update settings (identity, nagios paths) |
| /api/settings/browse | POST | Browse filesystem for directory selection |
| /api/settings/logging | GET | Get logging configuration |
| /api/settings/logging | POST | Update logging configuration (levels, rotation) |
| /api/logs/operations | GET | Fetch operation logs (JSON Lines format) |
| /api/logs/operations/download | GET | Download operation logs as file |
| /api/logs/frontend | POST | Write frontend error logs to server |
| /api/audit-log | GET | Get audit log entries (operation history) |
| /api/audit-log | POST | Write custom audit log entry |
| /api/audit-log/clear | POST | Clear current audit log (archives old) |
| /api/audit-log/archives | GET | List archived audit logs |
| /api/audit-log/archives/<filename> | GET | Download specific audit log archive |

### Page Routes (routes/pages.py)

All page routes render Jinja2 templates extending base.html:

| Route | Template | What |
|-------|----------|------|
| / | explorer.html | Main explorer (three-pane layout) |
| /objects | objects.html | Legacy object browser (deprecated) |
| /bulk-rename | bulk_rename.html | Bulk rename interface |
| /find-replace | find_replace.html | Find/replace interface |
| /reorganize | reorganize.html | File/folder reorganization |
| /audit-log | audit_log.html | Audit log viewer |
| /backups | backups.html | Backup management |
| /validate | validate.html | Nagios validation results |
| /dependencies | dependencies.html | D3 dependency graph |
| /git | git.html | Git page with diff viewer |
| /settings | settings.html | Settings and configuration |
| /health-check | health_check.html | Config health checks |
| /bulk-attributes | bulk_attributes.html | Bulk attribute editor |
| /inheritance | inheritance.html | Inheritance tree visualization |
| /smart-grouping | smart_grouping.html | Smart grouping suggestions |

## Frontend Module Index

### Core JavaScript (static/)

| Module | What | When |
|--------|------|------|
| app.js | Global utilities: escapeHtml, formatDate, debounce, keyboard shortcuts, tooltip init | Adding global utility functions or app-wide event handlers |
| js/base.js | Session/lock management, toast notifications, global commit dialog, staging state, git operations UI | Modifying lock UI, commit workflow, or toast behavior |
| js/api-client.js | Centralized fetch wrapper with error handling, staging headers, toast integration | Changing API call patterns or error handling |

### Explorer Modules (static/js/explorer/)

Modular architecture using shared `Explorer` namespace defined in main.js.

| Module | What | When |
|--------|------|------|
| main.js | Namespace definition, shared state (allObjects, selections, staging maps, undo stack, UI state) | Understanding state structure or initialization flow |
| app.js | Tree rendering, filtering, selection logic, autocomplete, reference/inheritance display, dependency object detection (getEffectiveAttrs, findDependencyObjects, formatFailureCriteria helpers) | Modifying tree UI, search, object relationship views, or dependency visualization |
| object-editor.js | Center pane attribute editor, validation, staging edits, create/edit/delete workflows | Changing object editing UI or attribute manipulation |
| file-operations.js | Target pane (file tree), move/create operations, folder management, drag targets | Modifying file tree or move operations UI |
| context-menu.js | Right-click menus, dialogs (rename, clone, delete), preview modal, keyboard shortcuts | Adding context menu items or dialog types |
| dialogs.js | Move dialog, create dialog, delete confirmations, bulk operation dialogs | Changing dialog UI or bulk operation flows |
| data-loading.js | Initial load, refresh, server sync, pending changes polling | Modifying data loading or sync behavior |
| state-management.js | State persistence (staging, undo), sync with server, lock-aware operations, refreshAfterObjectChange() for post-mutation UI refresh | Changing how state syncs or persists, after any object mutation (delete, create, edit, move, undo) |
| drag-drop.js | Drag-and-drop for objects and files, auto-expand folders, drop zone highlighting | Modifying drag-drop behavior or visual feedback |
| analysis.js | Template detection, inheritance analysis, issue detection, suggestions tab | Adding analysis features or suggestion logic |
| ui-utils.js | Common UI helpers: formatObjectName, buildBreadcrumb, status badges | Adding UI formatting utilities |

### Page-Specific JavaScript (static/js/)

| Module | What | When |
|--------|------|------|
| objects.js | Legacy object browser: search, syntax highlighting, edit modal | Maintaining legacy object browser page |
| git.js | Git page: file list, diff viewer, commit/discard UI, tab switching | Modifying git page UI or diff display |
| backups.js | Backup page: list backups, restore modal, delete confirmations | Adding backup management features |
| audit-log.js | Audit log: filtering, pagination, event type display | Modifying audit log UI or filters |
| dependencies.js | Graph view: D3 dependency graph, zoom/pan, legend, object type filtering (1932 lines) | Changing graph visualization or layout |
| settings.js | Settings page: identity config, git preferences, config path management | Adding settings fields or validation |
| find-replace.js | Find/replace: search, preview, bulk replacement | Modifying search or replace logic |
| bulk-rename.js | Bulk rename: pattern-based renaming, preview | Changing bulk rename UI |
| bulk-attributes.js | Bulk attribute editing: multi-select, batch updates | Modifying bulk attribute operations |
| reorganize.js | Reorganize page: file/folder restructuring | Changing reorganization UI |
| smart-grouping.js | Smart grouping: auto-suggest grouping based on patterns | Modifying grouping logic |
| inheritance.js | Inheritance visualization: template hierarchy | Changing inheritance display |
| validate.js | Validation page: nagios -v output display | Modifying validation UI |
| health-check.js | Health check page: config sanity checks | Adding health check rules |

### Templates (templates/)

| Template | What | When |
|----------|------|------|
| base.html | Master template: navbar, dialogs (commit, confirm, git result, identity, shortcuts), inline styles, script loading order | Modifying global UI structure or adding app-wide dialogs |
| explorer.html | Object explorer: three-pane layout (tree, editor, files), extends base.html | Changing explorer page layout |
| git.html | Git page: sidebar (filters), main content (file list, diff viewer) | Modifying git page structure |
| backups.html | Backup page: backup list, restore controls | Changing backup page layout |
| audit_log.html | Audit log: filter sidebar, event table | Modifying audit log layout |
| dependencies.html | Graph view: sidebar (filters), SVG container for D3 | Changing graph page structure |
| settings.html | Settings: forms for identity, git config, paths | Adding settings sections |

### CSS Architecture (static/css/)

| File | What | When |
|------|------|------|
| tokens.css | Design system: colors, spacing, typography, shadows, z-index scale (PAN-OS 11 inspired) | Changing design tokens or adding theme variables |
| style.css | Global styles: cards, tables, object rows, code highlighting | Modifying app-wide component styles |
| explorer.css | Explorer three-pane layout, tree styles, editor pane, target pane | Changing explorer-specific UI |
| git.css | Git page: file list, diff viewer, staging preview | Modifying git page styles |
| backups.css | Backup list, restore modal | Changing backup page styles |
| dependencies.css | Graph view: legend, zoom controls, node/edge styles | Modifying graph visualization styles |
| audit_log.css | Audit log table, filter chips | Changing audit log styles |
| inheritance.css | Inheritance tree visualization | Modifying inheritance display |
| settings.css | Settings page forms and sections | Changing settings page styles |

Inline styles in base.html: Dialogs, toasts, commit UI, lock banner, keyboard shortcuts. DO NOT refactor to external CSS without verifying no FOUC (Flash of Unstyled Content).

## Style Guides

| Guide | What | When |
|-------|------|------|
| .claude/BUTTON_STYLE_GUIDE.md | Canonical button styling system: .nbe-btn variants, sizes, states, migration path | Creating/modifying buttons, converting legacy button classes |

## Frontend Architecture Patterns

### Event Delegation

Uses `data-action` attributes for click handlers instead of inline `onclick`:

```javascript
// In base.js - single event listener on document
document.addEventListener('click', function(e) {
    const actionEl = e.target.closest('[data-action]');
    if (actionEl) {
        const handler = actionHandlers[actionEl.dataset.action];
        if (handler) handler(e);
    }
});
```

Add new actions to `actionHandlers` map in base.js. Use `data-action="action-name"` in HTML.

### ApiClient Pattern

All API calls use `ApiClient` from api-client.js for consistent error handling:

```javascript
// Example: GET request with silent mode
const result = await ApiClient.get('/api/endpoint', { silent: true });
if (result.success) {
    // Use result.data
} else {
    // result.error already shown as toast unless silent: true
}

// Example: POST with data
const result = await ApiClient.post('/api/endpoint', { key: 'value' });
```

Features: automatic staging headers (X-Session-Id), standardized `{success, data, error}` format, toast notifications, timeout support.

### Global Functions

Defined in app.js (loaded first):

- `escapeHtml(text)` - HTML entity encoding (used everywhere)
- `formatDate(dateStr, useRelative=true)` - Relative time formatting ("2 hours ago")
- `debounce(func, wait)` - Debounce for search inputs
- `escapeRegex(str)` - Escape regex special chars
- `copyToClipboard(text)` - Clipboard API with fallback
- `setButtonLoading(button, loading)` - Button loading state

Defined in base.js (loaded second):

- `showToast(message, type, duration)` - Toast notifications with message filtering
- `showConfirmDialog(options)` - Promise-based confirmation dialogs
- `getSessionId()` / `getUserIdentity()` - Session/identity management
- `getStagingHeaders()` - Headers for staging API calls

### Explorer State Management

Shared state in `Explorer.state` (defined in explorer/main.js):

```javascript
Explorer.state = {
    allObjects: [],           // All loaded objects
    selectedKeys: new Set(),  // Selected object keys
    pendingEdits: new Map(),  // global_index -> {original, edited, object}
    stagedMoves: new Map(),   // objKey -> {targetFile, originalFile, object}
    undoStack: [],           // Undo history
    // ... more staging state
};
```

Modules access via `Explorer.state` or local `state` alias. Functions exported on `Explorer` namespace for cross-module calls.

### UI Refresh After Object Changes

Centralized refresh function in state-management.js handles UI updates after object mutations:

```javascript
Explorer.refreshAfterObjectChange(options = {
    skipTree: false,       // Skip tree re-render
    skipCenter: false,     // Skip center pane update
    skipTarget: false,     // Skip target pane update
    skipSuggestions: false, // Skip suggestions panel refresh
    skipCommit: false      // Skip commit UI badge update
});
```

**When to call**: After ANY object mutation operation:
- Object delete (staged or committed)
- Object create (staged or committed)
- Object edit (staged or committed)
- Object move (staged)
- Undo operation

**What it does**:
1. Rebuilds object tree with updated staging badges (if not skipped)
2. Updates target pane (file tree) (if not skipped)
3. Syncs center pane with current object state if an object is selected (if not skipped)
4. Refreshes suggestions panel with force flag to bypass debounce (if not skipped)
5. Updates commit UI badge counts (if not skipped)

Note: Does NOT clear selection or hide center pane. Caller is responsible for selection management and center pane visibility if needed.

**Options parameter**: Allows skipping specific components for performance when partial refresh is sufficient.

### Reference Field Synchronization

Reference field definitions are duplicated across 4 locations that must stay in sync:

| Location | Purpose | Type |
|----------|---------|------|
| nagios_model.py:REFERENCE_FIELDS | Authoritative source, backend dependency analysis | Python dict |
| object-editor.js:ATTR_REFERENCE_MAP | Autocomplete hints for attribute editor (~line 43) | JS object |
| main.js:referenceAttrs | Triggers for Dependencies/Dependents refresh (~line 136) | JS array |
| app.js:loadCenterReferences:referenceFields | Dependency detection for center pane (~line 2173) | JS object |

**When to sync**: Adding new Nagios reference fields (rare - spec frozen since 2013).

**Sync comments**: Each location has comment documenting all 4 sync points.

**Why duplicated**: Backend needs for graph analysis, frontend needs for real-time UI without API calls, different representations required (dict vs object vs array).

### Dependency Object Detection

Helper functions in app.js for hostdependency/servicedependency display:

| Function | What | Returns |
|----------|------|---------|
| getEffectiveAttrs(obj) | Get attributes respecting pending edits (module-level, ~line 2155) | Object attributes (staged or original) |
| findDependencyObjects(obj, allObjects) | Find dependency rules where obj is master or dependent (~line 2231) | {asMaster: [...], asDependent: [...]} |
| formatFailureCriteria(depObj) | Format execution/notification criteria as compact string (~line 2310) | "(skip: c,u)" or "(skip: c,u; notify: w,c)" |

**Matching logic**:
- hostdependency: Matches host_name (master) and dependent_host_name (dependent)
- servicedependency: Matches service_description with host_name scoping; hostgroup_name services cannot be matched (requires expansion not implemented)

**Display**: Dependency objects shown inline in Dependencies/Dependents sections with "rule" badge and failure criteria.

### Toast Message Filtering

Toast notifications in base.js filter out noisy messages. Only shows:

- All error messages
- Important success/info messages (contains: "discarded", "committed", "valid", "restored", "cleared", "wiped", "configure", "settings")
- Filters out routine operation confirmations

### Template Inheritance

```
base.html (master)
  ├─ navbar with commit button
  ├─ lock banner
  ├─ global dialogs (commit, confirm, git result, shortcuts)
  └─ blocks: title, extra_css, content, scripts

All pages extend base.html and override blocks
```

Load order: Bootstrap CSS → tokens.css → style.css → page CSS → Bootstrap JS → app.js → api-client.js → base.js → page JS

### Design Tokens (tokens.css)

All colors, spacing, typography use CSS variables:

```css
var(--nbe-primary)           /* #006fcc */
var(--nbe-success)           /* Green for create */
var(--nbe-danger)            /* Red for delete */
var(--nbe-warning)           /* Orange for move */
var(--nbe-text-primary)      /* #1f2937 */
var(--nbe-bg-surface)        /* White */
var(--nbe-space-md)          /* 12px */
var(--nbe-radius-md)         /* 4px */
var(--nbe-shadow-sm)         /* Elevation */
```

Use tokens instead of hard-coded values. See tokens.css for complete reference.

## Staging System Architecture

The staging system implements true staging where NO changes are written to disk until user clicks "Apply".

### Lock Management

- **Session-based locking**: Only one session can edit at a time
- **Lock acquisition**: First edit by a session acquires lock via sessionId
- **Lock validation**: Every staging operation checks `sm.can_modify(session_id)`
- **Lock release**: Cleared on apply, discard, or explicit clear

Lock check pattern:

```python
if not sm.can_modify(session_id):
    return jsonify({'error': 'Staging is locked by another user'}), 423
```

### Staging State Transitions

```
EMPTY ──(first edit by session)──> ACTIVE ──(apply/clear)──> EMPTY
  ^                                   |
  |                                   v
  └──(clear)── RESTORE_PENDING <──(backup restore populates staging)
```

- **EMPTY**: No session owns staging, available for acquisition
- **ACTIVE**: Session holds lock, normal editing allowed
- **RESTORE_PENDING**: Backup restore populated staging, awaiting apply/discard

Status tracked via `StagingStatus` enum in `staging.json`.

### Staged Operations

All operations stored in `staging.json` until apply:

| Operation Type | Staging Field | Description |
|----------------|---------------|-------------|
| Object edits | pendingEdits | Attribute changes (original + edited dicts) |
| Object moves | stagedMoves | Move between files (source + target + insertPosition) |
| Object creates | stagedCreations | New objects (type + attrs + targetFile) |
| Object deletes | stagedObjectDeletions | Objects to delete (source_file + line_number) |
| File creates | stagedFileCreations | New .cfg files to create |
| File deletes | stagedFileDeletions | Files to delete |
| File moves | stagedFileMoves | File rename/relocate (sourcePath + targetPath) |
| Folder creates | stagedFolderCreations | New folders to create |
| Folder deletes | stagedFolderDeletions | Folders to delete recursively |
| Folder moves | stagedFolderMoves | Folder rename/relocate |

### Undo Stack

Each staged operation pushes an undo entry:

```python
{
    'id': uuid[:8],
    'type': 'edit' | 'move' | 'creation' | 'deletion' | 'file_create' | ...,
    'data': { ... operation-specific data ... },
    'description': "Edit host 'webserver01'",
    'timestamp': time.time()
}
```

Undo handler registry in `staging_manager.py`:

```python
UNDO_HANDLERS = {
    OperationType.EDIT: _undo_edit,
    OperationType.MOVE: _undo_move,
    # ... handlers for each operation type
}
```

### Conflict Detection

Base file checksums captured when staging begins:

```python
# When first edit to a file:
sm.update_base_checksums([file_path])

# Before apply:
conflicts = sm.detect_conflicts()  # Compares current vs base checksums
```

Apply is blocked if conflicts detected (423 status).

### Apply Phase Order

`POST /api/staging/apply` executes in this order to avoid conflicts:

1. **Folder creates** (parent → child sort)
2. **File creates**
3. **Object deletions** (reverse line order per file)
4. **Object moves** (file-based rewrite, computes final order)
5. **Object edits** (surgical replace)
6. **Object creations** (append to target files)
7. **File moves**
8. **Folder moves**
9. **File deletions**
10. **Folder deletions** (child → parent sort)

Each phase implemented as `service.apply_<phase>(staging_data, is_safe_path)`.

### Stable Keys

Objects identified by stable key `"source_file|object_type|name"` instead of global_index:

```python
stable_key = generate_stable_key(obj.source_file, obj.object_type, obj.get_name())
idx, obj = service.find_object_by_stable_key(stable_key)
```

Survives parser reloads and index changes during staging.

## File Operations Patterns

### Atomic Writes

All file operations use atomic pattern:

```python
# find_block_range() → character offsets
start_char, end_char = find_block_range(content, line_number)

# Brace-aware parsing (respects quotes)
new_content = content[:start_char] + new_block + content[end_char:]

# Direct write (no temp file needed - single operation)
Path(file_path).write_text(new_content)
```

### Block Detection

`find_block_range(content, line_number)` uses brace-counting parser:

- Handles nested braces in quotes
- Tracks quote state (`in_double_quote`, `in_single_quote`)
- Respects escape sequences (`\\"`)
- Returns character offsets `(start_char, end_char)`

### Path Safety

`is_safe_path(path, base_dir)` validates before all file operations:

- Null byte injection check
- Path traversal prevention (`..` in path)
- Symlink resolution
- Base directory containment verification

Used in all file/folder creation, move, delete operations.

### Move Object Pattern

Special handling for same-file vs cross-file moves:

```python
if source_real == target_real:
    # Same file: delete → add (with adjusted insert position)
    delete_object_from_file(source_file, source_line)
    add_object_to_file(target_file, obj_type, attrs, adjusted_insert_line)
else:
    # Cross-file: add → delete (prevents data loss on failure)
    add_object_to_file(target_file, obj_type, attrs, insert_line)
    delete_object_from_file(source_file, source_line)  # Rollback on failure
```

## Git Integration Patterns

### Subprocess Wrapper

All git operations via `_run_git(args, timeout, retry)`:

```python
# Timeout presets
TIMEOUT_QUERY = 5      # rev-parse, config lookups
TIMEOUT_STATUS = 10    # status, reset, branch
TIMEOUT_MUTATE = 30    # commit, checkout, clean, add, diff

# Retry on transient errors
_TRANSIENT_PATTERNS = ('index.lock', 'unable to create', 'cannot lock ref')
```

Returns `OperationResult` with `data=GitRunResult(stdout, stderr, returncode)`.

### Thread Safety

Multi-step mutations serialized via `self._lock`:

```python
with self._lock:
    # git add -A
    # git commit -m "..."
    # git rev-parse --short HEAD
    # All steps atomic from external perspective
```

### Identity Injection

User identity passed per-operation (not global config):

```python
git_svc.commit(
    message="Update hosts",
    user_name="John Doe",
    user_email="john@example.com"
)

# Executes: git -c user.name=... -c user.email=... commit -m "..."
```

### Diff Context Control

Frontend requests diff with context control:

```python
# Full file context (default)
git_svc.get_diff(filepath, full_file=True)  # Uses -U9999

# Limited context
git_svc.get_diff(filepath, context_lines=3)  # Uses -U3
```

Commit dialog includes context slider to reduce diff size.

## Error Handling Conventions

### Result Objects

All service methods return `OperationResult`:

```python
@dataclass
class OperationResult:
    success: bool
    error: Optional[str] = None
    data: Any = None
```

Routes convert to JSON:

```python
result = service.create_object(...)
if not result.success:
    return jsonify({'error': result.error}), 500
return jsonify({'success': True, 'data': result.data})
```

### HTTP Status Codes

| Code | Meaning | Use Case |
|------|---------|----------|
| 200 | Success | Normal operation |
| 400 | Bad Request | Invalid input, missing required fields |
| 404 | Not Found | Object/file not found |
| 409 | Conflict | Staging conflicts detected |
| 423 | Locked | Staging locked by another session |
| 500 | Internal Error | Unexpected exception, operation failure |

### Backup on Mutation

All mutating operations create backup first:

```python
bm = get_backup_manager()
backup_path = bm.create_backup("pre_operation_name")

# Perform mutation
result = service.update_object(...)

# Return backup path in response
return jsonify({'success': True, 'backup': backup_path})
```

Backup paths returned to client for manual rollback if needed.

### Logging Pattern

Structured logging via `OperationLogger`:

```python
if op_logger:
    op_logger.info('service', 'create_object',
                   params={'file': file_path, 'obj_type': obj_type},
                   result='success')
    op_logger.error('service', 'create_object',
                    params={'file': file_path},
                    error=str(e))
```

Log levels: DEBUG (parser reload), INFO (successful operations), WARNING (retries, partial failures), ERROR (failures).

## Testing Patterns

### Isolated App Instances

Each test gets fresh app instance:

```python
def test_feature():
    app = create_app(config_path='./test-config')
    with app.test_client() as client:
        response = client.get('/api/objects')
        assert response.status_code == 200
```

Services reinitialized per test, no shared state.

### Parser Reload After Mutation

Service automatically reloads parser after writes:

```python
def update_object(self, source_file, line_number, new_attrs, obj_type):
    with self._lock:
        result = edit_object_in_file(...)
        # Automatic reload
        self._parser = NagiosConfigParser(self._config_path)
        self._parser.parse_all()
        return OperationResult(True)
```

Tests see changes immediately without manual reload.

### Fixture Patterns

Common test fixtures:

```python
@pytest.fixture
def app():
    """Fresh app instance with test config."""
    return create_app('./test-config')

@pytest.fixture
def client(app):
    """Test client for making requests."""
    return app.test_client()

@pytest.fixture
def parser(app):
    """Parser for test config."""
    with app.app_context():
        return get_service().parser
```

## Key Service Functions

### NagiosService

| Function | What | Returns |
|----------|------|---------|
| get_objects() | Return all parsed objects | List[NagiosObject] |
| find_object_by_index(idx) | Get object by global index | Optional[NagiosObject] |
| find_object_by_stable_key(key) | Get object by stable key | Optional[Tuple[int, NagiosObject]] |
| search_objects(query, type, field, regex) | Search objects | List[NagiosObject] |
| create_object(file, type, attrs, after_line) | Create new object | OperationResult |
| update_object(file, line, attrs, type) | Update object in place | OperationResult |
| delete_object(file, line) | Delete object | OperationResult |
| move_object(src_file, src_line, tgt_file, type, attrs) | Move object between files | OperationResult |
| apply_folder_creations(staging_data, is_safe) | Create staged folders | OperationResult |
| apply_file_creations(staging_data, is_safe) | Create staged files | OperationResult |
| apply_object_deletions(staging_data) | Delete staged objects | OperationResult |
| apply_object_moves(staging_data) | Move staged objects | OperationResult |
| apply_object_edits(staging_data) | Edit staged objects | OperationResult |
| apply_object_creations(staging_data) | Create staged objects | OperationResult |
| get_typed_staging() | Get typed StagingState instance | Optional[StagingState] |
| reload() | Force parser reload | NagiosConfigParser |

### StagingManager

| Function | What | Returns |
|----------|------|---------|
| get_staging() | Get current staging data | Optional[Dict] |
| save_staging(data) | Save staging atomically | OperationResult |
| clear_staging() | Clear all staging | OperationResult |
| has_staging() | Check if lock held | bool |
| get_lock_owner() | Get session owning lock | Optional[str] |
| can_modify(session_id) | Check if session can modify | bool |
| validate_or_acquire_lock(session_id) | Acquire lock if available | bool |
| get_lock_status(session_id) | Detailed lock info | Dict |
| add_to_undo_stack(type, data, desc) | Push undo entry | Optional[str] |
| pop_undo_stack() | Pop and return undo entry | Optional[Dict] |
| compute_file_checksum(path) | SHA256 checksum | Optional[str] |
| update_base_checksums(paths) | Store base checksums | OperationResult |
| detect_conflicts() | Find external modifications | List[Dict] |
| stage_file_creation(path) | Stage file create | OperationResult |
| stage_file_deletion(path) | Stage file delete | OperationResult |
| stage_file_move(src, tgt) | Stage file move | OperationResult |
| unstage_operation(op_id, op_type) | Remove staged op by ID | OperationResult |

### GitService

| Function | What | Returns |
|----------|------|---------|
| is_repo() | Check if inside git repo | OperationResult[bool] |
| get_user_identity() | Get configured user.name/email | OperationResult[Dict] |
| get_status(excluded_paths) | Git status porcelain | OperationResult[GitStatusResult] |
| get_diff(filepath, staged, context) | Get diff for file/all | OperationResult[str] |
| get_workspace_diff(excluded) | Structured diff for commit dialog | OperationResult[Dict] |
| get_log(limit) | Commit history | OperationResult[Dict] |
| has_uncommitted_changes() | Check if dirty working dir | OperationResult[bool] |
| init_repo() | Initialize git repo | OperationResult |
| commit(message, files, user_name, user_email) | Stage and commit | OperationResult[Dict] |
| discard(filepath) | Discard changes to file | OperationResult[Dict] |
| discard_all() | Hard reset + clean | OperationResult[Dict] |
| restore(commit_hash) | Restore to specific commit | OperationResult[Dict] |
| clear_history(user_name, user_email) | Wipe history, fresh commit | OperationResult[Dict] |

### BackupManager

| Function | What | Returns |
|----------|------|---------|
| create_backup(desc, user_name, user_email) | Create zip backup with metadata | str (backup path) |
| list_backups() | List all backups (zip + legacy) | List[Dict] |
| restore_backup(name, user_name, user_email) | Restore from backup | Dict |
| delete_backup(name) | Delete specific backup | bool |
| cleanup_old_backups(keep_count) | Keep N recent, delete rest | int (deleted count) |

### Frontend Flow

```
User Action → Event Handler → ApiClient.post/get → Backend API
                           ↓
                    Update Explorer.state
                           ↓
                    Render UI (tree/editor/target panes)
                           ↓
                    Update staging badges
```

### Commit Workflow

```
User clicks Commit button
    ↓
base.js: showGlobalCommitDialog()
    ↓
Fetch /api/staging/diff + /api/staging/analyze-references
    ↓
Build commit UI with file-based changes view
    ↓
User enters message + checks "Update references"
    ↓
POST /api/staging/apply {updateReferences: true}
    ↓
POST /api/git/commit {message, user_name, user_email}
    ↓
Show git result panel (terminal-style)
    ↓
Clear staging + reload page
```

## Staging Status States

```
EMPTY ──(acquire lock)──> ACTIVE ──(clear)──> EMPTY
  ^                          |
  |                          v
  └──(clear)── RESTORE_PENDING <──(backup restore)
```

- **EMPTY**: No session owns staging, available for acquisition
- **ACTIVE**: Session holds lock via sessionId, normal editing
- **RESTORE_PENDING**: Backup restore populated staging, awaiting commit/discard

## Key Frontend Conventions

### Naming Conventions

- **Functions**: camelCase (`showToast`, `escapeHtml`)
- **Classes**: kebab-case for CSS (`commit-btn`, `toast-message`)
- **Data attributes**: kebab-case (`data-action`, `data-object-type`)
- **CSS variables**: kebab-case with namespace (`--nbe-primary`, `--nbe-space-md`)
- **Explorer namespace**: `Explorer.functionName()`, `Explorer.state.property`

### Cross-Language Naming (Python ↔ JavaScript)

API responses use snake_case (Python), frontend converts to camelCase (JavaScript) as needed.

| Python (API) | JavaScript (Frontend) | Context |
|--------------|----------------------|---------|
| `session_id` | `sessionId` | Request headers, localStorage key |
| `user_name` | `userName` | Git identity, audit log |
| `user_email` | `userEmail` | Git identity |
| `source_file` | `source_file` | Object location (kept as-is) |
| `object_type` | `object_type` | Object type (kept as-is) |
| `global_index` | `global_index` | Object index (kept as-is) |
| `stable_key` | `stableKey` | Object identifier |
| `pending_edits` | `pendingEdits` | Staging state |
| `staged_moves` | `stagedMoves` | Staging state |

Pattern: API returns snake_case; frontend uses camelCase for local state but preserves API field names when sending/receiving.

### State Management

- **Explorer state**: Centralized in `Explorer.state`, modified by functions on `Explorer` namespace
- **Session state**: localStorage (`nagios_session_id`, `nagios_user_name`, `nagios_user_email`)
- **Lock state**: `baseState` in base.js, synced with `window.isEditingLocked` for legacy compatibility
- **Staging sync**: frontend state syncs to backend via `/api/staging/*` endpoints

### Error Handling

- API errors: ApiClient shows toast unless `{silent: true}` passed
- User confirmations: Use `showConfirmDialog()` for destructive actions
- Network timeouts: ApiClient supports timeout option for long-running operations
- Lock conflicts: UI automatically disables edit controls when `isEditingLocked === true`

### Autocomplete Pattern

Used in explorer attribute editor and create dialogs:

```javascript
// Show dropdown on input
function showAutocomplete(input, suggestions, onSelect) {
    // Build dropdown positioned near input
    // Arrow keys navigate, Enter selects, Escape closes
    // Click outside closes via blur event with setTimeout
}
```

See explorer/app.js `showAttributeAutocomplete` for reference implementation.

### Keyboard Shortcuts

Registered in app.js and base.js:

- Global: Escape (close dialogs), Ctrl+Z (undo), ? (show help)
- Explorer: Space (preview), M (move), Delete (stage deletion)
- Selection: Ctrl+Click (toggle), Shift+Click (range)
- Autocomplete: Arrow keys, Enter, Escape

Add new shortcuts to `handleGlobalKeydown` in app.js or page-specific handlers.

### CSS Architecture

- **tokens.css**: Design system variables (MUST use these)
- **style.css**: Global component styles (cards, tables, buttons)
- **base.html inline**: Dialog/toast/commit UI styles (avoid FOUC)
- **Page CSS**: Page-specific overrides and layouts
- **Responsive**: Uses Bootstrap grid, custom breakpoints in tokens

Page-specific CSS should:
1. Use design tokens (`var(--nbe-*)`)
2. Match explorer.css patterns for sidebar/header/content
3. Avoid hard-coded colors/spacing
4. Use semantic class names (`.backup-item`, not `.blue-box`)

### Modifying Explorer

Explorer uses modular architecture:

1. **Add feature to existing module**: Export function on `Explorer` namespace
2. **Add new module**: Create file in explorer/, load in explorer.html, attach to `Explorer` namespace
3. **Modify state**: Update `Explorer.state` definition in main.js
4. **Add dialog**: Use context-menu.js or dialogs.js patterns

All modules loaded after main.js can access `Explorer.state` and call `Explorer.functionName()`.

### Performance Considerations

- **Large object lists**: Tree uses virtual scrolling (render visible items only)
- **Debounce search**: Use `debounce()` for search inputs (300ms delay)
- **Diff context**: Commit dialog uses context lines slider to limit diff size
- **Autocomplete**: Limit suggestions to 50 items, cache reference data
- **Polling**: Lock status polls every 5 seconds, can be disabled when inactive

## Decision Log

### 2026-01-27: multiprocessing.Lock over threading.Lock

**Context**: NagiosService and GitService need locking to protect multi-step mutations (e.g., write file then reload parser, git add then commit).

**Decision**: Use `multiprocessing.Lock` instead of `threading.Lock`.

**Rationale**: Flask's development server (`flask run`) and production WSGI servers (gunicorn, uwsgi) may spawn multiple worker processes. A `threading.Lock` only protects threads within a single process, so two worker processes could corrupt shared state simultaneously. `multiprocessing.Lock` works across processes.

**Trade-off**: multiprocessing.Lock has slightly higher overhead than threading.Lock due to inter-process synchronization, but correctness is more important than micro-optimization in a configuration management tool.
