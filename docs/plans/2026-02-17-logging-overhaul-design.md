# Logging System Overhaul — Design

**Date:** 2026-02-17
**Approach:** Python stdlib `logging` for everything (Approach 1)

## Overview

Replace the current dual-format logging system (JSONL operation logger + JSON audit service) with two plain-text `.log` files using Python's stdlib `logging` module. Replace the card-based audit log page with a unified log viewer page using table-based UI matching the existing git/backup page styling.

## Log Files

### Application Log (`logs/app.log`)

Syslog-style format:

```
Feb 17 14:23:01 nagios-editor [INFO] backup.create_backup: Created backup pre_apply (user=admin@example.com)
Feb 17 14:23:02 nagios-editor [WARNING] nagios_parser.parse: Syntax warning in hosts.cfg line 42
Feb 17 14:23:03 nagios-editor [ERROR] git_service.commit: Failed to commit - working tree dirty
```

Format template: `{date} nagios-editor [{level}] {module}.{operation}: {message} ({key=value context})`

**Sources:** All existing `logging.getLogger(__name__)` calls (~9 modules), Flask request logging. Replaces `operation_logger.py`.

### Audit Log (`logs/audit.log`)

Key=value format, one line per change, grouped by transaction ID:

```
Feb 17 14:23:01 AUDIT txn=a1b2c3 user="admin@example.com" action=apply type=host name=web01 field=alias op=modify from="Old Alias" to="New Alias"
Feb 17 14:23:01 AUDIT txn=a1b2c3 user="admin@example.com" action=apply type=host name=web01 field=address op=modify from="10.0.0.1" to="10.0.0.2"
Feb 17 14:23:01 AUDIT txn=a1b2c3 user="admin@example.com" action=apply type=service name=web01-http op=create
Feb 17 14:23:05 AUDIT txn=d4e5f6 user="admin@example.com" action=backup_restore description="pre_apply"
Feb 17 14:23:10 AUDIT txn=g7h8i9 user="admin@example.com" action=git_commit message="Updated host configs"
```

- `txn` ties changes from the same Apply together (grouping key for UI)
- One line per field change for object edits; one line per create/delete/move/git/backup action
- Parseable with `grep`, `awk`, or Python regex/split

### Rotation (both files)

- `RotatingFileHandler` with configurable max size (default 10MB)
- Configurable backup count (default 5)
- Rotated files: `app.log.1`, `app.log.2`, etc. (no gzip)

## Frontend — Unified Log Page

### Page Structure

Replaces `/audit-log`. Single page at `/logs` with two tabs:

```
[Audit Log]  [Application Log]
─────────────────────────────────────────────
[Search: ___________]  [Filter chips]  [Download]  [Clear]
─────────────────────────────────────────────
| Timestamp | User | Action | Object | Details |
|-----------|------|--------|--------|---------|
```

### Styling

Follows existing git/backup table patterns exactly:
- `border-collapse: collapse` with `--nbe-*` CSS variables
- Column headers: secondary background, 2px bottom border, bold text
- Alternating rows: `nth-child(even)` with tertiary background
- Hover state on rows
- Badges: existing pill style (accent background, small rounded)
- User display: backup table pattern (name + email in secondary accent)
- Filter chips: existing chip style from current audit log sidebar
- All spacing, fonts, and colors from existing design system

### Audit Log Tab — Columns

| Column | Width | Content |
|--------|-------|---------|
| Timestamp | ~150px | `Feb 17 14:23:01` |
| User | ~180px | Email address |
| Action | ~100px | Badge: Apply, Backup, Git |
| Object | ~200px | `type/name` (e.g. `host/web01`) |
| Details | auto | Field change summary: `alias: "Old" -> "New"` |

**Transaction grouping:** Rows sharing the same `txn` ID get a shared left border (accent color) and a subtle shared background. First row in a group shows timestamp/user/action; subsequent rows omit/grey them out.

### Application Log Tab — Columns

| Column | Width | Content |
|--------|-------|---------|
| Timestamp | ~150px | `Feb 17 14:23:01` |
| Level | ~80px | Badge: INFO (blue), WARNING (yellow), ERROR (red) |
| Source | ~180px | Module name (e.g. `nagios_parser`) |
| Message | auto | The log message |

### Filters

- **Audit tab:** Action type chips: Creates, Edits, Moves, Deletes, Git, Backups
- **App tab:** Log level chips: DEBUG, INFO, WARNING, ERROR

### Pagination

- Newest entries first
- 100 entries at a time with "load more" button

## API Endpoints

### New

