# Package Restructure Design

**Date**: 2026-03-17
**Status**: Approved
**Approach**: Big Bang (single branch, single PR)

## Motivation

Follow standard Flask project structure for maintainability. Move all application code into an `app/` Python package. No external consumers — purely internal convention improvement.

## Target Structure

```
nagios-bulk-editor/
├── app/                        # Python package
│   ├── __init__.py             # create_app() factory, exports `app`
│   ├── nagios_service.py
│   ├── nagios_model.py
│   ├── nagios_parser.py
│   ├── nagios_writer.py
│   ├── file_operations.py
│   ├── shadow_copy_manager.py
│   ├── git_service.py
│   ├── backup_manager.py
│   ├── inheritance.py
│   ├── validator.py
│   ├── audit_service.py
│   ├── server_config.py
│   ├── config_discovery.py
│   ├── nagios_cfg.py
│   ├── stable_keys.py
│   ├── routes/                 # Moves inside app/
│   ├── templates/              # Moves inside app/
│   └── static/                 # Moves inside app/
├── wsgi.py                     # Stays at root
├── tests/                      # Stays at root
├── config/                     # Stays at root
├── sample-config/              # Stays at root
├── deploy/                     # Stays at root
├── docs/                       # Stays at root
├── logs/                       # Stays at root
└── .claude/                    # Stays at root
```

## Import Strategy

**Inside `app/`**: All relative imports.

```python
# app/nagios_service.py
from .file_operations import add_object_to_file, ...
from .nagios_model import NAME_FIELDS, NagiosObject, OperationResult
from .stable_keys import parse_stable_key
```

**Routes**: Relative imports up one level for parent package modules.

```python
# app/routes/objects.py
from ..audit_service import log_audit
from .helpers import get_service, ...
```

**Tests**: Absolute imports via package name.

```python
# tests/test_backup_manager.py
from app.backup_manager import BackupManager
```

**wsgi.py**: Unchanged (`from app import app` — `app` is now a package).

## Path Resolution

Three locations use `Path(__file__).parent` to find project-root-relative paths:

- **`server_config.py`**: `CONFIG_DIR = Path(__file__).parent.parent / "config"` (was `.parent`)
- **`app/__init__.py`**: `PROJECT_ROOT = Path(__file__).parent.parent` for log dir and root-relative paths
- **Flask template/static**: No change — `templates/` and `static/` move with the package, Flask auto-discovers them

## Documentation Updates

Files needing path reference updates:
- `CLAUDE.md` — module index, import examples, setup section
- `routes/CLAUDE.md` — import examples
- `.claude/FILE_OPS_REFERENCE.md`, `GIT_REFERENCE.md`, `STAGING_REFERENCE.md`
- Memory files in `.claude/projects/`

## Testing Strategy

1. `python3 -m pytest tests/ -v` — all tests must pass
2. `npx pyright` — catch broken imports
3. `python3 -c "from app import create_app; print('OK')"` — smoke test
4. Verify `gunicorn wsgi:app` starts

## What Stays Unchanged

- All business logic (no code changes beyond imports and path resolution)
- `wsgi.py` import works as-is
- Frontend code (templates, JS, CSS)
- `config/`, `sample-config/`, `deploy/`, `logs/`
- Git history preserved via `git mv`
