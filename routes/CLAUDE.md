# Routes

Flask blueprints registered in `__init__.py`. Service access via `helpers.py`.

## Module Index

| Module | Routes |
|--------|--------|
| `pages.py` | GET /, /explorer, /backups, /git, /settings, /logs, /docs, /dependencies |
| `objects.py` | GET /api/objects, POST /api/objects/update, /create, /delete, /move, /delete-multiple |
| `staging.py` | GET /api/staging, /info, /lock, /diff, POST /api/staging/apply, /undo, /lock/break, DELETE /api/staging |
| `files.py` | GET /api/files, /folders, POST /api/files/create, /move, /folders, /folders/move, DELETE /api/files/<path>, /folders/<path> |
| `bulk_ops.py` | POST /api/move-objects, /api/batch-mutations |
| `git.py` | GET /api/git/status, /identity, /log, POST /api/git/commit, /diff, /discard, /discard-all, /clear-history, /restore |
| `backups.py` | GET/POST /api/backups, POST /api/backups/<name>/restore, DELETE /api/backups/<name>, /all |
| `analysis.py` | GET /api/dependencies, /inheritance/list/<type>, /inheritance/<type>/<name>, /smart-grouping/suggest, /templates/issues, /escalation-path/<type>/<name>, /object-references |
| `templates.py` | GET /api/templates, /inheritance/<stable_key> |
| `metadata.py` | GET /api/metadata |
| `validation.py` | POST /api/reload, /validate, GET /api/summary, /health-check |
| `settings.py` | GET/POST /api/settings, /logging, POST /api/settings/browse, /api/logs/frontend, GET /api/logs/operations |
| `logs.py` | GET /api/logs/audit, /app, /download, POST /clear |

## Key Helpers (helpers.py)

```python
operation_response(result, success_data=None, error_code=500)
# Converts OperationResult → (jsonify, status_code)
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
