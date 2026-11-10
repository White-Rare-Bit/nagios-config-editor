"""Install and live-update the app.log / audit.log handlers.

create_app() calls setup_logging(). Saved logging settings (level, rotation
size and count) are applied without a restart by apply_runtime_settings():
directly in the worker that handled the save, and in every other gunicorn
worker when its before_request settings sync (app/__init__.py) notices that
config/settings.json changed. Loggers are process-global, so there is one set
of handlers per process no matter how many apps create_app() has built.
"""

import logging
import os

from .log_handlers import IsoTimestampFormatter, MultiProcessRotatingFileHandler

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")

APP_FORMAT = "%(asctime)s nagios-editor [%(levelname)s] %(name)s: %(message)s"
AUDIT_FORMAT = "%(asctime)s %(message)s"

# Marks the handlers setup_logging installs, so a second create_app() call
# replaces them instead of stacking another set (which writes every line twice).
_HANDLER_TAG = "_nbe_handler"

def _installed_handlers(lgr) -> list[MultiProcessRotatingFileHandler]:
    return [h for h in lgr.handlers
            if isinstance(h, MultiProcessRotatingFileHandler) and getattr(h, _HANDLER_TAG, False)]


def _file_handler(path, fmt):
    handler = MultiProcessRotatingFileHandler(path)
    handler.setFormatter(IsoTimestampFormatter(fmt=fmt))
    setattr(handler, _HANDLER_TAG, True)
    return handler


def apply_runtime_settings(log_cfg):
    """Apply level and rotation settings to the installed handlers in this process."""
    level = getattr(logging, (log_cfg.log_level or "INFO").upper(), logging.INFO)
    max_bytes = int((log_cfg.max_file_size_mb or 10) * 1024 * 1024)
    backup_count = log_cfg.max_backup_files or 5

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    for handler in _installed_handlers(root_logger):
        handler.setLevel(level)
    for lgr in (root_logger, logging.getLogger("audit")):
        for handler in _installed_handlers(lgr):
            handler.maxBytes = max_bytes
            handler.backupCount = backup_count


def setup_logging(log_cfg, log_dir):
    """Configure stdlib logging with file handlers for app and audit logs.

    Safe to call repeatedly: handlers from an earlier call are replaced.
    """
    os.makedirs(log_dir, exist_ok=True)

    root_logger = logging.getLogger()
    audit_logger = logging.getLogger("audit")
    for lgr in (root_logger, audit_logger):
        for handler in _installed_handlers(lgr):
            lgr.removeHandler(handler)
            handler.close()

    # App log — syslog-style layout with an ISO 8601 timestamp
    root_logger.addHandler(_file_handler(os.path.join(log_dir, "app.log"), APP_FORMAT))

    # Audit log — minimal format (timestamp + raw message)
    audit_handler = _file_handler(os.path.join(log_dir, "audit.log"), AUDIT_FORMAT)
    audit_handler.setLevel(logging.INFO)
    audit_logger.setLevel(logging.INFO)  # independent of log_level: never drop audit lines
    audit_logger.addHandler(audit_handler)
    audit_logger.propagate = False  # Don't duplicate audit lines into app.log

    # Suppress werkzeug request logs from app.log (floods with GET /api/... lines)
    logging.getLogger("werkzeug").propagate = False

    apply_runtime_settings(log_cfg)


def log_error_responses(response):
    """after_request hook: record every 5xx response in app.log.

    Many routes turn a failed OperationResult or a caught exception into a
    500 JSON body without logging it, so the error reached the browser but
    left no trace for operators. Unhandled exceptions are additionally logged
    with their traceback by Flask itself.
    """
    if response.status_code < 500:
        return response
    from flask import request

    detail = ""
    if response.is_json:
        body = response.get_json(silent=True)
        if isinstance(body, dict):
            detail = str(body.get("error") or body.get("message") or "")
    logging.getLogger("app.http").error(
        "%s %s -> %d%s", request.method, request.path, response.status_code,
        f": {detail}" if detail else "",
    )
    return response
