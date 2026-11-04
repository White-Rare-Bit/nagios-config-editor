"""Audit logging service — writes key=value lines to audit.log via stdlib logging.

Each audit event is a single log line in the format:
    AUDIT txn=<id> user="<email>" action=<type> key1=value1 key2="value with spaces"

Transaction IDs (txn) group related changes from a single Apply operation.
"""

import logging
import uuid


audit_logger = logging.getLogger("audit")

# Characters that force a value into quotes. Backslash, quote, CR and LF are
# also escaped inside the quotes, so a value can never end the line early (a
# newline would otherwise let a field value forge a second audit entry).
_NEEDS_QUOTES = (" ", '"', "\\", "\n", "\r", "=")
_ESCAPES = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r"}


def _escape(v_str: str) -> str:
    return "".join(_ESCAPES.get(c, c) for c in v_str)


def _format_value(value) -> str:
    """Render one value: bare if safe, otherwise quoted with escapes."""
    v_str = str(value) if value is not None else ""
    if v_str and not any(c in v_str for c in _NEEDS_QUOTES):
        return v_str
    return f'"{_escape(v_str)}"'


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

    parts = [f'AUDIT txn={txn} user="{_escape(user or "")}" action={action}']

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
        parts.append(f"{k}={_format_value(v)}")

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
