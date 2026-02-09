# CLAUDE.md

## Setup

```bash
pip install -r requirements.txt
python3 app.py
# Access at http://localhost:8080
```

Dependencies: `flask>=2.0.0,<4.0.0`

## Documentation Index

**Reference docs** (`.claude/`): ROUTES_REFERENCE.md, API_REFERENCE.md, STAGING_REFERENCE.md, GIT_REFERENCE.md, FILE_OPS_REFERENCE.md, TYPOGRAPHY_REFERENCE.md, DECISION_LOG.md

**Module docs**: routes/CLAUDE.md, templates/CLAUDE.md, static/css/CLAUDE.md, static/js/CLAUDE.md, static/js/explorer/CLAUDE.md

## Backend Architecture

### App Factory (app.py)

Services stored in `app.extensions`, accessed via helpers:

```python
from .helpers import get_service, get_staging_manager, get_backup_manager, get_server_config
```

### Thread Safety

`multiprocessing.Lock` (not `threading.Lock`) — WSGI servers may use multiple processes.
- **NagiosService**: Lock for all mutations
- **GitService**: Lock for multi-step mutations
- **StagingManager**: Atomic file writes (temp file + rename)

### OperationResult

All service methods return `OperationResult(success: bool, error: str = None, data: Any = None)`.

### Server Configuration

`config/settings.json`. Precedence: env vars > config file > defaults.

## Backend Module Index

| Module | What |
|--------|------|
| `app.py` | App factory, service init |
| `server_config.py` | Config load/save, env overrides |
| `nagios_service.py` | CRUD operations, apply phases |
| `staging_manager.py` | Staging state, locks, undo stack |
| `backup_manager.py` | Zip backups, restore |
| `nagios_parser.py` | Parse .cfg files |
| `nagios_writer.py` | Write .cfg files |
| `nagios_model.py` | NagiosObject, NAME_FIELDS, REFERENCE_FIELDS, domain constants |
| `file_operations.py` | Atomic file ops, path safety |
| `git_service.py` | Git wrapper, retry logic |
| `validator.py` | nagios -v validation |
| `operation_logger.py` | Structured JSON logging |
| `audit_service.py` | Audit log writer |

## Domain Metadata

All Nagios domain constants are defined in `nagios_model.py` and served via `GET /api/metadata`. The frontend fetches once at startup into `Explorer.constants`. **Never hardcode domain metadata in JavaScript.**

To add a new object type or reference field: update `nagios_model.py` — frontend picks it up automatically.

## Staging System

True staging: NO changes written to disk until "Apply". See `.claude/STAGING_REFERENCE.md`.

- **Lock**: Session-based. First edit acquires lock. Check: `sm.can_modify(session_id)`.
- **Stable keys**: `"source_file|object_type|name"` for object identity (not global_index).
- **Operations**: pendingEdits, stagedMoves, stagedCreations, stagedObjectDeletions, stagedFileCreations, stagedFileDeletions, stagedFileMoves, stagedFolderCreations, stagedFolderDeletions, stagedFolderMoves

## Error Handling

**HTTP status codes:** 200 (success), 400 (invalid input), 404 (not found), 409 (staging conflicts), 423 (locked), 500 (internal error)

**Backup on mutation:** `bm.create_backup("pre_operation_name")` before any write.

## Conventions

- **Python**: snake_case | **JavaScript**: camelCase | **CSS classes**: kebab-case | **CSS variables**: `--nbe-*`
- **API ↔ Frontend**: API returns snake_case; frontend preserves API field names in requests
- **Event delegation**: `data-action` attributes → `actionHandlers` map in `base.js`
- **API calls**: `ApiClient.get/post()` → `{success, data, error}`
