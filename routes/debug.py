"""Debug Routes - Development-only debugging endpoints.

These endpoints are only active when Flask is running in debug mode.
"""

import json
import logging
import os
from logging.handlers import RotatingFileHandler

from flask import Blueprint, current_app, jsonify, request

debug_bp = Blueprint("debug", __name__)
logger = logging.getLogger("nagios_bulk_editor.debug")

# Maximum character length for JSON values in console log output
_MAX_JSON_LENGTH = 500

# Configure dedicated file handler for frontend logs
_handler_configured = False


def _ensure_log_handler():
    """Set up file handler for frontend console logs (once)."""
    global _handler_configured
    if _handler_configured:
        return
    _handler_configured = True

    # Create logs directory if needed
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)

    # Set up rotating file handler
    log_path = os.path.join(log_dir, "frontend.log")
    handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )

    # Human-readable format for dev debugging
    formatter = logging.Formatter(
        "%(asctime)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    # Prevent propagation to root logger (avoid duplicate stderr output)
    logger.propagate = False


def _format_message_part(msg):
    """Format a single console message part to string."""
    if isinstance(msg, str):
        return msg
    if msg is None:
        return "null"
    if isinstance(msg, bool):
        return "true" if msg else "false"
    if isinstance(msg, (int, float)):
        return str(msg)
    if isinstance(msg, (dict, list)):
        return _format_json_value(msg)
    return str(msg)


def _format_json_value(value):
    """Format a dict or list as truncated JSON string."""
    try:
        s = json.dumps(value, default=str)
        if len(s) > _MAX_JSON_LENGTH:
            s = s[:_MAX_JSON_LENGTH] + "..."
        return s
    except (ValueError, TypeError):
        return "[Object]" if isinstance(value, dict) else "[Array]"


_LOG_LEVEL_MAP = {
    "error": logging.ERROR,
    "warn": logging.WARNING,
    "warning": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG,
    "log": logging.INFO,
}


def _extract_page_path(url):
    """Extract just the path portion from a URL."""
    page = url.split("?")[0].split("#")[0] if url else "unknown"
    if "://" in page:
        page = "/" + "/".join(page.split("/")[3:])
    return page


@debug_bp.before_request
def check_debug_mode():
    """Block all debug endpoints unless Flask is in debug mode."""
    if not current_app.debug:
        return jsonify({"error": "Debug endpoints disabled in production"}), 403
    # Initialize log handler on first request
    _ensure_log_handler()
    return None


@debug_bp.route("/api/debug/console", methods=["POST"])
def receive_console_log():
    """Receive frontend console messages and log them server-side.

    Expected JSON payload:
    {
        "level": "log" | "warn" | "error" | "info" | "debug",
        "messages": [...],  // Array of message parts
        "timestamp": "ISO timestamp",
        "url": "page URL",
        "userAgent": "browser info"  // optional
    }
    """
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"ok": False, "error": "No JSON data"}), 400

        level = data.get("level", "log")
        messages = data.get("messages", [])
        url = data.get("url", "")

        message_str = " ".join(_format_message_part(msg) for msg in messages)
        page = _extract_page_path(url)
        log_prefix = f"[FRONTEND:{level.upper()}] ({page})"
        log_level = _LOG_LEVEL_MAP.get(level.lower(), logging.INFO)

        logger.log(log_level, "%s %s", log_prefix, message_str)

        return jsonify({"ok": True})

    except Exception as e:
        # Don't let errors here cause issues - just log and return ok
        logger.exception("Error processing frontend console log")
        return jsonify({"ok": False, "error": str(e)}), 500
