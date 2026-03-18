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
| `health_checks.py` | Utility module (no routes) — health check functions imported by validation.py |

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
make_relative_path(path) # Relative to config root
get_parser_for_modification() # Parser operating on shadow copy
get_audit_user_identity()     # User identity from request headers
format_audit_user(name, email) # Format for audit log
```

## Patterns

**Shadow lock** (required before all mutations):
```python
session_id = request.headers.get("X-Session-Id")
success, error = ensure_shadow_lock(session_id)
if not success:
    return error  # 423 if locked by another session
```

**Snapshot before mutation** (enables undo):
```python
sm = get_shadow_manager()
rel_path = os.path.relpath(obj.source_file, sm._config_dir)
sm.snapshot_files([rel_path], "description of change")
```
