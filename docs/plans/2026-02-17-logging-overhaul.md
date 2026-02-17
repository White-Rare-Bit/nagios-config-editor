# Logging System Overhaul — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace custom JSONL/JSON logging with Python stdlib `logging` producing plain-text `.log` files, and replace the card-based audit log page with a unified table-based log viewer.

**Architecture:** Two `RotatingFileHandler`s configured in `app.py`: one for app logs (syslog-style), one for audit logs (key=value format). `operation_logger.py` is deleted; `audit_service.py` becomes a thin wrapper. A new `/logs` page with two tabs replaces the old `/audit-log` page.

**Tech Stack:** Python stdlib `logging`, Flask blueprints, plain JavaScript, CSS following existing `--nbe-*` design system.

**Design doc:** `docs/plans/2026-02-17-logging-overhaul-design.md`

---

## Task 1: Rewrite `audit_service.py` to use stdlib logging

**Files:**
- Modify: `audit_service.py` (lines 1-137 — full rewrite)
- Test: `tests/test_audit_service.py`

**Step 1: Write tests for new `log_audit()` function**

Create `tests/test_audit_service.py`:

```python
"""Tests for audit_service — key=value log line formatting."""

import logging

from audit_service import format_audit_line, log_audit


class TestFormatAuditLine:
    """Test key=value line formatting."""

    def test_basic_apply_modify(self):
        line = format_audit_line(
            action="apply", txn="abc123", user="admin@example.com",
            type="host", name="web01", field="alias", op="modify",
            from_val="Old Alias", to_val="New Alias",
        )
        assert "AUDIT" in line
        assert 'txn=abc123' in line
        assert 'user="admin@example.com"' in line
        assert "action=apply" in line
        assert "type=host" in line
        assert "name=web01" in line
        assert "field=alias" in line
        assert "op=modify" in line
        assert 'from="Old Alias"' in line
        assert 'to="New Alias"' in line

    def test_create_action(self):
        line = format_audit_line(
            action="apply", txn="abc123", user="admin@example.com",
            type="service", name="web01-http", op="create",
        )
        assert "op=create" in line
        assert "field" not in line

    def test_backup_action(self):
        line = format_audit_line(
            action="backup_restore", txn="def456", user="admin@example.com",
            description="pre_apply",
        )
        assert "action=backup_restore" in line
        assert "description=pre_apply" in line

    def test_git_commit_action(self):
        line = format_audit_line(
            action="git_commit", txn="ghi789", user="admin@example.com",
            message="Updated host configs",
        )
        assert "action=git_commit" in line
        assert 'message="Updated host configs"' in line

    def test_values_with_spaces_get_quoted(self):
        line = format_audit_line(
            action="apply", txn="abc", user="a@b.com",
            name="my host",
        )
        assert 'name="my host"' in line

    def test_values_without_spaces_not_quoted(self):
        line = format_audit_line(
            action="apply", txn="abc", user="a@b.com",
            type="host",
        )
        assert "type=host" in line

    def test_empty_value(self):
        line = format_audit_line(
            action="apply", txn="abc", user="a@b.com",
            description="",
        )
        assert 'description=""' in line

    def test_values_with_quotes_get_escaped(self):
        line = format_audit_line(
            action="apply", txn="abc", user="a@b.com",
            from_val='value with "quotes"',
        )
        # Quotes inside values should be escaped
        assert 'from="value with \\"quotes\\""' in line


class TestLogAudit:
    """Test that log_audit writes to the audit logger."""

    def test_log_audit_writes_to_logger(self, caplog):
        with caplog.at_level(logging.INFO, logger="audit"):
            log_audit(
                action="apply", user="admin@example.com", txn="abc123",
                type="host", name="web01", op="modify",
            )
        assert len(caplog.records) == 1
        assert "AUDIT" in caplog.records[0].message
        assert "txn=abc123" in caplog.records[0].message

    def test_log_audit_generates_txn_if_none(self, caplog):
        with caplog.at_level(logging.INFO, logger="audit"):
            log_audit(action="backup_created", user="admin@example.com")
        assert "txn=" in caplog.records[0].message
        # Should be a non-empty txn value
        msg = caplog.records[0].message
        txn_start = msg.index("txn=") + 4
        txn_end = msg.index(" ", txn_start)
        assert len(msg[txn_start:txn_end]) > 0
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_audit_service.py -v`
Expected: FAIL — `format_audit_line` and new `log_audit` signature don't exist yet.

**Step 3: Implement the new `audit_service.py`**

Replace `audit_service.py` entirely:

