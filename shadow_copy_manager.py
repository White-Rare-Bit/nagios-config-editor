"""Shadow Copy Manager for Nagios Bulk Editor.

Replaces JSON-diff staging with a shadow copy architecture:
- Full directory copy on first edit
- Direct mutations on shadow copy
- File-level undo snapshots
- All-or-nothing apply back to original
"""

import difflib
import filecmp
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

    @property
    def _checksums_file(self) -> str:
        """Path to the original-file checksums."""
        return os.path.join(self.shadow_base_path, "checksums.json")

    @staticmethod
    def _hash_cfg_files(directory: str) -> dict[str, str]:
        """Compute SHA-256 hashes of all .cfg files in directory.

        Returns:
            Dict mapping relative paths to hex digest strings
        """
        import hashlib
        checksums = {}
        for root, _dirs, files in os.walk(directory):
            for fn in files:
                if fn.endswith(".cfg"):
                    full = os.path.join(root, fn)
                    rel = os.path.relpath(full, directory)
                    h = hashlib.sha256()
                    with open(full, "rb") as f:
                        for chunk in iter(lambda: f.read(8192), b""):
                            h.update(chunk)
                    checksums[rel] = h.hexdigest()
        return checksums

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

                # Hash original files for conflict detection at apply time
                os.makedirs(self.shadow_base_path, exist_ok=True)
                checksums = self._hash_cfg_files(self.config_path)
                with open(self._checksums_file, "w", encoding="utf-8") as f:
                    json.dump(checksums, f)

                # Write lock file
                lock_data = {
                    "session_id": session_id,
                    "user_name": user_name,
                    "user_email": user_email,
                    "created_at": time.time(),
                }
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

    # =========================================================================
    # Diff computation
    # =========================================================================

    def _collect_files(self, root: str) -> set[str]:
        """Collect all file paths relative to root."""
        result = set()
        for dirpath, _dirnames, filenames in os.walk(root):
            for filename in filenames:
                full = os.path.join(dirpath, filename)
                rel = os.path.relpath(full, root)
                result.add(rel)
        return result

    def get_changed_files(self) -> list[dict]:
        """Compute file-level diff between shadow and original.

        Returns:
            List of dicts with 'path' and 'status' (added/modified/deleted)

        """
        if not self.has_shadow():
            return []

        original_files = self._collect_files(self.config_path)
        shadow_files = self._collect_files(self._config_dir)

        changes = []

        # Files in shadow but not in original → added
        for f in sorted(shadow_files - original_files):
            changes.append({"path": f, "status": "added"})

        # Files in original but not in shadow → deleted
        for f in sorted(original_files - shadow_files):
            changes.append({"path": f, "status": "deleted"})

        # Files in both → check for modifications
        for f in sorted(original_files & shadow_files):
            orig = self.original_path(f)
            shad = self.shadow_path(f)
            if not filecmp.cmp(orig, shad, shallow=False):
                changes.append({"path": f, "status": "modified"})

        return changes

    @staticmethod
    def _chunk_by_objects(lines: list[str]) -> list[str]:
        """Group lines into object-level chunks for diffing.

        Each 'define type { ... }' block becomes a single string (one "line"
        for difflib). Lines between objects stay individual. This prevents
        the diff algorithm from matching identical 'define type {' lines
        across different objects.
        """
        chunks = []
        current_block = []
        in_block = False

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("define ") and stripped.endswith("{"):
                in_block = True
                current_block = [line]
            elif in_block:
                current_block.append(line)
                if stripped == "}":
                    chunks.append("".join(current_block))
                    current_block = []
                    in_block = False
            else:
                chunks.append(line)

        # If file ended mid-block (malformed), flush remaining
        if current_block:
            chunks.extend(current_block)

        return chunks

    def get_file_diff(self, relative_path: str, context_lines: int = 3) -> dict:
        """Compute unified diff for a single file.

        Uses object-aware chunking so that each 'define type { ... }' block
        is treated as an atomic unit, preventing the diff algorithm from
        splitting object boundaries.

        Args:
            relative_path: Path relative to config root
            context_lines: Number of context lines around changes (default 3)

        Returns:
            Dict with 'diff_text' containing unified diff string

        """
        orig = self.original_path(relative_path)
        shad = self.shadow_path(relative_path)

        orig_lines = []
        shad_lines = []

        if os.path.isfile(orig):
            with open(orig, encoding="utf-8", errors="replace") as f:
                orig_lines = f.readlines()
        if os.path.isfile(shad):
            with open(shad, encoding="utf-8", errors="replace") as f:
                shad_lines = f.readlines()

        orig_chunks = self._chunk_by_objects(orig_lines)
        shad_chunks = self._chunk_by_objects(shad_lines)

        diff = difflib.unified_diff(
            orig_chunks,
            shad_chunks,
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
            n=context_lines,
        )

        # Expand multi-line chunks back to individual lines with correct prefixes
        result_lines = []
        for diff_line in diff:
            if diff_line.startswith("---") or diff_line.startswith("+++") or diff_line.startswith("@@"):
                result_lines.append(diff_line)
            elif diff_line.startswith("+") or diff_line.startswith("-"):
                prefix = diff_line[0]
                content = diff_line[1:]
                for sub_line in content.splitlines(True):
                    result_lines.append(prefix + sub_line)
            elif diff_line.startswith(" "):
                content = diff_line[1:]
                for sub_line in content.splitlines(True):
                    result_lines.append(" " + sub_line)
            else:
                result_lines.append(diff_line)

        return {"diff_text": "".join(result_lines)}

    def get_changed_object_count(self) -> int:
        """Count the number of changed Nagios objects between shadow and original.

        Parses both directories and compares objects by stable key.

        Returns:
            Number of added, modified, or deleted objects

        """
        from nagios_parser import NagiosConfigParser
        from stable_keys import generate_stable_key

        def _build_object_map(config_path: str) -> dict[str, dict]:
            parser = NagiosConfigParser(config_path)
            objects = parser.parse_all()
            obj_map = {}
            for obj in objects:
                rel_path = os.path.relpath(obj.source_file, config_path)
                key = generate_stable_key(rel_path, obj.object_type, obj.get_display_name())
                obj_map[key] = dict(obj.attributes)
            return obj_map

        orig_map = _build_object_map(self.config_path)
        shadow_map = _build_object_map(self._config_dir)

        count = 0
        # Added objects
        count += len(shadow_map.keys() - orig_map.keys())
        # Deleted objects
        count += len(orig_map.keys() - shadow_map.keys())
        # Modified objects
        for key in orig_map.keys() & shadow_map.keys():
            if orig_map[key] != shadow_map[key]:
                count += 1

        return count

    # =========================================================================
    # Apply
    # =========================================================================

    def apply(self, backup_manager=None) -> OperationResult:
        """Apply shadow changes back to the original config directory.

        Copies changed files from shadow to original, removes deleted files,
        then destroys the shadow copy.

        Args:
            backup_manager: Optional BackupManager to create pre-apply backup

        Returns:
            OperationResult with data={'changed_files': [...]} on success

        """
        with self._lock:
            if not self.has_shadow():
                # No shadow — nothing to apply, still success
                return OperationResult(success=True, data={"changed_files": []})

            try:
                changed = self.get_changed_files()

                # Create backup before applying if manager provided and there are changes
                if backup_manager and changed:
                    backup_manager.create_backup("pre_shadow_apply")

                for change in changed:
                    rel_path = change["path"]
                    orig = self.original_path(rel_path)
                    shad = self.shadow_path(rel_path)

                    if change["status"] == "deleted":
                        if os.path.isfile(orig):
                            os.remove(orig)
                            # Remove empty parent directories
                            parent = os.path.dirname(orig)
                            while parent != self.config_path:
                                if os.path.isdir(parent) and not os.listdir(parent):
                                    os.rmdir(parent)
                                    parent = os.path.dirname(parent)
                                else:
                                    break

                    elif change["status"] in ("added", "modified"):
                        # Ensure parent directory exists
                        os.makedirs(os.path.dirname(orig), exist_ok=True)
                        # Atomic copy: write to temp, then replace
                        import tempfile as _tempfile
                        fd, tmp_path = _tempfile.mkstemp(
                            dir=os.path.dirname(orig),
                            suffix=".tmp",
                        )
                        try:
                            with os.fdopen(fd, "wb") as tmp_f:
                                with open(shad, "rb") as src_f:
                                    shutil.copyfileobj(src_f, tmp_f)
                                tmp_f.flush()
                                os.fsync(tmp_f.fileno())
                            os.replace(tmp_path, orig)
                        except:
                            if os.path.exists(tmp_path):
                                os.unlink(tmp_path)
                            raise

                # Handle new directories from shadow that may be empty
                for dirpath, dirnames, filenames in os.walk(self._config_dir):
                    rel_dir = os.path.relpath(dirpath, self._config_dir)
                    orig_dir = os.path.join(self.config_path, rel_dir)
                    if not os.path.isdir(orig_dir):
                        os.makedirs(orig_dir, exist_ok=True)

                logger.info("Applied %d changed files", len(changed))

            except Exception as e:
                logger.error("Failed to apply shadow changes: %s", e)
                return OperationResult(success=False, error=str(e))

        # Destroy shadow (outside the lock since destroy_shadow acquires it)
        self.destroy_shadow()
        return OperationResult(success=True, data={"changed_files": changed})
