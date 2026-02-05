"""
Debug Routes - Development-only debugging endpoints.

These endpoints are only active when Flask is running in debug mode.
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from flask import Blueprint, request, jsonify, current_app

debug_bp = Blueprint('debug', __name__)
logger = logging.getLogger('nagios_bulk_editor.debug')

# Configure dedicated file handler for frontend logs
_handler_configured = False


def _ensure_log_handler():
    """Set up file handler for frontend console logs (once)."""
    global _handler_configured
    if _handler_configured:
        return
    _handler_configured = True

    # Create logs directory if needed
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)

    # Set up rotating file handler
    log_path = os.path.join(log_dir, 'frontend.log')
    handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding='utf-8'
    )

    # Human-readable format for dev debugging
    formatter = logging.Formatter(
        '%(asctime)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    # Prevent propagation to root logger (avoid duplicate stderr output)
    logger.propagate = False


@debug_bp.before_request
def check_debug_mode():
    """Block all debug endpoints unless Flask is in debug mode."""
    if not current_app.debug:
        return jsonify({'error': 'Debug endpoints disabled in production'}), 403
    # Initialize log handler on first request
    _ensure_log_handler()


@debug_bp.route('/api/debug/console', methods=['POST'])
def receive_console_log():
    """
    Receive frontend console messages and log them server-side.

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
            return jsonify({'ok': False, 'error': 'No JSON data'}), 400

        level = data.get('level', 'log')
        messages = data.get('messages', [])
        timestamp = data.get('timestamp', '')
        url = data.get('url', '')

        # Format the message parts into a single string
        formatted_parts = []
        for msg in messages:
            if isinstance(msg, str):
                formatted_parts.append(msg)
            elif msg is None:
                formatted_parts.append('null')
            elif isinstance(msg, bool):
                formatted_parts.append('true' if msg else 'false')
            elif isinstance(msg, (int, float)):
                formatted_parts.append(str(msg))
            elif isinstance(msg, dict):
                # Truncate large objects
                import json
                try:
                    s = json.dumps(msg, default=str)
                    if len(s) > 500:
                        s = s[:500] + '...'
                    formatted_parts.append(s)
                except Exception:
                    formatted_parts.append('[Object]')
            elif isinstance(msg, list):
                import json
                try:
                    s = json.dumps(msg, default=str)
                    if len(s) > 500:
                        s = s[:500] + '...'
                    formatted_parts.append(s)
                except Exception:
                    formatted_parts.append('[Array]')
            else:
                formatted_parts.append(str(msg))

        message_str = ' '.join(formatted_parts)

        # Extract just the path from URL for cleaner logs
        page = url.split('?')[0].split('#')[0] if url else 'unknown'
        if '://' in page:
            page = '/' + '/'.join(page.split('/')[3:])

        # Format: [FRONTEND:level] (page) message
        log_prefix = f'[FRONTEND:{level.upper()}] ({page})'

        # Map frontend level to Python logging level
        log_level_map = {
            'error': logging.ERROR,
            'warn': logging.WARNING,
            'warning': logging.WARNING,
            'info': logging.INFO,
            'debug': logging.DEBUG,
            'log': logging.INFO,
        }
        log_level = log_level_map.get(level.lower(), logging.INFO)

        # Log to server
        logger.log(log_level, f'{log_prefix} {message_str}')

        return jsonify({'ok': True})

    except Exception as e:
        # Don't let errors here cause issues - just log and return ok
        logger.exception('Error processing frontend console log')
        return jsonify({'ok': False, 'error': str(e)}), 500
