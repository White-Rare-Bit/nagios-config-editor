# Routes

Flask blueprints registered in `__init__.py`. Service access via `helpers.py`.

## Module Index

| Module | Routes |
|--------|--------|
| `pages.py` | GET /, /explorer, /backups, /git, /settings, /validate, etc. |
| `objects.py` | GET /api/objects, POST /api/objects/update, /create, /delete, /move, /delete-multiple |
| `staging.py` | GET /api/staging/info, POST /api/staging/apply, /undo, /break-lock, /clear |
| `files.py` | GET /api/files, /folders, POST /api/files/create, /move, /folders, /folders/move, DELETE /api/files/<path>, /folders/<path> |
| `bulk_ops.py` | POST /api/preview-rename, /api/diff/rename, /api/apply-rename, /api/move-objects |
| `git.py` | GET /api/git/status, POST /api/git/commit, /restore, GET /api/git/log |
| `backups.py` | GET/POST /api/backups, POST /api/backups/<name>/restore, DELETE |
| `analysis.py` | GET /api/dependencies, /inheritance, POST /api/smart-grouping/suggest |
| `templates.py` | GET /api/templates, /inheritance/<key>, /validate-use |
| `metadata.py` | GET /api/metadata |
| `validation.py` | POST /api/reload, /validate, GET /api/summary, /health-check |
| `settings.py` | GET/POST /api/settings, /logging |
| `logs.py` | GET /api/logs/audit, /app, POST /clear, GET /download |

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
