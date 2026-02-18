# Routes

Flask blueprints registered in `__init__.py`. Service access via `helpers.py`.

## Module Index

| Module | Routes |
|--------|--------|
| `pages.py` | GET /, /explorer, /backups, /git, /settings, /validate, etc. |
| `objects.py` | GET /api/objects, POST /api/delete-objects, POST /api/clone-objects |
| `staging.py` | GET/POST/DELETE /api/staging, POST /api/staging/apply, /undo |
| `files.py` | GET /api/files, POST /api/files/create, /move, DELETE /api/files/<path> |
| `bulk_ops.py` | POST /api/apply-rename, POST /api/move-objects |
| `git.py` | GET /api/git/status, POST /api/git/commit, /restore, GET /api/git/log |
| `backups.py` | GET/POST /api/backups, POST /api/backups/<name>/restore, DELETE |
| `analysis.py` | GET /api/dependencies, /inheritance, POST /api/smart-grouping/suggest |
| `templates.py` | GET /api/templates, /inheritance/<key>, /validate-use |
| `metadata.py` | GET /api/metadata |
| `validation.py` | POST /api/reload, /validate, GET /api/summary, /health-check |
| `settings.py` | GET/POST /api/settings, /logging |
| `logs.py` | GET /api/logs/audit, /app, POST /clear, GET /download |
| `debug.py` | Debug/diagnostic endpoints |

## Key Helpers (helpers.py)

```python
operation_response(result, success_data=None, error_code=500)
# Converts OperationResult → (jsonify, status_code)
```

## Patterns

**Lock check** (required for staging mutations):
```python
if not sm.can_modify(request.headers.get('X-Session-Id')):
    return jsonify({'error': 'Locked by another user', 'locked': True}), 423
```

**Parser modification** (holds lock, reloads on exit):
```python
with get_parser_for_modification() as p:
    # Multi-step mutation
```

**Backup before mutation**: `bm.create_backup("operation_name")` before any write.
