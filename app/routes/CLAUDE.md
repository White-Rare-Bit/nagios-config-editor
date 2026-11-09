# Routes

Flask blueprints registered in `__init__.py`. Service access via `helpers.py`.

## Module Index

| Module | Routes |
|--------|--------|
| `pages.py` | GET /, /explorer, /backups, /git, /settings, /logs, /docs, /api/docs/\<page\>, /dependencies |
| `objects.py` | GET /api/objects, POST /api/objects/update, /create, /delete, /move, /delete-multiple |
| `staging.py` | GET /api/staging, /info, /lock, /diff, POST /api/staging/apply, /undo, /lock/break, DELETE /api/staging |
| `files.py` | GET /api/files, /folders, POST /api/files/create, /move, /folders, /folders/move, DELETE /api/files/\<path\>, /folders/\<path\> |
| `bulk_ops.py` | POST /api/move-objects, /api/batch-mutations |
| `git.py` | GET /api/git/status, /identity, /log, POST /api/git/commit, /diff, /discard, /discard-all, /clear-history, /restore |
| `backups.py` | GET/POST /api/backups, POST /api/backups/\<name\>/restore, DELETE /api/backups/\<name\>, /all |
| `analysis.py` | GET /api/dependencies, /inheritance/list/\<type\>, /inheritance/\<type\>/\<name\>, /smart-grouping/suggest, /templates/issues, /escalation-path/\<type\>/\<name\>[/\<service_desc\>], /object-references |
| `templates.py` | GET /api/templates, /inheritance/\<stable_key\> |
| `metadata.py` | GET /api/metadata |
| `validation.py` | POST /api/reload, /validate, GET /api/summary, /health-check |
| `settings.py` | GET/POST /api/settings, /api/settings/logging, POST /api/settings/browse, /api/logs/frontend, GET /api/logs/operations, /api/logs/operations/download |
| `logs.py` | GET /api/logs/audit, /api/logs/audit/download, /api/logs/app, /api/logs/app/download, POST /api/logs/audit/clear, /api/logs/app/clear |
| `mutation.py` | No routes — `staged_mutation()`, `staging_owner()`, `ApiError`, `public_lock_status()`; the only way a route may change configuration |

Health-check logic lives in `app/health_checks.py` (not a routes module).

## Key Helpers (helpers.py)

```python
operation_response(result, success_data=None, error_code=500)
# Converts OperationResult → (jsonify, status_code)

get_service()            # NagiosService from app.extensions
get_shadow_manager()     # ShadowCopyManager from app.extensions
get_backup_manager()     # BackupManager from app.extensions
get_git_service()        # GitService from app.extensions
get_server_config()      # ServerConfig from app.extensions
get_config()             # Flask current_app.config
get_config_roots()       # Config root directories
get_config_path()        # Main config path
make_relative_path(path, config_path) # Relative to the config root's parent
audit_file_path(path)    # Display path for audit lines, any config root
get_audit_user_identity()     # User identity from request headers
format_audit_user(name, email) # Format for audit log
```

## Patterns

**Mutations** (edits, creates, moves, deletes): always inside `staged_mutation()`.
It holds the cross-worker lock, returns 423 if another session owns the staging
lock, creates the shadow on first use, and removes it again if the request
changed nothing.

```python
from .mutation import ApiError, staged_mutation

if not stable_key:
    raise ApiError("stable_key required")          # 400, standard error body

with staged_mutation() as m:
    obj = m.require(stable_key)                     # 404 if missing
    m.snapshot([obj.source_file], "edit host x")    # before changing anything (enables undo)
    result = m.service.update_object(...)           # service writes to the shadow
    m.audit("object_edit", type=..., file=m.display(obj.source_file))
return operation_response(result)
```

Direct file operations: `physical = m.physical(logical)` (400 outside the config
roots), change the file, then `m.files_changed()` so every worker reparses.

**Owner-only operations** on an existing session or the live config (apply,
discard, undo, restore): `with staging_owner() as sm:`. Never creates a shadow.

**Paths**: requests and responses carry logical paths (original config
locations). `m.resolve(client_path)` → absolute logical path; never build shadow
paths by hand and never read `sm._config_dir`.
