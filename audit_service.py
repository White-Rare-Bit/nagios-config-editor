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


# Backwards-compat shims — removed in Task 4 when callers are updated
def write_audit_log(audit_entry, config_dir=None):
    """Legacy shim: converts old dict-based audit calls to new log_audit()."""
    action = audit_entry.get("action", "unknown")
    user = audit_entry.get("userEmail", audit_entry.get("userName", ""))
    # Pass remaining keys as kwargs, excluding internal fields
    skip = {"action", "userEmail", "userName", "timestamp"}
    kwargs = {k: v for k, v in audit_entry.items() if k not in skip and v is not None}
    log_audit(action=action, user=user, **kwargs)


def get_audit_log_dir(config_dir=None):
    """Legacy shim — returns log directory path."""
    import os
    default = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    if config_dir is None:
        return default
    return os.path.join(config_dir, "logs")


def get_audit_log_path(config_dir=None):
    """Legacy shim — returns audit log file path."""
    import os
    return os.path.join(get_audit_log_dir(config_dir), "audit_log.json")


def rotate_audit_log(entries):
    """Legacy shim — no-op, rotation handled by RotatingFileHandler."""
    return entries
