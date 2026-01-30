"""
Audit Log Service

Manages audit log persistence, rotation, and retrieval.
"""

import os
import json
import threading
from datetime import datetime

# C-09: Module-level lock for thread-safe audit log writes
_audit_lock = threading.Lock()


AUDIT_LOG_DIR = None
AUDIT_LOG_FILE = None
AUDIT_LOG_MAX_ENTRIES = 1000  # Rotate after this many entries


def get_audit_log_dir(config_dir: str = None):
    """Get the path to the audit log directory, creating it if needed.

    Args:
        config_dir: Configuration directory path. If None, uses current directory.

    Returns:
        Path to audit log directory.
    """
    global AUDIT_LOG_DIR
    if AUDIT_LOG_DIR is None:
        if config_dir is None:
            config_dir = os.path.dirname(os.path.abspath(__file__))
        AUDIT_LOG_DIR = os.path.join(config_dir, 'logs')
        os.makedirs(AUDIT_LOG_DIR, exist_ok=True)
    return AUDIT_LOG_DIR


def get_audit_log_path(config_dir: str = None):
    """Get the path to the current audit log file.

    Args:
        config_dir: Configuration directory path. If None, uses current directory.

    Returns:
        Path to audit log file.
    """
    global AUDIT_LOG_FILE
    if AUDIT_LOG_FILE is None:
        AUDIT_LOG_FILE = os.path.join(get_audit_log_dir(config_dir), 'audit_log.json')
    return AUDIT_LOG_FILE


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
    archive_path = os.path.join(log_dir, f'audit_log_{timestamp}.json')

    # Write all current entries to archive
    with open(archive_path, 'w', encoding='utf-8') as f:
        json.dump({'entries': entries, 'archived_at': datetime.now().isoformat()}, f, indent=2)

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
                with open(audit_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    entries = data.get('entries', [])
            except (IOError, json.JSONDecodeError):
                entries = []

        # Append new entry
        entries.append(audit_entry)

        # Rotate if needed
        entries = rotate_audit_log(entries)

        # Save
        with open(audit_path, 'w', encoding='utf-8') as f:
            json.dump({'entries': entries}, f, indent=2)