```python
"""Audit logging service — writes key=value lines to audit.log via stdlib logging.

Each audit event is a single log line in the format:
    AUDIT txn=<id> user="<email>" action=<type> key1=value1 key2="value with spaces"

Transaction IDs (txn) group related changes from a single Apply operation.
"""

import logging
import uuid


audit_logger = logging.getLogger("audit")


def format_audit_line(action, txn=None, user=None, **kwargs):
    """Format an audit event as a key=value log line.

    Args:
        action: The action type (apply, backup_created, git_commit, etc.)
        txn: Transaction ID for grouping related changes. Auto-generated if None.
        user: User email address.
        **kwargs: Additional key=value pairs. Use from_val/to_val for
                  from/to fields (since 'from' is a Python keyword).

    Returns:
        Formatted string like: AUDIT txn=abc123 user="a@b.com" action=apply ...

    """
    if txn is None:
        txn = uuid.uuid4().hex[:8]

    parts = [f"AUDIT txn={txn} user=\"{user or ''}\" action={action}"]

    # Rename from_val/to_val to from/to in output
    renamed = {}
    for k, v in kwargs.items():
        if k == "from_val":
            renamed["from"] = v
        elif k == "to_val":
            renamed["to"] = v
        else:
            renamed[k] = v

    for k, v in renamed.items():
        v_str = str(v) if v is not None else ""
        if '"' in v_str:
            v_str = v_str.replace('"', '\\"')
            parts.append(f'{k}="{v_str}"')
        elif not v_str or " " in v_str:
            parts.append(f'{k}="{v_str}"')
        else:
            parts.append(f"{k}={v_str}")

    return " ".join(parts)


def log_audit(action, user=None, txn=None, **kwargs):
    """Write an audit log line.

    Args:
        action: The action type.
        user: User email address.
        txn: Transaction ID. Auto-generated if None.
        **kwargs: Additional key=value pairs for the log line.

    """
    line = format_audit_line(action, txn=txn, user=user, **kwargs)
    audit_logger.info(line)
```

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_audit_service.py -v`
Expected: All PASS.

**Step 5: Commit**

```bash
git add audit_service.py tests/test_audit_service.py
git commit -m "refactor: rewrite audit_service to use stdlib logging with key=value format"
```

---

## Task 2: Configure stdlib logging in `app.py`

**Files:**
- Modify: `app.py` (lines 16, 70-96, 130-132)
- Test: `tests/test_app_logging.py`

**Step 1: Write tests for logging configuration**

Create `tests/test_app_logging.py`:

```python
"""Tests for app-level logging configuration."""

import logging
import os
import tempfile

from app import create_app


class TestLoggingSetup:
    """Verify that create_app configures both log handlers."""

    def test_app_logger_has_file_handler(self):
        """App logger should write to logs/app.log."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "logs")
            app = create_app({"TESTING": True, "LOG_DIR": log_dir})
            # Check that a file handler exists on the root logger or app logger
            root = logging.getLogger()
            file_handlers = [
                h for h in root.handlers
                if hasattr(h, "baseFilename") and "app.log" in h.baseFilename
            ]
            assert len(file_handlers) >= 1

    def test_audit_logger_has_file_handler(self):
        """Audit logger should write to logs/audit.log."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "logs")
            app = create_app({"TESTING": True, "LOG_DIR": log_dir})
            audit = logging.getLogger("audit")
            file_handlers = [
                h for h in audit.handlers
                if hasattr(h, "baseFilename") and "audit.log" in h.baseFilename
            ]
            assert len(file_handlers) >= 1

    def test_app_log_format_is_syslog_style(self):
        """App log lines should match syslog-style format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "logs")
            app = create_app({"TESTING": True, "LOG_DIR": log_dir})

            test_logger = logging.getLogger("test_module")
            test_logger.info("Test message")

            log_path = os.path.join(log_dir, "app.log")
            with open(log_path) as f:
                line = f.readline()
            assert "nagios-editor" in line
            assert "[INFO]" in line
            assert "Test message" in line

    def test_audit_log_format_is_passthrough(self):
        """Audit log lines should pass through the message unmodified (formatter adds only timestamp)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "logs")
            app = create_app({"TESTING": True, "LOG_DIR": log_dir})

            audit = logging.getLogger("audit")
            audit.info('AUDIT txn=abc123 user="admin@example.com" action=apply')

            log_path = os.path.join(log_dir, "audit.log")
            with open(log_path) as f:
                line = f.readline()
            # Should have timestamp prefix + the raw AUDIT line
            assert "AUDIT txn=abc123" in line
            assert 'user="admin@example.com"' in line
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_app_logging.py -v`
Expected: FAIL — logging not yet configured for file output.

**Step 3: Modify `app.py` to configure logging**

In `app.py`, replace the `OperationLogger` initialization (lines 16, 70-96) with stdlib logging setup. The key changes:

1. Remove `from operation_logger import LogConfig, OperationLogger` (line 16)
2. Replace the OperationLogger block with:

```python
import logging
from logging.handlers import RotatingFileHandler

