# Routes Directory

Flask blueprints for HTTP API endpoints and page rendering.

## Blueprint Registration

`__init__.py` registers all blueprints via `register_blueprints(app)` called from app factory in `app.py`.

## Helper Utilities (helpers.py)

Central access to app extensions and shared response formatting.

**Service Access:**
```python
from .helpers import (
    get_service,              # NagiosService instance
    get_staging_manager,      # StagingManager instance
    get_backup_manager,       # BackupManager instance
    get_git_service,          # GitService instance
    get_config_path,          # Current Nagios config directory
    get_server_config,        # ServerConfig object
    get_op_logger,            # OperationLogger instance
    get_audit_user_identity   # Extract user identity from request
)
```

**Response Helpers:**
```python
operation_response(result, success_data=None, error_code=500)
# Converts OperationResult to Flask JSON response
# Returns (jsonify, status_code) tuple
```

## Route Module Index

| Module | What | Routes |
|--------|------|--------|
| **pages.py** | HTML page rendering | GET /, /explorer, /backups, /git, /settings, /validate, etc. |
| **objects.py** | Object operations | GET /api/objects, POST /api/delete-objects, POST /api/clone-objects |
| **staging.py** | Staging system API | GET/POST/DELETE /api/staging, POST /api/staging/apply, POST /api/staging/undo |
| **files.py** | File/folder operations | GET /api/files, POST /api/files/create, POST /api/files/move, DELETE /api/files/<path> |
| **bulk_ops.py** | Bulk operations | POST /api/apply-rename, POST /api/move-objects |
| **git.py** | Git integration | GET /api/git/status, POST /api/git/commit, POST /api/git/restore, GET /api/git/log |
| **backups.py** | Backup management | GET /api/backups, POST /api/backups, POST /api/backups/<name>/restore, DELETE /api/backups/<name> |
| **analysis.py** | Dependencies & analysis | GET /api/dependencies, GET /api/inheritance/\<type>/\<name>, POST /api/smart-grouping/suggest |
| **templates.py** | Template operations | GET /api/templates, GET /api/templates/inheritance/\<key>, GET /api/templates/validate-use |
| **validation.py** | Config validation | POST /api/reload, GET /api/summary, POST /api/validate, GET /api/health-check |
| **settings.py** | Settings & logging | GET/POST /api/settings, POST /api/settings/browse, GET/POST /api/settings/logging, GET /api/audit-log |

## Pattern: Blueprint Structure

Each route module follows the same structure:

```python
from flask import Blueprint, request, jsonify
from .helpers import get_service, get_staging_manager, ...

bp = Blueprint('module_name', __name__)

@bp.route('/api/endpoint', methods=['GET'])
def api_endpoint():
    service = get_service()
    # ...logic
    return jsonify({'success': True, 'data': result})
```

## Pattern: Lock Validation

Routes that mutate staging require session lock ownership:

```python
session_id = request.headers.get('X-Session-Id')
sm = get_staging_manager()

if not sm.can_modify(session_id):
    return jsonify({'error': 'Locked by another user', 'locked': True}), 423
```

## Pattern: Backup Before Mutation

All mutating operations create backup first:

```python
bm = get_backup_manager()
backup_path = bm.create_backup("operation_name")
# ...perform mutation
return jsonify({'success': True, 'backup': backup_path})
```

## Pattern: Atomic Writes with Lock

When modifying parser state, use context manager to hold lock:

```python
with get_parser_for_modification() as p:
    # Multi-step mutation protected by lock
    # Parser reloaded on exit
```

## Common Response Formats

**Success:**
```json
{"success": true, "data": {...}, "backup": "path"}
```

**Error:**
```json
{"error": "message"}  // Status 400/404/500
```

**Lock Conflict:**
```json
{"error": "Locked by another user", "locked": true}  // Status 423
```

**Validation Conflict:**
```json
{"error": "message", "conflicts": [...], "requiresResolution": true}  // Status 409
```

## HTTP Status Codes

| Code | Use Case |
|------|----------|
| 200 | Success |
| 400 | Invalid input |
| 404 | Not found |
| 409 | Conflict (staging conflicts, duplicates) |
| 423 | Locked (staging locked by another session) |
| 500 | Internal error |

## Adding New Routes

1. Create blueprint in new module:
   ```python
   bp = Blueprint('feature', __name__)
   ```

2. Import helpers for service access:
   ```python
   from .helpers import get_service, get_staging_manager, ...
   ```

3. Define routes with `@bp.route(...)` decorator

4. Register blueprint in `__init__.py`:
   ```python
   from .feature import bp as feature_bp
   app.register_blueprint(feature_bp)
   ```

## Key Routes by Use Case

**Object Editing:**
- `objects.py`: CRUD operations with stable keys
- `staging.py`: True staging (changes not on disk until apply)

**Bulk Operations:**
- `bulk_ops.py`: Rename, move

**File Operations:**
- `files.py`: Create/move/delete files and folders (staged)
- `staging.py`: Apply staged file operations to disk

**Commit Workflow:**
- `staging.py`: Apply changes → `git.py`: Commit to git

**Analysis:**
- `analysis.py`: Dependencies graph, inheritance chains, smart grouping
- `validation.py`: Health check, Nagios validation

**Template Management:**
- `templates.py`: List templates, inheritance chains, validation
- `analysis.py`: Template issues (unused, circular, invalid references)

## Reference Documentation

Complete route listing: `.claude/ROUTES_REFERENCE.md`
