"""Operation Logger - Enterprise-grade file-based logging for filesystem operations.

Uses Python's logging module with RotatingFileHandler, outputs structured JSON Lines format.
"""

import gzip
import json
import logging
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path


@dataclass
class LogConfig:
    """Configuration for the operation logger."""

    level: str = "INFO"
    log_dir: str = "logs"
    filename: str = "operations.jsonl"
    max_size_mb: int = 10
    max_backup_files: int = 5
    enabled: bool = True


class JsonLineFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
        }

        # Add extra fields from the record
        for key in ("session_id", "user_name", "user_email", "category",
                    "operation", "params", "result", "duration_ms", "error"):
            value = getattr(record, key, None)
            if value is not None:
                entry[key] = value

        return json.dumps(entry, default=str)


@dataclass
class OperationContext:
    """Context yielded by the operation() context manager."""

    _result: str | None = field(default=None, init=False)
    _error: str | None = field(default=None, init=False)

    def set_result(self, result: str) -> None:
        self._result = result

    def set_error(self, error: str) -> None:
        self._error = error


class OperationLogger:
    """Core logging class for operation tracking."""

    def __init__(self, config: LogConfig | None = None):
        self._config = config or LogConfig()
        self._logger = logging.getLogger("nagios_bulk_editor.operations")
        self._handler: RotatingFileHandler | None = None
        self._setup_handler()

    def _setup_handler(self) -> None:
        """Set up the rotating file handler."""
        # Remove existing handler if any
        if self._handler:
            self._logger.removeHandler(self._handler)
            self._handler.close()
            self._handler = None

        if not self._config.enabled:
            self._logger.setLevel(logging.CRITICAL + 1)
            return

        # Ensure log directory exists
        log_dir = Path(self._config.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

        log_path = log_dir / self._config.filename
        max_bytes = self._config.max_size_mb * 1024 * 1024

        self._handler = RotatingFileHandler(
            str(log_path),
            maxBytes=max_bytes,
            backupCount=self._config.max_backup_files,
            encoding="utf-8",
        )
        self._handler.namer = self._gz_namer
        self._handler.rotator = self._gz_rotator
        self._handler.setFormatter(JsonLineFormatter())

        self._logger.addHandler(self._handler)
        self._logger.setLevel(getattr(logging, self._config.level, logging.INFO))

    @staticmethod
    def _gz_namer(name: str) -> str:
        """Append .gz to rotated log filenames."""
        return name + ".gz"

    @staticmethod
    def _gz_rotator(source: str, dest: str) -> None:
        """Compress the rotated log file with gzip."""
        with open(source, "rb") as f_in, gzip.open(dest, "wb") as f_out:
            f_out.writelines(f_in)
        os.remove(source)

    def _log(self, level: int, category: str, operation: str, **kwargs) -> None:
        """Internal log method."""
        if not self._config.enabled:
            return

        extra = {
            "category": category,
            "operation": operation,
            "session_id": kwargs.get("session_id"),
            "user_name": kwargs.get("user_name"),
            "user_email": kwargs.get("user_email"),
            "params": kwargs.get("params"),
            "result": kwargs.get("result"),
            "duration_ms": kwargs.get("duration_ms"),
            "error": kwargs.get("error"),
        }

        self._logger.log(level, "", extra=extra)

    def debug(self, category: str, operation: str, **kwargs) -> None:
        """Log a DEBUG level operation."""
        self._log(logging.DEBUG, category, operation, **kwargs)

    def info(self, category: str, operation: str, **kwargs) -> None:
        """Log an INFO level operation."""
        self._log(logging.INFO, category, operation, **kwargs)

    def warning(self, category: str, operation: str, **kwargs) -> None:
        """Log a WARNING level operation."""
        self._log(logging.WARNING, category, operation, **kwargs)

    def error(self, category: str, operation: str, **kwargs) -> None:
        """Log an ERROR level operation."""
        self._log(logging.ERROR, category, operation, **kwargs)

    def exception(self, category: str, operation: str, **kwargs) -> None:
        """Log an ERROR level operation with traceback from current exception."""
        self._log(logging.ERROR, category, operation, **kwargs)

    @contextmanager
    def operation(self, category: str, operation: str, **kwargs):
        """Context manager that logs start, duration, and result/error of an operation."""
        ctx = OperationContext()
        start = time.perf_counter()

        self._log(logging.DEBUG, category, operation, result="started", **kwargs)

        try:
            yield ctx
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            result = ctx._result or "success"
            self._log(logging.INFO, category, operation,
                      result=result, duration_ms=duration_ms, **kwargs)
        except Exception as e:  # noqa: BLE001
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            error_msg = ctx._error or str(e)
            self._log(logging.ERROR, category, operation,
                      result="error", error=error_msg, duration_ms=duration_ms, **kwargs)
            raise

    def reconfigure(self, new_config: LogConfig) -> None:
        """Hot-reload settings without restart."""
        self._config = new_config
        self._setup_handler()

    def get_log_file_path(self) -> Path:
        """Get the path to the current log file."""
        return Path(self._config.log_dir) / self._config.filename

    def get_log_file_size(self) -> int:
        """Get the current log file size in bytes."""
        path = self.get_log_file_path()
        if path.exists():
            return path.stat().st_size
        return 0

    def get_rotated_files(self) -> list[Path]:
        """Get list of rotated log files (gzipped)."""
        base_path = self.get_log_file_path()
        rotated = []
        for i in range(1, self._config.max_backup_files + 1):
            gz_path = Path(f"{base_path}.{i}.gz")
            if gz_path.exists():
                rotated.append(gz_path)
            else:
                # Legacy uncompressed rotated files
                plain_path = Path(f"{base_path}.{i}")
                if plain_path.exists():
                    rotated.append(plain_path)
        return rotated

    @property
    def config(self) -> LogConfig:
        """Get current configuration."""
        return self._config
