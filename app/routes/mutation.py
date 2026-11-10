"""The one way a request may change configuration.

Every mutating route needs the same things in the same order: exclude other
workers, check who owns the staging lock, open the shadow copy if needed,
translate client paths, take an undo snapshot, change files, tell every
worker to reparse, write the audit log. Doing that by hand in each route is
how individual routes came to skip a step. Routes now do it through:

- ``staged_mutation()`` for changes to the shadow copy (edits, creates,
  moves, deletes). Creates the shadow on first use.
- ``staging_owner()`` for operations on an existing staging session or on
  the live config (apply, discard, undo, restore, git). Never creates one.

Both raise ``ApiError``, which the app turns into the standard error body.
"""

import logging
import os
from contextlib import contextmanager

from flask import current_app, request

from ..audit_service import log_audit
from ..file_operations import is_safe_path
from .helpers import (
    audit_file_path,
    format_audit_user,
    get_audit_user_identity,
    get_service,
    get_shadow_manager,
)

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """An error to report to the client as {"success": false, "error": message}."""

    def __init__(self, message: str, status: int = 400, **extra):
        super().__init__(message)
        self.message = message
        self.status = status
        self.extra = extra


LOCKED_MESSAGE = "Staging is locked by another user"


def session_id() -> str | None:
    return request.headers.get("X-Session-Id")


def public_lock_status(sm=None) -> dict:
    """Lock status that is safe to send to any client.

    The owner's session id is what proves ownership, so it never leaves the
    server; each caller is only told whether it is the owner.
    """
    sm = sm or get_shadow_manager()
    status = sm.get_lock_status()
    if not status.get("locked"):
        return {"locked": False, "is_owner": False}
    return {
        "locked": True,
        "is_owner": bool(session_id()) and status.get("session_id") == session_id(),
        "user_name": status.get("user_name"),
        "user_email": status.get("user_email"),
        "created_at": status.get("created_at"),
    }


def _locked_error(sm) -> ApiError:
    return ApiError(LOCKED_MESSAGE, 423, locked=True, lockOwner=public_lock_status(sm))


