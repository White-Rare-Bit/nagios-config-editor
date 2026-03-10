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
import uuid

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

    # =========================================================================
    # Path helpers
    # =========================================================================

    def shadow_path(self, relative_path: str) -> str:
        """Return absolute path to a file in the shadow config directory.

        Args:
            relative_path: Path relative to config root (e.g. "hosts.cfg")

        Returns:
            Absolute path into shadow config dir

        """
        return os.path.join(self._config_dir, relative_path)

    def original_path(self, relative_path: str) -> str:
        """Return absolute path to a file in the original config directory.

        Args:
            relative_path: Path relative to config root

        Returns:
            Absolute path into original config dir

        """
        return os.path.join(self.config_path, relative_path)

    # =========================================================================
    # Undo snapshots
    # =========================================================================

    def snapshot_files(self, file_paths: list[str], description: str) -> str:
        """Take a snapshot of files before mutation for undo support.

        For each relative path, copies the file from shadow config to a
        snapshot directory. If the file doesn't exist, records it as "absent"
        so undo can delete a newly created file.

        Args:
            file_paths: List of relative paths to snapshot
            description: Human-readable description of the operation

        Returns:
            Snapshot UUID

        """
        snapshot_id = f"{time.time():.6f}_{uuid.uuid4().hex[:8]}"
        snapshot_dir = os.path.join(self._snapshots_dir, snapshot_id)
        files_dir = os.path.join(snapshot_dir, "files")
        os.makedirs(files_dir, exist_ok=True)

        file_records = []
        for rel_path in file_paths:
            src = self.shadow_path(rel_path)
            if os.path.isfile(src):
                # Copy existing file to snapshot
                dest = os.path.join(files_dir, rel_path)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy2(src, dest)
                file_records.append({"path": rel_path, "status": "exists"})
            else:
                # File doesn't exist yet — record as absent for creation undo
                file_records.append({"path": rel_path, "status": "absent"})

        # Write metadata
        meta = {
            "description": description,
            "timestamp": time.time(),
            "files": file_records,
        }
        with open(os.path.join(snapshot_dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f)

        return snapshot_id

    def undo(self) -> OperationResult:
        """Undo the most recent operation by restoring from snapshot.

        Returns:
            OperationResult with success/error

        """
        with self._lock:
            if not os.path.isdir(self._snapshots_dir):
                return OperationResult(success=False, error="No undo history")

            snapshots = sorted(os.listdir(self._snapshots_dir))
            if not snapshots:
                return OperationResult(success=False, error="No undo history")

            latest = snapshots[-1]
            snapshot_dir = os.path.join(self._snapshots_dir, latest)
            meta_path = os.path.join(snapshot_dir, "meta.json")

            try:
                with open(meta_path, encoding="utf-8") as f:
                    meta = json.load(f)

                files_dir = os.path.join(snapshot_dir, "files")
                for file_record in meta["files"]:
                    rel_path = file_record["path"]
                    shadow_file = self.shadow_path(rel_path)

                    if file_record["status"] == "absent":
                        # File was absent before — delete it to undo creation
                        if os.path.isfile(shadow_file):
                            os.remove(shadow_file)
                    else:
                        # Restore file from snapshot
                        src = os.path.join(files_dir, rel_path)
                        os.makedirs(os.path.dirname(shadow_file), exist_ok=True)
                        shutil.copy2(src, shadow_file)

                # Remove the snapshot
                shutil.rmtree(snapshot_dir)

                logger.info("Undo applied: %s", meta.get("description", ""))
                return OperationResult(success=True)

            except Exception as e:
                logger.error("Failed to undo: %s", e)
                return OperationResult(success=False, error=str(e))

    def get_undo_count(self) -> int:
        """Return the number of available undo operations."""
        if not os.path.isdir(self._snapshots_dir):
            return 0
        return len([
            d for d in os.listdir(self._snapshots_dir)
            if os.path.isdir(os.path.join(self._snapshots_dir, d))
        ])
