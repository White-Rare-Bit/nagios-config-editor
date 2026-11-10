"""Log viewer API routes — serves parsed log data for the unified log page."""

import logging
import os
import re

from flask import Blueprint, Response, current_app, jsonify, request

from ..audit_service import log_audit
from .helpers import format_audit_user, get_audit_user_identity

bp = Blueprint("logs", __name__)
logger = logging.getLogger(__name__)

# Regex for parsing key=value pairs (handles quoted and unquoted values)
_KV_PATTERN = re.compile(r'(\w+)=(?:"((?:[^"\\]|\\.)*)"|(\S*))')
_UNESCAPE_PATTERN = re.compile(r"\\(.)")
_UNESCAPES = {"\\": "\\", '"': '"', "n": "\n", "r": "\r"}

# Line timestamps: ISO 8601 with UTC offset (written since the logging fixes,
# e.g. 2026-11-04T12:43:45.123+00:00), or the older syslog style without a year
# (e.g. "Nov 04 12:43:45") so existing log files still display.
_TIMESTAMP = (
    r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z)"
    r"|\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})"
)

# Regex for parsing syslog-style app log lines
_APP_PATTERN = re.compile(
    _TIMESTAMP + r'\s+nagios-editor\s+\[(\w+)\]\s+([\w.]+):\s+(.*)'
)

# Timestamp prefix pattern for audit lines
_AUDIT_TS_PATTERN = re.compile(_TIMESTAMP + r'\s+AUDIT\s+(.*)')

# The viewer returns the newest entries first and stops after this many
# (the frontend asks for 10000); MAX_LIMIT caps what a client may ask for.
DEFAULT_LIMIT = 10000
MAX_LIMIT = 50000
_READ_BLOCK = 64 * 1024


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
        if m.group(2) is not None:
            # Quoted: undo audit_service's escapes. Unknown sequences are kept
            # as-is so lines written before backslashes were escaped still read.
            value = _UNESCAPE_PATTERN.sub(lambda e: _UNESCAPES.get(e.group(1), e.group(0)), m.group(2))
        else:
            value = m.group(3)
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


def _reverse_lines(path):
    """Yield the lines of a file last-first, reading it backwards in blocks.

    Avoids loading a whole (up to max_file_size_mb) log file into memory.
    """
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        pos = f.tell()
        tail = b""
        while pos > 0:
            step = min(_READ_BLOCK, pos)
            pos -= step
            f.seek(pos)
            block = f.read(step) + tail
            lines = block.split(b"\n")
            tail = lines.pop(0)  # may be cut off; completed by the next block
            for raw in reversed(lines):
                if raw:
                    yield raw.decode("utf-8", errors="replace")
        if tail:
            yield tail.decode("utf-8", errors="replace")


def _log_files_newest_first(log_path):
    """The live log file, then its rotated copies .1, .2, ... while they exist."""
    if os.path.exists(log_path):
        yield log_path
    n = 1
    while os.path.exists(f"{log_path}.{n}"):
        yield f"{log_path}.{n}"
        n += 1


def _read_log_entries(log_path, parser_fn, limit):
    """Parse entries newest first across the live and rotated log files.

    Returns (entries, truncated): at most `limit` entries, and whether older
    entries were left out.
    """
    entries = []
    for path in _log_files_newest_first(log_path):
        try:
            for line in _reverse_lines(path):
                entry = parser_fn(line)
                if entry is None:
                    continue
                if len(entries) >= limit:
                    return entries, True
                entries.append(entry)
        except OSError as e:
            logger.warning("Could not read log file %s: %s", path, e)
    return entries, False


def _entries_response(filename, parser_fn):
    limit = request.args.get("limit", DEFAULT_LIMIT, type=int)
    limit = max(1, min(limit, MAX_LIMIT))
    log_path = os.path.join(_get_log_dir(), filename)
    entries, truncated = _read_log_entries(log_path, parser_fn, limit)
    return jsonify({
        "success": True,
        "data": {
            "entries": entries,
            "total": len(entries),
            "truncated": truncated,
        },
    })


@bp.route("/api/logs/audit", methods=["GET"])
def api_get_audit_logs():
    """Get parsed audit log entries, newest first (frontend handles pagination)."""
    return _entries_response("audit.log", parse_audit_line)


def _download_response(filename):
    """The live log and its rotated copies as one text file, oldest line first."""
    log_path = os.path.join(_get_log_dir(), filename)
    paths = list(_log_files_newest_first(log_path))[::-1]
    if not paths:
        return jsonify({"error": "Log file not found"}), 404

    def generate():
        for path in paths:
            try:
                with open(path, "rb") as f:
                    while chunk := f.read(_READ_BLOCK):
                        yield chunk
            except OSError as e:
                logger.warning("Could not read log file %s for download: %s", path, e)

    return Response(generate(), mimetype="text/plain", headers={
        "Content-Disposition": f"attachment; filename={filename}",
    })


@bp.route("/api/logs/audit/download", methods=["GET"])
def api_download_audit_log():
    """Download the audit log, including rotated files."""
    return _download_response("audit.log")


# There is deliberately no endpoint to clear the audit log: it is the record of
# who changed what, so it must not be erasable from the app it audits. Its size
# is bounded by rotation (max_file_size_mb x max_backup_files).


@bp.route("/api/logs/app", methods=["GET"])
def api_get_app_logs():
    """Get parsed application log entries, newest first (frontend handles pagination)."""
    return _entries_response("app.log", parse_app_line)


@bp.route("/api/logs/app/download", methods=["GET"])
def api_download_app_log():
    """Download the application log, including rotated files."""
    return _download_response("app.log")


@bp.route("/api/logs/app/clear", methods=["POST"])
def api_clear_app_log():
    """Truncate the live application log file. Recorded in the audit log."""
    log_path = os.path.join(_get_log_dir(), "app.log")
    try:
        with open(log_path, "w") as f:
            f.truncate(0)
    except OSError as e:
        logger.error("Failed to clear app log %s: %s", log_path, e)
        return jsonify({"error": str(e)}), 500
    log_audit(action="log_clear", user=format_audit_user(get_audit_user_identity()), log="app")
    return jsonify({"success": True})
