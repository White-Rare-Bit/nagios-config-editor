# CLAUDE.md

## Setup

```bash
pip install -r requirements.txt
python3 -m app
# Access at http://localhost:8080
```

Dependencies: `flask>=2.0.0,<4.0.0`, `gunicorn>=21.2.0,<24.0.0`

## Documentation Index

**Reference docs** (`.claude/`): ROUTES_REFERENCE.md, API_REFERENCE.md, GIT_REFERENCE.md, FILE_OPS_REFERENCE.md, TYPOGRAPHY_REFERENCE.md, DECISION_LOG.md

**Module docs**: app/routes/CLAUDE.md, app/templates/CLAUDE.md, app/static/css/CLAUDE.md, app/static/js/CLAUDE.md, app/static/js/explorer/CLAUDE.md

## Backend Architecture

### App Factory (app/__init__.py)

Services stored in `app.extensions`, accessed via helpers:

```python
from .helpers import get_service, get_shadow_manager, get_backup_manager, get_server_config
```

### Thread Safety

`multiprocessing.Lock` (not `threading.Lock`) — WSGI servers may use multiple processes.
- **NagiosService**: Lock for all mutations
- **GitService**: Lock for multi-step mutations
- **ShadowCopyManager**: File-level undo snapshots, session lock

### OperationResult

All service methods return `OperationResult(success: bool, error: str = None, data: Any = None)`.

### Server Configuration

`config/settings.json`. Precedence: env vars > config file > defaults.

## Backend Module Index

| Module | What |
|--------|------|
| `app/__init__.py` | App factory, service init |
| `app/server_config.py` | Config load/save, env overrides |
| `app/nagios_service.py` | CRUD operations, reload |
| `app/shadow_copy_manager.py` | Shadow copy lifecycle, session lock, file-level undo, apply/destroy |
| `app/stable_keys.py` | Stable key generation and lookup helpers |
| `app/backup_manager.py` | Zip backups, restore |
| `app/nagios_parser.py` | Parse .cfg files |
| `app/nagios_writer.py` | Write .cfg files |
| `app/nagios_model.py` | NagiosObject, NAME_FIELDS, REFERENCE_FIELDS, domain constants |
| `app/file_operations.py` | Atomic file ops, path safety |
| `app/git_service.py` | Git wrapper, retry logic |
| `app/validator.py` | nagios -v validation |
| `app/audit_service.py` | JSON audit log (append-only JSONL) |

## Domain Metadata

All Nagios domain constants are defined in `app/nagios_model.py` and served via `GET /api/metadata`. The frontend fetches once at startup into `Explorer.constants`. **Never hardcode domain metadata in JavaScript.**

To add a new object type or reference field: update `app/nagios_model.py` — frontend picks it up automatically.

## Shadow Copy Architecture

On first edit, a full directory copy ("shadow") is created. All mutations write directly to shadow files. Apply = replace original with shadow; Discard = destroy shadow.

- **Lock**: Session-based. First mutation calls `ensure_shadow_lock()` which creates shadow + acquires lock. Check: `sm.can_modify(session_id)`.
- **Undo**: File-level snapshots. Before each mutation, `sm.snapshot_files([rel_path], description)` saves affected files. Undo restores previous snapshot.
- **Stable keys**: `"source_file|object_type|name"` for object identity across reloads.
- **Diff**: `sm.get_shadow_diff()` returns per-file unified diffs (shadow vs original).

## Error Handling

**HTTP status codes:** 200 (success), 400 (invalid input), 404 (not found), 409 (staging conflicts), 423 (locked), 500 (internal error)

**Backup on mutation:** `bm.create_backup("pre_operation_name")` before any write.

## Tool Preferences

- **Use LSP (Pyright)** for code navigation: hover for types, goToDefinition, findReferences, incomingCalls/outgoingCalls, documentSymbol — prefer over grep/read/bash scripts for type lookups, symbol searches, and function discovery.
- Use `npx pyright` via Bash for bulk type-error auditing.

## Debugging

**Frontend bugs**: Add `console.warn` with a stack trace (`new Error().stack`) to pinpoint the call chain. Browser stack traces reveal race conditions and unexpected callers far faster than reading code.

**Backend bugs**: Check Flask server logs for HTTP status codes (404, 423, 500) and correlate timestamps with frontend actions.

## Conventions

- **Python**: snake_case | **JavaScript**: camelCase | **CSS classes**: kebab-case | **CSS variables**: `--nbe-*`
- **API ↔ Frontend**: API returns snake_case; frontend preserves API field names in requests
- **Event delegation**: `data-action` attributes → `actionHandlers` map in `base.js`
- **API calls**: `ApiClient.get/post()` → `{success, data, error}`