def _setup_logging(app, server_config):
    """Configure stdlib logging with file handlers for app and audit logs."""
    log_cfg = server_config.logging
    log_dir = app.config.get("LOG_DIR", log_cfg.log_dir or "logs")
    os.makedirs(log_dir, exist_ok=True)

    max_bytes = int((log_cfg.max_file_size_mb or 10) * 1024 * 1024)
    backup_count = log_cfg.max_backup_files or 5
    level = getattr(logging, (log_cfg.log_level or "INFO").upper(), logging.INFO)

    # App log — syslog-style format
    app_handler = RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=max_bytes, backupCount=backup_count,
    )
    app_formatter = logging.Formatter(
        fmt="%(asctime)s nagios-editor [%(levelname)s] %(name)s: %(message)s",
        datefmt="%b %d %H:%M:%S",
    )
    app_handler.setFormatter(app_formatter)
    app_handler.setLevel(level)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(app_handler)

    # Audit log — minimal format (timestamp + raw message)
    audit_handler = RotatingFileHandler(
        os.path.join(log_dir, "audit.log"),
        maxBytes=max_bytes, backupCount=backup_count,
    )
    audit_formatter = logging.Formatter(
        fmt="%(asctime)s %(message)s",
        datefmt="%b %d %H:%M:%S",
    )
    audit_handler.setFormatter(audit_formatter)
    audit_handler.setLevel(logging.INFO)

    audit_logger = logging.getLogger("audit")
    audit_logger.addHandler(audit_handler)
    audit_logger.propagate = False  # Don't duplicate audit lines into app.log

    # Store config for settings page
    app.extensions["log_dir"] = log_dir
    app.extensions["log_config"] = {
        "level": log_cfg.log_level or "INFO",
        "max_size_mb": log_cfg.max_file_size_mb or 10,
        "backup_count": log_cfg.max_backup_files or 5,
    }
```

3. In `create_app()`, call `_setup_logging(app, server_config)` instead of creating OperationLogger
4. Remove `op_logger` parameter from all service constructors: `StagingManager(...)`, `NagiosService(...)`, `BackupManager(...)`, `GitService(...)`
5. Remove `file_operations.set_logger(op_logger)` call
6. Remove `app.extensions["op_logger"] = op_logger`

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_app_logging.py -v`
Expected: All PASS.

**Step 5: Commit**

```bash
git add app.py tests/test_app_logging.py
git commit -m "refactor: configure stdlib logging handlers in app.py, remove OperationLogger"
```

---

## Task 3: Remove `op_logger` from services

**Files:**
- Modify: `nagios_service.py`, `backup_manager.py`, `git_service.py`, `staging_manager.py`, `file_operations.py`
- Modify: `routes/helpers.py` (remove `get_op_logger`)
- Delete: `operation_logger.py`

**Step 1: Update each service module**

For each service, the pattern is the same:
1. Remove `op_logger` constructor parameter and `self._op_logger` attribute
2. Add `logger = logging.getLogger(__name__)` at module level (if not already present)
3. Replace all `if self._op_logger: self._op_logger.info(...)` calls with `logger.info(...)`

**`nagios_service.py`:**
- Line 37-42: Remove `op_logger=None` param, remove `self._op_logger = op_logger`
- Add `logger = logging.getLogger(__name__)` near top
- Replace ~15 `if self._op_logger:` blocks with direct `logger.info(...)` / `logger.warning(...)` / `logger.error(...)` calls

**`backup_manager.py`:**
- Constructor: Remove `op_logger=None` param, remove `self._op_logger = op_logger`
- Add `logger = logging.getLogger(__name__)` near top
- Replace ~5 `if self._op_logger:` blocks with `logger.info(...)` calls

**`git_service.py`:**
- Line 133: Remove `op_logger` param, remove `self._op_logger = op_logger`
- Add `logger = logging.getLogger(__name__)` near top (if not present)
- Replace ~5 `if self._op_logger:` blocks with `logger.warning(...)` / `logger.error(...)` calls

**`staging_manager.py`:**
- Line 754: Remove `op_logger` param, remove `self._op_logger = op_logger`
- Add `logger = logging.getLogger(__name__)` near top (if not present)
- Replace ~5 `if self._op_logger:` blocks with `logger.info(...)` / `logger.debug(...)` calls

**`file_operations.py`:**
- Lines 15-22: Remove `_op_logger` module variable and `set_logger()` function entirely
- Add `logger = logging.getLogger(__name__)` near top
- Replace all `if _op_logger: _op_logger.debug(...)` calls with `logger.debug(...)` calls

**Step 2: Remove `get_op_logger` from helpers**

In `routes/helpers.py` (lines 94-96): Remove the `get_op_logger()` function.

**Step 3: Remove `get_op_logger` imports from routes**

In each route file that imports `get_op_logger`, remove it from the import list:
- `routes/staging.py` line 22
- `routes/backups.py` line 14
- `routes/git.py` line 15

Also remove any `op_log = get_op_logger()` calls and `if op_log:` blocks — these become direct `logger.info(...)` calls using a module-level logger.

**Step 4: Delete `operation_logger.py`**

```bash
git rm operation_logger.py
```

**Step 5: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All PASS (existing tests may need fixture updates for removed `op_logger` params).

**Step 6: Commit**

```bash
git add -A
git commit -m "refactor: remove op_logger from all services, use stdlib logging"
```

---

## Task 4: Update audit log callers in routes

**Files:**
- Modify: `routes/staging.py` (lines 13, 821-890)
- Modify: `routes/backups.py` (lines 8, 47, 101, 126, 145)
- Modify: `routes/git.py` (lines 7, 82-112, 427, 476, 569)

**Step 1: Write tests for route audit logging**

Create `tests/test_audit_routes.py`:

