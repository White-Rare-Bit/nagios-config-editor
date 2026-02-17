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
