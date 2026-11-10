"""Audit logging service — writes key=value lines to audit.log via stdlib logging.

Each audit event is a single log line in the format:
    AUDIT txn=<id> user="<email>" action=<type> key1=value1 key2="value with spaces"

Transaction IDs (txn) group the lines written by one request (e.g. one field
line per attribute of a single object edit).

session=<ref> links lines to the staging session that made them: edits are
audited when staged, and the session's later apply, staging_discard, undo or
lock_break line (lock_break carries it as owner_session) says what became of
them. The ref is a hash of the X-Session-Id, never the id itself: anyone
holding the id can act as that session's lock owner.
"""

import hashlib
import logging
import uuid

from flask import has_request_context, request


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


def session_ref(session_id):
    """Short, non-reversible reference to a staging session id for audit lines."""
    if not session_id:
        return ""
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:8]


def log_audit(action, user=None, txn=None, **kwargs):
    """Write an audit log line.

    Args:
        action: The action type.
        user: User email address.
        txn: Transaction ID. Auto-generated if None.
        **kwargs: Additional key=value pairs for the log line. session= is
            filled from the request's X-Session-Id unless given.

    """
    if "session" not in kwargs and has_request_context():
        ref = session_ref(request.headers.get("X-Session-Id"))
        if ref:
            kwargs["session"] = ref
    line = format_audit_line(action, txn=txn, user=user, **kwargs)
    audit_logger.info(line)
