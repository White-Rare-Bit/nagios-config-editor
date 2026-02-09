# Nagios Bulk Editor

Web interface for bulk editing Nagios configuration files with staging, backups, and validation.

## Architecture

```
HTTP Request → Flask Route → app.extensions
                               ├── ['service']  → NagiosService (CRUD, apply phases)
                               ├── ['staging']  → StagingManager (locks, undo)
                               └── ['backup']   → BackupManager
                                        ↓
                              Parser / Writer → .cfg files
```

## Staging System

No changes written to disk until "Apply". Staging uses explicit state enum:

```
EMPTY ──(acquire lock)──> ACTIVE ──(clear)──> EMPTY
  ^                          |
  └──────(clear)──── RESTORE_PENDING <──(backup restore)
```

Apply processes staged changes in 10 phases: folder creations → file creations → object deletions → object moves → object edits → object creations → file moves → folder moves → file deletions → folder deletions.

Staging entries use dict format only. Legacy list format rejected at API boundary with 400.

## Key Invariants

1. **Single-writer**: Only one session holds staging lock at a time.
2. **Atomic writes**: Temp file + rename to prevent partial writes.
3. **Parser sync**: NagiosService reloads parser after file modifications.
4. **Backup preservation**: `/backups/` paths excluded from `.cfg` discovery.

## Testing

```bash
python3 -m pytest tests/ -v
```

## Configuration

```
config_path/
├── objects/         # .cfg object definitions
├── backups/         # Timestamped backups (auto-created)
└── staging.json     # Active staging state (auto-created)
```