class Mutation:
    """What a route can do inside ``staged_mutation()``.

    Paths given to and returned from these methods are logical paths (the
    original config locations) unless a method says otherwise.
    """

    def __init__(self, sm, service):
        self.sm = sm
        self.service = service
        self.touched = False
        self._user = None

    # -- identity ----------------------------------------------------------

    @property
    def user(self) -> str:
        """The requesting user as 'Name <email>' for the audit log."""
        if self._user is None:
            self._user = format_audit_user(get_audit_user_identity())
        return self._user

    # -- paths -------------------------------------------------------------

    def resolve(self, client_path: str) -> str:
        """Turn a path from the client into an absolute logical path.

        Absolute paths are taken as they are. Relative ones are relative to
        the primary config root. A URL path segment cannot start with "/",
        so an absolute path that arrives without it is recognised by being
        inside a config root once the slash is restored.
        """
        if "\x00" in client_path:
            raise ApiError("Path contains null bytes", 400)
        if os.path.isabs(client_path):
            return os.path.normpath(client_path)
        as_absolute = os.path.normpath(os.sep + client_path)
        if self.sm.composite_path(as_absolute) is not None:
            return self.sm.logical_path(as_absolute)
        return os.path.normpath(os.path.join(self.service.config_path, client_path))

    def physical(self, path: str) -> str:
        """Where a logical path lives in the shadow copy.

        Raises ApiError(400) for anything outside the config roots: there is
        no shadow location for such a path, and it must never be written.
        """
        physical = self.sm.physical_path(path)
        if physical is None:
            raise ApiError("Path must be within a configuration directory", 400)
        # Defence in depth: null bytes, traversal and symlinks out of the shadow.
        safe = is_safe_path(physical, self.sm.shadow_config_dir)
        if not safe.success:
            raise ApiError(safe.error or "Unsafe path", 400)
        return physical

    def logical(self, path: str) -> str:
        """Normalise a client path that may be logical or (legacy) physical."""
        if self.sm.composite_path(path) is None:
            raise ApiError("Path must be within a configuration directory", 400)
        return self.sm.logical_path(path)

    def display(self, path: str) -> str:
        """Short path for audit log lines."""
        return audit_file_path(path)

    # -- objects -----------------------------------------------------------

    def find(self, stable_key: str):
        """Return the object for a stable key, or None."""
        found = self.service.find_object_by_stable_key(stable_key)
        return found[1] if found else None

    def require(self, stable_key: str):
        """Return the object for a stable key or raise ApiError(404)."""
        obj = self.find(stable_key)
        if obj is None:
            raise ApiError(f"Object not found: {stable_key}", 404)
        return obj

    # -- undo, reload, audit -----------------------------------------------

    def snapshot(self, files, description: str, *, moved_keys=None, dirs=()) -> None:
        """Save the given files (and note the given dirs) so undo can restore them.

        Must be called before the files are changed.
        """
        self.sm.snapshot_files(
            sorted({self._composite(p) for p in files}),
            description,
            moved_keys=list(moved_keys) if moved_keys else None,
            dir_paths=[self._composite(p) for p in dirs] or None,
        )
        self.touched = True

    def _composite(self, path: str) -> str:
        composite = self.sm.composite_path(path)
        if composite is None:
            raise ApiError("Path must be within a configuration directory", 400)
        return composite

    def rollback(self) -> None:
        """Undo everything this request changed, as if it had not happened.

        Restores the snapshot taken by ``snapshot()`` (undo consumes it, so
        undo history is as it was before the request) and reparses. Clears
        ``touched`` so a shadow this request created is removed again.
        Call it only when this request took exactly one snapshot.
        """
        result = self.sm.undo()
        if not result.success:
            # The shadow may be half-written: keep ``touched`` set so it is
            # not destroyed under the user, and say so.
            logger.error("Rollback failed: %s", result.error)
            raise ApiError(
                f"Batch failed and could not be rolled back: {result.error}. "
                "Use Undo or Discard to recover.",
                500,
            )
        self.service.reload()
        self.touched = False

    def files_changed(self) -> None:
        """Call after changing shadow files directly (not through the service)."""
        self.touched = True
        self.service.reload()

    def audit(self, action: str, **fields) -> None:
        log_audit(action=action, user=self.user, **fields)


def _mutation_lock():
    return current_app.extensions["mutation_lock"]


@contextmanager
def staged_mutation():
    """Run a change against the shadow copy, creating it on first use.

    Holds the cross-worker mutation lock for the whole block, so two requests
    cannot interleave their find/snapshot/write steps. Yields a Mutation.

    If this request created the shadow and then changed nothing (it failed
    validation, or had nothing to do), the shadow is removed again so a
    refused request does not leave its sender holding the lock.
    """
    sid = session_id()
    if not sid:
        raise ApiError("X-Session-Id header required", 400)

    sm = get_shadow_manager()
    service = get_service()

    with _mutation_lock():
        created = False
        if not sm.has_shadow():
            identity = get_audit_user_identity()
            result = sm.create_shadow(
                sid, identity.get("userName") or "", identity.get("userEmail") or "",
            )
            if not result.success:
                raise ApiError(result.error or "Failed to create shadow", 500)
            created = True
        elif not sm.is_owner(sid):
            raise _locked_error(sm)

        mutation = Mutation(sm, service)
        try:
            yield mutation
        finally:
            if created and not mutation.touched:
                sm.destroy_shadow()


@contextmanager
def staging_owner():
    """Run an operation that only the staging-lock owner may perform.

    Passes when no staging session exists (there is nobody to protect) or
    when the caller owns it; raises ApiError(423) otherwise. A request with
    no session id cannot prove ownership and is refused while a session
    exists. Holds the cross-worker mutation lock for the whole block.
    """
    sm = get_shadow_manager()
    with _mutation_lock():
        if sm.has_shadow() and not sm.is_owner(session_id()):
            raise _locked_error(sm)
        yield sm