```python
"""Tests for audit log calls in route handlers."""

import logging
from unittest.mock import patch

import pytest

from app import create_app


@pytest.fixture
def app(tmp_path):
    """Create test app with temp config."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    app = create_app({
        "TESTING": True,
        "LOG_DIR": str(tmp_path / "logs"),
    })
    return app


class TestBackupAuditLogging:
    """Verify backup routes call log_audit."""

    def test_create_backup_logs_audit(self, app, caplog):
        with app.test_client() as client:
            with caplog.at_level(logging.INFO, logger="audit"):
                # This will fail without a proper config path, but we just
                # need to verify the audit call pattern compiles
                pass  # Placeholder — real test needs sample-config setup


class TestGitAuditLogging:
    """Verify git routes call log_audit."""

    def test_discard_all_logs_audit(self, app, caplog):
        with app.test_client() as client:
            with caplog.at_level(logging.INFO, logger="audit"):
                pass  # Placeholder — real test needs git repo setup
```

**Step 2: Update `routes/backups.py`**

Replace `from audit_service import write_audit_log` with `from audit_service import log_audit`.

Replace each `write_audit_log({...})` call. For example, the backup create (line 47-53):

Before:
```python
write_audit_log({
    "timestamp": datetime.now().isoformat(),
    "action": "backup_created",
    "description": description,
    "backup_path": os.path.basename(backup_path) if backup_path else None,
    **identity,
})
```

After:
```python
log_audit(
    action="backup_created",
    user=identity.get("userEmail", ""),
    description=description,
    backup_path=os.path.basename(backup_path) if backup_path else None,
)
```

Apply the same pattern to restore (line 101), delete_all (line 126), delete (line 145).

Also remove `op_log = get_op_logger()` calls and the `if op_log:` blocks — replace with `logger.info(...)` using a module-level `logger = logging.getLogger(__name__)`.

**Step 3: Update `routes/git.py`**

Same pattern:
- Replace `from audit_service import write_audit_log` with `from audit_service import log_audit`
- Rewrite `_write_commit_audit_log()` (lines 82-112) to use `log_audit()`
- Update discard_all (line 427), clear_history (line 476), restore (line 569)
- Remove `get_op_logger` import and usage, replace with module-level `logger`

**Step 4: Update `routes/staging.py`**

This is the most complex. The `_build_audit_entry()` function (lines 821-860) builds a dict with object_edits, object_moves, etc. This needs to be rewritten to emit multiple `log_audit()` calls — one line per change.

Replace `_write_audit_log_safely()` (lines 865-890):

```python
def _write_audit_log_safely(staging_data, session_id, all_details, errors, log):
    """Write audit log entries for an apply operation.

    Emits one log_audit() call per individual change, all sharing the same txn ID.
    """
    import uuid
    txn = uuid.uuid4().hex[:8]
    user = staging_data.get("userEmail", "")

    try:
        for phase_key, audit_key in _PHASE_TO_AUDIT_KEY.items():
            details = all_details.get(phase_key, [])
            for detail in details:
                if audit_key == "object_edits":
                    obj_type = detail.get("object_type", "")
                    obj_name = detail.get("object_name", "")
                    for change in detail.get("changes", []):
                        log_audit(
                            action="apply", user=user, txn=txn,
                            type=obj_type, name=obj_name,
                            field=change.get("key", ""),
                            op=change.get("type", "modify"),
                            from_val=change.get("from", ""),
                            to_val=change.get("to", ""),
                        )
                elif audit_key == "object_creations":
                    log_audit(
                        action="apply", user=user, txn=txn,
                        type=detail.get("object_type", ""),
                        name=detail.get("object_name", ""),
                        op="create",
                    )
                elif audit_key == "object_deletions":
                    log_audit(
                        action="apply", user=user, txn=txn,
                        type=detail.get("object_type", ""),
                        name=detail.get("object_name", ""),
                        op="delete",
                    )
                elif audit_key == "object_moves":
                    log_audit(
                        action="apply", user=user, txn=txn,
                        type=detail.get("object_type", ""),
                        name=detail.get("object_name", ""),
                        op="move",
                        from_val=detail.get("from_file", ""),
                        to_val=detail.get("to_file", ""),
                    )
                # File-level operations
                elif audit_key in ("file_creations", "file_deletions", "file_moves",
                                   "folder_creations", "folder_deletions", "folder_moves"):
                    op_type = audit_key.rstrip("s").split("_")[-1]  # creation->create, etc.
                    log_audit(
                        action="apply", user=user, txn=txn,
                        op=f"file_{op_type}" if "file" in audit_key else f"folder_{op_type}",
                        path=detail.get("path", detail.get("from", "")),
                    )

        if errors:
            for error in errors:
                log_audit(action="apply_error", user=user, txn=txn, error=str(error))

        return True, None
    except Exception as e:
        error_msg = f"Failed to write audit log: {e}"
        log.exception(error_msg)
        return False, error_msg
```

**Step 5: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All PASS.

**Step 6: Commit**

```bash
git add routes/staging.py routes/backups.py routes/git.py tests/test_audit_routes.py
git commit -m "refactor: update all route audit callers to use log_audit()"
```

---

## Task 5: Create log parsing and API endpoints (`routes/logs.py`)

