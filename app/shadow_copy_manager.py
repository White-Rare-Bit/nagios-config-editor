"""Shadow Copy Manager for Nagios Bulk Editor.

Replaces JSON-diff staging with a shadow copy architecture:
- Full directory copy on first edit (supports multiple config roots)
- Direct mutations on shadow copy
- File-level undo snapshots
- All-or-nothing apply back to originals
"""

import difflib
import filecmp
import hashlib
import json
import logging
import multiprocessing
import os
import shutil
import time
import uuid

from .config_discovery import PROTECTED_FILENAMES
from .nagios_model import OperationResult

logger = logging.getLogger(__name__)


class ShadowCopyManager:
    """Manages a shadow copy of Nagios config directories.

    Shadow directory layout (multi-root):
        <shadow_base>/config/<root_0>/  - Copy of first config root
        <shadow_base>/config/<root_1>/  - Copy of second config root
        <shadow_base>/root_map.json     - Maps shadow names to original paths
        <shadow_base>/lock.json         - Session lock info
        <shadow_base>/snapshots/        - Undo snapshots
        <shadow_base>/checksums.json    - Original file hashes for conflict detection
    """

    def __init__(self, config_path=None, shadow_base_path=None, *, cfg_dirs=None):
        if config_path is not None:
            self._cfg_dirs = [os.path.abspath(config_path)]
        elif cfg_dirs is not None:
            self._cfg_dirs = [os.path.abspath(d) for d in cfg_dirs]
        else:
            self._cfg_dirs = []
        self.shadow_base_path = shadow_base_path or ""
        self._lock = multiprocessing.Lock()

    @property
    def config_path(self) -> str:
        """First config root for backward compat."""
        return self._cfg_dirs[0] if self._cfg_dirs else ""

    @config_path.setter
    def config_path(self, path: str) -> None:
        """Set single config path (backward compat, replaces all dirs)."""
        self._cfg_dirs = [os.path.abspath(path)]

    @property
    def _config_dir(self) -> str:
        """Path to the shadow config directory (top level)."""
        return os.path.realpath(os.path.join(self.shadow_base_path, "config"))

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

    @property
    def _root_map_file(self) -> str:
        """Path to the root map file."""
        return os.path.join(self.shadow_base_path, "root_map.json")

    # =========================================================================
    # Root map
    # =========================================================================

    def _build_root_map(self) -> dict[str, str]:
        """Build root map: shadow_name -> original_abs_path."""
        return {
            f"root_{i}": os.path.abspath(d) for i, d in enumerate(self._cfg_dirs)
        }

    def _save_root_map(self, root_map: dict[str, str]) -> None:
        with open(self._root_map_file, "w", encoding="utf-8") as f:
            json.dump(root_map, f)

    def get_root_map(self) -> dict[str, str]:
        """Load root map from disk. Returns shadow_name -> original_abs_path."""
        if not os.path.isfile(self._root_map_file):
            return {}
        with open(self._root_map_file, encoding="utf-8") as f:
            return json.load(f)

    def _find_root_for_path(self, abs_path: str) -> tuple[str, str] | None:
        """Find which root an absolute path belongs to.

        Returns (shadow_name, original_root) or None.
        """
        root_map = self.get_root_map()
        for shadow_name, original_root in root_map.items():
            if abs_path.startswith(original_root + os.sep) or abs_path == original_root:
                return shadow_name, original_root
        return None

    def _find_shadow_root_for_path(self, abs_shadow_path: str) -> tuple[str, str] | None:
        """Find which root a shadow path belongs to.

        Returns (shadow_name, original_root) or None.
        """
        root_map = self.get_root_map()
        for shadow_name, original_root in root_map.items():
            shadow_root = os.path.join(self._config_dir, shadow_name)
            if abs_shadow_path.startswith(shadow_root + os.sep) or abs_shadow_path == shadow_root:
                return shadow_name, original_root
        return None

    @property
    def shadow_cfg_dirs(self) -> list[str]:
        """Return shadow directory paths for each config root."""
        root_map = self.get_root_map()
        return [os.path.join(self._config_dir, name) for name in sorted(root_map.keys())]

    # =========================================================================
    # Path helpers
    # =========================================================================

    def shadow_path_for(self, original_abs_path: str) -> str:
        """Map an original absolute path to its shadow equivalent."""
        result = self._find_root_for_path(original_abs_path)
        if result is None:
            # Fallback: use first root
            if self._cfg_dirs:
                rel = os.path.relpath(original_abs_path, self._cfg_dirs[0])
                return os.path.join(self._config_dir, "root_0", rel)
            return os.path.join(self._config_dir, original_abs_path)
        shadow_name, original_root = result
        rel = os.path.relpath(original_abs_path, original_root)
        return os.path.join(self._config_dir, shadow_name, rel)

    def original_path_for(self, shadow_abs_path: str) -> str:
        """Map a shadow absolute path back to the original."""
        result = self._find_shadow_root_for_path(shadow_abs_path)
        if result is None:
            return shadow_abs_path
        shadow_name, original_root = result
        shadow_root = os.path.join(self._config_dir, shadow_name)
        rel = os.path.relpath(shadow_abs_path, shadow_root)
        return os.path.join(original_root, rel)

    def shadow_path(self, relative_path: str) -> str:
        """Return absolute path to a file in the shadow config directory.

        Backward compat: uses first root (root_0).

        Args:
            relative_path: Path relative to config root (e.g. "hosts.cfg")

        Returns:
            Absolute path into shadow config dir

        """
        return os.path.join(self._config_dir, "root_0", relative_path)

    def original_path(self, relative_path: str) -> str:
        """Return absolute path to a file in the original config directory.

        Backward compat: uses first root.

        Args:
            relative_path: Path relative to config root

        Returns:
            Absolute path into original config dir

        """
        return os.path.join(self.config_path, relative_path)

    # =========================================================================
    # Hashing
    # =========================================================================

    def _hash_all_roots(self) -> dict[str, str]:
        """Hash all cfg files across all roots.

        Returns dict mapping 'shadow_name/rel_path' -> hex digest.
        """
        checksums = {}
        root_map = self._build_root_map()
        for shadow_name, original_root in root_map.items():
            if not os.path.isdir(original_root):
                continue
            for root, _dirs, files in os.walk(original_root):
                for fn in files:
                    if fn.endswith(".cfg") and fn not in PROTECTED_FILENAMES:
                        full = os.path.join(root, fn)
                        rel = os.path.relpath(full, original_root)
                        key = f"{shadow_name}/{rel}"
                        h = hashlib.sha256()
                        with open(full, "rb") as f:
                            for chunk in iter(lambda: f.read(8192), b""):
                                h.update(chunk)
                        checksums[key] = h.hexdigest()
        return checksums

    # =========================================================================
    # Shadow lifecycle
    # =========================================================================

    def has_shadow(self) -> bool:
        """Check if a shadow copy exists."""
        return os.path.isdir(self._config_dir)

    def create_shadow(self, session_id: str, user_name: str, user_email: str) -> OperationResult:
        """Create shadow copies of all config roots.

        Copies each cfg_dir into shadow_base/config/<root_N>/, filtering
        protected files. Writes root_map.json and lock.json.

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
                os.makedirs(self.shadow_base_path, exist_ok=True)
                os.makedirs(self._config_dir, exist_ok=True)

                # Build and save root map
                root_map = self._build_root_map()
                self._save_root_map(root_map)

                # Copy each root into its shadow subdir
                shadow_base_abs = os.path.abspath(self.shadow_base_path)
                for shadow_name, original_root in root_map.items():
                    shadow_subdir = os.path.join(self._config_dir, shadow_name)
                    if os.path.isdir(original_root):
                        def _ignore(directory, contents, _base=shadow_base_abs, _prot=PROTECTED_FILENAMES):
                            ignored = set()
                            for name in contents:
                                full = os.path.join(directory, name)
                                # Skip protected files
                                if name in _prot:
                                    ignored.add(name)
                                # Skip the shadow base itself (if nested in config root)
                                elif os.path.abspath(full) == _base:
                                    ignored.add(name)
                            return ignored

                        shutil.copytree(
                            original_root,
                            shadow_subdir,
                            ignore=_ignore,
                        )
                    else:
                        os.makedirs(shadow_subdir, exist_ok=True)

                # Hash original files for conflict detection
                checksums = self._hash_all_roots()
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

                logger.info("Shadow copy created for session %s by %s (%d roots)",
                            session_id, user_name, len(root_map))
                return OperationResult(success=True)

            except Exception as e:
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
        """Remove shadow config, lock, root_map, checksums, and snapshots."""
        if os.path.isdir(self._config_dir):
            shutil.rmtree(self._config_dir)
        for f in (self._lock_file, self._root_map_file, self._checksums_file):
            if os.path.isfile(f):
                os.remove(f)
        if os.path.isdir(self._snapshots_dir):
            shutil.rmtree(self._snapshots_dir)

    # =========================================================================
    # Lock management
    # =========================================================================

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
    # Undo snapshots
    # =========================================================================

    def snapshot_files(
        self,
        file_paths: list[str],
        description: str,
        moved_keys: list[str] | None = None,
        dir_paths: list[str] | None = None,
    ) -> str:
        """Take a snapshot of files before mutation for undo support.

        For each relative path, copies the file from shadow config to a
        snapshot directory. If the file doesn't exist, records it as "absent"
        so undo can delete a newly created file.

        Args:
            file_paths: List of relative paths to snapshot
            description: Human-readable description of the operation
            moved_keys: Optional stable keys of objects being moved (for
                reorder highlighting). Uses relative paths.

        Returns:
            Snapshot UUID

        """
        snapshot_id = f"{time.time():.6f}_{uuid.uuid4().hex[:8]}"
        snapshot_dir = os.path.join(self._snapshots_dir, snapshot_id)
        files_dir = os.path.join(snapshot_dir, "files")
        os.makedirs(files_dir, exist_ok=True)

        file_records = []
        for rel_path in file_paths:
            _orig, shadow_file = self._resolve_paths(rel_path)
            if os.path.isfile(shadow_file):
                dest = os.path.join(files_dir, rel_path)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy2(shadow_file, dest)
                file_records.append({"path": rel_path, "status": "exists"})
            else:
                file_records.append({"path": rel_path, "status": "absent"})

        dir_records = []
        for rel_path in (dir_paths or []):
            _orig, shadow_dir = self._resolve_paths(rel_path)
            if os.path.isdir(shadow_dir):
                dir_records.append({"path": rel_path, "status": "exists"})
            else:
                dir_records.append({"path": rel_path, "status": "absent"})

        meta: dict = {
            "description": description,
            "timestamp": time.time(),
            "files": file_records,
        }
        if moved_keys:
            meta["moved_keys"] = moved_keys
        if dir_records:
            meta["dirs"] = dir_records
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
                    _orig, shadow_file = self._resolve_paths(rel_path)

                    if file_record["status"] == "absent":
                        if os.path.isfile(shadow_file):
                            os.remove(shadow_file)
                    else:
                        src = os.path.join(files_dir, rel_path)
                        os.makedirs(os.path.dirname(shadow_file), exist_ok=True)
                        shutil.copy2(src, shadow_file)

                # Undo directory creation (remove dirs that were absent before)
                for dir_record in meta.get("dirs", []):
                    rel_path = dir_record["path"]
                    _orig, shadow_dir = self._resolve_paths(rel_path)
                    if dir_record["status"] == "absent" and os.path.isdir(shadow_dir):
                        try:
                            os.rmdir(shadow_dir)  # Only removes empty dirs
                        except OSError:
                            pass  # Dir not empty — leave it

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

    def _collect_files_for_root(self, directory: str) -> set[str]:
        """Collect all file paths relative to directory."""
        result = set()
        if not os.path.isdir(directory):
            return result
        for dirpath, _dirnames, filenames in os.walk(directory):
            for filename in filenames:
                full = os.path.join(dirpath, filename)
                rel = os.path.relpath(full, directory)
                result.add(rel)
        return result

    @staticmethod
    def _collect_dirs_for_root(directory: str) -> set[str]:
        """Collect all directory paths relative to directory."""
        result = set()
        if not os.path.isdir(directory):
            return result
        for dirpath, dirnames, _filenames in os.walk(directory):
            for d in dirnames:
                full = os.path.join(dirpath, d)
                rel = os.path.relpath(full, directory)
                result.add(rel)
        return result

    def get_changed_files(self) -> list[dict]:
        """Compute file-level diff between shadow and originals across all roots.

        Returns:
            List of dicts with 'path' (shadow_name/rel) and 'status' (added/modified/deleted)

        """
        if not self.has_shadow():
            return []

        root_map = self.get_root_map()
        changes = []

        for shadow_name, original_root in root_map.items():
            shadow_subdir = os.path.join(self._config_dir, shadow_name)
            display_root = os.path.basename(original_root)
            original_files = self._collect_files_for_root(original_root)
            shadow_files = self._collect_files_for_root(shadow_subdir)

            # Filter out protected files from original (they weren't copied)
            original_files = {f for f in original_files
                              if os.path.basename(f) not in PROTECTED_FILENAMES}

            for f in sorted(shadow_files - original_files):
                changes.append({"path": f"{shadow_name}/{f}", "display_path": f"{display_root}/{f}", "status": "added"})

            for f in sorted(original_files - shadow_files):
                changes.append({"path": f"{shadow_name}/{f}", "display_path": f"{display_root}/{f}", "status": "deleted"})

            for f in sorted(original_files & shadow_files):
                orig = os.path.join(original_root, f)
                shad = os.path.join(shadow_subdir, f)
                if not filecmp.cmp(orig, shad, shallow=False):
                    changes.append({"path": f"{shadow_name}/{f}", "display_path": f"{display_root}/{f}", "status": "modified"})

            # Detect new empty directories
            original_dirs = self._collect_dirs_for_root(original_root)
            shadow_dirs = self._collect_dirs_for_root(shadow_subdir)
            for d in sorted(shadow_dirs - original_dirs):
                # Only report if the directory has no files (non-empty dirs covered by file changes)
                dir_abs = os.path.join(shadow_subdir, d)
                if not any(os.path.join(shadow_subdir, f).startswith(dir_abs + os.sep) for f in shadow_files):
                    changes.append({
                        "path": f"{shadow_name}/{d}",
                        "display_path": f"{display_root}/{d}",
                        "status": "added",
                        "is_dir": True,
                    })

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

        if current_block:
            chunks.extend(current_block)

        return chunks

    def _resolve_paths(self, composite_path: str) -> tuple[str, str]:
        """Resolve a composite path (shadow_name/rel) to original and shadow absolute paths.

        For composite paths like 'root_0/hosts.cfg', splits into shadow_name and
        relative path, then resolves using the root map.

        Args:
            composite_path: Either a composite 'shadow_name/rel' path or a simple relative path

        Returns:
            Tuple of (original_abs_path, shadow_abs_path)

        """
        root_map = self.get_root_map()
        # Check if path starts with a known shadow name
        for shadow_name, original_root in root_map.items():
            prefix = shadow_name + "/"
            if composite_path.startswith(prefix):
                rel = composite_path[len(prefix):]
                orig = os.path.join(original_root, rel)
                shad = os.path.join(self._config_dir, shadow_name, rel)
                return orig, shad
        # Fallback: use backward-compat methods
        return self.original_path(composite_path), self.shadow_path(composite_path)

    def get_file_diff(self, relative_path: str, context_lines: int = 3,
                      display_path: str = "") -> dict:
        """Compute unified diff for a single file.

        Uses object-aware chunking so that each 'define type { ... }' block
        is treated as an atomic unit, preventing the diff algorithm from
        splitting object boundaries.

        Args:
            relative_path: Path relative to config root (or shadow_name/rel for multi-root)
            context_lines: Number of context lines around changes (default 3)

        Returns:
            Dict with 'diff_text' containing unified diff string

        """
        orig, shad = self._resolve_paths(relative_path)
        label = display_path or relative_path

        for path in (orig, shad):
            if os.path.isfile(path):
                with open(path, "rb") as f:
                    if b"\x00" in f.read(8192):
                        return {"diff_text": f"Binary file {label}\n"}

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
            fromfile=f"a/{label}",
            tofile=f"b/{label}",
            n=context_lines,
        )

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

    def get_changed_object_keys(self) -> list[str]:
        """Return stable keys of all changed Nagios objects between shadow and originals.

        Parses both original and shadow directories and compares objects by stable key.
        Also includes moved keys recorded in snapshot metadata.

        Returns:
            List of stable keys for added, modified, deleted, or moved objects

        """
        from .nagios_parser import NagiosConfigParser
        from .stable_keys import generate_stable_key

        if not self.has_shadow():
            return []

        root_map = self.get_root_map()

        def _build_object_map(cfg_dirs: list[str]) -> dict[str, dict]:
            parser = NagiosConfigParser(cfg_dirs=cfg_dirs)
            objects = parser.parse_all()
            obj_map = {}
            for obj in objects:
                # Find which root this file belongs to for relative path
                for d in cfg_dirs:
                    abs_d = os.path.abspath(d)
                    if obj.source_file.startswith(abs_d):
                        rel_path = os.path.relpath(obj.source_file, abs_d)
                        break
                else:
                    rel_path = os.path.basename(obj.source_file)
                key = generate_stable_key(rel_path, obj.object_type, obj.get_display_name())
                obj_map[key] = dict(obj.attributes)
            return obj_map

        original_dirs = list(root_map.values())
        shadow_dirs = [os.path.join(self._config_dir, name) for name in sorted(root_map.keys())]

        orig_map = _build_object_map(original_dirs)
        shadow_map = _build_object_map(shadow_dirs)

        changed = []
        changed.extend(sorted(shadow_map.keys() - orig_map.keys()))
        changed.extend(sorted(orig_map.keys() - shadow_map.keys()))
        for key in sorted(orig_map.keys() & shadow_map.keys()):
            if orig_map[key] != shadow_map[key]:
                changed.append(key)

        # Include moved keys from snapshot metadata
        changed_set = set(changed)
        if os.path.isdir(self._snapshots_dir):
            for snap_name in os.listdir(self._snapshots_dir):
                meta_path = os.path.join(self._snapshots_dir, snap_name, "meta.json")
                if not os.path.isfile(meta_path):
                    continue
                try:
                    with open(meta_path, encoding="utf-8") as f:
                        meta = json.load(f)
                    for key in meta.get("moved_keys", []):
                        if key not in changed_set:
                            changed.append(key)
                            changed_set.add(key)
                except (OSError, json.JSONDecodeError):
                    continue

        return changed

    def get_changed_object_count(self) -> int:
        """Count the number of changed Nagios objects between shadow and originals."""
        return len(self.get_changed_object_keys())

    # =========================================================================
    # Conflict Detection
    # =========================================================================

    def _detect_conflicts(self) -> list[str]:
        """Compare current originals against stored checksums.

        Returns:
            List of relative paths that have changed externally.
            Empty list if checksums.json doesn't exist (backward compat).
        """
        if not os.path.isfile(self._checksums_file):
            return []

        with open(self._checksums_file, encoding="utf-8") as f:
            stored = json.load(f)

        current = self._hash_all_roots()
        conflicts = []
        for key, original_hash in stored.items():
            current_hash = current.get(key)
            if current_hash is None:
                conflicts.append(key)
            elif current_hash != original_hash:
                conflicts.append(key)
        return conflicts

    # =========================================================================
    # Apply
    # =========================================================================

    def apply(self, backup_manager=None, force: bool = False) -> OperationResult:
        """Apply shadow changes back to the original config directories.

        Checks for external modifications first (unless force=True).
        For each root, copies changed files from shadow back to original,
        removes deleted files, then destroys the shadow copy.

        Args:
            backup_manager: Optional BackupManager to create pre-apply backup
            force: If True, skip conflict detection and overwrite

        Returns:
            OperationResult with data={'changed_files': [...]} on success

        """
        with self._lock:
            if not self.has_shadow():
                return OperationResult(success=True, data={"changed_files": []})

            try:
                if not force:
                    conflicts = self._detect_conflicts()
                    if conflicts:
                        return OperationResult(
                            success=False,
                            error="conflicts",
                            data={"conflicts": conflicts},
                        )

                changed = self.get_changed_files()

                if backup_manager and changed:
                    backup_manager.create_backup("pre_shadow_apply")

                root_map = self.get_root_map()

                for change in changed:
                    composite_path = change["path"]
                    # Parse shadow_name/rel_path
                    parts = composite_path.split("/", 1)
                    if len(parts) != 2:
                        continue
                    shadow_name, rel_path = parts
                    original_root = root_map.get(shadow_name, "")
                    if not original_root:
                        continue

                    orig = os.path.join(original_root, rel_path)
                    shad = os.path.join(self._config_dir, shadow_name, rel_path)

                    if change.get("is_dir"):
                        if change["status"] == "added":
                            os.makedirs(orig, exist_ok=True)
                    elif change["status"] == "deleted":
                        if os.path.isfile(orig):
                            os.remove(orig)
                            parent = os.path.dirname(orig)
                            while parent != original_root:
                                if os.path.isdir(parent) and not os.listdir(parent):
                                    os.rmdir(parent)
                                    parent = os.path.dirname(parent)
                                else:
                                    break

                    elif change["status"] in ("added", "modified"):
                        os.makedirs(os.path.dirname(orig), exist_ok=True)
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

                logger.info("Applied %d changed files", len(changed))

            except Exception as e:
                logger.error("Failed to apply shadow changes: %s", e)
                return OperationResult(success=False, error=str(e))

        # Destroy shadow (outside the lock since destroy_shadow acquires it)
        self.destroy_shadow()
        return OperationResult(success=True, data={"changed_files": changed})
