# Nagios Bulk Editor

Web interface for bulk editing Nagios configuration files with staging, backups, and validation.

## Architecture

```
HTTP Request
     |
     v
Flask Route (app.py)
     |
     v
app.extensions dict
     |
     +---> ['service']  → NagiosService
     +---> ['staging']  → StagingManager
     +---> ['backup']   → BackupManager
     |
     v
NagiosService
  ├── parser (NagiosConfigParser)
  ├── CRUD methods (create/update/delete/move)
  └── apply_* phase methods (10 phases)
     |
     v
File Operations / Parser / Writer
     |
     v
.cfg files ←→ staging.json ←→ backups/
```

## App Factory Pattern

Flask app factory provides test isolation and configuration flexibility:

```python
app = create_app(config_path="/path/to/nagios/config")
```

Services initialized once per app instance and stored in `app.extensions`:
- Routes access via `current_app.extensions['service']`
- Tests create isolated app instances via `create_app(test_config)`
- Eliminates global mutable state and import-time side effects

## Staging Status States

Staging uses explicit state enum instead of boolean flags:

```
EMPTY ──(acquire lock)──> ACTIVE ──(clear)──> EMPTY
  ^                          |
  |                          v
  └──(clear)── RESTORE_PENDING <──(backup restore)
```

**EMPTY**: No session owns staging. Any session can acquire the lock via `/api/staging/acquire`.

**ACTIVE**: Session holds lock via `sessionId`. Only that session can modify staging. All edits, moves, creations, and deletions stored in `staging.json` without writing to disk.

**RESTORE_PENDING**: Backup restore populated staging with previous configuration state. Session must commit (apply changes to disk) or discard (clear staging).

### Migration

Old `staging.json` files with `restorePending: true` boolean automatically migrate to `StagingStatus.RESTORE_PENDING` on load. If `sessionId` present and no `restorePending` flag, migrates to `ACTIVE`. Otherwise migrates to `EMPTY`.

## Data Flow

### Edit Flow

1. User acquires staging lock → status becomes `ACTIVE`
2. Edits stored in `staging.json` under `pendingEdits`
3. User clicks "Apply" → `NagiosService.apply_staged_edits()` writes to .cfg files
4. Git commit (if configured)
5. Staging cleared → status becomes `EMPTY`

### Backup/Restore Flow

1. User creates backup → `BackupManager.create_backup()` copies all .cfg files to timestamped directory
2. User restores backup → backup contents copied to staging → status becomes `RESTORE_PENDING`
3. User reviews and clicks "Apply" → staged changes written to disk → status becomes `EMPTY`

### Apply Phases

`NagiosService` processes staged changes in 10 phases to handle dependencies:

1. **Deletions**: Remove objects marked for deletion
2. **Moves**: Move objects between files
3. **Edits**: Apply attribute changes
4. **Creations**: Create new objects
5. **File operations**: Handle new files, file moves, file deletions
6. **Folder operations**: Handle folder creation, moves, deletions
7. **Reference updates**: Cascade renames to dependent objects
8. **Template inheritance**: Resolve `use` directives
9. **Validation**: Run `nagios -v` to check configuration
10. **Commit**: Write changes and reload parser

Staging entries use dict format only (`{key: data, ...}`). The `_ensure_dict_format()` helper in `staging_manager.py` validates entries and logs warnings for any non-dict data. Legacy list format (`[[key, data], ...]`) is rejected at the API boundary with a 400 error.

## Key Invariants

1. **Single-writer**: Only one session can hold staging lock at a time (`StagingStatus.ACTIVE`).
2. **Atomic writes**: All file operations use temp file + atomic rename to prevent partial writes.
3. **Parser synchronization**: `NagiosService` automatically reloads parser after file modifications.
4. **Backup preservation**: Backup directories ignored by parser (`/backups/` paths excluded from `.cfg` discovery).
5. **Schema versioning**: `staging.json` includes `schema_version` for forward compatibility.

## Testing

```bash
# Run all tests (512 tests)
python3 -m pytest tests/ --tb=short -q

# Run specific test file
python3 -m pytest tests/test_staging_manager.py -v

# Run with coverage
python3 -m pytest tests/ --cov=. --cov-report=html
```

Test fixtures use `create_app()` to create isolated app instances with test configuration.

## Configuration

App expects Nagios configuration directory structure:
```
config_path/
├── nagios.cfg          # Main config file
├── objects/            # Object definitions
│   ├── hosts.cfg
│   ├── services.cfg
│   └── ...
├── backups/            # Timestamped backups (auto-created)
└── staging.json        # Active staging state (auto-created)
```

## Dependencies

- Python 3.13.7
- Flask (web framework)
- pytest 7.4.4 (testing)
- Nagios binary for validation (optional)
