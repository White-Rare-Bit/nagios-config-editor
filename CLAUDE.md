# CLAUDE.md

## Setup

```bash
pip install -r requirements.txt
python3 -m app
# Access at http://localhost:8080
```

Dependencies: `flask>=2.0.0,<4.0.0`, `gunicorn>=21.2.0,<24.0.0`

Tests: `pip install -r requirements-dev.txt`, then `python3 -m pytest tests/`. `tests/conftest.py` isolates every test from `config/settings.json`, `logs/` and `sample-config/`; keep it that way.

## Documentation Index

**Reference docs** (`.claude/`): ROUTES_REFERENCE.md, API_REFERENCE.md, STAGING_REFERENCE.md, GIT_REFERENCE.md, FILE_OPS_REFERENCE.md, TYPOGRAPHY_REFERENCE.md, DECISION_LOG.md

**Module docs**: app/routes/CLAUDE.md, app/templates/CLAUDE.md, app/static/css/CLAUDE.md, app/static/js/CLAUDE.md, app/static/js/explorer/CLAUDE.md

## Backend Architecture

### App Factory (app/__init__.py)

`create_app()` builds a new, independent app on every call; importing `app` has no side effects (`wsgi.py` calls the factory). `init_services(app, server_config)` is the one place services are constructed (startup, settings change, and when a worker sees `config/settings.json` change on disk).

Services stored in `app.extensions`, accessed via helpers:

```python
from .routes.helpers import get_service, get_shadow_manager, get_backup_manager, get_server_config
```

### Process Safety

WSGI servers run several worker processes, and each worker builds its own app. **Workers share only the filesystem**, so:

- **Locks are file locks**: `ProcessLock` (`app/process_lock.py`, `flock` on a file under the shadow base). Never `threading.Lock` or `multiprocessing.Lock` for anything two workers must agree on: created per worker, they guard nothing between workers.
- **No staging state in memory**: whether a shadow exists, who owns it, and what roots are active is read from disk on every use. Never cache it on a service or re-point a service at a directory.
- **Settings**: `config/settings.json` is the shared copy. The before_request sync in `app/__init__.py` rebuilds services and re-applies logging level/rotation when another worker saved it; a route that saves must call `mark_settings_current()`.
- **Logging**: module loggers are `logging.getLogger(__name__)` (one `app.*` hierarchy). Don't swallow a failure that changes behaviour without logging it. Every outcome of staged work (apply, discard, undo, lock break) is audited; the audit log is never clearable and not subject to `log_level`.
- **Parser cache invalidation**: `ShadowCopyManager.generation()` changes on every mutation (`bump_generation()`); `NagiosService.parser` reparses when it differs. `service.reload()` bumps it; call that after changing files directly.
- **NagiosService**: lock for all mutations and parses · **GitService**: lock for multi-step mutations · **Routes**: `mutation_lock` held for a whole mutating request (see `routes/mutation.py`)

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
| `app/shadow_copy_manager.py` | Shadow copy lifecycle, session lock, file-level undo, apply/destroy, generation marker, logical↔physical path mapping |
| `app/process_lock.py` | `ProcessLock`: file lock that excludes other threads and other worker processes |
| `app/health_checks.py` | Health-check functions (`run_all_checks`); domain logic, no routes |
| `app/stable_keys.py` | Stable key generation and lookup helpers |
| `app/backup_manager.py` | Zip backups, restore |
| `app/nagios_parser.py` | Parse .cfg files |
| `app/nagios_syntax.py` | Shared define-block scanner (comment/quote rules) used by both the parser and `file_operations`, so they always agree where a block ends |
| `app/nagios_model.py` | NagiosObject, NAME_FIELDS, REFERENCE_FIELDS, domain constants, `format_object_block` (renders a define block) |
| `app/file_operations.py` | Atomic file ops, path safety |
| `app/git_service.py` | Git wrapper, retry logic |
| `app/validator.py` | nagios -v validation |
| `app/audit_service.py` | Key=value audit log (append-only, stdlib logging); `session=` hashed staging-session ref (never the raw id) |
| `app/logging_setup.py` | Installs app.log/audit.log handlers; applies level/rotation changes live; logs 5xx responses |
| `app/log_handlers.py` | `MultiProcessRotatingFileHandler` (flock-coordinated rotation for gunicorn workers), ISO 8601 formatter |
| `app/config_discovery.py` | Resolve config roots from nagios.cfg (cfg_dir/cfg_file directives) |
| `app/nagios_cfg.py` | Lightweight parser for nagios.cfg and resource.cfg ($USERn$ macros) |
| `app/inheritance.py` | Unified template inheritance resolution, chain walking, analysis |
| `app/references.py` | Type-aware reference matching (`referenced_by`) and rewriting (`reference_edits`) for rename and the delete warning |

## Domain Metadata

All Nagios domain constants are defined in `app/nagios_model.py` and served via `GET /api/metadata`. The frontend fetches once at startup into `Explorer.constants`. **Never hardcode domain metadata in JavaScript.**

To add a new object type or reference field: update `app/nagios_model.py` — frontend picks it up automatically.

## Shadow Copy Architecture

On first edit, a full directory copy ("shadow") is created. All mutations write directly to shadow files. Apply = replace original with shadow; Discard = destroy shadow.

- **Paths**: two namespaces. *Logical* paths are the original config locations; the API, `obj.source_file` and stable keys always use them, with or without a shadow. *Physical* paths are inside the shadow. Only `ShadowCopyManager` (`physical_path`, `logical_path`, `composite_path`) and `NagiosService` convert; a path outside every config root has no physical path and must be refused, never written.
- **Mutations**: every mutating route runs inside `staged_mutation()` (`app/routes/mutation.py`): cross-worker lock → ownership check → create shadow on first use → `m.snapshot()` → change → audit. Do not hand-assemble this sequence. `NagiosService` refuses to write when no shadow exists.
- **Lock**: Session-based; only the owner may mutate, apply, discard, undo or restore (`staging_owner()`), `sm.is_owner(session_id)`. Break-lock is open to others and audited. The owner's session id is never sent to clients (`public_lock_status()` returns `is_owner`).
- **Undo**: File-level snapshots. Before each mutation, `m.snapshot([logical_path], description)` saves affected files. Undo restores previous snapshot.
- **Lifetime**: a shadow survives server/worker restarts; startup only removes one made for different config roots (`discard_if_stale()`).
- **Stable keys**: `"source_file|object_type|name"` (logical path) for object identity across reloads and across staging start/end.
- **Multi-root**: staging and backups cover every config root. Git covers the primary directory only; `GET /api/git/status` lists the rest as `untracked_roots`.
- **Diff**: `sm.get_shadow_diff()` returns per-file unified diffs (shadow vs original).

## Error Handling

**HTTP status codes:** 200 (success), 400 (invalid input), 404 (not found), 409 (staging conflicts), 423 (locked), 500 (internal error)

**Error body:** always `{"success": false, "error": "<message>"}` (extra fields allowed). Raise `ApiError(message, status)` from routes; the app enforces the shape for every `/api/` error.

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
- **API calls**: `ApiClient.get/post()` → `{success, data, payload, error}`; `data` is the raw body, `payload` is the body with a `{success, data}` envelope removed. Read `payload`, don't write `x.data.data || x.data`.