**Files:**
- Create: `routes/logs.py`
- Modify: `routes/__init__.py` (register new blueprint)
- Modify: `routes/settings.py` (remove old log endpoints, lines 201-454)
- Test: `tests/test_log_routes.py`

**Step 1: Write tests for log parsing**

Create `tests/test_log_routes.py`:

```python
"""Tests for log API endpoints and log file parsing."""

import os
import tempfile

import pytest


# Import the parsing functions directly once created
from routes.logs import parse_audit_line, parse_app_line


class TestParseAuditLine:
    """Test parsing key=value audit log lines."""

    def test_basic_modify(self):
        line = 'Feb 17 14:23:01 AUDIT txn=abc123 user="admin@example.com" action=apply type=host name=web01 field=alias op=modify from="Old" to="New"'
        result = parse_audit_line(line)
        assert result["timestamp"] == "Feb 17 14:23:01"
        assert result["txn"] == "abc123"
        assert result["user"] == "admin@example.com"
        assert result["action"] == "apply"
        assert result["type"] == "host"
        assert result["name"] == "web01"
        assert result["op"] == "modify"
        assert result["from"] == "Old"
        assert result["to"] == "New"

    def test_unquoted_values(self):
        line = "Feb 17 14:23:01 AUDIT txn=abc user=a@b.com action=apply type=host name=web01 op=create"
        result = parse_audit_line(line)
        assert result["user"] == "a@b.com"
        assert result["op"] == "create"

    def test_quoted_value_with_spaces(self):
        line = 'Feb 17 14:23:01 AUDIT txn=abc user="a@b.com" action=apply name="my host"'
        result = parse_audit_line(line)
        assert result["name"] == "my host"

    def test_empty_quoted_value(self):
        line = 'Feb 17 14:23:01 AUDIT txn=abc user="a@b.com" action=apply description=""'
        result = parse_audit_line(line)
        assert result["description"] == ""

    def test_malformed_line_returns_none(self):
        result = parse_audit_line("not a valid log line")
        assert result is None

    def test_escaped_quotes_in_value(self):
        line = 'Feb 17 14:23:01 AUDIT txn=abc user="a@b.com" action=apply from="value with \\"quotes\\""'
        result = parse_audit_line(line)
        assert result["from"] == 'value with "quotes"'


class TestParseAppLine:
    """Test parsing syslog-style app log lines."""

    def test_basic_info(self):
        line = "Feb 17 14:23:01 nagios-editor [INFO] backup_manager: Created backup pre_apply"
        result = parse_app_line(line)
        assert result["timestamp"] == "Feb 17 14:23:01"
        assert result["level"] == "INFO"
        assert result["source"] == "backup_manager"
        assert result["message"] == "Created backup pre_apply"

    def test_warning_level(self):
        line = "Feb 17 14:23:01 nagios-editor [WARNING] nagios_parser: Syntax issue in hosts.cfg"
        result = parse_app_line(line)
        assert result["level"] == "WARNING"

    def test_error_level(self):
        line = "Feb 17 14:23:01 nagios-editor [ERROR] git_service: Failed to commit"
        result = parse_app_line(line)
        assert result["level"] == "ERROR"

    def test_malformed_line_returns_none(self):
        result = parse_app_line("garbage")
        assert result is None
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_log_routes.py -v`
Expected: FAIL — `routes.logs` module doesn't exist.

**Step 3: Create `routes/logs.py`**

