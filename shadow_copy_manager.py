"""Shadow Copy Manager for Nagios Bulk Editor.

Replaces JSON-diff staging with a shadow copy architecture:
- Full directory copy on first edit
- Direct mutations on shadow copy
- File-level undo snapshots
- All-or-nothing apply back to original
"""

import json
import logging
import multiprocessing
import os
import shutil
import time

from nagios_model import OperationResult

logger = logging.getLogger(__name__)


class ShadowCopyManager:
    """Manages a shadow copy of the Nagios config directory.

    Shadow directory layout:
        <shadow_base>/config/     - Full copy of config directory
        <shadow_base>/lock.json   - Session lock info
        <shadow_base>/snapshots/  - Undo snapshots
    """

    def __init__(self, config_path: str, shadow_base_path: str):
        self.config_path = config_path
        self.shadow_base_path = shadow_base_path
        self._lock = multiprocessing.Lock()

    @property
    def _config_dir(self) -> str:
        """Path to the shadow config directory."""
        return os.path.join(self.shadow_base_path, "config")

    @property
    def _lock_file(self) -> str:
        """Path to the lock file."""
        return os.path.join(self.shadow_base_path, "lock.json")

    @property
    def _snapshots_dir(self) -> str:
        """Path to the snapshots directory."""
        return os.path.join(self.shadow_base_path, "snapshots")

    def has_shadow(self) -> bool:
        """Check if a shadow copy exists."""
        return os.path.isdir(self._config_dir)

    def create_shadow(self, session_id: str, user_name: str, user_email: str) -> OperationResult:
        """Create a shadow copy of the config directory.

        Copies all files from config_path to shadow_base/config/.
        Writes lock.json with session info.

        Args:
            session_id: Session ID of the lock owner
            user_name: Display name of the user
            user_email: Email of the user

        Returns:
            OperationResult with success/error

        """
        with self._lock:
            if self.has_shadow():
                return OperationResult(
                    success=False,
                    error="Shadow copy already exists. Another session owns the lock.",
                )

            try:
                # Copy entire config directory
                shutil.copytree(self.config_path, self._config_dir)

                # Write lock file
                lock_data = {
                    "session_id": session_id,
                    "user_name": user_name,
                    "user_email": user_email,
                    "created_at": time.time(),
                }
                os.makedirs(self.shadow_base_path, exist_ok=True)
                with open(self._lock_file, "w", encoding="utf-8") as f:
                    json.dump(lock_data, f)

                # Create snapshots directory
                os.makedirs(self._snapshots_dir, exist_ok=True)

                logger.info("Shadow copy created for session %s by %s", session_id, user_name)
                return OperationResult(success=True)

            except Exception as e:
                # Clean up on failure
                self._cleanup_shadow_dirs()
                logger.error("Failed to create shadow copy: %s", e)
                return OperationResult(success=False, error=str(e))

    def destroy_shadow(self) -> OperationResult:
        """Destroy the shadow copy and release the lock.

        Returns:
            OperationResult with success/error

        """
        with self._lock:
            try:
                self._cleanup_shadow_dirs()
                return OperationResult(success=True)
            except Exception as e:
                logger.error("Failed to destroy shadow copy: %s", e)
                return OperationResult(success=False, error=str(e))

    def _cleanup_shadow_dirs(self) -> None:
        """Remove shadow config, lock, and snapshots."""
        if os.path.isdir(self._config_dir):
            shutil.rmtree(self._config_dir)
        if os.path.isfile(self._lock_file):
            os.remove(self._lock_file)
        if os.path.isdir(self._snapshots_dir):
            shutil.rmtree(self._snapshots_dir)

    def get_lock_status(self) -> dict:
        """Get current lock status.

        Returns:
            Dict with locked, session_id, user_name, user_email, created_at

        """
        if not os.path.isfile(self._lock_file):
            return {"locked": False}

        try:
            with open(self._lock_file, encoding="utf-8") as f:
                data = json.load(f)
            return {
                "locked": True,
                "session_id": data.get("session_id"),
                "user_name": data.get("user_name"),
                "user_email": data.get("user_email"),
                "created_at": data.get("created_at"),
            }
        except (json.JSONDecodeError, OSError):
            return {"locked": False}

    def can_modify(self, session_id: str) -> bool:
        """Check if the given session can modify the shadow copy.

        If no shadow exists, any session can start one (returns True).
        If shadow exists, only the lock owner can modify.

        Args:
            session_id: Session ID to check

        Returns:
            True if the session can modify

        """
        if not self.has_shadow():
            return True
        status = self.get_lock_status()
        if not status.get("locked"):
            return True
        return status.get("session_id") == session_id

    def break_lock(self) -> OperationResult:
        """Force-break the lock by destroying the shadow copy.

        Returns:
            OperationResult with success/error

        """
        return self.destroy_shadow()
