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

## Documentation Index

### Reference Documentation (.claude/)

| File | Content |
|------|---------|
| ROUTES_REFERENCE.md | All 70+ API routes with descriptions |
| API_REFERENCE.md | Service function signatures |
| STAGING_REFERENCE.md | Staging system internals, apply phases, undo stack |
| GIT_REFERENCE.md | Git integration patterns, timeouts, identity |
| FILE_OPS_REFERENCE.md | File operations, block detection, path safety |
| TYPOGRAPHY_REFERENCE.md | Typography tokens, font system |
| DECISION_LOG.md | Historical architecture decisions |

### Module-Level Documentation

| File | Content |
|------|---------|
| routes/CLAUDE.md | Flask blueprints, helper utilities, route patterns |
| templates/CLAUDE.md | Template hierarchy, blocks, load order, global components |
| static/css/CLAUDE.md | Design tokens, button system, dark theme, typography |
| static/js/CLAUDE.md | Page-specific JS modules, dependency graph architecture |
| static/js/explorer/CLAUDE.md | Explorer module architecture, state management |

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

## Frontend Modules

**Core:** app.js (global utils), base.js (session/lock/toast/commit), api-client.js (fetch wrapper)

**Explorer:** See `static/js/explorer/CLAUDE.md` - main.js (state), app.js (tree), object-editor.js (center pane), file-operations.js (target pane), context-menu.js, dialogs.js, data-loading.js, state-management.js, drag-drop.js, analysis.js, ui-utils.js

**Page-specific:** See `static/js/CLAUDE.md` - git.js, backups.js, audit-log.js, dependencies.js, settings.js, bulk-rename.js, reorganize.js, smart-grouping.js, inheritance.js, validate.js

## Cross-Cutting Concerns

### Event Delegation Pattern

Uses `data-action` attributes for click handlers. Add actions to `actionHandlers` map in base.js.

```javascript
<button data-action="reload-config">Reload</button>
```

### ApiClient Pattern

All API calls use `ApiClient.get/post()` returning `{success, data, error}`.

```javascript
const result = await ApiClient.get('/api/endpoint');
if (result.success) { /* use result.data */ }
```

### Global Functions

**app.js**: `escapeHtml()`, `formatDate()`, `debounce()`, `escapeRegex()`, `copyToClipboard()`, `setButtonLoading()`

**base.js**: `showToast()`, `showConfirmDialog()`, `getSessionId()`, `getUserIdentity()`, `getStagingHeaders()`

### Explorer State

See `static/js/explorer/CLAUDE.md` for complete details.

`Explorer.state` holds allObjects, selections, staging maps, undo stack. Call `Explorer.refreshAfterObjectChange(options)` after mutations.

### Domain Metadata

All Nagios domain constants (NAME_FIELDS, REQUIRED_FIELDS, REFERENCE_FIELDS,
VALID_ATTRIBUTES, etc.) are defined in `nagios_model.py` and served via
`GET /api/metadata`. The frontend fetches metadata once at startup and stores
it in `Explorer.constants`. **Never hardcode domain metadata in JavaScript.**

To add a new Nagios object type or reference field:
1. Update the relevant constant in `nagios_model.py`
2. The frontend will pick it up automatically via `/api/metadata`

### Design System

See `static/css/CLAUDE.md` for complete token reference. Use design tokens instead of hard-coded values:

```css
var(--nbe-primary)         /* Semantic colors */
var(--nbe-space-md)        /* Spacing */
var(--nbe-typography-h1-*) /* Typography */
var(--nbe-dark-bg-*)       /* Dark theme (explorer only) */
```

### Template System

See `templates/CLAUDE.md` for complete details. All pages extend `base.html` with blocks: `title`, `extra_css`, `content`, `scripts`.

## Staging System

True staging: NO changes written to disk until "Apply". See `.claude/STAGING_REFERENCE.md` for complete details.

**Lock management:** Session-based. First edit acquires lock. Check with `sm.can_modify(session_id)`.

**Stable keys:** Objects identified by `"source_file|object_type|name"` instead of global_index.

**Operations:** pendingEdits, stagedMoves, stagedCreations, stagedObjectDeletions, stagedFileCreations, stagedFileDeletions, stagedFileMoves, stagedFolderCreations, stagedFolderDeletions, stagedFolderMoves

## Error Handling

**HTTP status codes:** 200 (success), 400 (invalid input), 404 (not found), 409 (staging conflicts), 423 (locked), 500 (internal error)

**Backup on mutation:** All mutating operations create backup first via `bm.create_backup("pre_operation_name")`

## Conventions

### Naming

- **Python**: snake_case
- **JavaScript**: camelCase
- **CSS classes**: kebab-case
- **CSS variables**: `--nbe-*` namespace
- **API ↔ Frontend**: API returns snake_case; frontend preserves API field names in requests

### State Storage

- **Explorer**: `Explorer.state` (in-memory)
- **Session**: localStorage (`nagios_session_id`, `nagios_user_name`)
- **Lock**: `baseState` in base.js, synced with `window.isEditingLocked`

### Keyboard Shortcuts

Global: Escape, Ctrl+Z, ?
Explorer: Space (preview), M (move), Delete
Selection: Ctrl+Click (toggle), Shift+Click (range)

Add shortcuts to `handleGlobalKeydown` in app.js.
