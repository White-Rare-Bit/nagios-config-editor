"""A lock that excludes other worker processes, not just other threads.

WSGI servers run several worker processes. Each worker imports the app on its
own, so a ``multiprocessing.Lock`` or ``threading.Lock`` created at startup is
a different lock in every worker and guards nothing between them. The only
thing all workers share is the filesystem, so the lock lives there: an
advisory ``flock`` on a lock file.

Within one process the lock also serialises threads (a plain ``threading.Lock``
taken first), so it is a drop-in replacement for the locks it replaces.
"""

import os
import threading
import time

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX platforms
    fcntl = None

_POLL_SECONDS = 0.02


class ProcessLock:
    """Mutual exclusion across threads and processes.

    Args:
        path: Lock file path. Its directory is created on first use. With no
            path (or on a platform without ``flock``) the lock only excludes
            threads of the current process — enough for a service that is not
            shared between workers, such as one built directly in a unit test.

    Not reentrant: acquiring it twice from the same thread deadlocks, exactly
    like the locks it replaces.
    """

    def __init__(self, path: str | None = None):
        self._path = path if fcntl is not None else None
        self._thread_lock = threading.Lock()
        self._fd: int | None = None

    def acquire(self, timeout: float | None = None) -> bool:
        """Take the lock. Returns False if ``timeout`` seconds pass first."""
        deadline = None if timeout is None else time.monotonic() + timeout
        if not self._thread_lock.acquire(timeout=-1 if timeout is None else timeout):
            return False
        if self._path is None:
            return True
        assert fcntl is not None  # _path is only set when flock is available
        try:
            os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
            fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o644)
        except OSError:
            self._thread_lock.release()
            raise
        try:
            if deadline is None:
                fcntl.flock(fd, fcntl.LOCK_EX)
            else:
                while True:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            os.close(fd)
                            self._thread_lock.release()
                            return False
                        time.sleep(_POLL_SECONDS)
        except BaseException:
            os.close(fd)
            self._thread_lock.release()
            raise
        self._fd = fd
        return True

    def release(self) -> None:
        fd, self._fd = self._fd, None
        try:
            if fd is not None:
                # Closing the descriptor drops the flock.
                os.close(fd)
        finally:
            self._thread_lock.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc_info):
        self.release()
        return False