```python
"""Log viewer API routes — serves parsed log data for the unified log page."""

import logging
import os
import re

from flask import Blueprint, current_app, jsonify, request, send_file

bp = Blueprint("logs", __name__)
logger = logging.getLogger(__name__)

# Regex for parsing key=value pairs (handles quoted and unquoted values)
_KV_PATTERN = re.compile(r'(\w+)=(?:"((?:[^"\\]|\\.)*)"|(\S*))')

# Regex for parsing syslog-style app log lines
_APP_PATTERN = re.compile(
    r'^(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+nagios-editor\s+\[(\w+)\]\s+([\w.]+):\s+(.*)'
)

# Timestamp prefix pattern for audit lines
_AUDIT_TS_PATTERN = re.compile(
    r'^(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+AUDIT\s+(.*)'
)


def _get_log_dir():
    """Get the log directory path."""
    return current_app.extensions.get("log_dir", "logs")


def parse_audit_line(line):
    """Parse an audit log line into a dict.

    Returns None if the line doesn't match the expected format.
    """
    line = line.strip()
    match = _AUDIT_TS_PATTERN.match(line)
    if not match:
        return None

    timestamp = match.group(1)
    kv_part = match.group(2)

    result = {"timestamp": timestamp}
    for m in _KV_PATTERN.finditer(kv_part):
        key = m.group(1)
        value = m.group(2) if m.group(2) is not None else m.group(3)
        # Unescape quotes
        if value and '\\"' in value:
            value = value.replace('\\"', '"')
        result[key] = value

    return result


def parse_app_line(line):
    """Parse an app log line into a dict.

    Returns None if the line doesn't match the expected format.
    """
    line = line.strip()
    match = _APP_PATTERN.match(line)
    if not match:
        return None

    return {
        "timestamp": match.group(1),
        "level": match.group(2),
        "source": match.group(3),
        "message": match.group(4),
    }


def _read_log_entries(log_path, parser_fn, limit=100, offset=0, filter_key=None, filter_value=None):
    """Read and parse log entries from a .log file.

    Returns entries in reverse order (newest first).
    """
    if not os.path.exists(log_path):
        return [], 0

    try:
        with open(log_path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return [], 0

    total = len(lines)
    entries = []
    skipped = 0

    for line in reversed(lines):
        entry = parser_fn(line)
        if entry is None:
            continue
        if filter_key and filter_value:
            if entry.get(filter_key, "").upper() != filter_value.upper():
                continue
        if skipped < offset:
            skipped += 1
            continue
        entries.append(entry)
        if len(entries) >= limit:
            break

    return entries, total


@bp.route("/api/logs/audit", methods=["GET"])
def api_get_audit_logs():
    """Get parsed audit log entries."""
    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)
    action_filter = request.args.get("action", "")

    log_path = os.path.join(_get_log_dir(), "audit.log")
    entries, total = _read_log_entries(
        log_path, parse_audit_line, limit, offset,
        filter_key="action" if action_filter else None,
        filter_value=action_filter or None,
    )

    return jsonify({
        "success": True,
        "data": {
            "entries": entries,
            "total": total,
            "has_more": offset + len(entries) < total,
        },
    })


@bp.route("/api/logs/audit/download", methods=["GET"])
def api_download_audit_log():
    """Download raw audit.log file."""
    log_path = os.path.join(_get_log_dir(), "audit.log")
    if not os.path.exists(log_path):
        return jsonify({"error": "Log file not found"}), 404
    return send_file(log_path, mimetype="text/plain", as_attachment=True, download_name="audit.log")


@bp.route("/api/logs/audit/clear", methods=["POST"])
def api_clear_audit_log():
    """Truncate the audit log file."""
    log_path = os.path.join(_get_log_dir(), "audit.log")
    try:
        with open(log_path, "w") as f:
            f.truncate(0)
        return jsonify({"success": True})
    except OSError as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/logs/app", methods=["GET"])
def api_get_app_logs():
    """Get parsed application log entries."""
    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)
    level_filter = request.args.get("level", "")

    log_path = os.path.join(_get_log_dir(), "app.log")
    entries, total = _read_log_entries(
        log_path, parse_app_line, limit, offset,
        filter_key="level" if level_filter else None,
        filter_value=level_filter or None,
    )

    return jsonify({
        "success": True,
        "data": {
            "entries": entries,
            "total": total,
            "has_more": offset + len(entries) < total,
        },
    })


@bp.route("/api/logs/app/download", methods=["GET"])
def api_download_app_log():
    """Download raw app.log file."""
    log_path = os.path.join(_get_log_dir(), "app.log")
    if not os.path.exists(log_path):
        return jsonify({"error": "Log file not found"}), 404
    return send_file(log_path, mimetype="text/plain", as_attachment=True, download_name="app.log")


@bp.route("/api/logs/app/clear", methods=["POST"])
def api_clear_app_log():
    """Truncate the application log file."""
    log_path = os.path.join(_get_log_dir(), "app.log")
    try:
        with open(log_path, "w") as f:
            f.truncate(0)
        return jsonify({"success": True})
    except OSError as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/logs/archives", methods=["GET"])
def api_list_log_archives():
    """List rotated log files for both log types."""
    log_dir = _get_log_dir()
    archives = {"audit": [], "app": []}

    try:
        for filename in os.listdir(log_dir):
            filepath = os.path.join(log_dir, filename)
            stat = os.stat(filepath)
            entry = {
                "filename": filename,
                "size": stat.st_size,
                "modified": stat.st_mtime,
            }
            if filename.startswith("audit.log."):
                archives["audit"].append(entry)
            elif filename.startswith("app.log."):
                archives["app"].append(entry)

        archives["audit"].sort(key=lambda x: x["filename"])
        archives["app"].sort(key=lambda x: x["filename"])

        return jsonify({"success": True, "data": archives})
    except OSError as e:
        return jsonify({"error": str(e)}), 500
```

**Step 4: Register blueprint in `routes/__init__.py`**

Add to `register_blueprints()`:

```python
from .logs import bp as logs_bp
app.register_blueprint(logs_bp)
```

**Step 5: Remove old log endpoints from `routes/settings.py`**

Remove lines 201-454 (everything from `api_get_logging_settings` through `api_get_audit_archive`). Keep the logging *configuration* endpoints — move them into `routes/logs.py` or keep them in settings (they configure log level/size, not view logs). The settings page still needs to show logging config controls.

Actually, keep `api_get_logging_settings` and `api_update_logging_settings` in `routes/settings.py` but update them to work with the new `app.extensions["log_config"]` instead of `get_op_logger()`. Remove everything from line 263 onward (the old viewer/download/audit endpoints).

Remove these imports from `routes/settings.py`:
```python
from audit_service import get_audit_log_dir, get_audit_log_path, rotate_audit_log
from operation_logger import LogConfig
```

**Step 6: Run tests**

Run: `python3 -m pytest tests/test_log_routes.py tests/ -v`
Expected: All PASS.

