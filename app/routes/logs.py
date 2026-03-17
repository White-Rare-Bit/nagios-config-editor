"""Log viewer API routes — serves parsed log data for the unified log page."""

import logging
import os
import re

from flask import Blueprint, current_app, jsonify, send_file

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


def _read_log_entries(log_path, parser_fn):
    """Read and parse all log entries from a .log file.

    Returns entries in reverse order (newest first) and the total parsed count.
    """
    if not os.path.exists(log_path):
        return [], 0

    try:
        with open(log_path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return [], 0

    entries = []
    for line in reversed(lines):
        entry = parser_fn(line)
        if entry is not None:
            entries.append(entry)

    return entries, len(entries)


@bp.route("/api/logs/audit", methods=["GET"])
def api_get_audit_logs():
    """Get all parsed audit log entries (frontend handles pagination)."""
    log_path = os.path.join(_get_log_dir(), "audit.log")
    entries, total = _read_log_entries(log_path, parse_audit_line)

    return jsonify({
        "success": True,
        "data": {
            "entries": entries,
            "total": total,
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
    """Get all parsed application log entries (frontend handles pagination)."""
    log_path = os.path.join(_get_log_dir(), "app.log")
    entries, total = _read_log_entries(log_path, parse_app_line)

    return jsonify({
        "success": True,
        "data": {
            "entries": entries,
            "total": total,
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