| Endpoint | Method | Purpose | Params |
|----------|--------|---------|--------|
| `/api/logs/audit` | GET | Parse `audit.log`, return JSON for table | `limit`, `offset`, `action` |
| `/api/logs/audit/download` | GET | Download raw `audit.log` | — |
| `/api/logs/audit/clear` | POST | Truncate `audit.log` | — |
| `/api/logs/app` | GET | Parse `app.log`, return JSON for table | `limit`, `offset`, `level` |
| `/api/logs/app/download` | GET | Download raw `app.log` | — |
| `/api/logs/app/clear` | POST | Truncate `app.log` | — |
| `/api/logs/archives` | GET | List rotated files for both types | — |

### Removed

| Endpoint | Replacement |
|----------|-------------|
| `/api/logs/operations` | `/api/logs/app` |
| `/api/logs/operations/download` | `/api/logs/app/download` |
| `/api/audit-log` (POST/GET) | `/api/logs/audit` |
| `/api/audit-log/archives` | `/api/logs/archives` |
| `/api/audit-log/clear` | `/api/logs/audit/clear` |

### Response Formats

**`/api/logs/audit`:**
```json
{
  "success": true,
  "data": {
    "entries": [
      {
        "timestamp": "2026-02-17T14:23:01",
        "txn": "a1b2c3",
        "user": "admin@example.com",
        "action": "apply",
        "type": "host",
        "name": "web01",
        "field": "alias",
        "op": "modify",
        "from": "Old",
        "to": "New"
      }
    ],
    "total": 1523,
    "has_more": true
  }
}
```

**`/api/logs/app`:**
```json
{
  "success": true,
  "data": {
    "entries": [
      {
        "timestamp": "2026-02-17T14:23:01",
        "level": "INFO",
        "source": "backup",
        "operation": "create_backup",
        "message": "Created backup pre_apply (user=admin@example.com)"
      }
    ],
    "total": 8401,
    "has_more": true
  }
}
```

## Backend Module Changes

### Delete
- `operation_logger.py` — replaced by stdlib logging

### Simplify
- `audit_service.py` — rewrite to thin wrapper around `logging.getLogger("audit")`:
  ```python
  import logging

  audit_logger = logging.getLogger("audit")

  def log_audit(action, user=None, txn=None, **kwargs):
      parts = [f"AUDIT txn={txn} user=\"{user}\" action={action}"]
      for k, v in kwargs.items():
          parts.append(f'{k}="{v}"' if " " in str(v) else f"{k}={v}")
      audit_logger.info(" ".join(parts))
  ```

### Modify
- **`app.py`** — configure two `RotatingFileHandler`s in `create_app()`, remove `OperationLogger` init
- **`routes/settings.py`** — remove old log endpoints, keep logging config endpoints
- **`routes/staging.py`** — `write_audit_log()` → `log_audit()` calls
- **`routes/backups.py`** — same
- **`routes/git.py`** — same
- **`nagios_service.py`** — remove `op_logger` dependency, use stdlib logger
- **`backup_manager.py`** — same
- **`git_service.py`** — same
- **`staging_manager.py`** — same
- **`file_operations.py`** — remove `set_logger()`, use `logging.getLogger(__name__)`

### Create
- **`routes/logs.py`** — new blueprint for `/api/logs/*` endpoints + `.log` file parsing
- **`templates/logs.html`** — unified log page (replaces `audit_log.html`)
- **`static/js/logs.js`** — tab switching, table rendering, search, filters, pagination
- **`static/css/logs.css`** — table styling following git/backup patterns

### Remove (frontend)
- **`templates/audit_log.html`** — replaced by `logs.html`
- **`static/css/audit_log.css`** — replaced by `logs.css`
- **`static/js/audit_log.js`** — replaced by `logs.js`

### Navigation
- Rename sidebar link from "Audit Log" to "Logs", point to `/logs`

## Testing

### Update
- Audit service tests — rewrite for new `log_audit()` function and key=value format
- Route tests mocking `write_audit_log` — update to mock `log_audit`

### Delete
- `operation_logger` tests — module removed

### New
- Log parsing: `/api/logs/audit` and `/api/logs/app` correctly parse `.log` files
- Key=value parser: edge cases (spaces, quotes, empty fields, malformed lines)
- Transaction grouping: entries with same `txn` returned together
- Rotation: `RotatingFileHandler` config works correctly
- Filter/pagination: `limit`, `offset`, `level`, `action` params

## Migration

No migration of existing log data. New system starts with empty `.log` files. Old `.jsonl` and `.json` files remain on disk for manual cleanup. Settings config values (max size, backup count, log level) carry over from `config/settings.json`.