**Step 7: Commit**

```bash
git add routes/logs.py routes/__init__.py routes/settings.py tests/test_log_routes.py
git commit -m "feat: add log API endpoints with .log file parsing, remove old endpoints"
```

---

## Task 6: Create unified log page template and route

**Files:**
- Create: `templates/logs.html`
- Modify: `routes/pages.py` (add `/logs` route, remove `/audit-log`)
- Modify: `templates/base.html` (update nav link)

**Step 1: Create `templates/logs.html`**

Reference `templates/git.html` and `templates/backups.html` for the existing page structure pattern (extends base, has a main content area). The template should have:

- Two tab buttons (Audit Log / Application Log)
- A toolbar row with search input, filter chips, download button, clear button
- A table container that JavaScript will populate
- Script tag loading `logs.js`

```html
{% extends "base.html" %}
{% block title %}Logs{% endblock %}

{% block extra_css %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/logs.css') }}">
{% endblock %}

{% block content %}
<div class="logs-page">
    <div class="logs-header">
        <div class="logs-tabs">
            <button class="logs-tab active" data-tab="audit">Audit Log</button>
            <button class="logs-tab" data-tab="app">Application Log</button>
        </div>
    </div>

    <div class="logs-toolbar">
        <input type="text" class="logs-search" placeholder="Search logs..." />
        <div class="logs-filters" id="logsFilters">
            <!-- Filter chips injected by JS based on active tab -->
        </div>
        <div class="logs-toolbar-actions">
            <button class="btn btn-secondary" data-action="downloadLog" title="Download">Download</button>
            <button class="btn btn-danger-outline" data-action="clearLog" title="Clear">Clear</button>
        </div>
    </div>

    <div class="logs-table-container">
        <table class="logs-table" id="logsTable">
            <thead id="logsTableHead">
                <!-- Column headers injected by JS based on active tab -->
            </thead>
            <tbody id="logsTableBody">
                <!-- Rows injected by JS -->
            </tbody>
        </table>
        <div class="logs-empty" id="logsEmpty" style="display:none;">
            No log entries found.
        </div>
    </div>

    <div class="logs-footer">
        <span class="logs-count" id="logsCount"></span>
        <button class="btn btn-secondary" id="loadMoreBtn" style="display:none;" data-action="loadMore">
            Load More
        </button>
    </div>
</div>
{% endblock %}

{% block extra_js %}
<script src="{{ url_for('static', filename='js/logs.js') }}"></script>
{% endblock %}
```

**Step 2: Add `/logs` route to `routes/pages.py`**

```python
@bp.route("/logs")
def logs():
    """Unified log viewer page."""
    return render_template("logs.html")
```

Remove or redirect the old `/audit-log` route.

**Step 3: Update nav link in `templates/base.html`**

Change line ~32-33 from:
```html
<a class="nav-link {% if request.endpoint == 'pages.audit_log' %}active{% endif %}" href="{{ url_for('pages.audit_log') }}">Audit Log</a>
```
To:
```html
<a class="nav-link {% if request.endpoint == 'pages.logs' %}active{% endif %}" href="{{ url_for('pages.logs') }}">Logs</a>
```

**Step 4: Commit**

```bash
git add templates/logs.html routes/pages.py templates/base.html
git commit -m "feat: add unified log page template and route"
```

---

## Task 7: Create log page CSS (`static/css/logs.css`)

**Files:**
- Create: `static/css/logs.css`

**Step 1: Create the CSS**

Follow existing patterns from `static/css/git.css` (lines 525-712 for the history table) and `static/css/backups.css` (lines 116-287 for the backup table). Use `--nbe-*` CSS variables throughout.

Key selectors to implement:
- `.logs-page` — page container
- `.logs-tabs` / `.logs-tab` — tab buttons (active state with bottom border)
- `.logs-toolbar` — search + filters + actions row
- `.logs-search` — search input matching existing input styling
- `.logs-filters` — filter chip container
- `.logs-filter-chip` — individual filter chip (reuse existing audit chip pattern)
- `.logs-table` — `border-collapse: collapse`
- `.logs-table th` — secondary background, 2px bottom border
- `.logs-table td` — padding, vertical alignment
- `.logs-table tbody tr:nth-child(even)` — tertiary background
- `.logs-table tbody tr:hover` — hover background
- `.logs-badge` — level/action badges (INFO=blue, WARNING=yellow, ERROR=red, Apply=green, Git=blue, Backup=accent)
- `.logs-txn-group` — shared left border + subtle background for transaction grouping
- `.logs-txn-group-continuation td:first-child` — dimmed/omitted timestamp for grouped rows
- `.logs-empty` — empty state styling
- `.logs-footer` — load more button container

**Step 2: Commit**

```bash
git add static/css/logs.css
git commit -m "feat: add logs page CSS following existing table patterns"
```

---

## Task 8: Create log page JavaScript (`static/js/logs.js`)

**Files:**
- Create: `static/js/logs.js`
- Reference: `static/js/audit-log.js` for patterns, `static/js/base.js` for `ApiClient` and `data-action` delegation

**Step 1: Create `static/js/logs.js`**

The module should handle:

