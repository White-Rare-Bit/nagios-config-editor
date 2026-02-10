"""Audit Log Service

Manages audit log persistence, rotation, and retrieval.
"""

import contextlib
import json
import multiprocessing
import os
import tempfile
from datetime import datetime

# C-09: Module-level lock for process-safe audit log writes
# Uses multiprocessing.Lock because WSGI servers may use multiple processes
_audit_lock = multiprocessing.Lock()


AUDIT_LOG_MAX_ENTRIES = 1000  # Rotate after this many entries

# Default audit log directory - set once at module load to project root
# This ensures consistent paths regardless of which module calls first
_DEFAULT_AUDIT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")


def get_audit_log_dir(config_dir: str = None):
    """Get the path to the audit log directory, creating it if needed.

    Args:
        config_dir: Configuration directory path. If None, uses the project root
            (directory containing audit_service.py) to ensure consistent paths.

    Returns:
        Path to audit log directory (config_dir/logs/ or project_root/logs/).

    """
    if config_dir is None:
        log_dir = _DEFAULT_AUDIT_DIR
    else:
        log_dir = os.path.join(config_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


def get_audit_log_path(config_dir: str = None):
    """Get the path to the current audit log file.

    Args:
        config_dir: Configuration directory path. If None, uses the project root
            (directory containing audit_service.py) to ensure consistent paths.

    Returns:
        Path to audit log file.

    """
    return os.path.join(get_audit_log_dir(config_dir), "audit_log.json")


def rotate_audit_log(entries: list) -> list:
    """Rotate audit log to archive file, returning empty list for new log.

    Archives are named: audit_log_YYYYMMDD_HHMMSS.json

    Args:
        entries: List of audit log entries.

    Returns:
        Empty list if rotated, original list if not.

    """
    if len(entries) < AUDIT_LOG_MAX_ENTRIES:
        return entries

    log_dir = get_audit_log_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = os.path.join(log_dir, f"audit_log_{timestamp}.json")

    # Atomic write: temp file → flush → fsync → rename
    fd, tmp_path = tempfile.mkstemp(dir=log_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"entries": entries, "archived_at": datetime.now().isoformat()}, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, archive_path)
    except:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise

    # Return empty list to start fresh
    return []


def write_audit_log(audit_entry: dict, config_dir: str = None):
    """Write an audit log entry to the audit log file.

    C-09: Uses threading lock to prevent concurrent write race condition.
    The read-modify-write pattern requires atomicity to avoid lost updates.

    Args:
        audit_entry: Audit entry dictionary to log.
        config_dir: Configuration directory path. If None, uses current directory.

    """
    audit_path = get_audit_log_path(config_dir)

    # C-09: Acquire lock for thread-safe read-modify-write
    with _audit_lock:
        # Load existing entries
        entries = []
        if os.path.exists(audit_path):
            try:
                with open(audit_path, encoding="utf-8") as f:
                    data = json.load(f)
                    entries = data.get("entries", [])
            except (OSError, json.JSONDecodeError):
                entries = []

        # Append new entry
        entries.append(audit_entry)

        # Rotate if needed
        entries = rotate_audit_log(entries)

        # Atomic save: temp file → flush → fsync → rename
        audit_dir = os.path.dirname(audit_path)
        fd, tmp_path = tempfile.mkstemp(dir=audit_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"entries": entries}, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, audit_path)
        except:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise
