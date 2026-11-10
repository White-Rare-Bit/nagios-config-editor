"""Log handlers that are safe to share between worker processes.

Gunicorn runs several workers, each with its own handler writing the same
app.log/audit.log. The stdlib RotatingFileHandler decides to rotate on its own,
so two workers rotate over each other (lines are lost, renames fail with
FileNotFoundError) and a worker that didn't rotate keeps writing into the file
that is now app.log.1, which the log viewer never shows.

This module imports nothing from the `app` package, so it can be loaded and
tested on its own (the handler tests run it in separate processes).
"""

import contextlib
import logging
import os
from logging.handlers import RotatingFileHandler

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX platforms
    fcntl = None


class MultiProcessRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler that coordinates rotation across processes.

    Every write takes an exclusive flock on "<logfile>.lock", so only one
    process at a time checks the size, rotates and writes. Before writing, the
    handler checks whether the file it has open is still the live log file and
    reopens it if another process rotated it away.
    """

    def __init__(self, filename, *args, **kwargs):
        super().__init__(filename, *args, **kwargs)
        self._lock_path = self.baseFilename + ".lock"
        self._lock_fd = None
        self._lock_pid = None

    @contextlib.contextmanager
    def _interprocess_lock(self):
        if fcntl is None:
            yield
            return
        # flock locks belong to the open file description, which a forked child
        # shares with its parent. Reopen per process so they exclude each other.
        if self._lock_fd is None or self._lock_pid != os.getpid():
            self._lock_fd = os.open(self._lock_path, os.O_RDWR | os.O_CREAT, 0o644)
            self._lock_pid = os.getpid()
        fcntl.flock(self._lock_fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)

    def _reopen_if_rotated(self):
        """Drop the open stream if it no longer is the file at baseFilename."""
        if self.stream is None:
            return
        try:
            live = os.stat(self.baseFilename)
        except FileNotFoundError:
            live = None
        mine = os.fstat(self.stream.fileno())
        if live is None or (live.st_dev, live.st_ino) != (mine.st_dev, mine.st_ino):
            self.stream.close()
            self.stream = None  # pyright: ignore[reportAttributeAccessIssue] - reopened by shouldRollover / FileHandler.emit

    def emit(self, record):
        try:
            with self._interprocess_lock():
                self._reopen_if_rotated()
                if self.stream is not None:
                    # Other processes appended since our last write; measure the
                    # real size, not just what this process wrote.
                    self.stream.seek(0, os.SEEK_END)
                if self.shouldRollover(record):
                    self.doRollover()
                logging.FileHandler.emit(self, record)
        except Exception:
            self.handleError(record)

    def close(self):
        super().close()
        if self._lock_fd is not None and self._lock_pid == os.getpid():
            with contextlib.suppress(OSError):
                os.close(self._lock_fd)
        self._lock_fd = None


class IsoTimestampFormatter(logging.Formatter):
    """Formatter whose %(asctime)s is ISO 8601 local time with UTC offset.

    e.g. 2026-11-04T12:43:45.123+00:00. Carries the year and timezone, so audit
    entries stay unambiguous across years and hosts, and sorts as text.
    """

    def formatTime(self, record, datefmt=None):  # noqa: N802 - stdlib name
        from datetime import datetime

        return datetime.fromtimestamp(record.created).astimezone().isoformat(timespec="milliseconds")