1. **Tab switching** — click handlers on `.logs-tab` buttons, switch active tab, reload data
2. **Data fetching** — `ApiClient.get('/api/logs/audit')` and `ApiClient.get('/api/logs/app')` with limit/offset params
3. **Table rendering** — different column layouts per tab:
   - Audit: Timestamp, User, Action (badge), Object (type/name), Details (field changes)
   - App: Timestamp, Level (badge), Source, Message
4. **Transaction grouping** — for audit tab, group rows by `txn` ID, apply `.logs-txn-group` class, dim repeated timestamp/user/action on continuation rows
5. **Search** — client-side text filter across visible entries
6. **Filter chips** — audit: Creates, Edits, Moves, Deletes, Git, Backups; app: DEBUG, INFO, WARNING, ERROR
7. **Load more** — increment offset, append rows
8. **Download** — `window.location.href = '/api/logs/{type}/download'`
9. **Clear** — confirm dialog, then `ApiClient.post('/api/logs/{type}/clear')`, reload

Use `data-action` event delegation pattern from `base.js`.

**Step 2: Commit**

```bash
git add static/js/logs.js
git commit -m "feat: add logs page JavaScript with tabs, table rendering, filters"
```

---

## Task 9: Remove old audit log frontend files

**Files:**
- Delete: `templates/audit_log.html`
- Delete: `static/css/audit_log.css`
- Delete: `static/js/audit-log.js`

**Step 1: Remove old files**

```bash
git rm templates/audit_log.html static/css/audit_log.css static/js/audit-log.js
```

**Step 2: Search for any remaining references**

Check for any imports, links, or references to the old files:
- `audit_log.html` in templates
- `audit_log.css` in HTML
- `audit-log.js` in HTML
- `/audit-log` URL in JavaScript

Fix any remaining references.

**Step 3: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All PASS.

**Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove old audit log frontend files"
```

---

## Task 10: Update settings page logging section

**Files:**
- Modify: `routes/settings.py` (update logging config endpoints)
- Modify: `templates/settings.html` (remove download button, simplify logging section)
- Modify: `static/js/settings.js` (remove `downloadLog`, update settings functions)

**Step 1: Update `routes/settings.py` logging config endpoints**

The `api_get_logging_settings` and `api_update_logging_settings` need to work with `app.extensions["log_config"]` and stdlib logging instead of the old `OperationLogger`. Update to read/write config and reconfigure the root logger's handler at runtime.

**Step 2: Simplify settings template**

Remove the download button and log file path display from the logging section in `templates/settings.html`. Keep only the configuration controls (enable/disable, level, max size, backup count). Add a link: "View logs →" pointing to `/logs`.

**Step 3: Update `static/js/settings.js`**

Remove the `downloadLog()` function. Update `loadLoggingSettings()` and `saveLoggingSettings()` if the response format changed.

**Step 4: Run tests**

Run: `python3 -m pytest tests/ -v`
Expected: All PASS.

**Step 5: Commit**

```bash
git add routes/settings.py templates/settings.html static/js/settings.js
git commit -m "refactor: simplify settings logging section, link to unified log page"
```

---

## Task 11: Update documentation and references

**Files:**
- Modify: `CLAUDE.md` (update module index)
- Modify: `.claude/ROUTES_REFERENCE.md` (update endpoint list)
- Modify: `routes/CLAUDE.md` (update route table)
- Delete: any test files for removed modules

**Step 1: Update CLAUDE.md**

- Remove `operation_logger.py` from module index
- Update `audit_service.py` description: "Audit log writer" → "Audit log formatting (key=value lines via stdlib logging)"
- Add `routes/logs.py` to route descriptions
- Update the Settings routes to reflect removed endpoints

**Step 2: Update route reference docs**

Update `.claude/ROUTES_REFERENCE.md` and `routes/CLAUDE.md` to reflect:
- New `/api/logs/*` endpoints
- Removed `/api/audit-log/*` and `/api/logs/operations*` endpoints
- New `/logs` page route

**Step 3: Clean up test files**

Remove `tests/test_atomic_writes.py` if it only tests operation_logger (check first).

**Step 4: Commit**

```bash
git add -A
git commit -m "docs: update references for logging overhaul"
```

---

## Task 12: Final integration test

**Step 1: Start the application**

```bash
python3 app.py
```

**Step 2: Manual verification checklist**

- [ ] App starts without errors
- [ ] `logs/app.log` file is created with syslog-style lines
- [ ] Navigate to `/logs` — page loads with Audit Log tab active
- [ ] Application Log tab switches and shows app log entries
- [ ] Make a change via Explorer → Apply → verify audit.log gets key=value lines
- [ ] Verify transaction grouping in audit tab (same txn ID shares visual container)
- [ ] Filter chips work for both tabs
- [ ] Search filters table rows
- [ ] Download button downloads the raw .log file
- [ ] Clear button truncates the log (with confirmation)
- [ ] Load More button fetches next page
- [ ] Settings page shows logging config without download button
- [ ] Navigation sidebar shows "Logs" link, highlights when active
- [ ] Old `/audit-log` URL returns 404 or redirects

**Step 3: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All PASS.

**Step 4: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: integration test fixes for logging overhaul"
```
